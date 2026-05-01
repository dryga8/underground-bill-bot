import datetime
import pytz

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
import messages as msg
from utils import get_display_name, pluralize_days, fmt_number

MOSCOW_TZ = pytz.timezone("Europe/Moscow")

_MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _month_label(month: int, year: int) -> str:
    return f"{_MONTH_NAMES[month]} {year}"


def _month_prep(month: int) -> str:
    """Название месяца в предложном падеже: 'в Январе', 'в Мае' и т.д."""
    name = _MONTH_NAMES[month]
    if name.endswith("ь") or name.endswith("й"):
        return name[:-1] + "е"
    return name + "е"


def build_activity_leaderboard(activity_type: str, month: int, year: int) -> str:
    """Отформатированный лидерборд по одной активности (без заголовка)."""
    if activity_type == "steps":
        rows = db.get_steps_leaderboard(month, year)
        rows.sort(key=lambda r: get_display_name(r["user"]).lower())
        lines = []
        for r in rows:
            name = get_display_name(r["user"])
            if db.is_jailed(r["user"]["user_id"], "steps"):
                lines.append(f"{name} — 🚫")
            else:
                lines.append(f"{name} — {pluralize_days(r['days'])} / {fmt_number(r['steps_sum'])} шагов")
        return "\n".join(lines) if lines else "Пока никто не отметился."
    else:
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

    is_real_reply = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and not message.reply_to_message.forum_topic_created
    )
    if is_real_reply:
        ru = message.reply_to_message.from_user  # type: ignore[union-attr]
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

    steps_jailed = db.is_jailed(uid, "steps")
    exercise_jailed = db.is_jailed(uid, "exercise")

    steps_days_str = "🚫" if steps_jailed else pluralize_days(stats["steps"])

    monthly_steps = db.get_monthly_steps(uid, month, year)
    total_steps = db.get_total_steps(uid)
    xp = db.get_user_xp(uid)
    level = db.get_level(xp)
    monthly_salo = db.get_monthly_salo(uid, month, year)
    total_salo = db.get_total_salo(uid)
    total_exercise_days = db.get_total_exercise_days(uid)
    food_days = db.get_food_days(uid, month, year)

    monthly_steps_str = "🚫" if steps_jailed else fmt_number(monthly_steps)
    exercise_month_str = "🚫" if exercise_jailed else pluralize_days(stats["exercise"])
    exercise_total_str = "🚫" if exercise_jailed else pluralize_days(total_exercise_days)

    rewards = db.get_user_rewards(uid)
    rewards_str = ""
    if rewards:
        titles = ", ".join(f"{r['reward']} (ур. {r['level']})" for r in rewards)
        rewards_str = f"\n🎖 Награды: {titles}"

    text = (
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
        f"⭐ XP: {fmt_number(xp)} (Уровень {level})"
        f"{rewards_str}"
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
    await message.reply_text(text, parse_mode="HTML")


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
    await message.reply_text(text, parse_mode="HTML")


async def cmd_topxp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    rows = db.get_xp_leaderboard()
    if not rows:
        await message.reply_text("Пока никто не набрал XP. Шагайте, бойцы.")
        return

    lines = []
    for r in rows:
        name = get_display_name(r["user"])
        xp = r["total_xp"]
        level = db.get_level(xp)
        lines.append(f"{name} — {fmt_number(xp)} XP (Уровень {level})")

    text = f"{msg.get(msg.TOP_XP_HEADER)}\n\n" + "\n".join(lines)
    await message.reply_text(text, parse_mode="HTML")


def build_salo_leaderboard_text(month: int, year: int) -> str:
    salo_rows = db.get_salo_leaderboard(month, year)
    food_map = db.get_food_days_leaderboard(month, year)
    print(f"[TOPSALO] food_days_data={food_map}")

    # index salo data by uid
    salo_by_uid: dict[int, dict] = {int(r["user"]["user_id"]): r for r in salo_rows}
    print(f"[TOPSALO] salo_uids={list(salo_by_uid.keys())}")

    all_uids = set(salo_by_uid.keys()) | set(food_map.keys())
    if not all_uids:
        return "Пока никто не сбрасывал сало. Шевелитесь, бойцы."

    combined = []
    for uid in all_uids:
        if uid in salo_by_uid:
            r = salo_by_uid[uid]
            user = r["user"]
            monthly_grams = r["monthly_grams"]
            total_grams = r["total_grams"]
        else:
            user = db.get_user_by_id(uid)
            if not user:
                continue
            monthly_grams = 0
            total_grams = db.get_total_salo(uid)
        food_days = food_map.get(uid, 0)
        print(f"[TOPSALO] uid={uid} monthly_grams={monthly_grams} food_days={food_days}")
        combined.append({
            "name": get_display_name(user),
            "monthly_grams": monthly_grams,
            "total_grams": total_grams,
            "food_days": food_days,
        })

    combined.sort(key=lambda r: (-r["monthly_grams"], r["name"].lower()))
    lines = [
        f"{r['name']} — {r['monthly_grams']} г за месяц"
        f" / {r['total_grams']} г всего / 🍽 {r['food_days']} дней еды"
        for r in combined
    ]
    return "\n".join(lines)


async def cmd_topsalo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    month, year = now_msk.month, now_msk.year

    leaderboard = build_salo_leaderboard_text(month, year)
    if leaderboard == "Пока никто не сбрасывал сало. Шевелитесь, бойцы.":
        await message.reply_text(leaderboard)
        return

    text = (
        f"{msg.get(msg.TOP_HEADER)}\n"
        f"🥓 Сало — {_month_label(month, year)}\n\n"
        f"{leaderboard}"
    )
    await message.reply_text(text, parse_mode="HTML")


def build_handlers():
    return [
        CommandHandler("stats", cmd_stats),
        CommandHandler("topsteps", cmd_topsteps),
        CommandHandler("topexercise", cmd_topexercise),
        CommandHandler("topxp", cmd_topxp),
        CommandHandler("topsalo", cmd_topsalo),
    ]
