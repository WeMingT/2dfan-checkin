# 2dfmax.top 网站资产

> 最后更新: 2026-02-01

## 网站基本信息

- **网站名称**: 2DFan (二次元爱好者)
- **网站描述**: 专注于提供日本游戏、动漫相关内容的门户站点
- **主域名**: `2dfan.com`
- **备用域名**: `2dfdf.de`, `2dfmax.top`, `fan2d.top`, `galge.top`
- **域名发布页**: https://github.com/2dfan/domains/
- **图片CDN**: `img.achost.top`

## 签到相关端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/users/{user_id}/recheckin` | GET | 获取签到页面和 authenticity_token |
| `/checkins` | POST | 提交签到请求 |

## 验证码配置

- **类型**: Cloudflare Turnstile
- **websiteKey**: `0x4AAAAAAAju-ZORvFgbC-Cd`
- **rqData配置**:
  ```json
  {
    "mode": "",
    "metadataAction": "checkin",
    "metadataCdata": ""
  }
  ```

### 历史验证码 (已弃用)

- ReCaptcha V3 (2024年中旬之前使用)
  - websiteKey: `6LdUG0AgAAAAAAfSmLDXGMM7XKYMTItv87seZUan`
  - pageAction: `checkin`

## Cookie 说明

| Cookie 名称 | 用途 | 必需 |
|-------------|------|------|
| `_project_hgc_session` | 用户会话凭证 | ✓ |
| `pop-blocked` | 弹窗拦截状态 | |
| `_ga`, `_ga_RF77TZ6QMN` | Google Analytics | |

## 签到请求

### 请求头

```
accept: */*;q=0.5, text/javascript, application/javascript, application/ecmascript, application/x-ecmascript
content-type: application/x-www-form-urlencoded; charset=UTF-8
x-csrf-token: {authenticity_token}
x-requested-with: XMLHttpRequest
```

### 请求体

```
cf-turnstile-response={cf_token}&authenticity_token={auth_token}&format=json
```

### 响应格式

成功 (HTTP 200):
```json
{
  "checkins_count": 123,      // 累计签到次数
  "serial_checkins": 7        // 连续签到天数
}
```

## 网站特性

### 验证码策略
- 直连域名 (`2dfmax.top`): 使用 CF Turnstile 自动验证
- 中转域名: 使用画线验证码（需手动操作，体验较差）

### 已知问题
- GitHub Actions 的 IP 段可能被网站封禁
- 定时任务 (cron) 已关闭，需手动触发 workflow_dispatch
- 外部探测 `/users/{id}/recheckin` 与 `/checkins` 可能返回 403（Cloudflare 访问限制）

### VIP 签到奖励
- 普通用户: 1分签到积分
- VIP用户: 1分签到积分 + 2分VIP特别奖励

## 更新日志

- 2026-02-01: 更新域名发布页显示的主/备用域名列表；记录外部探测 403 现象
- 2026-01-31: 初始化资产文件
