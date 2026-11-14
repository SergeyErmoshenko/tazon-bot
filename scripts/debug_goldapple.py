"""Дамп страницы ЗЯ v2: дольше ждём, скроллим, ищем price-классы и JSON."""
import asyncio
import json
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = sys.argv[1] if len(sys.argv) > 1 else "https://goldapple.ru/19000007126-skin-guardian"

_DUMP_JS = """
() => {
  const out = {rubTexts: [], priceClasses: [], jsonld: [], state: null};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const t = (node.textContent || '').trim();
    if (t.includes('₽') && t.length < 60) out.rubTexts.push(t.slice(0, 50));
    if (out.rubTexts.length > 25) break;
  }
  for (const el of document.querySelectorAll('[class*="price" i], [data-testid*="price" i]')) {
    const cls = (el.className || '').toString();
    out.priceClasses.push({cls: cls.slice(0, 100), text: (el.textContent || '').trim().slice(0, 50)});
    if (out.priceClasses.length > 15) break;
  }
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    const t = s.textContent || '';
    if (t.toLowerCase().includes('price')) out.jsonld.push(t.slice(0, 2500));
  }
  const html = document.documentElement.outerHTML;
  const m = html.match(/"price"\\s*:\\s*"?\\d{2,6}"?/g);
  out.state = m ? m.slice(0, 12) : null;
  const h1 = document.querySelector('h1');
  out.title = h1 ? h1.textContent.trim().slice(0, 100) : null;
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
        await asyncio.sleep(6)
        await page.mouse.wheel(0, 600)
        await asyncio.sleep(5)
        data = await page.evaluate(_DUMP_JS)
        print("TITLE:", data.get("title"))
        print("=== ₽ TEXTS ===")
        for t in data.get("rubTexts", []):
            print(" ", repr(t))
        print("=== PRICE CLASSES ===")
        for n in data.get("priceClasses", []):
            print(" ", repr(n["text"]), "@", n["cls"][:80])
        print("=== JSON-LD with price ===")
        for j in data.get("jsonld", []):
            print(j[:1200])
        print('=== "price": N matches in HTML ===')
        for m in data.get("state") or []:
            print(" ", m)
    finally:
        await page.close()
        await browser.close()
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
