"""Проверка жизненного цикла Chrome на ноутбуке: старт -> есть -> close -> нет."""
import asyncio
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot.ozon import OzonParser  # noqa: E402


def chrome_count() -> int:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                         capture_output=True, text=True)
    return out.stdout.count("chrome.exe")


async def main() -> None:
    print("chrome before:", chrome_count())
    p = OzonParser()
    await p.start()
    await asyncio.sleep(2)
    print("chrome after start:", chrome_count())
    await p.close()
    await asyncio.sleep(3)
    print("chrome after close:", chrome_count())
    assert chrome_count() == 0, "Chrome пережил close()!"


if __name__ == "__main__":
    asyncio.run(main())
    print("LIFECYCLE-OK")
