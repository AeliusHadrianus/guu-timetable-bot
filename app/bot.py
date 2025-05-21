"""app/bot.py

Main entry‑point for Telegram bot "Расписание ГУУ".
Implements:
  • /start, /help – общие команды
  • /group – выбор учебной группы (inline‑keyboard)
  • /today – расписание на текущий день
  • /week – расписание на учебную неделю
  • Background APScheduler job → fetcher_parser.sync()

Стек:
  Python 3.12  •  aiogram 3.x  •  SQLAlchemy 2.x (async)  •  APScheduler 3.x

Usage::
    BOT_TOKEN=xxxxx DB_URL="sqlite+aiosqlite:///schedule.db" python -m app.bot
"""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import List

from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# local modules
from services.fetcher_parser import sync as fetcher_sync
from db import models  # assumes models package created via Alembic‑ready code‑gen

# ---------------------------------------------------------------------------
# Configuration -------------------------------------------------------------
# ---------------------------------------------------------------------------
BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var not set")

DB_URL: str = os.environ.get("DB_URL", "sqlite+aiosqlite:///schedule.db")


# ---------------------------------------------------------------------------
# Database helpers ----------------------------------------------------------
# ---------------------------------------------------------------------------
engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True, future=True)
SessionMaker = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncSession:  # noqa: D401
    """Async context manager that yields a DB session and commits on exit."""
    async with SessionMaker() as session:  # type: AsyncSession
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Caching layer -------------------------------------------------------------
# ---------------------------------------------------------------------------
# Cache key: (group_id, day ISO) → "formatted schedule markdown"
DAY_CACHE = TTLCache(maxsize=2048, ttl=60 * 15)  # 15 мин
WEEK_CACHE = TTLCache(maxsize=1024, ttl=60 * 30)  # 30 мин


# ---------------------------------------------------------------------------
# Helpers -------------------------------------------------------------------
# ---------------------------------------------------------------------------
async def _markdown_schedule_for_day(group_id: int, when: date) -> str:
    key = (group_id, when.isoformat())
    if key in DAY_CACHE:
        return DAY_CACHE[key]
    async with get_session() as db:
        q = (
            select(models.Lesson)
            .where(models.Lesson.group_id == group_id, models.Lesson.date == when)
            .order_by(models.Lesson.start_time)
        )
        res = await db.scalars(q)
        lessons: List[models.Lesson] = res.all()
    if not lessons:
        text = "📅 На {:%d.%m.%Y} занятий нет!".format(when)
    else:
        lines = ["📅 **Расписание на {:%d.%m.%Y}**".format(when)]
        for i, les in enumerate(lessons, 1):
            t_str = f"{les.start_time:%H:%M}–{les.end_time:%H:%M}"
            teacher = f"\n_преп.: {les.teacher.name}_" if les.teacher else ""
            room = f" ({les.room.building}-{les.room.number})" if les.room else ""
            lines.append(f"{i}. `{t_str}` **{les.subject}**{room}{teacher}")
        text = "\n".join(lines)
    DAY_CACHE[key] = text
    return text


async def _markdown_schedule_for_week(group_id: int, monday: date) -> str:
    key = (group_id, monday.isoformat())
    if key in WEEK_CACHE:
        return WEEK_CACHE[key]
    texts = []
    for d in (monday + timedelta(days=i) for i in range(6)):  # Пн‑Сб
        daily = await _markdown_schedule_for_day(group_id, d)
        if "занятий нет" in daily:
            continue
        texts.append(daily)
    result = "\n\n".join(texts) if texts else "ℹ️ На этой неделе занятий нет."
    WEEK_CACHE[key] = result
    return result


async def _get_or_create_user(telegram_id: int, db: AsyncSession) -> None:
    if await db.get(models.User, telegram_id) is None:
        db.add(models.User(id=telegram_id))


async def _get_active_group(user_id: int, db: AsyncSession) -> models.Group | None:
    q = (
        select(models.Group)
        .join(models.UserGroup)
        .where(models.UserGroup.user_id == user_id, models.UserGroup.is_active == True)  # noqa: E712
    )
    res = await db.scalars(q)
    return res.first()


# ---------------------------------------------------------------------------
# Routers & Handlers --------------------------------------------------------
# ---------------------------------------------------------------------------
router = Router()


@router.message(CommandStart())
async def cmd_start(msg: types.Message) -> None:
    async with get_session() as db:
        await _get_or_create_user(msg.from_user.id, db)
    await msg.answer(
        "Добро пожаловать!\n"\
        "\nВыберите вашу учебную группу через команду /group, „/группа“.\n"\
        "Затем используйте /today и /week, чтобы смотреть расписание.",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("help"))
async def cmd_help(msg: types.Message) -> None:
    await msg.answer(
        "**Справка**\n"\
        "/group — выбрать группу\n"\
        "/today — расписание на сегодня\n"\
        "/week — расписание на эту неделю\n"\
        "/help — эта справка",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("group"))
async def cmd_group(msg: types.Message) -> None:
    # Show paginated groups (first 50) — for demo simplicity.
    async with get_session() as db:
        res = await db.execute(select(models.Group).order_by(models.Group.code).limit(50))
        groups = res.scalars().all()
    kb = InlineKeyboardBuilder()
    for g in groups:
        kb.button(text=g.code, callback_data=f"setgrp:{g.id}")
    kb.adjust(2)
    await msg.answer("Выберите группу:", reply_markup=kb.as_markup())


@router.callback_query(lambda c: c.data.startswith("setgrp:"))
async def cb_set_group(cb: types.CallbackQuery) -> None:  # noqa: D401
    group_id = int(cb.data.split(":", 1)[1])
    async with get_session() as db:
        await _get_or_create_user(cb.from_user.id, db)
        # deactivate prev
        await db.execute(
            select(models.UserGroup)  # forcing load
            .where(models.UserGroup.user_id == cb.from_user.id, models.UserGroup.is_active == True)  # noqa: E712
            .execution_options(populate_existing=True)
        )
        await db.execute(
            models.UserGroup.__table__.update()
            .where(models.UserGroup.user_id == cb.from_user.id, models.UserGroup.is_active == True)  # noqa: E712
            .values(is_active=False)
        )
        db.add(models.UserGroup(user_id=cb.from_user.id, group_id=group_id, is_active=True))
    await cb.answer("Группа сохранена!")
    await cb.message.edit_text("✅ Группа сохранена. Теперь используйте /today или /week.")


@router.message(Command("today"))
async def cmd_today(msg: types.Message) -> None:
    today = date.today()
    async with get_session() as db:
        group = await _get_active_group(msg.from_user.id, db)
    if not group:
        await msg.answer("Сначала выберите группу через /group ⬅️")
        return
    text = await _markdown_schedule_for_day(group.id, today)
    await msg.answer(text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("week"))
async def cmd_week(msg: types.Message) -> None:
    today = date.today()
    monday = today - timedelta(days=today.weekday())  # 0 → Monday
    async with get_session() as db:
        group = await _get_active_group(msg.from_user.id, db)
    if not group:
        await msg.answer("Сначала выберите группу через /group ⬅️")
        return
    text = await _markdown_schedule_for_week(group.id, monday)
    await msg.answer(text, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Startup & Scheduler -------------------------------------------------------
# ---------------------------------------------------------------------------

aio_scheduler = AsyncIOScheduler()

aio_scheduler.add_job(fetcher_sync, "cron", hour=5, kwargs={"db": SessionMaker()})


async def main() -> None:
    bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(router)

    # on‑startup events
    aio_scheduler.start()
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
