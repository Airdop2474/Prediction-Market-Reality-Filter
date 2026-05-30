"""
calibration_service.py
======================
基于 Brier Score 的预测校准系统。

数据来源：analysis_audit.jsonl（与 ReputationEngine 共享同一数据源）
不再从 agent_memory.json 读取，避免数据断链。

Brier Score = (predicted_prob - actual_outcome)²
  完美预测 = 0.0   随机猜测 = 0.25   完全错误 = 1.0
"""

from collections import defaultdict
from typing import Any

from app.services.analysis_audit_service import load_recent_analyses


def brier_score(predicted: float, actual: float) -> float:
    return ((predicted / 100.0) - (actual / 100.0)) ** 2


def _load_resolved() -> list[dict]:
    """从 audit 日志加载所有已解决记录。"""
    all_records = load_recent_analyses(limit=10_000)
    return [
        r for r in all_records
        if r.get("resolved") and r.get("actual_outcome") is not None
    ]


def calculate_overall_brier() -> dict[str, Any]:
    resolved = _load_resolved()
    if not resolved:
        return {"score": None, "n": 0, "skill_score": None, "grade": "no_data"}

    scores = [
        brier_score(float(r.get("ai_probability", 50)),
                    float(r.get("actual_outcome", 50)))
        for r in resolved
    ]
    avg = sum(scores) / len(scores)
    skill = round(1.0 - avg / 0.25, 4)
    return {
        "score": round(avg, 4),
        "n": len(scores),
        "skill_score": skill,
        "grade": _grade(avg),
    }


def calculate_calibration_by_category() -> dict[str, Any]:
    resolved = _load_resolved()
    data: dict[str, list[float]] = defaultdict(list)
    for r in resolved:
        cat = r.get("base_rate_category", "unknown")
        data[cat].append(
            brier_score(float(r.get("ai_probability", 50)),
                        float(r.get("actual_outcome", 50)))
        )
    return {
        cat: {"brier_score": round(sum(s) / len(s), 4),
              "n": len(s), "grade": _grade(sum(s) / len(s))}
        for cat, s in data.items()
    }


def calculate_overconfidence() -> dict[str, Any]:
    resolved = _load_resolved()
    if len(resolved) < 10:
        return {"status": "insufficient_data", "n": len(resolved)}

    buckets: dict[int, list] = defaultdict(list)
    for r in resolved:
        pred = float(r.get("ai_probability", 50))
        actual = 1.0 if float(r.get("actual_outcome", 0)) >= 50 else 0.0
        buckets[min(9, int(pred / 10))].append((pred / 100.0, actual))

    calibration = []
    for b in range(10):
        items = buckets.get(b, [])
        if not items:
            continue
        avg_pred = sum(x[0] for x in items) / len(items)
        avg_act  = sum(x[1] for x in items) / len(items)
        calibration.append({
            "bucket": f"{b*10}-{(b+1)*10}%",
            "avg_predicted": round(avg_pred * 100, 1),
            "avg_actual":    round(avg_act  * 100, 1),
            "bias":          round((avg_pred - avg_act) * 100, 1),
            "n": len(items),
        })
    return {"status": "ok", "n": len(resolved), "calibration_curve": calibration}


def get_calibration_report() -> dict[str, Any]:
    overall = calculate_overall_brier()
    return {
        "overall": overall,
        "by_category": calculate_calibration_by_category(),
        "overconfidence": calculate_overconfidence(),
        "interpretation": _interpret(overall),
    }


def _grade(brier: float) -> str:
    if brier <= 0.05: return "EXCELLENT"
    if brier <= 0.10: return "GOOD"
    if brier <= 0.15: return "ACCEPTABLE"
    if brier <= 0.20: return "POOR"
    return "RANDOM_LEVEL"

_grade_brier = _grade  # alias for backtest.py


def _interpret(overall: dict) -> str:
    if overall["n"] == 0:
        return ("No resolved markets yet. "
                "Run POST /resolve/auto daily to accumulate calibration data.")
    skill = overall.get("skill_score") or 0
    msgs = {
        "EXCELLENT":    f"Well-calibrated. Skill={skill:.1%}. Trust signals.",
        "GOOD":         f"Good calibration. Skill={skill:.1%}. Signals are usable.",
        "ACCEPTABLE":   f"Acceptable. Skill={skill:.1%}. Use caution on position size.",
        "POOR":         f"Poor calibration. Skill={skill:.1%}. Review thresholds.",
        "RANDOM_LEVEL": "System at random level. Do NOT trade. Investigate.",
    }
    return msgs.get(overall.get("grade", ""), "Unknown state.")
