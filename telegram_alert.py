"""Sends Telegram alerts for High-impact news and helps discover the chat ID."""

import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from db import get_connection, init_db

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_SECONDS = 20


def get_chat_id():
    """Call after the user has sent the bot a message. Returns the chat_id or None."""
    resp = requests.get(f"{API_BASE}/getUpdates", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("result", [])
    if not results:
        return None
    return results[-1]["message"]["chat"]["id"]


def send_message(text):
    resp = requests.post(
        f"{API_BASE}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": False},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def alert_pending(limit=20):
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, headline, url, reason, direction, affects, published_at FROM news
           WHERE impact = 'High' AND telegram_sent = 0 LIMIT ?""",
        (limit,),
    ).fetchall()

    sent = 0
    for row in rows:
        direction_tag = {"Bullish": "BULLISH", "Bearish": "BEARISH"}.get(row["direction"], "NEUTRAL")
        affects_tag = row["affects"] or "Both"
        published = datetime.fromtimestamp(row["published_at"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        text = (f"HIGH IMPACT ({direction_tag}, {affects_tag}) - broke {published}\n\n{row['headline']}\n\n"
                f"{row['reason']}\n\n{row['url']}")
        try:
            send_message(text)
        except Exception as e:
            print(f"  telegram send error for news id {row['id']}: {e}")
            continue
        conn.execute("UPDATE news SET telegram_sent = 1 WHERE id = ?", (row["id"],))
        sent += 1

    conn.commit()
    conn.close()
    return sent


def alert_forever():
    init_db()
    print(f"Sending Telegram alerts for High-impact news every {POLL_SECONDS}s. Ctrl+C to stop.")
    while True:
        n = alert_pending()
        if n:
            print(f"[{time.strftime('%H:%M:%S')}] sent {n} alert(s)")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    alert_forever()
