from threading import Thread


def post_worker_init(worker):
    from app.services.market_worker import watch_market, watch_school_ranking

    worker.wsgi.logger.setLevel(worker.log.error_log.level)
    worker.wsgi.extensions['market'].store.open_pool()
    Thread(target=watch_market, args=(worker.wsgi,), name='market-tick', daemon=True).start()
    Thread(target=watch_school_ranking, args=(worker.wsgi,), name='school-ranking', daemon=True).start()


def worker_exit(server, worker):
    if getattr(worker, 'wsgi', None) is not None:
        worker.wsgi.extensions['market'].store.close_pool()
