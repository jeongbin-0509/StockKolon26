import time

from app.logics.logic import TICK_SECONDS


def watch_market(app):
    market = app.extensions['market']
    while True:
        try:
            if app.config['AUTO_NEWS_ENABLED'] and not market.store.postgres:
                app.extensions['admin'].publish_due_automatic_news()
            _, catching_up = market.advance()
            delay = 1 if catching_up else TICK_SECONDS - market.clock() % TICK_SECONDS
        except Exception:
            app.logger.exception('정기 시세 갱신 실패')
            delay = 5
        time.sleep(delay)
