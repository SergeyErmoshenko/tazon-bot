"""График истории цены товара (matplotlib, PNG для Telegram).

Одна линия — минимальная цена («с Ozon Картой» / «С банками»).
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # без дисплея

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from .db import PricePoint, Product  # noqa: E402
from .notifier import effective_price  # noqa: E402


def make_chart(product: Product, points: list[PricePoint]) -> bytes:
    """PNG с линией минимальной цены."""
    series = [(p.checked_at, effective_price(p.price, p.card_price)) for p in points]
    times = [t for t, v in series if v is not None]
    values = [v for _, v in series if v is not None]

    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=150)
    if values:
        ax.plot(times, values, color="#005bff", linewidth=2.2, marker="o", markersize=3.5)
        ax.annotate(f"{values[-1]:,} ₽".replace(",", " "),
                    xy=(times[-1], values[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center",
                    fontsize=10, color="#005bff", fontweight="bold")
        ax.axhline(min(values), color="#8a8f98", linewidth=1, linestyle="--", alpha=0.7)
        ax.annotate(f"мин. {min(values):,} ₽".replace(",", " "),
                    xy=(times[0], min(values)),
                    xytext=(0, 8), textcoords="offset points", fontsize=8.5, color="#8a8f98")

    has_card = any(p.card_price is not None for p in points)
    title = (product.title or f"Товар #{product.id}").strip()
    if len(title) > 70:
        title = title[:70] + "…"
    ax.set_title(title, fontsize=11, loc="left")

    # формат оси времени — по разбросу данных: часы держим как можно дольше,
    # дни без часов — только когда истории больше недели
    if times:
        span_days = (times[-1] - times[0]).total_seconds() / 86400
        if span_days >= 7:
            date_fmt = "%d.%m"
        elif span_days < 1:
            date_fmt = "%H:%M"
        else:
            date_fmt = "%d.%m %H:%M"
    else:
        date_fmt = "%d.%m"
    ax.xaxis.set_major_formatter(mdates.DateFormatter(date_fmt))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
    ax.set_ylabel("₽" + ("  (с Ozon Картой)" if has_card else ""))
    ax.grid(True, alpha=0.25, linewidth=0.6)
    fig.autofmt_xdate(rotation=30)
    if values:
        ax.set_ylim(min(values) * 0.97, max(values) * 1.03)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
