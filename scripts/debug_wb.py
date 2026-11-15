"""WB: дамп DOM страницы товара — элементы с ценами и классы."""
import asyncio
import subprocess
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NM = sys.argv[1] if len(sys.argv) > 1 else "604961294"
PRODUCT_URL = f"https://www.wildberries.ru/catalog/{NM}/detail.aspx"

DUMP_JS = """
() => {
  const out = {priceEls: [], h1: null, rubTexts: []};
  const h1 = document.querySelector('h1');
  out.h1 = h1 ? h1.textContent.trim().slice(0, 100) : null;
  for (const el of document.querySelectorAll('[class*="price" i]')) {
    const text = (el.textContent || '').trim();
    if (!text || text.length > 40) continue;
    const cls = String(el.className || '').slice(0, 90);
    const leaf = !el.querySelector('[class*="price" i]');
    out.priceEls.push({leaf, text: text.slice(0, 40), cls});
    if (out.priceEls.length > 20) break;
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const t = (node.textContent || '').trim();
    if (/^\\d[\\d\\u00a0\\u202f\\u2009\\s]{0,10}\\s?₽$/.test(t) && out.rubTexts.length < 12) {
      let el = node.parentElement, cls = '';
      for (let i = 0; el && i < 4; i++) { cls += String(el.className || '').slice(0, 40) + ' < '; el = el.parentElement; }
      out.rubTexts.push({t, cls: cls.slice(0, 140)});
    }
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
    lines = []
    try:
        await page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(8)
        await page.mouse.wheel(0, 400)
        await asyncio.sleep(2)
        d = await page.evaluate(DUMP_JS)
        lines.append("H1: " + str(d.get("h1")))
        lines.append("=== price elements ===")
        for n in d.get("priceEls", []):
            lines.append(f"{'LEAF' if n['leaf'] else 'CONT'} {n['text']!r} @ {n['cls']}")
        lines.append("=== ₽ text nodes ===")
        for n in d.get("rubTexts", []):
            lines.append(f"  {n['t']!r} @ {n['cls']}")
    except Exception as e:
        lines.append(f"FAIL: {type(e).__name__}: {e}")
    finally:
        await page.close()
        await browser.close()
        proc.terminate()
    for line in lines:
        print(line)
    with open(r"C:\Users\1\wb_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
