import datetime
import random
import pytz

from telegram.ext import ContextTypes

import database as db
import messages as msg
from config import GROUP_ID, STEPS_THREAD_ID, EXERCISE_THREAD_ID, NEWS_THREAD_ID, SALO_THREAD_ID, WRITERS_THREAD_ID
from utils import get_display_name, pluralize_days, fmt_number

MOSCOW_TZ = pytz.timezone("Europe/Moscow")

_MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}

_MEDALS = ["🥇", "🥈", "🥉"]


def _board_steps(rows: list) -> str:
    if not rows:
        return "В этом месяце никто не шагал. Расслабились, бойцы."
    lines = []
    for i, r in enumerate(rows):
        name = get_display_name(r["user"])
        prefix = _MEDALS[i] if i < 3 else f"{i + 1}."
        entry = f"{prefix} <b>{name}</b>" if i < 3 else f"{prefix} {name}"
        entry += f" — {pluralize_days(r['days'])} / {fmt_number(r['steps_sum'])} шагов"
        lines.append(entry)
    return "\n".join(lines)


def _board_exercise(rows: list) -> str:
    if not rows:
        return "В этом месяце никто не заряжался."
    lines = []
    for i, r in enumerate(rows):
        name = get_display_name(r["user"])
        prefix = _MEDALS[i] if i < 3 else f"{i + 1}."
        entry = f"{prefix} <b>{name}</b>" if i < 3 else f"{prefix} {name}"
        entry += f" — {pluralize_days(r['days'])}"
        lines.append(entry)
    return "\n".join(lines)


def _board_writing(rows: list) -> str:
    if not rows:
        return "В этом месяце никто не писал посты."
    lines = []
    for i, r in enumerate(rows):
        name = get_display_name(r["user"])
        prefix = _MEDALS[i] if i < 3 else f"{i + 1}."
        streak = r["current_streak"]
        best = r["max_streak_this_month"]
        entry = f"{prefix} <b>{name}</b>" if i < 3 else f"{prefix} {name}"
        entry += f" — {streak} дн. подряд (рекорд: {best})"
        lines.append(entry)
    return "\n".join(lines)


def _board_salo(rows: list) -> str:
    if not rows:
        return "В этом месяце сало не сбрасывали."
    lines = []
    for i, r in enumerate(rows):
        name = get_display_name(r["user"])
        prefix = _MEDALS[i] if i < 3 else f"{i + 1}."
        entry = f"{prefix} <b>{name}</b>" if i < 3 else f"{prefix} {name}"
        entry += f" — {r['monthly_grams']} г"
        lines.append(entry)
    return "\n".join(lines)


def _top3(rows: list, fmt_fn) -> str:
    top = rows[:3]
    if not top:
        return "нет данных"
    return ", ".join(f"{_MEDALS[i]} {fmt_fn(r)}" for i, r in enumerate(top))


async def _send(context: ContextTypes.DEFAULT_TYPE, text: str, thread_id: int | None = None) -> None:
    kwargs: dict = {"chat_id": GROUP_ID, "text": text, "parse_mode": "HTML"}
    if thread_id:
        kwargs["message_thread_id"] = thread_id
    try:
        await context.bot.send_message(**kwargs)
    except Exception as e:
        print(f"[MONTHLY_RESET] error sending to thread_id={thread_id}: {e}")


