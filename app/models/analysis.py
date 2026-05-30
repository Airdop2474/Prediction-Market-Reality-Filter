from pydantic import BaseModel


class AnalysisRequest(BaseModel):

    market_question: str

    market_probability: float


class AnalysisResponse(BaseModel):

    market_question: str

    market_probability: float

    ai_probability: float

    divergence: float

    signal_strength: str

    signal_direction: str

    overreaction_score: float

    confidence_score: float

    narrative_type: str

    narrative_summary: str

    reasoning: str

    risk_flags: list[str]

    signal: str

    position_size: float

    narrative_risk_score: int

    news_quality_score: float

    evidence_direction: str

    evidence_strength: float

    evidence_conflict_score: float

    freshness_score: float

    resolution_relevance_score: float

    priced_in_risk_score: int

    market_ambiguity_score: int

    condition_type: str

    base_rate_category: str

    base_rate_prior: float

    base_rate_range: list[float]

    evidence_constrained_probability: float

    base_rate_probability: float

    risk_level: str

    expected_edge: float
