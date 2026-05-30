"""
polymarket_history_service.py
=============================
从 Polymarket API 获取已解决市场的历史数据。

用于：
  1. 自动校准 agent_memory（填充历史数据）
  2. 回测系统信号准确率
  3. 计算基准利率的实证数据
"""

import httpx
from typing import Any


POLYMARKET_API = "https://gamma-api.polymarket.com/markets"


async def fetch_resolved_markets(
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    获取已解决的历史市场。
    返回包含 question、final_probability（实际结果）的列表。
    """
    params = {
        "closed": "true",
        "limit": str(limit),
        "offset": str(offset),
        "order": "volume",
        "ascending": "false",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(POLYMARKET_API, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return []

    markets = []
    for item in data:
        try:
            question = item.get("question", "")
            if not question:
                continue

            # 解析 outcome prices
            outcome_prices = item.get("outcomePrices", "[]")
            if isinstance(outcome_prices, str):
                import json
                prices = json.loads(outcome_prices)
            else:
                prices = outcome_prices

            if not prices or len(prices) < 2:
                continue

            yes_price = float(prices[0])

            # 已关闭市场：YES 价格接近 1 = YES 解决，接近 0 = NO 解决
            actual_outcome = 100.0 if yes_price >= 0.5 else 0.0

            markets.append({
                "id": str(item.get("id", "")),
                "question": question,
                "actual_outcome": actual_outcome,
                "final_yes_price": yes_price,
                "volume": float(item.get("volume", 0)),
                "liquidity": float(item.get("liquidity", 0)),
                "start_date": item.get("startDate", ""),
                "end_date": item.get("endDate", ""),
            })
        except Exception:
            continue

    return markets


async def get_backtest_baseline() -> dict[str, Any]:
    """
    获取市场基准：当你始终猜测"市场概率"（不做任何分析）时的 Brier Score。
    这是系统必须超越的基准线。
    """
    resolved = await fetch_resolved_markets(limit=100)
    if not resolved:
        return {"status": "no_data"}

    baseline_scores = []
    for m in resolved:
        # 基准：直接用最终市场价格作为预测
        pred = m["final_yes_price"] * 100
        actual = m["actual_outcome"]
        bs = ((pred / 100.0) - (actual / 100.0)) ** 2
        baseline_scores.append(bs)

    avg_baseline = sum(baseline_scores) / len(baseline_scores)

    return {
        "status": "ok",
        "n": len(resolved),
        "baseline_brier_score": round(avg_baseline, 4),
        "baseline_grade": _grade_brier(avg_baseline),
        "note": (
            "This is the Brier score you get by just trusting market prices. "
            "Your system must beat this to have any edge."
        ),
    }


def _grade_brier(b: float) -> str:
    if b <= 0.05:
        return "EXCELLENT"
    if b <= 0.10:
        return "GOOD"
    if b <= 0.15:
        return "ACCEPTABLE"
    if b <= 0.20:
        return "POOR"
    return "RANDOM_LEVEL"
