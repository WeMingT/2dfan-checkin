"""
FlareSolverr + WARP 签到模块
使用 FlareSolverr 服务绕过 Cloudflare 保护，配合 WARP 代理解决数据中心 IP 封锁

签到提交采用 curl_cffi 混合模式：
- FlareSolverr 负责通过 Cloudflare 验证并获取 cookies
- curl_cffi 发送真正的 AJAX 请求绕过 HTTP 406 问题
"""

import os
import re
import time
import socket
import requests
from typing import Optional, Dict, List
from dataclasses import dataclass
from urllib.parse import urlparse
from curl_cffi import requests as cffi_requests


@dataclass
class CheckinResult:
    """签到结果"""
    checkins_count: int
    serial_checkins: int
    error: str = ""


class FlareSolverrCheckin:
    """FlareSolverr + WARP 签到实现"""

    def __init__(
        self,
        user_id: str,
        session_cookie: str,
        flaresolverr_url: str,
        warp_proxy: str = "socks5://127.0.0.1:40000",
        host: str = "2dfan.com",
        captcha_service=None
    ):
        self.user_id = user_id
        self.session_cookie = session_cookie
        # 规范化 URL：确保以 /v1 结尾
        url = flaresolverr_url.rstrip('/')
        if not url.endswith('/v1'):
            url = url + '/v1'
        self.flaresolverr_url = url
        self._flare_host = urlparse(self.flaresolverr_url).hostname
        self.warp_proxy = self._normalize_proxy_url(warp_proxy, env_name='WARP_PROXY') if warp_proxy else None
        self._raw_warp_proxy = warp_proxy
        self._http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
        self._https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')

        raw_public = os.environ.get('WARP_PUBLIC_PROXY') or os.environ.get('WARP_REMOTE_PROXY')
        self.warp_public_proxy = self._normalize_proxy_url(raw_public, env_name='WARP_PUBLIC_PROXY')
        if os.environ.get('WARP_REMOTE_PROXY') and not os.environ.get('WARP_PUBLIC_PROXY'):
            print("  警告: WARP_REMOTE_PROXY 已弃用，请改用 WARP_PUBLIC_PROXY")

        self.host = host
        self.captcha_service = captcha_service
        self.session_id: Optional[str] = None
        timeout_env = os.environ.get('WARP_PROXY_PROBE_TIMEOUT', '3')
        try:
            self.proxy_probe_timeout = max(1, int(timeout_env))
        except ValueError:
            raise ValueError("WARP_PROXY_PROBE_TIMEOUT 必须是整数")
        self.request_timeout = 60

        if self._is_loopback(self._raw_warp_proxy) and self._flare_host and self._flare_host not in ('127.0.0.1', 'localhost', '0.0.0.0', '::1') and not self.warp_public_proxy:
            print("  提示: FlareSolverr 运行在远程主机，但 WARP_PROXY 仅监听本地，请通过 SSH 隧道或设置 WARP_PUBLIC_PROXY 暴露 WARP 端口")

    def _is_loopback(self, proxy_url: Optional[str]) -> bool:
        if not proxy_url:
            return False
        parsed = urlparse(proxy_url)
        return parsed.hostname in ('127.0.0.1', 'localhost', '0.0.0.0', '::1')

    def _get_flaresolverr_host(self) -> Optional[str]:
        return self._flare_host

    def _build_proxy_candidates(self) -> List["FlareSolverrCheckin.ProxyCandidate"]:
        candidates: List[FlareSolverrCheckin.ProxyCandidate] = []
        flare_host = self._get_flaresolverr_host()
        flare_is_remote = flare_host and flare_host not in ('127.0.0.1', 'localhost', '0.0.0.0')

        if self.warp_public_proxy:
            candidates.append(self.ProxyCandidate(
                label="自定义 WARP 代理",
                proxy_url=self.warp_public_proxy,
                require_probe=True,
                hint="确认 VPS 已将 warp-svc 暴露或通过 SSH 隧道映射",
                stop_on_fail=True
            ))

        if not self.warp_public_proxy and os.environ.get('WARP_REMOTE_PROXY'):
            deprecated_proxy = self._normalize_proxy_url(os.environ.get('WARP_REMOTE_PROXY'), 'WARP_REMOTE_PROXY')
            candidates.append(self.ProxyCandidate(
                label="deprecated WARP_REMOTE_PROXY",
                proxy_url=deprecated_proxy,
                require_probe=True,
                hint="请改用 WARP_PUBLIC_PROXY，并确保端口已开放",
                stop_on_fail=True
            ))

        if self.warp_proxy:
            if self._is_loopback(self._raw_warp_proxy) and flare_is_remote:
                warp_parsed = urlparse(self.warp_proxy)
                remote_warp = f"{warp_parsed.scheme}://{flare_host}:{warp_parsed.port}"
                candidates.append(self.ProxyCandidate(
                    label="自动推断的远程 WARP 代理",
                    proxy_url=remote_warp,
                    require_probe=True,
                    hint="请在 VPS 上暴露 WARP 端口或通过 SSH 隧道转发",
                    stop_on_fail=False
                ))
            else:
                candidates.append(self.ProxyCandidate(
                    label="WARP 代理",
                    proxy_url=self.warp_proxy,
                    require_probe=not self._is_loopback(self._raw_warp_proxy)
                ))
        else:
            print("  警告: 未提供 WARP_PROXY，将直接尝试 HTTP 代理或直连，cf_clearance 可能失效")

        if self._https_proxy or self._http_proxy:
            fallback_proxy = self._https_proxy or self._http_proxy
            candidates.append(self.ProxyCandidate(
                label="HTTP_PROXY",
                proxy_url=fallback_proxy,
                warn_on_use="该代理出口 IP 可能与 FlareSolverr 不一致，如遇 403 请确认 WARP 端口已暴露"
            ))

        candidates.append(self.ProxyCandidate(
            label="直接连接",
            proxy_url=None,
            warn_on_use="出口 IP 必定与 FlareSolverr 不同，cf_clearance 很可能失效"
        ))

        return candidates

    def _normalize_proxy_url(self, proxy_url: Optional[str], env_name: str) -> Optional[str]:
        if not proxy_url:
            return None
        parsed = urlparse(proxy_url)
        if parsed.scheme not in ('socks5', 'socks5h'):
            raise ValueError(f"{env_name} 仅支持 socks5/socks5h 协议，如 socks5://host:port")
        if not parsed.hostname or not parsed.port:
            raise ValueError(f"{env_name} 格式无效，应为 socks5://host:port")
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"

    def _create_session(self) -> str:
        """创建 FlareSolverr 浏览器会话"""
        print("创建 FlareSolverr 会话...")
        response = requests.post(
            self.flaresolverr_url,
            json={
                "cmd": "sessions.create",
                "proxy": {"url": self.warp_proxy}
            },
            timeout=self.request_timeout
        )
        data = response.json()

        if data.get("status") != "ok":
            raise ValueError(f"创建会话失败: {data.get('message', 'unknown error')}")

        self.session_id = data["session"]
        print(f"  会话创建成功: {self.session_id}")
        return self.session_id

    def _destroy_session(self):
        """销毁 FlareSolverr 会话"""
        if not self.session_id:
            return

        try:
            print("销毁 FlareSolverr 会话...")
            requests.post(
                self.flaresolverr_url,
                json={
                    "cmd": "sessions.destroy",
                    "session": self.session_id
                },
                timeout=30
            )
            print("  会话已销毁")
        except Exception as e:
            print(f"  销毁会话失败 (可忽略): {e}")

    def _get_page(self, url: str, cookies: Optional[list] = None, max_timeout: int = 60) -> dict:
        """
        通过 FlareSolverr 获取页面

        Args:
            url: 目标 URL
            cookies: Cookie 列表，格式 [{"name": "xxx", "value": "yyy"}, ...]
            max_timeout: 最大超时时间（秒）

        Returns:
            FlareSolverr 响应数据
        """
        payload = {
            "cmd": "request.get",
            "url": url,
            "session": self.session_id,
            "maxTimeout": max_timeout * 1000
        }
        if cookies:
            payload["cookies"] = cookies

        response = requests.post(
            self.flaresolverr_url,
            json=payload,
            timeout=max_timeout + 30
        )
        data = response.json()

        if data.get("status") != "ok":
            raise ValueError(f"获取页面失败: {data.get('message', 'unknown error')}")

        return data["solution"]

    def _post_page(self, url: str, post_data: str, headers: dict = None, max_timeout: int = 60) -> dict:
        """
        通过 FlareSolverr 提交 POST 请求

        Args:
            url: 目标 URL
            post_data: POST 数据（URL 编码格式）
            headers: 自定义请求头
            max_timeout: 最大超时时间（秒）

        Returns:
            FlareSolverr 响应数据
        """
        payload = {
            "cmd": "request.post",
            "url": url,
            "session": self.session_id,
            "postData": post_data,
            "maxTimeout": max_timeout * 1000
        }
        if headers:
            payload["headers"] = headers

        response = requests.post(
            self.flaresolverr_url,
            json=payload,
            timeout=max_timeout + 30
        )
        data = response.json()

        if data.get("status") != "ok":
            raise ValueError(f"POST 请求失败: {data.get('message', 'unknown error')}")

        return data["solution"]

    def _extract_cookies(self, solution: dict) -> dict:
        """从 FlareSolverr 响应提取 cookies"""
        cookies = {}
        for cookie in solution.get("cookies", []):
            cookies[cookie["name"]] = cookie["value"]
        return cookies

    @dataclass
    class ProxyCandidate:
        label: str
        proxy_url: Optional[str]
        require_probe: bool = False
        warn_on_use: Optional[str] = None
        hint: Optional[str] = None
        stop_on_fail: bool = False

        def as_requests_proxy(self) -> Optional[Dict[str, str]]:
            if not self.proxy_url:
                return None
            return {"https": self.proxy_url, "http": self.proxy_url}

    def _probe_proxy(self, proxy_url: str) -> bool:
        """探测 socks5 代理端口连通性"""
        try:
            parsed = urlparse(proxy_url)
            if not parsed.hostname or not parsed.port:
                return False
            with socket.create_connection((parsed.hostname, parsed.port), timeout=self.proxy_probe_timeout):
                return True
        except Exception as exc:
            exc_type = type(exc).__name__
            hint = None
            if isinstance(exc, socket.gaierror):
                hint = "DNS 解析失败，请检查域名或解析是否正确"
            elif isinstance(exc, TimeoutError):
                hint = f"连接超时（{self.proxy_probe_timeout}s），请检查端口与防火墙"
            elif isinstance(exc, ConnectionRefusedError):
                hint = "连接被拒绝，请确认代理服务已监听对应地址与端口"
            if hint:
                print(f"  代理连通性检测失败 ({proxy_url}): {exc_type}: {exc}，{hint}")
            else:
                print(f"  代理连通性检测失败 ({proxy_url}): {exc_type}: {exc}")
            return False

    def _ajax_post(self, url: str, data: dict, cookies: dict, csrf_token: str) -> cffi_requests.Response:
        """
        使用 curl_cffi 发送 AJAX POST 请求

        FlareSolverr 的 request.post 无法自定义请求头（v2 已弃用 headers 参数），
        导致 Rails 服务端返回 HTTP 406。使用 curl_cffi 可以完全控制请求头。

        Args:
            url: 目标 URL
            data: POST 数据字典
            cookies: Cookie 字典（包含 cf_clearance 和 session）
            csrf_token: CSRF token

        Returns:
            curl_cffi 响应对象
        """
        headers = {
            "Accept": "*/*;q=0.5, text/javascript, application/javascript, application/ecmascript, application/x-ecmascript",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": f"https://{self.host}",
            "Referer": f"https://{self.host}/users/{self.user_id}/recheckin",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-Token": csrf_token,
        }

        # 构建代理候选列表（按优先级排序）
        # cf_clearance 与 IP 绑定，必须使用与 FlareSolverr 相同的 WARP 出口 IP
        proxy_candidates = self._build_proxy_candidates()
        if not proxy_candidates:
            raise ValueError("未找到可用代理，请设置 WARP_PUBLIC_PROXY 或使 WARP_PROXY 可从本地访问")

        print("  代理候选列表:")
        for candidate in proxy_candidates:
            proxy_display = candidate.proxy_url or "无"
            probe_flag = "是" if candidate.require_probe else "否"
            stop_flag = "是" if candidate.stop_on_fail else "否"
            print(f"    - {candidate.label}: {proxy_display} (探测: {probe_flag}, 失败即停止: {stop_flag})")

        last_error = None
        errors: List[str] = []
        probe_errors: List[str] = []
        request_errors: List[str] = []
        for i, candidate in enumerate(proxy_candidates):
            proxies = candidate.as_requests_proxy()
            if candidate.require_probe and candidate.proxy_url:
                if not self._probe_proxy(candidate.proxy_url):
                    message = f"{candidate.label}: 连通性探测失败，{candidate.hint or '请确认端口已开放或配置 SSH 隧道'}"
                    print(f"  {message}")
                    errors.append(message)
                    probe_errors.append(message)
                    if candidate.stop_on_fail:
                        break
                    continue

            try:
                proxy_display = candidate.proxy_url or "无"
                print(f"  使用{candidate.label}: {proxy_display}")
                if candidate.warn_on_use:
                    print(f"  警告: {candidate.warn_on_use}")
                response = cffi_requests.post(
                    url,
                    data=data,
                    headers=headers,
                    cookies=cookies,
                    proxies=proxies,
                    impersonate="chrome131",
                    timeout=30
                )
                return response
            except Exception as e:
                last_error = e
                probe_note = "" if candidate.require_probe else "（未进行连通性探测）"
                error_msg = f"{candidate.label}连接失败{probe_note}: {e}"
                print(f"  {error_msg}")
                errors.append(error_msg)
                request_errors.append(error_msg)
                if candidate.stop_on_fail:
                    break
                if i < len(proxy_candidates) - 1:
                    print("  尝试下一个代理...")

        detail_parts: List[str] = []
        if probe_errors:
            detail_parts.append(f"探测失败: {'; '.join(probe_errors)}")
        if request_errors:
            detail_parts.append(f"请求失败: {'; '.join(request_errors)}")
        error_detail = " | ".join(detail_parts)
        if not error_detail:
            error_detail = "; ".join(errors) or (str(last_error) if last_error else "未知错误")
        raise ValueError(
            "所有代理均连接失败，" +
            "建议将 WARP 端口暴露为 0.0.0.0:40000、配置 SSH 隧道 (ssh -L 40000:127.0.0.1:40000 user@vps) 或设置 WARP_PUBLIC_PROXY。" +
            f"具体错误: {error_detail}"
        )

    def _extract_sitekey(self, html: str) -> Optional[str]:
        """从 HTML 提取 Turnstile sitekey"""
        match = re.search(r'data-sitekey="([^"]+)"', html)
        return match.group(1) if match else None

    def _extract_auth_token(self, html: str) -> Optional[str]:
        """从 HTML 提取 authenticity_token"""
        match = re.search(r'name="authenticity_token"\s+value="([^"]+)"', html)
        if match:
            return match.group(1)

        match = re.search(r'authenticity_token["\s:]+([^"&\s]+)', html)
        if match:
            return match.group(1)

        return None

    def _save_debug_html(self, html: str, prefix: str) -> None:
        """保存调试 HTML 文件"""
        try:
            import os
            from datetime import datetime
            os.makedirs('debug', exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'debug/{prefix}_{timestamp}.html'
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"  调试页面已保存: {filename}")
        except Exception as e:
            print(f"  保存调试文件失败: {e}")

    def _extract_turnstile_token(self, html: str) -> Optional[str]:
        """从 HTML 提取 Turnstile token"""
        match = re.search(r'name="cf-turnstile-response"\s+value="([^"]+)"', html)
        if match:
            token = match.group(1)
            if token and len(token) > 10:
                return token

        match = re.search(r'cf-turnstile-response["\s:=]+([^"&\s<>]{20,})', html)
        if match:
            return match.group(1)

        return None

    def _wait_for_turnstile(self, max_wait: int = 60) -> Optional[str]:
        """
        等待 Turnstile 自动验证完成

        FlareSolverr 运行真实浏览器，Turnstile 应该能自动完成验证。
        我们需要轮询页面直到获取到 token。

        Args:
            max_wait: 最大等待时间（秒）

        Returns:
            Turnstile token，失败返回 None
        """
        recheckin_url = f"https://{self.host}/users/{self.user_id}/recheckin"
        print("等待 Turnstile 验证完成...", end='', flush=True)

        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                solution = self._get_page(recheckin_url, max_timeout=30)
                html = solution.get("response", "")

                token = self._extract_turnstile_token(html)
                if token:
                    print(" 完成")
                    return token

                print(".", end='', flush=True)
                time.sleep(3)

            except Exception as e:
                print(f"(err:{e})", end='', flush=True)
                time.sleep(3)

        print(" 超时")
        return None

    def _is_cloudflare_challenge(self, html: str) -> bool:
        """检测是否是 Cloudflare 验证挑战页面（非正常页面内容）"""
        # 先检查是否有正常页面元素，有则一定不是验证页
        has_normal_content = '2DFan' in html or 'navbar' in html or '签到' in html
        if has_normal_content:
            return False

        # 只在缺少正常内容时，检测验证挑战页面特征
        challenge_indicators = [
            '请稍候',
            'Just a moment',
            'Checking your browser',
            'Verifying you are human'
        ]
        return any(ind in html for ind in challenge_indicators)

    def _check_already_checked_in(self, html: str) -> bool:
        """检查是否今日已签到 - 只检测明确的已签到标识"""
        # 只检测明确的已签到文字，不再检测 "冷却中" 和 "disabled"
        # "冷却中" 可能表示签到时间未到，不代表已签到
        explicit_indicators = ['今日已签到', '已经签到', 'already checked in']
        return any(indicator in html for indicator in explicit_indicators)

    def _parse_checkin_result(self, html: str) -> CheckinResult:
        """解析签到结果"""
        import json as json_module

        # 尝试解析 JSON 响应
        try:
            # 移除可能的 HTML 标签
            clean_text = re.sub(r'<[^>]+>', '', html).strip()
            if clean_text.startswith('{') and 'checkins_count' in clean_text:
                data = json_module.loads(clean_text)
                return CheckinResult(
                    checkins_count=data.get('checkins_count', -1),
                    serial_checkins=data.get('serial_checkins', -1)
                )
        except Exception:
            pass

        # 从 HTML 提取
        serial_match = re.search(r'连续签到[^\d]*(\d+)', html)
        total_match = re.search(r'累计签到[^\d]*(\d+)', html)

        checkins_count = int(total_match.group(1)) if total_match else -1
        serial_checkins = int(serial_match.group(1)) if serial_match else -1

        return CheckinResult(checkins_count=checkins_count, serial_checkins=serial_checkins)

    def checkin(self) -> CheckinResult:
        """
        执行签到流程

        流程:
        1. 创建 FlareSolverr 会话（启用 WARP 代理）
        2. 访问网站首页，通过 Cloudflare 验证
        3. 注入用户 session cookie
        4. 访问签到页面获取 authenticity_token
        5. 等待 Turnstile 自动验证完成
        6. 提交签到表单
        7. 解析结果并销毁会话

        Returns:
            CheckinResult 签到结果
        """
        try:
            print(f"开始 FlareSolverr 签到 (用户: {self.user_id[:6]}...)")

            # 1. 创建会话
            self._create_session()

            # 2. 先访问首页通过 Cloudflare 验证
            print("访问首页通过 Cloudflare 验证...")
            home_url = f"https://{self.host}/"
            self._get_page(home_url, max_timeout=60)
            print("  Cloudflare 验证通过")

            # 3. 注入 Cookie 并访问签到页面
            cookies = [
                {"name": "_project_hgc_session", "value": self.session_cookie},
                {"name": "pop-blocked", "value": "true"}
            ]

            recheckin_url = f"https://{self.host}/users/{self.user_id}/recheckin"
            print(f"访问签到页面: {recheckin_url}")
            solution = self._get_page(recheckin_url, cookies=cookies, max_timeout=60)
            html = solution.get("response", "")

            # 保存签到页面供调试
            self._save_debug_html(html, 'checkin_page')

            # 检查是否需要登录
            current_url = solution.get("url", "")
            if 'login' in current_url.lower() or 'sign_in' in current_url.lower():
                raise ValueError("Cookie 已失效，请重新获取 _project_hgc_session Cookie")

            # 检查是否是 Cloudflare 验证页面
            if self._is_cloudflare_challenge(html):
                raise ValueError("Cloudflare 验证未通过，请检查 WARP 代理状态")

            # 检查是否明确已签到
            if self._check_already_checked_in(html):
                print("今日已签到")
                return CheckinResult(checkins_count=-1, serial_checkins=-1, error="今日已签到")

            # 检查签到按钮状态 - "冷却中" 不代表已签到，继续尝试提交让服务端返回具体错误
            if '冷却中' in html:
                print("  签到按钮显示冷却中，尝试继续签到...")

            # 4. 提取 authenticity_token
            auth_token = self._extract_auth_token(html)
            if not auth_token:
                raise ValueError("无法获取 authenticity_token，页面可能未正确加载")
            print(f"  获取 authenticity_token: {auth_token[:20]}...")

            # 5. 尝试提取 Turnstile token
            # FlareSolverr 中 Turnstile 应该在页面加载时自动完成验证
            # 如果首次提取失败，等待后重新获取页面检查
            turnstile_token = self._extract_turnstile_token(html)
            if not turnstile_token and 'cf-turnstile' in html:
                print("  等待 Turnstile 验证...", end='', flush=True)
                for attempt in range(4):
                    time.sleep(8)
                    print(".", end='', flush=True)
                    try:
                        solution = self._get_page(recheckin_url, cookies=cookies, max_timeout=30)
                        html = solution.get("response", "")
                        turnstile_token = self._extract_turnstile_token(html)
                        if turnstile_token:
                            break
                        # 重新提取 auth_token（页面刷新后可能变化）
                        new_auth = self._extract_auth_token(html)
                        if new_auth:
                            auth_token = new_auth
                    except Exception as e:
                        print(f"(err:{e})", end='', flush=True)
                print()

            # 如果页面轮询无法获取 token，且配置了验证码服务，则调用 API
            if not turnstile_token and self.captcha_service:
                sitekey = self._extract_sitekey(html)
                if sitekey:
                    print("  调用验证码 API 获取 Turnstile token...")
                    try:
                        recheckin_url = f"https://{self.host}/users/{self.user_id}/recheckin"
                        turnstile_token = self.captcha_service.tft(
                            websiteURL=recheckin_url,
                            websiteKey=sitekey
                        )
                        print(f"  API 返回 token: {turnstile_token[:30]}...")
                    except Exception as e:
                        print(f"  验证码 API 调用失败: {e}")
                else:
                    print("  未找到 Turnstile sitekey，无法调用验证码 API")

            if turnstile_token:
                print(f"  获取 Turnstile token: {turnstile_token[:30]}...")
            else:
                print("  警告: 未获取到 Turnstile token，签到可能失败")
                if not self.captcha_service:
                    print("  提示: 配置 EZCAPTCHA_CLIENT_KEY 或 YESCAPTCHA_CLIENT_KEY 可启用验证码 API 回退")

            # 6. 提交签到（使用 curl_cffi 发送 AJAX 请求绕过 HTTP 406）
            print("提交签到...")

            # 从 FlareSolverr 响应提取 cookies（包含 cf_clearance）
            cf_cookies = self._extract_cookies(solution)
            # 确保包含 session cookie
            cf_cookies["_project_hgc_session"] = self.session_cookie

            post_data = {
                "authenticity_token": auth_token,
            }
            if turnstile_token:
                post_data["cf-turnstile-response"] = turnstile_token

            checkin_url = f"https://{self.host}/checkins"

            try:
                response = self._ajax_post(checkin_url, post_data, cf_cookies, auth_token)
                result_html = response.text
                print(f"  HTTP 状态码: {response.status_code}")
            except Exception as e:
                raise ValueError(f"AJAX 请求失败: {e}")

            # 保存签到响应供调试
            self._save_debug_html(result_html, 'checkin_result')

            # 7. 解析结果
            result = self._parse_checkin_result(result_html)

            # 检测 HTTP 错误页面
            if 'HTTP ERROR' in result_html or 'neterror' in result_html:
                error_match = re.search(r'HTTP ERROR (\d+)', result_html)
                error_code = error_match.group(1) if error_match else 'unknown'
                print(f"签到失败：服务端返回 HTTP {error_code}")
                result.error = f"HTTP 错误 {error_code}"
            elif result.checkins_count > 0:
                print(f"签到成功! 累计 {result.checkins_count} 天, 连续 {result.serial_checkins} 天")
            elif '签到成功' in result_html:
                print("签到成功")
            elif self._check_already_checked_in(result_html):
                print("今日已签到")
                result.error = "今日已签到"
            elif '验证码' in result_html or 'captcha' in result_html.lower() or 'turnstile' in result_html.lower():
                print("签到失败：验证码验证未通过")
                result.error = "验证码验证未通过"
            else:
                print("签到完成（结果未知）")
                result.error = "签到结果未知，请检查 debug 目录下的调试文件"

            return result

        finally:
            self._destroy_session()


