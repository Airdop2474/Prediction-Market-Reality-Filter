import json
import re

from openai import AsyncOpenAI

from app.core.config import settings


_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
        )
    return _client


def _extract_float(pattern: str, text: str, fallback: float = 0.0) -> float:
    match = re.search(pattern, text)
    if match:
        try:
            return float(match.group(1))
        except (ValueError, TypeError):
            return fallback
    return fallback


async def ask_llm(prompt: str) -> dict:
    """
    Legacy helper used by older agents (contrarian, crowd, etc.).
    Migrated to AsyncOpenAI with JSON mode.
    """
    client = get_client()

    system = (
        "You are a professional prediction market analyst. "
        "Return only valid JSON with keys: "
        "true_probability (0-100), confidence (0-1), "
        "narrative_type (string), reasoning (string ≤120 words)."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        data = json.loads(content)

        probability = float(data.get("true_probability", 50))
        confidence = float(data.get("confidence", 0.5))
        narrative_type = str(data.get("narrative_type", "unknown"))
        reasoning = str(data.get("reasoning", ""))

        return {
            "probability": max(0.0, min(100.0, probability)),
            "confidence": max(0.0, min(1.0, confidence)),
            "narrative_type": narrative_type,
            "reasoning": reasoning,
        }

    except Exception as exc:
        return {
            "probability": 50.0,
            "confidence": 0.0,
            "narrative_type": "API_ERROR",
            "reasoning": str(exc),
        }
