"""Тесты SQLite-слоя (временная БД)."""
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


def test_add_and_get(db):
    p = db.add_product("https://www.ozon.ru/product/111/", 111, "Товар 1")
    assert p.id is not None and p.title == "Товар 1"
    same = db.add_product("https://www.ozon.ru/product/111/", 111, "Дубль")
    assert same.id == p.id  # повторное добавление не создаёт дубль
    assert db.get_by_sku(111).title == "Товар 1"


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
    p = db.add_product("u", 2, None)
    assert db.increment_fail(p.id) == 1
    assert db.increment_fail(p.id) == 2
    db.reset_fail(p.id)
    assert db.increment_fail(p.id) == 1


def test_delete_cascades_points(db):
    p = db.add_product("u", 3, None)
    db.insert_point(p.id, 100, 90)
    assert db.delete_product(p.id) is True
    assert db.get_by_sku(3) is None
    assert db.get_history(p.id) == []
    assert db.delete_product(p.id) is False
