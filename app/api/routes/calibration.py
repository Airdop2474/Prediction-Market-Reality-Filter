from fastapi import APIRouter, Query
from app.services.calibration_service import get_calibration_report
from app.services.analysis_audit_service import (
    get_audit_summary,
    load_recent_analyses,
)

router = APIRouter()


@router.get("/")
async def get_calibration():
    """
    完整校准报告：整体 Brier Score、按类别分析、过度自信曲线。
    数据来源：analysis_audit.jsonl（需先运行 POST /resolve/auto 填充解决记录）
    """
    return get_calibration_report()


@router.get("/history")
async def get_prediction_history(
    limit: int = Query(default=50, ge=1, le=500),
    resolved_only: bool = Query(default=False),
    signal_filter: str = Query(default="", description="过滤信号类型，如 LONG、STRONG_LONG"),
):
    """
    查看历史分析记录（来自 audit 日志）。
    resolved_only=true  只看已解决的。
    signal_filter=LONG  只看 LONG 信号。
    """
    records = load_recent_analyses(limit=limit * 2)

    if resolved_only:
        records = [r for r in records if r.get("resolved")]
    if signal_filter:
        records = [r for r in records if r.get("signal") == signal_filter.upper()]

    return {
        "count": len(records),
        "predictions": records[-limit:],
    }


@router.get("/summary")
async def get_audit_overview(limit: int = Query(default=500, ge=1, le=5000)):
    """信号分布统计摘要，不需要已解决数据。"""
    return get_audit_summary(limit=limit)
