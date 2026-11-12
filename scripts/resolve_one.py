"""Тест разворачивания конкретной короткой ссылки (аргумент — ссылка)."""
import asyncio
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot.ozon import OzonParser  # noqa: E402


async def main() -> None:
    link = sys.argv[1]
    p = OzonParser()
    try:
        r = await p.resolve(link)
        print("resolve:", r)
    finally:
        await p.close()


if __name__ == "__main__":
    asyncio.run(main())
