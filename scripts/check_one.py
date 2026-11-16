"""Проверка одного товара по id (аргумент) с уведомлением подписчикам."""
import asyncio
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot  # noqa: E402

from bot import config, db, runner  # noqa: E402


async def main() -> None:
    config.settings = config.load_settings()
    product_id = int(sys.argv[1])
    product = db.get_product(product_id)
    if not product:
        print("no product", product_id)
        return
    bot = Bot(token=config.settings.bot_token)
    try:
        status = await runner.check_product(bot, product)
        print("status:", status, "| is_out:", db.is_out(product.id))
    finally:
        await bot.session.close()
        await runner.get_parser().close()


if __name__ == "__main__":
    asyncio.run(main())
