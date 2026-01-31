# Changelog

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
