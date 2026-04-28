import datetime
import pytz

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
import messages as msg
from config import OWNER_ID
from database import get_level
from utils import get_display_name

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

    if xp_amount <= 0:
        await message.reply_text("XP должен быть положительным числом.")
        return

    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(f"Боец @{username} в архивах не найден.")
        return

    new_total = db.add_xp(target["user_id"], xp_amount)
    level = db.get_level(new_total)
    display = get_display_name(target)

    await message.reply_text(
        f"{msg.get(msg.XP_ADDED)}\n\n"
        f"<b>{display}</b> +{xp_amount} XP → {new_total} XP (Уровень {level}).",
        parse_mode="HTML",
    )


def build_handlers():
    return [
        CommandHandler("addadmin", cmd_addadmin),
        CommandHandler("pardon", cmd_pardon),
        CommandHandler("reset", cmd_reset),
        CommandHandler("adddays", cmd_adddays),
        CommandHandler("removedays", cmd_removedays),
        CommandHandler("addxp", cmd_addxp),
    ]
