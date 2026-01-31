# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 2dfan.com 网站的自动签到工具，支持通过 GitHub Actions 或 Docker 运行。

支持三种签到模式：
- **浏览器模式**（默认，免费）：使用 undetected-chromedriver 驱动真实浏览器，Turnstile 自动验证
- **FlareSolverr 模式**（免费）：使用 FlareSolverr + Cloudflare WARP，适合 VPS 无人值守部署
- **API 模式**（付费）：使用 EzCaptcha 等验证码服务绕过 Turnstile

## 常用命令

### 环境配置

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境 (Windows)
.venv\Scripts\activate

# 激活虚拟环境 (Linux/macOS)
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 环境变量配置

创建 `.env` 文件:
```env
# 必需
SESSION_MAP={"user_id":"_project_hgc_session_cookie_value"}

# 可选 - 签到模式 (browser、flaresolverr 或 api，默认 browser)
CHECKIN_MODE=browser

# FlareSolverr 模式配置
FLARESOLVERR_URL=http://VPS_IP:8191/v1
WARP_PROXY=socks5://127.0.0.1:40000  # 默认值

# API 模式 - 验证码服务商选择 (ezcaptcha 或 yescaptcha，默认 ezcaptcha)
CAPTCHA_PROVIDER=ezcaptcha

# EzCaptcha 配置
EZCAPTCHA_CLIENT_KEY=your_api_key

# YesCaptcha 配置
YESCAPTCHA_CLIENT_KEY=your_api_key
YESCAPTCHA_USE_CN=false  # 是否使用国内节点

# 可选
HEADLESS=false          # 是否使用无头浏览器
HTTP_PROXY=http://proxy:port  # 仅 API 模式使用

# 邮件通知（可选）
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your@qq.com
SMTP_PASS=授权码
NOTIFY_EMAIL=receive@email.com
```

### 本地运行
```bash
python main.py
```

### Docker 运行
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
| `WARP_PROXY` | 否 | WARP 代理地址，默认 `socks5://127.0.0.1:40000` |
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

## 代码架构

```
main.py                    # 入口文件，根据 CHECKIN_MODE 选择签到方式
browser_checkin.py         # 浏览器自动化签到（undetected-chromedriver）
flaresolverr_checkin.py    # FlareSolverr + WARP 签到
api.py                     # API 签到，封装 HTTP 请求
recaptcha.py               # 验证码接口抽象和 EzCaptcha 实现
notify.py                  # 邮件通知模块
docs/FLARESOLVERR_SETUP.md # FlareSolverr VPS 部署指南（含 cron 和邮件配置）
```

### 核心流程

#### 浏览器模式（默认）

1. `main.py` 检测 `CHECKIN_MODE=browser`
2. 调用 `browser_checkin.py` 的 `BrowserCheckin` 类
3. 签到流程:
   - 启动 undetected Chrome 浏览器
   - 访问目标网站，等待 Cloudflare 验证通过（可能需要手动完成）
   - 注入 `_project_hgc_session` Cookie
   - 访问签到页面 `/users/{id}/recheckin`
   - 等待 Turnstile 自动验证完成
   - 点击签到按钮提交

#### FlareSolverr 模式

1. `main.py` 检测 `CHECKIN_MODE=flaresolverr`
2. 调用 `flaresolverr_checkin.py` 的 `FlareSolverrCheckin` 类
3. 签到流程:
   - 创建 FlareSolverr 浏览器会话（启用 WARP 代理）
   - 访问首页，自动通过 Cloudflare Challenge
   - 注入 `_project_hgc_session` Cookie，访问签到页面
   - 提取 `authenticity_token`
   - 等待 Turnstile 自动验证完成（真实浏览器，无需验证码服务）
   - POST 提交签到表单到 `/checkins`
   - 销毁浏览器会话

#### API 模式

1. `main.py` 检测 `CHECKIN_MODE=api`
2. 为每个用户创建 `User` 实例（`api.py`）
3. `User.checkin()` 执行签到:
   - 调用 `get_authenticity_token()` 获取 CSRF token
   - 调用 `create_cf_token()` 通过验证码服务获取 Cloudflare Turnstile token
   - POST 到 `/checkins` 完成签到

### 验证码接口

`recaptcha.py` 中的 `CaptchaInterface` 是抽象基类，定义了两个方法:
- `cap()`: ReCaptcha 验证（当前未使用）
- `tft()`: Cloudflare Turnstile 验证

已实现的服务商:
- `EzCaptchaImpl`: EzCaptcha 服务
- `YesCaptchaImpl`: YesCaptcha 服务（支持国内/国际节点）

如需接入其他验证码平台，实现 `CaptchaInterface` 接口即可。

---

## 资产探查与维护

目标网站 (2dfmax.top) 的技术信息存储在 `assets/2dfmax.top.md` 文件中。

### 执行任务前的探查要求

在执行任何与目标网站相关的任务之前，**必须**先进行以下探查:

1. **读取资产文件**: 查阅 `assets/2dfmax.top.md` 获取已知的网站信息
2. **验证端点有效性**: 使用 WebFetch 或 firecrawl 工具测试关键端点是否正常响应
3. **检查验证码配置**: 确认当前使用的验证码类型和 websiteKey 是否与资产文件一致
4. **核对域名状态**: 访问域名发布页确认当前可用域名

### 探查内容清单

- [ ] 签到页面 (`/users/{id}/recheckin`) 是否可访问
- [ ] 验证码类型是否变更 (Turnstile / ReCaptcha / 其他)
- [ ] websiteKey 是否更新
- [ ] CSRF token 获取方式是否变化
- [ ] 签到 POST 请求参数是否调整
- [ ] Cookie 认证机制是否改变

### 资产维护要求

在任务执行过程中，如发现以下情况，**必须**更新 `assets/2dfmax.top.md`:

1. **端点变更**: API 路径、请求方法或参数格式发生变化
2. **验证码更新**: 验证码类型、websiteKey 或配置参数变化
3. **新增发现**: 发现未记录的有用信息（如新的 Cookie、响应字段等）
4. **问题记录**: 遇到的错误、异常或已知限制
5. **域名变更**: 主域名或备用域名发生变化

### 更新资产文件的格式要求

- 在文件顶部更新 "最后更新" 日期
- 在 "更新日志" 部分添加变更记录
- 保持信息的准确性和时效性

## Development Guidelines

1. **版本控制**：所有更改必须通过 Git 提交，遵循语义化版本 (SemVer)
2. **文档同步**：功能完成且**用户确认验收**后，同步更新 README.md 和 CHANGELOG.md 和 CLAUDE.md
3. **临时文件管理**：开发时的调试文件（截图、HTML、日志）应放在`debug`文件夹中，并确保被 .gitignore 排除
4. **网站元信息记录**: 记录有用的网站元信息到文档，留作后用，无需提交到 git
5. **最小化 Git 提交**：只提交完成任务所必需的最少文件。对于不确定是否需要提交的文件，必须先询问用户确认