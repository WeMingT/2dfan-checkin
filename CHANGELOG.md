# Changelog

## [Unreleased]

### Added
- 代理候选列表与探测/请求失败的细化日志，提升 WARP 排障可读性。
- FlareSolverr 远程部署的高风险配置提示（WARP 仅本地监听时提醒）。
- 文档更新：README、docs/FLARESOLVERR_SETUP.md 增加 "connection to proxy closed" 排障提示；资产文件更新域名列表与 403 记录。

### Fixed
- （无）

---

## [0.3.0] - 2026-01-31

### Added
- 邮件通知功能：签到完成后自动发送结果通知（`notify.py`）
- FlareSolverr + WARP 签到模式（`flaresolverr_checkin.py`）
- `.env.example` 示例环境变量文件
- 浏览器自动化签到模式（`browser_checkin.py`）
- YesCaptcha 验证码服务支持
- 文档：
  - `docs/FLARESOLVERR_SETUP.md` - FlareSolverr 部署
  - `docs/CRON_SETUP.md` - Cron 定时签到
  - `docs/EMAIL_NOTIFY.md` - 邮件通知配置

### Fixed
- FlareSolverr 模式下"冷却中"状态未被正确识别为"已签到"

---

历史版本见 git log。
