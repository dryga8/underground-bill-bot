from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

import messages as msg
from config import GROUP_ID, NEWS_THREAD_ID

_DELETE_AFTER_SECONDS = 180


async def _delete_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
    except Exception as e:
        print(f"[WELCOME] не удалось удалить сообщение: {e}")


async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.new_chat_members:
        return

    chat = update.effective_chat
    if not chat or chat.id != GROUP_ID:
        return

    try:
        await message.delete()
    except Exception as e:
        print(f"[WELCOME] не удалось удалить системное сообщение: {e}")

    for member in message.new_chat_members:
        if member.is_bot:
            continue
        mention = member.mention_html()
        text = msg.get(msg.WELCOME_MESSAGES).format(mention=mention)
        send_kwargs = {"chat_id": GROUP_ID, "text": text, "parse_mode": "HTML"}
        if NEWS_THREAD_ID:
            send_kwargs["message_thread_id"] = NEWS_THREAD_ID
        sent = await context.bot.send_message(**send_kwargs)
        context.job_queue.run_once(
            _delete_message,
            when=_DELETE_AFTER_SECONDS,
            data={"chat_id": sent.chat_id, "message_id": sent.message_id},
        )


def build_handler() -> MessageHandler:
    return MessageHandler(
        filters.Chat(GROUP_ID) & filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_member,
    )
