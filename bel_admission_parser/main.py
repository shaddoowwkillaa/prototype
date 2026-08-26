from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from src.bot import router


async def main() -> None:
    load_dotenv()
    
    # Настраиваем логирование, чтобы видеть ошибки в терминале
    logging.basicConfig(level=logging.INFO)

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не найден в .env файле")

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Бот успешно запущен локально и ждет сообщения в Telegram...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())