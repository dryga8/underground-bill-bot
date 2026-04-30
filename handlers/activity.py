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
    print(f"[PINNED_UPDATE] activity_type={activity_type!r}  PINNED_STEPS_MESSAGE_ID={PINNED_STEPS_MESSAGE_ID}  PINNED_EXERCISE_MESSAGE_ID={PINNED_EXERCISE_MESSAGE_ID}")

    pinned_id = PINNED_STEPS_MESSAGE_ID if activity_type == "steps" else PINNED_EXERCISE_MESSAGE_ID
    print(f"[PINNED_UPDATE] vyibran pinned_id={pinned_id}")

    if not pinned_id:
        print("[PINNED_UPDATE] pinned_id=0, propuskaem")
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
    print(f"[PINNED_UPDATE] edit_message_text chat_id={GROUP_ID}  message_id={pinned_id}")
    try:
        await context.bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=pinned_id,
            text=text,
            parse_mode="HTML",
        )
        print("[PINNED_UPDATE] success")
    except Exception as e:
        print(f"[PINNED_UPDATE] error: {e}")


async def _handle_steps(message, user, context) -> None:
    text = ((message.caption or "") + " " + (message.text or "")).strip() or None
    steps_count = _extract_number_from_text(text)
    print(f"[STEPS] user={user.id} extracted steps_count={steps_count} from text={repr(text)}")

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
        print(f"[STEPS] user {user.id} is jailed")
        await message.reply_text(msg.get(msg.JAILED_TRY))
        return

    today = get_moscow_date()
    if db.is_activity_recorded(user.id, "steps", today):
        print(f"[STEPS] user {user.id} already recorded for {today}")
        await message.reply_text(msg.get(msg.ALREADY_SUBMITTED_STEPS))
        return

    print(f"[STEPS] recording: user={user.id} date={today} steps={steps_count}")
    db.record_steps(user.id, today, steps_count)
    print(f"[STEPS] record_steps done, now calling add_xp / add_total_steps")

    rewards = []
    try:
        xp_earned = min(steps_count // 500, 40)
        print(f"[STEPS] calling add_xp(user_id={user.id}, xp={xp_earned})")
        old_xp = db.get_user_xp(user.id)
        new_xp = db.add_xp(user.id, xp_earned)
        print(f"[STEPS] calling add_total_steps(user_id={user.id}, steps={steps_count})")
        db.add_total_steps(user.id, steps_count)
        print(f"[STEPS] add_xp and add_total_steps completed successfully")
        print(f"[STEPS] calling check_and_award_level: user={user.id} old_xp={old_xp} new_xp={new_xp}")
        rewards = db.check_and_award_level(user.id, old_xp, new_xp)
        print(f"[STEPS] check_and_award_level returned: {rewards}")
    except Exception as e:
        import traceback as tb
        print(f"[STEPS] ERROR in add_xp/add_total_steps: {type(e).__name__}: {e}")
        tb.print_exc()

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

    print(f"[PINNED] activity_type='exercise'  PINNED_EXERCISE_MESSAGE_ID={PINNED_EXERCISE_MESSAGE_ID}")
    await _update_pinned_leaderboard(context, "exercise")


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
