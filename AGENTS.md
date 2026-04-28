# AGENTS.md — Подпольщик Билл

Справочник для AI-агентов, работающих над этим проектом.

## Стек

| Компонент | Версия / детали |
|---|---|
| Python | 3.11+ |
| python-telegram-bot | 20.7, async (PTB v20) |
| Supabase | PostgreSQL через supabase-py |
| pytz | Работа с МСК временем |
| python-dotenv | Переменные окружения |
| Деплой | Railway, polling-режим, точка входа `python bot.py` |

## Структура проекта

```
.
├── bot.py               # Точка входа: сборка Application, регистрация хендлеров
├── config.py            # Все переменные окружения (load_dotenv + os.environ)
├── database.py          # Все запросы к Supabase. Без бизнес-логики
├── messages.py          # Все фразы бота. Случайный выбор через get(lst)
├── utils.py             # Утилиты: get_moscow_date, get_month_end,
│                        #           pluralize_days, fmt_number, get_display_name
├── handlers/
│   ├── activity.py      # Приём шагов и зарядки (MessageHandler)
│   ├── report.py        # /report и callback-голосование
│   ├── stats.py         # /stats, /topsteps, /topexercise
│   └── admin.py         # /addadmin, /pardon, /reset, /adddays, /removedays, /addxp
├── schema.sql           # Базовая SQL-схема (может не отражать prod-состояние)
├── requirements.txt
└── .env.example
```

## Переменные окружения

```
BOT_TOKEN               # Токен от @BotFather
SUPABASE_URL            # https://xxx.supabase.co
SUPABASE_KEY            # anon key из Supabase
OWNER_ID                # Telegram user_id хозяйки (int)
GROUP_ID                # ID супергруппы (отрицательный int)
STEPS_THREAD_ID         # ID топика «шаги» (int)
EXERCISE_THREAD_ID      # ID топика «зарядка» (int)
PINNED_STEPS_MESSAGE_ID    # ID закреплённого сообщения шагов (int, 0 = отключено)
PINNED_EXERCISE_MESSAGE_ID # ID закреплённого сообщения зарядки (int, 0 = отключено)
```

Все переменные читаются в `config.py`. Добавляя новую переменную — добавь её туда и в `.env.example`.

## База данных

Все запросы — в `database.py` через `_client = create_client(...)`. Никаких SQL-запросов в хендлерах.

### Таблицы

**users** — участники, upsert при каждом действии:
`user_id, username, first_name, last_name, created_at`

**activities** — записи активностей (одна в день на тип):
`id, user_id, activity_type ('steps'|'exercise'), activity_date, month, year, steps_count, created_at`
Уникальный ключ: `(user_id, activity_type, activity_date)`

**jails** — карцер:
`id, user_id, activity_type, jailed_until, active, jailed_at`
Активный карцер: `active = true`. Снимается через `pardon_user` / `pardon_all`.

**reports** — жалобы:
`id, reporter_id, reported_user_id, chat_id, message_id, vote_message_id, thread_id, status ('open'|'jailed'|'cleared'), yes_votes, created_at, expires_at`

**report_votes** — голоса по жалобам:
`id, report_id, voter_id, voted_at`
Уникальный ключ: `(report_id, voter_id)`

**admins** — администраторы:
`user_id, added_by, added_at`

**xp** — опыт участников:
`user_id, total_xp`

**total_steps** — шаги за всё время:
`user_id, all_time_steps`

> ⚠️ `schema.sql` не содержит таблицы `xp` и `total_steps`, а также колонку `steps_count` в `activities` и `activity_type` в `jails` — они были добавлены позже. При миграции нового окружения создавать их вручную.

## Логика приёма активности (`handlers/activity.py`)

### Шаги (топик STEPS_THREAD_ID)

Триггер: фото в топике шагов.

1. Парсим число из `caption + text` через `_parse_steps_count()`
2. Если число не найдено — тихо выходим (нет ответа)
3. `upsert_user`
4. Проверка карцера → `JAILED_TRY`
5. Проверка дубля за сегодня (МСК) → `ALREADY_SUBMITTED_STEPS`
6. Если число < 10 000 → `TOO_FEW_STEPS`
7. `record_steps` → `add_xp(steps // 500)` → `add_total_steps`
8. Ответ `STEPS_ACCEPTED` + обновление закреплённого лидерборда

`_parse_steps_count` принимает форматы: `12975`, `12 975`, `12,975`, `12.975`.

### Зарядка (топик EXERCISE_THREAD_ID)

Триггер: видео в топике зарядки.

