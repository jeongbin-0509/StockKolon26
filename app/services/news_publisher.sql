-- Executed by the application and pg_cron with the SAME transaction advisory lock.
-- __SCHEMA__ and __LOCK_ID__ are substituted from the validated Database object.
CREATE OR REPLACE FUNCTION __SCHEMA__.publish_due_news(
    p_now bigint DEFAULT floor(extract(epoch FROM clock_timestamp()))::bigint
) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER
SET search_path TO __SCHEMA__, pg_catalog
AS $publisher$
DECLARE
    saved automatic_news_state%ROWTYPE;
    article news_preset_catalog%ROWTYPE;
    visible_count integer;
    good_count integer;
    bad_count integer;
    directions text[];
    direction text;
    blocked bigint[];
    selected_club bigint;
    sequence_number bigint;
    article_key text;
    effective bigint;
    next_time bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(__LOCK_ID__);
    SELECT * INTO saved FROM automatic_news_state WHERE id=1;
    IF saved.next_at IS NOT NULL AND p_now < saved.next_at THEN RETURN false; END IF;
    sequence_number := coalesce(saved.published_count, 0);
    SELECT count(*) INTO visible_count FROM
        (SELECT id FROM news_articles ORDER BY published_at DESC, id DESC LIMIT 4) a;
    IF visible_count = 0 THEN
        directions := ARRAY['good', 'bad'];
    ELSE
        -- Keep the newest two. Replace/fill the other two while preserving the 2+2 balance.
        SELECT count(*) FILTER (WHERE impact > 0), count(*) FILTER (WHERE impact < 0)
        INTO good_count, bad_count FROM
            (SELECT impact FROM news_articles ORDER BY published_at DESC, id DESC LIMIT 2) a;
        directions := array_fill('good'::text, ARRAY[2-good_count]) ||
                      array_fill('bad'::text, ARRAY[2-bad_count]);
    END IF;
    SELECT array_agg(kind) INTO directions FROM
        (SELECT kind FROM unnest(directions) AS kind ORDER BY random() LIMIT 2) shuffled;
    SELECT coalesce(array_agg(target), ARRAY[]::bigint[]) INTO blocked FROM (
        (SELECT target FROM news_articles ORDER BY published_at DESC, id DESC LIMIT 4)
        UNION
        SELECT target FROM market_news WHERE target_kind='club' AND effective_at > p_now-3600
    ) unavailable;
    SELECT greatest(last_tick+30, (p_now/30)*30+30) INTO effective FROM market_state WHERE id=1;
    IF effective IS NULL THEN RAISE EXCEPTION 'Market state is not initialized'; END IF;
    FOREACH direction IN ARRAY directions LOOP
        SELECT club_num INTO selected_club FROM
            (SELECT DISTINCT club_num FROM news_preset_catalog
             WHERE sentiment=direction AND NOT (club_num=ANY(blocked))) candidates
            ORDER BY random() LIMIT 1;
        IF selected_club IS NULL THEN RAISE EXCEPTION 'No non-overlapping news target available'; END IF;
        SELECT * INTO STRICT article FROM news_preset_catalog
            WHERE club_num=selected_club AND sentiment=direction ORDER BY random() LIMIT 1;
        article_key := 'news-' || lpad(sequence_number::text, 12, '0') || '-' ||
                       md5(random()::text || clock_timestamp()::text);
        INSERT INTO market_news VALUES (article_key, 'club', article.club_num, article.impact, effective);
        INSERT INTO market_news_profiles VALUES (article_key, 2);
        INSERT INTO news_articles VALUES (article_key, article.title, article.body, 'club',
                                          article.club_num, article.impact, 'system', p_now);
        blocked := array_append(blocked, article.club_num);
        sequence_number := sequence_number + 1;
    END LOOP;
    next_time := CASE WHEN saved.next_at IS NULL THEN p_now+1800
        ELSE saved.next_at + ((p_now-saved.next_at)/1800+1)*1800 END;
    INSERT INTO automatic_news_state VALUES (1, next_time, sequence_number)
        ON CONFLICT(id) DO UPDATE SET next_at=excluded.next_at, published_count=excluded.published_count;
    RETURN true;
END;
$publisher$;
