"""Тесты детекта снижения и текстов уведомлений (без Telegram).

Семантика: отслеживается одна минимальная цена (card_price, иначе price).
"""
from __future__ import annotations

from datetime import datetime

from bot.db import PricePoint, Product
from bot.formatting import NBSP
from bot.notifier import build_drop_message, detect_drops, effective_price


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


# --- effective_price --------------------------------------------------------

def test_effective_prefers_card():
    assert effective_price(1000, 900) == 900
    assert effective_price(1000, None) == 1000
    assert effective_price(None, 900) == 900
    assert effective_price(None, None) is None


# --- detect_drops -----------------------------------------------------------

def test_first_point_is_not_drop():
    assert detect_drops(None, 1000, 900) == []


def test_no_change_no_drop():
    assert detect_drops(_point(1000, 900), 1000, 900) == []


def test_rise_is_not_drop():
    assert detect_drops(_point(1000, 900), 1200, 950) == []


def test_plain_drop_does_not_matter():
    """Обычная упала, минимальная нет — владелец следит только за минимальной."""
    assert detect_drops(_point(1000, 900), 900, 900) == []


def test_card_drop_notifies():
    old = _point(1000, 900)
    drops = detect_drops(old, 1000, 800)
    assert len(drops) == 1
    assert drops[0].label == "Цена с Ozon Картой"
    assert (drops[0].old, drops[0].new) == (900, 800)
    assert drops[0].diff == 100
    assert drops[0].percent == 11.1


def test_min_price_falls_back_to_plain():
    """Карточной не было и нет — следим за обычной."""
    drops = detect_drops(_point(1000, None), 950, None)
    assert len(drops) == 1
    assert drops[0].label == "Цена"
    assert (drops[0].old, drops[0].new) == (1000, 950)


def test_card_price_appearing_below_plain_not_notified():
    """Карточная появилась, когда обычная не изменилась — это не «снижение»
    отслеживаемой цены? Наоборот: eff упала 1000 -> 800, значит это снижение."""
    drops = detect_drops(_point(1000, None), 1000, 800)
    assert len(drops) == 1
    assert (drops[0].old, drops[0].new) == (1000, 800)


def test_none_new_values_no_drop():
    assert detect_drops(_point(1000, 900), None, None) == []


# --- текст сообщения --------------------------------------------------------

def test_message_contains_numbers_and_link():
    old = _point(1000, 900)
    drops = detect_drops(old, 1000, 800)
    msg = build_drop_message(PRODUCT, drops)
    assert msg is not None
    assert "900 ₽ → <b>800 ₽</b>" in msg
    assert "(−100 ₽, −11.1%)" in msg
    assert "Цена с Ozon Картой" in msg
    assert PRODUCT.url in msg


def test_message_escapes_html_in_title():
    drops = detect_drops(_point(1000, None), 950, None)
    msg = build_drop_message(PRODUCT, drops)
    assert "&amp;" in msg and "&lt;" in msg


def test_message_none_when_no_drops():
    assert build_drop_message(PRODUCT, []) is None
