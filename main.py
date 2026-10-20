"""Gold (XAUUSD) news alert bot. One run = one check. GitHub Actions runs it every ~5 minutes.

    python main.py             # real run (sends Telegram alerts if credentials are set)
    python main.py --dry-run   # prints alerts instead of sending
"""
import html
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from judge import judge
from notify import send
from sources import fetch_calendar, fetch_news, is_relevant

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
RANK = {"low": 0, "medium": 1, "high": 2}
EMOJI = {"bullish": "🟢", "bearish": "🔴"}
MAX_JUDGE = 15          # headlines judged per run (keeps free AI limits safe)
MAX_ALERTS = 5          # alerts sent per run


def env(key, default):
    return os.environ.get(key) or default


def load_state():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    state.setdefault("seen", {})
    state.setdefault("cal_sent", {})
    state.setdefault("calendar", {"fetched": 0, "events": []})
    return state


def save_state(state, now):
    state["seen"] = {k: v for k, v in state["seen"].items() if now - v < 3 * 86400}
    state["cal_sent"] = {k: v for k, v in state["cal_sent"].items() if now - v < 10 * 86400}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)


def in_quiet_hours(now):
    """QUIET_HOURS='23-6' means no routine alerts from 23:00 to 06:00 (high-confidence still sent)."""
    q = env("QUIET_HOURS", "")
    if not q:
        return False
    try:
        start, end = (int(x) for x in q.split("-"))
        hour = datetime.fromtimestamp(now, ZoneInfo(env("TZ_NAME", "America/Toronto"))).hour
    except Exception:  # noqa: BLE001
        return False
    return start <= hour < end if start < end else (hour >= start or hour < end)


def calendar_alerts(state, now):
    cal = state["calendar"]
    if now - cal["fetched"] > 3600:                 # refresh hourly; the free feed rate-limits
        events = fetch_calendar()
        if events:
            cal["events"], cal["fetched"] = events, now
        else:
            cal["fetched"] = now - 3000             # failed: retry in ~10 minutes
    countries = {c.strip().upper() for c in env("CAL_COUNTRIES", "USD").split(",")}
    lead = int(env("CAL_LEAD_MIN", "30"))
    due = []
    for e in cal["events"]:
        if e["impact"] != "High" or e["country"].upper() not in countries:
            continue
        minutes = (e["ts"] - now) / 60
        if 0 <= minutes <= lead and e["id"] not in state["cal_sent"]:
            state["cal_sent"][e["id"]] = now
            due.append((e, minutes))
    return due


def format_calendar(event, minutes):
    extra = " | ".join(
        x for x in (
            f"Forecast: {event['forecast']}" if event["forecast"] else "",
            f"Previous: {event['previous']}" if event["previous"] else "",
        ) if x
    )
    return (
        f"⏰ <b>High-impact {html.escape(event['country'])} event in ~{int(minutes)} min</b>\n"
        f"{html.escape(event['title'])}\n"
        f"{html.escape(extra)}\n"
        "Expect a sharp gold move and wider spreads."
    ).replace("\n\n", "\n")


def format_news(item, verdict, now):
    age = max(0, int((now - item["ts"]) / 60)) if item["ts"] else 0
    label = f"{verdict['direction'].capitalize()} gold ({verdict['confidence']})"
    lines = [f"{EMOJI[verdict['direction']]} <b>{label}</b>"]
    if verdict["reason"]:
        lines.append(html.escape(verdict["reason"]))
    lines.append(f"<i>{html.escape(item['title'])}</i>")
    lines.append(f"{html.escape(item['source'])}, {age} min ago")
    if item["url"]:
        lines.append(html.escape(item["url"]))
    return "\n".join(lines)


def main():
    dry = "--dry-run" in sys.argv or os.environ.get("DRY_RUN") == "1"
    now = time.time()
    state = load_state()
    first_run = not state.get("started")
    sent = 0

    # 1) Economic-calendar heads-ups
    for event, minutes in calendar_alerts(state, now):
        send(format_calendar(event, minutes), dry)
        sent += 1

    # 2) News
    max_age = int(env("MAX_AGE_MIN", "90")) * 60
    min_rank = RANK.get(env("MIN_CONFIDENCE", "medium").lower(), 1)
    quiet = in_quiet_hours(now)

    fresh, batch_ids = [], set()
    for item in fetch_news():
        if item["id"] in state["seen"] or item["id"] in batch_ids:
            continue
        batch_ids.add(item["id"])
        if item["ts"] and now - item["ts"] > max_age:
            state["seen"][item["id"]] = now        # too old: remember it, never alert
            continue
        fresh.append(item)

    if first_run:
        # Seed memory so the first run doesn't flood you with old headlines.
        for item in fresh:
            state["seen"][item["id"]] = now
        send("✅ Gold alert bot is live. You'll get alerts for gold-moving news and big USD events.", dry)
        state["started"] = True
        save_state(state, now)
        print(f"First run: seeded {len(fresh)} headlines.")
        return

    relevant = []
    for item in sorted(fresh, key=lambda i: i["ts"], reverse=True):
        if not is_relevant(item):
            state["seen"][item["id"]] = now
        elif len(relevant) < MAX_JUDGE:
            relevant.append(item)                  # overflow stays unseen for the next run

    verdicts = judge(relevant)
    for item, verdict in zip(relevant, verdicts):
        state["seen"][item["id"]] = now
        if verdict["direction"] == "neutral" or RANK[verdict["confidence"]] < min_rank:
            continue
        if quiet and verdict["confidence"] != "high":
            continue
        if sent >= MAX_ALERTS:
            break
        send(format_news(item, verdict, now), dry)
        sent += 1

    save_state(state, now)
    print(f"Done: {len(fresh)} new, {len(relevant)} judged, {sent} alerts.")


if __name__ == "__main__":
    main()
