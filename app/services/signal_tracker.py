"""
signal_tracker.py
=================
信号准确率追踪器。

不需要等市场正式解决——通过检查当前市场价格相对于我们预测时的变动方向，
给出实时的"方向准确率"反馈。

逻辑：
  - 预测 ai_probability > market_probability（LONG 信号）
  - 若当前价格上涨 → 方向正确
  - 若当前价格下跌 → 方向错误
  - 涨跌超过 2% 才算有效移动（排除噪音）

数据来源：analysis_audit.jsonl（有 market_id）
价格更新：Polymarket Gamma API
"""

import asyncio
import json
import os
import time
from typing import Any

import httpx

_GAMMA_URL = "https://gamma-api.polymarket.com/markets/{market_id}"
_CACHE: dict[str, tuple[float, float]] = {}  # {market_id: (yes_price, timestamp)}
_CACHE_TTL = 300  # 5 分钟缓存


def _audit_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "..", "..", "..", "analysis_audit.jsonl")


def _load_actionable() -> list[dict]:
    """加载所有有 market_id 的可操作信号记录。"""
    path = _audit_path()
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
                if (
                    d.get("market_id")
                    and d.get("signal") in ("LONG", "SHORT", "STRONG_LONG", "STRONG_SHORT")
                    and d.get("ai_probability") is not None
                    and d.get("market_probability") is not None
                ):
                    records.append(d)
            except Exception:
                continue
    return records


async def _fetch_current_price(market_id: str) -> float | None:
    """从 Polymarket 拿当前 YES 价格，带缓存。"""
    now = time.time()
    if market_id in _CACHE:
        price, ts = _CACHE[market_id]
        if now - ts < _CACHE_TTL:
            return price

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(_GAMMA_URL.format(market_id=market_id))
            if r.status_code == 200:
                data = r.json()
                prices_raw = data.get("outcomePrices", "[]")
                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                if prices:
                    price = float(prices[0]) * 100  # 转为百分比
                    _CACHE[market_id] = (price, now)
                    return price
    except Exception:
        pass
    return None


async def get_signal_accuracy() -> dict[str, Any]:
    """
    计算所有有 market_id 的信号的实时方向准确率。
    
    返回：
    - direction_accuracy: 价格朝预测方向移动的比例
    - avg_price_move: 平均价格移动幅度
    - by_signal_type: 按信号类型分组的准确率
    """
    records = _load_actionable()
    if not records:
        return {"status": "no_data", "message": "No actionable signals with market_id found."}

    # 并发拿当前价格
    tasks = [_fetch_current_price(r["market_id"]) for r in records]
    current_prices = await asyncio.gather(*tasks, return_exceptions=True)

    NOISE_THRESHOLD = 2.0  # 2% 以下的变动视为噪音

    results = []
    by_type: dict[str, dict] = {}

    for record, cur_price in zip(records, current_prices):
        if not isinstance(cur_price, float):
            continue

        entry_price = float(record["market_probability"])
        ai_price    = float(record["ai_probability"])
        signal      = record["signal"]
        price_move  = cur_price - entry_price  # 正=上涨，负=下跌

        # 判断方向
        expected_direction = "up" if ai_price > entry_price else "down"
        actual_direction   = "up" if price_move > NOISE_THRESHOLD else (
                             "down" if price_move < -NOISE_THRESHOLD else "neutral")

        direction_correct = (
            expected_direction == actual_direction
            if actual_direction != "neutral"
            else None  # 中性：不计入
        )

        entry = {
            "market_question":  record.get("market_question", "")[:80],
            "signal":           signal,
            "entry_price":      round(entry_price, 1),
            "ai_prediction":    round(ai_price, 1),
            "current_price":    round(cur_price, 1),
            "price_move":       round(price_move, 1),
            "expected_direction": expected_direction,
            "actual_direction": actual_direction,
            "direction_correct": direction_correct,
            "timestamp":        record.get("timestamp", ""),
        }
        results.append(entry)

        # 按信号类型汇总
        if signal not in by_type:
            by_type[signal] = {"total": 0, "correct": 0, "neutral": 0, "price_moves": []}
        by_type[signal]["total"] += 1
        by_type[signal]["price_moves"].append(abs(price_move))
        if direction_correct is True:
            by_type[signal]["correct"] += 1
        elif direction_correct is None:
            by_type[signal]["neutral"] += 1

    if not results:
        return {"status": "no_prices", "message": "Could not fetch current prices."}

    # 整体准确率（排除中性）
    decided = [r for r in results if r["direction_correct"] is not None]
    correct = [r for r in decided if r["direction_correct"]]
    accuracy = round(len(correct) / len(decided) * 100, 1) if decided else None

    # 汇总 by_type
    by_type_summary = {}
    for sig, d in by_type.items():
        decided_n = d["total"] - d["neutral"]
        rate = round(d["correct"] / decided_n * 100, 1) if decided_n > 0 else None
        by_type_summary[sig] = {
            "total": d["total"],
            "correct": d["correct"],
            "neutral": d["neutral"],
            "direction_accuracy": rate,
            "avg_abs_move": round(sum(d["price_moves"]) / len(d["price_moves"]), 1) if d["price_moves"] else 0,
        }

    return {
        "status": "ok",
        "total_signals": len(results),
        "decided_signals": len(decided),
        "correct_signals": len(correct),
        "direction_accuracy_pct": accuracy,
        "by_signal_type": by_type_summary,
        "signals": sorted(results, key=lambda x: abs(x["price_move"]), reverse=True),
        "note": f"Direction accuracy = price moved toward AI prediction. Neutral = move < {NOISE_THRESHOLD}%.",
    }
