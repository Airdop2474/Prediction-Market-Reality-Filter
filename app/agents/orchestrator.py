"""
orchestrator.py
===============
协调所有 Agent 的主流程。

流程：
  1. NarrativeAgent（串行，其他 Agent 依赖它的输出）
  2. 并行运行：ProbabilityAgent + ContrarianAgent + CrowdAgent
                + FundamentalAgent + ManipulationAgent
  3. RiskAgent（汇总所有 Agent 的 risk flags）
  4. JudgeAgent（reputation 加权合并概率）
  5. SignalAgent（Kelly Criterion 生成信号）
  6. 写入 MarketMemory 缓存
"""

import asyncio
import logging
from typing import Any

from app.agents.narrative_agent import NarrativeAgent
from app.agents.probability_agent import ProbabilityAgent
from app.agents.contrarian_agent import ContrarianAgent
from app.agents.crowd_agent import CrowdAgent
from app.agents.fundamental_agent import FundamentalAgent
from app.agents.manipulation_agent import ManipulationAgent
from app.agents.risk_agent import RiskAgent
from app.agents.signal_agent import SignalAgent
from app.agents.judge_agent import JudgeAgent
from app.models.agent import AgentResult
from app.memory.market_memory import get_cached_analysis, set_cached_analysis

logger = logging.getLogger(__name__)

# 默认 fallback narrative result
_NULL_NARRATIVE: dict[str, Any] = {
    "narrative_type": "unknown",
    "summary": "",
    "sentiment": "neutral",
    "hype_score": 0.0,
    "meme_score": 0.0,
    "satire_score": 0.0,
}

_NULL_PROBABILITY: dict[str, Any] = {
    "true_probability": 50.0,
    "confidence_score": 0.0,
    "reasoning": "unavailable",
    "anchored": False,
}


