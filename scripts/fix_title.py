"""Разовое: добрать отсутствующие названия товаров (использует Chrome бота на 9222).

Запуск на ноутбуке: .venv\\Scripts\\python.exe scripts\\fix_title.py
"""
import asyncio
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")

from bot import db  # noqa: E402
from bot.ozon import OzonParser  # noqa: E402


async def main() -> None:
    products = db.list_products(active_only=False)
    todo = [p for p in products if not p.title]
    print(f"товаров без названия: {len(todo)}")
    if not todo:
        return
    parser = OzonParser()
    try:
        for p in todo:
            r = await parser.fetch_prices(p.url)
            if r.title:
                db.update_title(p.id, r.title)
                print(f"ok   {p.sku}: {r.title[:60]}")
            else:
                print(f"fail {p.sku}: {'blocked' if r.blocked else r.error}")
    finally:
        await parser.close()


if __name__ == "__main__":
    asyncio.run(main())
