# Signatures and frames

Nine permanent achievements each unlock a matching avatar frame. Settings can equip one signature and one frame independently, or unequip either. PROLOGUE / ORIGIN is the default for every account. English display names are uppercase; the three Korean names follow the supplied names.

The private `cosmetic_profiles` table is created idempotently at app startup. It uses the existing persistent database, schema lock and transaction adapter. PostgreSQL RLS is enabled and PUBLIC / anon / authenticated privileges are revoked. Only the Flask session owner can equip unlocked items, with CSRF validation. Public member payloads expose only equipped style IDs and label, never tracking state or internal user IDs.

## Rules

- PRIME / APEX / SOVEREIGN: continuously hold school-wide total-asset rank <=30 / <=10 / 1 for 86,400 seconds. Competition ranks include ties. The asset calculation uses the same rounded sell quote as the leaderboard. Dropping below a threshold resets that timer, but never removes an earned award.
- 일찍 일어나는 새: a visible authenticated page visits during 03:00–03:59 Asia/Seoul. The server clock decides the hour; hidden tabs do not send visits.
- 추적자: improve by at least 200 ranks within a rolling 86,400-second window. A monotone maximum queue bounds the history while retaining possible worst ranks.
- 예언자: five consecutive sells with strictly positive realized profit. Buys do not reset the streak; zero or negative profit sells do. Cost allocation matches the existing partial-sale accounting. Replayed order IDs are never counted twice.
- ANCHOR: positive holdings in any one stock for 259,200 seconds. Adding shares and partial sales preserve the start; fully exiting resets it.
- SLAYER: a strictly profitable sell in a stock with an active negative news event. Uses `news_return(impact, age) < 0` and the actual quoted market tick, matching the price engine's club/sector targeting. It excludes future events and expired events. Currently the window is 120 × 30 seconds starting at `effective_at`; it is not an arbitrary period after article publication.

Historical achievements are not invented at rollout. Tracking starts when an account is first observed by this feature, including existing holdings. Every market tick, including offline catch-up, evaluates ranks in memory using a roster loaded once per transaction. Successful trades also evaluate before/after their cash and holding changes. New players are excluded from historical ticks before their first observation. Changed states are persisted as a batch. No additional scheduler or per-user polling query is required for rank tracking.

Validation: `python -m unittest discover -s tests -p test_cosmetics.py`; existing market, trading, ranking and route tests remain applicable. Disposable preview data is never part of production initialization.
