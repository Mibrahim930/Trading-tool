# ES/NQ Market News Monitor

Personal tool for monitoring news relevant to ES and NQ futures trading.

## Planned pieces
- Finnhub real-time news feed
- AI relevance/impact scoring (High/Medium/Low + one-line reason)
- Web dashboard showing all scored news
- Telegram alerts for High-impact items only
- Manual trade journal (entry/exit, auto duration + P&L for ES/NQ)

## Status
Currently validating the data source: checking whether Finnhub's free-tier
news feed is fresh/reliable enough to build the rest of the pipeline on.
See `scripts/test_finnhub_freshness.py`.

## Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in `FINNHUB_API_KEY` (and later
   `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`).
