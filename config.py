import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
OWNER_ID = int(os.environ["OWNER_ID"])
GROUP_ID = int(os.environ["GROUP_ID"])
STEPS_THREAD_ID = int(os.environ["STEPS_THREAD_ID"])
EXERCISE_THREAD_ID = int(os.environ["EXERCISE_THREAD_ID"])

PINNED_STEPS_MESSAGE_ID = int(os.getenv("PINNED_STEPS_MESSAGE_ID", "0"))
PINNED_EXERCISE_MESSAGE_ID = int(os.getenv("PINNED_EXERCISE_MESSAGE_ID", "0"))
PINNED_SALO_MESSAGE_ID = int(os.getenv("PINNED_SALO_MESSAGE_ID", "0"))
_salo_thread = os.getenv("SALO_THREAD_ID", "")
SALO_THREAD_ID: int | None = int(_salo_thread) if _salo_thread else None

_news_thread = os.getenv("NEWS_THREAD_ID", "")
NEWS_THREAD_ID: int | None = int(_news_thread) if _news_thread else None
