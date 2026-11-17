"""Диагностика WB title: как меняется <title> и URL страницы товара."""
import asyncio
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NM = sys.argv[1] if len(sys.argv) > 1 else "190519200"
PRODUCT_URL = f"https://www.wildberries.ru/catalog/{NM}/detail.aspx"


async def main() -> None:
    from playwright.async_api import async_playwright
    from bot import config

    proc = subprocess.Popen([
        config.CHROME_PATH,
        f"--remote-debugging-port=9334",
        f"--user-data-dir=C:\\Users\\1\\tazon-bot\\data\\wb-diag-profile",
        "--start-minimized", "--disable-background-networking",
        "--disable-component-update", "--disable-sync", "--no-first-run",
        "about:blank",
    ], creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    for _ in range(40):
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:9334/json/version", timeout=2)
            break
        except Exception:
            await asyncio.sleep(0.5)

    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9334")
    page = await browser.contexts[0].new_page()
    try:
        t0 = time.monotonic()
        await page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=45_000)
        print("final url:", page.url[:100])
        for i in range(6):
            await asyncio.sleep(2)
            title = await page.title()
            h1 = await page.evaluate("() => { const h = document.querySelector('h1'); return h ? h.textContent.trim().slice(0,60) : null }")
            print(f"t+{int(time.monotonic()-t0)}s title={title[:70]!r} h1={h1!r}")
    finally:
        await page.close()
        await browser.close()
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