def flaresolverr_checkin(
    user_id: str,
    session_cookie: str,
    flaresolverr_url: str,
    warp_proxy: str = "socks5://127.0.0.1:40000",
    host: str = "2dfan.com",
    captcha_service=None
) -> CheckinResult:
    """便捷函数：执行 FlareSolverr 签到"""
    checker = FlareSolverrCheckin(user_id, session_cookie, flaresolverr_url, warp_proxy, host, captcha_service)
    return checker.checkin()


if __name__ == '__main__':
    import os
    import json
    from dotenv import load_dotenv

    load_dotenv()

    session_map_str = os.environ.get('SESSION_MAP')
    flaresolverr_url = os.environ.get('FLARESOLVERR_URL')
    warp_proxy = os.environ.get('WARP_PROXY', 'socks5://127.0.0.1:40000')

    if not session_map_str:
        print("请设置 SESSION_MAP 环境变量")
        exit(1)

    if not flaresolverr_url:
        print("请设置 FLARESOLVERR_URL 环境变量")
        exit(1)

    session_map = json.loads(session_map_str)

    for user_id, session in session_map.items():
        print(f"\n{'='*50}")
        result = flaresolverr_checkin(user_id, session, flaresolverr_url, warp_proxy)
        print(f"签到结果: checkins_count={result.checkins_count}, serial_checkins={result.serial_checkins}")
