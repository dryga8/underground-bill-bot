import datetime
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
import messages as msg
from config import GROUP_ID, STEPS_THREAD_ID, EXERCISE_THREAD_ID
from utils import get_moscow_date, get_month_end, get_display_name

MOSCOW_TZ = pytz.timezone("Europe/Moscow")
VOTES_REQUIRED = 5

# Для ссылки на сообщение: -1001234567890 → 1234567890
_CHAT_ID_FOR_LINK = str(abs(GROUP_ID))[3:]


def _build_keyboard(report_id: int, yes_votes: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Да, обманул ({yes_votes})", callback_data=f"vote:yes:{report_id}"),
        InlineKeyboardButton("❌ Нет, всё чисто", callback_data=f"vote:no:{report_id}"),
    ]])


def _thread_to_activity_type(thread_id: int | None) -> str:
    if thread_id == EXERCISE_THREAD_ID:
        return "exercise"
    return "steps"


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    chat = update.effective_chat
    if not chat or chat.id != GROUP_ID:
        return

    reporter = update.effective_user
    if not reporter:
        return

    if not message.reply_to_message:
        await message.reply_text("Жалоба подаётся только в ответ на сообщение. Ответь на него командой /report.")
        return

    replied = message.reply_to_message
    reported_user = replied.from_user

    if not reported_user:
        await message.reply_text("Не могу определить автора сообщения.")
        return

    if reported_user.id == reporter.id:
        await message.reply_text("На себя жаловаться? Оригинально, но бессмысленно.")
        return

    if reported_user.is_bot:
        await message.reply_text("На бота жаловаться? Билл — не предатель.")
        return

    today_msk = get_moscow_date()
    msg_date = replied.date.astimezone(MOSCOW_TZ).date()
    if msg_date != today_msk:
        await message.reply_text("Жалобу можно подать только в тот же день что и исходное сообщение.")
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    if not db.is_user_active_this_month(reporter.id, now_msk.month, now_msk.year):
        await message.reply_text("Жаловаться могут только активные бойцы. Запишись сам — потом суди других.")
        return

    if db.has_open_report_for_message(chat.id, replied.message_id):
        await message.reply_text("По этому сообщению уже открыто голосование. Подожди результата.")
        return

    db.upsert_user(
        user_id=reporter.id,
        username=reporter.username,
        first_name=reporter.first_name,
        last_name=reporter.last_name,
    )
    db.upsert_user(
        user_id=reported_user.id,
        username=reported_user.username,
        first_name=reported_user.first_name,
        last_name=reported_user.last_name,
    )

    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
    report_id = db.create_report(
        reporter_id=reporter.id,
        reported_user_id=reported_user.id,
        chat_id=chat.id,
        message_id=replied.message_id,
        thread_id=message.message_thread_id,
        expires_at=expires_at,
    )

    reported_name = get_display_name({
        "first_name": reported_user.first_name,
        "last_name": reported_user.last_name,
        "username": reported_user.username,
    })
    reporter_name = get_display_name({
        "first_name": reporter.first_name,
        "last_name": reporter.last_name,
        "username": reporter.username,
    })

    msg_link = f"https://t.me/c/{_CHAT_ID_FOR_LINK}/{replied.message_id}"

    vote_text = (
        f"{msg.get(msg.REPORT_OPENED)}\n\n"
        f"Обвиняемый: <b>{reported_name}</b>\n"
        f"Жалобу подал: {reporter_name}\n"
        f"Спорное сообщение: <a href=\"{msg_link}\">ссылка</a>\n\n"
        f"Нужно {VOTES_REQUIRED} голосов «Да» за 24 часа."
    )

    vote_msg = await message.reply_text(
        vote_text,
        parse_mode="HTML",
        reply_markup=_build_keyboard(report_id, 0),
    )

    db.set_report_vote_message(report_id, vote_msg.message_id)

    context.job_queue.run_once(
        _close_expired_report,
        when=datetime.timedelta(hours=24),
        data={
            "report_id": report_id,
            "chat_id": chat.id,
            "vote_message_id": vote_msg.message_id,
            "thread_id": message.message_thread_id,
        },
        name=f"report_{report_id}",
    )


