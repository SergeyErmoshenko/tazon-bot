"""Тест: проходит ли антибот магазинов при plain-subprocess Chrome в --headless=new.

Проверяем все 4 магазина: если цены читаются в headless — переводим бота
на headless как дефолт, и проблема зависших окон исчезает как класс.
"""
import asyncio
import json
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright  # noqa: E402

from bot import config  # noqa: E402

URLS = {
    "ozon": "https://www.ozon.ru/product/5677610222/",
    "goldapple": "https://goldapple.ru/19000260312-macximal-matte-lipstick",
    "wildberries": "https://www.wildberries.ru/catalog/604961294/detail.aspx",
    "yandex": "https://market.yandex.ru/card/naushniki-nakladnyye-besprovodnyye-ergolux-elx-bthp01-c02-fm-mp3-mikrofon-chernyye-korobka-15355/6041984286",
}

CHECK_JS = """
() => {
  const rub = /\\d[\\d\\u00a0\\u202f\\u2009\\u2006 ]{3,12}₽/;
  const texts = [];
  for (const el of document.querySelectorAll('[data-widget="webPrice"], [class*="_ga-price"], [class*="ds-valueLine"], [class*="priceBlock"]')) {
    const t = (el.textContent || '').trim();
    if (rub.test(t)) texts.push(t.slice(0, 30));
  }
  if (!texts.length) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const t = (n.textContent || '').trim();
      if (rub.test(t) && t.length < 25) texts.push(t.slice(0, 25));
      if (texts.length >= 3) break;
    }
  }
  return {title: document.title.slice(0, 50), prices: texts.slice(0, 4)};
}
"""


async def main() -> None:
    profile = r"C:\Users\1\tazon-bot\data\headless-test-profile"
    proc = subprocess.Popen([
        config.CHROME_PATH,
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile}",
        "--headless=new",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--no-first-run",
        "about:blank",
    ], creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    for _ in range(40):
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2)
            break
        except Exception:
            await asyncio.sleep(0.5)

    out_lines = []
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    try:
        for store, url in URLS.items():
            page = await browser.contexts[0].new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                await asyncio.sleep(6)
                d = await page.evaluate(CHECK_JS)
                blocked = "робот" in d["title"].lower() or "checking" in d["title"].lower() or "нет соединения" in d["title"].lower()
                verdict = "BLOCKED" if blocked else ("PRICES" if d["prices"] else "NO-PRICES")
                out_lines.append(f"{store}: {verdict} title={d['title']!r} prices={d['prices']}")
            except Exception as e:
                out_lines.append(f"{store}: FAIL {type(e).__name__}: {str(e)[:80]}")
            finally:
                await page.close()
    finally:
        await browser.close()
        proc.terminate()
        subprocess.run(["taskkill", "/F", "/T", "/IM", "chrome.exe"], capture_output=True, check=False)
    for line in out_lines:
        print(line)
    with open(r"C:\Users\1\headless_test.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))


if __name__ == "__main__":
    asyncio.run(main())
