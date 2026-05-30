"""
auto_resolve_service.py
=======================
自动将已解决的 Polymarket 市场与本地预测记录匹配，
同步更新 agent_memory.json 和 analysis_audit.jsonl，
确保 calibration_service 和 ReputationEngine 都有数据可读。
"""

import re
from typing import Any

from app.memory.agent_memory import resolve_prediction
from app.services.analysis_audit_service import resolve_by_question
from app.services.polymarket_history_service import fetch_resolved_markets


_STOPWORDS = {
    "will", "the", "this", "that", "with", "from", "about", "after",
    "before", "over", "under", "yes", "no", "and", "or", "for", "to",
    "of", "in", "on", "by", "a", "an", "be", "is", "are", "was",
}

FUZZY_THRESHOLD = 0.82


async def run_auto_resolve(resolved_limit: int = 200) -> dict[str, Any]:
    """
    从 Polymarket 拉取已解决市场，与本地预测匹配，写入实际结果。
    同时更新 agent_memory.json（供 calibration_service）
    和 analysis_audit.jsonl（供 ReputationEngine）。
    """
    resolved_markets = await fetch_resolved_markets(limit=resolved_limit)
    if not resolved_markets:
        return {"status": "no_resolved_markets", "resolved_count": 0, "checked_count": 0}

    from app.memory.agent_memory import load_memory
    memory = load_memory()
    unresolved = [e for e in memory if not e.get("resolved")]

    if not unresolved:
        return {"status": "no_unresolved_predictions", "resolved_count": 0,
                "checked_count": len(resolved_markets)}

    resolved_index = _build_index(resolved_markets)
    resolved_count = 0
    match_log = []

    for prediction in unresolved:
        q = prediction.get("market_question", "")
        match = _find_match(q, resolved_index)
        if match is None:
            continue

        matched_question, actual_outcome, score = match

        # 更新 agent_memory.json
        resolve_prediction(market_question=q, actual_outcome=actual_outcome)

        # 更新 analysis_audit.jsonl（ReputationEngine 的数据源）
        resolve_by_question(market_question=q, actual_outcome=actual_outcome)

        resolved_count += 1
        match_log.append({
            "prediction": q[:80],
            "matched_to": matched_question[:80],
            "actual_outcome": actual_outcome,
            "match_score": round(score, 3),
        })

    return {
        "status": "ok",
        "resolved_count": resolved_count,
        "checked_count": len(resolved_markets),
        "unresolved_predictions": len(unresolved),
        "matches": match_log,
    }


def _build_index(resolved_markets: list[dict]) -> dict[str, tuple[str, float]]:
    index = {}
    for m in resolved_markets:
        q = m.get("question", "")
        outcome = float(m.get("actual_outcome", 50.0))
        key = _normalize(q)
        if key:
            index[key] = (q, outcome)
    return index


def _find_match(question: str, index: dict) -> tuple[str, float, float] | None:
    if not question:
        return None
    norm_q = _normalize(question)
    tokens_q = set(_tokenize(norm_q))

    if norm_q in index:
        orig, outcome = index[norm_q]
        return orig, outcome, 1.0

    best_score, best_entry = 0.0, None
    for norm_key, (orig, outcome) in index.items():
        score = _token_overlap(tokens_q, set(_tokenize(norm_key)))
        if score > best_score:
            best_score, best_entry = score, (orig, outcome)

    if best_score >= FUZZY_THRESHOLD and best_entry:
        return best_entry[0], best_entry[1], best_score
    return None


def _normalize(text: str) -> str:
    return " ".join(text.lower().split()).strip()

def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]{2,}", text) if t not in _STOPWORDS]

def _token_overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
