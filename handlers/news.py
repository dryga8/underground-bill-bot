import asyncio
import html
import random

import feedparser
from bs4 import BeautifulSoup
from telegram.ext import ContextTypes

import messages as msg
from config import GROUP_ID, NEWS_THREAD_ID

_RSS_FEEDS = [
    "https://lifehacker.ru/feed/",
    "https://marathonec.ru/feed/",
    "https://n1.ru/rss/",
    "https://vc.ru/rss",
]

_WHITELIST = [
    "шаги", "бег", "бегун", "тренировка", "зарядка", "ходьба", "здоровье",
    "привычка", "сон", "питание", "похудение", "вес", "калории", "марафон",
    "фитнес", "спорт", "активность", "мышцы", "кардио", "умные часы",
    "трекер", "биохакинг", "режим", "вода", "осанка",
]

_STOPWORDS = [
    "купить", "скидка", "акция", "реклама", "промокод", "распродажа", "магазин", "цена",
]


def _clean_html(raw: str) -> str:
    return BeautifulSoup(raw, "html.parser").get_text(separator=" ").strip()


def _matches_whitelist(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _WHITELIST)


def _has_stopword(title: str) -> bool:
    lower = title.lower()
    return any(sw in lower for sw in _STOPWORDS)


def _extract_image(entry) -> str | None:
    for enc in getattr(entry, "enclosures", []):
        if getattr(enc, "type", "").startswith("image/"):
            return enc.get("url") or enc.get("href")
    for mc in getattr(entry, "media_content", []):
        url = mc.get("url")
        if url:
            return url
    for mt in getattr(entry, "media_thumbnail", []):
        url = mt.get("url")
        if url:
            return url
    return None


def fetch_news() -> dict | None:
    candidates = []
    for feed_url in _RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                description = _clean_html(summary)
                if _has_stopword(title):
                    continue
                if not _matches_whitelist(title + " " + description):
                    continue
                candidates.append({
                    "title": title,
                    "link": getattr(entry, "link", "") or "",
                    "description": description[:300],
                    "image_url": _extract_image(entry),
                })
        except Exception as e:
            print(f"[NEWS] error fetching {feed_url}: {e}")
    return random.choice(candidates) if candidates else None


async def send_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    article = await asyncio.to_thread(fetch_news)
    if not article:
        return

    intro = msg.get(msg.NEWS_INTROS)
    title_esc = html.escape(article["title"])
    desc_esc = html.escape(article["description"])
    link = article["link"]

    full_text = (
        f"{intro}\n\n"
        f"<b>{title_esc}</b>\n\n"
        f"{desc_esc}\n\n"
        f'<a href="{link}">Читать полностью →</a>'
    )

    send_kwargs: dict = {"chat_id": GROUP_ID, "parse_mode": "HTML"}
    if NEWS_THREAD_ID:
        send_kwargs["message_thread_id"] = NEWS_THREAD_ID

    try:
        if article["image_url"]:
            caption = full_text if len(full_text) <= 1024 else (
                f"{intro}\n\n<b>{title_esc}</b>\n\n"
                f'<a href="{link}">Читать полностью →</a>'
            )
            await context.bot.send_photo(
                **send_kwargs,
                photo=article["image_url"],
                caption=caption,
            )
        else:
            await context.bot.send_message(**send_kwargs, text=full_text)
    except Exception as e:
        print(f"[NEWS] send error: {e}")
        try:
            await context.bot.send_message(**send_kwargs, text=full_text)
        except Exception as e2:
            print(f"[NEWS] fallback send error: {e2}")
