"""Дамп ответа card.wb.ru через Chrome бота (антибот WB блокирует небраузерные клиенты)."""
import asyncio
import json
import subprocess
import sys

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NM = sys.argv[1] if len(sys.argv) > 1 else "604961294"
API_URL = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={NM}"


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
        await page.goto(API_URL, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(3)
        body = (await page.evaluate("() => document.body ? document.body.innerText : ''")).strip()
        lines = [f"BODY HEAD: {body[:300]}"]
        try:
            d = json.loads(body)
            products = d.get("data", {}).get("products", [])
            if products:
                prod = products[0]
                lines.append(f"name: {(prod.get('name') or '')[:60]}")
                lines.append(f"priceU: {prod.get('priceU')} salePriceU: {prod.get('salePriceU')} sale: {prod.get('sale')}")
                lines.append("PARSED-OK")
            else:
                lines.append("no products in JSON")
        except json.JSONDecodeError as e:
            lines.append(f"JSON parse fail: {e}")
        for line in lines:
            print(line)
        with open(r"C:\Users\1\wb_out.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    finally:
        await page.close()
        await browser.close()
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
