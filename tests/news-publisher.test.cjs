// Optional real PostgreSQL engine validation without connecting to hosted data.
// PGLITE_TEST_MODULE=/absolute/path/to/@electric-sql/pglite/dist/index.cjs node --test tests/news-publisher.test.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const modulePath = process.env.PGLITE_TEST_MODULE;

test('Postgres publisher: idle scheduling, two-card warmup, balance, atomicity and price events',
  {skip: !modulePath}, async () => {
    const {PGlite} = require(modulePath);
    const db = new PGlite();
    try {
      await db.exec(`CREATE SCHEMA news_test; SET search_path TO news_test, pg_catalog;
        CREATE TABLE market_state(id bigint primary key,last_tick bigint);
        INSERT INTO market_state VALUES(1,1800000000);
        CREATE TABLE automatic_news_state(id bigint primary key,next_at bigint,published_count bigint);
        CREATE TABLE news_articles(id text primary key,title text,body text,target_kind text,target bigint,impact double precision,author_id text,published_at bigint);
        CREATE TABLE market_news(event_id text primary key,target_kind text,target bigint,impact double precision,effective_at bigint);
        CREATE TABLE market_news_profiles(event_id text primary key,profile bigint);
        CREATE TABLE news_preset_catalog(id text primary key,club_num bigint,sentiment text,title text,body text,impact double precision);`);
      const presets = JSON.parse(fs.readFileSync(path.join(root,'app/data/news_presets.json'),'utf8'));
      await db.query(`INSERT INTO news_preset_catalog SELECT id,club_num,sentiment,title,body,impact
        FROM jsonb_to_recordset($1::jsonb) AS p(id text,club_num bigint,sentiment text,title text,body text,impact double precision)`, [JSON.stringify(presets)]);
      const sql = fs.readFileSync(path.join(root,'app/services/news_publisher.sql'),'utf8')
        .replaceAll('__SCHEMA__','"news_test"').replaceAll('__LOCK_ID__','42');
      await db.exec(sql);
      const publish = async now => (await db.query('SELECT publish_due_news($1) AS done',[now])).rows[0].done;
      const feed = async () => (await db.query('SELECT * FROM news_articles ORDER BY published_at DESC,id DESC LIMIT 4')).rows;
      const balanced = rows => {
        assert.equal(rows.length,4);
        assert.equal(rows.filter(r=>r.impact>0).length,2);
        assert.equal(new Set(rows.map(r=>r.target)).size,4);
      };
      let now=1800000000;
      assert.equal(await publish(now),true);
      let rows=await feed();
      assert.equal(rows.length,2);
      assert.equal(rows.filter(r=>r.impact>0).length,1);
      assert.equal(await publish(now+1799),false);
      now+=1800;
      assert.equal(await publish(now),true);
      balanced(await feed());
      // No Flask app or visitor exists: invoke exactly the SQL used by the Cron job.
      for(let i=0;i<40;i++) {
        const before=await feed();
        now+=1800;
        assert.equal(await publish(now),true);
        assert.equal(await publish(now),false);
        const after=await feed(); balanced(after);
        assert.deepEqual(after.slice(2).map(r=>r.id),before.slice(0,2).map(r=>r.id));
        for(const row of after.slice(0,2)) assert(!before.some(old=>old.target===row.target));
      }
      const mismatches=await db.query(`SELECT count(*)::int AS n FROM news_articles a
        JOIN market_news n ON a.id=n.event_id JOIN market_news_profiles p ON p.event_id=a.id
        WHERE a.target<>n.target OR a.impact<>n.impact OR n.effective_at<>(a.published_at/30)*30+30 OR p.profile<>2`);
      assert.equal(mismatches.rows[0].n,0);
      const eventCount=(await db.query('SELECT count(*)::int AS n FROM market_news')).rows[0].n;
      assert.equal(eventCount,84);
      // A delayed wakeup retains the original cadence instead of drifting on every run.
      now+=1813;
      await publish(now);
      assert.equal(Number((await db.query('SELECT next_at FROM automatic_news_state')).rows[0].next_at),now-13+1800);
      const saved=await feed();
      await db.exec('BEGIN; DELETE FROM news_preset_catalog;');
      await assert.rejects(publish(now+1800), /No non-overlapping/);
      await db.exec('ROLLBACK;');
      assert.deepEqual(await feed(),saved);
      // Restarting/upgrading the function preserves the existing feed and timer.
      await db.exec(sql);
      assert.deepEqual(await feed(),saved);
      assert.equal(await publish(now),false);
      assert.equal((await db.query("SELECT prosecdef FROM pg_proc WHERE proname='publish_due_news'")).rows[0].prosecdef,false);
    } finally { await db.close(); }
  });
