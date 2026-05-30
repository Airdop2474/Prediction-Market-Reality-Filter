import asyncio
import logging
import math
import re
from typing import Any

from fastapi import APIRouter, Query

from app.memory.market_memory import get_cached_analysis, list_recent_markets, set_cached_analysis
from app.models.market import MarketModel
from app.services.analysis_audit_service import record_analysis
from app.services.ai_analysis_service import analyze_market
from app.services.gnews_service import fetch_google_news
from app.services.news_filter_service import filter_news_for_market
from app.services.polymarket_service import fetch_markets
from app.services.signal_audit_service import attach_audit_fields, audit_bucket
from app.memory.agent_memory import add_prediction
from app.services.rss_service import fetch_news
from app.agents.orchestrator import AgentOrchestrator
from app.utils.market_utils import safe_float

_deep_orchestrator = AgentOrchestrator()


router = APIRouter()
logger = logging.getLogger(__name__)

MIN_LIQUIDITY = 5_000
MIN_VOLUME = 1_000

ABSURD_MARKET_PATTERNS = (
    r"\bjesus\b.*\breturn",
    r"\bgta\b.*\bmeme",
    r"\bmeme spam\b",
    r"\babsurd crossover\b",
    r"\bwill .* say\b",
    r"\bwill .* tweet\b",
    r"\bwill .* post\b",
    r"\bwill .* wear\b",
)

ABSURD_MARKET_KEYWORDS = (
    "obvious joke",
    "meaningless",
    "shitpost",
    "meme coin drama",
    "random meme",
    "crossover episode",
)

NARRATIVE_CLARITY = {
    "factual": 1.0,
    "fundamental": 0.9,
    "official": 0.9,
    "speculative": 0.45,
    "clickbait": 0.35,
    "meme": 0.25,
    "satire": 0.2,
    "conspiracy": 0.2,
    "unknown": 0.3,
}


@router.get("/")
async def run_market_scanner(
    limit: int = Query(default=5, ge=1, le=20),
    use_cache: bool = Query(default=True),
):
    candidate_limit = min(limit * 5, 100)
    markets = await fetch_markets(limit=candidate_limit)

    # RSS 鏂伴椈鍙媺涓€娆★紝鎵€鏈夊競鍦哄鐢?
    rss_news = await fetch_news(limit=10)
    rss_articles = [
        {
            "title": item.title,
            "description": item.summary,
            "source": item.source,
            "published": item.published,
        }
        for item in rss_news
    ]
    # --- 骞惰澶勭悊姣忎釜甯傚満锛圙News + LLM 骞跺彂鎵ц锛?--
    # 鏈€澶у苟鍙戞暟 = 4锛岄伩鍏?LLM API 闄愰€?
    semaphore = asyncio.Semaphore(4)

    async def _process(market):
        async with semaphore:
            try:
                filter_reasons = get_market_filter_reasons(market)
                if filter_reasons:
                    log_filtered_market(market, filter_reasons)
                    return None

                if use_cache:
                    cached = get_cached_analysis(market.question)
                    if cached is not None:
                        logger.debug("Cache hit: %s", market.question[:60])
                        return cached

                google_news = await fetch_google_news(market.question)
                filtered_news = filter_news_for_market(
                    market_question=market.question,
                    articles=rss_articles + google_news,
                )
                if filtered_news["summary"]["selected_count"] == 0:
                    log_filtered_market(market, ["no_relevant_news"])
                    return None

                analysis = await analyze_market(
                    market_question=market.question,
                    market_probability=safe_float(market.yes_price, 0.5) * 100,
                    news_context=filtered_news["context"],
                    volume=safe_float(market.volume, 0),
                    liquidity=safe_float(market.liquidity, 0),
                )

                analysis["market_id"] = market.id
                analysis["liquidity"] = safe_float(market.liquidity, 0)
                analysis["volume"] = safe_float(market.volume, 0)
                analysis["market_quality_score"] = calculate_market_quality_score(
                    market=market,
                    news_count=filtered_news["summary"]["selected_count"],
                    narrative_type=analysis.get("narrative_type", "unknown"),
                )
                analysis["news_filter"] = filtered_news["summary"]
                analysis["evidence_profile"] = filtered_news["evidence_profile"]
                analysis["market_semantics"] = filtered_news["market_semantics"]

                log_signal_generated(analysis)
                record_analysis(analysis)
                add_prediction(
                    market_question=market.question,
                    market_probability=safe_float(market.yes_price, 0.5) * 100,
                    final_probability=safe_float(analysis.get("ai_probability"), 50),
                    agent_results=[{
                        "agent_name": "ai_analysis_service",
                        "probability": safe_float(analysis.get("ai_probability"), 50),
                        "confidence": safe_float(analysis.get("confidence_score"), 0),
                        "signal": analysis.get("signal", "WATCHLIST"),
                        "divergence": safe_float(analysis.get("divergence"), 0),
                    }],
                )
                if use_cache:
                    set_cached_analysis(market.question, analysis)
                return attach_audit_fields(analysis)
            except Exception as exc:
                logger.warning("Market processing failed [%s]: %s", market.question[:50], exc)
                return None

    raw_results = await asyncio.gather(*[_process(m) for m in markets])
    results = [r for r in raw_results if r is not None]

    results.sort(
        key=lambda item: (
            abs(safe_float(item.get("divergence"), 0)),
            safe_float(item.get("confidence_score"), 0),
            safe_float(item.get("liquidity"), 0),
        ),
        reverse=True,
    )
    return results[:limit]


