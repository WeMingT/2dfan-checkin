"""
FlareSolverr + WARP 签到模块
使用 FlareSolverr 服务绕过 Cloudflare 保护，配合 WARP 代理解决数据中心 IP 封锁
"""

import re
import time
import requests
from typing import Optional
from dataclasses import dataclass


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
        host: str = "2dfan.com"
    ):
        self.user_id = user_id
        self.session_cookie = session_cookie
        # 规范化 URL：确保以 /v1 结尾
        url = flaresolverr_url.rstrip('/')
        if not url.endswith('/v1'):
            url = url + '/v1'
        self.flaresolverr_url = url
        self.warp_proxy = warp_proxy
        self.host = host
        self.session_id: Optional[str] = None
        self.request_timeout = 60

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

    def _post_page(self, url: str, post_data: str, max_timeout: int = 60) -> dict:
        """
        通过 FlareSolverr 提交 POST 请求

        Args:
            url: 目标 URL
            post_data: POST 数据（URL 编码格式）
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

        response = requests.post(
            self.flaresolverr_url,
            json=payload,
            timeout=max_timeout + 30
        )
        data = response.json()

        if data.get("status") != "ok":
            raise ValueError(f"POST 请求失败: {data.get('message', 'unknown error')}")

        return data["solution"]

    def _extract_auth_token(self, html: str) -> Optional[str]:
        """从 HTML 提取 authenticity_token"""
        match = re.search(r'name="authenticity_token"\s+value="([^"]+)"', html)
        if match:
            return match.group(1)

        match = re.search(r'authenticity_token["\s:]+([^"&\s]+)', html)
        if match:
            return match.group(1)

        return None

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

    def _check_already_checked_in(self, html: str) -> bool:
        """检查是否已经签到"""
        indicators = ['已签到', '今日已签到', 'already checked', '冷却中', 'disabled="disabled"']
        return any(indicator in html for indicator in indicators)

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

            # 检查是否需要登录
            current_url = solution.get("url", "")
            if 'login' in current_url.lower() or 'sign_in' in current_url.lower():
                raise ValueError("Cookie 已失效，请重新获取 _project_hgc_session Cookie")

            # 检查是否已签到
            if self._check_already_checked_in(html):
                print("今日已签到")
                return CheckinResult(checkins_count=-1, serial_checkins=-1, error="今日已签到")

            # 4. 提取 authenticity_token
            auth_token = self._extract_auth_token(html)
            if not auth_token:
                raise ValueError("无法获取 authenticity_token，页面可能未正确加载")
            print(f"  获取 authenticity_token: {auth_token[:20]}...")

            # 5. 等待 Turnstile 验证完成
            turnstile_token = self._extract_turnstile_token(html)
            if not turnstile_token:
                # 页面上有 Turnstile，需要等待验证完成
                if 'cf-turnstile' in html:
                    turnstile_token = self._wait_for_turnstile(max_wait=90)
                    if not turnstile_token:
                        raise ValueError("Turnstile 验证超时")

            if turnstile_token:
                print(f"  获取 Turnstile token: {turnstile_token[:30]}...")

            # 6. 提交签到
            print("提交签到...")
            from urllib.parse import urlencode

            post_data = {
                "authenticity_token": auth_token,
                "button": ""
            }
            if turnstile_token:
                post_data["cf-turnstile-response"] = turnstile_token

            checkin_url = f"https://{self.host}/checkins"
            solution = self._post_page(checkin_url, urlencode(post_data), max_timeout=60)
            result_html = solution.get("response", "")

            # 7. 解析结果
            result = self._parse_checkin_result(result_html)

            if result.checkins_count > 0:
                print(f"签到成功! 累计 {result.checkins_count} 天, 连续 {result.serial_checkins} 天")
            elif '签到成功' in result_html or 'success' in result_html.lower():
                print("签到成功")
            elif self._check_already_checked_in(result_html):
                print("今日已签到")
            else:
                print("签到完成（结果未知）")
                # 保存调试信息
                try:
                    import os
                    os.makedirs('debug', exist_ok=True)
                    with open('debug/flaresolverr_result.html', 'w', encoding='utf-8') as f:
                        f.write(result_html)
                    print("  结果页面已保存到 debug/flaresolverr_result.html")
                except Exception:
                    pass

            return result

        finally:
            self._destroy_session()


def flaresolverr_checkin(
    user_id: str,
    session_cookie: str,
    flaresolverr_url: str,
    warp_proxy: str = "socks5://127.0.0.1:40000",
    host: str = "2dfan.com"
) -> CheckinResult:
    """便捷函数：执行 FlareSolverr 签到"""
    checker = FlareSolverrCheckin(user_id, session_cookie, flaresolverr_url, warp_proxy, host)
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
