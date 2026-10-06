"""Web dashboard: scored news feed, full-text search, and manual trade journal."""

import json
import time

from flask import Flask, abort, redirect, render_template, request, url_for

from accounts import create_account, get_active_account, list_accounts, set_active_account, update_account
from db import get_connection, init_db
from journal import (
    add_trade,
    add_trade_note,
    close_trade,
    compute_stat_detail,
    compute_stats,
    list_trades,
    update_trade,
    STAT_KEYS,
)

app = Flask(__name__)

SEARCH_LIMIT = 200


@app.context_processor
def inject_active_account():
    return {"active_account": get_active_account()}


def _opt_str(form, key):
    val = form.get(key, "").strip()
    return val or None


def _opt_int(form, key):
    val = form.get(key, "").strip()
    return int(val) if val else None


def _opt_float(form, key):
    val = form.get(key, "").strip()
    return float(val) if val else None


def _opt_date(form, key):
    val = form.get(key, "").strip()
    return int(time.mktime(time.strptime(val, "%Y-%m-%d"))) if val else None


@app.template_filter("fmt_time")
def fmt_time(unix_ts):
    if unix_ts is None:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(unix_ts))


@app.template_filter("fmt_date")
def fmt_date(unix_ts):
    if unix_ts is None:
        return "-"
    return time.strftime("%Y-%m-%d", time.localtime(unix_ts))


@app.template_filter("fmt_clock")
def fmt_clock(unix_ts):
    if unix_ts is None:
        return "-"
    return time.strftime("%b %d, %H:%M", time.localtime(unix_ts))


@app.template_filter("fmt_duration")
def fmt_duration(seconds):
    if seconds is None:
        return "-"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {sec}s"


@app.route("/")
def dashboard():
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM news WHERE scored_at IS NOT NULL
           ORDER BY published_at DESC LIMIT 100"""
    ).fetchall()
    conn.close()
    return render_template("dashboard.html", news=rows)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    impact = request.args.get("impact", "")
    direction = request.args.get("direction", "")
    affects = request.args.get("affects", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    clauses = ["scored_at IS NOT NULL"]
    params = []

    if q:
        clauses.append("(headline LIKE ? OR summary LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    if impact:
        clauses.append("impact = ?")
        params.append(impact)
    if direction:
        clauses.append("direction = ?")
        params.append(direction)
    if affects:
        clauses.append("affects = ?")
        params.append(affects)
    if date_from:
        clauses.append("published_at >= ?")
        params.append(int(time.mktime(time.strptime(date_from, "%Y-%m-%d"))))
    if date_to:
        clauses.append("published_at < ?")
        params.append(int(time.mktime(time.strptime(date_to, "%Y-%m-%d"))) + 86400)

    sql = f"SELECT * FROM news WHERE {' AND '.join(clauses)} ORDER BY published_at DESC LIMIT {SEARCH_LIMIT}"

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return render_template(
        "search.html", news=rows, q=q, impact=impact, direction=direction, affects=affects,
        date_from=date_from, date_to=date_to, result_limit=SEARCH_LIMIT,
    )


@app.route("/news/<int:news_id>")
def news_detail(news_id):
    conn = get_connection()
    item = conn.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if item is None:
        conn.close()
        abort(404)
    prev_item = conn.execute(
        """SELECT id, headline FROM news WHERE scored_at IS NOT NULL AND published_at > ?
           ORDER BY published_at ASC LIMIT 1""",
        (item["published_at"],),
    ).fetchone()
    next_item = conn.execute(
        """SELECT id, headline FROM news WHERE scored_at IS NOT NULL AND published_at < ?
           ORDER BY published_at DESC LIMIT 1""",
        (item["published_at"],),
    ).fetchone()
    conn.close()
    return render_template("news_detail.html", item=item, prev_item=prev_item, next_item=next_item)


@app.route("/journal")
def journal():
    """Trade Journal: an Apple-style scrolling story of stats, ending in an overview."""
    active = get_active_account()
    trades = list_trades(active["id"]) if active else []
    stats = compute_stats(trades, starting_balance=active["starting_balance"] if active else 0.0)
    return render_template("journal.html", stats=stats, stats_json=json.dumps(stats))


@app.route("/journal/stat/<key>")
def journal_stat(key):
    if key not in STAT_KEYS:
        abort(404)
    active = get_active_account()
    trades = list_trades(active["id"]) if active else []
    stats = compute_stats(trades, starting_balance=active["starting_balance"] if active else 0.0)
    detail = compute_stat_detail(key, stats)
    if detail is None:
        abort(404)
    return render_template("stat_detail.html", detail=detail, detail_json=json.dumps(detail))


@app.route("/journal/entries")
def journal_entries():
    """Trade Entries: log new trades, close them, and add timestamped notes."""
    active = get_active_account()
    trades = list_trades(active["id"]) if active else []
    return render_template("journal_entries.html", trades=trades)


@app.route("/journal/new", methods=["POST"])
def journal_new():
    form = request.form
    active = get_active_account()
    add_trade(
        symbol=_opt_str(form, "symbol"),
        side=_opt_str(form, "side"),
        contracts=_opt_int(form, "contracts"),
        entry_price=_opt_float(form, "entry_price"),
        entry_time=_opt_date(form, "entry_date"),
        exit_price=_opt_float(form, "exit_price"),
        pnl_override=_opt_float(form, "pnl"),
        notes=form.get("notes", "").strip(),
        account_id=active["id"] if active else None,
    )
    return redirect(url_for("journal_entries"))


@app.route("/journal/close/<int:trade_id>", methods=["POST"])
def journal_close(trade_id):
    form = request.form
    close_trade(
        trade_id,
        exit_price=_opt_float(form, "exit_price"),
        pnl_override=_opt_float(form, "pnl"),
    )
    return redirect(url_for("journal_entries"))


@app.route("/journal/edit/<int:trade_id>", methods=["POST"])
def journal_edit(trade_id):
    form = request.form
    update_trade(
        trade_id,
        symbol=_opt_str(form, "symbol"),
        side=_opt_str(form, "side"),
        contracts=_opt_int(form, "contracts"),
        entry_price=_opt_float(form, "entry_price"),
        entry_time=_opt_date(form, "entry_date"),
        exit_price=_opt_float(form, "exit_price"),
        exit_time=_opt_date(form, "exit_date"),
        pnl_override=_opt_float(form, "pnl"),
    )
    return redirect(url_for("journal_entries"))


@app.route("/journal/note/<int:trade_id>", methods=["POST"])
def journal_note(trade_id):
    note = request.form.get("note", "").strip()
    if note:
        add_trade_note(trade_id, note)
    return redirect(url_for("journal_entries"))


@app.route("/accounts")
def accounts_page():
    return render_template("accounts.html", accounts=list_accounts())


@app.route("/accounts/new", methods=["POST"])
def accounts_new():
    form = request.form
    name = _opt_str(form, "name") or "Trading Account"
    starting_balance = _opt_float(form, "starting_balance") or 0.0
    create_account(name, starting_balance, make_active=True)
    return redirect(url_for("accounts_page"))


@app.route("/accounts/activate/<int:account_id>", methods=["POST"])
def accounts_activate(account_id):
    set_active_account(account_id)
    return redirect(url_for("accounts_page"))


@app.route("/accounts/edit/<int:account_id>", methods=["POST"])
def accounts_edit(account_id):
    form = request.form
    update_account(
        account_id,
        name=_opt_str(form, "name"),
        starting_balance=_opt_float(form, "starting_balance"),
    )
    return redirect(url_for("accounts_page"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
