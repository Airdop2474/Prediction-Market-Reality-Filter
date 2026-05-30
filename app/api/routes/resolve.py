from fastapi import APIRouter, Body
from app.services.auto_resolve_service import run_auto_resolve
from app.memory.agent_memory import resolve_prediction, load_memory
from app.services.analysis_audit_service import resolve_by_question

router = APIRouter()


@router.post("/auto")
async def auto_resolve(limit: int = 200):
    """
    从 Polymarket 拉取已解决市场，自动匹配本地预测并写入实际结果。
    同时更新 agent_memory.json 和 analysis_audit.jsonl。
    建议每天调用一次。
    """
    return await run_auto_resolve(resolved_limit=limit)


@router.post("/manual")
async def manual_resolve(
    market_question: str = Body(...),
    actual_outcome: float = Body(..., ge=0, le=100),
):
    """
    手动解决一个预测。actual_outcome: 0=NO发生, 100=YES发生。
    同时更新 agent_memory.json 和 analysis_audit.jsonl。
    """
    mem_ok = resolve_prediction(
        market_question=market_question,
        actual_outcome=actual_outcome,
    )
    audit_updated = resolve_by_question(
        market_question=market_question,
        actual_outcome=actual_outcome,
    )
    return {
        "success": mem_ok or audit_updated > 0,
        "agent_memory_updated": mem_ok,
        "audit_updated": audit_updated,
        "market_question": market_question,
        "actual_outcome": actual_outcome,
    }


@router.get("/pending")
async def get_pending_predictions():
    """查看所有尚未解决的预测。"""
    memory = load_memory()
    pending = [e for e in memory if not e.get("resolved")]
    return {
        "count": len(pending),
        "predictions": [
            {
                "market_question": e.get("market_question", ""),
                "market_probability": e.get("market_probability"),
                "final_probability": e.get("final_probability"),
                "divergence": e.get("divergence"),
                "timestamp": e.get("timestamp"),
            }
            for e in pending[-50:]
        ],
    }
