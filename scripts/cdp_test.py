"""Диагностика: Chrome запускается обычным процессом (без флагов Playwright),
Playwright подключается по CDP. Если так Ozon пропускает — переводим бота
на эту схему.

Запуск на ноутбуке в сессии пользователя:
    .venv\\Scripts\\python.exe scripts\\cdp_test.py
"""
import asyncio
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = r"C:\Users\1\tazon-bot\data\browser-profile"
PORT = 9222
PRODUCT = "https://www.ozon.ru/product/5677610222/"


def wait_port(timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


async def main() -> None:
    proc = subprocess.Popen([
        CHROME,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--start-minimized",
        "about:blank",
    ])
    if not wait_port():
        print("CDP-порт не поднялся за 25 c")
        proc.terminate()
        return

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        ctx = browser.contexts[0]
        page = await ctx.new_page()
        try:
            r = await page.goto(PRODUCT, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(4)
            print("status:", r.status if r else "?")
            print("title :", (await page.title())[:80])
            try:
                await page.wait_for_selector("[data-widget='webPrice']", timeout=15_000)
                el = await page.query_selector("[data-widget='webPrice']")
                print("PRICE :", (await el.text_content())[:120].replace("\n", " | "))
            except Exception:
                print("PRICE : виджет не найден")
        except Exception as e:
            print("FAIL:", type(e).__name__, e)
        finally:
            await page.close()
            await browser.close()  # только отключаемся, Chrome живёт
    proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
