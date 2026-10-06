"""SQLite schema and connection helper shared by the poller, scorer, dashboard, and journal."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "market_monitor.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finnhub_id INTEGER UNIQUE NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    source TEXT,
    category TEXT,
    published_at INTEGER NOT NULL,
    fetched_at INTEGER NOT NULL,
    relevant INTEGER,
    impact TEXT,
    affects TEXT,
    direction TEXT,
    reason TEXT,
    scored_at INTEGER,
    telegram_sent INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    starting_balance REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    symbol TEXT,
    side TEXT,
    contracts INTEGER,
    entry_price REAL,
    entry_time INTEGER,
    exit_price REAL,
    exit_time INTEGER,
    pnl_override REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS trade_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    note TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


NEWS_COLUMNS_ADDED_AFTER_V1 = {"direction": "TEXT", "affects": "TEXT"}

# v1 trades had NOT NULL on symbol/side/contracts/entry_price/entry_time. Since
# entries can now be partial and edited later, those columns must accept NULL -
# SQLite can't drop a NOT NULL constraint in place, so the table is rebuilt.
TRADES_V1_COLUMNS = ("id", "symbol", "side", "contracts", "entry_price", "entry_time",
                     "exit_price", "exit_time", "notes")


def init_db():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = OFF")
    # Without this, "ALTER TABLE trades RENAME" rewrites trade_notes' FK clause to
    # point at the transient "trades_old" name, which dangles once it's dropped.
    conn.execute("PRAGMA legacy_alter_table = ON")
    conn.executescript(SCHEMA)

    existing_news_cols = {row["name"] for row in conn.execute("PRAGMA table_info(news)")}
    for col, col_type in NEWS_COLUMNS_ADDED_AFTER_V1.items():
        if col not in existing_news_cols:
            conn.execute(f"ALTER TABLE news ADD COLUMN {col} {col_type}")

    existing_trade_cols = {row["name"] for row in conn.execute("PRAGMA table_info(trades)")}
    if "pnl_override" not in existing_trade_cols:
        conn.execute("ALTER TABLE trades RENAME TO trades_old")
        conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                side TEXT,
                contracts INTEGER,
                entry_price REAL,
                entry_time INTEGER,
                exit_price REAL,
                exit_time INTEGER,
                pnl_override REAL,
                notes TEXT
            )
        """)
        cols = ", ".join(TRADES_V1_COLUMNS)
        conn.execute(f"INSERT INTO trades ({cols}) SELECT {cols} FROM trades_old")
        conn.execute("DROP TABLE trades_old")

    existing_trade_cols = {row["name"] for row in conn.execute("PRAGMA table_info(trades)")}
    if "account_id" not in existing_trade_cols:
        conn.execute("ALTER TABLE trades ADD COLUMN account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL")

    # Repair a trade_notes FK left dangling by an earlier buggy migration (it would
    # have been rewritten to reference "trades_old", which no longer exists).
    trade_notes_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='trade_notes'"
    ).fetchone()
    if trade_notes_sql and "trades_old" in trade_notes_sql["sql"]:
        conn.execute("ALTER TABLE trade_notes RENAME TO trade_notes_old")
        conn.execute("""
            CREATE TABLE trade_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
                note TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO trade_notes (id, trade_id, note, created_at) "
            "SELECT id, trade_id, note, created_at FROM trade_notes_old"
        )
        conn.execute("DROP TABLE trade_notes_old")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
