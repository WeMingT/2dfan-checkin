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

#### 3.1 暴露 WARP 端口（二选一）
1. **直接在 VPS 暴露**（示例）
   ```bash
   sudo systemctl stop warp-svc
   sudo warp-svc --register --config=/etc/wireguard/warp.conf --listen=0.0.0.0:40000 &
   ```
   或编辑 systemd service，加入 `--listen=0.0.0.0:40000`。
2. **SSH 隧道**（本地访问远程 WARP）
   ```bash
   ssh -L 40000:127.0.0.1:40000 user@VPS_IP
   # 本地将 WARP_PUBLIC_PROXY=socks5://127.0.0.1:40000
   ```

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

> 如需远程访问，可在防火墙中仅对可信 IP 开放 8191 端口，或通过 SSH 隧道 `ssh -L 8191:localhost:8191 user@VPS_IP`。

### 5. 验证部署

```bash
# 验证 WARP 代理出口 IP
curl --socks5 socks5://127.0.0.1:40000 https://www.cloudflare.com/cdn-cgi/trace

# 验证 FlareSolverr
curl http://localhost:8191/health

# 测试完整流程（确保代理可用）
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
WARP_PROXY=socks5://127.0.0.1:40000  # 默认值，仅本地可用
WARP_PUBLIC_PROXY=socks5://your.vps.ip:40000  # 推荐配置，供 curl_cffi 使用
WARP_PROXY_PROBE_TIMEOUT=3  # 可选，连通性探测超时（秒）
```

**注意**：`FLARESOLVERR_URL` 应填写 VPS 的公网 IP 或域名；若 curl_cffi 与 FlareSolverr 不在同一主机，务必暴露 WARP 端口并设置 `WARP_PUBLIC_PROXY`。

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

如果 curl_cffi 在另一台主机：
1. 打开 WARP 端口 (`--listen=0.0.0.0:40000`) 或建立 SSH 隧道；
2. 设置 `WARP_PUBLIC_PROXY=socks5://your.vps.ip:40000`；
3. 观察日志中的 `_probe_proxy` 报错，根据提示检查端口/防火墙。

### Q: `_probe_proxy` 日志显示“连通性探测失败”
- 检查 VPS 防火墙和云厂商安全组是否允许 40000 端口（TCP）。
- 若使用 SSH 隧道，确认隧道仍在运行且本地端口未被占用。
- 调整 `WARP_PROXY_PROBE_TIMEOUT` 以避免网络抖动导致的误报。

### Q: 日志显示“连接到代理被关闭 / connection to proxy closed”
- 常见原因：`warp-svc` 未正确监听、端口被中间设备重置、代理未暴露到外网。
- 先在 VPS 本机测试：
  ```bash
  curl --socks5 socks5://127.0.0.1:40000 https://www.cloudflare.com/cdn-cgi/trace
  ```
- 若本机 OK、远程失败：优先使用 SSH 隧道或将 `warp-svc` 监听改为 `0.0.0.0:40000`。

### Q: curl_cffi 日志提示使用 HTTP_PROXY 或直接连接
- 表示 WARP 远程端不可达，自动回退到兜底代理或直连。
- 这样会导致 `cf_clearance` IP 不一致，多数情况下签到返回 403。
- 需尽快修复 WARP 暴露或 SSH 隧道。

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
