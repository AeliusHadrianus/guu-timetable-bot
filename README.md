Telegram‑бот «Расписание ГУУ»

> Дипломный проект (май – июнь 2025 г.)
> Бот даёт студентам и преподавателям мгновенный доступ к актуальному расписанию занятий Государственного университета управления.

---

Основные возможности

| Для студентов и преподавателей             | Для администратора                                    |
| :----------------------------------------- | :---------------------------------------------------- |
| `/start`, `/help` — справка                | `/admin_help` — справка админа                        |
| `/group` — выбор группы                    | Загрузка *.xlsx* / *.csv* в чат                       |
| `/today`, `/week` — отображение расписания | `/admin_import_sheet <url>` — импорт из Google Sheets |
| Inline‑кнопки «день/неделя ±1»             | `/admin_sync` — форс‑синхронизация с guu.ru           |
| Markdown‑формат сообщений                  | Ежедневная авто‑синхронизация (05:00 МСК)             |

---

Стек технологий

* Python 3.12 + aiogram 3 — Telegram API
* SQLAlchemy 2 async + SQLite 3 — хранение данных
* APScheduler — фоновые задания
* openpyxl / pandas / httpx / BeautifulSoup — обработка расписаний
* pytest + anyio — тесты (coverage ≥ 80 %)
* GitHub Actions — lint → tests → автодеплой на Render

---

Быстрый старт (локально)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export BOT_TOKEN="<telegram‑token>"
export ADMIN_IDS="123456789"              # ваш Telegram‑ID
export DB_URL="sqlite+aiosqlite:///schedule.db"

alembic upgrade head                       # создаём схему
python -m app.bot                          # запускаем бота
```

> Проверьте работу: в Telegram выполните `/start`, затем `/group` → `/today`.

---

Переменные окружения

| Переменная         | Назначение                              | Пример                             |
| ------------------ | --------------------------------------- | ---------------------------------- |
| `BOT_TOKEN`        | Токен, полученный у @BotFather          | `123456:ABC-DEF…`                  |
| `DB_URL`           | URL базы в формате SQLAlchemy           | `sqlite+aiosqlite:///schedule.db`  |
| `ADMIN_IDS`        | CSV‑список Telegram‑ID с правами админа | `123,456`                          |
| `GUU_SCHEDULE_URL` | (опц.) URL страницы расписаний          | `https://guu.ru/student/schedule/` |

---

Тесты

```bash
pytest -q    # выполняет tests/ (≈ 2 с)
```

Покрытие ≥ 80 %. Проверяется:

* разбор времени и Excel;
* уникальность групп;
* форматирование расписания (helpers).

---

Деплой на Render

1. Fork репозиторий → «Deploy to Render» (Blueprint).
2. Задайте переменные `BOT_TOKEN`, `ADMIN_IDS`.
3. Тип сервиса — Background Worker, runtime — Python 3.12.
4. Start command: `python -m app.bot`.

> APScheduler запускает фоновую синхронизацию прямо в контейнере Render.

---

Обновление расписания

1. Автоматически — задача `fetcher_parser.sync` скачивает новые *.xlsx* с guu.ru ежедневно в 05:00 (МСК).
2. Вручную — админ может:

   * отправить .xlsx / .csv файл боту;
   * выполнить `/admin_import_sheet <url>` для публичной Google‑таблицы.

Дубликаты распознаются по SHA‑256, старые файлы не дублируются.

---

Структура проекта

```
app/
 ├─ bot.py                 # точка входа
 ├─ handlers/
 │   ├─ common.py          # /start, /help, /group, /today, /week
 │   └─ admin.py           # админ‑команды, импорт файлов/таблиц
 ├─ services/
 │   ├─ fetcher_parser.py  # guu.ru → Excel → БД
 │   ├─ google_sheets_import.py
 │   └─ …
 ├─ db/models.py           # ORM‑модели
 └─ tests/                 # unit + integration
```

ER‑диаграмма — `docs/er.pdf`.

---

Команды бота

| Роль            | Команда                     | Описание                 |
| --------------- | --------------------------- | ------------------------ |
| пользователь | `/start`, `/help`           | Справка                  |
|                 | `/group`                    | Выбор учебной группы     |
|                 | `/today`                    | Расписание на сегодня    |
|                 | `/week`                     | Расписание на неделю     |
| админ       | `/admin_help`               | Справка админа           |
|                 | `/admin_sync`               | Форс‑обновление с guu.ru |
|                 | `/admin_import_sheet <url>` | Импорт Google Sheets     |
|                 | отправить *.xlsx* / *.csv*  | Импорт файла             |

---

Документация и слайды

* docs/user\_admin\_guide.pdf — руководство (8 стр.).
* docs/defense\_slides.pptx — презентация (12 слайдов).

Собрать актуальные версии:

```bash
make docs        # либо ./scripts/build_docs.sh
```

---

Лицензия

Проект распространяется по лицензии MIT — используй, изменяй, делись.
