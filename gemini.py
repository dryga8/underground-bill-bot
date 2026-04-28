import base64
import traceback

import requests

from config import GEMINI_API_KEY

_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

_PROMPT = (
    "Look at this screenshot from a fitness/health app. "
    "Find the total daily step count for today. "
    "Return ONLY a single integer number with no text, units, or formatting. "
    "If you cannot find a clear step count, return 0."
)


def recognize_steps(image_bytes: bytes) -> int | None:
    """Распознаёт число шагов на скриншоте через Gemini REST API. Возвращает None если не распознано."""
    print(f"[GEMINI] вызов API, размер изображения={len(image_bytes)} байт, ключ={'установлен' if GEMINI_API_KEY else 'ПУСТОЙ'}")
    try:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64.b64encode(image_bytes).decode("utf-8"),
                            }
                        },
                        {"text": _PROMPT},
                    ]
                }
            ]
        }
        resp = requests.post(
            _URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=30,
        )
        print(f"[GEMINI] HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"[GEMINI] ошибка ответа: {resp.text}")
            return None
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"[GEMINI] текст ответа: {repr(raw)}")
        digits = "".join(filter(str.isdigit, raw))
        num = int(digits) if digits else 0
        print(f"[GEMINI] распознано шагов: {num}")
        return num if num >= 1 else None
    except (ValueError, KeyError, IndexError) as e:
        print(f"[GEMINI] не удалось распарсить ответ: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        print(f"[GEMINI] ошибка: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None
