"""Тесты SQLite-слоя (временная БД): товары глобальные, подписки персональные."""
from __future__ import annotations

import pytest

from bot import db as db_module


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Изолированная БД на каждый тест (_connect читает config.DB_PATH динамически)."""
    monkeypatch.setattr(db_module.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db_module.config, "DB_PATH", tmp_path / "test.db")
    db_module.init_db()
    return db_module


def test_add_product_is_global(db):
    p = db.add_product("https://www.ozon.ru/product/111/", 111, "Товар 1",
                       orig_url="https://www.ozon.ru/product/111/?at=ref&sh=xyz")
    assert p.id is not None and p.title == "Товар 1"
    assert p.display_url.endswith("?at=ref&sh=xyz")  # оригинальная ссылка сохранена
    same = db.add_product("https://www.ozon.ru/product/111/", 111, "Дубль",
                          orig_url="https://www.ozon.ru/product/111/?at=other")
    assert same.id == p.id  # один URL = одна строка независимо от того, кто добавляет
    assert same.display_url.endswith("sh=xyz")  # первый оригинал не перезаписывается


def test_add_product_without_orig_falls_back(db):
    p = db.add_product("https://www.ozon.ru/product/222/", 222, None)
    assert p.display_url == p.url


def test_subscribe_unsubscribe(db):
    p = db.add_product("u", 1, None)
    assert db.subscribe(100, p.id) is True
    assert db.subscribe(100, p.id) is False       # повторная подписка — no-op
    assert db.subscribers(p.id) == [100]
    assert db.is_subscribed(100, p.id) is True
    assert db.is_subscribed(200, p.id) is False

    assert db.subscribe(200, p.id) is True
    assert db.unsubscribe(100, p.id) is True
    assert db.unsubscribe(100, p.id) is False     # уже не подписан
    assert db.subscribers(p.id) == [200]
    assert db.get_product(p.id) is not None       # есть подписчик — товар жив

    assert db.unsubscribe(200, p.id) is True
    assert db.get_product(p.id) is None           # последний ушёл — товар удалён


def test_user_product_lists(db):
    p1 = db.add_product("u1", 1, None)
    p2 = db.add_product("u2", 2, None)
    db.subscribe(100, p1.id)
    db.subscribe(100, p2.id)
    db.subscribe(200, p2.id)
    assert {x.sku for x in db.list_user_products(100)} == {1, 2}
    assert {x.sku for x in db.list_user_products(200)} == {2}
    assert {x.sku for x in db.list_all_products()} == {1, 2}


def test_points_history_and_last(db):
    p = db.add_product("u", 1, None)
    assert db.get_last_point(p.id) is None
    db.insert_point(p.id, 500, 450)
    db.insert_point(p.id, 500, 450)
    db.insert_point(p.id, 480, None)
    history = db.get_history(p.id)
    assert len(history) == 3
    last = db.get_last_point(p.id)
    assert last.price == 480 and last.card_price is None
    first = db.get_first_point(p.id)
    assert first.price == 500


def test_fail_counter(db):
    p = db.add_product("u", 3, None)
    assert db.increment_fail(p.id) == 1
    assert db.increment_fail(p.id) == 2
    db.reset_fail(p.id)
    assert db.increment_fail(p.id) == 1


def test_delete_cascades_points(db):
    p = db.add_product("u", 4, None)
    db.insert_point(p.id, 100, 90)
    with db_module._connect() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM products WHERE id = ?", (p.id,))
    assert db.get_by_sku(4) is None
    assert db.get_history(p.id) == []


def test_backfill_subscriptions(db):
    p = db.add_product("legacy", 5, None)   # товар без подписчиков (старая схема)
    added = db.backfill_subscriptions(999)
    assert added == 1
    assert db.subscribers(p.id) == [999]
    assert db.backfill_subscriptions(999) == 0  # повторный вызов — no-op
