from fastapi import APIRouter
from app.services.rss_service import fetch_news

router = APIRouter()


@router.get("/")
async def get_news(limit: int = 10):
    news = await fetch_news(limit)

    return {
        "count": len(news),
        "news": news
    }