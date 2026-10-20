"""Turns headlines into gold verdicts.

JUDGE_PROVIDER = gemini (default, free tier) | claude (paid) | keywords (no AI, no key).
If the chosen AI call fails, the keyword judge is used so you still get alerts.
"""
import json
import os
import re
import time

import requests

PROMPT = """You are a gold (XAUUSD) market analyst. For each numbered headline, judge the likely
effect on the gold price over the next few hours.

Rules:
- bullish = likely pushes gold UP (e.g. rate-cut hopes, weaker USD, falling yields, escalating
  conflict, banking stress). bearish = likely pushes gold DOWN (e.g. hawkish Fed, stronger USD,
  rising yields, strong US data that lifts rate expectations, de-escalation).
- neutral if unrelated to gold, USD, rates, inflation, or geopolitics, or if the effect is unclear.
- confidence: high only for clear, market-moving news. Otherwise medium or low.
- reason: one short sentence, max 15 words.

Return ONLY a JSON array, one object per headline:
[{{"i": 0, "direction": "bullish|bearish|neutral", "confidence": "low|medium|high", "reason": "..."}}]

Headlines:
{lines}
"""

BULLISH = [
    "rate cut", "cuts rates", "dovish", "safe haven", "safe-haven", "weaker dollar", "dollar falls",
    "dollar slips", "dollar weakens", "yields fall", "yields drop", "yields slide", "soft jobs",
    "weak jobs", "cooler inflation", "inflation cools", "escalat", "missile", "airstrike",
    "gold rises", "gold climbs", "gold jumps", "gold surges", "record high", "banking stress",
]
BEARISH = [
    "rate hike", "hikes rates", "hawkish", "stronger dollar", "dollar rises", "dollar jumps",
    "dollar strengthens", "yields rise", "yields jump", "yields climb", "strong jobs", "hot cpi",
    "hotter inflation", "inflation accelerates", "ceasefire", "de-escalat", "gold falls",
    "gold drops", "gold slips", "gold slides", "gold tumbles", "higher for longer",
]


def _lines(items):
    out = []
    for n, it in enumerate(items):
        summary = f" - {it['summary'][:200]}" if it.get("summary") else ""
        out.append(f"{n}. {it['title']}{summary}")
    return "\n".join(out)


def _parse(text, count):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    verdicts = [{"direction": "neutral", "confidence": "low", "reason": ""} for _ in range(count)]
    for row in data:
        i = int(row.get("i", -1))
        if 0 <= i < count:
            d = str(row.get("direction", "neutral")).lower()
            c = str(row.get("confidence", "low")).lower()
            verdicts[i] = {
                "direction": d if d in ("bullish", "bearish", "neutral") else "neutral",
                "confidence": c if c in ("low", "medium", "high") else "low",
                "reason": str(row.get("reason", ""))[:160],
            }
    return verdicts


GEMINI_MODELS = [          # tried in order; a 404 just moves on to the next one
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
]


RETRY_CODES = (404, 429, 500, 502, 503, 504)   # model missing or overloaded: try the next one


def gemini_generate(prompt, tag="gemini"):
    """Ask Gemini, falling back across models and retrying once if they are overloaded.
    Returns the response text. Raises if nothing answers."""
    candidates = ([os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else []) + GEMINI_MODELS
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    last = "no model tried"
    for attempt in range(2):
        transient = False
        for model in candidates:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                json=body,
                timeout=45,
            )
            if r.status_code in RETRY_CODES:
                last = f"{model}: {r.status_code}"
                transient = transient or r.status_code != 404
                print(f"[{tag}] model {model} unavailable ({r.status_code}), trying next")
                continue
            r.raise_for_status()
            print(f"[{tag}] using {model}")
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        if attempt == 0 and transient:
            time.sleep(5)
        else:
            break
    raise RuntimeError(f"no Gemini model answered ({last})")


def _gemini(items):
    return _parse(gemini_generate(PROMPT.format(lines=_lines(items)), "judge:gemini"), len(items))


def _claude(items):
    model = os.environ.get("CLAUDE_MODEL") or "claude-haiku-5-5"
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": PROMPT.format(lines=_lines(items))}],
        },
        timeout=60,
    )
    r.raise_for_status()
    return _parse(r.json()["content"][0]["text"], len(items))


def _keywords(items):
    verdicts = []
    for it in items:
        text = (it["title"] + " " + it.get("summary", "")).lower()
        up = sum(k in text for k in BULLISH)
        down = sum(k in text for k in BEARISH)
        if up == down:
            verdicts.append({"direction": "neutral", "confidence": "low", "reason": ""})
            continue
        direction = "bullish" if up > down else "bearish"
        hits = max(up, down)
        verdicts.append({
            "direction": direction,
            "confidence": "medium" if hits >= 2 else "low",
            "reason": "Keyword match (no AI judge)",
        })
    return verdicts


def judge(items):
    if not items:
        return []
    provider = (os.environ.get("JUDGE_PROVIDER") or "gemini").lower()
    try:
        if provider == "gemini" and os.environ.get("GEMINI_API_KEY"):
            return _gemini(items)
        if provider == "claude" and os.environ.get("ANTHROPIC_API_KEY"):
            return _claude(items)
    except Exception as e:  # noqa: BLE001
        print(f"[judge:{provider}] failed, using keywords: {e}")
    return _keywords(items)
