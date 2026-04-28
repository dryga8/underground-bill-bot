import datetime
import pytz

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
import messages as msg
from utils import get_display_name, pluralize_days

MOSCOW_TZ = pytz.timezone("Europe/Moscow")

_MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _month_label(month: int, year: int) -> str:
    return f"{_MONTH_NAMES[month]} {year}"


def build_activity_leaderboard(activity_type: str, month: int, year: int) -> str:
    """Возвращает отформатированный лидерборд по одной активности (без заголовка)."""
    rows = db.get_activity_top(activity_type, month, year)
    rows.sort(key=lambda r: get_display_name(r["user"]).lower())

    lines = []
    for r in rows:
        name = get_display_name(r["user"])
        if db.is_jailed(r["user"]["user_id"], activity_type):
            lines.append(f"{name} — 🚫")
        else:
            lines.append(f"{name} — {pluralize_days(r['days'])}")
    return "\n".join(lines) if lines else "Пока никто не отметился."


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    month, year = now_msk.month, now_msk.year

    target_user_data: dict | None = None

    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        db.upsert_user(ru.id, ru.username, ru.first_name, ru.last_name)
        target_user_data = {
            "user_id": ru.id,
            "username": ru.username,
            "first_name": ru.first_name,
            "last_name": ru.last_name,
        }
    elif context.args:
        username = context.args[0].lstrip("@")
        target_user_data = db.get_user_by_username(username)
        if not target_user_data:
            await message.reply_text(f"Боец @{username} в архивах не найден. Может, ещё не отмечался?")
            return
    else:
        u = update.effective_user
        if not u:
            return
        db.upsert_user(u.id, u.username, u.first_name, u.last_name)
        target_user_data = {
            "user_id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
        }

    uid = target_user_data["user_id"]
    stats = db.get_user_stats(uid, month, year)
    display = get_display_name(target_user_data)

    steps_str = "🚫" if db.is_jailed(uid, "steps") else pluralize_days(stats["steps"])
    exercise_str = "🚫" if db.is_jailed(uid, "exercise") else pluralize_days(stats["exercise"])

    text = (
        f"{msg.get(msg.STATS_HEADER)}\n\n"
        f"🗂 Досье на бойца: <b>{display}</b>\n\n"
        f"📅 {_month_label(month, year)}:\n"
        f"  🚶 Шагает: {steps_str}\n"
        f"  ⚡ Заряжается: {exercise_str}"
    )
    await message.reply_text(text, parse_mode="HTML")


async def cmd_topsteps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    month, year = now_msk.month, now_msk.year

    leaderboard = build_activity_leaderboard("steps", month, year)
    text = (
        f"{msg.get(msg.TOP_HEADER)}\n"
        f"🚶 Шаги — {_month_label(month, year)}\n\n"
        f"{leaderboard}"
    )
    sent = await message.reply_text(text, parse_mode="HTML")
    print(f"[TOPSTEPS] chat_id={sent.chat_id}  message_id={sent.message_id}")


async def cmd_topexercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    month, year = now_msk.month, now_msk.year

    leaderboard = build_activity_leaderboard("exercise", month, year)
    text = (
        f"{msg.get(msg.TOP_HEADER)}\n"
        f"⚡ Зарядка — {_month_label(month, year)}\n\n"
        f"{leaderboard}"
    )
    sent = await message.reply_text(text, parse_mode="HTML")
    print(f"[TOPEXERCISE] chat_id={sent.chat_id}  message_id={sent.message_id}")


def build_handlers():
    return [
        CommandHandler("stats", cmd_stats),
        CommandHandler("topsteps", cmd_topsteps),
        CommandHandler("topexercise", cmd_topexercise),
    ]
