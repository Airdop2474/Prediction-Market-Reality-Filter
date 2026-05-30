import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.agent import AgentResult
from app.services.base_rate_service import (
    anchor_probability,
    classify_market,
    get_base_rate_context,
)


DEFAULT_PROBABILITY_RESULT: dict[str, Any] = {
    "true_probability": 50.0,
    "confidence_score": 0.0,
    "reasoning": "Probability estimate unavailable.",
    "base_rate_category": "unknown",
    "anchored": False,
}

client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.DASHSCOPE_BASE_URL,
)


class ProbabilityAgent:
    name = "probability_agent"

    async def estimate(
        self,
        market_question: str,
        market_probability: float,
        narrative_result: dict[str, Any],
    ) -> dict[str, Any]:
        base_rate_ctx = get_base_rate_context(market_question)
        prompt = self._build_prompt(
            market_question=market_question,
            market_probability=market_probability,
            narrative_result=narrative_result,
            base_rate_ctx=base_rate_ctx,
        )

        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You estimate event probability for prediction markets. "
                            "Return only valid JSON. Keep reasoning under 120 words. "
                            "Be calibrated: if you are uncertain, say so via confidence_score."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            parsed = json.loads(content or "{}")
            result = self._normalize_result(
                data=parsed,
                fallback_probability=market_probability,
            )

        except Exception:
            result = self._default_result(market_probability)

        # ── Base rate anchoring ───────────────────────────────────────────
        base_rate = classify_market(market_question)
        raw_prob = result["true_probability"]
        anchored_prob = anchor_probability(
            llm_probability=raw_prob,
            base_rate=base_rate,
            confidence=result["confidence_score"],
        )

        result["true_probability"] = anchored_prob
        result["raw_llm_probability"] = raw_prob
        result["base_rate_category"] = base_rate.category
        result["base_rate_prior"] = base_rate.prior
        result["anchored"] = True

        return result

    async def analyze(
        self,
        market_question: str,
        market_probability: float,
        narrative_result: dict[str, Any],
    ) -> AgentResult:
        result = await self.estimate(
            market_question=market_question,
            market_probability=market_probability,
            narrative_result=narrative_result,
        )
        return AgentResult(
            agent_name=self.name,
            probability=result["true_probability"],
            confidence=result["confidence_score"],
            reasoning=result["reasoning"],
            narrative_type="probability_estimation",
            risk_flags=[],
        )

    def _build_prompt(
        self,
        market_question: str,
        market_probability: float,
        narrative_result: dict[str, Any],
        base_rate_ctx: dict[str, Any],
    ) -> str:
        safe_question = market_question.strip()[:500]
        safe_narrative = json.dumps(narrative_result, ensure_ascii=False)[:3000]

        return f"""Task: estimate the TRUE probability for this prediction market.

IMPORTANT ANCHORING INFORMATION:
  Event category: {base_rate_ctx["category"]}
  Historical base rate for this category: {base_rate_ctx["historical_range"]}
  Note: {base_rate_ctx["note"]}

Start from the historical base rate. Only deviate if you have strong evidence.
Be resistant to hype and meme narratives in the news.

Market question:
{safe_question}

Current market probability (crowd estimate):
{market_probability}%

Narrative analysis:
{safe_narrative}

Rules:
- true_probability: 0–100 (your calibrated estimate)
- confidence_score: 0–1 (how confident are you? be honest)
- reasoning: ≤120 words, explain deviation from base rate

Return exactly:
{{
  "true_probability": 0.0,
  "confidence_score": 0.0,
  "reasoning": "..."
}}""".strip()

    def _normalize_result(
        self,
        data: dict[str, Any],
        fallback_probability: float,
    ) -> dict[str, Any]:
        result = self._default_result(fallback_probability)
        if not isinstance(data, dict):
            return result
        result["true_probability"] = self._clamp(
            data.get("true_probability", fallback_probability), 0, 100
        )
        result["confidence_score"] = self._clamp(
            data.get("confidence_score", 0.0), 0, 1
        )
        reasoning = data.get("reasoning", "")
        if isinstance(reasoning, str) and reasoning.strip():
            words = reasoning.split()
            result["reasoning"] = " ".join(words[:120])
        return result

    def _default_result(self, market_probability: float) -> dict[str, Any]:
        result = DEFAULT_PROBABILITY_RESULT.copy()
        result["true_probability"] = self._clamp(market_probability, 0, 100)
        return result

    def _clamp(self, value: Any, lo: float, hi: float) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            v = (lo + hi) / 2
        return round(max(lo, min(hi, v)), 3)
