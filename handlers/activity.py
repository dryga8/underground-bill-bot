import datetime
import re
import pytz

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
import messages as msg
from config import GROUP_ID, STEPS_THREAD_ID, EXERCISE_THREAD_ID, PINNED_STEPS_MESSAGE_ID, PINNED_EXERCISE_MESSAGE_ID
from utils import get_moscow_date

MOSCOW_TZ = pytz.timezone("Europe/Moscow")
MIN_STEPS = 10_000


def _has_plus_one(text: str | None) -> bool:
    return "+1" in (text or "").upper()


def _parse_steps_count(text: str) -> int | None:
    """Ищет наибольшее число в тексте.
    Принимает: '10000', '10 000', '10 000', '10,000', '10.000'.
    Не путает '+1' с числом шагов.
    """
    numbers = []
    # Числа с разделителями тысяч: '10 000', '10,000', '10.000'
    for m in re.finditer(r'\b\d{1,3}(?:[ ,.\u00a0]\d{3})+\b', text):
        digits = re.sub(r'\D', '', m.group())
        if digits:
            numbers.append(int(digits))
    # Числа без разделителей от 4 цифр: '10000', '15234'
    for m in re.finditer(r'\b\d{4,}\b', text):
        numbers.append(int(m.group()))
    return max(numbers) if numbers else None


async def _update_pinned_leaderboard(context: ContextTypes.DEFAULT_TYPE, activity_type: str) -> None:
    print(f"[PINNED_UPDATE] activity_type={activity_type!r}  PINNED_STEPS_MESSAGE_ID={PINNED_STEPS_MESSAGE_ID}  PINNED_EXERCISE_MESSAGE_ID={PINNED_EXERCISE_MESSAGE_ID}")

    pinned_id = PINNED_STEPS_MESSAGE_ID if activity_type == "steps" else PINNED_EXERCISE_MESSAGE_ID
    print(f"[PINNED_UPDATE] выбран pinned_id={pinned_id}")

    if not pinned_id:
        print("[PINNED_UPDATE] pinned_id=0, пропускаем")
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
    print(f"[PINNED_UPDATE] вызываем edit_message_text chat_id={GROUP_ID}  message_id={pinned_id}")
    try:
        await context.bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=pinned_id,
            text=text,
            parse_mode="HTML",
        )
        print("[PINNED_UPDATE] успешно обновлено")
    except Exception as e:
        print(f"[PINNED_UPDATE] ошибка: {e}")


async def _handle_steps(message, user, context) -> None:
    combined = (message.caption or "") + " " + (message.text or "")
    steps_count = _parse_steps_count(combined)

    print(f"[STEPS] user={user.id} combined={repr(combined[:80])} steps_count={steps_count}")

    if steps_count is None:
        print("[STEPS] steps_count=None — число шагов не найдено, выходим")
        return

    print(f"[STEPS] steps_count={steps_count} MIN_STEPS={MIN_STEPS} достаточно={steps_count >= MIN_STEPS}")

    try:
        db.upsert_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
    except Exception as e:
        print(f"[STEPS] ОШИБКА upsert_user: {e}")
        raise

    try:
        jailed = db.is_jailed(user.id, "steps")
    except Exception as e:
        print(f"[STEPS] ОШИБКА is_jailed: {e}")
        raise

    if jailed:
        print(f"[STEPS] user {user.id} в карцере")
        await message.reply_text(msg.get(msg.JAILED_TRY))
        return

    today = get_moscow_date()

    try:
        already = db.is_activity_recorded(user.id, "steps", today)
    except Exception as e:
        print(f"[STEPS] ОШИБКА is_activity_recorded: {e}")
        raise

    if already:
        print(f"[STEPS] user {user.id} уже записан за {today}")
        await message.reply_text(msg.get(msg.ALREADY_SUBMITTED_STEPS))
        return

    if steps_count < MIN_STEPS:
        print(f"[STEPS] steps_count={steps_count} < MIN_STEPS={MIN_STEPS} — мало шагов")
        await message.reply_text(msg.get(msg.TOO_FEW_STEPS))
        return

    print(f"[STEPS] записываем активность: user={user.id} date={today} steps={steps_count}")

    try:
        db.record_steps(user.id, today, steps_count)
    except Exception as e:
        print(f"[STEPS] ОШИБКА record_steps: {e}")
        raise

    print(f"[STEPS] запись успешна, начисляем XP")

    try:
        xp_earned = steps_count // 500
        db.add_xp(user.id, xp_earned)
        db.add_total_steps(user.id, steps_count)
    except Exception as e:
        print(f"[STEPS] ОШИБКА add_xp/add_total_steps (запись в activities уже сохранена): {e}")

    await message.reply_text(msg.get(msg.STEPS_ACCEPTED))

    print(f"[PINNED] activity_type='steps'  PINNED_STEPS_MESSAGE_ID={PINNED_STEPS_MESSAGE_ID}")
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
