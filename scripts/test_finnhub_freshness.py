"""
Sanity-check Finnhub's free-tier news feed before building anything on top of it.

Two modes:
  snapshot (default): fetch general market news once, report how old each
                       headline already is by the time we see it.
  --watch MINUTES:    poll repeatedly and log new headlines as they appear,
                       so we can see how often the feed actually updates.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FINNHUB_API_KEY")
NEWS_URL = "https://finnhub.io/api/v1/news"
POLL_SECONDS = 30


def fetch_general_news(category="general"):
    resp = requests.get(NEWS_URL, params={"category": category, "token": API_KEY}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def format_age(seconds):
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f} min"
    return f"{minutes / 60:.1f} hr"


def snapshot():
    articles = fetch_general_news()
    now = time.time()

    if not articles:
        print("No articles returned — free tier may not include this category, or key is invalid.")
        return

    articles.sort(key=lambda a: a["datetime"], reverse=True)

    print(f"Fetched {len(articles)} articles. Current time (UTC): "
          f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"{'Age':>10}  {'Published (UTC)':<20}  Headline")
    print("-" * 95)
    for a in articles[:20]:
        pub = datetime.fromtimestamp(a["datetime"], tz=timezone.utc)
        age_sec = now - a["datetime"]
        print(f"{format_age(age_sec):>10}  {pub.strftime('%Y-%m-%d %H:%M:%S'):<20}  {a['headline'][:70]}")

    ages = [now - a["datetime"] for a in articles[:20]]
    print("\n--- Summary ---")
    print(f"Newest article age:   {format_age(ages[0])}")
    print(f"Avg age of top 20:    {format_age(sum(ages) / len(ages))}")
    print(f"Oldest of top 20:     {format_age(ages[-1])}")


def watch(minutes):
    print(f"Polling every {POLL_SECONDS}s for {minutes} minute(s). Ctrl+C to stop early.\n")
    seen_ids = set()
    deadline = time.time() + minutes * 60

    # Seed with current articles so we only log genuinely NEW ones going forward.
    try:
        seen_ids.update(a["id"] for a in fetch_general_news())
    except requests.RequestException as e:
        print(f"Initial fetch failed: {e}")
        sys.exit(1)

    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        try:
            articles = fetch_general_news()
        except requests.RequestException as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] fetch error: {e}")
            continue

        now = time.time()
        new_ones = [a for a in articles if a["id"] not in seen_ids]
        new_ones.sort(key=lambda a: a["datetime"])
        for a in new_ones:
            seen_ids.add(a["id"])
            age_sec = now - a["datetime"]
            pub = datetime.fromtimestamp(a["datetime"], tz=timezone.utc).strftime("%H:%M:%S")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] NEW  "
                  f"published {pub} UTC  (age {format_age(age_sec)})  {a['headline'][:70]}")

    print("\nWatch window complete.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", type=float, default=0,
                         help="Poll for this many minutes and log new headlines as they arrive.")
    args = parser.parse_args()

    if not API_KEY:
        print("FINNHUB_API_KEY not set. Copy .env.example to .env and fill it in.")
        sys.exit(1)

    if args.watch > 0:
        watch(args.watch)
    else:
        snapshot()


if __name__ == "__main__":
    main()
