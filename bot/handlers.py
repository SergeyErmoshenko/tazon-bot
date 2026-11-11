"""Telegram-хендлеры: добавление по ссылке, список, графики, удаление, форс-проверка."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           Message)

from . import config, db
from .charts import make_chart
from .notifier import effective_price
from .ozon import normalize_url
from .runner import check_product, get_parser, run_check_all

log = logging.getLogger(__name__)

router = Router()

HELP_TEXT = (
    "Я слежу за ценами на Ozon 🛰\n\n"
    "• Кинь ссылку на товар — добавлю в мониторинг и покажу текущую цену\n"
    "• /list — список товаров (кнопка с 📈 пришлёт график)\n"
    "• /check — проверить все прямо сейчас\n"
    "• /del — удалить товар (можно сразу со ссылкой: /del https://…)\n"
    "• /help — эта справка\n\n"
    "Проверяю по расписанию, уведомлю при снижении "
    "(обычной цены или цены по Ozon Карте)."
)


def _guard(router: Router) -> None:
    """Бот отвечает только владельцу (ADMIN_CHAT_ID)."""
    admin_id = config.require_settings().admin_chat_id
    router.message.filter(F.chat.id == admin_id)
    router.callback_query.filter(F.from_user.id == admin_id)


@router.message(Command("start", "help"))
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    products = db.list_products(active_only=False)
    if not products:
        await message.answer("Список пуст. Кинь мне ссылку на товар Ozon — добавлю.")
        return

    rows: list[str] = []
    buttons: list[list[InlineKeyboardButton]] = []
    for p in products:
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
        rows.append(f"{p.id}. {title} — {price_str}{delta}")
        buttons.append([InlineKeyboardButton(text=f"📈 {title[:40]}", callback_data=f"chart:{p.id}")])

    await message.answer(
        "Твои товары:\n" + "\n".join(rows) + "\n\nКнопка — график:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        disable_web_page_preview=True,
    )


@router.message(Command("del"))
async def cmd_del(message: Message) -> None:
    # /del <ссылка> — удалить по ссылке; /del — показать кнопки
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        normalized = normalize_url(parts[1].strip())
        if normalized is None:
            await message.answer("Это не ссылка на товар Ozon. Пример: /del https://www.ozon.ru/product/…\nИли просто /del — покажу список с кнопками.")
            return
        _, sku = normalized
        product = db.get_by_sku(sku)
        if not product:
            await message.answer("Этого товара нет в списке.")
            return
        db.delete_product(product.id)
        title = (product.title or "(без названия)").strip()
        await message.answer(f"🗑 Удалил:\n{title}\n{product.url}", disable_web_page_preview=True)
        return

    products = db.list_products(active_only=False)
    if not products:
        await message.answer("Удалять нечего — список пуст.")
        return
    lines: list[str] = []
    buttons: list[list[InlineKeyboardButton]] = []
    for i, p in enumerate(products, 1):
        title = (p.title or "(название уточню при следующей проверке)").strip()
        lines.append(f"{i}. {title}\n   {p.url}")
        short = title if len(title) <= 50 else title[:50] + "…"
        buttons.append([InlineKeyboardButton(text=f"🗑 {i}. {short}", callback_data=f"del:{p.id}")])
    await message.answer(
        "Что удалить?\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        disable_web_page_preview=True,
    )


@router.message(Command("check"))
async def cmd_check(message: Message, bot: Bot) -> None:
    products = db.list_products(active_only=True)
    if not products:
        await message.answer("Список пуст — добавь сначала товары.")
        return
    est = int(len(products) * (sum(config.DELAY_BETWEEN_PRODUCTS) / 2 + 8) / 60) + 1
    await message.answer(f"Проверяю {len(products)} товаров, это займёт ~{est} мин. При снижении напишу.")
    asyncio.create_task(_run_and_report(bot))


async def _run_and_report(bot: Bot) -> None:
    try:
        summary = await run_check_all(bot)
        await bot.send_message(config.require_settings().admin_chat_id, summary)
    except Exception:  # noqa: BLE001 — фоновая задача не должна молча умереть
        log.exception("Прогон /check упал")


@router.callback_query(F.data.startswith("chart:"))
async def cb_chart(callback: CallbackQuery, bot: Bot) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    product = db.get_product(product_id)
    if not product:
        await callback.answer("Товар уже удалён", show_alert=True)
        return
    history = db.get_history(product_id)
    if len(history) < 2:
        await callback.answer("Пока одна точка — график будет после следующей проверки", show_alert=True)
        return
    await callback.answer("Рисую…")
    png = make_chart(product, history)
    await bot.send_photo(
        config.require_settings().admin_chat_id,
        photo=png,
        caption=f"📈 {product.title or product.url}\n{len(history)} точек истории",
    )


@router.callback_query(F.data.startswith("del:"))
async def cb_del(callback: CallbackQuery) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    if db.delete_product(product_id):
        await callback.answer("Удалил")
        if callback.message:
            await callback.message.delete()
    else:
        await callback.answer("Уже удалён", show_alert=True)


@router.message(F.text)
async def add_product(message: Message, bot: Bot) -> None:
    normalized = normalize_url(message.text or "")
    if normalized is None:
        await message.answer("Это не ссылка на товар Ozon. Жду ссылку вида https://www.ozon.ru/product/…")
        return
    url, sku = normalized

    existing = db.get_by_sku(sku)
    if existing:
        last = db.get_last_point(existing.id)
        if last:
            await message.answer("Этот товар уже в списке 🙂")
        else:
            await message.answer("Этот товар уже в списке, цены ещё не видел — возьму при следующей проверке.")
        return

    status = await message.answer("Открываю карточку, смотрю цену…")
    product = db.add_product(url, sku, title=None)
    result = await check_product(bot, product)

    if result == "blocked":
        await status.edit_text(
            "Добавил, но антибот сейчас не пустил 🛡\n"
            "Цену возьму при следующем прогоне (или попробуй /check через пару минут)."
        )
        return
    if result == "error":
        await status.edit_text(
            "Добавил, но цену прочитать не удалось 😕\n"
            f"{url}\nЕсли товар сняли с продажи — /del и удали."
        )
        return

    product = db.get_product(product.id) or product  # check_product мог записать title
    if not product.title:
        # гарантируем название сразу при добавлении: отдельная попытка,
        # если основной прогон не дождался заголовка
        title = await get_parser().fetch_title(url)
        if title:
            db.update_title(product.id, title)
            product = db.get_product(product.id) or product
    last = db.get_last_point(product.id)
    price_str = "цена не отображается"
    if last:
        eff = effective_price(last.price, last.card_price)
        if eff is not None:
            price_str = f"{eff:,} ₽".replace(",", " ") + (" с Ozon Картой" if last.card_price else "")
    title = product.title or "(название уточню при следующей проверке)"
    await status.edit_text(
        f"✅ Добавил в мониторинг:\n{title}\nСейчас: {price_str}\n\n"
        f"Уведомлю, когда подешевеет. /list — все товары."
    )


def setup_router() -> Router:
    _guard(router)
    return router
