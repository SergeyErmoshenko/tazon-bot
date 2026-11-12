"""Контрольный прогон всех товаров как планировщик + проверка, что Chrome умер."""
import asyncio
import subprocess
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot  # noqa: E402

from bot import config, runner  # noqa: E402


def chrome_count() -> int:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                         capture_output=True, text=True)
    return out.stdout.count("chrome.exe")


async def main() -> None:
    config.settings = config.load_settings()
    bot = Bot(token=config.settings.bot_token)
    try:
        summary = await runner.run_check_all(bot)
        print("SUMMARY:", summary.encode("utf-8", "replace").decode("utf-8", "replace"))
    finally:
        await bot.session.close()
    await asyncio.sleep(3)
    print("chrome after run:", chrome_count())


if __name__ == "__main__":
    asyncio.run(main())
