# AGENTS.md — Подпольщик Билл

Справочник для AI-агентов, работающих над этим проектом.

## Стек

| Компонент | Версия / детали |
|---|---|
| Python | 3.11 |
| python-telegram-bot | 20.7, async (PTB v20) + job-queue |
| Supabase | PostgreSQL через supabase-py 2.x |
| pytz | Работа с МСК временем |
| python-dotenv | Переменные окружения |
| requests | HTTP-запросы (использовался для Gemini, сейчас не активен) |
| Деплой | Railway, polling-режим, Procfile: `worker: python bot.py` |

## Структура проекта

```
.
├── bot.py               # Точка входа: сборка Application, регистрация хендлеров и jobs
├── config.py            # Все переменные окружения (load_dotenv + os.environ)
├── database.py          # Все запросы к Supabase. Без бизнес-логики
├── messages.py          # Все фразы бота. Случайный выбор через get(lst)
├── utils.py             # Утилиты: get_moscow_date, get_month_end,
│                        #           pluralize_days, fmt_number, get_display_name
├── handlers/
│   ├── activity.py      # Приём шагов и зарядки (MessageHandler + edited_message)
│   ├── report.py        # /report и callback-голосование
│   ├── stats.py         # /stats, /topsteps, /topexercise, /topxp, /topsalo
│   ├── admin.py         # Все админские команды
│   ├── welcome.py       # Приветствие новичков, удаление системных сообщений
│   ├── scheduler.py     # Автоматический сброс месяца в 00:00 МСК 1-го числа
│   └── common.py        # Общие утилиты хендлеров (например _DELETE_AFTER_SECONDS)
├── schema.sql           # SQL-схема (может не отражать prod — см. раздел Миграции)
├── requirements.txt
├── Procfile
└── .env.example
```

## Переменные окружения

```
BOT_TOKEN                    # Токен от @BotFather
SUPABASE_URL                 # https://xxx.supabase.co
SUPABASE_KEY                 # anon key (Legacy) из Supabase → Settings → API Keys
OWNER_ID                     # Telegram user_id хозяйки (int)
GROUP_ID                     # ID супергруппы (отрицательный int, формат -100xxxxxxxxxx)
STEPS_THREAD_ID              # ID топика «шаги» (int)
EXERCISE_THREAD_ID           # ID топика «зарядка» (int)
SALO_THREAD_ID               # ID топика «сало» (int, опциональный)
NEWS_THREAD_ID               # ID топика «новости» (int или пусто = основной чат)
PINNED_STEPS_MESSAGE_ID      # ID закреплённого сообщения шагов (int, 0 = отключено)
PINNED_EXERCISE_MESSAGE_ID   # ID закреплённого сообщения зарядки (int, 0 = отключено)
PINNED_SALO_MESSAGE_ID       # ID закреплённого сообщения сало (int, 0 = отключено)
```

Все переменные читаются в `config.py`. При добавлении новой — добавь туда и в `.env.example`.

## База данных

Все запросы — в `database.py` через `_client = create_client(...)`. Никаких Supabase-вызовов в хендлерах.

> ⚠️ **RLS**: у всех таблиц должен быть отключён Row Level Security. При создании новой таблицы сразу выполнять `ALTER TABLE имя DISABLE ROW LEVEL SECURITY;`

### Таблицы

**users** — участники, upsert при каждом действии:
`user_id, username, first_name, last_name, created_at`

**activities** — записи активностей (одна в день на тип):
`id, user_id, activity_type ('steps'|'exercise'), activity_date, month, year, steps_count, created_at`
Уникальный ключ: `(user_id, activity_type, activity_date)`

**jails** — карцер:
`id, user_id, activity_type ('steps'|'exercise'|'salo'), jailed_until, active, jailed_at`
Активный карцер: `active = true`. Карцеры раздельные по activity_type.

**reports** — жалобы:
`id, reporter_id, reported_user_id, chat_id, message_id, vote_message_id, thread_id, status ('open'|'jailed'|'cleared'), yes_votes, created_at, expires_at`

**report_votes** — голоса по жалобам:
`id, report_id, voter_id, voted_at`
Уникальный ключ: `(report_id, voter_id)`

