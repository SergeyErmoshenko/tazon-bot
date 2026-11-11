"""Настройки бота: читаются из .env, с дефолтами.

Модуль безопасен для импорта без .env — ошибки валидации только в load_settings().
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
DB_PATH = DATA_DIR / "monitor.db"
BROWSER_PROFILE_DIR = DATA_DIR / "browser-profile"

DEFAULT_CHECK_TIMES = "08:00,14:00,20:00,02:00"
DEFAULT_JITTER_MINUTES = 15
DEFAULT_HEADLESS = True

# --- Парсер: задержки и ретраи ---
PAGE_TIMEOUT_MS = 30_000          # навигация по карточке
PRICE_TIMEOUT_MS = 15_000         # ожидание виджета цены на загруженной странице
MAX_RETRIES = 3                   # попыток на товар за прогон
DELAY_BETWEEN_PRODUCTS = (2.0, 5.0)  # пауза между товарами, сек (random)
RETRY_DELAY = (5.0, 10.0)         # пауза перед повтором при антиботе, сек
FAIL_ALERT_THRESHOLD = 5          # подряд нечитаемых прогонов -> алерт админу

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class Settings:
    bot_token: str
    admin_chat_id: int
    check_times: list[tuple[int, int]] = field(default_factory=list)
    jitter_minutes: int = DEFAULT_JITTER_MINUTES
    headless: bool = DEFAULT_HEADLESS


# Устанавливается один раз в main.py при старте; остальной код берёт отсюда.
settings: Settings | None = None


def require_settings() -> Settings:
    if settings is None:
        raise RuntimeError("Settings не загружены: вызови load_settings() в точке входа")
    return settings


def _parse_check_times(raw: str) -> list[tuple[int, int]]:
    times: list[tuple[int, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        hh, _, mm = part.partition(":")
        hour, minute = int(hh), int(mm or 0)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Некорректное время проверки: {part!r}")
        times.append((hour, minute))
    if not times:
        raise ValueError("CHECK_TIMES пуст — укажи хотя бы одно время HH:MM")
    return times


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_raw = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN не задан: скопируй .env.example в .env и вставь токен от @BotFather")
    if not admin_raw or not admin_raw.lstrip("-").isdigit():
        raise ValueError("ADMIN_CHAT_ID не задан или не число: узнай свой id у @userinfobot")

    return Settings(
        bot_token=bot_token,
        admin_chat_id=int(admin_raw),
        check_times=_parse_check_times(os.getenv("CHECK_TIMES", DEFAULT_CHECK_TIMES)),
        jitter_minutes=int(os.getenv("JITTER_MINUTES", str(DEFAULT_JITTER_MINUTES))),
        headless=os.getenv("HEADLESS", str(DEFAULT_HEADLESS)).strip().lower() not in ("0", "false", "no"),
    )
