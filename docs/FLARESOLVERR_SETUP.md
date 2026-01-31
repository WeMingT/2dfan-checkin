# FlareSolverr + WARP VPS 部署指南

本指南介绍如何在 VPS 上部署 FlareSolverr + Cloudflare WARP，用于绕过 Cloudflare 保护完成自动签到。

## 背景

目标网站使用 Cloudflare 防护，数据中心 IP 被严格封锁。解决方案：

- **FlareSolverr**：运行真实浏览器解决 Cloudflare Challenge
- **Cloudflare WARP**：提供可信 IP（非数据中心 IP）

## VPS 要求

- 系统：Ubuntu 20.04 / 22.04 / Debian 11+
- 内存：最低 2GB（推荐 4GB）
- 存储：10GB+
- 网络：可访问 Cloudflare WARP 服务

## 部署步骤

### 1. 安装 Docker

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
docker --version
```

### 2. 安装 Cloudflare WARP

```bash
# 添加 Cloudflare GPG 密钥
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg

# 添加 APT 源
echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list

# 安装 WARP
sudo apt update && sudo apt install cloudflare-warp -y
```

### 3. 配置 WARP

```bash
# 注册 WARP（免费版）
warp-cli registration new

# 设置为代理模式（不影响系统其他流量）
warp-cli mode proxy

# 连接 WARP
warp-cli connect

# 验证状态
warp-cli status
```

WARP 默认在 `socks5://127.0.0.1:40000` 监听。

### 4. 部署 FlareSolverr

**重要**：必须使用 `--network host` 模式，让 FlareSolverr 能访问 WARP 代理。

```bash
docker run -d \
  --name flaresolverr \
  --network host \
  -e LOG_LEVEL=info \
  --restart unless-stopped \
  ghcr.io/flaresolverr/flaresolverr:latest
```

FlareSolverr 默认在端口 8191 监听。

### 5. 验证部署

```bash
# 验证 WARP 代理
curl -x socks5://127.0.0.1:40000 https://httpbin.org/ip
# 应返回 Cloudflare 的 IP

# 验证 FlareSolverr
curl http://localhost:8191/health
# 应返回 {"msg":"FlareSolverr is ready!","version":"...","userAgent":"..."}

# 测试完整流程
curl -X POST http://localhost:8191/v1 \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "request.get",
    "url": "https://httpbin.org/ip",
    "maxTimeout": 60000,
    "proxy": {"url": "socks5://127.0.0.1:40000"}
  }'
```

## 环境变量配置

在你的本地或 CI 环境中配置：

```env
# 必需
SESSION_MAP={"用户ID":"cookie值"}
CHECKIN_MODE=flaresolverr
FLARESOLVERR_URL=http://VPS_IP:8191/v1

# 可选（默认值如下）
WARP_PROXY=socks5://127.0.0.1:40000
```

**注意**：`FLARESOLVERR_URL` 应填写 VPS 的公网 IP 或域名。

## 运行签到

```bash
python main.py
```

预期输出：
```
begin checkin (mode: flaresolverr, headless: False)
FlareSolverr URL: http://VPS_IP:8191/v1
WARP Proxy: socks5://127.0.0.1:40000
开始 FlareSolverr 签到 (用户: 123456...)
创建 FlareSolverr 会话...
  会话创建成功: session_xxx
访问首页通过 Cloudflare 验证...
  Cloudflare 验证通过
访问签到页面: https://2dfan.com/users/123456/recheckin
  获取 authenticity_token: xxx...
等待 Turnstile 验证完成... 完成
  获取 Turnstile token: xxx...
提交签到...
签到成功! 累计 123 天, 连续 45 天
销毁 FlareSolverr 会话...
  会话已销毁
session: xxx 签到结果: {'checkins_count': 123, 'serial_checkins': 45}
finish checkin
```

## 常见问题

### Q: WARP 无法连接

```bash
# 检查状态
warp-cli status

# 如果显示 Disconnected，尝试重新连接
warp-cli disconnect
warp-cli connect

# 检查是否被防火墙阻止
sudo ufw allow out 443/udp
sudo ufw allow out 2408/udp
```

### Q: FlareSolverr 无法访问 WARP 代理

确保 FlareSolverr 使用 `--network host` 模式运行：

```bash
# 检查容器网络模式
docker inspect flaresolverr | grep NetworkMode

# 如果不是 host，重新创建
docker rm -f flaresolverr
docker run -d --name flaresolverr --network host ...
```

### Q: 签到页面加载超时

1. 检查 VPS 到目标网站的连通性
2. 增加 FlareSolverr 超时时间
3. 检查 WARP 是否正常工作

```bash
# 通过 WARP 测试目标网站
curl -x socks5://127.0.0.1:40000 https://2dfan.com -I
```

### Q: Turnstile 验证失败

FlareSolverr 运行真实浏览器，Turnstile 应该能自动通过。如果失败：

