import asyncio
import re
from functools import partial
from typing import Any

from gnews import GNews

from app.core.config import settings


_gnews_client = GNews(
    language="en",
    country="US",
    max_results=settings.GNEWS_MAX_RESULTS,
)

STOPWORDS = {
    "will", "this", "that", "with", "from", "about", "market",
    "polymarket", "before", "after", "above", "below", "between",
    "yes", "no", "the", "and", "or", "for", "to", "of", "in", "on",
}


def _sync_fetch(query: str) -> list[dict[str, Any]]:
    try:
        results = _gnews_client.get_news(query)
    except Exception:
        return []

    articles = []
    for item in results:
        publisher = item.get("publisher") or {}
        source = ""
        if isinstance(publisher, dict):
            source = str(publisher.get("title", "") or "")

        articles.append({
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "published_date": item.get("published date", ""),
            "source": source,
            "url": item.get("url", ""),
            "query": query,
        })
    return articles


async def fetch_google_news(query: str) -> list[dict[str, Any]]:
    loop = asyncio.get_event_loop()
    queries = build_news_queries(query)
    tasks = [
        loop.run_in_executor(None, partial(_sync_fetch, q))
        for q in queries
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    articles = []
    for result in results:
        if isinstance(result, Exception):
            continue
        articles.extend(result)

    return dedupe_articles(articles)


def build_news_queries(query: str) -> list[str]:
    clean_query = normalize_query(query)
    keywords = extract_keywords(clean_query)
    queries = [clean_query]

    if len(keywords) >= 2:
        queries.append(" ".join(keywords[:4]))
    if len(keywords) >= 3:
        queries.append(" ".join(keywords[:3]) + " latest news")

    unique = []
    seen = set()
    for item in queries:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item[:180])
    return unique[:3]


def normalize_query(query: str) -> str:
    text = (query or "").replace("?", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_keywords(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]{3,}", text.lower())
    return [
        token
        for token in tokens
        if token not in STOPWORDS and not token.isdigit()
    ][:8]


def dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for article in articles:
        key = normalize_article_key(article)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def normalize_article_key(article: dict[str, Any]) -> str:
    title = str(article.get("title", "") or "").lower()
    words = extract_keywords(title)
    return " ".join(words[:8])
