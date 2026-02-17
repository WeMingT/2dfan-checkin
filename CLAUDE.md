# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

2dfan.com 自动签到工具。使用 nodriver（无痕 Chrome 自动化）在本地运行浏览器完成签到，处理 Cloudflare 和 Turnstile 验证。

## 开发命令

```bash
# 安装依赖（使用 uv 管理）
uv sync

# 运行签到
uv run python main.py
```

需要先配置 `.env` 文件（参照 `.env.example`），包含 `ACCOUNTS`（JSON 数组，每项含 `user_id` 和 `session`）。

## 架构

**入口 `main.py`** → 加载环境变量，调用 `api.checkin()`

**核心 `api.py`** → 签到逻辑，采用三级降级策略：
1. 等待 Turnstile 自动解决 → 注入 AJAX 拦截器 → 点击按钮
2. 直接 fetch POST（绕过验证码）
3. 移除 captcha-wrapper DOM → 表单提交

签到结果通过注入的 `_INTERCEPTOR_JS` 拦截 XHR/fetch 响应捕获，或从按钮状态/页面文本中解析。

`CheckinResult` 包含 `checkins_count`（累计）和 `serial_checkins`（连续）。

## 运行环境

- Python >= 3.11，依赖 nodriver、opencv-python、python-dotenv
- 运行时需要 Chrome 浏览器，Chrome 用户数据目录存于项目根 `.chrome_profile/`
- 签到失败时会在项目根生成 `debug_{user_id}.html` 用于调试

## Git 提交规范

遵循语义化提交，中文描述，格式：`<type>: <description>`

常用 type：`feat` / `fix` / `chore` / `build` / `actions` / `add` / `del`

分批次提交，每次提交聚焦单一变更。