class AgentOrchestrator:
    def __init__(self) -> None:
        self.narrative_agent = NarrativeAgent()
        self.probability_agent = ProbabilityAgent()
        self.contrarian_agent = ContrarianAgent()
        self.crowd_agent = CrowdAgent()
        self.fundamental_agent = FundamentalAgent()
        self.manipulation_agent = ManipulationAgent()
        self.risk_agent = RiskAgent()
        self.signal_agent = SignalAgent()
        self.judge_agent = JudgeAgent()

    async def run(
        self,
        market_question: str,
        market_probability: float,
        news_context: str,
        volume: float | None = None,
        liquidity: float | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        market_probability = self._clamp(market_probability, 0, 100)

        # ── Cache ─────────────────────────────────────────────────────
        if use_cache:
            cached = get_cached_analysis(market_question)
            if cached is not None:
                logger.debug("Cache hit: %s", market_question[:60])
                return cached

        # ── Step 1: Narrative (serial — others depend on it) ──────────
        narrative_result = await self._safe(
            self.narrative_agent.analyze_json(
                market_question=market_question,
                news_context=news_context,
            ),
            fallback=_NULL_NARRATIVE.copy(),
            label="NarrativeAgent",
        )

        # ── Step 2: Parallel probability agents ───────────────────────
        prob_task = self._safe(
            self.probability_agent.estimate(
                market_question=market_question,
                market_probability=market_probability,
                narrative_result=narrative_result,
            ),
            fallback=_NULL_PROBABILITY.copy(),
            label="ProbabilityAgent",
        )
        contrarian_task = self._safe(
            self.contrarian_agent.analyze(
                market_question=market_question,
                market_probability=market_probability,
                news_context=news_context,
            ),
            fallback=self._null_agent_result("contrarian_agent", market_probability),
            label="ContrarianAgent",
        )
        crowd_task = self._safe(
            self.crowd_agent.analyze(
                market_question=market_question,
                market_probability=market_probability,
                news_context=news_context,
            ),
            fallback=self._null_agent_result("crowd_agent", market_probability),
            label="CrowdAgent",
        )
        fundamental_task = self._safe(
            self.fundamental_agent.analyze(
                market_question=market_question,
                market_probability=market_probability,
                news_context=news_context,
            ),
            fallback=self._null_agent_result("fundamental_agent", market_probability),
            label="FundamentalAgent",
        )
        manipulation_task = self._safe(
            self.manipulation_agent.analyze(
                market_question=market_question,
                market_probability=market_probability,
                news_context=news_context,
            ),
            fallback=self._null_agent_result("manipulation_agent", market_probability),
            label="ManipulationAgent",
        )

        (
            probability_result,
            contrarian_result,
            crowd_result,
            fundamental_result,
            manipulation_result,
        ) = await asyncio.gather(
            prob_task,
            contrarian_task,
            crowd_task,
            fundamental_task,
            manipulation_task,
        )

        # ── Step 3: Risk Agent ────────────────────────────────────────
        all_risk_flags = (
            (contrarian_result.risk_flags if isinstance(contrarian_result, AgentResult) else [])
            + (manipulation_result.risk_flags if isinstance(manipulation_result, AgentResult) else [])
        )
        risk_result = await self._safe(
            self.risk_agent.analyze(
                market_question=market_question,
                market_probability=market_probability,
                narrative_result=narrative_result,
                probability_result=probability_result,
                volume=volume,
                liquidity=liquidity,
            ),
            fallback={"risk_level": "HIGH", "risk_flags": ["agent_error"]},
            label="RiskAgent",
        )
        # Merge flags from sub-agents
        risk_result["risk_flags"] = list(
            set(risk_result.get("risk_flags", []) + all_risk_flags)
        )

        # ── Step 4: JudgeAgent (reputation-weighted probability) ──────
        agent_results: list[AgentResult] = []
        # ProbabilityAgent
        agent_results.append(AgentResult(
            agent_name="probability_agent",
            probability=probability_result.get("true_probability", market_probability),
            confidence=probability_result.get("confidence_score", 0.0),
            reasoning=probability_result.get("reasoning", ""),
            narrative_type="probability",
            risk_flags=[],
        ))
        for ar in [contrarian_result, crowd_result, fundamental_result, manipulation_result]:
            if isinstance(ar, AgentResult):
                agent_results.append(ar)

        judge_output = await self._safe(
            self.judge_agent.evaluate(
                market_question=market_question,
                market_probability=market_probability,
                agent_results=agent_results,
            ),
            fallback={
                "final_probability": probability_result.get("true_probability", market_probability),
                "divergence": 0.0,
                "agents": [],
            },
            label="JudgeAgent",
        )

        final_probability = self._clamp(
            judge_output.get("final_probability", market_probability), 0, 100
        )

        # ── Step 5: Signal Agent ──────────────────────────────────────
        probability_for_signal = dict(probability_result)
        probability_for_signal["true_probability"] = final_probability
        signal_result = await self._safe(
            self.signal_agent.generate(
                market_probability=market_probability,
                probability_result=probability_for_signal,
                risk_result=risk_result,
            ),
            fallback={
                "signal": "NO_TRADE", "edge": 0.0, "position_size": 0.0,
                "kelly_fraction": 0.0, "signal_strength": "LOW",
                "signal_direction": "NEUTRAL", "reason": "fallback",
            },
            label="SignalAgent",
        )

        divergence = round(final_probability - market_probability, 2)

        result: dict[str, Any] = {
            "market_question": market_question,
            "market_probability": market_probability,
            "ai_probability": final_probability,
            "true_probability": final_probability,
            "final_probability": final_probability,
            "raw_llm_probability": probability_result.get("raw_llm_probability"),
            "base_rate_category": probability_result.get("base_rate_category"),
            "base_rate_prior": probability_result.get("base_rate_prior"),
            "divergence": divergence,
            "overreaction_score": abs(divergence),
            "confidence_score": probability_result.get("confidence_score", 0.0),
            "reasoning": probability_result.get("reasoning", ""),
            "narrative_type": narrative_result.get("narrative_type", "unknown"),
            "narrative_summary": narrative_result.get("summary", ""),
            "narrative": narrative_result,
            "probability": probability_result,
            "risk": risk_result,
            "risk_flags": risk_result.get("risk_flags", []),
            "risk_level": risk_result.get("risk_level", "HIGH"),
            "signal": signal_result.get("signal", "NO_TRADE"),
            "signal_strength": signal_result.get("signal_strength", "LOW"),
            "signal_direction": signal_result.get("signal_direction", "NEUTRAL"),
            "position_size": signal_result.get("position_size", 0.0),
            "kelly_fraction": signal_result.get("kelly_fraction", 0.0),
            "expected_edge": signal_result.get("edge", 0.0),
            "signal_reason": signal_result.get("reason", ""),
            "judge": judge_output,
            "agents": {
                "narrative_agent": narrative_result,
                "probability_agent": probability_result,
                "risk_agent": risk_result,
                "signal_agent": signal_result,
                "judge_agent": judge_output,
            },
        }

        if use_cache:
            set_cached_analysis(market_question, result)

        return result

    # ── Helpers ───────────────────────────────────────────────────────

    async def _safe(self, coro, fallback: Any, label: str) -> Any:
        try:
            return await coro
        except Exception as exc:
            logger.warning("%s failed: %s", label, exc)
            return fallback

    def _null_agent_result(
        self, name: str, probability: float
    ) -> AgentResult:
        return AgentResult(
            agent_name=name,
            probability=probability,
            confidence=0.0,
            reasoning="Agent unavailable.",
            narrative_type="unknown",
            risk_flags=[],
        )

    def _clamp(self, value: Any, lo: float, hi: float) -> float:
        try:
            return round(max(lo, min(hi, float(value))), 2)
        except (TypeError, ValueError):
            return (lo + hi) / 2
