import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from app.services.market_semantics_service import (
    build_semantics_context,
    parse_market_semantics,
)


TRUSTED_SOURCES = (
    "reuters",
    "associated press",
    "ap news",
    "bloomberg",
    "financial times",
    "wall street journal",
    "wsj",
    "cnbc",
    "the guardian",
    "bbc",
    "politico",
    "axios",
    "the verge",
)

LOW_QUALITY_TERMS = (
    "rumor",
    "unconfirmed",
    "allegedly",
    "speculation",
    "shocking",
    "you won't believe",
    "bombshell",
    "insane",
    "meme",
    "satire",
    "parody",
    "the onion",
    "babylon bee",
    "conspiracy",
    "hoax",
)

STOPWORDS = {
    "will", "the", "this", "that", "with", "from", "into", "about",
    "after", "before", "over", "under", "market", "polymarket", "yes",
    "no", "and", "or", "for", "to", "of", "in", "on", "by", "a", "an",
}


def filter_news_for_market(
    market_question: str,
    articles: list[dict[str, Any]],
    max_items: int = 6,
) -> dict[str, Any]:
    scored = []
    rejected = []
    semantics = parse_market_semantics(market_question)

    for article in articles:
        normalized = normalize_article(article)
        score, reasons = score_article(market_question, normalized, semantics)
        normalized["quality_score"] = score
        normalized["quality_reasons"] = reasons

        if score < 0.35:
            rejected.append({
                "title": normalized["title"],
                "score": score,
                "reasons": reasons,
            })
            continue

        scored.append(normalized)

    scored.sort(
        key=lambda item: (
            item["quality_score"],
            item["source_quality"],
            item["relevance_score"],
        ),
        reverse=True,
    )
    selected = dedupe_articles(scored)[:max_items]
    evidence_profile = build_evidence_profile(market_question, selected)

    return {
        "articles": selected,
        "context": build_news_context(selected, evidence_profile, semantics),
        "evidence_profile": evidence_profile,
        "market_semantics": semantics,
        "summary": {
            "input_count": len(articles),
            "selected_count": len(selected),
            "rejected_count": len(rejected),
            "average_quality": average_quality(selected),
            "evidence_strength": evidence_profile["evidence_strength"],
            "evidence_direction": evidence_profile["evidence_direction"],
            "conflict_score": evidence_profile["conflict_score"],
            "freshness_score": evidence_profile["freshness_score"],
            "rejected": rejected[:10],
        },
    }


def normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    title = str(article.get("title", "") or "").strip()
    description = str(
        article.get("description")
        or article.get("summary")
        or article.get("desc")
        or ""
    ).strip()
    source = str(article.get("source", "") or article.get("publisher", "") or "").strip()
    published = str(
        article.get("published")
        or article.get("published_date")
        or article.get("published date")
        or ""
    ).strip()

    if not source:
        source = infer_source(title)

    return {
        "title": title,
        "description": description,
        "source": source,
        "published": published,
        "source_quality": score_source_quality(source, title),
        "age_score": score_age(published),
    }


