from typing import Any


DEFAULT_RISK_RESULT: dict[str, Any] = {
    "risk_level": "LOW",
    "risk_flags": [],
}


class RiskAgent:
    name = "risk_agent"

    async def analyze(
        self,
        market_question: str,
        market_probability: float,
        narrative_result: dict[str, Any],
        probability_result: dict[str, Any],
        volume: float | None = None,
        liquidity: float | None = None,
    ) -> dict[str, Any]:
        try:
            flags = []

            if self._score(narrative_result, "hype_score") >= 0.7:
                flags.append("high_hype")

            if self._score(narrative_result, "meme_score") >= 0.7:
                flags.append("meme_driven")

            if self._score(narrative_result, "satire_score") >= 0.6:
                flags.append("satire_or_unclear_source")

            if self._is_low_liquidity(liquidity):
                flags.append("low_liquidity")

            if self._is_low_volume(volume):
                flags.append("low_volume")

            confidence = self._score(
                probability_result,
                "confidence_score",
            )

            if confidence < 0.35:
                flags.append("low_model_confidence")

            divergence = abs(
                self._probability(
                    probability_result.get("true_probability"),
                    market_probability,
                )
                - self._probability(market_probability, 50.0)
            )

            if divergence >= 25:
                flags.append("large_market_divergence")

            return {
                "risk_level": self._risk_level(flags),
                "risk_flags": flags,
            }

        except Exception:
            return DEFAULT_RISK_RESULT.copy()

    def _risk_level(
        self,
        flags: list[str],
    ) -> str:
        high_risk_flags = {
            "low_liquidity",
            "satire_or_unclear_source",
            "low_model_confidence",
        }

        if len(flags) >= 4 or any(flag in high_risk_flags for flag in flags):
            return "HIGH"

        if len(flags) >= 2:
            return "MEDIUM"

        return "LOW"

    def _score(
        self,
        data: dict[str, Any],
        key: str,
    ) -> float:
        try:
            score = float(data.get(key, 0.0))
        except (AttributeError, TypeError, ValueError):
            return 0.0

        return max(0.0, min(score, 1.0))

    def _probability(
        self,
        value: Any,
        fallback: float,
    ) -> float:
        try:
            probability = float(value)
        except (TypeError, ValueError):
            probability = fallback

        return max(0.0, min(probability, 100.0))

    def _is_low_liquidity(
        self,
        liquidity: float | None,
    ) -> bool:
        if liquidity is None:
            return False

        try:
            return float(liquidity) < 1000
        except (TypeError, ValueError):
            return False

    def _is_low_volume(
        self,
        volume: float | None,
    ) -> bool:
        if volume is None:
            return False

        try:
            return float(volume) < 1000
        except (TypeError, ValueError):
            return False
