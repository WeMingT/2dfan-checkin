"""
浏览器自动化签到模块
使用 undetected-chromedriver 绕过 Cloudflare 检测，完成签到
"""

import os
import sys
import time
import re
import json
from typing import Optional

# 保存并清除代理环境变量（避免干扰浏览器连接）
_saved_proxies = {}
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    if proxy_var in os.environ:
        _saved_proxies[proxy_var] = os.environ.pop(proxy_var)

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class CheckinResult:
    """签到结果"""
    checkins_count: int
    serial_checkins: int

    def __init__(self, checkins_count: int, serial_checkins: int) -> None:
        self.checkins_count = checkins_count
        self.serial_checkins = serial_checkins


class BrowserCheckin:
    """浏览器自动化签到类"""

    def __init__(self, user_id: str, session_cookie: str, host: str = "2dfan.com", headless: bool = False):
        self.user_id = user_id
        self.session_cookie = session_cookie
        self.host = host
        self.headless = headless
        self.driver: Optional[uc.Chrome] = None

    def _create_driver(self) -> uc.Chrome:
        """创建 undetected Chrome 浏览器"""
        options = uc.ChromeOptions()
        if self.headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        # 自动检测 Chrome 版本并下载对应的 driver
        return uc.Chrome(options=options)

    def _wait_for_cloudflare(self, timeout: int = 180) -> bool:
        """等待 Cloudflare challenge 通过"""
        print("等待 Cloudflare 验证...")
        print("  >>> 如果浏览器显示 Cloudflare 验证，请手动完成 <<<")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                title = self.driver.title

                # Cloudflare challenge 页面的特征
                if '请稍候' in title or 'Just a moment' in title or 'moment' in title.lower():
                    print(".", end='', flush=True)
                    time.sleep(3)
                    continue

                # 通过了 challenge
                print(" 通过")
                return True

            except Exception:
                print("(err)", end='', flush=True)

            time.sleep(2)

        print(" 超时")
        self._save_debug_info('cloudflare_timeout.html')
        return False

    def _inject_cookie(self):
        """注入会话 Cookie"""
        # 先访问目标域名以建立会话
        self.driver.get(f"https://{self.host}/")

        # 等待 Cloudflare challenge 通过
        if not self._wait_for_cloudflare():
            raise ValueError("Cloudflare 验证超时，无法注入 Cookie")

        # 删除现有 cookies 然后注入新的
        self.driver.delete_all_cookies()

        # 注入 session cookie
        self.driver.add_cookie({
            'name': '_project_hgc_session',
            'value': self.session_cookie,
            'domain': self.host,
            'path': '/'
        })
        self.driver.add_cookie({
            'name': 'pop-blocked',
            'value': 'true',
            'domain': self.host,
            'path': '/'
        })

        # 刷新页面以应用 cookie
        print("刷新页面验证登录状态...")
        self.driver.refresh()
        time.sleep(3)

        # 检查是否登录成功
        html = self.driver.page_source
        if 'login' in self.driver.current_url.lower() or 'sign_in' in self.driver.current_url.lower():
            self._save_debug_info('login_failed.html')
            raise ValueError("Cookie 已失效，请重新从浏览器获取 _project_hgc_session Cookie")

        if '登录' in html and '注册' in html and '用户中心' not in html:
            self._save_debug_info('not_logged_in.html')
            raise ValueError("Cookie 已失效，请重新从浏览器获取 _project_hgc_session Cookie")

    def _wait_for_page_ready(self, timeout: int = 120) -> bool:
        """等待签到页面就绪"""
        print("等待页面就绪...", end='', flush=True)
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                title = self.driver.title
                html = self.driver.page_source
                url = self.driver.current_url

                # 还在 Cloudflare challenge
                if '请稍候' in title or 'Just a moment' in title:
                    print("(cf)", end='', flush=True)
                    time.sleep(3)
                    continue

                # 检查是否跳转到登录页
                if 'login' in url.lower() or 'sign_in' in url.lower():
                    print(" 需要登录")
                    return False

                # 到达了签到页面（包含签到表单）
                if 'authenticity_token' in html and '/checkins' in html:
                    # 必须等待 Turnstile 完成验证
                    if 'cf-turnstile' in html:
                        try:
                            turnstile_input = self.driver.find_element(By.CSS_SELECTOR, 'input[name="cf-turnstile-response"]')
                            token = turnstile_input.get_attribute('value')
                            if token and len(token) > 10:
                                print(" 就绪(Turnstile完成)")
                                return True
                            else:
                                print("(ts)", end='', flush=True)
                        except Exception:
                            print("(ts-err)", end='', flush=True)
                    else:
                        # 没有 Turnstile 要求，直接就绪
                        print(" 就绪")
                        return True

            except Exception:
                print("(err)", end='', flush=True)

            print(".", end='', flush=True)
            time.sleep(2)

        print(" 超时")
        self._save_debug_info('page_ready_timeout.html')
        return False

    def _save_debug_info(self, filename: str):
        """保存调试信息"""
        try:
            html = self.driver.page_source
            debug_file = f'debug/{filename}'
            os.makedirs('debug', exist_ok=True)
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"  - 页面 HTML 已保存到 {debug_file}")
        except Exception as e:
            print(f"  - 调试信息保存失败: {e}")

    def _submit_checkin(self) -> CheckinResult:
        """提交签到"""
        try:
            # 查找签到按钮
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]')
        except Exception:
            try:
                submit_btn = self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
            except Exception:
                # 可能已经签到了
                if '已签到' in self.driver.page_source:
                    print("今日已签到")
                    return CheckinResult(checkins_count=-1, serial_checkins=-1)
                self._save_debug_info('no_submit_btn.html')
                raise ValueError("找不到签到按钮")

        # 点击签到
        print("点击签到按钮...")
        submit_btn.click()

        # 等待响应
        time.sleep(5)

        # 保存签到后页面用于调试
        self._save_debug_info('after_checkin.html')

        # 解析结果
        return self._parse_result()

    def _parse_result(self) -> CheckinResult:
        """解析签到结果"""
        html = self.driver.page_source
        url = self.driver.current_url

        # 尝试从页面 body 中提取 JSON 响应（AJAX 签到返回 JSON）
        try:
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text.strip()
            if body_text.startswith('{') and 'checkins_count' in body_text:
                data = json.loads(body_text)
                print(f"签到成功: 累计 {data.get('checkins_count', '?')} 天, 连续 {data.get('serial_checkins', '?')} 天")
                return CheckinResult(
                    checkins_count=data.get('checkins_count', -1),
                    serial_checkins=data.get('serial_checkins', -1)
                )
        except Exception:
            pass

        # 尝试从 HTML 提取签到统计信息
        try:
            serial_match = re.search(r'连续签到[^\d]*(\d+)', html)
            total_match = re.search(r'累计签到[^\d]*(\d+)', html)

            if serial_match or total_match:
                serial_days = int(serial_match.group(1)) if serial_match else -1
                total_days = int(total_match.group(1)) if total_match else -1
                print(f"签到成功: 累计 {total_days} 天, 连续 {serial_days} 天")
                return CheckinResult(checkins_count=total_days, serial_checkins=serial_days)
        except Exception:
            pass

        if "签到成功" in html:
            print("签到成功")
        elif "已签到" in html:
            print("今日已签到")
        else:
            print(f"签到完成，当前页面: {url}")

        return CheckinResult(checkins_count=-1, serial_checkins=-1)

    def checkin(self) -> CheckinResult:
        """执行签到"""
        try:
            print(f"启动浏览器签到 (用户: {self.user_id[:3]}...)")
            self.driver = self._create_driver()

            # 注入 Cookie
            print("注入 Cookie...")
            self._inject_cookie()

            # 访问签到页面
            recheckin_url = f"https://{self.host}/users/{self.user_id}/recheckin"
            print(f"访问签到页面: {recheckin_url}")
            self.driver.get(recheckin_url)

            # 等待页面就绪
            if not self._wait_for_page_ready():
                if 'login' in self.driver.current_url.lower() or 'sign_in' in self.driver.current_url.lower():
                    raise ValueError("Cookie 已失效，需要重新登录获取")
                raise ValueError("页面加载超时")

            # 提交签到
            result = self._submit_checkin()
            return result

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass


def browser_checkin(user_id: str, session_cookie: str, host: str = "2dfan.com", headless: bool = False) -> CheckinResult:
    """便捷函数：执行浏览器签到"""
    checker = BrowserCheckin(user_id, session_cookie, host, headless)
    return checker.checkin()


if __name__ == '__main__':
    from dotenv import load_dotenv

    load_dotenv()

    session_map_str = os.environ.get('SESSION_MAP')
    if not session_map_str:
        print("请设置 SESSION_MAP 环境变量")
        exit(1)

    session_map = json.loads(session_map_str)

    for user_id, session in session_map.items():
        print(f"\n{'='*50}")
        result = browser_checkin(user_id, session, headless=False)
        print(f"签到结果: {result.__dict__}")