@router.get("/summary")
async def scan_summary(
    limit: int = Query(default=10, ge=1, le=20),
    use_cache: bool = Query(default=True),
):
    """
    浜虹被鍙鐨勪俊鍙锋憳瑕併€傜洿鎺ュ憡璇変綘锛氫粖澶╂湁娌℃湁鍊煎緱鐪嬬殑甯傚満銆?
    涓嶉渶瑕佽В鏋?JSON锛岀洿鎺ョ湅 lines 瀛楁銆?
    """
    from app.services.polymarket_service import fetch_markets
    from app.services.gnews_service import fetch_google_news
    from app.services.news_filter_service import filter_news_for_market
    from app.services.ai_analysis_service import analyze_market
    from app.memory.market_memory import get_cached_analysis, set_cached_analysis

    markets = await fetch_markets(limit=limit * 5)
    rss_news = await fetch_news(limit=5)
    rss_articles = [
        {"title": a.title, "description": a.summary,
         "source": a.source, "published": a.published}
        for a in rss_news
    ]

    signal_emoji = {
        "STRONG_LONG": "馃煝馃煝", "LONG": "馃煝",
        "SHORT": "馃敶", "STRONG_SHORT": "馃敶馃敶",
        "WATCHLIST": "馃煛",
    }
    lines = []
    actionable = []
    watchlist = []

    _sem2 = asyncio.Semaphore(4)

    async def _proc_sum(market):
        async with _sem2:
            try:
                if get_market_filter_reasons(market):
                    return None
                cached = get_cached_analysis(market.question)
                if cached:
                    return cached
                google_news = await fetch_google_news(market.question)
                filtered = filter_news_for_market(
                    market_question=market.question,
                    articles=rss_articles + google_news,
                )
                if filtered["summary"]["selected_count"] == 0:
                    return None
                a = await analyze_market(
                    market_question=market.question,
                    market_probability=safe_float(market.yes_price, 0.5) * 100,
                    news_context=filtered["context"],
                    volume=safe_float(market.volume, 0),
                    liquidity=safe_float(market.liquidity, 0),
                )
                set_cached_analysis(market.question, a)
                return attach_audit_fields(a)
            except Exception:
                return None

    _raw = await asyncio.gather(*[_proc_sum(m) for m in markets])

    for a in [x for x in _raw if x is not None]:  # noqa 鈥?replaces old loop

        a = attach_audit_fields(a)
        sig = a.get("signal", "WATCHLIST")
        div = safe_float(a.get("divergence"), 0)
        conf = safe_float(a.get("confidence_score"), 0)
        mkt = safe_float(a.get("market_probability"), 50)
        ai = safe_float(a.get("ai_probability"), 50)
        q = a.get("market_question", "")[:80]
        em = signal_emoji.get(sig, "!")

        entry = {
            "signal": sig,
            "audit_verdict": a.get("audit_verdict"),
            "audit_label": a.get("audit_label"),
            "audit_reason": a.get("audit_reason"),
            "question": a.get("market_question", ""),
            "market_probability": mkt,
            "ai_probability": ai,
            "divergence": div,
            "confidence": conf,
            "narrative_type": a.get("narrative_type", ""),
            "reasoning": a.get("reasoning", "")[:200],
            "risk_level": a.get("risk_level", ""),
            "position_size_pct": round(
                safe_float(a.get("position_size"), 0) * 100, 2
            ),
        }

        line = (
            f"{em} [{sig}] {q}\n"
            f"   Market: {mkt:.1f}% 鈫?AI: {ai:.1f}% (div: {div:+.1f}%) "
            f"| conf: {conf:.2f} | risk: {a.get('risk_level','?')}"
        )

        if audit_bucket(a) == "review_queue":
            actionable.append(entry)
            lines.append(line)
        else:
            watchlist.append(entry)

        if len(actionable) + len(watchlist) >= limit:
            break

    if not lines:
        lines.append("鈿?No actionable signals today. All markets are WATCHLIST.")

    return {
        "date": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "actionable_count": len(actionable),
        "watchlist_count": len(watchlist),
        "review_count": len(actionable),
        "observation_count": len(watchlist),
        "summary": lines,
        "actionable": actionable,
        "watchlist": watchlist[:5],
        "review_queue": actionable,
        "observation_queue": watchlist[:5],
    }