def score_article(
    market_question: str,
    article: dict[str, Any],
    semantics: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    text = f"{article['title']} {article['description']}".lower()
    reasons = []

    relevance = relevance_score(market_question, text, semantics)
    article["relevance_score"] = relevance
    if relevance < 0.2:
        reasons.append("low_relevance")

    low_quality_hits = [term for term in LOW_QUALITY_TERMS if term in text]
    penalty = min(0.45, len(low_quality_hits) * 0.09)
    if low_quality_hits:
        reasons.append("low_quality_terms:" + ",".join(low_quality_hits[:3]))

    if len(article["title"]) < 12:
        penalty += 0.1
        reasons.append("title_too_short")

    score = (
        relevance * 0.45
        + article["source_quality"] * 0.3
        + article["age_score"] * 0.15
        + 0.1
        - penalty
    )
    return round(max(0.0, min(1.0, score)), 3), reasons


def relevance_score(
    market_question: str,
    news_text: str,
    semantics: dict[str, Any] | None = None,
) -> float:
    semantic_tokens = []
    if semantics:
        semantic_tokens = list(semantics.get("entities", []))
        semantic_tokens += extract_keywords(semantics.get("yes_condition", ""))
        semantic_tokens += extract_keywords(semantics.get("no_condition", ""))

    question_tokens = list(dict.fromkeys(
        extract_keywords(market_question) + semantic_tokens
    ))
    if not question_tokens:
        return 0.0

    hits = sum(1 for token in question_tokens if token in news_text)
    return max(0.0, min(1.0, hits / min(len(question_tokens), 6)))


def extract_keywords(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]{3,}", (text or "").lower())
    return [
        token
        for token in tokens
        if token not in STOPWORDS and not token.isdigit()
    ][:12]


def score_source_quality(source: str, title: str) -> float:
    haystack = f"{source} {title}".lower()
    if any(source_name in haystack for source_name in TRUSTED_SOURCES):
        return 0.9
    if source:
        return 0.55
    return 0.35


def score_age(published: str) -> float:
    if not published:
        return 0.5

    try:
        parsed = parsedate_to_datetime(published)
    except (TypeError, ValueError):
        return 0.5

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    age_hours = (datetime.now(timezone.utc) - parsed).total_seconds() / 3600
    if age_hours <= 24:
        return 1.0
    if age_hours <= 72:
        return 0.8
    if age_hours <= 168:
        return 0.6
    return 0.35


def dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []

    for article in articles:
        key = normalize_key(article["title"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)

    return unique


def build_evidence_profile(
    market_question: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    semantics = parse_market_semantics(market_question)
    evidence_items = [
        classify_evidence(market_question, article, semantics)
        for article in articles
    ]
    support = sum(item["weighted_score"] for item in evidence_items if item["direction"] == "support")
    oppose = sum(item["weighted_score"] for item in evidence_items if item["direction"] == "oppose")
    neutral = sum(item["weighted_score"] for item in evidence_items if item["direction"] == "neutral")
    total = support + oppose + neutral

    if total <= 0:
        direction = "neutral"
        strength = 0.0
        conflict = 0.0
    else:
        net = support - oppose
        strength = abs(net) / total
        conflict = min(support, oppose) / max(support, oppose, 0.001)
        if strength < 0.15:
            direction = "neutral"
        elif net > 0:
            direction = "support"
        else:
            direction = "oppose"

    sources = sorted({
        item["source"]
        for item in evidence_items
        if item["source"]
    })
    freshness = average_field(articles, "age_score")
    resolution_relevance = average_evidence_field(
        evidence_items,
        "resolution_relevance_score",
    )

    return {
        "evidence_direction": direction,
        "evidence_strength": round(strength, 3),
        "support_score": round(support, 3),
        "oppose_score": round(oppose, 3),
        "neutral_score": round(neutral, 3),
        "conflict_score": round(conflict, 3),
        "freshness_score": round(freshness, 3),
        "resolution_relevance_score": round(resolution_relevance, 3),
        "source_count": len(sources),
        "sources": sources[:10],
        "items": evidence_items[:10],
    }


def classify_evidence(
    market_question: str,
    article: dict[str, Any],
    semantics: dict[str, Any],
) -> dict[str, Any]:
    text = f"{article['title']} {article['description']}".lower()
    question = market_question.lower()
    direction = infer_direction(question, text)
    resolution_relevance = score_resolution_relevance(text, semantics)
    weighted_score = (
        article["quality_score"]
        * article["relevance_score"]
        * article["source_quality"]
        * max(0.35, resolution_relevance)
    )

    return {
        "title": article["title"],
        "source": article["source"],
        "direction": direction,
        "weighted_score": round(weighted_score, 3),
        "quality_score": article["quality_score"],
        "relevance_score": article["relevance_score"],
        "resolution_relevance_score": resolution_relevance,
    }


def infer_direction(question: str, text: str) -> str:
    positive_terms = (
        "wins", "win", "passes", "passed", "approved", "approval",
        "launches", "confirmed", "confirms", "raises", "rise", "rises",
        "surges", "leads", "ahead", "beats", "growth", "record high",
    )
    negative_terms = (
        "loses", "lose", "fails", "failed", "rejected", "denied",
        "cancelled", "canceled", "delay", "delayed", "falls", "fall",
        "drops", "behind", "misses", "lawsuit", "investigation",
    )

    yes_positive = not any(term in question for term in (" not ", " fail", " lose", " below"))
    positive_hits = sum(1 for term in positive_terms if term in text)
    negative_hits = sum(1 for term in negative_terms if term in text)

    if positive_hits == negative_hits:
        return "neutral"

    supports_yes = positive_hits > negative_hits
    if not yes_positive:
        supports_yes = not supports_yes

    return "support" if supports_yes else "oppose"


def score_resolution_relevance(
    text: str,
    semantics: dict[str, Any],
) -> float:
    score = 0.25
    entities = semantics.get("entities", [])
    threshold = semantics.get("threshold")
    deadline = semantics.get("deadline")
    condition_type = semantics.get("condition_type", "binary_event")

    if entities:
        entity_hits = sum(1 for entity in entities if entity in text)
        score += min(0.35, entity_hits * 0.12)
    if threshold and threshold.lower() in text:
        score += 0.25
    if deadline and deadline.lower() in text:
        score += 0.15
    if condition_type == "threshold" and any(
        term in text for term in ("hit", "reach", "above", "record", "high", "price")
    ):
        score += 0.15
    elif condition_type == "election" and any(
        term in text for term in ("poll", "vote", "election", "lead", "wins")
    ):
        score += 0.15
    elif condition_type == "announcement_or_approval" and any(
        term in text for term in ("approve", "approval", "announce", "launch", "release")
    ):
        score += 0.15

    return round(max(0.0, min(1.0, score)), 3)


def build_news_context(
    articles: list[dict[str, Any]],
    evidence_profile: dict[str, Any],
    semantics: dict[str, Any],
) -> str:
    semantics_header = build_semantics_context(semantics)
    evidence_header = (
        "EVIDENCE PROFILE\n"
        f"DIRECTION: {evidence_profile['evidence_direction']}\n"
        f"STRENGTH: {evidence_profile['evidence_strength']}\n"
        f"CONFLICT: {evidence_profile['conflict_score']}\n"
        f"FRESHNESS: {evidence_profile['freshness_score']}\n"
        f"RESOLUTION_RELEVANCE: {evidence_profile['resolution_relevance_score']}\n"
        f"SOURCE_COUNT: {evidence_profile['source_count']}"
    )
    news_items = "\n\n".join(
        "NEWS ITEM\n"
        f"SOURCE: {article['source']}\n"
        f"QUALITY: {article['quality_score']}\n"
        f"RELEVANCE: {article['relevance_score']}\n"
        f"TITLE: {article['title']}\n"
        f"DESCRIPTION: {article['description']}"
        for article in articles
    )
    return f"{semantics_header}\n\n{evidence_header}\n\n{news_items}".strip()


def average_quality(articles: list[dict[str, Any]]) -> float:
    return average_field(articles, "quality_score")


def average_field(articles: list[dict[str, Any]], field: str) -> float:
    if not articles:
        return 0.0
    return round(
        sum(article[field] for article in articles) / len(articles),
        3,
    )


def average_evidence_field(items: list[dict[str, Any]], field: str) -> float:
    if not items:
        return 0.0
    return round(
        sum(item[field] for item in items) / len(items),
        3,
    )


def normalize_key(text: str) -> str:
    return " ".join(extract_keywords(text)[:8])


def infer_source(title: str) -> str:
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return ""
