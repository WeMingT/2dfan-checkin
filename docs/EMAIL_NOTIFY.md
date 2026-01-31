# 邮件通知配置

签到完成后自动发送结果通知邮件。

## 环境变量

```env
SMTP_SERVER=smtp.qq.com         # SMTP 服务器地址
SMTP_PORT=465                    # SMTP 端口
SMTP_USER=your@qq.com           # 发件人邮箱
SMTP_PASS=abcdefghijklmnop      # SMTP 授权码（非登录密码！）
NOTIFY_EMAIL=receive@email.com   # 收件人邮箱
```

配置 `SMTP_SERVER` 后即启用邮件通知，未配置则跳过。

## 支持的邮件服务

| 邮件服务 | SMTP 服务器 | 端口 |
|----------|-------------|------|
| QQ 邮箱 | smtp.qq.com | 465 (SSL) |
| 163 邮箱 | smtp.163.com | 465 (SSL) |
| Gmail | smtp.gmail.com | 465 (SSL) |
| Outlook | smtp.office365.com | 587 (TLS) |

## 获取 SMTP 授权码

**QQ 邮箱：**
1. 登录 QQ 邮箱 → 设置 → 账户
2. 找到「POP3/SMTP服务」，点击「开启」
3. 按提示发送短信验证
4. 复制生成的 16 位授权码

**163 邮箱：**
1. 登录 163 邮箱 → 设置 → POP3/SMTP/IMAP
2. 开启「SMTP服务」
3. 设置客户端授权密码

## 通知内容示例

**签到成功：**
```
主题：[2dfan] 签到成功
正文：用户 123456: 签到成功，累计 100 天，连续 15 天
```

**今日已签到：**
```
主题：[2dfan] 签到成功
正文：用户 123456: 今日已签到
```

**签到失败：**
```
主题：[2dfan] 签到失败
正文：用户 123456: Cookie 已失效
```

**部分成功（多用户）：**
```
主题：[2dfan] 签到部分成功 (1/2)
正文：
用户 123456: 签到成功，累计 100 天，连续 15 天
用户 789012: 签到失败 - 网络超时
```
