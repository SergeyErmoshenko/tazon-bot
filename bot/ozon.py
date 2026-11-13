"""Получение цен с карточки товара Ozon.

Схема, которая проходит антибот Ozon (fab_chlg): Chrome запускается как
ОБЫЧНЫЙ процесс (минимум флагов — только порт отладки и профиль), а Playwright
подключается к нему по CDP (connect_over_cdp). Chrome, запущенный самим
Playwright'ом, несёт ~20 служебных флагов и детектится антиботом.

Ответ 403 с title «Antibot Challenge Page» при этом НЕ означает блок:
челлендж проходится молча и страница рендерит цены. Блок констатируем
только если цены нет после ожидания.

Все знания о вёрстке Ozon — в PRICE_SELECTORS, *_LABEL и parse_price_block.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass

from . import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Чистые функции парсинга (без Playwright)
# ---------------------------------------------------------------------------

_PRODUCT_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:ozon|ozone)\.ru/product/([^/?#]+)/?", re.IGNORECASE
)
_SKU_RE = re.compile(r"(\d{5,})\s*/?\s*$")
# старый формат карточек: ozon.ru/context/detail/id/123456789
_OLD_STYLE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:ozon|ozone)\.ru/context/detail/id/(\d{5,})", re.IGNORECASE
)

# Число с разделителями разрядов (пробел, узкий пробел, nbsp) и знаком рубля
_PRICE_IN_TEXT_RE = re.compile(r"(\d[\d   \s]{0,15})\s*₽")

# Блоки DOM, где живёт цена (в порядке приоритета)
PRICE_SELECTORS = [
    "[data-widget='webPrice']",
    "[data-widget='webSalePrice']",
    "[data-widget='price']",
]

# Fallback: JSON, вшитый в страницу
PRICE_JSON_PATTERNS = [
    (re.compile(r'"cardPrice"\s*:\s*"?(\d{3,})'), "card"),
    (re.compile(r'"price"\s*:\s*\{[^{}]*?"price"\s*:\s*"?(\d{3,})'), "price"),
    (re.compile(r'"currentPrice"\s*:\s*"?(\d{3,})'), "price"),
    (re.compile(r'"price"\s*:\s*"?(\d{3,})'), "price"),
]

# Признаки страницы-блока (антибот / ограничение доступа)
TITLE_BLOCK_MARKERS = ("antibot", "доступ ограничен", "доступ заблокирован", "just a moment")
BODY_BLOCK_MARKERS = ("antibot challenge", "доступ ограничен", "доступ заблокирован", "just a moment")


def normalize_url(raw: str) -> tuple[str, int] | None:
    """Из любой ссылки/текста с карточкой Ozon -> (канонический url, sku).

    Понимает /product/<slug>-<sku>/, /product/<sku> и старый
    /context/detail/id/<sku> на доменах ozon.ru и ozone.ru. Короткие
    редиректы (ozon.ru/t/<hash>) через регэксп не решаются — их
    разворачивает OzonParser.resolve.
    """
    m = _OLD_STYLE_RE.search(raw)
    if m:
        sku = int(m.group(1))
        return f"https://www.ozon.ru/product/{sku}/", sku
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
    return int(re.sub(r"[   \s]", "", number))


def parse_price_block(text: str) -> tuple[int | None, int | None]:
    """Фолбэк-разбор текста блока цены, когда DOM-анализ недоступен.

    Цены «за 1 шт / за 1 уп / за 100 г…» (цена единицы, не товара) skip'аются.
    Дальше — по порядку (порядок в блоке стабилен: карточная, обычная, старая):
    две цены и вторая больше -> (обычная, карточная); иначе первая -> обычная.

    Возвращает (обычная цена, скидочная/карточная).
    """
    prices = []
    for m in _PRICE_IN_TEXT_RE.finditer(text):
        tail = text[m.end():]
        if re.match(r"\s*за\s", tail):
            continue  # «638 ₽ за 1 шт» — цена за единицу, не цена товара
        prices.append(_to_int(m.group(1)))
    prices = [p for p in prices if p >= 10]
    if not prices:
        return None, None
    if len(prices) == 1:
        return prices[0], None
    if prices[1] > prices[0]:
        return prices[1], prices[0]
    return prices[0], None


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


def looks_like_block(title: str, html: str) -> bool:
    """Похоже ли на страницу-блок (вызывается уже ПОСЛЕ того, как цены нет)."""
    title_lower = (title or "").lower()
    if any(marker in title_lower for marker in TITLE_BLOCK_MARKERS):
        return True
    body_head = html[:20_000].lower()
    return any(marker in body_head for marker in BODY_BLOCK_MARKERS)


# JS в контексте страницы: все цены блока с признаками «зачёркнута» и
# «цена за единицу» (за 1 шт / за 1 уп / за 100 г …). Зачёркнутая — старая
# цена, за единицу — не цена товара; обе игнорируем. Из живых: min = карточная,
# max = обычная.
_PRICE_DOM_JS = """
(sel) => {
  const root = document.querySelector(sel);
  if (!root) return null;
  const out = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const t = node.textContent || '';
    const m = t.match(/(\\d[\\d\\u00a0\\u202f\\u2009\\s]{0,15})\\s*₽/);
    if (!m) continue;
    const parentText = (node.parentElement && node.parentElement.textContent) || '';
    const isUnit = /₽\\s*за\\s|за\\s+\\d+[\\s.,]*\\d*\\s*(шт|упак|уп|кг|г|гр|мл|л|м|см|пар)/i.test(parentText);
    let el = node.parentElement;
    let struck = false;
    while (el && el !== root.parentElement) {
      const cs = getComputedStyle(el);
      const td = cs.textDecorationLine || cs.textDecoration || '';
      if (String(td).includes('line-through')) { struck = true; break; }
      el = el.parentElement;
    }
    const value = parseInt(m[1].replace(/\\D/g, ''), 10);
    if (value >= 10 && !isUnit) out.push({ value: value, struck: struck });
  }
  return out.length ? out : null;
}
"""


# ---------------------------------------------------------------------------
# Браузер: обычный Chrome + Playwright over CDP
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    url: str
    price: int | None = None
    card_price: int | None = None
    title: str | None = None
    blocked: bool = False          # антибот не пустил (цен нет)
    error: str | None = None       # прочая ошибка (таймаут и т.п.)

    @property
    def ok(self) -> bool:
        return not self.blocked and not self.error and (self.price is not None or self.card_price is not None)


def _cdp_alive(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False


class OzonParser:
    """Chrome запускается субпроцессом и живёт между прогонами; Playwright — сбоку."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._proc: subprocess.Popen | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._context is not None:
            return
        from playwright.async_api import async_playwright

        config.BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        port = config.CDP_PORT

        if not _cdp_alive(port):
            log.info("Запускаю Chrome: %s (profile=%s)", config.CHROME_PATH, config.BROWSER_PROFILE_DIR)
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._proc = subprocess.Popen(
                [
                    config.CHROME_PATH,
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={config.BROWSER_PROFILE_DIR}",
                    "--start-minimized",
                    # фоновый жор режем: без фоновой сети/синхронизации/обновлений
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--mute-audio",
                    "--no-first-run",
                    "about:blank",
                ],
                creationflags=creationflags,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if _cdp_alive(port):
                    break
                if self._proc.poll() is not None:
                    raise RuntimeError(f"Chrome умер при старте, код {self._proc.returncode}")
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError("CDP-порт Chrome не поднялся за 30 с")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        # картинки и видео в ценах не участвуют, а весят дорого (CPU на рендер
        # и трафик через VPN) — глушим ещё на уровне сети
        await self._context.route(
            "**/*", self._block_heavy_resources,
        )
        log.info("Подключён к Chrome по CDP (порт %d)", port)

    @staticmethod
    async def _block_heavy_resources(route) -> None:
        if route.request.resource_type in ("image", "media"):
            try:
                await route.abort()
            except Exception:  # noqa: BLE001 — страница могла уже закрыться
                return
        else:
            try:
                await route.continue_()
            except Exception:  # noqa: BLE001
                return

    async def close(self) -> None:
        for obj, name in ((self._browser, "browser"), (self._playwright, "playwright")):
            if obj is not None:
                try:
                    await obj.close()
                except Exception:  # noqa: BLE001
                    pass
        self._browser = None
        self._context = None
        self._playwright = None
        if self._proc is not None:
            try:
                if sys.platform == "win32":
                    # terminate() убивает только главный процесс; Chrome-дети
                    # (renderer/GPU) могут осиротеть — глушим всё дерево
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self._proc.pid)],
                        capture_output=True, check=False,
                    )
                else:
                    self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._proc = None

    async def _restart(self) -> None:
        log.warning("Перезапуск Chrome/CDP")
        await self.close()
        await self.start()

    async def fetch_prices(self, url: str) -> FetchResult:
        """Открыть карточку и снять цены. До MAX_RETRIES попыток."""
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
                        log.error("Chrome не перезапускается: %r", restart_exc)
                        return FetchResult(url=url, error=f"chrome not starting: {restart_exc}")
                if last is not None and last.ok:
                    return last
                if attempt < config.MAX_RETRIES:
                    await asyncio.sleep(random.uniform(*config.RETRY_DELAY))
            return last or FetchResult(url=url, error="no attempts")

    async def _new_page(self):
        await self.start()
        assert self._context is not None
        page = await self._context.new_page()
        page.set_default_timeout(config.PRICE_TIMEOUT_MS)
        return page

    async def _fetch_once(self, url: str) -> FetchResult:
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)

            # Статус/титул могут быть от челленджа, но страница рендерится:
            # сначала ждём ЦЕНУ, и только её отсутствие считаем блоком.
            plain = card = None
            deadline = time.monotonic() + config.CHALLENGE_WAIT_S
            while time.monotonic() < deadline and plain is None and card is None:
                plain, card = await self._extract_dom_prices(page)
                if plain is None and card is None:
                    await asyncio.sleep(1.0)

            if plain is None and card is None:
                # запасной путь: цены из JSON, вшитого в страницу
                try:
                    html = await page.content()
                    plain, card = extract_prices_from_html(html)
                except Exception:  # noqa: BLE001
                    pass

            if plain is not None or card is not None:
                return FetchResult(url=url, price=plain, card_price=card, title=await self._product_title(page))

            title = await page.title()
            html = ""
            try:
                html = await page.content()
            except Exception:  # noqa: BLE001
                pass
            if looks_like_block(title, html):
                log.warning("Антибот-блок (title=%r): %s", title, url)
                return FetchResult(url=url, blocked=True)
            return FetchResult(url=url, error="цена не найдена на странице")
        finally:
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass

    async def _extract_dom_prices(self, page) -> tuple[int | None, int | None]:
        """Цены из DOM: (обычная, карточная).

        Порядок цен в виджете стабилен: [карточная «С банками», обычная,
        старая зачёркнутая, «за 1 шт»…]. Детект зачёркивания у Ozon ненадёжен
        (линия рисуется не text-decoration), поэтому доверяем ПОРЯДКУ:
        две цены и вторая больше -> (обычная, карточная); остальное игнорируем.

        Возвращает (None, None), если виджет ещё не отрендерился — вызывающий
        код будет поллить.
        """
        for selector in PRICE_SELECTORS:
            try:
                data = await page.evaluate(_PRICE_DOM_JS, selector)
            except Exception:  # noqa: BLE001 — селектор/страница не готовы
                continue
            if not data:
                continue
            live = [d["value"] for d in data if not d["struck"]]
            if not live:
                continue
            if len(live) == 1:
                return live[0], None
            if live[1] > live[0]:
                return live[1], live[0]
            return live[0], None
        return None, None

    async def resolve(self, raw_url: str) -> tuple[str, int] | None:
        """Развернуть короткую/редиректную ссылку (ozon.ru/t/<hash> и т.п.):

        открываем её в Chrome, ждём, пока URL станет карточкой товара,
        и нормализуем финальный адрес. None — не дождались.
        """
        async with self._lock:
            try:
                await self.start()
                page = await self._new_page()
                try:
                    await page.goto(raw_url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
                    deadline = time.monotonic() + config.CHALLENGE_WAIT_S
                    while time.monotonic() < deadline:
                        m = normalize_url(page.url)
                        if m:
                            return m
                        await asyncio.sleep(1.0)
                    return normalize_url(page.url)
                finally:
                    try:
                        await page.close()
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as exc:  # noqa: BLE001
                log.warning("resolve(%s): %r", raw_url, exc)
                return None

    async def fetch_title(self, url: str) -> str | None:
        """Отдельная попытка достать только название.

        Вызывается при добавлении товара, если основной прогон не дождался
        заголовка: свежая навигация по карточке почти всегда его отдаёт.
        """
        async with self._lock:
            try:
                page = await self._new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
                    return await self._product_title(page)
                finally:
                    try:
                        await page.close()
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as exc:  # noqa: BLE001
                log.warning("fetch_title(%s): %r", url, exc)
                return None

    async def _product_title(self, page) -> str | None:
        # заголовок может отрисоваться позже цен (ленивая загрузка) — ждём до 12 с
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                h1 = await page.query_selector("h1")
                if h1:
                    text = (await h1.text_content() or "").strip()
                    if text:
                        return text
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(1.0)
        try:
            title = (await page.title() or "").strip()
            if title and not any(m in title.lower() for m in TITLE_BLOCK_MARKERS):
                return title
        except Exception:  # noqa: BLE001
            pass
        return None
