"""Прогон проверки товаров: браузер -> БД -> уведомления подписчикам.

Используется и расписанием (все товары), и командой /check (только товары
запросившего). Lock гарантирует один одновременный прогон.
"""
from __future__ import annotations

import asyncio
import logging
import random

from aiogram import Bot

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import config, db, notifier
from .ozon import OzonParser

log = logging.getLogger(__name__)

_run_lock = asyncio.Lock()
_parsers: dict[str, OzonParser] = {}


def get_parser(store: str = "ozon") -> OzonParser:
    """Парсер на магазин: ЗЯ ходит через отдельный профиль (config.GA_*),
    остальные — через общий."""
    if store not in _parsers:
        if store == "goldapple":
            _parsers[store] = OzonParser(cdp_port=config.GA_CDP_PORT, profile_dir=config.GA_PROFILE_DIR)
        else:
            _parsers[store] = OzonParser()
    return _parsers[store]


async def close_parsers() -> None:
    """Погасить все Chrome-инстансы (в конце прогона)."""
    for parser in _parsers.values():
        await parser.close()


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _chart_keyboard(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📈 График", callback_data=f"chart:{product_id}")]]
    )


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _notify_subscribers(bot: Bot, product: db.Product, text: str,
                              with_chart_button: bool = False) -> None:
    markup = _chart_keyboard(product.id) if with_chart_button else None
    for chat_id in db.subscribers(product.id):
        try:
            # parse_mode явный: уведомления могут уходить из вспомогательных
            # скриптов, где у Bot нет HTML-дефолта
            await bot.send_message(chat_id, text, parse_mode="HTML",
                                   link_preview_options={"is_disabled": True},
                                   reply_markup=markup)
        except Exception:  # noqa: BLE001 — один недоступный чат не роняет рассылку
            log.warning("Не доставил уведомление chat_id=%s (product %s)", chat_id, product.sku)


async def check_product(bot: Bot, product: db.Product) -> str:
    """Проверить один товар: записать точку, уведомить подписчиков о снижении."""
    parser = get_parser(product.store)
    result = await parser.fetch_prices(product.url)

    if result.out_of_stock:
        was_out = db.is_out(product.id)
        db.set_out(product.id, True)
        db.reset_fail(product.id)
        if not was_out:
            title = (product.title or product.display_url).strip()
            await _notify_subscribers(
                bot, product,
                f"🚫 Товар закончился:\n<b>{_escape_html(title)}</b>\nНапишу, когда появится снова.",
                with_chart_button=False,
            )
        return "out"

    # товар снова в наличии — сообщаем один раз и возвращаем флаг
    if result.ok and db.is_out(product.id):
        db.set_out(product.id, False)
        title = (product.title or product.display_url).strip()
        eff = notifier.effective_price(result.price, result.card_price)
        price_str = f" Цена: {eff:,} ₽".replace(",", " ") if eff else ""
        await _notify_subscribers(
            bot, product,
            f"✅ Товар снова в наличии!{_escape_html(price_str)}\n<b>{_escape_html(title)}</b>\n{product.display_url}",
        )

    if result.blocked:
        fails = db.increment_fail(product.id)
        log.warning("Антибот: %s (подряд %d)", product.url, fails)
        if fails == config.FAIL_ALERT_THRESHOLD:
            await _notify_subscribers(
                bot, product,
                f"⚠️ {fails} прогонов подряд не читается:\n{product.url}\n"
                f"Возможно, товар сняли с продажи или антибот ужесточился.",
            )
        return "blocked"

    if result.error or (result.price is None and result.card_price is None):
        fails = db.increment_fail(product.id)
        log.warning("Ошибка чтения %s: %s (подряд %d)", product.url, result.error, fails)
        if fails == config.FAIL_ALERT_THRESHOLD:
            await _notify_subscribers(
                bot, product,
                f"⚠️ Товар {fails} прогонов подряд без цены:\n{product.url}\n{result.error or 'цена не найдена'}",
            )
        return "error"

    db.reset_fail(product.id)
    if result.title and product.title != result.title:
        db.update_title(product.id, result.title)

    prev = db.get_last_point(product.id)
    db.insert_point(product.id, result.price, result.card_price)

    card_labels = {"ozon": "Цена с Ozon Картой", "goldapple": "Цена в клубе",
                   "wildberries": "Цена с WB Кошельком"}
    drops = notifier.detect_drops(
        prev, result.price, result.card_price,
        card_label=card_labels.get(product.store, "Цена"),
    )
    msg = notifier.build_drop_message(product, drops)
    if msg:
        await _notify_subscribers(bot, product, msg, with_chart_button=True)
        log.info("Снижение по %s: %s", product.url, drops)
    return "drop" if drops else "ok"


async def run_check_all(bot: Bot, chat_id: int | None = None) -> str:
    """Прогон: товары пользователя (chat_id) или все (расписание).

    Chrome терминируется в finally — он нужен только на время прогона
    (свежий subprocess проходит антибот так же, см. CLAUDE.md).
    """
    async with _run_lock:
        try:
            products = db.list_user_products(chat_id) if chat_id else db.list_all_products()
            if not products:
                return "Список товаров пуст — кинь мне ссылку на товар Ozon, чтобы добавить."

            stats = {"ok": 0, "drop": 0, "blocked": 0, "error": 0, "out": 0}
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
                f"закончились {stats.get('out', 0)}, "
                f"антибот {stats.get('blocked', 0)}, "
                f"ошибки {stats.get('error', 0)}"
            )
            log.info(summary)
            return summary
        finally:
            await close_parsers()


async def resolve_single(raw_url: str) -> tuple[str, int] | None:
    """Развернуть короткую ссылку через Chrome (под общим локом, с гашением)."""
    async with _run_lock:
        try:
            return await get_parser().resolve(raw_url)
        finally:
            await close_parsers()


async def run_single(bot: Bot, product: db.Product) -> tuple[str, db.Product]:
    """Проверка одного товара (при добавлении) под общим локом.

    Возвращает (статус, свежий Product). Тоже гасит Chrome по завершении.
    """
    async with _run_lock:
        try:
            status = await check_product(bot, product)
            product = db.get_product(product.id) or product
            if status == "ok" and not product.title:
                title = await get_parser(product.store).fetch_title(product.url)
                if title:
                    db.update_title(product.id, title)
                    product = db.get_product(product.id) or product
            return status, product
        finally:
            await close_parsers()
