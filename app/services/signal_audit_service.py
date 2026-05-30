from typing import Any

from app.utils.market_utils import safe_float


ACTIONABLE_SIGNALS = {"STRONG_LONG", "LONG", "SHORT", "STRONG_SHORT"}


def audit_verdict(analysis: dict[str, Any]) -> str:
    signal = str(analysis.get("signal", "WATCHLIST"))
    confidence = safe_float(analysis.get("confidence_score"), 0)
    news_quality = safe_float(analysis.get("news_quality_score"), 0)
    evidence_strength = safe_float(analysis.get("evidence_strength"), 0)
    relevance = safe_float(analysis.get("resolution_relevance_score"), 0)
    conflict = safe_float(analysis.get("evidence_conflict_score"), 0)
    priced_in = safe_float(analysis.get("priced_in_risk_score"), 100)

    if signal not in ACTIONABLE_SIGNALS:
        return "OBSERVE"
    if confidence >= 0.68 and news_quality >= 0.55 and evidence_strength >= 0.35 and relevance >= 0.35 and conflict <= 0.45 and priced_in <= 65:
        return "HIGH_TRUST"
    return "REVIEW"


def audit_label(verdict: str) -> str:
    return {
        "HIGH_TRUST": "High-trust audit",
        "REVIEW": "Needs human review",
        "OBSERVE": "Observe only",
    }.get(verdict, "Observe only")


def audit_reason(analysis: dict[str, Any]) -> str:
    verdict = audit_verdict(analysis)
    if verdict == "HIGH_TRUST":
        return "Passed signal, evidence, relevance, conflict, and priced-in audit gates."
    if verdict == "REVIEW":
        return "Signal exists, but at least one audit dimension needs human review before action."
    return "Did not pass the full credibility gate; keep it in observation."


def attach_audit_fields(analysis: dict[str, Any]) -> dict[str, Any]:
    result = dict(analysis)
    verdict = audit_verdict(result)
    result["audit_verdict"] = verdict
    result["audit_label"] = audit_label(verdict)
    result["audit_reason"] = audit_reason(result)
    result["decision_mode"] = "HUMAN_REVIEW"
    return result


def audit_bucket(analysis: dict[str, Any]) -> str:
    verdict = str(analysis.get("audit_verdict") or audit_verdict(analysis))
    if verdict in {"HIGH_TRUST", "REVIEW"}:
        return "review_queue"
    return "observation_queue"
