import json
import os
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.utils.file_store import locked_file


AUDIT_FILE = os.path.join(
    os.path.dirname(settings.MEMORY_FILE),
    "analysis_audit.jsonl",
)


def record_analysis(analysis: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_id": analysis.get("market_id"),
        "market_question": analysis.get("market_question"),
        "market_probability": analysis.get("market_probability"),
        "ai_probability": analysis.get("ai_probability"),
        "divergence": analysis.get("divergence"),
        "confidence_score": analysis.get("confidence_score"),
        "signal": analysis.get("signal"),
        "signal_strength": analysis.get("signal_strength"),
        "news_quality_score": analysis.get("news_quality_score"),
        "narrative_risk_score": analysis.get("narrative_risk_score"),
        "priced_in_risk_score": analysis.get("priced_in_risk_score"),
        "evidence_direction": analysis.get("evidence_direction"),
        "evidence_strength": analysis.get("evidence_strength"),
        "evidence_conflict_score": analysis.get("evidence_conflict_score"),
        "freshness_score": analysis.get("freshness_score"),
        "resolution_relevance_score": analysis.get("resolution_relevance_score"),
        "base_rate_category": analysis.get("base_rate_category"),
        "base_rate_prior": analysis.get("base_rate_prior"),
        "risk_flags": analysis.get("risk_flags", []),
        "news_filter": analysis.get("news_filter", {}),
    }
    with locked_file(AUDIT_FILE):
        with open(AUDIT_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def resolve_by_question(
    market_question: str,
    actual_outcome: float,
) -> int:
    """
    将指定问题的最近一条未解决记录标记为已解决。
    actual_outcome: 0.0（NO 解决）或 100.0（YES 解决）

    返回更新的记录数量（0 = 未找到匹配记录）。
    """
    if not os.path.exists(AUDIT_FILE):
        return 0

    records: list[dict[str, Any]] = []
    with locked_file(AUDIT_FILE):
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    updated = 0
    for record in reversed(records):
        if (
            record.get("market_question") == market_question
            and not record.get("resolved")
        ):
            record["resolved"] = True
            record["actual_outcome"] = actual_outcome
            record["resolved_at"] = datetime.now(timezone.utc).isoformat()
            updated += 1
            break  # 只更新最近一条

    if updated:
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        with locked_file(AUDIT_FILE):
            with open(AUDIT_FILE, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return updated


def load_recent_analyses(limit: int = 100) -> list[dict[str, Any]]:
    if not os.path.exists(AUDIT_FILE):
        return []

    records = []
    with locked_file(AUDIT_FILE):
        with open(AUDIT_FILE, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records[-limit:]


def get_audit_summary(limit: int = 500) -> dict[str, Any]:
    records = load_recent_analyses(limit=limit)
    if not records:
        return {"count": 0, "status": "no_data"}

    signal_counts: dict[str, int] = {}
    for item in records:
        sig = str(item.get("signal", "WATCHLIST"))
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

    actionable = [
        item for item in records
        if item.get("signal") in ("STRONG_LONG", "LONG", "SHORT", "STRONG_SHORT")
    ]

    return {
        "count": len(records),
        "signal_breakdown": signal_counts,
        "actionable_count": len(actionable),
        "watchlist_count": signal_counts.get("WATCHLIST", 0),
        "average_confidence": average(records, "confidence_score"),
        "average_news_quality": average(records, "news_quality_score"),
        "average_evidence_strength": average(records, "evidence_strength"),
        "average_conflict": average(records, "evidence_conflict_score"),
        "average_resolution_relevance": average(records, "resolution_relevance_score"),
        "average_priced_in_risk": average(records, "priced_in_risk_score"),
        "latest": records[-10:],
    }


def average(records: list[dict[str, Any]], field: str) -> float:
    values = [
        float(item[field])
        for item in records
        if item.get(field) is not None
    ]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)
