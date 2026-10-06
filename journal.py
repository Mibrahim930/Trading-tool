"""Manual trade journal: log entries, close trades, timestamped notes, and stats."""

import time
from collections import OrderedDict
from datetime import datetime

from db import get_connection

POINT_VALUE = {"ES": 50.0, "NQ": 20.0}
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

EDITABLE_FIELDS = ("symbol", "side", "contracts", "entry_price", "entry_time",
                   "exit_price", "exit_time", "pnl_override")


def add_trade(symbol=None, side=None, contracts=None, entry_price=None, entry_time=None,
              exit_price=None, exit_time=None, pnl_override=None, notes="", account_id=None):
    conn = get_connection()
    now = int(time.time())
    if entry_time is None:
        entry_time = now
    cur = conn.execute(
        """INSERT INTO trades (account_id, symbol, side, contracts, entry_price, entry_time,
                                exit_price, exit_time, pnl_override, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (account_id, symbol, side, contracts, entry_price, entry_time, exit_price, exit_time, pnl_override, notes),
    )
    trade_id = cur.lastrowid
    if notes:
        conn.execute(
            "INSERT INTO trade_notes (trade_id, note, created_at) VALUES (?, ?, ?)",
            (trade_id, notes, now),
        )
    conn.commit()
    conn.close()
    return trade_id


def update_trade(trade_id, **fields):
    """Replace any of EDITABLE_FIELDS wholesale (None clears the field) - used by the
    edit form, which always submits the trade's full current state."""
    cols = [k for k in fields if k in EDITABLE_FIELDS]
    if not cols:
        return
    conn = get_connection()
    set_clause = ", ".join(f"{c} = ?" for c in cols)
    values = [fields[c] for c in cols] + [trade_id]
    conn.execute(f"UPDATE trades SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def close_trade(trade_id, exit_price=None, pnl_override=None, exit_time=None):
    conn = get_connection()
    if exit_time is None:
        exit_time = int(time.time())
    conn.execute(
        "UPDATE trades SET exit_price = ?, exit_time = ?, pnl_override = COALESCE(?, pnl_override) WHERE id = ?",
        (exit_price, exit_time, pnl_override, trade_id),
    )
    conn.commit()
    conn.close()


def add_trade_note(trade_id, note):
    conn = get_connection()
    conn.execute(
        "INSERT INTO trade_notes (trade_id, note, created_at) VALUES (?, ?, ?)",
        (trade_id, note, int(time.time())),
    )
    conn.commit()
    conn.close()


def get_trade(trade_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    t = dict(row)
    t["pnl"] = compute_pnl(row)
    t["duration_seconds"] = compute_duration_seconds(row)
    return t


def compute_pnl(trade):
    if trade["pnl_override"] is not None:
        return trade["pnl_override"]
    if trade["entry_price"] is None or trade["exit_price"] is None or trade["contracts"] is None:
        return None
    point_value = POINT_VALUE.get(trade["symbol"], 1.0)
    direction = -1 if trade["side"] == "short" else 1
    return (trade["exit_price"] - trade["entry_price"]) * point_value * trade["contracts"] * direction


def compute_duration_seconds(trade):
    if trade["exit_time"] is None or trade["entry_time"] is None:
        return None
    return trade["exit_time"] - trade["entry_time"]


def _settled_time(trade):
    """The timestamp a closed trade is attributed to for sorting/grouping - its exit
    time when known, otherwise its entry time (all we have for imported P&L-only rows)."""
    return trade["exit_time"] if trade["exit_time"] is not None else trade["entry_time"]


def list_trade_notes(trade_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM trade_notes WHERE trade_id = ? ORDER BY created_at ASC", (trade_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _all_notes_by_trade():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM trade_notes ORDER BY created_at ASC").fetchall()
    conn.close()
    by_trade = {}
    for r in rows:
        by_trade.setdefault(r["trade_id"], []).append(dict(r))
    return by_trade


def list_trades(account_id=None):
    conn = get_connection()
    if account_id is None:
        rows = conn.execute("SELECT * FROM trades ORDER BY entry_time DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM trades WHERE account_id = ? ORDER BY entry_time DESC", (account_id,)
        ).fetchall()
    conn.close()
    notes_by_trade = _all_notes_by_trade()
    trades = []
    for row in rows:
        t = dict(row)
        t["pnl"] = compute_pnl(row)
        t["duration_seconds"] = compute_duration_seconds(row)
        t["timeline"] = notes_by_trade.get(row["id"], [])
        trades.append(t)
    return trades


def compute_stats(trades, starting_balance=0.0):
    closed = [t for t in trades if t["pnl"] is not None and _settled_time(t) is not None]
    closed.sort(key=_settled_time)

    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] < 0]
    breakeven = [t for t in closed if t["pnl"] == 0]

    daily_pnl = OrderedDict()
    for t in closed:
        day = datetime.fromtimestamp(_settled_time(t)).strftime("%Y-%m-%d")
        daily_pnl[day] = daily_pnl.get(day, 0) + t["pnl"]

    # equity_curve tracks account balance over time, starting from the account's
    # starting_balance rather than 0, so it lines up with what the broker shows.
    equity_curve = []
    running = starting_balance
    for t in closed:
        running += t["pnl"]
        equity_curve.append({"time": _settled_time(t), "equity": running})

    total_trades = len(closed)

    avg_win = (sum(t["pnl"] for t in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss else (gross_win if gross_win else 0.0)

    best_trade = max(closed, key=lambda t: t["pnl"]) if closed else None
    worst_trade = min(closed, key=lambda t: t["pnl"]) if closed else None

    durations = [t["duration_seconds"] for t in closed if t["duration_seconds"]]
    avg_duration = (sum(durations) / len(durations)) if durations else 0

    # streaks (chronological)
    longest_win_streak = longest_loss_streak = cur_streak = 0
    cur_type = None
    streak_series = []
    for t in closed:
        kind = "win" if t["pnl"] > 0 else ("loss" if t["pnl"] < 0 else "flat")
        if kind == cur_type:
            cur_streak += 1
        else:
            cur_type = kind
            cur_streak = 1
        if kind == "win":
            longest_win_streak = max(longest_win_streak, cur_streak)
        elif kind == "loss":
            longest_loss_streak = max(longest_loss_streak, cur_streak)
        streak_series.append({"time": _settled_time(t), "streak": cur_streak if kind == "win" else -cur_streak})

    current_streak = 0
    current_streak_type = None
    if closed:
        current_streak_type = "win" if closed[-1]["pnl"] > 0 else ("loss" if closed[-1]["pnl"] < 0 else "flat")
        for t in reversed(closed):
            kind = "win" if t["pnl"] > 0 else ("loss" if t["pnl"] < 0 else "flat")
            if kind == current_streak_type:
                current_streak += 1
            else:
                break

    by_symbol = OrderedDict()
    for t in closed:
        s = by_symbol.setdefault(t["symbol"] or "Unspecified", {"pnl": 0.0, "count": 0, "wins": 0})
        s["pnl"] += t["pnl"]
        s["count"] += 1
        if t["pnl"] > 0:
            s["wins"] += 1

    by_side = OrderedDict()
    for t in closed:
        s = by_side.setdefault(t["side"] or "unspecified", {"pnl": 0.0, "count": 0, "wins": 0})
        s["pnl"] += t["pnl"]
        s["count"] += 1
        if t["pnl"] > 0:
            s["wins"] += 1

    by_weekday = OrderedDict((name, {"pnl": 0.0, "count": 0}) for name in WEEKDAY_NAMES)
    for t in closed:
        name = WEEKDAY_NAMES[datetime.fromtimestamp(_settled_time(t)).weekday()]
        by_weekday[name]["pnl"] += t["pnl"]
        by_weekday[name]["count"] += 1

    total_pnl = sum(t["pnl"] for t in closed)

    return {
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": (len(wins) / total_trades * 100) if total_trades else 0,
        "total_pnl": total_pnl,
        "starting_balance": starting_balance,
        "account_balance": starting_balance + total_pnl,
        "days_traded": len(daily_pnl),
        "days_won": sum(1 for v in daily_pnl.values() if v > 0),
        "days_lost": sum(1 for v in daily_pnl.values() if v < 0),
        "daily_pnl": [{"date": d, "pnl": v} for d, v in daily_pnl.items()],
        "equity_curve": equity_curve,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "avg_duration": avg_duration,
        "longest_win_streak": longest_win_streak,
        "longest_loss_streak": longest_loss_streak,
        "current_streak": current_streak,
        "current_streak_type": current_streak_type,
        "streak_series": streak_series,
        "by_symbol": by_symbol,
        "by_side": by_side,
        "by_weekday": by_weekday,
        "open_trades": sum(1 for t in trades if t["pnl"] is None),
    }


STAT_KEYS = {"balance", "pnl", "winrate", "trades", "days", "avgtrade", "streak"}


def compute_stat_detail(key, stats):
    """Build a self-contained detail payload (hero value + chart configs) for one stat card."""
    fmt_money = lambda v: f"${v:,.2f}"

    if key == "balance":
        return {
            "key": key,
            "eyebrow": "Account",
            "title": "Account Balance",
            "subtitle": "Starting balance plus every closed trade's P&L, in order.",
            "hero_value": fmt_money(stats["account_balance"]),
            "hero_class": "pos" if stats["total_pnl"] > 0 else ("neg" if stats["total_pnl"] < 0 else ""),
            "stat_cards": [
                {"label": "Starting balance", "value": fmt_money(stats["starting_balance"]), "cls": ""},
                {"label": "Total P&L", "value": fmt_money(stats["total_pnl"]),
                 "cls": "pos" if stats["total_pnl"] > 0 else ("neg" if stats["total_pnl"] < 0 else "")},
                {"label": "Days traded", "value": str(stats["days_traded"]), "cls": ""},
                {"label": "Total trades", "value": str(stats["total_trades"]), "cls": ""},
            ],
            "charts": [
                {"id": "c1", "type": "line", "title": "Balance Over Time",
                 "labels": [datetime.fromtimestamp(p["time"]).strftime("%b %d") for p in stats["equity_curve"]],
                 "datasets": [{"data": [p["equity"] for p in stats["equity_curve"]], "color": "accent", "fill": True}]},
                {"id": "c2", "type": "bar", "title": "Daily P&L",
                 "labels": [d["date"][5:] for d in stats["daily_pnl"]],
                 "datasets": [{"data": [d["pnl"] for d in stats["daily_pnl"]], "colorByValue": True}]},
            ],
        }

    if key == "pnl":
        return {
            "key": key,
            "eyebrow": "Performance",
            "title": "Total P&L",
            "subtitle": "Cumulative realized profit and loss across every closed trade.",
            "hero_value": fmt_money(stats["total_pnl"]),
            "hero_class": "pos" if stats["total_pnl"] > 0 else ("neg" if stats["total_pnl"] < 0 else ""),
            "stat_cards": [
                {"label": "Gross avg win", "value": fmt_money(stats["avg_win"]), "cls": "pos"},
                {"label": "Gross avg loss", "value": fmt_money(stats["avg_loss"]), "cls": "neg"},
                {"label": "Profit factor", "value": f"{stats['profit_factor']:.2f}", "cls": ""},
                {"label": "Days traded", "value": str(stats["days_traded"]), "cls": ""},
            ],
            "charts": [
                {"id": "c1", "type": "line", "title": "Equity Curve",
                 "labels": [datetime.fromtimestamp(p["time"]).strftime("%b %d") for p in stats["equity_curve"]],
                 "datasets": [{"data": [p["equity"] for p in stats["equity_curve"]], "color": "accent", "fill": True}]},
                {"id": "c2", "type": "bar", "title": "Daily P&L",
                 "labels": [d["date"][5:] for d in stats["daily_pnl"]],
                 "datasets": [{"data": [d["pnl"] for d in stats["daily_pnl"]], "colorByValue": True}]},
            ],
        }

    if key == "winrate":
        return {
            "key": key,
            "eyebrow": "Consistency",
            "title": "Win Rate",
            "subtitle": "Share of closed trades that ended profitable.",
            "hero_value": f"{stats['win_rate']:.0f}%",
            "hero_class": "",
            "stat_cards": [
                {"label": "Wins", "value": str(stats["wins"]), "cls": "pos"},
                {"label": "Losses", "value": str(stats["losses"]), "cls": "neg"},
                {"label": "Breakeven", "value": str(stats["breakeven"]), "cls": ""},
                {"label": "Total trades", "value": str(stats["total_trades"]), "cls": ""},
            ],
            "charts": [
                {"id": "c1", "type": "doughnut", "title": "Win / Loss / Breakeven",
                 "labels": ["Wins", "Losses", "Breakeven"],
                 "datasets": [{"data": [stats["wins"], stats["losses"], stats["breakeven"]],
                               "colors": ["bull", "bear", "low"]}]},
                {"id": "c2", "type": "bar", "title": "By Symbol — Win Count",
                 "labels": list(stats["by_symbol"].keys()),
                 "datasets": [{"data": [v["wins"] for v in stats["by_symbol"].values()], "color": "bull"}]},
            ],
        }

    if key == "trades":
        return {
            "key": key,
            "eyebrow": "Activity",
            "title": "Total Trades",
            "subtitle": "Volume of trades taken, broken down by instrument and direction.",
            "hero_value": str(stats["total_trades"]),
            "hero_class": "",
            "stat_cards": [
                {"label": "Open trades", "value": str(stats["open_trades"]), "cls": ""},
                {"label": "Symbols traded", "value": str(len(stats["by_symbol"])), "cls": ""},
                {"label": "Longs", "value": str(stats["by_side"].get("long", {}).get("count", 0)), "cls": ""},
                {"label": "Shorts", "value": str(stats["by_side"].get("short", {}).get("count", 0)), "cls": ""},
            ],
            "charts": [
                {"id": "c1", "type": "bar", "title": "P&L by Symbol",
                 "labels": list(stats["by_symbol"].keys()),
                 "datasets": [{"data": [v["pnl"] for v in stats["by_symbol"].values()], "colorByValue": True}]},
                {"id": "c2", "type": "bar", "title": "P&L: Long vs Short",
                 "labels": list(stats["by_side"].keys()),
                 "datasets": [{"data": [v["pnl"] for v in stats["by_side"].values()], "colorByValue": True}]},
            ],
        }

    if key == "days":
        return {
            "key": key,
            "eyebrow": "Rhythm",
            "title": "Days Traded",
            "subtitle": "How results are distributed across the days you were active.",
            "hero_value": str(stats["days_traded"]),
            "hero_class": "",
            "stat_cards": [
                {"label": "Days won", "value": str(stats["days_won"]), "cls": "pos"},
                {"label": "Days lost", "value": str(stats["days_lost"]), "cls": "neg"},
                {"label": "Best day", "value": fmt_money(max((d["pnl"] for d in stats["daily_pnl"]), default=0)), "cls": "pos"},
                {"label": "Worst day", "value": fmt_money(min((d["pnl"] for d in stats["daily_pnl"]), default=0)), "cls": "neg"},
            ],
            "charts": [
                {"id": "c1", "type": "bar", "title": "Daily P&L",
                 "labels": [d["date"] for d in stats["daily_pnl"]],
                 "datasets": [{"data": [d["pnl"] for d in stats["daily_pnl"]], "colorByValue": True}]},
                {"id": "c2", "type": "bar", "title": "P&L by Weekday",
                 "labels": list(stats["by_weekday"].keys()),
                 "datasets": [{"data": [v["pnl"] for v in stats["by_weekday"].values()], "colorByValue": True}]},
            ],
        }

    if key == "avgtrade":
        best = stats["best_trade"]
        worst = stats["worst_trade"]
        return {
            "key": key,
            "eyebrow": "Edge",
            "title": "Avg Win / Avg Loss",
            "subtitle": "The shape of a typical winner versus a typical loser.",
            "hero_value": f"{stats['profit_factor']:.2f}",
            "hero_class": "pos" if stats["profit_factor"] >= 1 else "neg",
            "stat_cards": [
                {"label": "Avg win", "value": fmt_money(stats["avg_win"]), "cls": "pos"},
                {"label": "Avg loss", "value": fmt_money(stats["avg_loss"]), "cls": "neg"},
                {"label": "Best trade", "value": fmt_money(best["pnl"]) if best else "-", "cls": "pos"},
                {"label": "Worst trade", "value": fmt_money(worst["pnl"]) if worst else "-", "cls": "neg"},
            ],
            "charts": [
                {"id": "c1", "type": "bar", "title": "Avg Win vs Avg Loss",
                 "labels": ["Avg Win", "Avg Loss"],
                 "datasets": [{"data": [stats["avg_win"], stats["avg_loss"]], "colorByValue": True}]},
            ],
        }

    if key == "streak":
        return {
            "key": key,
            "eyebrow": "Momentum",
            "title": "Current Streak",
            "subtitle": "Consecutive wins or losses, and the longest runs on record.",
            "hero_value": f"{stats['current_streak']} {stats['current_streak_type'] or ''}".strip(),
            "hero_class": "pos" if stats["current_streak_type"] == "win" else ("neg" if stats["current_streak_type"] == "loss" else ""),
            "stat_cards": [
                {"label": "Longest win streak", "value": str(stats["longest_win_streak"]), "cls": "pos"},
                {"label": "Longest loss streak", "value": str(stats["longest_loss_streak"]), "cls": "neg"},
                {"label": "Avg trade duration", "value": _fmt_dur(stats["avg_duration"]), "cls": ""},
                {"label": "Total trades", "value": str(stats["total_trades"]), "cls": ""},
            ],
            "charts": [
                {"id": "c1", "type": "bar", "title": "Streak Over Time (+win / -loss)",
                 "labels": [datetime.fromtimestamp(p["time"]).strftime("%b %d") for p in stats["streak_series"]],
                 "datasets": [{"data": [p["streak"] for p in stats["streak_series"]], "colorByValue": True}]},
            ],
        }

    return None


def _fmt_dur(seconds):
    if not seconds:
        return "-"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {sec}s"
