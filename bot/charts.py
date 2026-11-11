"""График истории цены товара (matplotlib, PNG для Telegram)."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # без дисплея

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from .db import PricePoint, Product  # noqa: E402


def make_chart(product: Product, points: list[PricePoint]) -> bytes:
    """PNG с двумя линиями: обычная цена и цена по Ozon Карте."""
    times = [p.checked_at for p in points]
    prices = [p.price for p in points]
    cards = [p.card_price for p in points]

    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=150)

    plain_times = [t for t, v in zip(times, prices) if v is not None]
    plain_values = [v for v in prices if v is not None]
    card_times = [t for t, v in zip(times, cards) if v is not None]
    card_values = [v for v in cards if v is not None]

    if plain_values:
        ax.plot(plain_times, plain_values, color="#8a8f98", linewidth=1.8, marker="o", markersize=3, label="Обычная цена")
        ax.annotate(f"{plain_values[-1]:,} ₽".replace(",", " "),
                    xy=(plain_times[-1], plain_values[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=9, color="#8a8f98")
    if card_values:
        ax.plot(card_times, card_values, color="#005bff", linewidth=2.2, marker="o", markersize=3.5, label="С Ozon Картой")
        ax.annotate(f"{card_values[-1]:,} ₽".replace(",", " "),
                    xy=(card_times[-1], card_values[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=9, color="#005bff", fontweight="bold")

    title = (product.title or f"Товар #{product.id}").strip()
    if len(title) > 70:
        title = title[:70] + "…"
    ax.set_title(title, fontsize=11, loc="left")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m %H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
    ax.set_ylabel("₽")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.legend(loc="best", fontsize=9, frameon=False)
    fig.autofmt_xdate(rotation=30)
    all_vals = [v for v in plain_values + card_values if v]
    if all_vals:
        ax.set_ylim(min(all_vals) * 0.97, max(all_vals) * 1.03)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
