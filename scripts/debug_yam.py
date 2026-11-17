"""Дамп страницы Яндекс Маркета через ОСНОВНОЙ профиль бота (тёплые куки Яндекса)."""
import asyncio
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot import config  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://market.yandex.ru/card/naushniki-nakladnyye-besprovodnyye-ergolux-elx-bthp01-c02-fm-mp3-mikrofon-chernyye-korobka-15355/6041984286"

DUMP_JS = """
() => {
  const out = {title: document.title, h1: null, rubTexts: [], priceEls: []};
  const h1 = document.querySelector('h1');
  out.h1 = h1 ? h1.textContent.trim().slice(0, 80) : null;
  for (const el of document.querySelectorAll('[class*="price" i], [data-auto*="price" i]')) {
    const text = (el.textContent || '').trim();
    if (!text || text.length > 50) continue;
    const leaf = !el.querySelector('[class*="price" i]');
    out.priceEls.push({leaf, text: text.slice(0, 40), cls: String(el.className || '').slice(0, 80)});
    if (out.priceEls.length > 15) break;
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const t = (node.textContent || '').trim();
    if (/\\d[\\d\\u00a0\\u202f\\u2009 ]{0,10}(₽|руб\\.?)/.test(t) && t.length < 30 && out.rubTexts.length < 12) {
      let el = node.parentElement, cls = '';
      for (let i = 0; el && i < 4; i++) { cls += String(el.className || '').slice(0, 30) + ' < '; el = el.parentElement; }
      out.rubTexts.push({t: t.slice(0, 30), cls: cls.slice(0, 120)});
    }
  }
  return out;
}
"""


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
    try:
        t0 = time.monotonic()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(8)
        d = await page.evaluate(DUMP_JS)
        lines.append(f"t+{int(time.monotonic()-t0)}s title={d['title'][:70]!r}")
        lines.append(f"h1: {d['h1']!r}")
        lines.append("=== price elements ===")
        for n in d["priceEls"]:
            lines.append(f"{'LEAF' if n['leaf'] else 'CONT'} {n['text']!r} @ {n['cls']}")
        lines.append("=== rub texts ===")
        for n in d["rubTexts"]:
            lines.append(f"  {n['t']!r} @ {n['cls']}")
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
