import calendar
import datetime
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

LEVELS = [0, 50, 150, 300, 500, 750, 1100, 1600, 2200, 3000,
          4000, 5200, 6600, 8200, 10000, 12000, 14500, 17500, 21000, 25000]


def get_level(xp: int) -> int:
    level = 0
    for i, threshold in enumerate(LEVELS):
        if xp >= threshold:
            level = i
    if xp >= LEVELS[-1]:
        level = len(LEVELS) - 1 + (xp - LEVELS[-1]) // 5000
    return level

_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def upsert_user(user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> None:
    _client.table("users").upsert({
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
    }).execute()


def get_user_by_username(username: str) -> dict | None:
    username = username.lstrip("@")
    res = _client.table("users").select("*").eq("username", username).limit(1).execute()
    return res.data[0] if res.data else None


def get_user_by_id(user_id: int) -> dict | None:
    res = _client.table("users").select("*").eq("user_id", user_id).limit(1).execute()
    return res.data[0] if res.data else None


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

def is_activity_recorded(user_id: int, activity_type: str, activity_date: datetime.date) -> bool:
    res = (
        _client.table("activities")
        .select("id")
        .eq("user_id", user_id)
        .eq("activity_type", activity_type)
        .eq("activity_date", activity_date.isoformat())
        .limit(1)
        .execute()
    )
    return bool(res.data)


def record_activity(user_id: int, activity_type: str, activity_date: datetime.date) -> None:
    _client.table("activities").insert({
        "user_id": user_id,
        "activity_type": activity_type,
        "activity_date": activity_date.isoformat(),
        "month": activity_date.month,
        "year": activity_date.year,
        "steps_count": 0,
    }).execute()


def record_steps(user_id: int, activity_date: datetime.date, steps_count: int) -> None:
    _client.table("activities").insert({
        "user_id": user_id,
        "activity_type": "steps",
        "activity_date": activity_date.isoformat(),
        "month": activity_date.month,
        "year": activity_date.year,
        "steps_count": steps_count,
    }).execute()


def get_monthly_steps(user_id: int, month: int, year: int) -> int:
    res = (
        _client.table("activities")
        .select("steps_count")
        .eq("user_id", user_id)
        .eq("activity_type", "steps")
        .eq("month", month)
        .eq("year", year)
        .execute()
    )
    return sum(r.get("steps_count") or 0 for r in res.data)


def get_steps_leaderboard(month: int, year: int) -> list[dict]:
    res = (
        _client.table("activities")
        .select("user_id, steps_count")
        .eq("activity_type", "steps")
        .eq("month", month)
        .eq("year", year)
        .execute()
    )
    from collections import defaultdict
    agg: dict[int, dict] = defaultdict(lambda: {"days": 0, "steps_sum": 0})
    for row in res.data:
        agg[row["user_id"]]["days"] += 1
        agg[row["user_id"]]["steps_sum"] += (row.get("steps_count") or 0)

    result = []
    for uid, data in agg.items():
        user = get_user_by_id(uid)
        if user:
            result.append({"user": user, "days": data["days"], "steps_sum": data["steps_sum"]})
    return result


def get_user_stats(user_id: int, month: int, year: int) -> dict:
    res = (
        _client.table("activities")
        .select("activity_type")
        .eq("user_id", user_id)
        .eq("month", month)
        .eq("year", year)
        .execute()
    )
    steps = sum(1 for r in res.data if r["activity_type"] == "steps")
    exercise = sum(1 for r in res.data if r["activity_type"] == "exercise")
    return {"steps": steps, "exercise": exercise}


def is_user_active_this_month(user_id: int, month: int, year: int) -> bool:
    res = (
        _client.table("activities")
        .select("id")
        .eq("user_id", user_id)
        .eq("month", month)
        .eq("year", year)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def get_top_stats(month: int, year: int) -> list[dict]:
    res = (
        _client.table("activities")
        .select("user_id, activity_type")
        .eq("month", month)
        .eq("year", year)
        .execute()
    )
    from collections import defaultdict
    counts: dict[int, dict] = defaultdict(lambda: {"steps": 0, "exercise": 0})
    for row in res.data:
        counts[row["user_id"]][row["activity_type"]] += 1

    result = []
    for uid, stats in counts.items():
        user = get_user_by_id(uid)
        if user:
            result.append({"user": user, "steps": stats["steps"], "exercise": stats["exercise"]})
    return result


def get_activity_top(activity_type: str, month: int, year: int) -> list[dict]:
    """Список пользователей с количеством дней по одной активности за месяц."""
    res = (
        _client.table("activities")
        .select("user_id")
        .eq("activity_type", activity_type)
        .eq("month", month)
        .eq("year", year)
        .execute()
    )
    from collections import Counter
    counts: Counter = Counter(row["user_id"] for row in res.data)

    result = []
    for uid, count in counts.items():
        user = get_user_by_id(uid)
        if user:
            result.append({"user": user, "days": count})
    return result


def add_days(user_id: int, activity_type: str, days: int, month: int, year: int) -> int:
    """Добавляет до `days` записей активности за свободные даты месяца. Возвращает сколько добавлено."""
    existing_res = (
        _client.table("activities")
        .select("activity_date")
        .eq("user_id", user_id)
        .eq("activity_type", activity_type)
        .eq("month", month)
        .eq("year", year)
        .execute()
    )
    existing_dates = {r["activity_date"] for r in existing_res.data}

    last_day = calendar.monthrange(year, month)[1]
    added = 0
    for day in range(1, last_day + 1):
        if added >= days:
            break
        d = datetime.date(year, month, day)
        if d.isoformat() not in existing_dates:
            _client.table("activities").insert({
                "user_id": user_id,
                "activity_type": activity_type,
                "activity_date": d.isoformat(),
                "month": month,
                "year": year,
            }).execute()
            added += 1
    return added


def remove_days(user_id: int, activity_type: str, days: int, month: int, year: int) -> int:
    """Удаляет до `days` самых последних записей активности за месяц. Возвращает сколько удалено."""
    res = (
        _client.table("activities")
        .select("id, activity_date")
        .eq("user_id", user_id)
        .eq("activity_type", activity_type)
        .eq("month", month)
        .eq("year", year)
        .order("activity_date", desc=True)
        .limit(days)
        .execute()
    )
    ids_to_delete = [r["id"] for r in res.data]
    if ids_to_delete:
        _client.table("activities").delete().in_("id", ids_to_delete).execute()
    return len(ids_to_delete)


# ---------------------------------------------------------------------------
# XP
# ---------------------------------------------------------------------------

def get_user_xp(user_id: int) -> int:
    res = _client.table("xp").select("total_xp").eq("user_id", user_id).limit(1).execute()
    return res.data[0]["total_xp"] if res.data else 0


def get_xp_leaderboard() -> list[dict]:
    """Все пользователи из таблицы xp, отсортированные по total_xp DESC."""
    res = _client.table("xp").select("user_id, total_xp").order("total_xp", desc=True).execute()
    result = []
    for row in res.data:
        user = get_user_by_id(row["user_id"])
        if user:
            result.append({"user": user, "total_xp": row["total_xp"] or 0})
    return result


def add_xp(user_id: int, xp: int) -> int:
    print(f"[DB:add_xp] START user={user_id} xp_to_add={xp}")
    try:
        existing = _client.table("xp").select("total_xp").eq("user_id", user_id).limit(1).execute()
        print(f"[DB:add_xp] SELECT result: data={existing.data}")
        if existing.data:
            new_total = max(0, (existing.data[0]["total_xp"] or 0) + xp)
            print(f"[DB:add_xp] UPDATE user={user_id} total_xp={new_total}")
            res = _client.table("xp").update({"total_xp": new_total}).eq("user_id", user_id).execute()
            print(f"[DB:add_xp] UPDATE response: data={res.data}")
        else:
            new_total = max(0, xp)
            if new_total == 0:
                print(f"[DB:add_xp] no row and xp<=0, skipping insert")
                return 0
            print(f"[DB:add_xp] UPSERT (new row) user={user_id} total_xp={new_total}")
            res = _client.table("xp").upsert({"user_id": user_id, "total_xp": new_total}).execute()
            print(f"[DB:add_xp] UPSERT response: data={res.data}")
        print(f"[DB:add_xp] DONE user={user_id} new_total={new_total}")
        return new_total
    except Exception as e:
        import traceback
        print(f"[DB:add_xp] EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


# ---------------------------------------------------------------------------
# Total steps
# ---------------------------------------------------------------------------

def get_total_steps(user_id: int) -> int:
    res = _client.table("total_steps").select("all_time_steps").eq("user_id", user_id).limit(1).execute()
    return res.data[0]["all_time_steps"] if res.data else 0


def add_total_steps(user_id: int, steps: int) -> None:
    print(f"[DB:add_total_steps] START user={user_id} steps_to_add={steps}")
    try:
        existing = _client.table("total_steps").select("all_time_steps").eq("user_id", user_id).limit(1).execute()
        print(f"[DB:add_total_steps] SELECT result: data={existing.data}")
        if existing.data:
            current = existing.data[0]["all_time_steps"] or 0
            new_total = current + steps
            print(f"[DB:add_total_steps] UPDATE user={user_id} all_time_steps={new_total}")
            res = _client.table("total_steps").update({"all_time_steps": new_total}).eq("user_id", user_id).execute()
            print(f"[DB:add_total_steps] UPDATE response: data={res.data}")
        else:
            print(f"[DB:add_total_steps] UPSERT (new row) user={user_id} all_time_steps={steps}")
            res = _client.table("total_steps").upsert({"user_id": user_id, "all_time_steps": steps}).execute()
            print(f"[DB:add_total_steps] UPSERT response: data={res.data}")
        print(f"[DB:add_total_steps] DONE user={user_id}")
    except Exception as e:
        import traceback
        print(f"[DB:add_total_steps] EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


# ---------------------------------------------------------------------------
# Jails
# ---------------------------------------------------------------------------

def is_jailed(user_id: int, activity_type: str) -> bool:
    res = (
        _client.table("jails")
        .select("id")
        .eq("user_id", user_id)
        .eq("activity_type", activity_type)
        .eq("active", True)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def jail_user(user_id: int, jailed_until: datetime.date, activity_type: str) -> None:
    _client.table("jails").insert({
        "user_id": user_id,
        "activity_type": activity_type,
        "jailed_until": jailed_until.isoformat(),
        "active": True,
    }).execute()


def pardon_user(user_id: int) -> None:
    _client.table("jails").update({"active": False}).eq("user_id", user_id).eq("active", True).execute()


def pardon_all() -> None:
    _client.table("jails").update({"active": False}).eq("active", True).execute()


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def has_open_report_for_message(chat_id: int, message_id: int) -> bool:
    res = (
        _client.table("reports")
        .select("id")
        .eq("chat_id", chat_id)
        .eq("message_id", message_id)
        .eq("status", "open")
        .limit(1)
        .execute()
    )
    return bool(res.data)


def create_report(
    reporter_id: int,
    reported_user_id: int,
    chat_id: int,
    message_id: int,
    thread_id: int | None,
    expires_at: datetime.datetime,
) -> int:
    res = _client.table("reports").insert({
        "reporter_id": reporter_id,
        "reported_user_id": reported_user_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "thread_id": thread_id,
        "status": "open",
        "yes_votes": 0,
        "expires_at": expires_at.isoformat(),
    }).execute()
    return res.data[0]["id"]


def set_report_vote_message(report_id: int, vote_message_id: int) -> None:
    _client.table("reports").update({"vote_message_id": vote_message_id}).eq("id", report_id).execute()


def get_report(report_id: int) -> dict | None:
    res = _client.table("reports").select("*").eq("id", report_id).limit(1).execute()
    return res.data[0] if res.data else None


def has_voted(report_id: int, voter_id: int) -> bool:
    res = (
        _client.table("report_votes")
        .select("id")
        .eq("report_id", report_id)
        .eq("voter_id", voter_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def add_vote(report_id: int, voter_id: int) -> int:
    _client.table("report_votes").insert({
        "report_id": report_id,
        "voter_id": voter_id,
    }).execute()
    res = _client.table("reports").select("yes_votes").eq("id", report_id).limit(1).execute()
    current = res.data[0]["yes_votes"]
    new_count = current + 1
    _client.table("reports").update({"yes_votes": new_count}).eq("id", report_id).execute()
    return new_count


def close_report(report_id: int, status: str) -> None:
    _client.table("reports").update({"status": status}).eq("id", report_id).execute()


# ---------------------------------------------------------------------------
# Admins
# ---------------------------------------------------------------------------

def is_admin(user_id: int) -> bool:
    res = _client.table("admins").select("user_id").eq("user_id", user_id).limit(1).execute()
    return bool(res.data)


def add_admin(user_id: int, added_by: int) -> None:
    _client.table("admins").upsert({"user_id": user_id, "added_by": added_by}).execute()
