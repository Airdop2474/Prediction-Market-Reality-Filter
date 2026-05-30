"""
market_filter_service.py
========================
智能市场过滤器。

目标：只分析那些可能有真实 edge 的市场。

过滤逻辑：
  1. 流动性 ≥ $10,000（低流动性市场容易被操纵）
  2. 交易量 ≥ $5,000（量太低说明市场关注度不够）
  3. 市场概率不在极端区间（90%+ 或 10%- 的市场没什么edge）
  4. 问题长度合理（太短的问题通常是垃圾市场）
  5. 优先选择：概率在 20%-80% 区间（不确定性最大的市场）
  6. 优先选择：高关注度类别（选举、加密、宏观）
"""

from app.models.market import MarketModel


# 最低流动性门槛（美元）
MIN_LIQUIDITY = 5_000

# 最低交易量门槛（美元）
MIN_VOLUME = 2_000

# 过滤掉极端确定性市场（>92% 或 <8%）
CERTAINTY_HIGH = 92.0
CERTAINTY_LOW = 8.0

# 高优先级市场类型关键词
HIGH_PRIORITY_KEYWORDS = [
    "election", "president", "senate", "house", "vote",
    "bitcoin", "btc", "ethereum", "fed", "rate",
    "recession", "inflation", "tariff",
    "ai", "openai", "gpt",
    "trump", "harris", "biden",
]

# 低优先级（暂时不分析，效率太低）
LOW_PRIORITY_KEYWORDS = [
    "oscar", "emmy", "grammy", "celebrity",
    "sports team", "will x say", "tweet",
]


def filter_markets(
    markets: list[MarketModel],
    min_liquidity: float = MIN_LIQUIDITY,
    min_volume: float = MIN_VOLUME,
    max_markets: int = 10,
) -> list[MarketModel]:
    """
    过滤并排序市场列表。
    返回最适合分析的前 max_markets 个市场。
    """
    filtered = []
    for market in markets:
        issues = _get_filter_issues(market, min_liquidity, min_volume)
        if not issues:
            filtered.append(market)

    # 按优先级排序
    filtered.sort(key=lambda m: _priority_score(m), reverse=True)
    return filtered[:max_markets]


def _get_filter_issues(
    market: MarketModel,
    min_liquidity: float,
    min_volume: float,
) -> list[str]:
    issues = []
    q = market.question.lower()

    if market.liquidity < min_liquidity:
        issues.append(f"low_liquidity(${market.liquidity:.0f})")

    if market.volume < min_volume:
        issues.append(f"low_volume(${market.volume:.0f})")

    prob = market.yes_price * 100
    if prob >= CERTAINTY_HIGH or prob <= CERTAINTY_LOW:
        issues.append(f"too_certain({prob:.0f}%)")

    if len(market.question.strip()) < 20:
        issues.append("question_too_short")

    if any(kw in q for kw in LOW_PRIORITY_KEYWORDS):
        issues.append("low_priority_category")

    return issues


def _priority_score(market: MarketModel) -> float:
    """
    高 score → 更优先分析。
    综合考虑：流动性、交易量、不确定性、类别。
    """
    q = market.question.lower()
    score = 0.0

    # 流动性对数权重
    if market.liquidity > 0:
        import math
        score += math.log10(max(1, market.liquidity)) * 2

    # 交易量对数权重
    if market.volume > 0:
        import math
        score += math.log10(max(1, market.volume))

    # 不确定性权重：50% 附近的市场 edge 最大
    prob = market.yes_price * 100
    uncertainty = 1.0 - abs(prob - 50) / 50.0
    score += uncertainty * 10

    # 高优先级类别加分
    if any(kw in q for kw in HIGH_PRIORITY_KEYWORDS):
        score += 5

    return score


def explain_filter(market: MarketModel) -> dict:
    """调试用：解释为什么一个市场被过滤或保留。"""
    issues = _get_filter_issues(market, MIN_LIQUIDITY, MIN_VOLUME)
    return {
        "question": market.question,
        "yes_price": market.yes_price,
        "liquidity": market.liquidity,
        "volume": market.volume,
        "priority_score": round(_priority_score(market), 2),
        "passed": len(issues) == 0,
        "issues": issues,
    }
