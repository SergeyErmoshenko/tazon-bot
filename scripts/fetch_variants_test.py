"""Разовая диагностика: как Chromium проходит на Ozon (прямо / через прокси / с разогревом).

Запускается на ноутбуке: python scripts/fetch_variants_test.py
НЕ часть бота — лежит для воспроизводимости экспериментов с антиботом.
"""
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

PRODUCT = "https://www.ozon.ru/product/5677610222/"


async def variant(p, name, proxy=None, warmup=False, profile="", channel="chromium"):
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=profile,
        headless=True,
        channel=channel,
        proxy=proxy,
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    page = await ctx.new_page()
    try:
        if warmup:
            await page.goto("https://www.ozon.ru/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            print(f"  [{name}] warmup title: {(await page.title())[:60]!r}")
        r = await page.goto(PRODUCT, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        title = await page.title()
        h1 = None
        try:
            await page.wait_for_selector("h1", timeout=15000)
            el = await page.query_selector("h1")
            if el:
                h1 = (await el.text_content())[:60]
        except Exception:
            pass
        price_txt = None
        price_el = await page.query_selector("[data-widget='webPrice']")
        if price_el:
            price_txt = (await price_el.text_content())[:80]
        print(f"  [{name}] status={r.status if r else '?'} title={title[:60]!r} h1={h1!r} price={price_txt!r}")
    except Exception as e:
        print(f"  [{name}] FAIL {type(e).__name__}: {e}")
    finally:
        await ctx.close()


async def main():
    async with async_playwright() as p:
        print("[1/3] bundled chromium, direct + warmup:")
        await variant(p, "direct+warmup", warmup=True, profile="C:/Users/1/pw-prof-a")
        print("[2/3] real Chrome binary, direct + warmup:")
        await variant(p, "chrome+warmup", warmup=True, profile="C:/Users/1/pw-prof-c", channel="chrome")
        print("[3/3] real Chrome binary, via proxy 7897 + warmup:")
        await variant(p, "chrome+proxy", proxy={"server": "http://127.0.0.1:7897"}, warmup=True, profile="C:/Users/1/pw-prof-d", channel="chrome")


if __name__ == "__main__":
    asyncio.run(main())
