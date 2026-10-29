"""30초 단위 모의시장. I/O 없이 이전 상태와 입력으로 다음 상태를 계산한다.

수치는 실제 시장 추정치가 아닌 게임 초기 설정이다. 내부 가격은 소수점을 유지한다.
상승 횟수나 미래 경로를 미리 정하지 않는다.
"""

import math

TICK_SECONDS = 30
CANDLE_SECONDS = 300
NEWS_TICKS = 120
MAX_LOG_RETURN = math.log1p(0.01)


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
    market_vol = min(2.5, 1 + abs(previous) / 0.001)
    market = 0.15 * previous + rng.gauss(0, 0.00022 * market_vol)
    sectors = {}
    for sector in sorted({club_num // 10 for club_num in stocks}):
        last = state.get("sectors", {}).get(str(sector), 0.0)
        sectors[str(sector)] = 0.2 * last + rng.gauss(0, 0.00027)

    prices, volatility, components = {}, {}, {}
    for club_num, price in sorted(stocks.items()):
        news_effect = news.get(club_num, 0.0)
        flow_effect = 0.002 * math.tanh(flows.get(club_num, 0) / 1000)
        target_vol = min(3.0, 1 + 60 * abs(news_effect) + 300 * abs(flow_effect))
        old_vol = state.get("volatility", {}).get(str(club_num), 1.0)
        vol = max(target_vol, 1 + (old_vol - 1) * 0.9)
        beta = 0.8 + (club_num % 5) * 0.1
        individual = rng.gauss(0, 0.00032 * vol)
        parts = {
            "market": beta * market,
            "sector": sectors[str(club_num // 10)],
            "news": news_effect,
            "flow": flow_effect,
            "individual": individual,
        }
        movement = max(-MAX_LOG_RETURN, min(MAX_LOG_RETURN, sum(parts.values())))
        prices[club_num] = max(1.0, price * math.exp(movement))
        volatility[str(club_num)] = vol
        components[club_num] = {**parts, "applied": movement}

    return prices, {
        "market": market, "sectors": sectors, "volatility": volatility,
    }, components
