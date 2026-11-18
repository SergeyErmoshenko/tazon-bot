"""Пытаемся пройти Яндекс SmartCaptcha: reload + клик по кнопке подтверждения."""
import asyncio
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot import config  # noqa: E402


def kill_chrome_tree(proc):
    """terminate() убивает только главный процесс — Chrome-дети осирают."""
    import subprocess as sp
    if sys.platform == "win32":
        sp.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        proc.terminate()


URL = "https://market.yandex.ru/card/naushniki-nakladnyye-besprovodnyye-ergolux-elx-bthp01-c02-fm-mp3-mikrofon-chernyye-korobka-15355/6041984286"

CLICK_JS = """
() => {
  const btns = document.querySelectorAll('button, [role="button"], input[type="submit"], label');
  const words = ['подтверд', 'не робот', 'не робот?', 'продолжить', 'все в порядке'];
  for (const b of btns) {
    const t = (b.textContent || b.getAttribute('value') || '').trim().toLowerCase();
    if (t && words.some(w => t.includes(w)) && t.length < 60) {
      b.click();
      return 'clicked: ' + t.slice(0, 40);
    }
  }
  return 'no button';
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
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            await asyncio.sleep(5)
            title = (await page.title() or "").lower()
            if "робот" not in title and "robot" not in title:
                lines.append(f"PASSED: title={title[:60]!r}")
                prices = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('[class*="price" i]'))
                        .map(e => (e.textContent || '').trim().slice(0, 30))
                        .filter(t => t.includes('₽')).slice(0, 8)
                """)
                lines.append(f"prices: {prices}")
                break
            clicked = await page.evaluate(CLICK_JS)
            lines.append(f"captcha still: title={title[:40]!r}, {clicked}")
            await page.reload(wait_until="domcontentloaded")
    except Exception as e:
        lines.append(f"FAIL: {type(e).__name__}: {e}")
    finally:
        await page.close()
        await browser.close()
        kill_chrome_tree(proc)
    for line in lines:
        print(line)
    with open(r"C:\Users\1\yam_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
