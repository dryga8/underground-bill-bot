import datetime
import calendar
import pytz

MOSCOW_TZ = pytz.timezone("Europe/Moscow")


def get_moscow_date() -> datetime.date:
    return datetime.datetime.now(MOSCOW_TZ).date()


def get_month_end(year: int, month: int) -> datetime.date:
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, last_day)


def pluralize_days(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return f"{n} дней"
    rem = n % 10
    if rem == 1:
        return f"{n} день"
    if 2 <= rem <= 4:
        return f"{n} дня"
    return f"{n} дней"


def fmt_number(n: int) -> str:
    """Форматирует число с пробелом как разделителем тысяч: 1234567 → '1 234 567'."""
    return f"{n:,}".replace(",", " ")


def get_display_name(user: dict) -> str:
    username = user.get("username")
    if username:
        return username.lstrip("@")
    first = (user.get("first_name") or "").strip()
    if first:
        return first
    return "Неизвестный боец"
