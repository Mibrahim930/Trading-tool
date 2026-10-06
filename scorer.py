"""Scores unscored news items for ES/NQ relevance and impact using Claude Haiku."""

import os
import time

import anthropic
from dotenv import load_dotenv

from db import get_connection, init_db

load_dotenv()

MODEL = "claude-haiku-4-5"
POLL_SECONDS = 20

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = (
    "You are a market analyst judging whether a news headline/summary is relevant "
    "to trading E-mini S&P 500 (ES) or E-mini Nasdaq-100 (NQ) futures. Consider "
    "macro events, Fed policy, major tech/index constituent companies, geopolitics "
    "affecting markets, and broad economic data. Ignore purely single-stock news for "
    "companies that are not major index constituents, and ignore non-market topics. "
    "When relevant, also judge whether the news is bullish or bearish for ES/NQ - i.e. "
    "would it likely push those indices up or down."
)

CLASSIFY_TOOL = {
    "name": "classify",
    "description": "Classify a news item's relevance, impact, and directional bias for ES/NQ futures trading.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevant": {
                "type": "boolean",
                "description": "Whether this news is relevant to ES/NQ futures trading.",
            },
            "impact": {
                "type": "string",
                "enum": ["High", "Medium", "Low"],
                "description": "Expected market impact if relevant. Use Low if not relevant.",
            },
            "affects": {
                "type": "string",
                "enum": ["ES", "NQ", "Both"],
                "description": "Which index this news more specifically affects. Use 'Both' for "
                                "broad macro/Fed/economic news impacting the whole market equally. "
                                "Use 'NQ' for tech/AI/semiconductor-heavy news, 'ES' for news skewed "
                                "toward financials/industrials/energy/broad S&P sectors not concentrated "
                                "in NQ. Use 'Both' if not relevant.",
            },
            "direction": {
                "type": "string",
                "enum": ["Bullish", "Bearish", "Neutral"],
                "description": "Whether the news is good (Bullish), bad (Bearish), or mixed/unclear "
                                "(Neutral) for ES/NQ. Use Neutral if not relevant.",
            },
            "reason": {
                "type": "string",
                "description": "One-line reason covering the relevance/impact/direction judgment.",
            },
        },
        "required": ["relevant", "impact", "affects", "direction", "reason"],
        "additionalProperties": False,
    },
}


def classify(headline, summary):
    text = headline if not summary else f"{headline}\n\n{summary}"
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        tools=[CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify"},
        messages=[{"role": "user", "content": text}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Model did not return a tool_use block")


def score_pending(limit=20):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, headline, summary FROM news WHERE scored_at IS NULL LIMIT ?", (limit,)
    ).fetchall()

    scored = 0
    for row in rows:
        try:
            result = classify(row["headline"], row["summary"])
        except Exception as e:
            print(f"  scoring error for news id {row['id']}: {e}")
            continue

        conn.execute(
            """UPDATE news SET relevant = ?, impact = ?, affects = ?, direction = ?, reason = ?, scored_at = ?
               WHERE id = ?""",
            (1 if result["relevant"] else 0, result["impact"], result["affects"],
             result["direction"], result["reason"], int(time.time()), row["id"]),
        )
        scored += 1

    conn.commit()
    conn.close()
    return scored


def score_forever():
    init_db()
    print(f"Scoring unscored news every {POLL_SECONDS}s. Ctrl+C to stop.")
    while True:
        n = score_pending()
        if n:
            print(f"[{time.strftime('%H:%M:%S')}] scored {n} article(s)")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    score_forever()
