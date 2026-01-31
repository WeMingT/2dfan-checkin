# 2dfan 自动签到

2dfan.com 网站的自动签到工具，支持两种模式：
- **浏览器模式**（免费）：使用 undetected-chromedriver 自动化浏览器
- **API 模式**（付费）：使用 EzCaptcha 等验证码服务

## 快速开始

### 1. 获取 Cookie

1. 浏览器访问 `2dfan.com` 并登录
2. F12 → Application → Cookies → 复制 `_project_hgc_session` 的值
3. 个人主页 URL 中的数字就是用户 ID（如 `/users/12345`）

### 2. 配置环境变量

创建 `.env` 文件：
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

### API 模式（付费）

使用 EzCaptcha 等验证码服务绕过 Turnstile 验证。

```env
CHECKIN_MODE=api
EZCAPTCHA_CLIENT_KEY=your_api_key
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
| `CHECKIN_MODE` | 否 | 签到模式：`browser`（默认）或 `api` |
| `EZCAPTCHA_CLIENT_KEY` | api模式 | EzCaptcha API 密钥 |
| `HEADLESS` | 否 | 是否使用无头浏览器，默认 Windows 下为 false |
| `HTTP_PROXY` | 否 | HTTP 代理地址（仅 api 模式） |

## 补充说明

有能力的话，请支持 2dfan 的运营，这一项目更多是用来学习尝试的。
