"""Получение цен с карточки товара Ozon через реальный браузер (Playwright).

Устроено в два слоя:
- чистые функции (normalize_url / parse_price_block / extract_prices_from_html /
  looks_like_block) — работают по строке, тестируются оффлайн на фикстурах;
- OzonParser — браузерная обвязка: persistent-профиль (куки антибота живут между
  прогонами), stealth-маскировка, последовательный обход с задержками и ретраями.

Все знания о вёрстке Ozon сосредоточены здесь: если цены перестали читаться —
чинить селекторы PRICE_SELECTORS и паттерны PRICE_JSON_PATTERNS в этом файле.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass

from . import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Чистые функции парсинга (без Playwright)
# ---------------------------------------------------------------------------

_PRODUCT_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?ozon\.ru/product/([^/?#]+)/?", re.IGNORECASE
)
_SKU_RE = re.compile(r"(\d{5,})\s*/?\s*$")

# Число с разделителями разрядов (пробел, узкий пробел, nbsp) и знаком рубля
_PRICE_IN_TEXT_RE = re.compile(r"(\d[\d   \s]{0,15})\s*₽")

# Блоки DOM, где живёт цена (в порядке приоритета)
PRICE_SELECTORS = [
    "[data-widget='webPrice']",
    "[data-widget='webSalePrice']",
    "[data-widget='price']",
]

# Fallback: JSON, вшитый в страницу. Порядок = приоритет.
PRICE_JSON_PATTERNS = [
    (re.compile(r'"cardPrice"\s*:\s*"?(\d{3,})'), "card"),
    (re.compile(r'"price"\s*:\s*\{[^{}]*?"price"\s*:\s*"?(\d{3,})'), "price"),
    (re.compile(r'"currentPrice"\s*:\s*"?(\d{3,})'), "price"),
    (re.compile(r'"price"\s*:\s*"?(\d{3,})'), "price"),
]

# Признаки страницы-блока (антибот / ограничение доступа).
# Слабые маркеры проверяем только в <title> (в теле страницы слово "antibot"
# может встретиться в скриптах нормальной карточки).
TITLE_BLOCK_MARKERS = ("antibot", "доступ ограничен", "доступ заблокирован", "just a moment")
BODY_BLOCK_MARKERS = ("antibot challenge", "доступ ограничен", "доступ заблокирован", "just a moment")


def normalize_url(raw: str) -> tuple[str, int] | None:
    """Из любой ссылки/текста с ozon.ru/product/... -> (канонический url, sku).

    Возвращает None, если это не ссылка на карточку товара или sku не найден.
    """
    m = _PRODUCT_URL_RE.search(raw)
    if not m:
        return None
    slug = m.group(1)
    sku_m = _SKU_RE.search(slug)
    if not sku_m:
        return None
    sku = int(sku_m.group(1))
    return f"https://www.ozon.ru/product/{sku}/", sku


def _to_int(number: str) -> int:
    return int(re.sub(r"[   \s]", "", number))


def _nearest_before(prices: list[tuple[int, int]], pos: int) -> int | None:
    """Цена, стоящая в тексте непосредственно перед позицией pos (или None)."""
    before = [p for at, p in prices if at < pos]
    return before[-1] if before else None


def _nearest_after(prices: list[tuple[int, int]], pos: int) -> int | None:
    """Первая цена, стоящая после позиции pos (или None)."""
    after = [p for at, p in prices if at > pos]
    return after[0] if after else None


def parse_price_block(text: str) -> tuple[int | None, int | None]:
    """Разобрать текст блока цены (innerText виджета webPrice).

    Типичные варианты (подписи идут ПОСЛЕ своей цены):
      "1 949 ₽"                                  -> (1949, None)
      "1 749 ₽\\n1 949 ₽ без Ozon Карты"         -> (1949, 1749)
      "1 749 ₽ с Ozon Картой\\n1 949 ₽"          -> (1949, 1749)

    Возвращает (обычная цена, цена по Ozon Карте).
    """
    prices = [(m.start(), _to_int(m.group(1))) for m in _PRICE_IN_TEXT_RE.finditer(text)]
    prices = [(pos, p) for pos, p in prices if p >= 10]  # отсечь мусорные числа
    if not prices:
        return None, None

    lower = text.lower()
    without_idx = lower.find("без ozon карт")
    with_idx = lower.find("с ozon карт")

    plain: int | None = None
    card: int | None = None

    if without_idx != -1:
        # "... CARD ₽ ... PLAIN ₽ без Ozon Карты" — подпись при обычной цене
        plain = _nearest_before(prices, without_idx)
        plain_pos = next((at for at, p in prices if p == plain and at < without_idx), -1)
        card = _nearest_before(prices, plain_pos) if plain_pos > 0 else None
    elif with_idx != -1:
        # "... CARD ₽ с Ozon Картой ... PLAIN ₽"
        card = _nearest_before(prices, with_idx)
        plain = _nearest_after(prices, with_idx)
    else:
        plain = prices[0][1]

    return plain, card


def extract_prices_from_html(html: str) -> tuple[int | None, int | None]:
    """Fallback, когда DOM-виджет недоступен: искать цены в JSON внутри HTML."""
    price: int | None = None
    card: int | None = None
    for pattern, kind in PRICE_JSON_PATTERNS:
        m = pattern.search(html)
        if not m:
            continue
        value = int(m.group(1))
        if kind == "card" and card is None:
            card = value
        elif kind == "price" and price is None:
            price = value
        if price is not None and card is not None:
            break
    if price is None and card is not None:
        price = card
    return price, card


def looks_like_block(status: int | None, title: str, html: str) -> bool:
    """Похоже ли на страницу антибот-блока, а не на карточку товара."""
    if status == 403:
        return True
    title_lower = (title or "").lower()
    if any(marker in title_lower for marker in TITLE_BLOCK_MARKERS):
        return True
    body_head = html[:20_000].lower()
    return any(marker in body_head for marker in BODY_BLOCK_MARKERS)


# ---------------------------------------------------------------------------
# Браузерная обвязка
# ---------------------------------------------------------------------------

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en'] });
"""


