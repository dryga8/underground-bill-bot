import messages as msg
from config import GROUP_ID, NEWS_THREAD_ID

_DELETE_AFTER_SECONDS = 60


async def _delete_job(context) -> None:
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
    except Exception:
        pass


async def send_level_up_notifications(context, name: str, rewards: list[tuple[int, str]]) -> None:
    """Send a level-up announcement for each (level, reward) pair, auto-deleted after 60s."""
    for level, reward in rewards:
        text = msg.get(msg.LEVEL_UP_MESSAGES).format(name=name, level=level, reward=reward)
        send_kwargs = {"chat_id": GROUP_ID, "text": text, "parse_mode": "HTML"}
        print(f"[LEVEL_UP] sending to chat_id={GROUP_ID} thread_id=None level={level} reward={reward!r} name={name!r}")
        try:
            sent = await context.bot.send_message(**send_kwargs)
            print(f"[LEVEL_UP] sent ok message_id={sent.message_id}")
            context.job_queue.run_once(
                _delete_job,
                when=_DELETE_AFTER_SECONDS,
                data={"chat_id": sent.chat_id, "message_id": sent.message_id},
            )
        except Exception as e:
            print(f"[LEVEL_UP] ERROR отправки: {e}")
