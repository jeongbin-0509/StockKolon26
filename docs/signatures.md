# Signatures and frames

Fourteen permanent achievements each unlock a matching leaderboard card frame. Settings can equip one signature and one frame independently, or unequip either. Frames decorate ranking cards (including My Position) and podium pedestal boxes, never avatar images. Settings previews use the same box decorations. PROLOGUE / ORIGIN is the default for every account. English display names are uppercase; the three Korean names follow the supplied names.

The private `cosmetic_profiles` table is created idempotently at app startup. It uses the existing persistent database, schema lock and transaction adapter. PostgreSQL RLS is enabled and PUBLIC / anon / authenticated privileges are revoked. Only the Flask session owner can equip unlocked items, with CSRF validation. Public member payloads expose only equipped style IDs and label, never tracking state or internal user IDs.

## Rules

- PRIME / APEX / SOVEREIGN: continuously hold school-wide total-asset rank <=30 / <=10 / 1 for 86,400 seconds. Competition ranks include ties. The asset calculation uses the same rounded current price as the leaderboard. Dropping below a threshold resets that timer, but never removes an earned award.
- 일찍 일어나는 새: a visible authenticated page visits during 03:00–03:59 Asia/Seoul. The server clock decides the hour; hidden tabs do not send visits.
- 추적자: improve by at least 200 ranks within a rolling 86,400-second window. A monotone maximum queue bounds the history while retaining possible worst ranks.
- 예언자: five consecutive sells with strictly positive realized profit. Buys do not reset the streak; zero or negative profit sells do. Cost allocation matches the existing partial-sale accounting. Replayed order IDs are never counted twice.
- ANCHOR: positive holdings in any one stock for 259,200 seconds. Adding shares and partial sales preserve the start; fully exiting resets it.
- SLAYER: a strictly profitable sell in a stock with an active negative news event. Uses `news_return(impact, age) < 0` and the actual quoted market tick, matching the price engine's club/sector targeting. It excludes future events and expired events. Currently the window is 120 × 30 seconds starting at `effective_at`; it is not an arbitrary period after article publication.

Historical achievements are not invented at rollout. Tracking starts when an account is first observed by this feature, including existing holdings. Every market tick, including offline catch-up, evaluates ranks in memory using a roster loaded once per transaction. Successful trades also evaluate before/after their cash and holding changes. New players are excluded from historical ticks before their first observation. Changed states are persisted as a batch. No additional scheduler or per-user polling query is required for rank tracking.

Validation: `python -m unittest discover -s tests -p test_cosmetics.py`; existing market, trading, ranking and route tests remain applicable. Disposable preview data is never part of production initialization.

Restored on 2026-11-27 without reverting connection pooling, read-only market snapshots, lazy charts, current-price execution or the five-minute school ranking cache. The collection GET also reads committed state without advancing prices. Ranking responses fetch equipped decorations in one batch after retrieving cached rank data, so an equipment change is visible immediately. Existing saved achievements and choices are retained.

## Companion collection

- LUCKY PAW / PAW PRINT: first sell with strictly positive realized profit after this addition. A loss, zero-profit sale or a replayed order cannot grant it.
- BUSY BEE / HONEYCOMB: visit a visible authenticated page on seven consecutive Asia/Seoul calendar dates. Repeated visits on one date count once; skipping a date resets the streak. Background market catch-up never counts as attendance. Earned rewards remain permanent.
- MOON BUNNY / MOONLIGHT: visit on three distinct Korean dates during 22:00–23:59. These dates need not be consecutive. Midnight is excluded and repeated visits count once per night. At most three dates are stored.
- CHERRY ON TOP / SUGAR GLAZE: observed school-wide rank 30 or higher, including ties and players already in the top 30. No 24-hour holding requirement.
- OCTO CLUB / OCTO GARDEN: simultaneously hold positive quantities in five distinct stocks. Existing qualifying holdings count on observation; fully sold or zero-quantity stocks do not. Selling later does not revoke the reward.

New attendance fields are optional JSON keys, so existing profiles and equipped items remain compatible with no schema migration. Server time is authoritative. Companion frames share the same card placement and reduced-motion controls as the original collection; illustrations are inline SVG, with no external asset downloads.