**admins** — администраторы:
`user_id, added_by, added_at`

**xp** — опыт участников:
`user_id, total_xp`

**total_steps** — шаги за всё время (не обнуляется):
`user_id, all_time_steps`

**total_exercise** — дни зарядки за всё время (не обнуляется):
`user_id, all_time_days`

**salo** — записи сброшенного веса за месяц:
`id, user_id, grams, month, year, created_at`

**total_salo** — сало за всё время (не обнуляется):
`user_id, all_time_grams`

**rewards** — награды за уровни:
`id, user_id, level, reward, awarded_at`

### Миграции (таблицы добавленные после первого деплоя)

При разворачивании нового окружения выполнить в Supabase SQL Editor:

```sql
ALTER TABLE activities ADD COLUMN IF NOT EXISTS steps_count INTEGER DEFAULT 0;
ALTER TABLE jails ADD COLUMN IF NOT EXISTS activity_type TEXT DEFAULT 'steps';

CREATE TABLE IF NOT EXISTS xp (user_id BIGINT PRIMARY KEY REFERENCES users(user_id), total_xp INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS total_steps (user_id BIGINT PRIMARY KEY REFERENCES users(user_id), all_time_steps BIGINT DEFAULT 0);
CREATE TABLE IF NOT EXISTS total_exercise (user_id BIGINT PRIMARY KEY REFERENCES users(user_id), all_time_days INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS salo (id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(user_id), grams INTEGER NOT NULL, month INTEGER NOT NULL, year INTEGER NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS total_salo (user_id BIGINT PRIMARY KEY REFERENCES users(user_id), all_time_grams BIGINT DEFAULT 0);
CREATE TABLE IF NOT EXISTS rewards (id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(user_id), level INTEGER NOT NULL, reward TEXT NOT NULL, awarded_at TIMESTAMPTZ DEFAULT NOW());

ALTER TABLE xp DISABLE ROW LEVEL SECURITY;
ALTER TABLE total_steps DISABLE ROW LEVEL SECURITY;
ALTER TABLE total_exercise DISABLE ROW LEVEL SECURITY;
ALTER TABLE salo DISABLE ROW LEVEL SECURITY;
ALTER TABLE total_salo DISABLE ROW LEVEL SECURITY;
ALTER TABLE rewards DISABLE ROW LEVEL SECURITY;
```

## Логика приёма активности (`handlers/activity.py`)

### Шаги (топик STEPS_THREAD_ID)

Триггер: фото в топике шагов (новое сообщение или edited_message).

1. Парсим число из `caption + text` через `_parse_steps_count()`
2. Если число не найдено → `STEPS_NOT_RECOGNIZED` (просьба написать число вручную или отредактировать подпись)
3. `upsert_user`
4. Проверка карцера по 'steps' → `JAILED_TRY`
5. Проверка дубля за сегодня (МСК) → `ALREADY_SUBMITTED_STEPS`
6. Если число < 10 000 → `TOO_FEW_STEPS`
7. `record_steps(steps_count)` → `add_xp(min(steps // 500, 40))` → `add_total_steps`
8. `check_and_award_level(old_xp, new_xp)` → если новые уровни → `send_level_up_notifications`
9. Ответ `STEPS_ACCEPTED` + обновление закреплённого лидерборда

**Лимит XP за шаги**: максимум 40 XP за одну запись (соответствует 20 000 шагов).

`_parse_steps_count` принимает форматы: `12975`, `12 975`, `12,975`, `12.975`.

Бот также обрабатывает `edited_message` — когда пользователь редактирует подпись к фото.

### Зарядка (топик EXERCISE_THREAD_ID)

Триггер: видео в топике зарядки.

1. Проверка "+1" в `caption + text` — если нет, тихо выходим
2. Проверка длины видео: `message.video.duration >= 60` сек → если короче → `TOO_SHORT_VIDEO`
3. `upsert_user`
4. Проверка карцера по 'exercise' → `JAILED_TRY`
5. Проверка дубля → `ALREADY_SUBMITTED_EXERCISE`
6. `record_activity('exercise')` + `add_total_exercise_days()` → `add_xp(10)`
7. `check_and_award_level` → уведомления о наградах
8. Ответ `EXERCISE_ACCEPTED` + обновление закреплённого лидерборда

