"""
trade_journal_service.py
========================
交易日志：记录你基于信号实际进行的操作，计算盈亏。

每条记录包含：
  - 信号来源（市场问题、系统信号、偏差、置信度）
  - 入场信息（方向、金额、入场价格）
  - 出场信息（出场价格、实际盈亏）
  - 决策备注

这是把系统从"分析工具"变成"可量化验证的交易记录"的核心数据。
"""

import os
import time
from datetime import datetime, timezone
from typing import Any

from app.utils.file_store import locked_file, read_json, write_json_atomic


def _journal_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(base, "..", "..", "..", "trade_journal.json")
    return os.path.abspath(root)


def _load() -> list[dict]:
    p = _journal_path()
    with locked_file(p):
        return _load_unlocked(p)


def _save(trades: list[dict]) -> None:
    p = _journal_path()
    with locked_file(p):
        _save_unlocked(p, trades)


def _load_unlocked(path: str) -> list[dict]:
    data = read_json(path, [])
    return data if isinstance(data, list) else []


def _save_unlocked(path: str, trades: list[dict]) -> None:
    write_json_atomic(path, trades, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_trade(
    market_question: str,
    signal: str,
    direction: str,            # "YES" or "NO"
    entry_price: float,        # 0-1 (Polymarket price)
    amount_usd: float,         # 投入金额 USD
    system_divergence: float,
    system_confidence: float,
    market_probability: float,
    ai_probability: float,
    notes: str = "",
) -> dict:
    """开仓：记录一笔新交易。"""
    p = _journal_path()
    with locked_file(p):
        trades = _load_unlocked(p)
        trade_id = f"T{int(time.time() * 1000) % 10**9:09d}"
        side = _normalize_direction(direction)
        position_price = _position_price(side, entry_price)

        shares = amount_usd / position_price if position_price > 0 else 0
        max_profit = shares * (1.0 - position_price)
        max_loss = amount_usd

        trade = {
            "id": trade_id,
            "status": "OPEN",
            "opened_at": _now(),
            "closed_at": None,
            "market_question": market_question,
            "signal": signal,
            "direction": side,
            "entry_price": round(entry_price, 4),
            "position_price": round(position_price, 4),
            "amount_usd": round(amount_usd, 2),
            "shares": round(shares, 4),
            "max_profit_usd": round(max_profit, 2),
            "max_loss_usd": round(max_loss, 2),
            "system_divergence": round(system_divergence, 2),
            "system_confidence": round(system_confidence, 3),
            "market_probability": round(market_probability, 2),
            "ai_probability": round(ai_probability, 2),
            "exit_price": None,
            "exit_value_price": None,
            "pnl_usd": None,
            "pnl_pct": None,
            "outcome": None,  # "WIN" | "LOSS" | "BREAK_EVEN"
            "notes": notes,
        }
        trades.append(trade)
        _save_unlocked(p, trades)
        return trade


def close_trade(
    trade_id: str,
    exit_price: float,     # 0-1 if partial exit, 1.0 if YES resolved, 0.0 if NO
    notes: str = "",
) -> dict | None:
    """平仓：记录出场价格，计算盈亏。"""
    p = _journal_path()
    with locked_file(p):
        trades = _load_unlocked(p)
        for t in trades:
            if t["id"] == trade_id and t["status"] == "OPEN":
                shares = t["shares"]
                amount = t["amount_usd"]
                side = _normalize_direction(t.get("direction", "YES"))
                exit_value_price = _position_price(side, exit_price)
                pnl = shares * exit_value_price - amount
                pnl_pct = pnl / amount * 100 if amount > 0 else 0

                t["status"] = "CLOSED"
                t["closed_at"] = _now()
                t["exit_price"] = round(exit_price, 4)
                t["exit_value_price"] = round(exit_value_price, 4)
                t["pnl_usd"] = round(pnl, 2)
                t["pnl_pct"] = round(pnl_pct, 2)
                t["outcome"] = "WIN" if pnl > 0.01 else "LOSS" if pnl < -0.01 else "BREAK_EVEN"
                if notes:
                    t["notes"] = (t.get("notes") or "") + " | " + notes
                _save_unlocked(p, trades)
                return t
    return None


def _normalize_direction(direction: str) -> str:
    side = (direction or "").strip().upper()
    if side not in {"YES", "NO"}:
        raise ValueError("direction must be YES or NO")
    return side


def _position_price(direction: str, yes_price: float) -> float:
    yes = max(0.0, min(1.0, float(yes_price)))
    if direction == "NO":
        return 1.0 - yes
    return yes


def get_summary() -> dict[str, Any]:
    """汇总所有交易的盈亏统计。"""
    trades = _load()
    open_t   = [t for t in trades if t["status"] == "OPEN"]
    closed_t = [t for t in trades if t["status"] == "CLOSED"]

    if not closed_t:
        return {
            "total_trades": len(trades),
            "open_trades": len(open_t),
            "closed_trades": 0,
            "win_rate": None,
            "total_pnl_usd": 0,
            "avg_pnl_pct": None,
            "best_trade_usd": None,
            "worst_trade_usd": None,
            "by_signal": {},
        }

    wins   = [t for t in closed_t if t["outcome"] == "WIN"]
    losses = [t for t in closed_t if t["outcome"] == "LOSS"]
    pnls   = [t["pnl_usd"] for t in closed_t if t["pnl_usd"] is not None]
    pcts   = [t["pnl_pct"] for t in closed_t if t["pnl_pct"] is not None]

    # Group by signal type
    by_signal: dict[str, dict] = {}
    for t in closed_t:
        sig = t.get("signal", "?")
        if sig not in by_signal:
            by_signal[sig] = {"count": 0, "wins": 0, "total_pnl": 0.0}
        by_signal[sig]["count"] += 1
        by_signal[sig]["total_pnl"] += t.get("pnl_usd") or 0
        if t.get("outcome") == "WIN":
            by_signal[sig]["wins"] += 1

    for sig, d in by_signal.items():
        d["win_rate"] = round(d["wins"] / d["count"] * 100, 1) if d["count"] else None
        d["avg_pnl"] = round(d["total_pnl"] / d["count"], 2) if d["count"] else None
        d["total_pnl"] = round(d["total_pnl"], 2)

    return {
        "total_trades": len(trades),
        "open_trades": len(open_t),
        "closed_trades": len(closed_t),
        "win_rate": round(len(wins) / len(closed_t) * 100, 1),
        "total_pnl_usd": round(sum(pnls), 2),
        "avg_pnl_usd": round(sum(pnls) / len(pnls), 2),
        "avg_pnl_pct": round(sum(pcts) / len(pcts), 1),
        "best_trade_usd": max(pnls),
        "worst_trade_usd": min(pnls),
        "by_signal": by_signal,
    }


def list_trades(status: str | None = None) -> list[dict]:
    trades = _load()
    if status:
        trades = [t for t in trades if t["status"] == status.upper()]
    return sorted(trades, key=lambda t: t.get("opened_at", ""), reverse=True)
