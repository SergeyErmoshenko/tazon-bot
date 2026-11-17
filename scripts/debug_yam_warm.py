"""Прогрев куки Яндекса: ya.ru -> market главная -> карточка товара."""
import asyncio
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot import config  # noqa: E402

CARD = "https://market.yandex.ru/card/naushniki-nakladnyye-besprovodnyye-ergolux-elx-bthp01-c02-fm-mp3-mikrofon-chernyye-korobka-15355/6041984286"


async def main() -> None:
    from playwright.async_api import async_playwright

    proc = subprocess.Popen([
        config.CHROME_PATH,
        "--remote-debugging-port=9222",
        f"--user-data-dir={config.BROWSER_PROFILE_DIR}",
        "--start-minimized", "--disable-background-networking",
        "--disable-component-update", "--disable-sync", "--no-first-run",
        "about:blank",
    ], creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    for _ in range(40):
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2)
            break
        except Exception:
            await asyncio.sleep(0.5)

    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = await browser.contexts[0].new_page()
    lines = []

    async def go(url: str, wait: float, label: str) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(wait)
        title = (await page.title() or "").strip()
        lines.append(f"{label}: title={title[:60]!r} url={page.url[:60]}")

    try:
        await go("https://ya.ru", 4, "ya.ru")
        await page.keyboard.type("наушники", delay=120)
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        await asyncio.sleep(4)
        lines.append(f"search: title={(await page.title() or '')[:50]!r}")
        await go("https://market.yandex.ru", 6, "market-home")
        await go(CARD, 8, "card")
        prices = await page.evaluate("""
            () => Array.from(document.querySelectorAll('[class*="price" i]'))
                .map(e => (e.textContent || '').trim().slice(0, 30))
                .filter(t => t.includes('₽')).slice(0, 8)
        """)
        lines.append(f"prices: {prices}")
    except Exception as e:
        lines.append(f"FAIL: {type(e).__name__}: {e}")
    finally:
        await page.close()
        await browser.close()
        proc.terminate()
    for line in lines:
        print(line)
    with open(r"C:\Users\1\yam_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
