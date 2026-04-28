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
    print(f"[GEMINI] вызов API, размер изображения={len(image_bytes)} байт, ключ={'установлен' if GEMINI_API_KEY else 'ПУСТОЙ'}")
    try:
        response = _model.generate_content([
            _PROMPT,
            {"mime_type": "image/jpeg", "data": image_bytes},
        ])
        print(f"[GEMINI] ответ получен, finish_reason={getattr(response.candidates[0], 'finish_reason', '?') if response.candidates else 'нет candidates'}")
        raw = response.text.strip()
        print(f"[GEMINI] текст ответа: {repr(raw)}")
        value = int(raw)
        print(f"[GEMINI] распознано шагов: {value}")
        return None if value == 0 else value
    except (ValueError, AttributeError) as e:
        print(f"[GEMINI] не удалось распарсить ответ: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        import traceback
        print(f"[GEMINI] ошибка API: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None
