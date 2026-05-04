import datetime
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, filters

import database as db
import messages as msg
from handlers.stats import build_activity_leaderboard, build_salo_leaderboard_text, _month_label, _month_prep
from utils import get_display_name, pluralize_days, fmt_number

MOSCOW_TZ = pytz.timezone("Europe/Moscow")

_PM_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 Моя стата", callback_data="pm:stats")],
    [
        InlineKeyboardButton("🚶 Рейтинг шагов", callback_data="pm:topsteps"),
        InlineKeyboardButton("⚡ Рейтинг зарядки", callback_data="pm:topexercise"),
    ],
    [
        InlineKeyboardButton("🥓 Рейтинг сала", callback_data="pm:topsalo"),
        InlineKeyboardButton("⭐ Рейтинг XP", callback_data="pm:topxp"),
    ],
    [
        InlineKeyboardButton("✍️ Рейтинг графоманов", callback_data="pm:topwriters"),
        InlineKeyboardButton("📈 Таблица уровней", callback_data="pm:levels"),
    ],
    [InlineKeyboardButton("❓ Помощь", callback_data="pm:help")],
    [InlineKeyboardButton("🔄 Обновить", callback_data="pm:refresh")],
])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    u = update.effective_user
    if u:
        db.upsert_user(u.id, u.username, u.first_name, u.last_name)
    await message.reply_text(msg.get(msg.PM_WELCOME), reply_markup=_PM_KEYBOARD, parse_mode="HTML")


def _build_stats_text(user_id: int, user_data: dict) -> str:
    now_msk = datetime.datetime.now(MOSCOW_TZ)
    month, year = now_msk.month, now_msk.year

    stats = db.get_user_stats(user_id, month, year)
    display = get_display_name(user_data)

    steps_jailed = db.is_jailed(user_id, "steps")
    exercise_jailed = db.is_jailed(user_id, "exercise")

    monthly_steps = db.get_monthly_steps(user_id, month, year)
    total_steps = db.get_total_steps(user_id)
    xp = db.get_user_xp(user_id)
    level = db.get_level(xp)
    monthly_salo = db.get_monthly_salo(user_id, month, year)
    total_salo = db.get_total_salo(user_id)
    total_exercise_days = db.get_total_exercise_days(user_id)
    food_days = db.get_food_days(user_id, month, year)
    writing = db.get_writing_streak(user_id)

    rewards = db.get_user_rewards(user_id)
    rewards_str = ""
    if rewards:
        titles = ", ".join(f"{r['reward']} (ур. {r['level']})" for r in rewards)
        rewards_str = f"\n🎖 Награды: {titles}"

    steps_days_str = "🚫" if steps_jailed else pluralize_days(stats["steps"])
    monthly_steps_str = "🚫" if steps_jailed else fmt_number(monthly_steps)
    exercise_month_str = "🚫" if exercise_jailed else pluralize_days(stats["exercise"])
    exercise_total_str = "🚫" if exercise_jailed else pluralize_days(total_exercise_days)

    return (
        f"{msg.get(msg.STATS_HEADER)}\n\n"
        f"🗂 Досье пирата: <b>{display}</b>\n\n"
        f"📅 {_month_label(month, year)}:\n"
        f"⚡ Заряжается в {_month_prep(month)}: {exercise_month_str}\n"
        f"⚡ Заряжается всего: {exercise_total_str}\n"
        f"🚶 Шагает: {steps_days_str}\n"
        f"👟 Шагов за месяц: {monthly_steps_str}\n"
        f"👟 Шагов всего: {fmt_number(total_steps)}\n"
        f"🥓 Сала за месяц: {monthly_salo} г\n"
        f"🥓 Сала всего: {total_salo} г\n"
        f"🍽 Сфоткал еду в {_month_prep(month)}: {pluralize_days(food_days)}\n"
        f"✍️ Посты в {_month_prep(month)}: {writing['current_streak']} дн. подряд "
        f"(рекорд месяца: {writing['max_streak_this_month']} дн.)\n"
        f"⭐ XP: {fmt_number(xp)} (Уровень {level})"
        f"{rewards_str}"
    )


