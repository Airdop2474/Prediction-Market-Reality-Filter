from fastapi import APIRouter
from app.services.polymarket_service import fetch_markets

router = APIRouter()


@router.get("/")
async def get_markets(limit: int = 10):
    markets = await fetch_markets(limit)

    return {
        "count": len(markets),
        "markets": markets
    }