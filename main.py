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

    if checkin_mode == 'browser':
        from browser_checkin import browser_checkin
        for key in session_map.keys():
            session = session_map[key]
            result = browser_checkin(key, session, headless=headless)
            print('session:', session[:3], '签到结果:', result.__dict__)

    elif checkin_mode == 'api':
        from api import User
        from recaptcha import EzCaptchaImpl
        for key in session_map.keys():
            session = session_map[key]
            user = User(key, session, EzCaptchaImpl())
            if http_proxy:
                user.session.proxies.update({
                    'http': http_proxy,
                    'https': http_proxy,
                })
            print('session:', session[:3], '签到结果:', user.checkin().__dict__)

    else:
        raise ValueError(f"不支持的签到模式: {checkin_mode}，请使用 'browser' 或 'api'")

    print("finish checkin")
