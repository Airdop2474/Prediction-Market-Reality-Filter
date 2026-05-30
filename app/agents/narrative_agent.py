import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.agent import AgentResult


DEFAULT_NARRATIVE_RESULT: dict[str, Any] = {
    "narrative_type": "unknown",
    "summary": "",
    "sentiment": "neutral",
    "hype_score": 0.0,
    "meme_score": 0.0,
    "satire_score": 0.0,
}


client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.DASHSCOPE_BASE_URL,
)


class NarrativeAgent:
    name = "narrative_agent"

    async def analyze_json(
        self,
        market_question: str,
        news_context: str,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(
            market_question=market_question,
            news_context=news_context,
        )

        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You analyze news narratives. Return only "
                            "valid JSON. Keep the answer concise."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            parsed = json.loads(content or "{}")

            return self._normalize_result(parsed)

        except Exception:
            return DEFAULT_NARRATIVE_RESULT.copy()

    async def analyze(
        self,
        market_question: str,
        market_probability: float,
        news_context: str,
    ) -> AgentResult:
        result = await self.analyze_json(
            market_question=market_question,
            news_context=news_context,
        )

        return AgentResult(
            agent_name=self.name,
            probability=market_probability,
            confidence=self._confidence_from_scores(result),
            reasoning=json.dumps(
                result,
                ensure_ascii=False,
            ),
            narrative_type=result["narrative_type"],
            risk_flags=self._risk_flags(result),
        )

    def _build_prompt(
        self,
        market_question: str,
        news_context: str,
    ) -> str:
        safe_question = self._sanitize_text(market_question)
        safe_news = self._sanitize_text(news_context)[:8000]

        return f"""
Task: summarize the news and identify the narrative.

Focus only on:
- news summary
- narrative type
- meme signal
- hype signal
- satire signal

Do not estimate probability. Do not provide trading signals.
Use gentle labels such as geopolitical tension, political instability,
or international conflict when relevant.

Return exactly this JSON shape:
{{
  "narrative_type": "...",
  "summary": "...",
  "sentiment": "...",
  "hype_score": 0.0,
  "meme_score": 0.0,
  "satire_score": 0.0
}}

Market question:
{safe_question}

News:
{safe_news}
""".strip()

    def _normalize_result(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        result = DEFAULT_NARRATIVE_RESULT.copy()

        if not isinstance(data, dict):
            return result

        for key in ("narrative_type", "summary", "sentiment"):
            value = data.get(key)

            if isinstance(value, str):
                result[key] = value.strip()

        for key in ("hype_score", "meme_score", "satire_score"):
            result[key] = self._clamp_score(data.get(key))

        return result

    def _clamp_score(
        self,
        value: Any,
    ) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0

        return round(
            max(0.0, min(score, 1.0)),
            3,
        )

    def _confidence_from_scores(
        self,
        result: dict[str, Any],
    ) -> float:
        max_signal = max(
            result["hype_score"],
            result["meme_score"],
            result["satire_score"],
        )

        if result["summary"]:
            return round(max(0.3, max_signal), 3)

        return 0.0

    def _risk_flags(
        self,
        result: dict[str, Any],
    ) -> list[str]:
        flags = []

        if result["hype_score"] >= 0.7:
            flags.append("high_hype")

        if result["meme_score"] >= 0.7:
            flags.append("meme_narrative")

        if result["satire_score"] >= 0.7:
            flags.append("possible_satire")

        return flags

    def _sanitize_text(self, text: str) -> str:
        """
        清理文本，移除 null bytes 等控制字符。

        原有的词汇替换逻辑（war → geopolitical tension 等）已移除：
        - str.replace() 是子串匹配，会破坏合法词汇（如 "award" → "ageopolitical tensionrd"）
        - 内容过滤应由 news_filter_service 的 LOW_QUALITY_TERMS 来处理
        - LLM 系统提示中的 HARD_RULES 足以引导分析方向
        """
        return (text or "").replace("\x00", " ").strip()
