"""Polls Finnhub for general market news and stores new items in the database."""

import os
import time

import sqlite3

import requests
from dotenv import load_dotenv

from db import get_connection, init_db

load_dotenv()

API_KEY = os.getenv("FINNHUB_API_KEY")
NEWS_URL = "https://finnhub.io/api/v1/news"
POLL_SECONDS = 60


def fetch_general_news():
    resp = requests.get(NEWS_URL, params={"category": "general", "token": API_KEY}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def store_new_articles(articles):
    conn = get_connection()
    now = int(time.time())
    inserted = 0
    for a in articles:
        try:
            conn.execute(
                """INSERT INTO news
                   (finnhub_id, headline, summary, url, source, category, published_at, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (a["id"], a["headline"], a.get("summary", ""), a.get("url", ""),
                 a.get("source", ""), a.get("category", ""), a["datetime"], now),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # duplicate finnhub_id, already stored
    conn.commit()
    conn.close()
    return inserted


def poll_forever():
    init_db()
    print(f"Polling Finnhub every {POLL_SECONDS}s. Ctrl+C to stop.")
    while True:
        try:
            articles = fetch_general_news()
            new_count = store_new_articles(articles)
            if new_count:
                print(f"[{time.strftime('%H:%M:%S')}] stored {new_count} new article(s)")
        except requests.RequestException as e:
            print(f"[{time.strftime('%H:%M:%S')}] fetch error: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    poll_forever()
