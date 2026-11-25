from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter


database_timings = ContextVar('database_timings', default=None)


@contextmanager
def collect_timings():
    timings = {}
    token = database_timings.set(timings)
    try:
        yield timings
    finally:
        database_timings.reset(token)


@contextmanager
def measure(stage):
    timings = database_timings.get()
    if timings is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        duration = (perf_counter() - started) * 1000
        timings[stage] = timings.get(stage, 0) + duration


def format_timings(timings):
    return ', '.join(f'{stage};dur={duration:.2f}' for stage, duration in timings.items())
