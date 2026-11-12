"""Точка входа: Telegram-бот + планировщик в одном процессе.

Запуск: python -m bot.main
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from . import config, db
from .handlers import setup_router
from .scheduler import create_scheduler


def setup_logging() -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    file_handler = logging.FileHandler(config.LOGS_DIR / "bot.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)


async def main() -> None:
    setup_logging()
    config.settings = config.load_settings()
    settings = config.settings

    db.init_db()
    orphans = db.backfill_subscriptions(settings.admin_chat_id)
    if orphans:
        log.info("Подписал %d товаров без подписчиков на владельца бота", orphans)
    log = logging.getLogger("main")
    log.info("Старт: chat_id=%s, проверки=%s", settings.admin_chat_id, settings.check_times)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(setup_router())

    scheduler = create_scheduler(bot)
    scheduler.start()

    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        scheduler.shutdown(wait=False)
        from .runner import get_parser
        await get_parser().close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