@router.get("/debug")
async def scan_debug(market_question: str, market_probability: float = 50.0):
    """
    璋冭瘯绔偣锛氬鍗曚釜甯傚満闂鎷嗚В璐ㄩ噺闂ㄧ殑姣忎釜鏉′欢锛?
    甯姪璇婃柇涓轰粈涔堜俊鍙锋病鏈夋墦鍑烘潵銆?
    """
    from app.services.gnews_service import fetch_google_news
    from app.services.news_filter_service import filter_news_for_market
    from app.services.ai_analysis_service import (
        passes_analysis_quality_gate,
        calculate_confidence_score,
        calculate_priced_in_risk_score,
        score_news_quality,
        default_evidence_profile,
    )

    google_news = await fetch_google_news(market_question)
    rss_news = await fetch_news(limit=5)
    rss_articles = [
        {"title": a.title, "description": a.summary,
         "source": a.source, "published": a.published}
        for a in rss_news
    ]
    filtered = filter_news_for_market(
        market_question=market_question,
        articles=rss_articles + google_news,
    )
    evidence = filtered.get("evidence_profile") or default_evidence_profile()
    news_context = filtered.get("context", "")
    news_quality = score_news_quality(news_context)  # 浼?context 瀛楃涓诧紝涓嶆槸 articles 鍒楄〃
    priced_in = calculate_priced_in_risk_score(
        market_probability=market_probability,
        evidence_profile=evidence,
    )

    gate_checks = {
        "confidence_placeholder": {
            "note": "Run full /scan/ to get real LLM confidence",
            "threshold": ">= 0.50",
        },
        "news_quality": {
            "value": round(news_quality, 3),
            "threshold": ">= 0.40",
            "passes": news_quality >= 0.40,
        },
        "evidence_strength": {
            "value": round(evidence["evidence_strength"], 3),
            "threshold": ">= 0.20",
            "passes": evidence["evidence_strength"] >= 0.20,
        },
        "resolution_relevance": {
            "value": round(evidence["resolution_relevance_score"], 3),
            "threshold": ">= 0.22",
            "passes": evidence["resolution_relevance_score"] >= 0.22,
        },
        "conflict_score": {
            "value": round(evidence["conflict_score"], 3),
            "threshold": "<= 0.65",
            "passes": evidence["conflict_score"] <= 0.65,
        },
        "priced_in_risk": {
            "value": priced_in,
            "threshold": "<= 80",
            "passes": priced_in <= 80,
        },
    }

    failing = [k for k, v in gate_checks.items()
               if isinstance(v.get("passes"), bool) and not v["passes"]]
    news_count = filtered["summary"]["selected_count"]

    return {
        "market_question": market_question,
        "market_probability": market_probability,
        "news_articles_found": news_count,
        "news_articles_selected": news_count,
        "evidence_direction": evidence["evidence_direction"],
        "quality_gate": gate_checks,
        "failing_checks": failing,
        "would_pass_gate": len(failing) == 0,
        "diagnosis": (
            "鉁?Gate passed (confidence still needed from full LLM run)"
            if not failing
            else f"鉂?Blocked by: {', '.join(failing)}. "
                 "These conditions must ALL pass for any signal."
        ),
        "recommendation": _diagnose(failing, news_count),
    }


