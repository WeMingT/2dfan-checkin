import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

from api import checkin

# 抑制 Windows asyncio 管道关闭时的 __del__ 异常
_orig_hook = sys.unraisablehook


def _quiet_hook(args):
    if isinstance(args.exc_value, ValueError) and "closed pipe" in str(args.exc_value):
        return
    _orig_hook(args)


sys.unraisablehook = _quiet_hook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class Account:
    user_id: str
    session: str


def load_accounts() -> list[Account]:
    accounts_json = os.environ.get("ACCOUNTS")
    if not accounts_json:
        logger.error("请在 .env 中配置 ACCOUNTS")
        sys.exit(1)
    raw = json.loads(accounts_json)
    return [Account(user_id=str(a["user_id"]), session=a["session"]) for a in raw]


async def main():
    load_dotenv()
    accounts = load_accounts()
    logger.info("共 %d 个账号待签到", len(accounts))

    results: list[tuple[Account, str]] = []

    for i, acc in enumerate(accounts, 1):
        logger.info("── 账号 %d/%d (ID: %s) ──", i, len(accounts), acc.user_id)
        try:
            result = await checkin(acc.user_id, acc.session)
            if result:
                msg = f"签到成功！累计: {result.checkins_count}, 连续: {result.serial_checkins}"
            else:
                msg = "今日已签到，无需操作"
            logger.info("[%s] %s", acc.user_id, msg)
            results.append((acc, msg))
        except Exception as e:
            msg = f"签到失败: {e}"
            logger.error("[%s] %s", acc.user_id, msg)
            results.append((acc, msg))

    logger.info("── 签到汇总 ──")
    for acc, msg in results:
        logger.info("  [%s] %s", acc.user_id, msg)


if __name__ == "__main__":
    asyncio.run(main())
