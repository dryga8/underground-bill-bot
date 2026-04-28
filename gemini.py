import google.generativeai as genai

from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel("gemini-1.5-flash")

_PROMPT = (
    "Look at this screenshot from a fitness/health app. "
    "Find the total daily step count for today. "
    "Return ONLY a single integer number with no text, units, or formatting. "
    "If you cannot find a clear step count, return 0."
)


def recognize_steps(image_bytes: bytes) -> int | None:
    """Распознаёт число шагов на скриншоте. Возвращает None если не распознано."""
    try:
        response = _model.generate_content([
            _PROMPT,
            {"mime_type": "image/jpeg", "data": image_bytes},
        ])
        raw = response.text.strip()
        print(f"[GEMINI] ответ: {repr(raw)}")
        value = int(raw)
        return None if value == 0 else value
    except (ValueError, AttributeError) as e:
        print(f"[GEMINI] не удалось распарсить ответ: {e}")
        return None
    except Exception as e:
        print(f"[GEMINI] ошибка API: {e}")
        return None
