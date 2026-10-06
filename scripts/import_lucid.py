"""One-off (re-)import of Lucid Trading's daily P&L-by-symbol history into the journal,
tagged to a fresh $50,000 account so balance tracks against real starting capital.

Lucid's dashboard only exposes daily aggregates per symbol (no per-trade entry/exit
price or long/short side), so each row here becomes one journal entry with just a
date, symbol, contracts (Lucid's QTY column), and P&L override. Entry price and side
are intentionally left blank - that data doesn't exist in what Lucid provides.
"""

import time

from accounts import create_account
from db import get_connection, init_db
from journal import add_trade

ACCOUNT_NAME = "LucidFlex 50K"
STARTING_BALANCE = 50000.0

# (date MM/DD/YYYY, symbol, net_pnl, qty) - from Lucid's "Trading History" table,
# oldest to newest.
ROWS = [
    ("04/28/2026", "MESM6", 41.00, 19),
    ("04/29/2026", "MESM6", -2.00, 2),
    ("04/30/2026", "MESM6", -298.75, 5),
    ("05/01/2026", "MESM6", 88.00, 12),
    ("05/04/2026", "MNQM6", -91.00, 3),
    ("05/05/2026", "MNQM6", -141.50, 5),
    ("05/05/2026", "MESM6", 76.00, 4),
    ("05/12/2026", "MESM6", -212.50, 5),
    ("05/14/2026", "MESM6", -19.00, 4),
    ("06/17/2026", "MNQU6", 7.00, 4),
    ("06/18/2026", "MNQU6", 315.50, 3),
    ("06/18/2026", "MESU6", -32.00, 2),
    ("06/24/2026", "MESU6", -203.00, 3),
    ("06/25/2026", "MESU6", 22.25, 4),
    ("06/26/2026", "MESU6", 213.50, 4),
    ("06/29/2026", "MNQU6", -404.50, 5),
    ("06/30/2026", "MNQU6", -191.00, 3),
    ("06/30/2026", "MESU6", 487.50, 10),
    ("07/01/2026", "MESU6", 60.75, 3),
    ("07/02/2026", "MESU6", 174.50, 3),
    ("07/10/2026", "MESU6", -422.50, 5),
    ("07/13/2026", "MESU6", 133.00, 7),
    ("07/21/2026", "MNQU6", -2.50, 3),
    ("07/21/2026", "MESU6", 230.75, 3),
    ("07/22/2026", "MESU6", 60.50, 7),
    ("07/23/2026", "MNQU6", 80.50, 1),
    ("07/27/2026", "MNQU6", -65.50, 1),
    ("07/27/2026", "MESU6", -109.50, 2),
    ("07/28/2026", "MESU6", -351.00, 6),
    ("08/11/2026", "MNQU6", 469.50, 2),
    ("08/11/2026", "MESU6", 364.50, 8),
    ("08/20/2026", "MNQU6", 283.50, 2),
    ("08/21/2026", "MNQU6", -81.00, 1),
    ("08/25/2026", "MESU6", 194.75, 9),
    ("08/26/2026", "MESU6", -605.00, 10),
    ("09/08/2026", "MESU6", 42.00, 8),
    ("09/09/2026", "MNQU6", 47.50, 6),
    ("09/17/2026", "MESZ6", 96.50, 6),
]


def normalize_symbol(raw):
    """Lucid's contract codes (MESU6, MNQZ6, ...) collapse to the underlying
    instrument: anything containing "ES" is ES, anything containing "NQ" is NQ."""
    if "NQ" in raw:
        return "NQ"
    if "ES" in raw:
        return "ES"
    return raw


def main():
    init_db()

    conn = get_connection()
    conn.execute("DELETE FROM trade_notes")
    conn.execute("DELETE FROM trades")
    conn.execute("DELETE FROM accounts")
    conn.commit()
    conn.close()

    account_id = create_account(ACCOUNT_NAME, STARTING_BALANCE, make_active=True)

    for date_str, symbol, pnl, qty in ROWS:
        entry_time = int(time.mktime(time.strptime(date_str, "%m/%d/%Y")))
        add_trade(
            symbol=normalize_symbol(symbol),
            side=None,
            contracts=qty,
            entry_price=None,
            entry_time=entry_time,
            exit_price=None,
            pnl_override=pnl,
            notes="",
            account_id=account_id,
        )
    print(f"Created account '{ACCOUNT_NAME}' (${STARTING_BALANCE:,.2f}) and imported {len(ROWS)} rows.")


if __name__ == "__main__":
    main()
