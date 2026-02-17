"""2dfan.com 签到模块 — 使用 nodriver 自动化 Chrome 完成签到。

流程：启动 Chrome → 设置 cookie → 通过 Cloudflare → 等待 Turnstile → 点击签到
三级降级策略：Turnstile 自动解决 → 直接 POST → 移除验证码后表单提交
"""

import json
import logging
import os
import re

import nodriver as uc

logger = logging.getLogger(__name__)

_CF_TITLES = ["Just a moment", "请稍候"]
_CHROME_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chrome_profile")

# 注入浏览器的 AJAX 拦截器，同时拦截 XHR 和 fetch
_INTERCEPTOR_JS = """
window.__checkinJSON = null;
window.__checkinRaw = null;
(function() {
    var _open = XMLHttpRequest.prototype.open;
    var _send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(m, url) {
        this._url = url;
        return _open.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
        this.addEventListener('load', function() {
            if (this._url && this._url.includes('/checkins')) {
                window.__checkinRaw = this.responseText;
                try { window.__checkinJSON = JSON.parse(this.responseText); } catch(e) {}
            }
        });
        return _send.apply(this, arguments);
    };
    var _fetch = window.fetch;
    window.fetch = function(url) {
        return _fetch.apply(this, arguments).then(function(resp) {
            if (url && url.toString().includes('/checkins')) {
                resp.clone().text().then(function(t) {
                    window.__checkinRaw = t;
                    try { window.__checkinJSON = JSON.parse(t); } catch(e) {}
                });
            }
            return resp;
        });
    };
})();
"""

# 获取按钮状态的 JS
_BTN_STATE_JS = """
(() => {
    var b = document.getElementById('do_checkin');
    if (!b) return null;
    return JSON.stringify({
        text: b.textContent.trim(),
        cls: b.className,
        disabled: b.disabled
    });
})()
"""

# 获取表单文本的 JS
_FORM_TEXT_JS = """
(() => {
    var f = document.getElementById('checkin');
    return f ? f.textContent : '';
})()
"""


class CheckinResult:
    def __init__(self, checkins_count: int = -1, serial_checkins: int = -1):
        self.checkins_count = checkins_count
        self.serial_checkins = serial_checkins


# ── Cloudflare 挑战处理 ───────────────────────────────────────────


async def _on_cf_challenge(tab) -> bool:
    try:
        title = await tab.evaluate("document.title")
        return any(kw in (title or "") for kw in _CF_TITLES)
    except Exception:
        return True


async def _pass_cf_challenge(tab, timeout: int = 90) -> bool:
    for sec in range(timeout):
        if not await _on_cf_challenge(tab):
            logger.info("Cloudflare 验证通过（%d 秒）", sec)
            return True
        if sec % 10 == 0:
            logger.info("等待 Cloudflare 验证... (%d/%ds)", sec, timeout)
        await tab.sleep(1)
    return False


# ── 页面状态检测 ──────────────────────────────────────────────────


async def _get_btn_state(tab) -> dict | None:
    raw = await tab.evaluate(_BTN_STATE_JS)
    if not raw:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw


async def _check_already_done(tab) -> bool:
    """检查表单文本是否显示已签到"""
    text = await tab.evaluate(_FORM_TEXT_JS)
    return bool(text and "已签到" in text)


def _extract_serial_days(text: str) -> int:
    m = re.search(r"连续签到\s*(\d+)", text or "")
    return int(m.group(1)) if m else -1


# ── 结果解析 ─────────────────────────────────────────────────────


def _parse_text(text: str) -> CheckinResult | None:
    """从任意文本中提取签到结果"""
    if not text:
        return None
    # JSON 结构
    m = re.search(
        r'"checkins_count"\s*:\s*(\d+).*?"serial_checkins"\s*:\s*(\d+)', text
    )
    if m:
        return CheckinResult(int(m.group(1)), int(m.group(2)))
    # 中文关键词
    c = re.search(r"累[计積].*?(\d+)", text)
    s = re.search(r"连[续續].*?(\d+)", text)
    if c and s:
        return CheckinResult(int(c.group(1)), int(s.group(1)))
    if "签到成功" in text:
        return CheckinResult()
    return None


async def _read_intercepted(tab) -> CheckinResult | None:
    """从拦截器变量中读取签到结果"""
    jr = await tab.evaluate("window.__checkinJSON")
    if isinstance(jr, dict) and "checkins_count" in jr:
        return CheckinResult(jr.get("checkins_count", -1), jr.get("serial_checkins", -1))
    raw = await tab.evaluate("window.__checkinRaw")
    if isinstance(raw, str):
        logger.info("AJAX 原始响应: %.300s", raw)
        return _parse_text(raw)
    return None


# ── 签到提交策略 ─────────────────────────────────────────────────


async def _submit_normal(tab) -> CheckinResult | None:
    """策略1: Turnstile 已解决 → 注入拦截器 → 点击按钮 → 解析"""
    await tab.evaluate(_INTERCEPTOR_JS)

    btn = await tab.query_selector("#do_checkin")
    if not btn:
        raise ValueError("签到按钮消失")

    logger.info("点击签到按钮...")
    await btn.click()
    await tab.sleep(5)

    # 拦截器捕获
    r = await _read_intercepted(tab)
    if r:
        return r

    # 按钮状态变化
    bs = await _get_btn_state(tab)
    logger.info("点击后按钮: %s", bs)
    if bs and (bs.get("disabled") or "btn-success" in bs.get("cls", "")):
        return CheckinResult()
    if bs is None and await _check_already_done(tab):
        text = await tab.evaluate(_FORM_TEXT_JS)
        return CheckinResult(serial_checkins=_extract_serial_days(text))

    # 全页面兜底
    return _parse_text(await tab.get_content())


