from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable, Sequence

from .models import Candidate


DEFAULT_HOT_KEYWORDS: tuple[str, ...] = (
    "热点",
    "新闻",
    "突发",
    "快讯",
    "通报",
    "热搜",
    "最新",
    "曝光",
    "现场",
)


def _age_hours(published_at: str, now: datetime) -> float:
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return max(0.0, (now - published.astimezone(timezone.utc)).total_seconds() / 3600)
    except ValueError:
        return 168.0


def _duration_fit(duration_sec: float) -> float:
    if 15 <= duration_sec <= 600:
        return 1.0
    if 600 < duration_sec <= 1800:
        return 0.7
    if 5 <= duration_sec < 15:
        return 0.5
    if duration_sec == 0:
        return 0.6
    return 0.2


def _keyword_relevance(candidate: Candidate, keywords: Sequence[str] | None = None) -> float:
    haystack = " ".join(
        part
        for part in (
            candidate.title,
            candidate.description,
            candidate.source_keyword,
            " ".join(candidate.tags),
        )
        if part
    ).lower()
    if not haystack:
        return 0.4
    active_keywords = [kw.strip().lower() for kw in (keywords or DEFAULT_HOT_KEYWORDS) if kw.strip()]
    if not active_keywords:
        return 0.7
    matches = sum(1 for kw in active_keywords if kw in haystack)
    if matches >= 2:
        return 1.0
    if matches == 1 or candidate.source_keyword:
        return 0.85
    return 0.6


def score(
    candidate: Candidate,
    now: datetime | None = None,
    keywords: Sequence[str] | None = None,
) -> float:
    current = now or datetime.now(timezone.utc)
    age = _age_hours(candidate.published_at, current)
    weighted_interactions = (
        candidate.likes
        + 1.5 * candidate.collects
        + 2.0 * candidate.comments
        + 3.0 * candidate.shares
        + 0.05 * candidate.views
    )
    engagement = math.log1p(max(0.0, weighted_interactions))
    velocity = engagement / math.sqrt(age + 1.0)
    recency = math.exp(-age / 48.0)
    duration_fit = _duration_fit(candidate.duration_sec)
    metadata_quality = (
        0.7 * (1.0 if candidate.source_url and candidate.title else 0.5)
        + 0.3 * _keyword_relevance(candidate, keywords)
    )
    total = 100.0 * (
        0.42 * recency
        + 0.36 * min(1.0, velocity / 8.0)
        + 0.14 * duration_fit
        + 0.08 * metadata_quality
    )
    return round(min(100.0, max(0.0, total)), 3)


def rank(
    candidates: Iterable[Candidate],
    now: datetime | None = None,
    keywords: Sequence[str] | None = None,
) -> list[Candidate]:
    ranked = []
    for candidate in candidates:
        candidate.hot_score = score(candidate, now, keywords=keywords)
        ranked.append(candidate)
    return sorted(ranked, key=lambda item: item.hot_score, reverse=True)
