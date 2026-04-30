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
    if activity_type == "exercise":
        add_total_exercise_days(user_id)


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
            if activity_type == "exercise":
                add_total_exercise_days(user_id)
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
    existing = _client.table("xp").select("total_xp").eq("user_id", user_id).limit(1).execute()
    if existing.data:
        new_total = max(0, (existing.data[0]["total_xp"] or 0) + xp)
        _client.table("xp").update({"total_xp": new_total}).eq("user_id", user_id).execute()
    else:
        new_total = max(0, xp)
        if new_total == 0:
            return 0
        _client.table("xp").upsert({"user_id": user_id, "total_xp": new_total}).execute()
    return new_total


# ---------------------------------------------------------------------------
# Total steps
# ---------------------------------------------------------------------------

def get_total_steps(user_id: int) -> int:
    res = _client.table("total_steps").select("all_time_steps").eq("user_id", user_id).limit(1).execute()
    return res.data[0]["all_time_steps"] if res.data else 0


def add_total_steps(user_id: int, steps: int) -> None:
    existing = _client.table("total_steps").select("all_time_steps").eq("user_id", user_id).limit(1).execute()
    if existing.data:
        new_total = (existing.data[0]["all_time_steps"] or 0) + steps
        _client.table("total_steps").update({"all_time_steps": new_total}).eq("user_id", user_id).execute()
    else:
        _client.table("total_steps").upsert({"user_id": user_id, "all_time_steps": steps}).execute()


# ---------------------------------------------------------------------------
# Total exercise days
# ---------------------------------------------------------------------------

def get_total_exercise_days(user_id: int) -> int:
    res = _client.table("total_exercise").select("all_time_days").eq("user_id", user_id).limit(1).execute()
    return res.data[0]["all_time_days"] if res.data else 0


def add_total_exercise_days(user_id: int) -> None:
    existing = _client.table("total_exercise").select("all_time_days").eq("user_id", user_id).limit(1).execute()
    if existing.data:
        new_total = (existing.data[0]["all_time_days"] or 0) + 1
        _client.table("total_exercise").update({"all_time_days": new_total}).eq("user_id", user_id).execute()
    else:
        _client.table("total_exercise").upsert({"user_id": user_id, "all_time_days": 1}).execute()


# ---------------------------------------------------------------------------
# Salo
# ---------------------------------------------------------------------------

def add_salo(user_id: int, grams: int, month: int, year: int) -> None:
    _client.table("salo").insert({
        "user_id": user_id,
        "grams": grams,
        "month": month,
        "year": year,
    }).execute()
    existing = _client.table("total_salo").select("all_time_grams").eq("user_id", user_id).limit(1).execute()
    if existing.data:
        new_total = (existing.data[0]["all_time_grams"] or 0) + grams
        _client.table("total_salo").update({"all_time_grams": new_total}).eq("user_id", user_id).execute()
    else:
        _client.table("total_salo").upsert({"user_id": user_id, "all_time_grams": grams}).execute()


def get_monthly_salo(user_id: int, month: int, year: int) -> int:
    res = (
        _client.table("salo")
        .select("grams")
        .eq("user_id", user_id)
        .eq("month", month)
        .eq("year", year)
        .execute()
    )
    return sum(r["grams"] for r in res.data)


def get_total_salo(user_id: int) -> int:
    res = _client.table("total_salo").select("all_time_grams").eq("user_id", user_id).limit(1).execute()
    return res.data[0]["all_time_grams"] if res.data else 0


def get_salo_leaderboard(month: int, year: int) -> list[dict]:
    res = _client.table("salo").select("user_id, grams").eq("month", month).eq("year", year).execute()
    from collections import defaultdict
    agg: dict[int, int] = defaultdict(int)
    for row in res.data:
        agg[row["user_id"]] += row["grams"]
    result = []
    for uid, monthly in agg.items():
        user = get_user_by_id(uid)
        total = get_total_salo(uid)
        if user:
            result.append({"user": user, "monthly_grams": monthly, "total_grams": total})
    return result


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


def get_all_admins() -> list[dict]:
    res = _client.table("admins").select("user_id").execute()
    result = []
    for row in res.data:
        user = get_user_by_id(row["user_id"])
        if user:
            result.append(user)
    return result


# ---------------------------------------------------------------------------
# Steps (admin override)
# ---------------------------------------------------------------------------

def set_steps_for_date(user_id: int, activity_date, steps_count: int) -> bool:
    """Insert or update steps for a given date. Returns True if new record was created."""
    existing = (
        _client.table("activities")
        .select("id")
        .eq("user_id", user_id)
        .eq("activity_type", "steps")
        .eq("activity_date", activity_date.isoformat())
        .limit(1)
        .execute()
    )
    if existing.data:
        _client.table("activities").update({"steps_count": steps_count}).eq("id", existing.data[0]["id"]).execute()
        return False
    else:
        _client.table("activities").insert({
            "user_id": user_id,
            "activity_type": "steps",
            "activity_date": activity_date.isoformat(),
            "month": activity_date.month,
            "year": activity_date.year,
            "steps_count": steps_count,
        }).execute()
        return True


# ---------------------------------------------------------------------------
# Full reset (owner only)
# ---------------------------------------------------------------------------

def full_reset() -> None:
    """Delete all activity/game data. IRREVERSIBLE. Users and admins are preserved."""
    _client.table("report_votes").delete().gte("id", 0).execute()
    _client.table("reports").delete().gte("id", 0).execute()
    _client.table("jails").delete().gte("id", 0).execute()
    _client.table("rewards").delete().gte("id", 0).execute()
    _client.table("xp").delete().gte("user_id", 0).execute()
    _client.table("total_steps").delete().gte("user_id", 0).execute()
    _client.table("total_salo").delete().gte("user_id", 0).execute()
    _client.table("total_exercise").delete().gte("user_id", 0).execute()
    _client.table("activities").delete().gte("id", 0).execute()
    _client.table("salo").delete().gte("id", 0).execute()


# ---------------------------------------------------------------------------
# Rewards
# ---------------------------------------------------------------------------

_OLD_RANK_REWARDS = [
    'Новобранец подполья', 'Ефрейтор Сопротивления', 'Верный делу боец',
    'Сержант Сопротивления', 'Надёжный сержант', 'Боец с опытом',
]


def cleanup_old_rewards() -> None:
    """Удаляет устаревшие награды-звания из БД (одноразовая миграция)."""
    try:
        _client.table("rewards").delete().in_("reward", _OLD_RANK_REWARDS).execute()
    except Exception as e:
        print(f"[CLEANUP] ERROR deleting old rewards: {e}")


def add_reward(user_id: int, level: int, reward: str) -> None:
    _client.table("rewards").insert({
        "user_id": user_id,
        "level": level,
        "reward": reward,
    }).execute()


def get_user_rewards(user_id: int) -> list[dict]:
    res = (
        _client.table("rewards")
        .select("level, reward")
        .eq("user_id", user_id)
        .order("level")
        .execute()
    )
    return res.data


def check_and_award_level(user_id: int, old_xp: int, new_xp: int) -> list[tuple[int, str]]:
    """Award titles for each level crossed. Returns list of (level, reward) tuples."""
    import messages as msg
    old_level = get_level(old_xp)
    new_level = get_level(new_xp)
    awarded = []
    for level in range(old_level + 1, new_level + 1):
        if level in msg.REWARDS:
            reward = msg.get(msg.REWARDS[level])
            try:
                add_reward(user_id, level, reward)
                awarded.append((level, reward))
            except Exception as e:
                print(f"[AWARD] add_reward FAILED: level={level} error={e}")
    return awarded
