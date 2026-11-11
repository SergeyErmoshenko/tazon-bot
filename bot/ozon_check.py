"""Диагностика парсера на живой карточке: python -m bot.ozon_check <url> [--show]

Печатает, что удалось извлечь (цены, title, признаки антибота) — удобно,
чтобы проверить селекторы на реальной странице без запуска бота.
--show открывает окно браузера (headless=False).
"""
from __future__ import annotations

import asyncio
import sys

from .ozon import OzonParser, normalize_url


async def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    raw_url = argv[0]
    show = "--show" in argv[1:]

    normalized = normalize_url(raw_url)
    if normalized is None:
        print("Не похоже на ссылку на товар Ozon: нужна вида https://www.ozon.ru/product/…")
        return 2
    url, sku = normalized
    print(f"URL: {url}\nSKU: {sku}\n")

    parser = OzonParser(headless=not show)
    try:
        result = await parser.fetch_prices(url)
    finally:
        await parser.close()

    print(f"ok       : {result.ok}")
    print(f"blocked  : {result.blocked}")
    print(f"error    : {result.error}")
    print(f"title    : {result.title}")
    print(f"price    : {result.price}")
    print(f"card     : {result.card_price}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
