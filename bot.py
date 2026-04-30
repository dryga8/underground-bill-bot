import datetime
import logging
import traceback
import pytz

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import messages as msg
from config import BOT_TOKEN, GROUP_ID
from handlers import activity, report, stats, admin, welcome, scheduler

MOSCOW_TZ = pytz.timezone("Europe/Moscow")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Необработанное исключение в хендлере:", exc_info=context.error)
    traceback.print_exc()


async def debug_ids(update: Update, _) -> None:
    m = update.effective_message
    if m:
        print(f"[DEBUG] chat_id={m.chat_id}  message_thread_id={m.message_thread_id}")


async def cmd_help(update: Update, _) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(msg.HELP_TEXT)


def main() -> None:
    import os
    import database as db
    print(f"[ENV] все ключи окружения: {sorted(os.environ.keys())}")
    db.cleanup_old_rewards()

    app = Application.builder().token(BOT_TOKEN).build()

    # TODO: убрать после получения ID топиков
    app.add_handler(MessageHandler(filters.ALL, debug_ids), group=1)

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))

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

    logger.info("Подпольщик Билл выходит на связь...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
