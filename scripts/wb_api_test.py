"""Тест публичного API Wildberries с ноутбука."""
import asyncio
import json
import sys

import aiohttp

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36")
API = "https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={nm}"


async def main() -> None:
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        for nm in (604961294, 16530335):
            try:
                async with s.get(API.format(nm=nm), timeout=aiohttp.ClientTimeout(total=20)) as r:
                    body = await r.text()
                    print(f"--- nm={nm}: HTTP {r.status}, {len(body)} bytes")
                    d = json.loads(body)
                    products = d.get("data", {}).get("products", [])
                    if not products:
                        print("  no products")
                        continue
                    p = products[0]
                    print("  name:", (p.get("name") or p.get("imt_name") or "")[:60])
                    print("  priceU:", p.get("priceU"), "salePriceU:", p.get("salePriceU"), "sale:", p.get("sale"))
                    print("  keys:", sorted(p.keys())[:20])
            except Exception as e:
                print(f"--- nm={nm}: FAIL {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
