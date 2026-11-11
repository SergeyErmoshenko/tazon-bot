"""Диагностика блока цены: полный дамп webPrice (текст + все цены с признаками).

Запуск на ноутбуке:
    .venv\\Scripts\\python.exe scripts\\debug_price.py https://www.ozon.ru/product/<sku>/
"""
import asyncio
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot.ozon import PRICE_SELECTORS, OzonParser  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.ozon.ru/product/5394836310/"

_DUMP_JS = """
(sel) => {
  const root = document.querySelector(sel);
  if (!root) return null;
  const out = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node, i = 0;
  while ((node = walker.nextNode())) {
    const t = node.textContent || '';
    const m = t.match(/(\\d[\\d\\u00a0\\u202f\\u2009\\s]{0,15})\\s*₽/);
    if (!m) continue;
    let el = node.parentElement, struck = false;
    while (el) {
      const cs = getComputedStyle(el);
      const td = (cs.textDecorationLine || '') + ' ' + (cs.textDecoration || '');
      if (String(td).includes('line-through')) { struck = true; break; }
      el = el.parentElement;
    }
    out.push({n: i++, raw: t.trim().slice(0, 50), value: parseInt(m[1].replace(/\\D/g, ''), 10), struck: struck});
  }
  return {text: root.innerText.slice(0, 500), prices: out};
}
"""


async def main() -> None:
    p = OzonParser()
    try:
        await p.start()
        page = await p._new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=30_000)

        data = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            data = await page.evaluate(_DUMP_JS, PRICE_SELECTORS[0])
            if data and data.get("prices"):
                break
            await asyncio.sleep(1)

        print("=== WIDGET TEXT ===")
        print((data or {}).get("text", "виджет не найден"))
        print("=== PRICES (в порядке DOM) ===")
        for d in (data or {}).get("prices", []):
            mark = "STRUCK" if d["struck"] else "live  "
            print(f"  [{d['n']}] {mark} {d['value']:>7}  raw={d['raw']!r}")

        h1 = await page.query_selector("h1")
        print("=== H1 ===")
        print((await h1.text_content())[:100].strip() if h1 else "ОТСУТСТВУЕТ")
        print("=== TITLE ===")
        print(await page.title())

        await page.close()
    finally:
        await p.close()  # отключаемся от CDP; Chrome бота продолжает жить


if __name__ == "__main__":
    asyncio.run(main())
