"""Детект снижения цены и тексты уведомлений.

Чистые функции без Telegram — легко тестировать. Уведомляем только о снижении;
рост и «без изменений» просто пишутся в историю.
"""
from __future__ import annotations

from dataclasses import dataclass

from .db import PricePoint, Product
from .formatting import fmt_rub


@dataclass(frozen=True)
class Drop:
    kind: str          # "price" | "card"
    label: str         # "Цена" | "Цена по Ozon Карте"
    old: int
    new: int

    @property
    def diff(self) -> int:
        return self.old - self.new

    @property
    def percent(self) -> float:
        return round((self.old - self.new) / self.old * 100, 1) if self.old else 0.0


def detect_drops(old: PricePoint | None, new_price: int | None, new_card: int | None) -> list[Drop]:
    """Сравнить новую пару цен с последней записанной точкой.

    Первая точка (old=None) снижением не считается.
    None в цене означает «не нашли/не отображается» — сравнивать нечего.
    """
    if old is None:
        return []
    drops: list[Drop] = []

    if old.price is not None and new_price is not None and new_price < old.price:
        drops.append(Drop("price", "Цена", old.price, new_price))
    if old.card_price is not None and new_card is not None and new_card < old.card_price:
        drops.append(Drop("card", "Цена по Ozon Карте", old.card_price, new_card))
    return drops


def _fmt(n: int) -> str:
    return fmt_rub(n)


def build_drop_message(product: Product, drops: list[Drop]) -> str | None:
    """HTML-сообщение о снижении или None, если снижений нет."""
    if not drops:
        return None
    title = (product.title or f"Товар #{product.id}").strip()
    lines = [f"📉 <b>{_escape(title)}</b>", ""]
    for d in drops:
        lines.append(f"{d.label}: {_fmt(d.old)} ₽ → <b>{_fmt(d.new)} ₽</b> (−{_fmt(d.diff)} ₽, −{d.percent}%)")
    lines += ["", f"{product.url}"]
    return "\n".join(lines)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
