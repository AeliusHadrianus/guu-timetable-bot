"""app/handlers/admin.py

Административные команды и обработчики загрузки расписаний.
Доступно только Telegram‑ID, перечисленным в переменной окружения
``ADMIN_IDS`` (список целых через запятую).

Функции
-------
* Приём *.xlsx* / *.csv* файлов расписаний.
* Импорт из **публичной Google‑таблицы** командой ``/admin_import_sheet <URL>``.
* Быстрый запуск ``fetcher_parser.sync`` — ``/admin_sync``.
* Справка ``/admin_help``.
"""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import Sequence

import pandas as pd
from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.filters.message import DocumentFilter
from openpyxl.utils.exceptions import InvalidFileException

from services.fetcher_parser import (
    Lesson,
    SourceFileMeta,
    bulk_insert_lessons,
    parse_excel,
    sha256_path,
    upsert_source_file,
)
from services.fetcher_parser import sync as fetcher_sync
from services.google_sheets_import import lessons_from_sheet

from app.bot import get_session  # session helper

ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x}
GOOGLE_SHEET_RE = re.compile(r"docs.google.com/spreadsheets/d/([a-zA-Z0-9_-]+)/")

router = Router(name="admin-router")

# ---------------------------------------------------------------------------
# Helpers -------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _parse_csv(path: Path) -> Sequence[Lesson]:
    """CSV → Lesson parser with predefined column names."""
    df = pd.read_csv(path)
    required = {"group_code", "date", "start_time", "end_time", "subject"}
    if missing := required - set(df.columns):
        raise ValueError(f"CSV missing columns: {', '.join(missing)}")
    lessons: list[Lesson] = []
    for row in df.itertuples(index=False):
        lessons.append(
            Lesson(
                group_code=str(row.group_code).upper(),
                date=pd.to_datetime(row.date).date(),
                start_time=pd.to_datetime(row.start_time).time(),
                end_time=pd.to_datetime(row.end_time).time(),
                subject=str(row.subject),
                teacher=getattr(row, "teacher", None),
                room=getattr(row, "room", None),
            )
        )
    return lessons


async def _is_admin(user: types.User) -> bool:
    return user.id in ADMIN_IDS


async def _import_lessons(lessons: Sequence[Lesson], source: SourceFileMeta) -> int:
    """Insert lessons into DB, returns inserted count."""
    async with get_session() as db:
        source_id = await upsert_source_file(source, db)
        await bulk_insert_lessons(lessons, source_id, db)
    return len(lessons)


# ---------------------------------------------------------------------------
# Command handlers ----------------------------------------------------------
# ---------------------------------------------------------------------------


@router.message(Command("admin_help"))
async def admin_help(msg: types.Message) -> None:
    if not await _is_admin(msg.from_user):
        return
    text = (
        "**Админ-команды**\n"
        "• отправьте *.xlsx* или *.csv* — бот импортирует файл;\n"
        "• /admin_import_sheet <URL> — импорт из публичной Google‑таблицы;\n"
        "• /admin_sync — немедленно скачать новые файлы с guu.ru и обновить БД.\n"
    )
    await msg.answer(text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("admin_sync"))
async def admin_sync_cmd(msg: types.Message) -> None:
    if not await _is_admin(msg.from_user):
        return
    await msg.answer("⏳ Синхронизирую…")
    async with get_session() as db:
        await fetcher_sync(db)
    await msg.answer("✅ Готово!")


@router.message(Command("admin_import_sheet"))
async def admin_import_sheet(msg: types.Message, command: CommandObject) -> None:
    if not await _is_admin(msg.from_user):
        return
    if not command.args:
        await msg.answer("⚠️ Укажите URL таблицы после команды.")
        return
    url = command.args.strip()
    if not GOOGLE_SHEET_RE.search(url):
        await msg.answer("⚠️ Похоже, это не ссылка на Google‑таблицу.")
        return
    await msg.answer("⏳ Скачиваю таблицу…")
    try:
        lessons = await lessons_from_sheet(url)
    except Exception as exc:  # pylint: disable=broad-except
        await msg.answer(f"❌ Ошибка: {exc}")
        return
    count = await _import_lessons(lessons, SourceFileMeta(url=url, sha256="gsheet:" + url))
    await msg.answer(f"✅ Импортировано занятий: {count}")


# ---------------------------------------------------------------------------
# File upload handler -------------------------------------------------------
# ---------------------------------------------------------------------------


@router.message(DocumentFilter())
async def admin_upload(msg: types.Message) -> None:  # noqa: D401
    if not await _is_admin(msg.from_user):
        return

    doc: types.Document = msg.document
    file_name = doc.file_name or "uploaded_file"
    suffix = Path(file_name).suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        await msg.answer("⚠️ Поддерживаются только .xlsx и .csv файлы")
        return

    await msg.answer("⏳ Получаю файл…")
    tmpdir = Path(tempfile.mkdtemp())
    dest = tmpdir / file_name
    await msg.bot.download(doc, dest)

    try:
        if suffix == ".xlsx":
            lessons = parse_excel(dest)
        else:
            lessons = _parse_csv(dest)
    except (ValueError, InvalidFileException) as exc:
        await msg.answer(f"❌ Ошибка парсинга: {exc}")
        return

    count = await _import_lessons(lessons, SourceFileMeta(url=f"uploaded:{file_name}", sha256=sha256_path(dest)))
    await msg.answer(f"✅ Импортировано занятий: {count}")
