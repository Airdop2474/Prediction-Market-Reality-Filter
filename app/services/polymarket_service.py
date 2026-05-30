import json
import logging
from typing import Any

import httpx

from app.models.market import MarketModel


POLYMARKET_API = "https://gamma-api.polymarket.com/markets"
logger = logging.getLogger(__name__)

ALLOWED_KEYWORDS = (
    "trump", "election", "president", "bitcoin", "btc", "crypto",
    "fed", "china", "war", "ukraine", "russia", "ai", "openai",
    "tesla", "recession", "tariff", "etf", "ethereum", "eth",
    "solana", "inflation", "rate", "nasdaq", "spy", "sp500",
)


async def fetch_markets(limit: int = 10) -> list[MarketModel]:
    params = {
        "limit": str(max(limit, 1) * 3),
        "closed": "false",
        "archived": "false",
        "order": "volume",
        "ascending": "false",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(POLYMARKET_API, params=params)
        response.raise_for_status()
        data = response.json()

    markets = []
    for item in data:
        market = parse_market(item)
        if market is None:
            continue
        if not is_allowed_market(market):
            continue

        markets.append(market)
        if len(markets) >= limit:
            break

    return markets


def parse_market(item: dict[str, Any]) -> MarketModel | None:
    try:
        question = str(item.get("question", "") or "").strip()
        if not question:
            return None

        yes_price, no_price = parse_outcome_prices(item.get("outcomePrices"))
        return MarketModel(
            id=str(item.get("id", "") or ""),
            question=question,
            yes_price=yes_price,
            no_price=no_price,
            volume=safe_float(item.get("volume"), 0.0),
            liquidity=safe_float(item.get("liquidity"), 0.0),
            closed=bool(item.get("closed", False)),
            archived=bool(item.get("archived", False)),
            resolved=bool(
                item.get("resolved", False)
                or item.get("isResolved", False)
                or item.get("resolutionStatus") == "resolved"
            ),
            end_date=str(item.get("endDate", "") or ""),
        )
    except Exception as exc:
        logger.warning("Failed to parse Polymarket market: %s", exc)
        return None


def parse_outcome_prices(raw_prices: Any) -> tuple[float, float]:
    try:
        prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
        if not isinstance(prices, list) or len(prices) < 2:
            raise ValueError("missing outcome prices")
        return safe_float(prices[0], 0.5), safe_float(prices[1], 0.5)
    except Exception:
        return 0.5, 0.5


def is_allowed_market(market: MarketModel) -> bool:
    if market.closed or market.archived or market.resolved:
        return False
    question = market.question.lower()
    return any(keyword in question for keyword in ALLOWED_KEYWORDS)


def safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
