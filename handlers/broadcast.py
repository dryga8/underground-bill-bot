import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from config import OWNER_ID, GROUP_ID, NEWS_THREAD_ID
from utils import get_display_name

logger = logging.getLogger(__name__)

_WAIT_BROADCAST    = "wait_broadcast"
_WAIT_DM           = "wait_dm"
_WAIT_DM_USER_ID   = "wait_dm_user_id"
_WAIT_DM_DISPLAY   = "wait_dm_display"
_WAIT_DM_BOT_OK    = "wait_dm_bot_ok"

_MSG_ASK          = "Напиши текст или пришли медиа для отправки в новости. /cancel — отмена."
_MSG_ASK_DM       = "Напиши текст или пришли медиа для {display}. /cancel — отмена."
_MSG_SENT         = "✅ Отправлено в новости, ID: {message_id}"
_MSG_CANCELLED    = "❌ Отменено."
_MSG_NO_USER      = "Боец @{username} в архивах не найден."
_MSG_NO_BOT_START = "⚠️ Пользователь не активировал бота. Попроси его написать /start боту."
_MSG_FORBIDDEN    = "⚠️ Пользователь заблокировал бота."
_MSG_DM_SENT      = "✅ Сообщение отправлено {display}."
_MSG_NOTIFY_SENT  = "✅ Тег отправлен в новости."