async def send_daily_xp_leaderboard(context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.get_xp_leaderboard()
    if not rows:
        return

    lines = []
    for i, r in enumerate(rows):
        name = get_display_name(r["user"])
        xp = r["total_xp"]
        level = db.get_level(xp)
        prefix = _MEDALS[i] if i < 3 else f"{i + 1}."
        entry = f"{prefix} <b>{name}</b>" if i < 3 else f"{prefix} {name}"
        lines.append(f"{entry} — {fmt_number(xp)} XP (Уровень {level})")

    text = f"{msg.get(msg.DAILY_XP_HEADER)}\n\n" + "\n".join(lines)
    await _send(context, text, NEWS_THREAD_ID)


async def send_steps_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.datetime.now(MOSCOW_TZ).date()
    users = db.get_users_without_activity_today("steps", today)
    if not users:
        return
    user = random.choice(users)
    name = get_display_name(user)
    mention = f'<a href="tg://user?id={user["user_id"]}">{name}</a>'
    text = msg.get(msg.REMINDER_STEPS).replace("{name}", mention)
    await _send(context, text, STEPS_THREAD_ID)


async def send_exercise_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.datetime.now(MOSCOW_TZ).date()
    users = db.get_users_without_activity_today("exercise", today)
    if not users:
        return
    user = random.choice(users)
    name = get_display_name(user)
    mention = f'<a href="tg://user?id={user["user_id"]}">{name}</a>'
    text = msg.get(msg.REMINDER_EXERCISE).replace("{name}", mention)
    await _send(context, text, EXERCISE_THREAD_ID)


async def send_salo_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not SALO_THREAD_ID:
        return
    users = db.get_all_users()
    if not users:
        return
    user = random.choice(users)
    name = get_display_name(user)
    mention = f'<a href="tg://user?id={user["user_id"]}">{name}</a>'
    text = msg.get(msg.REMINDER_SALO).replace("{name}", mention)
    await _send(context, text, SALO_THREAD_ID)


async def monthly_reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    now_msk = datetime.datetime.now(MOSCOW_TZ)
    # Job fires at 00:00 MSK on 1st — subtract 1 day to get the month that just ended
    prev = now_msk - datetime.timedelta(days=1)
    month, year = prev.month, prev.year
    month_name = _MONTH_NAMES[month]

    print(f"[MONTHLY_RESET] starting for {month_name} {year}")

    steps_rows = sorted(db.get_steps_leaderboard(month, year), key=lambda r: r["steps_sum"], reverse=True)
    exercise_rows = sorted(db.get_activity_top("exercise", month, year), key=lambda r: r["days"], reverse=True)
    salo_rows = sorted(db.get_salo_leaderboard(month, year), key=lambda r: r["monthly_grams"], reverse=True)
    writing_rows = sorted(db.get_writing_leaderboard(), key=lambda r: r["max_streak_this_month"], reverse=True)

    # Steps thread
    await _send(
        context,
        f"{msg.get(msg.MONTH_END_STEPS)}\n\n🚶 Итоги по шагам — {month_name} {year}\n\n{_board_steps(steps_rows)}",
        STEPS_THREAD_ID,
    )

    # Exercise thread
    await _send(
        context,
        f"{msg.get(msg.MONTH_END_EXERCISE)}\n\n⚡ Итоги по зарядке — {month_name} {year}\n\n{_board_exercise(exercise_rows)}",
        EXERCISE_THREAD_ID,
    )

    # Salo thread (optional)
    if SALO_THREAD_ID:
        await _send(
            context,
            f"{msg.get(msg.MONTH_END_SALO)}\n\n🥓 Итоги по салу — {month_name} {year}\n\n{_board_salo(salo_rows)}",
            SALO_THREAD_ID,
        )

    # Writing thread (optional)
    if WRITERS_THREAD_ID:
        await _send(
            context,
            f"{msg.get(msg.MONTH_END_WRITING)}\n\n✍️ Итоги по постам — {month_name} {year}\n\n{_board_writing(writing_rows)}",
            WRITERS_THREAD_ID,
        )

    # News thread — compact top-3 summary
    top3_steps = _top3(steps_rows, lambda r: f"{get_display_name(r['user'])}: {fmt_number(r['steps_sum'])} шагов")
    top3_exercise = _top3(exercise_rows, lambda r: f"{get_display_name(r['user'])}: {pluralize_days(r['days'])}")
    top3_salo = _top3(salo_rows, lambda r: f"{get_display_name(r['user'])}: {r['monthly_grams']} г")
    top3_writing = _top3(writing_rows, lambda r: f"{get_display_name(r['user'])}: {r['max_streak_this_month']} дн.")

    news_text = (
        f"{msg.get(msg.MONTH_END_NEWS)}\n\n"
        f"📅 Месяц {month_name} позади! Вот лидеры:\n\n"
        f"🚶 Шаги: {top3_steps}\n"
        f"⚡ Зарядка: {top3_exercise}\n"
        f"🥓 Сало: {top3_salo}\n"
        f"✍️ Посты: {top3_writing}"
    )
    await _send(context, news_text, NEWS_THREAD_ID)

    # Lift all jails
    db.pardon_all()

    # Reset writing streaks for new month
    db.reset_writing_streaks()

    print(f"[MONTHLY_RESET] done for {month_name} {year}, all jails pardoned, writing streaks reset")
