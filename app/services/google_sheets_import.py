"""
services/google_sheets_import.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Импорт расписания из *публичной* Google-таблицы (режим «Anyone with the link»).

Алгоритм
--------
1. По URL преобразуем ссылку в CSV-export (`…/export?format=csv`).
2. Скачиваем CSV (без OAuth — работает только с публичными таблицами).
3. Читаем в pandas.DataFrame.
4. Конвертируем строки DataFrame → объекты Lesson (pydantic-модель, та же,
   что используется в fetcher_parser.py).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Sequence

import httpx
import pandas as pd
from pydantic import ValidationError

# берём модель Lesson из уже существующего парсера Excel
from services.fetcher_parser import Lesson

# ────────────────────────────────────────────────────────────────────────────────
# Константы и утилиты
# ────────────────────────────────────────────────────────────────────────────────
SHEET_URL_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)/")          # извлекаем ID таблицы
TIME_RE = re.compile(r"(\\d{1,2}):(\\d{2})\\s*[–—-]\\s*(\\d{1,2}):(\\d{2})")

# ────────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ────────────────────────────────────────────────────────────────────────────────
async def _download_csv(sheet_url: str) -> str:
    """Возвращает CSV-текст из публичной Google-таблицы."""
    m = SHEET_URL_RE.search(sheet_url)
    if not m:
        raise ValueError("Некорректная ссылка на Google Sheets")

    sheet_id = m.group(1)
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    )

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(csv_url)
        r.raise_for_status()
        return r.text


def _df_to_lessons(df: pd.DataFrame) -> list[Lesson]:
    """
    Переводит DataFrame в список Lesson.

    Минимальные колонки (регистр не важен):
      • group / group_code
      • date
      • time  – строка вида «10:30-12:05»
      • subject
    Необязательные:
      • teacher
      • room
    """
    df = df.rename(columns={c.lower().strip(): c for c in df.columns})

    # гибко принимаем group или group_code
    if "group_code" not in df and "group" in df:
        df = df.rename(columns={"group": "group_code"})

    required = {"group_code", "date", "time", "subject"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"В таблице нет колонок: {', '.join(missing)}")

    lessons: list[Lesson] = []

    for row in df.itertuples(index=False):
        # время
        match = TIME_RE.match(str(row.time))
        if not match:
            continue
        sh, sm, eh, em = map(int, match.groups())
        start_t = time(sh, sm)
        end_t = time(eh, em)

        # дата
        raw_date = row.date
        if isinstance(raw_date, (pd.Timestamp, datetime)):
            lesson_date: date = raw_date.date()
        else:
            lesson_date = datetime.strptime(str(raw_date), "%d.%m.%Y").date()

        try:
            lessons.append(
                Lesson(
                    group_code=str(row.group_code).upper(),
                    date=lesson_date,
                    start_time=start_t,
                    end_time=end_t,
                    subject=str(row.subject),
                    teacher=getattr(row, "teacher", None),
                    room=getattr(row, "room", None),
                )
            )
        except ValidationError:
            # пропускаем строку, если не проходит валидацию pydantic
            continue

    return lessons


# ────────────────────────────────────────────────────────────────────────────────
# Публичная функция
# ────────────────────────────────────────────────────────────────────────────────
async def lessons_from_sheet(sheet_url: str) -> Sequence[Lesson]:
    """
    Загружает Google-таблицу и возвращает список Lesson.

    Пример:
        lessons = await lessons_from_sheet(
            \"\"\"https://docs.google.com/spreadsheets/d/1ABCdEfGhIjKlMNOpqRS_tUvwXYZ/edit#gid=0\"\"\"
        )
    """
    csv_text = await _download_csv(sheet_url)

    # pandas 2.x дружит с TextIO, используем напрямую
    df = pd.read_csv(pd.compat.StringIO(csv_text))  # type: ignore[arg-type]
    return _df_to_lessons(df)


# ────────────────────────────────────────────────────────────────────────────────
# CLI-отладка (запуск в терминале)
# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m services.google_sheets_import <Google-Sheet-URL>")
        raise SystemExit(1)

    async def _main():
        lessons = await lessons_from_sheet(sys.argv[1])
        print("Parsed", len(lessons), "lessons")

    asyncio.run(_main())
