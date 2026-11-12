"""SQLite-хранилище: товары, подписки и история цен.

Модель многопользовательская: товары глобальные (один URL = одна строка и одна
история — дублировать обход для разных людей незачем), а пользователи подписаны
на товары через таблицу subscriptions. Уведомления уходят всем подписчикам;
товар с нулём подписчиков удаляется вместе с историей.

Соединение открывается на операцию — для одного процесса с парой запросов в
минуту это дешевле, чем держать коннект. Время пишем локальное (datetime.now(),
без tz) — оно же идёт на графики.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL,
    sku        INTEGER NOT NULL UNIQUE,
    title      TEXT,
    is_active  INTEGER NOT NULL DEFAULT 1,
    fail_count INTEGER NOT NULL DEFAULT 0,
    added_at   TEXT NOT NULL,
    orig_url   TEXT
);
CREATE TABLE IF NOT EXISTS price_points (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price      INTEGER,
    card_price INTEGER,
    checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id    INTEGER NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    added_at   TEXT NOT NULL,
    PRIMARY KEY (chat_id, product_id)
);
CREATE INDEX IF NOT EXISTS idx_points_product
    ON price_points(product_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_subs_chat
    ON subscriptions(chat_id);
"""


@dataclass
class Product:
    id: int
    url: str
    sku: int
    title: str | None
    is_active: bool
    fail_count: int
    added_at: str
    orig_url: str | None = None  # ссылка, которой товар добавили (с реферальными хвостами)

    @property
    def display_url(self) -> str:
        """Ссылка для показа пользователю: оригинальная, если сохранилась."""
        return self.orig_url or self.url


@dataclass
class PricePoint:
    id: int
    product_id: int
    price: int | None
    card_price: int | None
    checked_at: datetime


def _connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # миграция для БД, созданных до появления orig_url
        try:
            conn.execute("ALTER TABLE products ADD COLUMN orig_url TEXT")
        except sqlite3.OperationalError:
            pass  # колонка уже есть
        conn.execute("UPDATE products SET orig_url = url WHERE orig_url IS NULL")


def _row_to_product(row: sqlite3.Row) -> Product:
    return Product(
        id=row["id"],
        url=row["url"],
        sku=row["sku"],
        title=row["title"],
        is_active=bool(row["is_active"]),
        fail_count=row["fail_count"],
        added_at=row["added_at"],
        orig_url=row["orig_url"],
    )


def _row_to_point(row: sqlite3.Row) -> PricePoint:
    return PricePoint(
        id=row["id"],
        product_id=row["product_id"],
        price=row["price"],
        card_price=row["card_price"],
        checked_at=datetime.fromisoformat(row["checked_at"]),
    )


def add_product(url: str, sku: int, title: str | None, orig_url: str | None = None) -> Product:
    """Получить глобальный товар по sku (создать, если первый раз).

    orig_url — ссылка, которой товар добавили (с реферальными хвостами):
    запоминаем при первом добавлении, у существующего товара не перезаписываем.
    """
    with _connect() as conn:
        existing = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        if existing:
            if orig_url and not existing["orig_url"]:
                conn.execute("UPDATE products SET orig_url = ? WHERE id = ?", (orig_url, existing["id"]))
                existing = conn.execute("SELECT * FROM products WHERE id = ?", (existing["id"],)).fetchone()
            return _row_to_product(existing)
        cur = conn.execute(
            "INSERT INTO products (url, sku, title, added_at, orig_url) VALUES (?, ?, ?, ?, ?)",
            (url, sku, title, datetime.now().isoformat(timespec="seconds"), orig_url or url),
        )
        row = conn.execute("SELECT * FROM products WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_product(row)


def update_orig_url(product_id: int, orig_url: str) -> None:
    """Перезаписать оригинальную ссылку (пользователь прислал товар повторно)."""
    with _connect() as conn:
        conn.execute("UPDATE products SET orig_url = ? WHERE id = ?", (orig_url, product_id))


def subscribe(chat_id: int, product_id: int) -> bool:
    """Подписать пользователя на товар. False, если уже подписан."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO subscriptions (chat_id, product_id, added_at) VALUES (?, ?, ?)",
            (chat_id, product_id, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.rowcount > 0


def unsubscribe(chat_id: int, product_id: int) -> bool:
    """Отписать пользователя. Если подписчиков не осталось — удалить товар
    вместе с историей. True, если подписка была снята."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND product_id = ?",
            (chat_id, product_id),
        )
        if cur.rowcount == 0:
            return False
        left = conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE product_id = ?", (product_id,)
        ).fetchone()[0]
        if left == 0:
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        return True