def _diagnose(failing: list[str], news_count: int) -> str:
    if not failing:
        return "Pre-gate checks pass. Run /scan/ for LLM confidence + final signal."
    tips = []
    if "news_quality" in failing:
        tips.append(
            "News quality < 0.40. Sources may be low-credibility or absent. "
            "Check if the topic has recent Reuters/AP/Bloomberg coverage."
        )
    if "evidence_strength" in failing:
        tips.append(
            f"Evidence strength < 0.20 ({news_count} articles selected). "
            "Too few relevant articles or articles don't clearly lean YES/NO."
        )
    if "resolution_relevance" in failing:
        tips.append(
            "Resolution relevance < 0.22. News discusses the topic but doesn't "
            "address the specific YES/NO condition. Look for more targeted sources."
        )
    if "conflict_score" in failing:
        tips.append(
            "Conflict score > 0.65. Sources strongly disagree. "
            "High-conflict markets are risky 鈥?wait for clearer consensus."
        )
    if "priced_in_risk" in failing:
        tips.append(
            "Priced-in risk > 80. Evidence already aligns with market price 鈥?"
            "little edge available from this news."
        )
    return " | ".join(tips) if tips else "Review evidence profile above."


@router.get("/deep")
async def run_deep_scanner(
    limit: int = Query(default=3, ge=1, le=10),
    use_cache: bool = Query(default=True),
):
    """
    娣卞害澶?Agent 鍒嗘瀽妯″紡銆?
    姣忎釜甯傚満骞惰杩愯 5 涓?Agent锛?
      NarrativeAgent 鈫?[ProbabilityAgent + ContrarianAgent + CrowdAgent
                         + FundamentalAgent + ManipulationAgent]
      鈫?RiskAgent 鈫?JudgeAgent锛堜俊瑾夊姞鏉冨悎骞讹級鈫?SignalAgent锛圞elly Criterion锛?

    姣?/scan/ 娑堣€楃害 5脳 鐨?LLM tokens锛屼絾淇″彿鏇寸ǔ鍋ャ€?
    寤鸿锛氬厛鐢?/scan/ 绛涢€夛紝瀵规劅鍏磋叮鐨勫競鍦哄啀鐢?/deep銆?
    """
    markets = await fetch_markets(limit=limit * 4)
    rss_news = await fetch_news(limit=10)
    rss_context = "\n\n".join(
        f"[{a.source}] {a.title}\n{a.summary}" for a in rss_news
    )
    results = []

    for market in markets:
        filter_reasons = get_market_filter_reasons(market)
        if filter_reasons:
            continue

        if use_cache:
            cached = get_cached_analysis(f"deep:{market.question}")
            if cached is not None:
                results.append(cached)
                continue

        google_news = await fetch_google_news(market.question)
        google_context = "\n\n".join(
            f"TITLE:\n{a['title']}\n\nDESCRIPTION:\n{a['description']}"
            for a in google_news
        )
        combined_news = f"{rss_context}\n\n{google_context}"

        analysis = await _deep_orchestrator.run(
            market_question=market.question,
            market_probability=safe_float(market.yes_price, 0.5) * 100,
            news_context=combined_news,
            volume=safe_float(market.volume, 0),
            liquidity=safe_float(market.liquidity, 0),
            use_cache=False,
        )
        analysis["market_id"] = market.id
        analysis["mode"] = "deep"

        set_cached_analysis(f"deep:{market.question}", analysis)
        results.append(analysis)

        if len(results) >= limit:
            break

    results.sort(
        key=lambda x: abs(safe_float(x.get("divergence"), 0)),
        reverse=True,
    )
    return results


