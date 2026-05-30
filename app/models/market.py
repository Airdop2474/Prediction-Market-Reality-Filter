from pydantic import BaseModel
from typing import Optional


class MarketModel(BaseModel):
    id: str
    question: str
    yes_price: Optional[float] = None
    no_price: Optional[float] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    closed: bool = False
    archived: bool = False
    resolved: bool = False
    end_date: Optional[str] = None
