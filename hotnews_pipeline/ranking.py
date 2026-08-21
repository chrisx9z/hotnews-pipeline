from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable

from .models import Candidate


def _age_hours(published_at: str, now: datetime) -> float:
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return max(0.0, (now - published.astimezone(timezone.utc)).total_seconds() / 3600)
    except ValueError:
        return 168.0


def score(candidate: Candidate, now: datetime | None = None) -> float:
    current = now or datetime.now(timezone.utc)
    age = _age_hours(candidate.published_at, current)
    engagement = math.log1p(candidate.likes + 2 * candidate.comments + 3 * candidate.shares)
    velocity = engagement / math.sqrt(age + 1)
    recency = math.exp(-age / 48)
    duration = candidate.duration_sec
    duration_fit = 1.0 if 15 <= duration <= 600 else 0.7 if 0 < duration <= 1800 else 0.2
    metadata = 1.0 if candidate.source_url and candidate.title else 0.5
    return round(100 * (0.42 * recency + 0.36 * min(1, velocity / 8) + 0.14 * duration_fit + 0.08 * metadata), 3)


def rank(candidates: Iterable[Candidate], now: datetime | None = None) -> list[Candidate]:
    ranked = []
    for candidate in candidates:
        candidate.hot_score = score(candidate, now)
        ranked.append(candidate)
    return sorted(ranked, key=lambda item: item.hot_score, reverse=True)
