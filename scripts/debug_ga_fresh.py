"""Тест: проходит ли ЗЯ-челлендж со свежим профилем браузера."""
import asyncio
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot import config  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://goldapple.ru/19000260312-macximal-matte-lipstick"
FRESH_PROFILE = r"C:\Users\1\tazon-bot\data\ga-profile"


async def main() -> None:
    from playwright.async_api import async_playwright

    proc = subprocess.Popen([
        config.CHROME_PATH,
        f"--remote-debugging-port=9333",
        f"--user-data-dir={FRESH_PROFILE}",
        "--start-minimized", "--disable-background-networking",
        "--disable-component-update", "--disable-sync", "--no-first-run",
        "about:blank",
    ], creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    for _ in range(40):
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=2)
            break
        except Exception:
            await asyncio.sleep(0.5)

    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    page = await browser.contexts[0].new_page()
    lines = []
    try:
        t0 = time.monotonic()
        await page.goto(URL, wait_until="domcontentloaded", timeout=45_000)
        for step in (5, 10, 15, 20, 30, 40):
            await asyncio.sleep(step if step == 5 else step - lines.__len__())
            title = (await page.title() or "").lower()
            values = await page.evaluate("""
                () => {
                  const vals = new Set();
                  for (const el of document.querySelectorAll('[class*="_ga-price"]')) {
                    const cls = String(el.className || '');
                    if (cls.includes('_ga-price_old') || cls.includes('strikethrough') || cls.includes('__currency')) continue;
                    if (el.querySelector('[class*="_ga-price"]:not([class*="__currency"])')) continue;
                    const m = (el.textContent || '').match(/(\\d[\\d\\u00a0\\u202f\\u2009\\s]{0,12})\\s*₽/);
                    if (m) vals.add(parseInt(m[1].replace(/\\D/g, ''), 10));
                  }
                  return Array.from(vals);
                }
            """)
            lines.append(f"t+{int(time.monotonic()-t0)}s: title={title[:50]!r} prices={values}")
            if values:
                break
    except Exception as e:
        lines.append(f"FAIL: {type(e).__name__}: {e}")
    finally:
        await page.close()
        await browser.close()
        proc.terminate()
    for line in lines:
        print(line)
    with open(r"C:\Users\1\ga_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