def _build_levels_text() -> str:
    levels = db.LEVELS
    lines = ["📈 <b>Таблица уровней Сопротивления</b>\n"]
    for i, threshold in enumerate(levels):
        lines.append(f"Уровень {i} — от {fmt_number(threshold)} XP")
    lines.append(f"\nУровень {len(levels)}+ — каждые 5 000 XP после {fmt_number(levels[-1])}")
    return "\n".join(lines)


async def callback_pm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()

    action = (query.data or "").split(":")[1] if query.data else ""
    u = query.from_user
    if not u:
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    month, year = now_msk.month, now_msk.year

    if action == "refresh":
        await query.message.edit_text(
            msg.get(msg.PM_WELCOME), reply_markup=_PM_KEYBOARD, parse_mode="HTML"
        )
        return

    if action == "stats":
        db.upsert_user(u.id, u.username, u.first_name, u.last_name)
        user_data = {
            "user_id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
        }
        await query.message.reply_text(_build_stats_text(u.id, user_data), parse_mode="HTML")
        return

    if action == "topsteps":
        leaderboard = build_activity_leaderboard("steps", month, year)
        text = (
            f"{msg.get(msg.TOP_HEADER)}\n"
            f"🚶 Шаги — {_month_label(month, year)}\n\n"
            f"{leaderboard}"
        )
        await query.message.reply_text(text, parse_mode="HTML")
        return

    if action == "topexercise":
        leaderboard = build_activity_leaderboard("exercise", month, year)
        text = (
            f"{msg.get(msg.TOP_HEADER)}\n"
            f"⚡ Зарядка — {_month_label(month, year)}\n\n"
            f"{leaderboard}"
        )
        await query.message.reply_text(text, parse_mode="HTML")
        return

    if action == "topsalo":
        leaderboard = build_salo_leaderboard_text(month, year)
        if leaderboard == "Пока никто не сбрасывал сало. Шевелитесь, бойцы.":
            await query.message.reply_text(leaderboard)
            return
        text = (
            f"{msg.get(msg.TOP_HEADER)}\n"
            f"🥓 Сало — {_month_label(month, year)}\n\n"
            f"{leaderboard}"
        )
        await query.message.reply_text(text, parse_mode="HTML")
        return

    if action == "topxp":
        rows = db.get_xp_leaderboard()
        if not rows:
            await query.message.reply_text("Пока никто не набрал XP. Шагайте, бойцы.")
            return
        lines = []
        for r in rows:
            name = get_display_name(r["user"])
            xp_val = r["total_xp"]
            level = db.get_level(xp_val)
            lines.append(f"{name} — {fmt_number(xp_val)} XP (Уровень {level})")
        text = f"{msg.get(msg.TOP_XP_HEADER)}\n\n" + "\n".join(lines)
        await query.message.reply_text(text, parse_mode="HTML")
        return

    if action == "topwriters":
        rows = db.get_writing_leaderboard()
        if not rows:
            await query.message.reply_text("Пока никто не писал посты. Графоманов нет — подполье молчит.")
            return
        _medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, r in enumerate(rows):
            name = get_display_name(r["user"])
            prefix = _medals[i] if i < 3 else f"{i + 1}."
            streak = r["current_streak"]
            best = r["max_streak_this_month"]
            if i < 3:
                lines.append(f"{prefix} <b>{name}</b> — {streak} дн. подряд (рекорд: {best})")
            else:
                lines.append(f"{prefix} {name} — {streak} дн. подряд (рекорд: {best})")
        text = (
            f"{msg.get(msg.TOP_HEADER)}\n"
            f"✍️ Графоманы — {_month_label(month, year)}\n\n"
            + "\n".join(lines)
        )
        await query.message.reply_text(text, parse_mode="HTML")
        return

    if action == "levels":
        await query.message.reply_text(_build_levels_text(), parse_mode="HTML")
        return

    if action == "help":
        await query.message.reply_text(msg.HELP_MAIN, parse_mode="HTML")
        return


def build_handlers():
    return [
        CommandHandler("start", cmd_start, filters=filters.ChatType.PRIVATE),
        CallbackQueryHandler(callback_pm, pattern=r"^pm:"),
    ]
