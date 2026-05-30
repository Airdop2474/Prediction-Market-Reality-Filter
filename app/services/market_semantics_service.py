import re
from typing import Any


AMBIGUITY_TERMS = (
    "major", "significant", "substantial", "widely", "mainstream",
    "announce", "confirmed", "official", "recognized", "involved",
)

TIME_PATTERNS = (
    r"\bby ([a-z]+ \d{1,2},? \d{4})\b",
    r"\bbefore ([a-z]+ \d{1,2},? \d{4})\b",
    r"\bby end of (\d{4})\b",
    r"\bin (\d{4})\b",
    r"\bbefore end of (\d{4})\b",
)

STOPWORDS = {
    "will", "this", "that", "with", "from", "about", "market",
    "polymarket", "before", "after", "above", "below", "between",
    "yes", "no", "the", "and", "or", "for", "to", "of", "in", "on",
    "by", "end", "hit", "reach", "happen", "occur", "there", "their",
}


def parse_market_semantics(market_question: str) -> dict[str, Any]:
    question = normalize_question(market_question)
    keywords = extract_entities(question)
    deadline = extract_deadline(question)
    threshold = extract_threshold(question)
    condition_type = infer_condition_type(question)
    yes_condition = build_yes_condition(question, condition_type, deadline, threshold)
    no_condition = build_no_condition(question, condition_type, deadline, threshold)
    ambiguity_score, ambiguity_flags = score_resolution_ambiguity(question)

    return {
        "question": question,
        "condition_type": condition_type,
        "yes_condition": yes_condition,
        "no_condition": no_condition,
        "deadline": deadline,
        "threshold": threshold,
        "entities": keywords[:10],
        "ambiguity_score": ambiguity_score,
        "ambiguity_flags": ambiguity_flags,
    }


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip())


def infer_condition_type(question: str) -> str:
    q = question.lower()
    if any(term in q for term in ("above", "over", "at least", "hit", "reach")):
        return "threshold"
    if any(term in q for term in ("win", "wins", "elected", "nominee")):
        return "election"
    if any(term in q for term in ("launch", "release", "announce", "approve", "approval")):
        return "announcement_or_approval"
    if any(term in q for term in ("war", "ceasefire", "tariff", "rate cut", "rate hike")):
        return "policy_or_geopolitical"
    return "binary_event"


def build_yes_condition(
    question: str,
    condition_type: str,
    deadline: str | None,
    threshold: str | None,
) -> str:
    suffix = f" by {deadline}" if deadline else " within the market resolution window"
    if condition_type == "threshold":
        target = f" {threshold}" if threshold else " the market threshold"
        return f"The referenced metric reaches or exceeds{target}{suffix}."
    if condition_type == "election":
        return f"The referenced candidate or side wins the specified election or nomination{suffix}."
    if condition_type == "announcement_or_approval":
        return f"The referenced official launch, release, announcement, or approval occurs{suffix}."
    if condition_type == "policy_or_geopolitical":
        return f"The specified policy or geopolitical event occurs according to resolution rules{suffix}."
    return f"The event described by the market question occurs{suffix}."


def build_no_condition(
    question: str,
    condition_type: str,
    deadline: str | None,
    threshold: str | None,
) -> str:
    suffix = f" by {deadline}" if deadline else " within the market resolution window"
    if condition_type == "threshold":
        target = f" {threshold}" if threshold else " the market threshold"
        return f"The referenced metric does not reach{target}{suffix}."
    if condition_type == "election":
        return f"The referenced candidate or side does not win the specified race{suffix}."
    if condition_type == "announcement_or_approval":
        return f"The referenced official launch, release, announcement, or approval does not occur{suffix}."
    if condition_type == "policy_or_geopolitical":
        return f"The specified policy or geopolitical event does not occur under resolution rules{suffix}."
    return f"The event described by the market question does not occur{suffix}."


def extract_deadline(question: str) -> str | None:
    q = question.lower()
    for pattern in TIME_PATTERNS:
        match = re.search(pattern, q)
        if not match:
            continue
        raw = match.group(1)
        if raw.isdigit():
            return f"end of {raw}"
        return raw
    return None


def extract_threshold(question: str) -> str | None:
    patterns = (
        r"(\d+(?:\.\d+)?%)",
        r"(\$?\d+(?:\.\d+)?\s?(?:k|m|b|million|billion|trillion)?)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, question.lower())
        for match in matches:
            if match.isdigit() and len(match) == 4:
                continue
            return match.replace(" ", "")
    return None


def extract_entities(question: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9$]{3,}", question.lower())
    return [
        token
        for token in tokens
        if token not in STOPWORDS and not token.isdigit()
    ]


def score_resolution_ambiguity(question: str) -> tuple[int, list[str]]:
    q = question.lower()
    flags = []

    if not extract_deadline(q):
        flags.append("missing_explicit_deadline")
    for term in AMBIGUITY_TERMS:
        if term in q:
            flags.append(f"ambiguous_term:{term}")

    if len(extract_entities(q)) < 2:
        flags.append("few_identifiable_entities")

    score = min(100, len(flags) * 20)
    return score, flags


def build_semantics_context(semantics: dict[str, Any]) -> str:
    return (
        "MARKET SEMANTICS\n"
        f"CONDITION_TYPE: {semantics['condition_type']}\n"
        f"YES_CONDITION: {semantics['yes_condition']}\n"
        f"NO_CONDITION: {semantics['no_condition']}\n"
        f"DEADLINE: {semantics['deadline'] or 'unknown'}\n"
        f"THRESHOLD: {semantics['threshold'] or 'unknown'}\n"
        f"ENTITIES: {', '.join(semantics['entities'])}\n"
        f"AMBIGUITY_SCORE: {semantics['ambiguity_score']}\n"
        f"AMBIGUITY_FLAGS: {', '.join(semantics['ambiguity_flags'])}"
    )
