"""Дамп всех ds-valueLine цен по порядку DOM с контекстом (найти кэшбэк)."""
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
  const out = [];
  for (const el of document.querySelectorAll('[class*="ds-valueLine"], [data-auto="priceValue"]')) {
    const text = (el.textContent || '').trim();
    const m = text.match(/^(\\d[\\d\\u00a0\\u202f\\u2009\\u2006 ]{0,10})\\s*₽$/);
    if (!m) continue;
    let struck = false, el2 = el;
    let parentCls = '';
    while (el2) {
      const cs = getComputedStyle(el2);
      if (String(cs.textDecorationLine || '').includes('line-through')) struck = true;
      if (!parentCls && el2.parentElement) {
        parentCls = String(el2.parentElement.className || '').slice(0, 60);
      }
      el2 = el2.parentElement;
    }
    const v = parseInt(m[1].replace(/[\\u00a0\\u202f\\u2009\\u2006 ]/g, ''), 10);
    let sib = '';
    const p = el.closest('div');
    if (p && p.previousElementSibling) sib = (p.previousElementSibling.textContent || '').trim().slice(0, 40);
    if (!sib && p && p.nextElementSibling) sib = 'next: ' + (p.nextElementSibling.textContent || '').trim().slice(0, 40);
    out.push({v: v, struck: struck, sib: sib});
    if (out.length >= 12) break;
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
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(8)
        for n in await page.evaluate(DUMP_JS):
            lines.append(f"{n['v']:>6} struck={n['struck']} near={n['sib']!r}")
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
