import datetime
import pytz

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
import messages as msg
from config import GROUP_ID, STEPS_THREAD_ID, EXERCISE_THREAD_ID, PINNED_STEPS_MESSAGE_ID, PINNED_EXERCISE_MESSAGE_ID
from utils import get_moscow_date

MOSCOW_TZ = pytz.timezone("Europe/Moscow")


def _has_plus_one(text: str | None) -> bool:
    return "+1" in (text or "").upper()


async def _update_pinned_leaderboard(context: ContextTypes.DEFAULT_TYPE, activity_type: str) -> None:
    """Редактирует закреплённое сообщение с актуальным лидербордом."""
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
    except Exception:
        pass


async def handle_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    chat = update.effective_chat
    print(
        f"[ACT] chat_id={chat.id if chat else None} "
        f"thread_id={message.message_thread_id} "
        f"photo={bool(message.photo)} "
        f"video={bool(message.video)} "
        f"text={repr((message.text or message.caption or '')[:80])}"
    )

    if not chat or chat.id != GROUP_ID:
        return

    thread_id = message.message_thread_id

    if thread_id == STEPS_THREAD_ID:
        activity_type = "steps"
        has_media = bool(message.photo)
        phrase_accepted = msg.STEPS_ACCEPTED
        phrase_duplicate = msg.ALREADY_SUBMITTED_STEPS
    elif thread_id == EXERCISE_THREAD_ID:
        activity_type = "exercise"
        has_media = bool(message.video)
        phrase_accepted = msg.EXERCISE_ACCEPTED
        phrase_duplicate = msg.ALREADY_SUBMITTED_EXERCISE
    else:
        return

    if not has_media:
        return

    caption = message.caption or ""
    text = message.text or ""
    if not _has_plus_one(caption) and not _has_plus_one(text):
        return

    user = update.effective_user
    if not user:
        return

    db.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    if db.is_jailed(user.id, activity_type):
        await message.reply_text(msg.get(msg.JAILED_TRY))
        return

    today = get_moscow_date()
    if db.is_activity_recorded(user.id, activity_type, today):
        await message.reply_text(msg.get(phrase_duplicate))
        return

    db.record_activity(user.id, activity_type, today)
    await message.reply_text(msg.get(phrase_accepted))

    print(f"[PINNED] activity_type={activity_type!r}  PINNED_STEPS_MESSAGE_ID={PINNED_STEPS_MESSAGE_ID}  PINNED_EXERCISE_MESSAGE_ID={PINNED_EXERCISE_MESSAGE_ID}")
    await _update_pinned_leaderboard(context, activity_type)


def build_handler() -> MessageHandler:
    return MessageHandler(
        filters.Chat(GROUP_ID) & (filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
        handle_activity,
    )