1. 检查 FlareSolverr 日志：`docker logs flaresolverr`
2. 确保 WARP 提供的 IP 不是已知数据中心 IP
3. 尝试使用 WARP+ 获得更好的 IP 质量

### Q: Cookie 失效

签到失败并提示 Cookie 失效时，需要重新从浏览器获取 `_project_hgc_session` Cookie。

## 安全建议

1. **防火墙配置**：只对可信 IP 开放 8191 端口

   ```bash
   sudo ufw allow from YOUR_IP to any port 8191
   ```

2. **使用 SSH 隧道**：本地通过 SSH 隧道访问 FlareSolverr

   ```bash
   ssh -L 8191:localhost:8191 user@VPS_IP
   # 然后设置 FLARESOLVERR_URL=http://localhost:8191/v1
   ```

3. **定期更新**：保持 FlareSolverr 和 WARP 更新

   ```bash
   docker pull ghcr.io/flaresolverr/flaresolverr:latest
   docker rm -f flaresolverr
   # 重新运行 docker run 命令
   ```

## 定时签到（Cron）

在 VPS 上配置定时任务，实现每日自动签到。

### 1. 创建签到脚本目录

```bash
# 克隆项目
cd /opt
git clone https://github.com/your-repo/2dfan-checkin.git
cd 2dfan-checkin

# 安装依赖
pip3 install -r requirements.txt

# 创建环境变量文件
cp .env.example .env
nano .env
```

### 2. 配置环境变量

编辑 `/opt/2dfan-checkin/.env`：

```env
# 必需
SESSION_MAP={"用户ID":"cookie值"}
CHECKIN_MODE=flaresolverr
FLARESOLVERR_URL=http://127.0.0.1:8191/v1

# 邮件通知（可选）
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your@qq.com
SMTP_PASS=授权码
NOTIFY_EMAIL=receive@email.com
```

### 3. 配置 Cron

```bash
# 编辑 crontab
crontab -e

# 添加定时任务（每日北京时间 8:21，即 UTC 0:21）
21 0 * * * cd /opt/2dfan-checkin && /usr/bin/python3 main.py >> /var/log/2dfan-checkin.log 2>&1
```

### 4. 验证 Cron 配置

```bash
# 查看当前 cron 任务
crontab -l

# 手动测试（确保配置正确）
cd /opt/2dfan-checkin && python3 main.py

# 查看日志
tail -f /var/log/2dfan-checkin.log
```

### 5. 常见 Cron 时间配置

| 时间（北京时间） | Cron 表达式（UTC） | 说明 |
|------------------|---------------------|------|
| 每天 08:00 | `0 0 * * *` | 早晨签到 |
| 每天 12:30 | `30 4 * * *` | 中午签到 |
| 每天 20:00 | `0 12 * * *` | 晚间签到 |

> 注意：服务器通常使用 UTC 时间，北京时间 = UTC + 8 小时

## 邮件通知

签到完成后自动发送结果通知。

### 支持的邮件服务

| 邮件服务 | SMTP 服务器 | 端口 |
|----------|-------------|------|
| QQ 邮箱 | smtp.qq.com | 465 (SSL) |
| 163 邮箱 | smtp.163.com | 465 (SSL) |
| Gmail | smtp.gmail.com | 465 (SSL) |
| Outlook | smtp.office365.com | 587 (TLS) |

### 环境变量配置

```env
SMTP_SERVER=smtp.qq.com         # SMTP 服务器地址
SMTP_PORT=465                    # SMTP 端口
SMTP_USER=your@qq.com           # 发件人邮箱
SMTP_PASS=abcdefghijklmnop      # SMTP 授权码（非登录密码！）
NOTIFY_EMAIL=receive@email.com   # 收件人邮箱
```

### 获取 SMTP 授权码

**QQ 邮箱：**
1. 登录 QQ 邮箱 → 设置 → 账户
2. 找到「POP3/SMTP服务」，点击「开启」
3. 按提示发送短信验证
4. 复制生成的 16 位授权码

**163 邮箱：**
1. 登录 163 邮箱 → 设置 → POP3/SMTP/IMAP
2. 开启「SMTP服务」
3. 设置客户端授权密码

### 通知内容示例

**签到成功：**
```
主题：[2dfan] 签到成功
正文：
用户 123456: 签到成功，累计 100 天，连续 15 天
```

**签到失败：**
```
主题：[2dfan] 签到失败
正文：
用户 123456: 签到失败 - Cookie 已失效
```

**部分成功（多用户）：**
```
主题：[2dfan] 签到部分成功 (1/2)
正文：
用户 123456: 签到成功，累计 100 天，连续 15 天
用户 789012: 签到失败 - 网络超时
```

## 参考资料

- [FlareSolverr GitHub](https://github.com/FlareSolverr/FlareSolverr)
- [Cloudflare WARP 官方文档](https://developers.cloudflare.com/warp-client/)
