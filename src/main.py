"""Entry point for Ephemeral VC bot."""

import asyncio
import logging

from src.bot import EphemeralVCBot
from src.config import settings

# ログレベルを INFO に設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def main() -> None:
    """Run the bot."""
    bot = EphemeralVCBot()
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
