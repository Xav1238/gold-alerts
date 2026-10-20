"""Gold digest: one Telegram summary of recent gold-moving news plus the next 24h of big USD events.

Runs on its own schedule (digest.yml) and never touches state.json.
    python digest.py             # send to Telegram
    python digest.py --dry-run   # just print
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from judge import GEMINI_MODELS
from notify import send
from sources import fetch_calendar, fetch_news, is_relevant

PROMPT = """You are a gold (XAUUSD) market analyst writing a short briefing for a trader.
Below are recent headlines, newest first. Judge the overall likely direction for gold over the next
several hours.

Rules:
- Use ONLY the headlines given. Do not invent prices, numbers or events.
- If the headlines point in different directions, say "mixed".
- bias is one of: bullish, bearish, mixed, unclear. confidence is one of: low, medium, high.
- summary: 2-3 plain sentences. drivers: up to 4 short bullet strings (max 15 words each).

Return ONLY JSON:
{{"bias": "...", "confidence": "...", "summary": "...", "drivers": ["...", "..."]}}

Headlines:
{lines}
"""

EMOJI = {"bullish": "🟢", "bearish": "🔴", "mixed": "🟡", "unclear": "⚪"}


def esc(value):
    return html.escape(str(value), quote=False)


def env(key, default):
    return os.environ.get(key) or default


def ask_gemini(lines):
    """Returns the briefing dict, or None if no AI is configured or no model answers."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key or env("JUDGE_PROVIDER", "gemini").lower() != "gemini":
        return None
    candidates = ([os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else []) + GEMINI_MODELS
    body = {
        "contents": [{"parts": [{"text": PROMPT.format(lines=lines)}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    for model in candidates:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json=body,
            timeout=60,
        )
        if r.status_code == 404:
            print(f"[digest:gemini] model {model} not available, trying next")
            continue
        r.raise_for_status()
        print(f"[digest:gemini] using {model}")
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        return json.loads(text)
    print("[digest:gemini] no model available")
    return None


def age_text(ts, now):
    if not ts:
        return "time unknown"
    mins = max(0, int((now - ts) / 60))
    return f"{mins} min ago" if mins < 90 else f"{mins // 60} h ago"


def build_message(items, events, brief, now, tz, hours_back):
    stamp = datetime.fromtimestamp(now, tz).strftime("%a %I:%M %p").replace(" 0", " ")
    head = [f"📊 <b>Gold digest</b> · {stamp}"]

    body = []
    if not items:
        body.append(f"No major gold-relevant headlines in the last {hours_back:g} hours.")
    elif brief:
        bias = str(brief.get("bias", "unclear")).lower()
        bias = bias if bias in EMOJI else "unclear"
        conf = str(brief.get("confidence", "low")).lower()
        body.append(f"{EMOJI[bias]} <b>Overall read: {bias.capitalize()} ({esc(conf)})</b>")
        if brief.get("summary"):
            body.append(esc(str(brief["summary"]))[:700])
        drivers = [str(d) for d in (brief.get("drivers") or [])][:4]
        if drivers:
            body.append("\n".join("• " + esc(d[:200]) for d in drivers))
    else:
        body.append("<i>AI summary unavailable, showing headlines only.</i>")

    ev_lines = []
    if events:
        ev_lines.append("⏰ <b>Next 24h, high-impact</b>")
        for e in events:
            when = datetime.fromtimestamp(e["ts"], tz).strftime("%a %I:%M %p").replace(" 0", " ")
            extra = " | ".join(x for x in (
                f"F: {e['forecast']}" if e["forecast"] else "",
                f"P: {e['previous']}" if e["previous"] else "",
            ) if x)
            line = f"• {when} {esc(e['country'])} {esc(e['title'])}"
            ev_lines.append(line + (f" ({esc(extra)})" if extra else ""))

    def headline_block(n):
        if not items or n == 0:
            return []
        out = ["📰 <b>Latest headlines</b>"]
        for it in items[:n]:
            title = esc(it["title"][:140])
            link = f'<a href="{html.escape(it["url"], quote=True)}">{title}</a>' if it["url"] else title
            out.append(f"• {link} <i>({esc(it['source'])}, {age_text(it['ts'], now)})</i>")
        return out

    for n in (6, 4, 2, 0):                       # shrink until it fits Telegram's 4096 limit
        sections = [head[0], "\n\n".join(body), "\n".join(ev_lines), "\n".join(headline_block(n))]
        msg = "\n\n".join(s for s in sections if s)
        if len(msg) <= 4000:
            return msg
    return msg[:4000]


def main():
    dry = "--dry-run" in sys.argv or os.environ.get("DRY_RUN") == "1"
    now = time.time()
    tz = ZoneInfo(env("TZ_NAME", "America/Toronto"))
    hours_back = float(env("DIGEST_HOURS_BACK", "8"))
    max_items = int(env("DIGEST_MAX_HEADLINES", "25"))

    items, seen = [], set()
    for it in sorted(fetch_news(), key=lambda i: i["ts"], reverse=True):
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        if it["ts"] and now - it["ts"] > hours_back * 3600:
            continue
        if is_relevant(it):
            items.append(it)
    items = items[:max_items]

    countries = {c.strip().upper() for c in env("CAL_COUNTRIES", "USD").split(",")}
    events = sorted(
        (e for e in fetch_calendar()
         if e["impact"] == "High" and e["country"].upper() in countries and 0 <= e["ts"] - now <= 24 * 3600),
        key=lambda e: e["ts"],
    )

    brief = None
    if items:
        lines = "\n".join(f"{n}. {it['title']} ({age_text(it['ts'], now)})" for n, it in enumerate(items))
        try:
            brief = ask_gemini(lines)
        except Exception as e:  # noqa: BLE001
            print(f"[digest:gemini] failed: {e}")

    send(build_message(items, events, brief, now, tz, hours_back), dry)
    print(f"Digest: {len(items)} headlines, {len(events)} events, AI={'yes' if brief else 'no'}.")


if __name__ == "__main__":
    main()
