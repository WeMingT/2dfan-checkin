import json
import os
import sys
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# sessions = os.environ.get(key='SESSIONS', default='').split(',')
session_map_str: Optional[str] = os.environ.get(key='SESSION_MAP', default=None)
if not session_map_str:
    raise EnvironmentError("缺少环境变量 SESSION_MAP")
session_map: dict[str, str] = json.loads(session_map_str)
http_proxy: str = os.environ.get(key='HTTP_PROXY', default=None)
checkin_mode: str = os.environ.get(key='CHECKIN_MODE', default='browser')
# 在非 Linux 系统上（如 Windows），无头模式可能被 Cloudflare 检测，默认使用非无头模式
headless_env = os.environ.get(key='HEADLESS', default=None)
if headless_env is not None:
    headless = headless_env.lower() in ('true', '1', 'yes')
else:
    # Linux 上默认使用无头模式（配合虚拟显示），其他系统默认非无头
    headless = sys.platform.startswith('linux')

if __name__ == '__main__':
    print(f"begin checkin (mode: {checkin_mode}, headless: {headless})")

    # 收集签到结果用于通知
    results: list[tuple[str, any]] = []

    if checkin_mode == 'browser':
        from browser_checkin import browser_checkin
        for key in session_map.keys():
            session = session_map[key]
            result = browser_checkin(key, session, headless=headless)
            results.append((key, result))
            print('session:', session[:3], '签到结果:', result.__dict__)

    elif checkin_mode == 'api':
        from api import User
        from recaptcha import EzCaptchaImpl, YesCaptchaImpl

        # 选择验证码服务商
        captcha_provider = os.environ.get('CAPTCHA_PROVIDER', 'ezcaptcha').lower()
        if captcha_provider == 'yescaptcha':
            use_cn = os.environ.get('YESCAPTCHA_USE_CN', 'false').lower() in ('true', '1', 'yes')
            captcha = YesCaptchaImpl(use_cn_node=use_cn)
            print(f"使用 YesCaptcha 服务 ({'国内节点' if use_cn else '国际节点'})")
        else:
            captcha = EzCaptchaImpl()
            print("使用 EzCaptcha 服务")

        for key in session_map.keys():
            session = session_map[key]
            user = User(key, session, captcha)
            if http_proxy:
                user.session.proxies.update({
                    'http': http_proxy,
                    'https': http_proxy,
                })
            result = user.checkin()
            results.append((key, result))
            print('session:', session[:3], '签到结果:', result.__dict__)

    elif checkin_mode == 'flaresolverr':
        from flaresolverr_checkin import flaresolverr_checkin
        flaresolverr_url = os.environ.get('FLARESOLVERR_URL')
        if not flaresolverr_url:
            raise EnvironmentError("FlareSolverr 模式需要设置 FLARESOLVERR_URL 环境变量")
        warp_proxy = os.environ.get('WARP_PROXY', 'socks5://127.0.0.1:40000')
        print(f"FlareSolverr URL: {flaresolverr_url}")
        print(f"WARP Proxy: {warp_proxy}")
        for key in session_map.keys():
            session = session_map[key]
            result = flaresolverr_checkin(key, session, flaresolverr_url, warp_proxy)
            results.append((key, result))
            print('session:', session[:3], '签到结果:', result.__dict__)

    else:
        raise ValueError(f"不支持的签到模式: {checkin_mode}，请使用 'browser'、'api' 或 'flaresolverr'")

    print("finish checkin")

    # 发送邮件通知（如果配置了 SMTP）
    if os.environ.get('SMTP_SERVER') and results:
        from notify import send_checkin_notification
        if send_checkin_notification(results):
            print("邮件通知已发送")
        else:
            print("邮件通知发送失败")
