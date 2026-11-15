"""Дамп leaf-элементов _ga-price с текстами и классами — почему мусор в ценах."""
import asyncio
import subprocess
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = sys.argv[1] if len(sys.argv) > 1 else "https://goldapple.ru/19000001064-purify-hudra-mask"

DUMP_JS = """
() => {
  const out = [];
  for (const el of document.querySelectorAll('[class*="_ga-price"]')) {
    const cls = String(el.className || '');
    const inner = el.querySelector('[class*="_ga-price"]:not([class*="__currency"])');
    const text = (el.textContent || '').trim().slice(0, 40);
    out.push({cls: cls.slice(0, 90), text, isLeaf: !inner});
  }
  return out;
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
        await page.goto(URL, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(5)
        await page.mouse.wheel(0, 600)
        await asyncio.sleep(3)
        data = await page.evaluate(DUMP_JS)
        for n in data:
            print(("LEAF " if n["isLeaf"] else "CONT "), repr(n["text"]), "@", n["cls"])
    finally:
        await page.close()
        await browser.close()
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
