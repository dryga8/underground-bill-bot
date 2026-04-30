import datetime
import re
import pytz

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
import messages as msg
from config import GROUP_ID, STEPS_THREAD_ID, EXERCISE_THREAD_ID, PINNED_STEPS_MESSAGE_ID, PINNED_EXERCISE_MESSAGE_ID
from utils import get_moscow_date, fmt_number, get_display_name
from handlers.common import send_level_up_notifications

MOSCOW_TZ = pytz.timezone("Europe/Moscow")
MIN_STEPS = 10_000


def _has_plus_one(text: str | None) -> bool:
    return "+1" in (text or "").upper()


def _extract_number_from_text(text: str | None) -> int | None:
    if not text:
        return None
    normalized = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    numbers = [int(m) for m in re.findall(r'\d+', normalized)]
    return max(numbers) if numbers else None


async def _update_pinned_leaderboard(context: ContextTypes.DEFAULT_TYPE, activity_type: str) -> None:
    pinned_id = PINNED_STEPS_MESSAGE_ID if activity_type == "steps" else PINNED_EXERCISE_MESSAGE_ID
    if not pinned_id:
        return

    from handlers.stats import build_activity_leaderboard
    now_msk = datetime.datetime.now(MOSCOW_TZ)
    month, year = now_msk.month, now_msk.year

    icon = "🚶" if activity_type == "steps" else "⚡"
    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
    }
    month_label = f"{month_names[month]} {year}"
    leaderboard = build_activity_leaderboard(activity_type, month, year)

    text = f"{icon} {month_label}\n\n{leaderboard}"
    try:
        await context.bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=pinned_id,
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"[PINNED_UPDATE] error: {e}")


async def _handle_steps(message, user, context) -> None:
    text = ((message.caption or "") + " " + (message.text or "")).strip() or None
    steps_count = _extract_number_from_text(text)

    if steps_count is None:
        await message.reply_text(msg.get(msg.STEPS_NOT_RECOGNIZED))
        return
    if steps_count < MIN_STEPS:
        await message.reply_text(msg.get(msg.TOO_FEW_STEPS))
        return

    db.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    if db.is_jailed(user.id, "steps"):
        await message.reply_text(msg.get(msg.JAILED_TRY))
        return

    today = get_moscow_date()
    if db.is_activity_recorded(user.id, "steps", today):
        await message.reply_text(msg.get(msg.ALREADY_SUBMITTED_STEPS))
        return

    db.record_steps(user.id, today, steps_count)

    rewards = []
    try:
        xp_earned = min(steps_count // 500, 40)
        old_xp = db.get_user_xp(user.id)
        new_xp = db.add_xp(user.id, xp_earned)
        rewards = db.check_and_award_level(user.id, old_xp, new_xp)
    except Exception as e:
        import traceback as tb
        print(f"[STEPS] ERROR in add_xp/check_and_award_level: {type(e).__name__}: {e}")
        tb.print_exc()

    try:
        db.add_total_steps(user.id, steps_count)
    except Exception as e:
        print(f"[STEPS] ERROR in add_total_steps: {type(e).__name__}: {e}")

    reply = f"Билл насчитал {fmt_number(steps_count)} шагов. " + msg.get(msg.STEPS_ACCEPTED)
    await message.reply_text(reply)

    if rewards:
        name = get_display_name({"user_id": user.id, "username": user.username,
                                  "first_name": user.first_name, "last_name": user.last_name})
        await send_level_up_notifications(context, name, rewards)

    await _update_pinned_leaderboard(context, "steps")


async def _handle_exercise(message, user, context) -> None:
    combined = (message.caption or "") + " " + (message.text or "")
    if not _has_plus_one(combined):
        return

    if message.video and message.video.duration < 60:
        await message.reply_text(msg.get(msg.TOO_SHORT_VIDEO))
        return

    db.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    if db.is_jailed(user.id, "exercise"):
        await message.reply_text(msg.get(msg.JAILED_TRY))
        return

    today = get_moscow_date()
    if db.is_activity_recorded(user.id, "exercise", today):
        await message.reply_text(msg.get(msg.ALREADY_SUBMITTED_EXERCISE))
        return

    db.record_activity(user.id, "exercise", today)
    await message.reply_text(msg.get(msg.EXERCISE_ACCEPTED))

    old_xp = db.get_user_xp(user.id)
    new_xp = db.add_xp(user.id, 10)
    rewards = db.check_and_award_level(user.id, old_xp, new_xp)
    if rewards:
        name = get_display_name({"user_id": user.id, "username": user.username,
                                  "first_name": user.first_name, "last_name": user.last_name})
        await send_level_up_notifications(context, name, rewards)

    await _update_pinned_leaderboard(context, "exercise")


async def handle_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    chat = update.effective_chat
    if not chat or chat.id != GROUP_ID:
        return

    user = update.effective_user
    if not user:
        return

    thread_id = message.message_thread_id

    if thread_id == STEPS_THREAD_ID and message.photo:
        await _handle_steps(message, user, context)
    elif thread_id == EXERCISE_THREAD_ID and message.video:
        await _handle_exercise(message, user, context)


def build_handler() -> MessageHandler:
    return MessageHandler(
        filters.Chat(GROUP_ID) & (filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
        handle_activity,
    )


def build_edited_handler() -> MessageHandler:
    return MessageHandler(
        filters.UpdateType.EDITED_MESSAGE & filters.Chat(GROUP_ID) & (filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
        handle_activity,
    )
