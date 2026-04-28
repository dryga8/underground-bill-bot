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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
