from app.models.agent import AgentResult

from app.memory.reputation_engine import (
    ReputationEngine
)


class JudgeAgent:

    def __init__(self):

        self.rep_engine = ReputationEngine()

    async def evaluate(
        self,
        market_question: str,
        market_probability: float,
        agent_results: list[AgentResult]
    ):

        reputation_scores = (
            self.rep_engine.calculate_scores()
        )

        total_weight = 0

        weighted_sum = 0

        agent_outputs = []

        for result in agent_results:

            rep_score = reputation_scores.get(
                result.agent_name,
                {}
            ).get("score", 0.5)

            final_weight = (
                result.confidence * rep_score
            )

            weighted_sum += (
                result.probability * final_weight
            )

            total_weight += final_weight

            agent_outputs.append({

                "agent_name": result.agent_name,

                "probability": result.probability,

                "confidence": result.confidence,

                "reputation": rep_score,

                "weight": round(
                    final_weight,
                    3
                ),

                "reasoning": result.reasoning,

                "narrative_type": (
                    result.narrative_type
                ),

                "risk_flags": result.risk_flags
            })

        if total_weight == 0:

            final_probability = (
                market_probability
            )

        else:

            final_probability = (
                weighted_sum / total_weight
            )

        divergence = (
            final_probability
            - market_probability
        )

        abs_div = abs(divergence)

        if abs_div >= 25:
            signal_strength = "EXTREME"

        elif abs_div >= 15:
            signal_strength = "HIGH"

        elif abs_div >= 7:
            signal_strength = "MEDIUM"

        else:
            signal_strength = "LOW"

        if divergence > 0:
            signal_direction = "BULLISH"

        elif divergence < 0:
            signal_direction = "BEARISH"

        else:
            signal_direction = "NEUTRAL"

        return {

            "market_question": market_question,

            "market_probability": (
                market_probability
            ),

            "final_probability": round(
                final_probability,
                2
            ),

            "divergence": round(
                divergence,
                2
            ),

            "signal_strength": (
                signal_strength
            ),

            "signal_direction": (
                signal_direction
            ),

            "agents": agent_outputs
        }