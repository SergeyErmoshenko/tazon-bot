"""Telegram-хендлеры: многопользовательский режим.

Каждый пользователь ведёт свой список (таблица подписок); одинаковые товары
у разных людей разделяют одну историю цен — обход идёт один раз на URL.
Уведомления о снижении получают все подписчики товара.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

from . import config, db
from .charts import make_chart
from .notifier import effective_price
from .ozon import normalize_url
from .runner import run_check_all, run_single

log = logging.getLogger(__name__)

router = Router()

HELP_TEXT = (
    "Я слежу за ценами на Ozon 🛰\n\n"
    "• Кинь ссылку на товар — добавлю в твой список и покажу текущую цену\n"
    "• /list — твой список товаров (кнопка пришлёт график)\n"
    "• /check — проверить твои товары прямо сейчас\n"
    "• /del — удалить товар (можно сразу со ссылкой: /del https://…)\n"
    "• /help — эта справка\n\n"
    "Проверяю по расписанию, уведомлю при снижении минимальной цены "
    "(«с Ozon Картой» / «С банками»). Один и тот же товар у разных людей — "
    "общая история цен, но уведомления у каждого свои."
)


@router.message(Command("start", "help"))
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    chat_id = message.chat.id
    products = db.list_user_products(chat_id)
    if not products:
        await message.answer("Твой список пуст. Кинь мне ссылку на товар Ozon — добавлю.")
        return

    rows: list[str] = []
    buttons: list[list[InlineKeyboardButton]] = []
    for i, p in enumerate(products, 1):
        last = db.get_last_point(p.id)
        first = db.get_first_point(p.id)
        title = (p.title or "⏳ название уточню при следующей проверке")
        if len(title) > 120:
            title = title[:120] + "…"
        price_str = "—"
        if last:
            eff = effective_price(last.price, last.card_price)
            if eff is not None:
                price_str = f"{eff:,} ₽".replace(",", " ") + (" с картой" if last.card_price else "")
        delta = ""
        if last and first and last.price and first.price and last.price != first.price:
            d = last.price - first.price
            sign = "+" if d > 0 else ""
            delta = f" ({sign}{d:,} ₽ к первой)".replace(",", " ")
        rows.append(f"{i}. {title} — {price_str}{delta}\n   ссылка: {p.display_url}")
        buttons.append([InlineKeyboardButton(text=f"📈 {i}. {title[:40]}", callback_data=f"chart:{p.id}")])

    await message.answer(
        "Твои товары:\n" + "\n".join(rows) + "\n\nКнопка — график:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        disable_web_page_preview=True,
    )


@router.message(Command("del"))
async def cmd_del(message: Message) -> None:
    chat_id = message.chat.id
    # /del <ссылка> — удалить по ссылке; /del — показать кнопки
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        normalized = normalize_url(parts[1].strip())
        if normalized is None:
            await message.answer("Это не ссылка на товар Ozon. Пример: /del https://www.ozon.ru/product/…\nИли просто /del — покажу список с кнопками.")
            return
        _, sku = normalized
        product = db.get_by_sku(sku)
        if not product or not db.is_subscribed(chat_id, product.id):
            await message.answer("Этого товара нет в твоём списке.")
            return
        db.unsubscribe(chat_id, product.id)
        title = (product.title or "(без названия)").strip()
        await message.answer(f"🗑 Удалил из твоего списка:\n{title}\n{product.url}", disable_web_page_preview=True)
        return

    products = db.list_user_products(chat_id)
    if not products:
        await message.answer("Удалять нечего — твой список пуст.")
        return
    lines: list[str] = []
    buttons: list[list[InlineKeyboardButton]] = []
    for i, p in enumerate(products, 1):
        title = (p.title or "(название уточню при следующей проверке)").strip()
        lines.append(f"{i}. {title}\n   ссылка: {p.display_url}")
        short = title if len(title) <= 50 else title[:50] + "…"
        buttons.append([InlineKeyboardButton(text=f"🗑 {i}. {short}", callback_data=f"del:{p.id}")])
    await message.answer(
        "Что удалить?\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        disable_web_page_preview=True,
    )


@router.message(Command("check"))
async def cmd_check(message: Message, bot: Bot) -> None:
    products = db.list_user_products(message.chat.id)
    if not products:
        await message.answer("Твой список пуст — добавь сначала товары.")
        return
    est = int(len(products) * (sum(config.DELAY_BETWEEN_PRODUCTS) / 2 + 8) / 60) + 1
    await message.answer(f"Проверяю {len(products)} товаров, это займёт ~{est} мин. При снижении напишу.")
    asyncio.create_task(_run_and_report(bot, message.chat.id))


async def _run_and_report(bot: Bot, chat_id: int) -> None:
    try:
        summary = await run_check_all(bot, chat_id=chat_id)
        await bot.send_message(chat_id, summary)
    except Exception:  # noqa: BLE001 — фоновая задача не должна молча умереть
        log.exception("Прогон /check упал")


@router.callback_query(F.data.startswith("chart:"))
async def cb_chart(callback: CallbackQuery, bot: Bot) -> None:
    product_id = int((callback.data or "").split(":", 1)[1])
    chat_id = callback.from_user.id
    product = db.get_product(product_id)
    if not product or not db.is_subscribed(chat_id, product_id):
        await callback.answer("Этого товара нет в твоём списке", show_alert=True)
        return
    history = db.get_history(product_id)
    if len(history) < 2:
        await callback.answer("Пока одна точка — график будет после следующей проверки", show_alert=True)
        return
    await callback.answer("Рисую…")
    png = make_chart(product, history)
    await bot.send_photo(
        chat_id,
        photo=BufferedInputFile(png, filename="chart.png"),
        caption=f"📈 {product.title or product.url}\n{len(history)} точек истории",
    )


@router.callback_query(F.data.startswith("del:"))
async def cb_del(callback: CallbackQuery) -> None:
    product_id = int((callback.data or "").split(":", 1)[1])
    chat_id = callback.from_user.id
    if db.unsubscribe(chat_id, product_id):
        await callback.answer("Удалил из твоего списка")
        if callback.message:
            await callback.message.delete()
    else:
        await callback.answer("Этого товара уже нет в твоём списке", show_alert=True)


@router.message(F.text)
async def add_product(message: Message, bot: Bot) -> None:
    chat_id = message.chat.id
    normalized = normalize_url(message.text or "")
    if normalized is None:
        await message.answer("Это не ссылка на товар Ozon. Жду ссылку вида https://www.ozon.ru/product/…")
        return
    url, sku = normalized
    sent_link = (message.text or "").strip()

    existing = db.get_by_sku(sku)
    if existing and db.is_subscribed(chat_id, existing.id):
        # уже в списке — но обновим сохранённую ссылку на присланный вариант
        db.update_orig_url(existing.id, sent_link)
        await message.answer("Этот товар уже в твоём списке 🙂 — обновил ссылку на присланный вариант.")
        return

    product = db.add_product(url, sku, title=None, orig_url=sent_link)
    db.subscribe(chat_id, product.id)

    status = await message.answer("Открываю карточку, смотрю цену…")
    result, product = await run_single(bot, product)

    if result == "blocked":
        await status.edit_text(
            "Добавил в твой список, но антибот сейчас не пустил 🛡\n"
            "Цену возьму при следующем прогоне (или попробуй /check через пару минут)."
        )
        return
    if result == "error":
        await status.edit_text(
            "Добавил в твой список, но цену прочитать не удалось 😕\n"
            f"{url}\nЕсли товар сняли с продажи — /del и удали."
        )
        return

    last = db.get_last_point(product.id)
    price_str = "цена не отображается"
    if last:
        eff = effective_price(last.price, last.card_price)
        if eff is not None:
            price_str = f"{eff:,} ₽".replace(",", " ") + (" с Ozon Картой" if last.card_price else "")
    title = product.title or "(название уточню при следующей проверке)"
    await status.edit_text(
        f"✅ Добавил в твой список:\n{title}\nСейчас: {price_str}\n\n"
        f"Уведомлю, когда подешевеет. /list — твой список."
    )


def setup_router() -> Router:
    return router
