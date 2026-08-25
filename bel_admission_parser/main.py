from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from src.bot import router


async def main() -> None:
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не найден в .env файле")

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
