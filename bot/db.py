"""SQLite-хранилище: товары и история цен.

Соединение открывается на операцию — для одного процесса с парой запросов в минуту
это дешевле, чем держать коннект и следить за потоками.
Время пишем локальное (datetime.now(), без tz) — оно же идёт на графики.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL,
    sku        INTEGER NOT NULL UNIQUE,
    title      TEXT,
    is_active  INTEGER NOT NULL DEFAULT 1,
    fail_count INTEGER NOT NULL DEFAULT 0,
    added_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_points (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price      INTEGER,
    card_price INTEGER,
    checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_points_product
    ON price_points(product_id, checked_at);
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


def _row_to_product(row: sqlite3.Row) -> Product:
    return Product(
        id=row["id"],
        url=row["url"],
        sku=row["sku"],
        title=row["title"],
        is_active=bool(row["is_active"]),
        fail_count=row["fail_count"],
        added_at=row["added_at"],
    )


def _row_to_point(row: sqlite3.Row) -> PricePoint:
    return PricePoint(
        id=row["id"],
        product_id=row["product_id"],
        price=row["price"],
        card_price=row["card_price"],
        checked_at=datetime.fromisoformat(row["checked_at"]),
    )


def add_product(url: str, sku: int, title: str | None) -> Product:
    """Добавить товар. Если sku уже есть — вернуть существующего (без изменений)."""
    with _connect() as conn:
        existing = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        if existing:
            return _row_to_product(existing)
        cur = conn.execute(
            "INSERT INTO products (url, sku, title, added_at) VALUES (?, ?, ?, ?)",
            (url, sku, title, datetime.now().isoformat(timespec="seconds")),
        )
        row = conn.execute("SELECT * FROM products WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_product(row)


def get_by_sku(sku: int) -> Product | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        return _row_to_product(row) if row else None


def get_product(product_id: int) -> Product | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _row_to_product(row) if row else None


def list_products(active_only: bool = True) -> list[Product]:
    query = "SELECT * FROM products"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY id"
    with _connect() as conn:
        return [_row_to_product(r) for r in conn.execute(query).fetchall()]


def delete_product(product_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        return cur.rowcount > 0


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
