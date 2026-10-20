"""Prints your Telegram chat id. Message your bot first, then run:
    TELEGRAM_BOT_TOKEN=xxxx python get_chat_id.py
"""
import os

import requests

token = os.environ["TELEGRAM_BOT_TOKEN"]
data = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
seen = set()
for u in data.get("result", []):
    chat = (u.get("message") or {}).get("chat") or {}
    if chat.get("id") and chat["id"] not in seen:
        seen.add(chat["id"])
        print("chat id:", chat["id"], "-", chat.get("first_name", ""))
if not seen:
    print("No messages found. Send any message to your bot, then run this again.")
