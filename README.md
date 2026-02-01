# 2dfan 自动签到

2dfan.com 网站的自动签到工具，支持三种模式：
- **浏览器模式**（免费）：使用 undetected-chromedriver 自动化浏览器
- **FlareSolverr 模式**（免费）：使用 FlareSolverr + Cloudflare WARP，适合 VPS 部署
- **API 模式**（付费）：使用 EzCaptcha 等验证码服务

## 快速开始

### 1. 获取 Cookie

1. 浏览器访问 `2dfan.com` 并登录
2. F12 → Application → Cookies → 复制 `_project_hgc_session` 的值
3. 个人主页 URL 中的数字就是用户 ID（如 `/users/12345`）

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并修改：
```bash
cp .env.example .env
```

```env
SESSION_MAP={"用户ID":"cookie值"}
```

### 3. 运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行签到
python main.py
```

## 签到模式

### 浏览器模式（默认，免费）

使用 undetected-chromedriver 驱动真实浏览器完成签到。

```env
CHECKIN_MODE=browser
```

**注意**：首次运行时可能需要手动完成一次 Cloudflare 验证。

### FlareSolverr 模式（VPS 部署，免费）

使用 FlareSolverr + Cloudflare WARP，适合在 VPS 上无人值守运行。

```env
CHECKIN_MODE=flaresolverr
FLARESOLVERR_URL=http://VPS_IP:8191/v1
WARP_PROXY=socks5://127.0.0.1:40000  # 默认值（仅本地可用）
WARP_PUBLIC_PROXY=socks5://your.vps.ip:40000  # 推荐，curl_cffi 直接访问的远程 WARP
WARP_PROXY_PROBE_TIMEOUT=3  # 可选，探测超时时间（秒）
```

> 如果 FlareSolverr 运行在 VPS，而 curl_cffi 在本地或 GitHub Actions，必须暴露 WARP 端口或通过 `ssh -L 40000:127.0.0.1:40000 user@vps` 创建隧道，否则 `cf_clearance` 无法复用。若出现 `connection to proxy closed`，优先检查 warp-svc 监听与端口可达性。

需要在 VPS 上部署 FlareSolverr 和 Cloudflare WARP，并确认：
1. `warp-svc` 监听远程地址 (`--listen=0.0.0.0:40000`) 或建立 SSH 隧道；
2. 将暴露后的地址写入 `WARP_PUBLIC_PROXY`；
3. 通过 `curl --socks5 socks5://your.vps.ip:40000 https://www.cloudflare.com/cdn-cgi/trace` 验证出口 IP。

详见 [部署指南](docs/FLARESOLVERR_SETUP.md)，该指南包含暴露 WARP 端口、SSH 隧道与排障操作。

**定时签到**：配置 Cron 实现每日自动签到，详见 [Cron 配置](docs/CRON_SETUP.md)。

### API 模式（付费）

使用验证码服务绕过 Turnstile 验证，支持 EzCaptcha 和 YesCaptcha。

**EzCaptcha（默认）：**
```env
CHECKIN_MODE=api
EZCAPTCHA_CLIENT_KEY=your_api_key
```

**YesCaptcha：**
```env
CHECKIN_MODE=api
CAPTCHA_PROVIDER=yescaptcha
YESCAPTCHA_CLIENT_KEY=your_api_key
YESCAPTCHA_USE_CN=false  # 可选，设为 true 使用国内节点
```

## Docker 运行

```bash
docker build -t 2dfan-checkin .
docker run --env-file .env 2dfan-checkin
```

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `SESSION_MAP` | 是 | JSON 格式的用户映射，如 `{"user_id": "cookie_value"}` |
| `CHECKIN_MODE` | 否 | 签到模式：`browser`（默认）、`flaresolverr` 或 `api` |
| `FLARESOLVERR_URL` | flaresolverr模式 | FlareSolverr 服务地址，如 `http://IP:8191/v1` |
| `WARP_PROXY` | 否 | WARP 代理地址，默认 `socks5://127.0.0.1:40000`（仅本地可用） |
| `WARP_PUBLIC_PROXY` | 否 | curl_cffi 可直接访问的远程 WARP 代理，确保与 FlareSolverr 共用出口 IP |
| `WARP_PROXY_PROBE_TIMEOUT` | 否 | WARP 代理连通性探测超时（秒，默认 3） |
| `WARP_REMOTE_PROXY` | 否 | 已弃用，改用 `WARP_PUBLIC_PROXY` |
| `CAPTCHA_PROVIDER` | 否 | 验证码服务商：`ezcaptcha`（默认）或 `yescaptcha` |
| `EZCAPTCHA_CLIENT_KEY` | api模式 | EzCaptcha API 密钥 |
| `YESCAPTCHA_CLIENT_KEY` | api模式 | YesCaptcha API 密钥 |
| `YESCAPTCHA_USE_CN` | 否 | YesCaptcha 是否使用国内节点，默认 `false` |
| `HEADLESS` | 否 | 是否使用无头浏览器，默认 Windows 下为 false |
| `HTTP_PROXY` | 否 | HTTP 代理地址（仅 api 模式） |
| `SMTP_SERVER` | 否 | SMTP 服务器地址（如 smtp.qq.com） |
| `SMTP_PORT` | 否 | SMTP 端口，默认 465 |
| `SMTP_USER` | 否 | 发件人邮箱 |
| `SMTP_PASS` | 否 | SMTP 授权码 |
| `NOTIFY_EMAIL` | 否 | 收件人邮箱 |

## 邮件通知

签到完成后自动发送结果通知，详见 [邮件通知配置](docs/EMAIL_NOTIFY.md)。

```env
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your@qq.com
SMTP_PASS=smtp授权码
NOTIFY_EMAIL=receive@email.com
```

## 补充说明

有能力的话，请支持 2dfan 的运营，这一项目更多是用来学习尝试的。
