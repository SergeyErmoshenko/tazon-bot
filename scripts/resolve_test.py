"""Тест разворачивания ссылок на ноутбуке."""
import asyncio
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot.ozon import OzonParser, normalize_url  # noqa: E402


async def main() -> None:
    print("inline old-style:", normalize_url("https://www.ozon.ru/context/detail/id/5677610222/"))
    print("inline ozone domain:", normalize_url("https://ozone.ru/product/1234567890/"))
    print("inline t-link (None expected):", normalize_url("https://ozon.ru/t/Xk2Pq9"))
    p = OzonParser()
    try:
        r = await p.resolve("https://www.ozon.ru/product/xiaomi-smartfon-redmi-note-17-global-8-256-gb-nano-sim-fioletovyy-5677610222/?sh=test123")
        print("resolve full:", r)
        r2 = await p.resolve("https://ozon.ru/t/nonexistent-hash-abc")
        print("resolve fake t-link:", r2)
    finally:
        await p.close()


if __name__ == "__main__":
    asyncio.run(main())
