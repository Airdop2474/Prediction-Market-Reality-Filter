from fastapi import APIRouter, Body, Query
from app.services.trade_journal_service import (
    open_trade, close_trade, get_summary, list_trades,
)

router = APIRouter()


@router.post("/open")
async def api_open_trade(
    market_question:    str   = Body(...),
    signal:             str   = Body(...),
    direction:          str   = Body(..., description="YES or NO"),
    entry_price:        float = Body(..., ge=0.01, le=0.99),
    amount_usd:         float = Body(..., gt=0),
    system_divergence:  float = Body(default=0),
    system_confidence:  float = Body(default=0),
    market_probability: float = Body(default=50),
    ai_probability:     float = Body(default=50),
    notes:              str   = Body(default=""),
):
    """
    记录一笔新入场交易。

    示例：
      direction = "YES"  → 买入 YES（LONG 信号）
      direction = "NO"   → 买入 NO（SHORT 信号）
      entry_price = 0.155  → Polymarket 当前 YES 价格（即市场概率 15.5%）
      amount_usd = 50    → 投入 50 美元
    """
    trade = open_trade(
        market_question=market_question,
        signal=signal,
        direction=direction,
        entry_price=entry_price,
        amount_usd=amount_usd,
        system_divergence=system_divergence,
        system_confidence=system_confidence,
        market_probability=market_probability,
        ai_probability=ai_probability,
        notes=notes,
    )
    return trade


@router.post("/close/{trade_id}")
async def api_close_trade(
    trade_id:   str,
    exit_price: float = Body(..., ge=0.0, le=1.0,
                             description="1.0=YES resolved, 0.0=NO resolved, 0.x=partial"),
    notes:      str   = Body(default=""),
):
    """
    平仓一笔交易，计算并记录盈亏。

    exit_price:
      1.0  → YES 解决（买了 YES，获得全部收益）
      0.0  → NO  解决（买了 YES，全部亏损）
      0.75 → 中途以 0.75 价格卖出
    """
    result = close_trade(trade_id=trade_id, exit_price=exit_price, notes=notes)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Open trade '{trade_id}' not found")
    return result


@router.get("/summary")
async def api_trade_summary():
    """交易盈亏汇总：胜率、总盈亏、按信号类型分析。"""
    return get_summary()


@router.get("/")
async def api_list_trades(
    status: str = Query(default="", description="OPEN | CLOSED | (空=全部)"),
):
    """列出所有交易记录（按时间倒序）。"""
    return list_trades(status=status or None)
