"""Оффлайн-тесты чистых функций парсера (Playwright не нужен)."""
from __future__ import annotations

from bot.ozon import (extract_prices_from_html, looks_like_block,
                      normalize_url, parse_price_block)


# --- normalize_url ---------------------------------------------------------

def test_normalize_url_plain():
    assert normalize_url("https://www.ozon.ru/product/1234567890/") == ("https://www.ozon.ru/product/1234567890/", 1234567890)


def test_normalize_url_with_slug():
    url = "https://www.ozon.ru/product/smartfon-apple-iphone-15-128gb-972645812/"
    assert normalize_url(url) == ("https://www.ozon.ru/product/972645812/", 972645812)


def test_normalize_url_with_query_and_trash():
    url = "смотри https://www.ozon.ru/product/naushniki-besprovodnye-77123456/?utm=chat&utm=friend&from=sg  классные!"
    assert normalize_url(url) == ("https://www.ozon.ru/product/77123456/", 77123456)


def test_normalize_url_mobile_no_scheme():
    assert normalize_url("ozon.ru/product/5551234567") == ("https://www.ozon.ru/product/5551234567/", 5551234567)


def test_normalize_url_rejects_non_product():
    assert normalize_url("https://www.ozon.ru/category/telefony-30006/") is None
    assert normalize_url("https://www.ozon.ru/") is None
    assert normalize_url("просто текст") is None


def test_normalize_url_rejects_slug_without_sku():
    assert normalize_url("https://www.ozon.ru/product/chto-to-strannoe/") is None


# --- parse_price_block (текстовый фолбэк: min/max) --------------------------

def test_price_block_plain_only():
    assert parse_price_block("1 949 ₽") == (1949, None)


def test_price_block_card_then_without_label():
    # card = min, plain = max; зачёркнутую старую текст не различает
    text = "1 749 ₽\n1 949 ₽ без Ozon Карты"
    assert parse_price_block(text) == (1949, 1749)


def test_price_block_card_label_between():
    text = "1 749 ₽ с Ozon Картой\n1 949 ₽"
    assert parse_price_block(text) == (1949, 1749)


def test_price_block_card_only_single():
    text = "1 749 ₽ с Ozon Картой"
    assert parse_price_block(text) == (1749, None)


def test_price_block_no_prices():
    assert parse_price_block("Цена не указана") == (None, None)


def test_price_block_big_numbers():
    assert parse_price_block("129 900 ₽\n149 900 ₽ без Ozon Карты") == (149900, 129900)


def test_price_block_banks_format_2026():
    # реальная разметка 2026: 21 098 (с банками) / 22 691 / 32 438 (старая).
    # Порядок стабилен: карточная, обычная, старая -> первые две.
    text = " 21 098 ₽  С банками      22 691 ₽  32 438 ₽  С другими банками"
    assert parse_price_block(text) == (22691, 21098)


def test_price_block_banks_format_no_card():
    text = "22 691 ₽  32 438 ₽  С другими банками"
    assert parse_price_block(text) == (32438, 22691)


def test_price_block_skips_unit_price():
    # реальный кейс зубной щётки (набор): «638 ₽ за 1 шт» — не цена товара
    text = "1 276 ₽  С банками  1 418 ₽  8 888 ₽  С другими банками  638 ₽ за 1 шт"
    plain, card = parse_price_block(text)
    assert card == 1276      # отслеживаемая — «С банками» (первая в блоке)
    assert plain == 1418     # обычная — вторая; старая 8888 игнорируется


# --- extract_prices_from_html (fallback) -----------------------------------

def test_extract_from_json_card_and_price():
    html = '<script>{"price":{"price":"1490","cardPrice":"1390"}}</script>'
    assert extract_prices_from_html(html) == (1490, 1390)


def test_extract_from_json_price_only():
    html = '<script>{"currentPrice": 25990 }</script>'
    assert extract_prices_from_html(html) == (25990, None)


def test_extract_from_json_card_only_fills_price():
    html = '<script>{"cardPrice":"999"}</script>'
    assert extract_prices_from_html(html) == (999, 999)


def test_extract_from_json_nothing():
    assert extract_prices_from_html("<html><body>пусто</body></html>") == (None, None)


# --- looks_like_block ------------------------------------------------------

def test_block_by_title_antibot():
    assert looks_like_block("Antibot Challenge Page", "<html></html>") is True


def test_block_by_russian_marker():
    assert looks_like_block("Ozon", "доступ ограничен, подождите") is True


def test_not_block_normal_page():
    assert looks_like_block("Смартфон — Ozon", "<html>обычная карточка</html>") is False
