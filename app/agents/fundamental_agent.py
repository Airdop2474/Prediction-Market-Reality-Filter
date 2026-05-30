from app.agents.base_agent import BaseAgent

from app.models.agent import AgentResult

from app.services.openai_service import ask_llm


class FundamentalAgent(BaseAgent):

    name = "fundamental_agent"

    async def analyze(
        self,
        market_question: str,
        market_probability: float,
        news_context: str
    ):

        prompt = f"""
You are a fundamental analysis agent.

Ignore media hype.

Focus ONLY on:

- historical probability
- political structure
- economic fundamentals
- realistic event likelihood

MARKET QUESTION:
{market_question}

MARKET PROBABILITY:
{market_probability}

Return EXACTLY:

TRUE_PROBABILITY: <number>

CONFIDENCE: <0-1>

NARRATIVE_TYPE: Fundamental

REASONING:
<reasoning>
"""

        result = await ask_llm(prompt)

        return AgentResult(
            agent_name=self.name,

            probability=result["probability"],

            confidence=result["confidence"],

            reasoning=result["reasoning"],

            narrative_type=result["narrative_type"],

            risk_flags=[]
        )