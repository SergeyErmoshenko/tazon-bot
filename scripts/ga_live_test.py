"""Живой тест ЗЯ через run_single: добавляет тестовый товар, снимает цены, чистит за собой."""
import asyncio
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot  # noqa: E402

from bot import config, db, runner  # noqa: E402

SKU = 19000007126


async def main() -> None:
    config.settings = config.load_settings()
    db.init_db()
    p = db.add_product("goldapple", f"https://goldapple.ru/{SKU}", SKU, None,
                       orig_url="https://goldapple.ru/19000007126-skin-guardian")
    db.subscribe(config.settings.admin_chat_id, p.id)
    bot = Bot(token=config.settings.bot_token)
    try:
        status, p = await runner.run_single(bot, p)
        print("status:", status)
        last = db.get_last_point(p.id)
        if last:
            print("price:", last.price, "club:", last.card_price)
        print("title:", (p.title or "-")[:70])
    finally:
        await bot.session.close()
        # тестовый товар убираем, чтобы не попал в списки владельца
        db.unsubscribe(config.settings.admin_chat_id, p.id)
        if db.subscribers(p.id) == []:
            print("cleaned up test product")


if __name__ == "__main__":
    asyncio.run(main())
