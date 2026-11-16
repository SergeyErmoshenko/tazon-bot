"""Таймированный полный прогон: сколько длится цикл с параллельностью."""
import asyncio
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot  # noqa: E402

from bot import config, runner  # noqa: E402


async def main() -> None:
    import logging
    from bot.main import setup_logging  # type: ignore[attr-defined]
    import logging
    setup_logging()
    logging.getLogger().setLevel(logging.INFO)
    config.settings = config.load_settings()
    bot = Bot(token=config.settings.bot_token)
    t0 = time.monotonic()
    try:
        summary = await runner.run_check_all(bot)
        dt = time.monotonic() - t0
        print(f"CYCLE TIME: {dt:.0f}s ({dt/60:.1f} min)")
        print("SUMMARY:", summary.encode("utf-8", "replace").decode("utf-8", "replace"))
    finally:
        await bot.session.close()
        await runner.close_parsers()


if __name__ == "__main__":
    asyncio.run(main())
