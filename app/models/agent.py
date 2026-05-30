from pydantic import BaseModel
from typing import List


class AgentResult(BaseModel):

    agent_name: str

    probability: float

    confidence: float

    reasoning: str

    narrative_type: str

    risk_flags: List[str] = []