def _is_privileged(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    return any(a["user_id"] == user_id for a in db.get_all_admins())


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    u = update.effective_user
    if not u or not _is_privileged(u.id):
        await message.reply_text("Недостаточно полномочий.")
        return

    text = " ".join(context.args) if context.args else ""
    if text:
        kwargs: dict = {"chat_id": GROUP_ID, "text": text, "parse_mode": "HTML"}
        if NEWS_THREAD_ID:
            kwargs["message_thread_id"] = NEWS_THREAD_ID
        sent = await context.bot.send_message(**kwargs)
        logger.info("[BROADCAST] text sent by %s, message_id=%s", u.id, sent.message_id)
        await message.reply_text(_MSG_SENT.format(message_id=sent.message_id))
        return

    context.user_data[_WAIT_DM] = False
    context.user_data[_WAIT_BROADCAST] = True
    await message.reply_text(_MSG_ASK)


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get(_WAIT_BROADCAST):
        return
    message = update.effective_message
    if not message:
        return
    u = update.effective_user
    if not u or not _is_privileged(u.id):
        return

    context.user_data[_WAIT_BROADCAST] = False

    kwargs: dict = {
        "chat_id": GROUP_ID,
        "from_chat_id": message.chat_id,
        "message_id": message.message_id,
    }
    if NEWS_THREAD_ID:
        kwargs["message_thread_id"] = NEWS_THREAD_ID
    sent = await context.bot.copy_message(**kwargs)
    logger.info("[BROADCAST] media sent by %s, message_id=%s", u.id, sent.message_id)
    await message.reply_text(_MSG_SENT.format(message_id=sent.message_id))


async def handle_dm_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get(_WAIT_DM):
        return
    message = update.effective_message
    if not message:
        return
    u = update.effective_user
    if not u or not _is_privileged(u.id):
        return

    context.user_data[_WAIT_DM] = False
    uid = context.user_data.pop(_WAIT_DM_USER_ID, None)
    display = context.user_data.pop(_WAIT_DM_DISPLAY, "пользователь")
    bot_ok = context.user_data.pop(_WAIT_DM_BOT_OK, False)

    if not uid:
        await message.reply_text("⚠️ Не найден получатель. Начни заново.")
        return

    if not bot_ok:
        await message.reply_text(_MSG_NO_BOT_START)
        return

    try:
        await context.bot.copy_message(
            chat_id=uid,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
        logger.info("[BROADCAST] DM (copy) sent to user_id=%s", uid)
        await message.reply_text(_MSG_DM_SENT.format(display=display))
    except Exception as e:
        if "Forbidden" in str(e):
            await message.reply_text(_MSG_FORBIDDEN)
        else:
            logger.error("[BROADCAST] DM error for user_id=%s: %s", uid, e)
            await message.reply_text(f"⚠️ Ошибка отправки: {e}")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    context.user_data[_WAIT_BROADCAST] = False
    context.user_data[_WAIT_DM] = False
    context.user_data.pop(_WAIT_DM_USER_ID, None)
    context.user_data.pop(_WAIT_DM_DISPLAY, None)
    context.user_data.pop(_WAIT_DM_BOT_OK, None)
    await message.reply_text(_MSG_CANCELLED)


async def cmd_notify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    u = update.effective_user
    if not u or not _is_privileged(u.id):
        await message.reply_text("Недостаточно полномочий.")
        return

    if not context.args or len(context.args) < 2:
        await message.reply_text("Формат: /notify @username текст")
        return

    username = context.args[0].lstrip("@")
    text = " ".join(context.args[1:])
    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(_MSG_NO_USER.format(username=username))
        return

    uid = target["user_id"]
    display = get_display_name(target)
    notify_text = f'<a href="tg://user?id={uid}">{display}</a>\n\n{text}'
    kwargs: dict = {"chat_id": GROUP_ID, "text": notify_text, "parse_mode": "HTML"}
    if NEWS_THREAD_ID:
        kwargs["message_thread_id"] = NEWS_THREAD_ID
    await context.bot.send_message(**kwargs)
    logger.info("[BROADCAST] notify sent for user_id=%s", uid)
    await message.reply_text(_MSG_NOTIFY_SENT)


async def cmd_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    u = update.effective_user
    if not u or not _is_privileged(u.id):
        await message.reply_text("Недостаточно полномочий.")
        return

    if not context.args:
        await message.reply_text("Формат: /dm @username [текст]")
        return

    username = context.args[0].lstrip("@")
    target = db.get_user_by_username(username)
    if not target:
        await message.reply_text(_MSG_NO_USER.format(username=username))
        return

    uid = target["user_id"]
    display = get_display_name(target)

    # Quick mode: text provided inline — old behaviour via send_message
    if len(context.args) >= 2:
        text = " ".join(context.args[1:])
        if not target.get("bot_started"):
            await message.reply_text(_MSG_NO_BOT_START)
            return
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            logger.info("[BROADCAST] DM sent to user_id=%s", uid)
            await message.reply_text(_MSG_DM_SENT.format(display=display))
        except Exception as e:
            if "Forbidden" in str(e):
                await message.reply_text(_MSG_FORBIDDEN)
            else:
                logger.error("[BROADCAST] DM error for user_id=%s: %s", uid, e)
                await message.reply_text(f"⚠️ Ошибка отправки: {e}")
        return

    # Interactive mode: wait for next message, checks happen at send time
    context.user_data[_WAIT_BROADCAST] = False
    context.user_data[_WAIT_DM] = True
    context.user_data[_WAIT_DM_USER_ID] = uid
    context.user_data[_WAIT_DM_DISPLAY] = display
    context.user_data[_WAIT_DM_BOT_OK] = bool(target.get("bot_started"))
    await message.reply_text(_MSG_ASK_DM.format(display=display))


def build_handlers():
    _private = filters.ChatType.PRIVATE
    return [
        CommandHandler("broadcast", cmd_broadcast, filters=_private),
        CommandHandler("cancel",    cmd_cancel,    filters=_private),
        CommandHandler("notify",    cmd_notify,    filters=_private),
        CommandHandler("dm",        cmd_dm,        filters=_private),
        MessageHandler(
            _private
            & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
            & ~filters.COMMAND,
            handle_broadcast_message,
        ),
        MessageHandler(
            _private
            & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
            & ~filters.COMMAND,
            handle_dm_message,
        ),
    ]