## Логика жалоб (`handlers/report.py`)

`/report` — только reply на чужое сообщение в ветках шагов, зарядки или сала:
- Жалоба только в день публикации исходного сообщения (МСК)
- Reporter должен иметь хоть одну запись в `activities` за текущий месяц
- Нельзя подать повторную жалобу на то же сообщение
- Нельзя голосовать против себя
- Нельзя голосовать дважды или менять голос
- Голосование 24 часа, **5 голосов «Да»** → карцер до конца месяца по соответствующей activity_type
- Только кнопка «Да» влияет на исход; «Нет» — для UX
- Закрытие через `job_queue.run_once()` на 24 часа
- В сообщении трибунала — ссылка на спорное сообщение: `https://t.me/c/{chat_id_без_минус100}/{message_id}`

Callback-кнопки: `vote:yes:{report_id}`, `vote:no:{report_id}`

## Система XP и наград

### Начисление XP

| Активность | XP | Лимит |
|---|---|---|
| Шаги | steps // 500 | макс. 40 XP в день |
| Зарядка | 10 XP за день | нет |
| Сало | grams // 20 | нет |
| Ручное начисление админом | любое | нет |

### Таблица уровней

```python
LEVELS = [0, 50, 150, 300, 500, 750, 1100, 1600, 2200, 3000,
          4000, 5200, 6600, 8200, 10000, 12000, 14500, 17500, 21000, 25000]
```
После уровня 20 — шаг 5000 XP на каждый следующий уровень.

### Награды

При достижении нового уровня игрок получает случайный предмет из `REWARDS[level]` в `messages.py`.
Награды записываются в таблицу `rewards`. При пропуске уровней — награда за каждый пропущенный.
Объявление о награде отправляется в `NEWS_THREAD_ID` и удаляется через 2 минуты.

## Статистика (`handlers/stats.py`)

`/stats [@username]` — досье пирата:
- Шагает в месяце: X дней
- Шагов за месяц: X
- Шагов всего: X
- Заряжается в [месяц]: X дней
- Заряжается всего: X дней
- Сала за месяц: X г
- Сала всего: X г
- XP: X (Уровень N)
- Награды: список предметов с уровнями

`/topsteps` — лидерборд шагов за месяц: дней + количество шагов
`/topexercise` — лидерборд зарядки за месяц: дней
`/topsalo` — лидерборд сала за месяц: граммы за месяц + всего
`/topxp` — лидерборд XP: total_xp + уровень

Во всех лидербордах — ники без @, без таблиц, каждый участник отдельной строкой.

Закреплённые сообщения обновляются автоматически после каждой записи активности или `/addsalo`.

## Приветствие новичков (`handlers/welcome.py`)

При вступлении нового пользователя:
1. Удаляется системное сообщение Telegram «X вступил в группу»
2. Отправляется приветствие из `WELCOME_MESSAGES` в `NEWS_THREAD_ID` с тегом пользователя
3. Через 3 минуты приветствие автоматически удаляется

## Автосброс месяца (`handlers/scheduler.py`)

Запускается автоматически в **00:00 МСК 1-го числа каждого месяца** через `job_queue`.

Порядок действий:
1. Собирает итоги уходящего месяца (берёт `now - 1 день` чтобы попасть в прошлый месяц)
2. Отправляет полный список с 🥇🥈🥉 в STEPS_THREAD_ID, EXERCISE_THREAD_ID, SALO_THREAD_ID
3. Отправляет топ-3 каждого марафона в NEWS_THREAD_ID
4. Снимает все активные карцеры

Месячные данные (шаги, зарядка, сало) обнуляются автоматически — они считаются по `month` и `year`, поэтому в новом месяце счётчики стартуют с нуля без удаления записей.

## Админ-команды (`handlers/admin.py`)

