"""Прогон проверки всех товаров: браузер -> БД -> уведомления.

Используется и расписанием (APScheduler), и командой /check.
Lock гарантирует один одновременный прогон (не гоняем два браузера).
"""
from __future__ import annotations

import asyncio
import logging
import random

from aiogram import Bot

from . import config, db, notifier
from .ozon import OzonParser

log = logging.getLogger(__name__)

_run_lock = asyncio.Lock()
_parser: OzonParser | None = None


def get_parser() -> OzonParser:
    global _parser
    if _parser is None:
        _parser = OzonParser()
    return _parser


async def check_product(bot: Bot, product: db.Product) -> str:
    """Проверить один товар: записать точку, уведомить о снижении. Возвращает статус."""
    parser = get_parser()
    result = await parser.fetch_prices(product.url)

    chat_id = config.require_settings().admin_chat_id

    if result.blocked:
        fails = db.increment_fail(product.id)
        log.warning("Антибот: %s (подряд %d)", product.url, fails)
        if fails == config.FAIL_ALERT_THRESHOLD:
            await bot.send_message(
                chat_id,
                f"⚠️ {fails} прогонов подряд не читается:\n{product.url}\n"
                f"Возможно, товар сняли с продажи или антибот ужесточился "
                f"(попробуй /check позже или открой ссылку в браузере).",
            )
        return "blocked"

    if result.error or (result.price is None and result.card_price is None):
        fails = db.increment_fail(product.id)
        log.warning("Ошибка чтения %s: %s (подряд %d)", product.url, result.error, fails)
        if fails == config.FAIL_ALERT_THRESHOLD:
            await bot.send_message(
                chat_id,
                f"⚠️ Товар {fails} прогонов подряд без цены:\n{product.url}\n{result.error or 'цена не найдена'}",
            )
        return "error"

    db.reset_fail(product.id)
    if result.title and product.title != product.title:
        db.update_title(product.id, result.title)

    prev = db.get_last_point(product.id)
    db.insert_point(product.id, result.price, result.card_price)

    drops = notifier.detect_drops(prev, result.price, result.card_price)
    msg = notifier.build_drop_message(product, drops)
    if msg:
        await bot.send_message(chat_id, msg, disable_web_page_preview=True)
        log.info("Снижение по %s: %s", product.url, drops)
    return "drop" if drops else "ok"


async def run_check_all(bot: Bot) -> str:
    """Прогон по всем активным товарам. Возвращает сводку для ответа пользователю."""
    async with _run_lock:
        products = db.list_products(active_only=True)
        if not products:
            return "Список товаров пуст — кинь мне ссылку на товар Ozon, чтобы добавить."

        stats = {"ok": 0, "drop": 0, "blocked": 0, "error": 0}
        for i, product in enumerate(products):
            try:
                status = await check_product(bot, product)
            except Exception:  # noqa: BLE001 — один товар не должен ронять прогон
                log.exception("Прогон по товару %s упал", product.url)
                status = "error"
            stats[status] = stats.get(status, 0) + 1
            if i < len(products) - 1:
                await asyncio.sleep(random.uniform(*config.DELAY_BETWEEN_PRODUCTS))

        summary = (
            f"✅ Проверено {len(products)}: "
            f"снизились {stats.get('drop', 0)}, "
            f"без изменений {stats.get('ok', 0)}, "
            f"антибот {stats.get('blocked', 0)}, "
            f"ошибки {stats.get('error', 0)}"
        )
        log.info(summary)
        return summary
