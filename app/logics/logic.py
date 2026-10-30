"""30초 단위 모의시장. I/O 없이 이전 상태와 입력으로 다음 상태를 계산한다.

수치는 실제 시장 추정치가 아닌 게임 초기 설정이다. 내부 가격은 소수점을 유지한다.
상승 횟수나 미래 경로를 미리 정하지 않는다.
"""

import math

TICK_SECONDS = 30
CANDLE_SECONDS = 300
NEWS_TICKS = 120
MAX_LOG_RETURN = math.log1p(0.01)
MARKET_MEMORY = 0.72
MARKET_SHOCK = 0.00009
SECTOR_MEMORY = 0.58
SECTOR_SHOCK = 0.00014
TREND_MEMORY = 0.86
TREND_SHOCK = 0.000045
INDIVIDUAL_SHOCK = 0.00018
FLOW_MAX_LOG_RETURN = 0.0008
FLOW_LIQUIDITY_SHARES = 1200
RANDOM_EVENT_PROBABILITY = 1 / 40  # 진행 중인 이벤트가 없을 때 틱당 2.5%
RANDOM_EVENT_MIN_TICKS = 6
RANDOM_EVENT_MAX_TICKS = 12
RANDOM_EVENT_MIN_RETURN = 0.02
RANDOM_EVENT_MAX_RETURN = 0.04


def news_return(impact, age):
    """한 이벤트의 유한한 로그수익률 예산: 첫 틱 60%, 이후 119틱 40%."""
    if age < 0 or age >= NEWS_TICKS:
        return 0.0
    budget = math.log1p(impact)
    if age == 0:
        return budget * 0.6
    decay = 0.94
    normalizer = (1 - decay ** (NEWS_TICKS - 1)) / (1 - decay)
    return budget * 0.4 * decay ** (age - 1) / normalizer


def next_tick(stocks, state, news, flows, rng):
    """stocks={번호: 내부가격}, news={번호: 이번 틱 뉴스 로그수익률}.

    flows는 서버 상대 체결의 유저 순매수 주식 수다. 전체 체결 양쪽의 합이 아니다.
    한 틱 최대 변동을 넘는 영향은 소진하며 나중에 보장 수익으로 이월하지 않는다.
    """
    previous = state.get("market", 0.0)
    old_market_vol = state.get("market_volatility", 1.0)
    volatility_signal = min(2.0, max(0.8, 0.85 + abs(previous) / 0.00025))
    market_vol = min(2.0, max(0.8, 0.92 * old_market_vol + 0.08 * volatility_signal))
    market = MARKET_MEMORY * previous + rng.gauss(0, MARKET_SHOCK * market_vol)
    sectors = {}
    for sector in sorted({club_num // 10 for club_num in stocks}):
        last = state.get("sectors", {}).get(str(sector), 0.0)
        sector_vol = 0.85 + 0.15 * market_vol
        sectors[str(sector)] = SECTOR_MEMORY * last + rng.gauss(0, SECTOR_SHOCK * sector_vol)

    # 한 번에 한 종목만 선택하고, 충격을 여러 틱에 나눠 적용한다.
    # 상태는 DB에 저장되어 서버 재시작과 과거 틱 복구 시에도 이어진다.
    event = state.get("random_event")
    if not isinstance(event, dict) or event.get("club") not in stocks or event.get("remaining", 0) <= 0:
        event = None
    prices, volatility, trends, components = {}, {}, {}, {}
    for club_num, price in sorted(stocks.items()):
        news_effect = news.get(club_num, 0.0)
        flow_effect = FLOW_MAX_LOG_RETURN * math.tanh(
            flows.get(club_num, 0) / FLOW_LIQUIDITY_SHARES
        )
        target_vol = min(3.0, 1 + 60 * abs(news_effect) + 300 * abs(flow_effect))
        old_vol = state.get("volatility", {}).get(str(club_num), 1.0)
        vol = max(target_vol, 1 + (old_vol - 1) * 0.9)
        beta = 0.8 + (club_num % 5) * 0.1
        old_trend = state.get("trends", {}).get(str(club_num), 0.0)
        trend = TREND_MEMORY * old_trend + rng.gauss(0, TREND_SHOCK)
        individual = trend + rng.gauss(0, INDIVIDUAL_SHOCK * vol)
        parts = {
            "market": beta * market,
            "sector": sectors[str(club_num // 10)],
            "news": news_effect,
            "flow": flow_effect,
            "individual": individual,
            "random_event": event["per_tick"] if event and event["club"] == club_num else 0.0,
        }
        movement = max(-MAX_LOG_RETURN, min(MAX_LOG_RETURN, sum(parts.values())))
        prices[club_num] = max(1.0, price * math.exp(movement))
        volatility[str(club_num)] = vol
        trends[str(club_num)] = trend
        components[club_num] = {**parts, "applied": movement}

    if event:
        event = {**event, "remaining": event["remaining"] - 1}
        if event["remaining"] <= 0:
            event = None
    elif stocks and rng.random() < RANDOM_EVENT_PROBABILITY:
        duration = rng.randint(RANDOM_EVENT_MIN_TICKS, RANDOM_EVENT_MAX_TICKS)
        magnitude = rng.uniform(RANDOM_EVENT_MIN_RETURN, RANDOM_EVENT_MAX_RETURN)
        direction = 1 if rng.random() < 0.5 else -1
        event = {"club": rng.choice(sorted(stocks)), "remaining": duration,
                 "per_tick": direction * magnitude / duration}

    return prices, {
        "market": market, "market_volatility": market_vol,
        "sectors": sectors, "volatility": volatility, "trends": trends,
        "random_event": event,
    }, components