| Команда | Доступ | Действие |
|---|---|---|
| `/addadmin @ник` | Только OWNER_ID | Добавить в `admins` |
| `/pardon @ник` | Админы + owner | Снять карцер с участника |
| `/reset` | Админы + owner | Снять все карцеры + объявить новый месяц |
| `/fullreset` | Только OWNER_ID | Очистить все данные кроме users и admins |
| `/adddays @ник steps\|exercise N` | Админы + owner | Добавить N дней активности |
| `/removedays @ник steps\|exercise N` | Админы + owner | Удалить N дней активности |
| `/addsteps @ник N` | Админы + owner | Добавить N шагов (+ XP автоматически) |
| `/addsalo @ник N` | Админы + owner | Добавить N грамм сала (+ XP автоматически) |
| `/addxp @ник N` | Админы + owner | Начислить XP вручную (можно отрицательное) |
| `/admin` | Все пользователи | Тегнуть всех админов |

## Правила написания кода

**Временна́я зона.** Всегда `Europe/Moscow`. Дата сегодня — `get_moscow_date()` из `utils.py`. Никаких `datetime.date.today()` или `datetime.datetime.utcnow()`.

**Ответы бота.** Всегда `message.reply_text(...)` — ответ-реплай на исходное сообщение. Исключения: объявления на весь топик — `context.bot.send_message` с `message_thread_id`.

**parse_mode.** Везде где нужно форматирование — `parse_mode="HTML"`. Markdown не используется.

**Фразы.** Все строки бота живут в `messages.py` как списки. Используй `msg.get(msg.СПИСОК)`. Не хардкодь текст в хендлерах. При добавлении новых фраз — выдерживай стиль Подпольщика Билла.

**База данных.** Весь Supabase — только в `database.py`. Хендлеры импортируют `database as db`.

**Обработка ошибок.** DB-вызовы оборачивать в `try/except` с `print(f"[МОДУЛЬ] ОШИБКА: {e}")`. Критические ошибки (до записи активности) — `raise`. XP/total_steps/rewards ошибки — не re-raise (запись уже сохранена).

**Карцер.** `jailed_until` = последний день текущего месяца по МСК (`get_month_end`). Карцер раздельный по `activity_type`: 'steps', 'exercise', 'salo'.

**Отображаемое имя.** Всегда через `get_display_name(user_dict)` из `utils.py`. Порядок: `username` (без @) → `first_name` → `«Неизвестный боец»`. Никаких комбинаций имя+фамилия.

**Автоудаление сообщений.** Через `job_queue.run_once(_delete_message, delay)`. Константа `_DELETE_AFTER_SECONDS` в `handlers/common.py` (сейчас 120 сек = 2 мин).

## Логирование (соглашения)

```
[ACT]           handle_activity — входящее сообщение
[STEPS]         _handle_steps — каждый шаг обработки шагов
[PINNED]        запуск обновления закреплённого сообщения
[PINNED_UPDATE] детали вызова edit_message_text
[TOPSTEPS]      message_id ответа /topsteps
[TOPEXERCISE]   message_id ответа /topexercise
[TOPSALO]       message_id ответа /topsalo
[AWARD]         выдача наград за уровень
[LEVEL_UP]      отправка уведомления о новом уровне
[DB:add_xp]     детали начисления XP
[CLEANUP]       очистка устаревших данных при старте
[DEBUG]         debug_ids — все входящие апдейты (временный хендлер, удалить после использования)
[ENV]           список переменных окружения при старте (временный, удалить после отладки)
```

## Персонаж бота

**Подпольщик Билл** — старый космический пират-подпольщик.
- Язык: только русский
- Тон: саркастичный, ироничный, революционный, в душе добрый
- Лексика: «боец», «Сопротивление», «карцер», «вива ля резистанс», «подполье», «командование»
- Называет себя по имени, не «ботом»
- Стиль: короткие ёмкие фразы, без воды

## Известные ограничения и TODO

- [ ] Проверка длины видео зарядки (≥60 сек) — добавлена недавно, проверить в продакшне
- [ ] Карцер по салу через `/report` — добавлен недавно
- [ ] Команда `/admin` вызова админов — добавлена недавно
- [ ] `/help` с кнопками по разделам и автоудалением через 15 минут — TODO
- [ ] Таблица XP в `/help` — TODO
- [ ] Напоминания пользователям о невыполненных активностях — TODO
- [ ] Рейтинг благодарностей — TODO
