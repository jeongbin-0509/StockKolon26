import time

from app.logics.logic import TICK_SECONDS
from app.services.database_timing import collect_timings, format_timings, measure


def watch_market(app):
    market = app.extensions['market']
    while True:
        try:
            if app.config['AUTO_NEWS_ENABLED'] and not market.store.postgres:
                app.extensions['admin'].publish_due_automatic_news()
            with collect_timings() as timings:
                try:
                    with measure('worker'):
                        _, catching_up = market.advance()
                finally:
                    if market.store.postgres:
                        app.logger.info('market_db_timing %s', format_timings(timings))
            delay = 1 if catching_up else TICK_SECONDS - market.clock() % TICK_SECONDS
        except Exception:
            app.logger.exception('정기 시세 갱신 실패')
            delay = 5
        time.sleep(delay)


def watch_school_ranking(app):
    ranking = app.extensions['ranking']
    while True:
        try:
            ranking.refresh_school()
        except Exception:
            app.logger.exception('전교 순위 갱신 실패')
        time.sleep(300 - time.time() % 300)
