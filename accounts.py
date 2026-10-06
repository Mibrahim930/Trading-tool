"""Trading accounts/profiles: starting balance, active-account switching."""

import time

from db import get_connection
from journal import compute_pnl


def create_account(name, starting_balance=0.0, make_active=True):
    conn = get_connection()
    if make_active:
        conn.execute("UPDATE accounts SET is_active = 0")
    cur = conn.execute(
        "INSERT INTO accounts (name, starting_balance, is_active, created_at) VALUES (?, ?, ?, ?)",
        (name, starting_balance, 1 if make_active else 0, int(time.time())),
    )
    account_id = cur.lastrowid
    conn.commit()
    conn.close()
    return account_id


def update_account(account_id, name=None, starting_balance=None):
    conn = get_connection()
    if name is not None:
        conn.execute("UPDATE accounts SET name = ? WHERE id = ?", (name, account_id))
    if starting_balance is not None:
        conn.execute("UPDATE accounts SET starting_balance = ? WHERE id = ?", (starting_balance, account_id))
    conn.commit()
    conn.close()


def set_active_account(account_id):
    conn = get_connection()
    conn.execute("UPDATE accounts SET is_active = 0")
    conn.execute("UPDATE accounts SET is_active = 1 WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()


def get_active_account():
    conn = get_connection()
    row = conn.execute("SELECT * FROM accounts WHERE is_active = 1 LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def list_accounts():
    """All accounts with their realized P&L and current balance (starting_balance + P&L)."""
    conn = get_connection()
    accounts = [dict(r) for r in conn.execute("SELECT * FROM accounts ORDER BY created_at ASC")]
    for account in accounts:
        trade_rows = conn.execute("SELECT * FROM trades WHERE account_id = ?", (account["id"],)).fetchall()
        realized_pnl = sum(compute_pnl(t) or 0 for t in trade_rows)
        account["trade_count"] = len(trade_rows)
        account["realized_pnl"] = realized_pnl
        account["balance"] = account["starting_balance"] + realized_pnl
    conn.close()
    return accounts