@dataclass
class FetchResult:
    url: str
    price: int | None = None
    card_price: int | None = None
    title: str | None = None
    blocked: bool = False          # антибот не пустил
    error: str | None = None       # прочая ошибка (таймаут и т.п.)

    @property
    def ok(self) -> bool:
        return not self.blocked and not self.error and (self.price is not None or self.card_price is not None)


class OzonParser:
    """Общий браузерный контекст на все прогоны; страницы открываются на каждый товар."""

    def __init__(self, headless: bool = config.DEFAULT_HEADLESS) -> None:
        self._headless = headless
        self._playwright = None
        self._context = None
        self._lock = asyncio.Lock()  # один товар в один момент времени

    async def start(self) -> None:
        if self._context is not None:
            return
        from playwright.async_api import async_playwright

        config.BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(config.BROWSER_PROFILE_DIR),
            headless=self._headless,
            viewport={"width": 1440, "height": 900},
            user_agent=config.USER_AGENT,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-infobars",
            ],
        )
        await self._context.add_init_script(_STEALTH_JS)
        log.info("Браузер запущен (headless=%s, profile=%s)", self._headless, config.BROWSER_PROFILE_DIR)

    async def close(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:  # noqa: BLE001 — закрытие не должно падать
                pass
            self._context = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None

    async def _restart(self) -> None:
        log.warning("Перезапуск браузерного контекста")
        await self.close()
        await self.start()

    async def fetch_prices(self, url: str) -> FetchResult:
        """Открыть карточку и снять цены. До MAX_RETRIES попыток при антибот-блоке."""
        async with self._lock:
            last: FetchResult | None = None
            for attempt in range(1, config.MAX_RETRIES + 1):
                try:
                    last = await self._fetch_once(url)
                except Exception as exc:  # браузер умер / таймаут навигации
                    log.warning("Попытка %d: ошибка %s: %r", attempt, url, exc)
                    last = FetchResult(url=url, error=f"{type(exc).__name__}: {exc}")
                    try:
                        await self._restart()
                    except Exception as restart_exc:  # браузер вообще не поднимается
                        log.error("Браузер не перезапускается: %r", restart_exc)
                        return FetchResult(url=url, error=f"browser not starting: {restart_exc}")
                if last is not None and not (last.blocked or last.error):
                    return last
                if attempt < config.MAX_RETRIES:
                    await asyncio.sleep(random.uniform(*config.RETRY_DELAY))
            return last or FetchResult(url=url, error="no attempts")

    async def _fetch_once(self, url: str) -> FetchResult:
        await self.start()
        assert self._context is not None
        page = await self._context.new_page()
        page.set_default_timeout(config.PRICE_TIMEOUT_MS)
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
            status = response.status if response else None
            title_tag = await page.title()

            html = ""
            try:
                html = await page.content()
            except Exception:  # noqa: BLE001 — контент может не дочитаться
                pass

            if looks_like_block(status, title_tag, html):
                log.warning("Антибот-блок (status=%s, title=%r): %s", status, title_tag, url)
                return FetchResult(url=url, blocked=True)

            # основной путь: DOM-виджет цены
            price_text: str | None = None
            for selector in PRICE_SELECTORS:
                try:
                    loc = page.locator(selector).first
                    price_text = await loc.text_content()
                    if price_text and "₽" in price_text:
                        break
                    price_text = None
                except Exception:  # noqa: BLE001 — селектор не нашёлся
                    continue

            plain = card = None
            if price_text:
                plain, card = parse_price_block(price_text)

            if plain is None and card is None:
                await asyncio.sleep(random.uniform(1.5, 3.0))
                html = await page.content()
                plain, card = extract_prices_from_html(html)

            h1 = await page.query_selector("h1")
            title = (await h1.text_content()).strip() if h1 else title_tag

            return FetchResult(url=url, price=plain, card_price=card, title=title or None)
        finally:
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass
