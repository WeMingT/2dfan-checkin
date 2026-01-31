# Changelog

## [Unreleased]

### Added
- 邮件通知功能：签到完成后自动发送结果通知（`notify.py`）
- FlareSolverr + WARP 签到模式（`flaresolverr_checkin.py`）
- FlareSolverr VPS 部署指南，含 cron 定时任务和邮件通知说明（`docs/FLARESOLVERR_SETUP.md`）
- `.env.example` 示例环境变量文件
- 浏览器自动化签到模式（`browser_checkin.py`）
- YesCaptcha 验证码服务支持

### Fixed
- FlareSolverr 模式下"冷却中"状态未被正确识别为"已签到"

---

历史版本见 git log。
