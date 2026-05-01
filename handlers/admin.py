import datetime
import pytz

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, filters

import database as db
import messages as msg
from config import OWNER_ID, PINNED_SALO_MESSAGE_ID, GROUP_ID
from database import get_level
from utils import get_display_name, get_moscow_date, fmt_number
from handlers.common import send_level_up_notifications

MOSCOW_TZ = pytz.timezone("Europe/Moscow")


def _is_privileged(user_id: int) -> bool:
    return user_id == OWNER_ID or db.is_admin(user_id)


async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or caller.id != OWNER_ID:
        await message.reply_text("Только хозяйка бота может назначать админов.")
        return

    if not context.args:
        await message.reply_text("Укажи username: /addadmin @username")
        return

    username = context.args[0].lstrip("@")
    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(
            f"Боец @{username} в архивах не найден. "
            "Пусть сначала отметится в чате."
        )
        return

    db.add_admin(target["user_id"], caller.id)
    display = get_display_name(target)
    await message.reply_text(f"<b>{display}</b> теперь админ Сопротивления.", parse_mode="HTML")


async def cmd_pardon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or not _is_privileged(caller.id):
        await message.reply_text("Недостаточно полномочий. Это для командования.")
        return

    if not context.args:
        await message.reply_text("Укажи username: /pardon @username")
        return

    username = context.args[0].lstrip("@")
    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(f"Боец @{username} в архивах не найден.")
        return

    db.pardon_user(target["user_id"])
    display = get_display_name(target)

    chat = update.effective_chat
    send_kwargs = {
        "chat_id": chat.id,
        "text": f"{msg.get(msg.JAIL_LIFTED)}\n\n<b>{display}</b> помилован.",
        "parse_mode": "HTML",
    }
    if message.message_thread_id:
        send_kwargs["message_thread_id"] = message.message_thread_id

    await context.bot.send_message(**send_kwargs)


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or not _is_privileged(caller.id):
        await message.reply_text("Недостаточно полномочий. Это для командования.")
        return

    db.pardon_all()

    chat = update.effective_chat
    send_kwargs = {
        "chat_id": chat.id,
        "text": msg.RESET_ANNOUNCEMENT,
        "parse_mode": "HTML",
    }
    if message.message_thread_id:
        send_kwargs["message_thread_id"] = message.message_thread_id

    await context.bot.send_message(**send_kwargs)


def _parse_days_args(args: list[str]) -> tuple[str, str, int] | None:
    """Парсит [@username, activity_type, days]. Возвращает None при ошибке."""
    if len(args) < 3:
        return None
    username = args[0].lstrip("@")
    activity_type = args[1].lower()
    if activity_type not in ("steps", "exercise"):
        return None
    try:
        days = int(args[2])
    except ValueError:
        return None
    if days <= 0:
        return None
    return username, activity_type, days


_ACTIVITY_LABEL = {"steps": "шаги", "exercise": "зарядка"}


