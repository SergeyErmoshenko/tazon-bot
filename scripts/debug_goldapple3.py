"""Отладка ошибки ЗЯ: печатает FetchResult целиком."""
import asyncio
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot.ozon import OzonParser  # noqa: E402

URL = "https://goldapple.ru/19000007126-skin-guardian"


async def main() -> None:
    p = OzonParser()
    try:
        r = await p.fetch_prices(URL)
        print("ok      :", r.ok)
        print("blocked :", r.blocked)
        print("error   :", r.error)
        print("price   :", r.price, "club:", r.card_price)
        print("title   :", (r.title or "-")[:60])
    finally:
        await p.close()


if __name__ == "__main__":
    asyncio.run(main())