def subscribers(product_id: int) -> list[int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT chat_id FROM subscriptions WHERE product_id = ? ORDER BY chat_id",
            (product_id,),
        ).fetchall()
        return [r["chat_id"] for r in rows]


def is_subscribed(chat_id: int, product_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM subscriptions WHERE chat_id = ? AND product_id = ?",
            (chat_id, product_id),
        ).fetchone()
        return row is not None


def get_by_sku(sku: int) -> Product | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        return _row_to_product(row) if row else None


def get_product(product_id: int) -> Product | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _row_to_product(row) if row else None


def list_user_products(chat_id: int) -> list[Product]:
    """Товары, на которые подписан пользователь."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT p.* FROM products p JOIN subscriptions s ON s.product_id = p.id "
            "WHERE s.chat_id = ? ORDER BY p.id",
            (chat_id,),
        ).fetchall()
        return [_row_to_product(r) for r in rows]


def list_all_products() -> list[Product]:
    """Все товары бота (для планового прогона: проверяем каждый URL один раз)."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
        return [_row_to_product(r) for r in rows]


def get_last_point(product_id: int) -> PricePoint | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM price_points WHERE product_id = ? ORDER BY id DESC LIMIT 1",
            (product_id,),
        ).fetchone()
        return _row_to_point(row) if row else None


def get_first_point(product_id: int) -> PricePoint | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM price_points WHERE product_id = ? ORDER BY id ASC LIMIT 1",
            (product_id,),
        ).fetchone()
        return _row_to_point(row) if row else None


def get_history(product_id: int) -> list[PricePoint]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM price_points WHERE product_id = ? ORDER BY id ASC",
            (product_id,),
        ).fetchall()
        return [_row_to_point(r) for r in rows]


def insert_point(product_id: int, price: int | None, card_price: int | None) -> PricePoint:
    """Записать точку истории (цена могла не измениться — всё равно пишем)."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO price_points (product_id, price, card_price, checked_at) VALUES (?, ?, ?, ?)",
            (product_id, price, card_price, datetime.now().isoformat(timespec="seconds")),
        )
        row = conn.execute("SELECT * FROM price_points WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_point(row)


def increment_fail(product_id: int) -> int:
    """+1 к счётчику нечитаемых прогонов, вернуть новое значение."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE products SET fail_count = fail_count + 1 WHERE id = ? RETURNING fail_count",
            (product_id,),
        )
        return cur.fetchone()[0]


def reset_fail(product_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE products SET fail_count = 0 WHERE id = ?", (product_id,))


def update_title(product_id: int, title: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE products SET title = ? WHERE id = ?", (title, product_id))


def backfill_subscriptions(default_chat_id: int) -> int:
    """Гарантировать инвариант «у товара есть подписчик»: товары без
    подписчиков (наследие старой схемы) приписываются default_chat_id.
    Возвращает число приписанных."""
    with _connect() as conn:
        orphans = conn.execute(
            "SELECT p.id FROM products p LEFT JOIN subscriptions s ON s.product_id = p.id "
            "WHERE s.chat_id IS NULL"
        ).fetchall()
        now = datetime.now().isoformat(timespec="seconds")
        for row in orphans:
            conn.execute(
                "INSERT OR IGNORE INTO subscriptions (chat_id, product_id, added_at) VALUES (?, ?, ?)",
                (default_chat_id, row["id"], now),
            )
        return len(orphans)
