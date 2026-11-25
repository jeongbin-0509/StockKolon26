from threading import Thread


def post_worker_init(worker):
    from app.services.market_worker import watch_market

    Thread(target=watch_market, args=(worker.wsgi,), name='market-tick', daemon=True).start()
