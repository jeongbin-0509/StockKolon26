"""DB-owned news timer: continues while the web process is stopped or idle."""

from pathlib import Path
from app.news_catalog import news_presets
from app.services.database import DatabaseError


def publisher_sql(store):
    # Database validates schema as [a-z][a-z0-9_]{0,62}; neither value comes from a request.
    return (Path(__file__).with_name('news_publisher.sql').read_text(encoding='utf-8')
            .replace('__SCHEMA__', f'"{store.schema}"')
            .replace('__LOCK_ID__', str(store.lock_id)))


def install_publisher(db, store):
    """Install the same private publisher used by HTTP requests and the DB timer."""
    db.execute('CREATE TABLE IF NOT EXISTS news_preset_catalog ('
               'id TEXT PRIMARY KEY, club_num BIGINT NOT NULL, sentiment TEXT NOT NULL, '
               'title TEXT NOT NULL, body TEXT NOT NULL, impact DOUBLE PRECISION NOT NULL)')
    db.execute('ALTER TABLE news_preset_catalog ENABLE ROW LEVEL SECURITY')
    db.execute('REVOKE ALL ON news_preset_catalog FROM PUBLIC')
    presets = news_presets()
    db.execute('DELETE FROM news_preset_catalog')
    db.executemany('INSERT INTO news_preset_catalog VALUES (?, ?, ?, ?, ?, ?)',
                   [(p['id'], p['club_num'], p['sentiment'], p['title'], p['body'], p['impact']) for p in presets])
    db.raw.execute(publisher_sql(store))
    db.execute('REVOKE ALL ON FUNCTION publish_due_news(bigint) FROM PUBLIC')


def install_schedule(market):
    """Called on production startup only. Fail explicitly if Cron cannot be installed."""
    store = market.store
    job_name = f'{store.schema}-news-pairs'
    command = (f'SELECT "{store.schema}".publish_due_news(); '
               "DELETE FROM cron.job_run_details WHERE jobid = "
               f"(SELECT jobid FROM cron.job WHERE jobname='{job_name}' AND username=current_user) "
               "AND end_time < now() - interval '7 days';")
    try:
        with market.connection(write=True) as db:
            db.execute('CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog')
            db.execute("SELECT cron.schedule(?, '30 seconds', ?)", (job_name, command))
            job = db.execute('SELECT active, schedule, command FROM cron.job '
                             'WHERE jobname=? AND username=current_user', (job_name,)).fetchone()
            if not job or not job['active'] or job['schedule'] != '30 seconds' or job['command'] != command:
                raise RuntimeError('뉴스 자동 발행 예약 작업을 확인하지 못했습니다.')
    except DatabaseError:
        raise RuntimeError('뉴스 자동 발행 예약 실패: Supabase Cron(pg_cron) 활성화 및 DB 계정의 작업 등록 권한을 확인하세요.') from None
