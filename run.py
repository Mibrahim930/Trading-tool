"""Runs the news poller, AI scorer, Telegram alerter, and web dashboard together."""

import threading

from db import init_db
import app as app_module
import news_poller
import scorer
import telegram_alert


def main():
    init_db()
    threading.Thread(target=news_poller.poll_forever, daemon=True).start()
    threading.Thread(target=scorer.score_forever, daemon=True).start()
    threading.Thread(target=telegram_alert.alert_forever, daemon=True).start()
    app_module.app.run(port=5000)


if __name__ == "__main__":
    main()
