"""Тесты детекта снижения и текстов уведомлений (без Telegram)."""
from __future__ import annotations

from datetime import datetime

from bot.db import PricePoint, Product
from bot.formatting import NBSP
from bot.notifier import build_drop_message, detect_drops


def _point(price: int | None, card: int | None, minutes_ago: int = 0) -> PricePoint:
    return PricePoint(
        id=1,
        product_id=1,
        price=price,
        card_price=card,
        checked_at=datetime(2026, 11, 11, 12, minutes_ago),
    )


PRODUCT = Product(id=1, url="https://www.ozon.ru/product/1234567890/", sku=1234567890,
                  title="Наушники & <классные>", is_active=True, fail_count=0,
                  added_at="2026-11-11T12:00:00")


def test_first_point_is_not_drop():
    assert detect_drops(None, 1000, 900) == []


def test_no_change_no_drop():
    old = _point(1000, 900)
    assert detect_drops(old, 1000, 900) == []


def test_rise_is_not_drop():
    old = _point(1000, 900)
    assert detect_drops(old, 1200, 950) == []


def test_plain_drop_only():
    old = _point(1000, 900)
    drops = detect_drops(old, 900, 900)
    assert len(drops) == 1
    assert drops[0].kind == "price"
    assert drops[0].diff == 100
    assert drops[0].percent == 10.0


def test_card_drop_only():
    """Карточная упала, обычная нет — уведомляем всё равно."""
    old = _point(1000, 900)
    drops = detect_drops(old, 1000, 800)
    assert len(drops) == 1
    assert drops[0].kind == "card"
    assert drops[0].percent == 11.1


def test_both_drops():
    old = _point(1000, 900)
    drops = detect_drops(old, 900, 800)
    assert [d.kind for d in drops] == ["price", "card"]


def test_none_new_values_no_drop():
    """Цена «не нашли» — это не снижение и не рост, молчим."""
    old = _point(1000, 900)
    assert detect_drops(old, None, None) == []


def test_old_none_new_value_is_not_drop():
    """Раньше цены по карте не было, теперь появилась — не уведомляем."""
    old = _point(1000, None)
    assert detect_drops(old, 1000, 800) == []


# --- текст сообщения --------------------------------------------------------

def test_message_contains_numbers_and_link():
    old = _point(1000, 900)
    drops = detect_drops(old, 900, 800)
    msg = build_drop_message(PRODUCT, drops)
    assert msg is not None
    assert f"1{NBSP}000 ₽ → <b>900 ₽</b>" in msg
    assert "(−100 ₽, −10.0%)" in msg
    assert "Цена по Ozon Карте" in msg
    assert PRODUCT.url in msg


def test_message_escapes_html_in_title():
    old = _point(1000, None)
    drops = detect_drops(old, 950, None)
    msg = build_drop_message(PRODUCT, drops)
    assert "&amp;" in msg and "&lt;" in msg


def test_message_none_when_no_drops():
    assert build_drop_message(PRODUCT, []) is None
