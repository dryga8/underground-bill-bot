import datetime
import logging
import traceback
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes

import database as db
import messages as msg
from config import BOT_TOKEN, GROUP_ID
from handlers import activity, report, stats, admin, welcome, scheduler, news
from utils import get_display_name

MOSCOW_TZ = pytz.timezone("Europe/Moscow")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Необработанное исключение в хендлере:", exc_info=context.error)
    traceback.print_exc()


_HELP_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🚶 Марафон шагов", callback_data="help:steps"),
        InlineKeyboardButton("⚡ Марафон зарядки", callback_data="help:exercise"),
    ],
    [
        InlineKeyboardButton("🥓 Марафон сала", callback_data="help:salo"),
        InlineKeyboardButton("⭐ XP и уровни", callback_data="help:xp"),
    ],
    [InlineKeyboardButton("📋 Команды", callback_data="help:commands")],
])

_HELP_SECTIONS: dict[str, str] = {
    "steps":    msg.HELP_STEPS,
    "exercise": msg.HELP_EXERCISE,
    "salo":     msg.HELP_SALO,
    "xp":       msg.HELP_XP,
    "commands": msg.HELP_COMMANDS,
}

_HELP_DELETE_SECONDS = 900


async def _delete_msg_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
    except Exception:
        pass


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    sent = await message.reply_text(msg.HELP_MAIN, parse_mode="HTML", reply_markup=_HELP_KEYBOARD)
    context.job_queue.run_once(
        _delete_msg_job,
        when=_HELP_DELETE_SECONDS,
        data={"chat_id": sent.chat_id, "message_id": sent.message_id},
    )


async def callback_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    section = (query.data or "").split(":")[1] if query.data else ""
    text = _HELP_SECTIONS.get(section)
    if not text or not query.message:
        return
    sent = await query.message.reply_text(text, parse_mode="HTML")
    context.job_queue.run_once(
        _delete_msg_job,
        when=_HELP_DELETE_SECONDS,
        data={"chat_id": sent.chat_id, "message_id": sent.message_id},
    )


async def cmd_admin(update: Update, _) -> None:
    message = update.effective_message
    if not message:
        return
    chat = update.effective_chat
    if not chat or chat.id != GROUP_ID:
        return
    admins = db.get_all_admins()
    if not admins:
        await message.reply_text("Командование недоступно. Билл сам разберётся.", parse_mode="HTML")
        return
    mentions = " ".join(
        f'<a href="tg://user?id={a["user_id"]}">{get_display_name(a)}</a>'
        for a in admins
    )
    await message.reply_text(f"{msg.get(msg.ADMIN_CALL)}\n\n{mentions}", parse_mode="HTML")


def main() -> None:
    import database as db
    db.cleanup_old_rewards()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(callback_help, pattern=r"^help:"))

    app.add_handler(activity.build_handler())
    app.add_handler(activity.build_edited_handler())

    for handler in report.build_handlers():
        app.add_handler(handler)

    for handler in stats.build_handlers():
        app.add_handler(handler)

    for handler in admin.build_handlers():
        app.add_handler(handler)

    app.add_handler(welcome.build_handler())

    app.add_error_handler(error_handler)

    reset_time = datetime.time(hour=0, minute=0, second=0, tzinfo=MOSCOW_TZ)
    app.job_queue.run_monthly(scheduler.monthly_reset, when=reset_time, day=1)

    for hour in (8, 14, 20):
        app.job_queue.run_daily(
            scheduler.send_steps_reminder,
            time=datetime.time(hour=hour, minute=0, second=0, tzinfo=MOSCOW_TZ),
        )
    for hour in (9, 15, 21):
        app.job_queue.run_daily(
            scheduler.send_exercise_reminder,
            time=datetime.time(hour=hour, minute=0, second=0, tzinfo=MOSCOW_TZ),
        )
    for hour in (10, 16, 22):
        app.job_queue.run_daily(
            scheduler.send_salo_reminder,
            time=datetime.time(hour=hour, minute=0, second=0, tzinfo=MOSCOW_TZ),
        )

    app.job_queue.run_daily(
        scheduler.send_daily_xp_leaderboard,
        time=datetime.time(hour=7, minute=30, second=0, tzinfo=MOSCOW_TZ),
    )

    for hour in (9, 14, 19):
        app.job_queue.run_daily(
            news.send_news,
            time=datetime.time(hour=hour, minute=0, second=0, tzinfo=MOSCOW_TZ),
        )

    logger.info("Подпольщик Билл выходит на связь...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
