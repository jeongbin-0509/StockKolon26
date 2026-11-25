from threading import Thread


def post_worker_init(worker):
    from app.services.market_worker import watch_market, watch_school_ranking

    Thread(target=watch_market, args=(worker.wsgi,), name='market-tick', daemon=True).start()
    Thread(target=watch_school_ranking, args=(worker.wsgi,), name='school-ranking', daemon=True).start()
