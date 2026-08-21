from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping


def _first(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return 0.0
    text = str(value).replace(",", "").strip().lower()
    multipliers = {"k": 1_000, "m": 1_000_000, "万": 10_000, "亿": 100_000_000}
    multiplier = 1
    if text[-1:] in multipliers:
        multiplier = multipliers[text[-1]]
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return 0.0


def _datetime(value: Any) -> str:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    if value:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Candidate:
    candidate_id: str
    platform: str
    source_url: str
    media_path: str
    title: str = ""
    description: str = ""
    author: str = ""
    published_at: str = ""
    likes: float = 0.0
    comments: float = 0.0
    shares: float = 0.0
    duration_sec: float = 0.0
    thumbnail_url: str = ""
    hot_score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Candidate":
        platform = str(_first(data, "platform", "source", default="unknown"))
        source_url = str(_first(data, "source_url", "url", "video_url", "note_url", default=""))
        title = str(_first(data, "title", "desc", "description", "content", default=""))
        author = str(_first(data, "author", "author_name", "nickname", "user_nickname", default=""))
        identity = str(_first(data, "candidate_id", "id", "aweme_id", "note_id", "video_id", default=""))
        if not identity:
            identity = sha256(f"{platform}|{source_url}|{author}|{title}".encode()).hexdigest()[:20]
        return cls(
            candidate_id=identity,
            platform=platform,
            source_url=source_url,
            media_path=str(_first(data, "media_path", "local_path", "video_path", "file_path", default="")),
            title=title,
            description=str(_first(data, "description", "desc", "content", default="")),
            author=author,
            published_at=_datetime(_first(data, "published_at", "publish_time", "create_time", "created_at")),
            likes=_number(_first(data, "likes", "liked_count", "liked", "like_count")),
            comments=_number(_first(data, "comments", "comment_count", "comments_count")),
            shares=_number(_first(data, "shares", "share_count", "shared_count")),
            duration_sec=_number(_first(data, "duration_sec", "duration", "video_duration")),
            thumbnail_url=str(_first(data, "thumbnail_url", "cover_url", "cover", default="")),
            hot_score=_number(data.get("hot_score")),
            raw=dict(data),
        )

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)