async def cmd_adddays(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or not _is_privileged(caller.id):
        await message.reply_text("Недостаточно полномочий. Это для командования.")
        return

    parsed = _parse_days_args(context.args or [])
    if not parsed:
        await message.reply_text("Формат: /adddays @username steps 3\nТипы: steps, exercise")
        return

    username, activity_type, days = parsed
    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(f"Боец @{username} в архивах не найден.")
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    added = db.add_days(target["user_id"], activity_type, days, now_msk.month, now_msk.year)
    display = get_display_name(target)
    label = _ACTIVITY_LABEL[activity_type]

    await message.reply_text(
        f"{msg.get(msg.DAYS_ADDED)}\n\n"
        f"<b>{display}</b> — добавлено {added} дн. ({label}).",
        parse_mode="HTML",
    )


async def cmd_removedays(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or not _is_privileged(caller.id):
        await message.reply_text("Недостаточно полномочий. Это для командования.")
        return

    parsed = _parse_days_args(context.args or [])
    if not parsed:
        await message.reply_text("Формат: /removedays @username steps 3\nТипы: steps, exercise")
        return

    username, activity_type, days = parsed
    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(f"Боец @{username} в архивах не найден.")
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    removed = db.remove_days(target["user_id"], activity_type, days, now_msk.month, now_msk.year)
    display = get_display_name(target)
    label = _ACTIVITY_LABEL[activity_type]

    await message.reply_text(
        f"{msg.get(msg.DAYS_REMOVED)}\n\n"
        f"<b>{display}</b> — удалено {removed} дн. ({label}).",
        parse_mode="HTML",
    )


async def cmd_addxp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or not _is_privileged(caller.id):
        await message.reply_text("Недостаточно полномочий. Это для командования.")
        return

    if not context.args or len(context.args) < 2:
        await message.reply_text("Формат: /addxp @username 100")
        return

    username = context.args[0].lstrip("@")
    try:
        xp_amount = int(context.args[1])
    except ValueError:
        await message.reply_text("XP должен быть числом.")
        return

    if xp_amount == 0:
        await message.reply_text("XP должен быть ненулевым числом.")
        return

    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(f"Боец @{username} в архивах не найден.")
        return

    old_xp = db.get_user_xp(target["user_id"])
    new_total = db.add_xp(target["user_id"], xp_amount)
    level = db.get_level(new_total)
    display = get_display_name(target)
    sign = "+" if xp_amount > 0 else ""

    await message.reply_text(
        f"{msg.get(msg.XP_ADDED)}\n\n"
        f"<b>{display}</b> {sign}{xp_amount} XP → {new_total} XP (Уровень {level}).",
        parse_mode="HTML",
    )

    if xp_amount > 0:
        rewards = db.check_and_award_level(target["user_id"], old_xp, new_total)
        if rewards:
            await send_level_up_notifications(context, display, rewards)


async def cmd_addsteps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or not _is_privileged(caller.id):
        await message.reply_text("Недостаточно полномочий. Это для командования.")
        return

    if not context.args or len(context.args) < 2:
        await message.reply_text("Формат: /addsteps @username 12500")
        return

    username = context.args[0].lstrip("@")
    try:
        steps_count = int(context.args[1])
    except ValueError:
        await message.reply_text("Количество шагов должно быть числом.")
        return

    if steps_count <= 0:
        await message.reply_text("Количество шагов должно быть положительным числом.")
        return

    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(f"Боец @{username} в архивах не найден.")
        return

    today = get_moscow_date()
    db.set_steps_for_date(target["user_id"], today, steps_count)

    xp_earned = min(steps_count // 500, 40)
    old_xp = db.get_user_xp(target["user_id"])
    new_total = db.add_xp(target["user_id"], xp_earned)
    level = db.get_level(new_total)
    display = get_display_name(target)

    rewards = db.check_and_award_level(target["user_id"], old_xp, new_total)

    try:
        db.add_total_steps(target["user_id"], steps_count)
    except Exception as e:
        print(f"[ADDSTEPS] ERROR in add_total_steps: {type(e).__name__}: {e}")

    await message.reply_text(
        f"{msg.get(msg.DAYS_ADDED)}\n\n"
        f"<b>{display}</b> — {fmt_number(steps_count)} шагов за сегодня. "
        f"+{xp_earned} XP → {fmt_number(new_total)} XP (Уровень {level}).",
        parse_mode="HTML",
    )

    if rewards:
        await send_level_up_notifications(context, display, rewards)


async def cmd_addsalo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or not _is_privileged(caller.id):
        await message.reply_text("Недостаточно полномочий. Это для командования.")
        return

    if not context.args or len(context.args) < 2:
        await message.reply_text("Формат: /addsalo @username 500")
        return

    username = context.args[0].lstrip("@")
    try:
        grams = int(context.args[1])
    except ValueError:
        await message.reply_text("Граммы должны быть числом.")
        return

    if grams <= 0:
        await message.reply_text("Количество грамм должно быть положительным.")
        return

    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(f"Боец @{username} в архивах не найден.")
        return

    if db.is_jailed(target["user_id"], "salo"):
        await message.reply_text(
            f"<b>{get_display_name(target)}</b> в карцере по марафону сала. "
            "Записи не принимаются до конца месяца.",
            parse_mode="HTML",
        )
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    db.add_salo(target["user_id"], grams, now_msk.month, now_msk.year)

    xp_earned = grams // 20
    old_xp = db.get_user_xp(target["user_id"])
    if xp_earned > 0:
        new_total = db.add_xp(target["user_id"], xp_earned)
        rewards = db.check_and_award_level(target["user_id"], old_xp, new_total)
    else:
        new_total = old_xp
        rewards = []
    level = get_level(new_total)
    display = get_display_name(target)

    await message.reply_text(
        f"{msg.get(msg.SALO_ADDED).format(grams=grams, xp=xp_earned)}\n\n"
        f"<b>{display}</b> — итого {fmt_number(new_total)} XP (Уровень {level}).",
        parse_mode="HTML",
    )

    if rewards:
        await send_level_up_notifications(context, display, rewards)

    if PINNED_SALO_MESSAGE_ID:
        from handlers.stats import build_salo_leaderboard_text
        _month_names = {
            1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
            5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
            9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
        }
        month_label = f"{_month_names[now_msk.month]} {now_msk.year}"
        leaderboard = build_salo_leaderboard_text(now_msk.month, now_msk.year)
        pinned_text = f"🥓 {month_label}\n\n{leaderboard}"
        try:
            await context.bot.edit_message_text(
                chat_id=GROUP_ID,
                message_id=PINNED_SALO_MESSAGE_ID,
                text=pinned_text,
                parse_mode="HTML",
            )
            print(f"[PINNED_SALO] updated message_id={PINNED_SALO_MESSAGE_ID}")
        except Exception as e:
            print(f"[PINNED_SALO] error: {e}")


async def cmd_addwriting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or not _is_privileged(caller.id):
        await message.reply_text("Недостаточно полномочий. Это для командования.")
        return

    if not context.args or len(context.args) < 2:
        await message.reply_text("Формат: /addwriting @username 3 (или -2 для уменьшения)")
        return

    username = context.args[0].lstrip("@")
    try:
        delta = int(context.args[1])
    except ValueError:
        await message.reply_text("Количество дней должно быть числом.")
        return

    if delta == 0:
        await message.reply_text("Укажи ненулевое число дней.")
        return

    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(f"Боец @{username} в архивах не найден.")
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    result = db.adjust_writing_streak(target["user_id"], delta, now_msk.month, now_msk.year)
    display = get_display_name(target)
    sign = "+" if delta > 0 else ""

    await message.reply_text(
        f"{msg.get(msg.DAYS_ADDED)}\n\n"
        f"<b>{display}</b> — {sign}{delta} к стрику.\n"
        f"Текущий стрик: {result['current_streak']} дн., рекорд месяца: {result['max_streak_this_month']} дн.",
        parse_mode="HTML",
    )


async def cmd_fullreset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    caller = update.effective_user
    if not caller or caller.id != OWNER_ID:
        await message.reply_text("Эта команда — только для хозяйки. Билл не тронет.")
        return

    db.full_reset()
    await message.reply_text(
        "💥 Полный сброс выполнен. Все таблицы очищены: пользователи, активности, XP, сало, карцеры, жалобы, награды, админы. Начинаем с нуля."
    )


def build_handlers():
    _group = filters.Chat(GROUP_ID)
    return [
        CommandHandler("addadmin", cmd_addadmin, filters=_group),
        CommandHandler("pardon", cmd_pardon, filters=_group),
        CommandHandler("reset", cmd_reset, filters=_group),
        CommandHandler("adddays", cmd_adddays, filters=_group),
        CommandHandler("removedays", cmd_removedays, filters=_group),
        CommandHandler("addxp", cmd_addxp, filters=_group),
        CommandHandler("addsteps", cmd_addsteps, filters=_group),
        CommandHandler("addsalo", cmd_addsalo, filters=_group),
        CommandHandler("addwriting", cmd_addwriting, filters=_group),
        CommandHandler("fullreset", cmd_fullreset, filters=_group),
    ]
