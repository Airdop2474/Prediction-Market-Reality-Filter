from fastapi import APIRouter

from app.services.gnews_service import fetch_google_news

from app.models.analysis import AnalysisRequest

from app.services.analysis_audit_service import get_audit_summary, record_analysis

from app.services.ai_analysis_service import analyze_market

from app.services.news_filter_service import filter_news_for_market

from app.services.rss_service import fetch_news


router = APIRouter()


@router.post("/")
async def run_analysis(payload: AnalysisRequest):

    news_items = await fetch_news(limit=5)

    google_news = await fetch_google_news(
        payload.market_question
    )

    rss_articles = [
        {
            "title": n.title,
            "description": n.summary,
            "source": n.source,
            "published": n.published,
        }
        for n in news_items
    ]
    filtered_news = filter_news_for_market(
        market_question=payload.market_question,
        articles=rss_articles + google_news,
    )

    analysis = await analyze_market(
        market_question=payload.market_question,
        market_probability=payload.market_probability,
        news_context=filtered_news["context"],
    )
    analysis["news_filter"] = filtered_news["summary"]
    analysis["evidence_profile"] = filtered_news["evidence_profile"]
    analysis["market_semantics"] = filtered_news["market_semantics"]
    record_analysis(analysis)

    return analysis


@router.get("/audit")
async def get_analysis_audit():
    return get_audit_summary()
