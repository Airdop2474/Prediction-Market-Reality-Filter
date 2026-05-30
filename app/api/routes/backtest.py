from fastapi import APIRouter, Query
from app.services.polymarket_history_service import (
    fetch_resolved_markets,
    get_backtest_baseline,
)
from app.services.base_rate_service import classify_market, get_base_rate_context
from app.services.calibration_service import brier_score, _grade_brier

router = APIRouter()


@router.get("/baseline")
async def backtest_baseline(limit: int = Query(default=100, ge=10, le=500)):
    """
    计算"盲目信任市场价格"的 Brier Score 基准线。
    这是系统必须超越的最低门槛。
    """
    return await get_backtest_baseline()


@router.get("/base-rate")
async def backtest_base_rate(limit: int = Query(default=100, ge=10, le=500)):
    """
    用历史基准利率（base rate prior）代替市场价格预测，计算 Brier Score。
    若 base_rate Brier < market Brier，说明基准利率锚定提供了正向贡献。
    """
    resolved = await fetch_resolved_markets(limit=limit)
    if not resolved:
        return {"status": "no_data"}

    market_scores = []
    base_rate_scores = []
    category_counts: dict[str, int] = {}

    for m in resolved:
        actual = m["actual_outcome"]
        market_pred = m["final_yes_price"] * 100

        br = classify_market(m["question"])
        base_pred = br.prior

        market_scores.append(brier_score(market_pred, actual))
        base_rate_scores.append(brier_score(base_pred, actual))

        cat = br.category
        category_counts[cat] = category_counts.get(cat, 0) + 1

    avg_market = sum(market_scores) / len(market_scores)
    avg_base = sum(base_rate_scores) / len(base_rate_scores)
    improvement = round(avg_market - avg_base, 4)

    return {
        "status": "ok",
        "n": len(resolved),
        "market_brier": round(avg_market, 4),
        "market_grade": _grade_brier(avg_market),
        "base_rate_brier": round(avg_base, 4),
        "base_rate_grade": _grade_brier(avg_base),
        "improvement_vs_market": improvement,
        "base_rate_helps": improvement > 0,
        "categories_found": category_counts,
        "interpretation": (
            "base_rate_brier < market_brier means base rate anchoring "
            "helps vs blindly trusting the crowd."
            if improvement > 0
            else "Market pricing is better than base rates for this sample."
        ),
    }


@router.get("/resolved-markets")
async def get_resolved_markets(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """直接返回 Polymarket 历史已解决市场列表，用于调试和分析。"""
    markets = await fetch_resolved_markets(limit=limit, offset=offset)
    return {"count": len(markets), "markets": markets}
