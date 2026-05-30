from app.agents.base_agent import BaseAgent

from app.models.agent import AgentResult

from app.services.openai_service import ask_llm


class ContrarianAgent(BaseAgent):

    name = "contrarian_agent"

    async def analyze(
        self,
        market_question: str,
        market_probability: float,
        news_context: str
    ):

        prompt = f"""
You are a contrarian prediction market agent.

Your task:

1. Assume the crowd is wrong
2. Find hidden risks
3. Detect irrational narratives
4. Detect speculative bubbles
5. Challenge consensus thinking

MARKET QUESTION:
{market_question}

MARKET PROBABILITY:
{market_probability}

NEWS:
{news_context}

Return EXACTLY:

TRUE_PROBABILITY: <number>

CONFIDENCE: <0-1>

NARRATIVE_TYPE: <type>

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

            risk_flags=[
                "contrarian_analysis"
            ]
        )