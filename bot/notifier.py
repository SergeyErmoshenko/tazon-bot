"""Детект снижения цены и тексты уведомлений.

По требованию владельца отслеживается ОДНА цена — минимальная («с Ozon
Картой» / «С банками»). Уведомляем только о её снижении; рост и «без
изменений» просто пишутся в историю.
"""
from __future__ import annotations

from dataclasses import dataclass

from .db import PricePoint, Product
from .formatting import fmt_rub


@dataclass(frozen=True)
class Drop:
    label: str         # «Цена с Ozon Картой» | «Цена»
    old: int
    new: int

    @property
    def diff(self) -> int:
        return self.old - self.new

    @property
    def percent(self) -> float:
        return round((self.old - self.new) / self.old * 100, 1) if self.old else 0.0


def effective_price(price: int | None, card_price: int | None) -> int | None:
    """Минимальная цена: карточная, а если её нет — обычная."""
    return card_price if card_price is not None else price


def detect_drops(old: PricePoint | None, new_price: int | None, new_card: int | None) -> list[Drop]:
    """Сравнить минимальную цену с последней записанной точкой.

    Первая точка (old=None) снижением не считается; None означает
    «не нашли/не отображается» — сравнивать нечего.
    """
    if old is None:
        return []
    old_eff = effective_price(old.price, old.card_price)
    new_eff = effective_price(new_price, new_card)
    if old_eff is None or new_eff is None or new_eff >= old_eff:
        return []
    label = "Цена с Ozon Картой" if new_card is not None else "Цена"
    return [Drop(label, old_eff, new_eff)]


def build_drop_message(product: Product, drops: list[Drop]) -> str | None:
    """HTML-сообщение о снижении или None, если снижений нет."""
    if not drops:
        return None
    title = (product.title or f"Товар #{product.id}").strip()
    lines = [f"📉 <b>{_escape(title)}</b>", ""]
    for d in drops:
        lines.append(f"{d.label}: {fmt_rub(d.old)} ₽ → <b>{fmt_rub(d.new)} ₽</b> (−{fmt_rub(d.diff)} ₽, −{d.percent}%)")
    lines += ["", product.display_url]
    return "\n".join(lines)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
