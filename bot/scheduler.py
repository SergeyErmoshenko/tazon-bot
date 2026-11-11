"""Расписание проверок: cron-триггеры из config.CHECK_TIMES + jitter."""
from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config, runner

log = logging.getLogger(__name__)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    settings = config.require_settings()
    # без явного timezone APScheduler использует локальную зону ноутбука — то, что нужно
    scheduler = AsyncIOScheduler()
    for hour, minute in settings.check_times:
        scheduler.add_job(
            runner.run_check_all,
            trigger=CronTrigger(hour=hour, minute=minute, jitter=settings.jitter_minutes * 60),
            args=[bot],
            id=f"check_{hour:02d}{minute:02d}",
            max_instances=1,
            coalesce=True,
        )
        log.info("Проверка запланирована на %02d:%02d (+/−%d мин)", hour, minute, settings.jitter_minutes)
    return scheduler