async def _close_expired_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    report_id = data["report_id"]
    chat_id = data["chat_id"]
    vote_message_id = data["vote_message_id"]
    thread_id = data.get("thread_id")

    report = db.get_report(report_id)
    if not report or report["status"] != "open":
        return

    db.close_report(report_id, "cleared")

    expired_text = (
        f"{msg.get(msg.VOTE_EXPIRED)}\n\n"
        f"Итог голосования: {report['yes_votes']} из {VOTES_REQUIRED} голосов."
    )
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=vote_message_id,
            text=expired_text,
            parse_mode="HTML",
        )
    except Exception:
        pass

    send_kwargs = {"chat_id": chat_id, "text": expired_text, "parse_mode": "HTML"}
    if thread_id:
        send_kwargs["message_thread_id"] = thread_id
    try:
        await context.bot.send_message(**send_kwargs)
    except Exception:
        pass


async def callback_vote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    parts = (query.data or "").split(":")
    if len(parts) != 3:
        await query.answer()
        return

    _, vote_type, report_id_str = parts
    report_id = int(report_id_str)
    voter = query.from_user

    if vote_type == "no":
        await query.answer("Твой голос учтён.")
        return

    report = db.get_report(report_id)
    if not report or report["status"] != "open":
        await query.answer("Голосование уже завершено.", show_alert=True)
        return

    if voter.id == report["reported_user_id"]:
        await query.answer("За себя не голосуют. Даже в трибунале.", show_alert=True)
        return

    if db.has_voted(report_id, voter.id):
        await query.answer("Ты уже голосовал по этому делу.", show_alert=True)
        return

    now_msk = datetime.datetime.now(MOSCOW_TZ)
    if not db.is_user_active_this_month(voter.id, now_msk.month, now_msk.year):
        await query.answer("Голосовать могут только активные бойцы Сопротивления.", show_alert=True)
        return

    db.upsert_user(
        user_id=voter.id,
        username=voter.username,
        first_name=voter.first_name,
        last_name=voter.last_name,
    )

    new_count = db.add_vote(report_id, voter.id)

    if new_count >= VOTES_REQUIRED:
        reported_user_id = report["reported_user_id"]
        today_msk = get_moscow_date()
        jail_until = get_month_end(today_msk.year, today_msk.month)
        activity_type = _thread_to_activity_type(report.get("thread_id"))
        db.jail_user(reported_user_id, jail_until, activity_type)
        db.close_report(report_id, "jailed")

        reported_user_data = db.get_user_by_id(reported_user_id)
        reported_name = get_display_name(reported_user_data) if reported_user_data else "Боец"

        verdict_text = (
            f"{msg.get(msg.JAIL_VERDICT)}\n\n"
            f"<b>{reported_name}</b> отправлен в карцер до конца месяца.\n"
            f"Голосов: {new_count}/{VOTES_REQUIRED}."
        )
        await query.answer("Вердикт вынесен.")
        try:
            await query.edit_message_text(verdict_text, parse_mode="HTML")
        except Exception:
            pass

        send_kwargs = {
            "chat_id": report["chat_id"],
            "text": verdict_text,
            "parse_mode": "HTML",
        }
        if report.get("thread_id"):
            send_kwargs["message_thread_id"] = report["thread_id"]
        try:
            await context.bot.send_message(**send_kwargs)
        except Exception:
            pass
    else:
        await query.answer(f"Голос принят. Сейчас: {new_count}/{VOTES_REQUIRED}.")
        try:
            await query.edit_message_reply_markup(
                reply_markup=_build_keyboard(report_id, new_count)
            )
        except Exception:
            pass


def build_handlers():
    return [
        CommandHandler("report", cmd_report),
        CallbackQueryHandler(callback_vote, pattern=r"^vote:(yes|no):\d+$"),
    ]
