"""Telegram sender. With no credentials (or in dry-run) it just prints."""
import os

import requests


def send(text: str, dry_run: bool = False) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if dry_run or not token or not chat_id:
        print("---- ALERT (not sent) ----")
        print(text)
        return True
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] failed: {e}")
        return False