@router.get("/cache")
async def get_cached_markets(limit: int = Query(default=20, ge=1, le=100)):
    """Return recent cached market analysis summaries without calling the LLM."""
    return list_recent_markets(limit=limit)


def get_market_filter_reasons(market: MarketModel) -> list[str]:
    reasons = []
    liquidity = safe_float(market.liquidity, 0)
    volume = safe_float(market.volume, 0)
    if liquidity < MIN_LIQUIDITY:
        reasons.append(f"liquidity<{MIN_LIQUIDITY}({liquidity:.0f})")
    if volume < MIN_VOLUME:
        reasons.append(f"volume<{MIN_VOLUME}({volume:.0f})")
    if bool(getattr(market, "closed", False)):
        reasons.append("closed_market")
    if bool(getattr(market, "resolved", False)):
        reasons.append("resolved_market")
    if is_absurd_market(market.question):
        reasons.append("absurd_market")
    return reasons


def is_absurd_market(question: str) -> bool:
    normalized = " ".join((question or "").lower().split())
    if not normalized:
        return True
    if any(keyword in normalized for keyword in ABSURD_MARKET_KEYWORDS):
        return True
    return any(re.search(pattern, normalized) for pattern in ABSURD_MARKET_PATTERNS)


def calculate_market_quality_score(
    market: MarketModel,
    news_count: int,
    narrative_type: str,
) -> int:
    liquidity = safe_float(market.liquidity, 0)
    volume = safe_float(market.volume, 0)
    liquidity_score = log_scaled_score(liquidity, floor=MIN_LIQUIDITY, ceiling=100_000)
    volume_score = log_scaled_score(volume, floor=MIN_VOLUME, ceiling=50_000)
    news_score = min(1.0, news_count / 5)
    clarity_score = NARRATIVE_CLARITY.get((narrative_type or "unknown").lower(), 0.45)
    score = (
        liquidity_score * 35
        + volume_score * 25
        + news_score * 20
        + clarity_score * 20
    )
    return int(max(0, min(100, round(score))))


def log_scaled_score(value: float, floor: float, ceiling: float) -> float:
    if value <= 0:
        return 0.0
    value = max(floor, min(value, ceiling))
    low = math.log10(floor)
    high = math.log10(ceiling)
    return (math.log10(value) - low) / (high - low)


def log_filtered_market(market: MarketModel, reasons: list[str]) -> None:
    logger.info(
        "Market filtered: id=%s liquidity=%.0f volume=%.0f reasons=%s question=%s",
        market.id,
        safe_float(market.liquidity, 0),
        safe_float(market.volume, 0),
        ",".join(reasons),
        market.question,
    )


def log_signal_generated(analysis: dict[str, Any]) -> None:
    logger.info(
        "Signal generated: signal=%s divergence=%.2f confidence=%.3f "
        "narrative_risk=%s priced_in=%s quality=%s liquidity=%.0f question=%s",
        analysis.get("signal", "WATCHLIST"),
        safe_float(analysis.get("divergence"), 0),
        safe_float(analysis.get("confidence_score"), 0),
        analysis.get("narrative_risk_score"),
        analysis.get("priced_in_risk_score"),
        analysis.get("market_quality_score"),
        safe_float(analysis.get("liquidity"), 0),
        analysis.get("market_question", ""),
    )