1. Проверка "+1" в `caption + text`
2. Если нет "+1" — тихо выходим
3. `upsert_user`
4. Проверка карцера → `JAILED_TRY`
5. Проверка дубля → `ALREADY_SUBMITTED_EXERCISE`
6. `record_activity` → ответ `EXERCISE_ACCEPTED` + обновление лидерборда

## Логика жалоб (`handlers/report.py`)

`/report` — только reply на чужое сообщение:
- Жалоба только в день публикации исходного сообщения (МСК)
- Reporter должен иметь хоть одну запись в `activities` за текущий месяц
- Нельзя подать повторную жалобу на то же сообщение
- Голосование 24 часа, 5 голосов «Да» → карцер до конца месяца
- Закрытие через `job_queue.run_once()` на 24 часа

Callback-кнопки: `vote:yes:{report_id}`, `vote:no:{report_id}`

## Статистика (`handlers/stats.py`)

`/stats` — досье: шаги/зарядка за месяц, шаги за месяц и всего, XP и уровень.
Цель: reply на сообщение → статистика того человека; `@username` → по нику; без аргументов → своя.

`/topsteps`, `/topexercise` — лидерборды по отдельной активности.
`build_activity_leaderboard()` используется также в `_update_pinned_leaderboard()` в `activity.py`.

## Админ-команды (`handlers/admin.py`)

| Команда | Доступ | Действие |
|---|---|---|
| `/addadmin @ник` | Только OWNER_ID | Добавить в `admins` |
| `/pardon @ник` | Админы + owner | Снять карцер с участника |
| `/reset` | Админы + owner | Снять все карцеры (activites не трогаем) |
| `/adddays @ник steps\|exercise N` | Админы + owner | Добавить N дней активности |
| `/removedays @ник steps\|exercise N` | Админы + owner | Удалить N дней активности |
| `/addxp @ник N` | Админы + owner | Начислить XP вручную |

## Правила написания кода

**Временна́я зона.** Всегда `Europe/Moscow`. Дата сегодня — `get_moscow_date()` из `utils.py`. Никаких `datetime.date.today()` или `datetime.datetime.utcnow()`.

**Ответы бота.** Всегда `message.reply_text(...)` — ответ-реплай на исходное сообщение пользователя. Исключения: объявления на весь топик (`context.bot.send_message` с `message_thread_id`).

**parse_mode.** Везде где нужно форматирование — `parse_mode="HTML"`. Markdown не используется.

**Фразы.** Все строки бота живут в `messages.py` как списки. Добавляй новые фразы туда, используй `msg.get(msg.СПИСОК)` в хендлерах. Не хардкодь текст внутри хендлеров.

**База данных.** Весь SQL/Supabase — только в `database.py`. Хендлеры импортируют `database as db` и вызывают функции. Не создавай Supabase-клиент вне `database.py`.

**Обработка ошибок.** DB-вызовы оборачивать в `try/except` с `print(f"[МОДУЛЬ] ОШИБКА имя_функции: {e}")`. Критические ошибки (до записи активности) — `raise`, чтобы глобальный `error_handler` в `bot.py` поймал и залогировал трейсбек. XP/total_steps ошибки — не re-raise (запись уже сохранена, ответ должен уйти).

**Карцер.** `jailed_until` = последний день текущего месяца по МСК (`get_month_end`). Карцер раздельный по `activity_type`: можно быть в карцере по шагам, но не по зарядке.

**Отображаемое имя.** Всегда через `get_display_name(user_dict)` из `utils.py`. Порядок: `@username` → `first_name last_name` → `«Неизвестный боец»`.

## Логирование (соглашения)

Все `print`-логи имеют префикс в квадратных скобках:

```
[ACT]         handle_activity — входящее сообщение (chat_id, thread_id, photo, video, text)
[STEPS]       _handle_steps — каждый шаг обработки шагов
[PINNED]      запуск обновления закреплённого сообщения
[PINNED_UPDATE] детали вызова edit_message_text
[TOPSTEPS]    chat_id и message_id ответа /topsteps
[TOPEXERCISE] chat_id и message_id ответа /topexercise
[DEBUG]       debug_ids — все входящие апдейты (временный хендлер)
```

Глобальный `error_handler` в `bot.py` логирует все необработанные исключения через `logger.error` + `traceback.print_exc()`.

## Персонаж бота

**Подпольщик Билл** — старый космический пират-подпольщик.
- Язык: только русский
- Тон: саркастичный, ироничный, революционный, в душе добрый
- Лексика: «боец», «Сопротивление», «Фаундер», «карцер», «вива ля резистанс»
- Стиль ответов: короткие ёмкие фразы, без лишних слов

При добавлении новых фраз — выдерживай этот стиль.