async def _submit_fetch(tab) -> CheckinResult | None:
    """策略2: 直接 fetch POST 签到（绕过验证码）"""
    raw = await tab.evaluate("""
        (async () => {
            try {
                var c = document.querySelector('meta[name="csrf-token"]').content;
                var r = await fetch('/checkins', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRF-Token': c,
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json, text/javascript, */*'
                    },
                    body: 'authenticity_token=' + encodeURIComponent(c) + '&format=json',
                    credentials: 'include'
                });
                return JSON.stringify({status: r.status, body: await r.text()});
            } catch(e) {
                return JSON.stringify({error: e.message});
            }
        })()
    """)
    if not raw:
        return None
    data = json.loads(raw) if isinstance(raw, str) else raw
    if data.get("error") or data.get("status") != 200:
        logger.warning(
            "fetch POST: status=%s err=%s body=%.300s",
            data.get("status"), data.get("error"), data.get("body", ""),
        )
        return None
    body = data.get("body", "")
    try:
        j = json.loads(body)
        if isinstance(j, dict) and "checkins_count" in j:
            return CheckinResult(j["checkins_count"], j.get("serial_checkins", -1))
    except (json.JSONDecodeError, TypeError):
        pass
    return _parse_text(body)


async def _submit_no_captcha(tab) -> CheckinResult | None:
    """策略3: 移除 captcha-wrapper 后通过表单提交"""
    await tab.evaluate(_INTERCEPTOR_JS)
    await tab.evaluate(
        "var w = document.getElementById('captcha-wrapper'); if (w) w.remove();"
    )
    btn = await tab.query_selector("#do_checkin")
    if not btn:
        return None

    logger.info("点击签到按钮（跳过验证码）...")
    await btn.click()

    for _ in range(15):
        r = await _read_intercepted(tab)
        if r:
            return r
        await tab.sleep(1)
    return None


# ── Turnstile 处理 ───────────────────────────────────────────────


async def _wait_turnstile(tab, timeout: int = 20) -> bool:
    """等待页面 Turnstile 自动解决，期间尝试 verify_cf 辅助"""
    try:
        await tab.verify_cf()
    except Exception:
        pass

    for sec in range(timeout):
        solved = await tab.evaluate(
            '!!document.querySelector(\'input[name="cf-turnstile-response"]\')?.value'
        )
        if solved:
            logger.info("Turnstile 解决（%ds）", sec)
            return True
        if sec % 5 == 0:
            logger.info("等待 Turnstile... (%d/%ds)", sec, timeout)
        if sec == 10:
            try:
                await tab.verify_cf()
            except Exception:
                pass
        await tab.sleep(1)
    return False


# ── 主入口 ───────────────────────────────────────────────────────


async def checkin(user_id: str, session_cookie: str) -> CheckinResult | None:
    """
    执行 2dfan.com 签到。

    Returns:
        CheckinResult  签到成功（含累计/连续天数）
        None           今日已签到，无需操作
    Raises:
        RuntimeError   Cloudflare 验证超时
        ValueError     页面异常（找不到签到按钮）
    """
    browser = await uc.start(user_data_dir=_CHROME_PROFILE)
    try:
        tab = await browser.get("about:blank")

        # 设置 session cookie
        await tab.send(uc.cdp.network.set_cookie(
            name="_project_hgc_session",
            value=session_cookie,
            domain=".2dfan.com",
            path="/",
            secure=True,
            http_only=True,
        ))

        # 导航
        tab = await browser.get(f"https://2dfan.com/users/{user_id}/recheckin")
        await tab.sleep(3)

        # Cloudflare 挑战
        if await _on_cf_challenge(tab):
            logger.info("检测到 Cloudflare 挑战")
            try:
                await tab.verify_cf()
            except Exception as e:
                logger.warning("verify_cf: %s", e)
            if not await _pass_cf_challenge(tab):
                raise RuntimeError("Cloudflare 验证超时")
        else:
            logger.info("无 Cloudflare 挑战")

        await tab.sleep(3)
        logger.info("页面: %s", await tab.evaluate("location.href"))

        # 检查按钮
        bs = await _get_btn_state(tab)
        logger.info("按钮: %s", bs)

        if bs is None:
            if await _check_already_done(tab):
                logger.info("今日已签到")
                return None
            raise ValueError("找不到签到按钮，页面可能未正确加载")

        if bs.get("disabled") or "btn-success" in bs.get("cls", ""):
            logger.info("今日已签到")
            return None

        # ── 执行签到（三级降级） ──

        logger.info("[1/3] 等待 Turnstile...")
        if await _wait_turnstile(tab):
            return await _submit_normal(tab)

        logger.info("[2/3] 直接 POST...")
        r = await _submit_fetch(tab)
        if r:
            return r

        logger.info("[3/3] 移除验证码后提交...")
        r = await _submit_no_captcha(tab)
        if r:
            return r

        logger.error("所有签到策略均失败")
        with open(f"debug_{user_id}.html", "w", encoding="utf-8") as f:
            f.write(await tab.get_content())
        return None

    finally:
        browser.stop()
