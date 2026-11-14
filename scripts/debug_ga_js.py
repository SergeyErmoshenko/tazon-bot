"""Диагностика v3: тайминги парсера + счётчики _ga-price элементов по шагам."""
import asyncio
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://goldapple.ru/19000007126-skin-guardian"

COUNT_JS = """
() => {
  const els = document.querySelectorAll('[class*="_ga-price"]');
  const vals = [];
  for (const el of els) {
    const cls = String(el.className || '');
    if (cls.includes('_ga-price_old') || cls.includes('strikethrough') || cls.includes('__currency')) continue;
    if (el.querySelector('[class*="_ga-price"]')) continue;
    const m = (el.textContent || '').match(/(\\d[\\d\\u00a0\\u202f\\u2009\\s]{0,12})\\s*₽/);
    if (m) vals.push(parseInt(m[1].replace(/\\D/g, ''), 10));
  }
  return {count: els.length, vals: vals};
}
"""


async def main() -> None:
    from playwright.async_api import async_playwright
    from bot import config

    proc = subprocess.Popen([
        config.CHROME_PATH,
        f"--remote-debugging-port={config.CDP_PORT}",
        f"--user-data-dir={config.BROWSER_PROFILE_DIR}",
        "--start-minimized", "--disable-background-networking",
        "--disable-component-update", "--disable-sync", "--no-first-run",
        "about:blank",
    ], creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    for _ in range(40):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{config.CDP_PORT}/json/version", timeout=2)
            break
        except Exception:
            await asyncio.sleep(0.5)

    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{config.CDP_PORT}")
    page = await browser.contexts[0].new_page()
    try:
        t0 = time.monotonic()
        await page.goto(URL, wait_until="domcontentloaded", timeout=45_000)
        print(f"goto done at {time.monotonic()-t0:.1f}s")
        for label, wait in (("t+3", 3), ("t+5", 2), ("t+8", 3), ("t+12", 4), ("t+18", 6), ("t+25", 7)):
            await asyncio.sleep(wait)
            d = await page.evaluate(COUNT_JS)
            print(f"{label}s: elements={d['count']} vals={d['vals']}")
        # прокрутка после первого замера не помогла — пробуем сильнее
    finally:
        await page.close()
        await browser.close()
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
