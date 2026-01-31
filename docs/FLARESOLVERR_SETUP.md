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
curl -fsSL https://get.docker.com | sh
sudo systemctl start docker
sudo systemctl enable docker
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
warp-cli registration new
warp-cli mode proxy
warp-cli connect
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

### 5. 验证部署

```bash
# 验证 WARP 代理
curl -x socks5://127.0.0.1:40000 https://httpbin.org/ip

# 验证 FlareSolverr
curl http://localhost:8191/health

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

```env
SESSION_MAP={"用户ID":"cookie值"}
CHECKIN_MODE=flaresolverr
FLARESOLVERR_URL=http://VPS_IP:8191/v1
WARP_PROXY=socks5://127.0.0.1:40000  # 可选，默认值
```

**注意**：`FLARESOLVERR_URL` 应填写 VPS 的公网 IP 或域名。

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

## 常见问题

### Q: WARP 无法连接

```bash
warp-cli status
warp-cli disconnect
warp-cli connect

# 检查防火墙
sudo ufw allow out 443/udp
sudo ufw allow out 2408/udp
```

### Q: FlareSolverr 无法访问 WARP 代理

确保使用 `--network host` 模式：

```bash
docker inspect flaresolverr | grep NetworkMode
```

### Q: 签到页面加载超时

```bash
curl -x socks5://127.0.0.1:40000 https://2dfan.com -I
```

### Q: Turnstile 验证失败

1. 检查日志：`docker logs flaresolverr`
2. 确保 WARP IP 不是已知数据中心 IP
3. 尝试 WARP+ 获得更好的 IP 质量

### Q: Cookie 失效

重新从浏览器获取 `_project_hgc_session` Cookie。

## 参考资料

- [FlareSolverr GitHub](https://github.com/FlareSolverr/FlareSolverr)
- [Cloudflare WARP 官方文档](https://developers.cloudflare.com/warp-client/)
