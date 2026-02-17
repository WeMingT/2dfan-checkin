# 2dfan 自动签到

使用 [nodriver](https://github.com/nichochar/nodriver)（无痕 Chrome 自动化）在本地运行浏览器完成 2dfan.com 签到，自动处理 Cloudflare 和 Turnstile 验证。支持多账号。

## 使用方法

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置账号

复制 `.env.example` 为 `.env`，填入账号信息：

```env
ACCOUNTS=[{"user_id":"你的用户ID","session":"你的session"}]
```

支持多账号，以 JSON 数组配置：

```env
ACCOUNTS=[{"user_id":"123","session":"xxx"},{"user_id":"456","session":"yyy"}]
```

**获取方式：**
- `user_id` — 2dfan.com 个人主页 URL 中的数字
- `session` — 浏览器 Cookie 中 `_project_hgc_session` 的值

### 3. 运行签到

```bash
uv run python main.py
```

程序会依次对每个账号执行签到，单个账号失败不影响其他账号，最后输出汇总结果。

## 免责声明

本项目仅供学习和个人使用，使用者需自行承担一切风险。作者不对因使用本工具而导致的任何损失或账号问题负责，也不保证工具的持续可用性。使用本项目即表示你同意遵守 2dfan.com 的服务条款。

## License

[MIT](LICENSE)
