# Cron 定时签到配置

在 VPS 上配置定时任务，实现每日自动签到。

## 部署签到脚本

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

## 配置环境变量

编辑 `/opt/2dfan-checkin/.env`：

```env
SESSION_MAP={"用户ID":"cookie值"}
CHECKIN_MODE=flaresolverr
FLARESOLVERR_URL=http://127.0.0.1:8191/v1

# 邮件通知（可选，见 EMAIL_NOTIFY.md）
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your@qq.com
SMTP_PASS=授权码
NOTIFY_EMAIL=receive@email.com
```

## 配置 Cron

```bash
# 编辑 crontab
crontab -e

# 添加定时任务（每日北京时间 8:21，即 UTC 0:21）
21 0 * * * cd /opt/2dfan-checkin && /usr/bin/python3 main.py >> /var/log/2dfan-checkin.log 2>&1
```

## 验证配置

```bash
# 查看当前 cron 任务
crontab -l

# 手动测试
cd /opt/2dfan-checkin && python3 main.py

# 查看日志
tail -f /var/log/2dfan-checkin.log
```

## 常见 Cron 时间配置

| 时间（北京时间） | Cron 表达式（UTC） | 说明 |
|------------------|---------------------|------|
| 每天 08:00 | `0 0 * * *` | 早晨签到 |
| 每天 12:30 | `30 4 * * *` | 中午签到 |
| 每天 20:00 | `0 12 * * *` | 晚间签到 |

> 注意：服务器通常使用 UTC 时间，北京时间 = UTC + 8 小时
