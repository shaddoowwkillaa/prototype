from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiohttp import web
from dotenv import load_dotenv

from src.bot import router

# Микро-веб-сервер для Render
async def handle_health_check(request):
    return web.Response(text="Bot is live!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main() -> None:
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не найден в .env файле")

    # Запуск фонового сервера для ответа на запросы Render
    await start_web_server()

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)

    try:
        info = await bot.get_webhook_info()
        logging.info(
            "Webhook: %s, pending: %s",
            info.url,
            info.pending_update_count,
        )
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())