import traceback

from google import genai

from config import GEMINI_API_KEY


async def recognize_steps(image_bytes: bytes) -> int | None:
    """Распознаёт число шагов на скриншоте. Возвращает None если не распознано."""
    print(f"[GEMINI] вызов API, размер изображения={len(image_bytes)} байт, ключ={'установлен' if GEMINI_API_KEY else 'ПУСТОЙ'}")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                {"mime_type": "image/jpeg", "data": image_bytes},
                "Look at this screenshot from a fitness/health app. Find the total daily step count for today. Return ONLY a single integer number with no text, units, or formatting. If you cannot find a clear step count, return 0.",
            ],
        )
        print(f"[GEMINI] ответ получен")
        raw = response.text.strip()
        print(f"[GEMINI] текст ответа: {repr(raw)}")
        digits = "".join(filter(str.isdigit, raw))
        num = int(digits) if digits else 0
        print(f"[GEMINI] распознано шагов: {num}")
        return num if num >= 1 else None
    except (ValueError, AttributeError) as e:
        print(f"[GEMINI] не удалось распарсить ответ: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        print(f"[GEMINI] ошибка API: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None
