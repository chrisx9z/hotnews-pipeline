from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping


_HASHTAG_RE = re.compile(r"#([^#\s]{1,40})")


def _first(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not value:
        return 0.0
    text = str(value).replace(",", "").strip().lower().rstrip("+")
    multipliers = {
        "k": 1_000,
        "w": 10_000,
        "m": 1_000_000,
        "千": 1_000,
        "万": 10_000,
        "亿": 100_000_000,
    }
    multiplier = 1.0
    if text[-1:] in multipliers:
        multiplier = float(multipliers[text[-1]])
        text = text[:-1].strip()
    try:
        return float(text) * multiplier
    except ValueError:
        return 0.0


def _datetime(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value)
        if timestamp <= 0:
            return datetime.now(timezone.utc).isoformat()
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    if value:
        text = str(value).strip()
        if text.isdigit():
            return _datetime(int(text))
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def _extract_tags(data: Mapping[str, Any], title: str, description: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()

    def _add(tag_value: str) -> None:
        cleaned = tag_value.strip().lstrip("#").strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            tags.append(cleaned)

    raw_tags = _first(data, "tags", "tag_list", default=None)
    if isinstance(raw_tags, list):
        for item in raw_tags:
            if isinstance(item, Mapping):
                _add(str(item.get("name", "")))
            elif item:
                _add(str(item))
    elif isinstance(raw_tags, str):
        for part in raw_tags.split(","):
            _add(part)

    for text in (title, description):
        for match in _HASHTAG_RE.finditer(text or ""):
            _add(match.group(1))
    return tags


def _infer_content_type(data: Mapping[str, Any], media_path: str) -> str:
    explicit = str(_first(data, "content_type", default="")).strip().lower()
    if explicit in {"video", "live_photo", "image", "note"}:
        return explicit
    if media_path and media_path.lower().endswith("_live.mp4"):
        return "live_photo"
    aweme_type = str(_first(data, "aweme_type", default="")).strip()
    if aweme_type == "68":
        return "live_photo" if media_path.lower().endswith(".mp4") else "image"
    note_type = str(_first(data, "type", "video_type", default="")).strip().lower()
    if note_type in {"video", "normal", "image"}:
        if note_type == "normal":
            return "live_photo" if media_path.lower().endswith(".mp4") else "image"
        return note_type
    return "video"


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
    collects: float = 0.0
    views: float = 0.0
    duration_sec: float = 0.0
    thumbnail_url: str = ""
    source_keyword: str = ""
    content_type: str = "video"
    tags: list[str] = field(default_factory=list)
    hot_score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Candidate":
        platform = str(_first(data, "platform", "source", default="unknown"))
        source_url = str(
            _first(data, "source_url", "url", "aweme_url", "video_url", "note_url", "content_url", default="")
        )
        title = str(_first(data, "title", "desc", "description", "content", default=""))
        description = str(_first(data, "description", "desc", "content", default=""))
        author = str(_first(data, "author", "author_name", "nickname", "user_nickname", default=""))
        identity = str(
            _first(data, "candidate_id", "id", "aweme_id", "note_id", "bvid", "video_id", "content_id", default="")
        )
        if not identity:
            identity = sha256(f"{platform}|{source_url}|{author}|{title}".encode()).hexdigest()[:20]
        media_path = str(_first(data, "media_path", "local_path", "video_path", "file_path", default=""))
        raw_payload = data.get("raw")
        raw_dict = dict(raw_payload) if isinstance(raw_payload, Mapping) else dict(data)
        return cls(
            candidate_id=identity,
            platform=platform,
            source_url=source_url,
            media_path=media_path,
            title=title,
            description=description,
            author=author,
            published_at=_datetime(
                _first(data, "published_at", "publish_time", "create_time", "time", "pubdate", "create_date_time", "created_at")
            ),
            likes=_number(_first(data, "likes", "liked_count", "liked", "like_count", "attitudes_count")),
            comments=_number(_first(data, "comments", "comment_count", "comments_count", "video_comment", "reply_count")),
            shares=_number(_first(data, "shares", "share_count", "shared_count", "video_share_count", "reposts_count")),
            collects=_number(_first(data, "collects", "collected_count", "video_favorite_count", "favorite_count")),
            views=_number(_first(data, "views", "video_play_count", "viewd_count", "view_count", "play_count")),
            duration_sec=_number(_first(data, "duration_sec", "duration", "video_duration")),
            thumbnail_url=str(_first(data, "thumbnail_url", "cover_url", "video_cover_url", "cover", default="")),
            source_keyword=str(_first(data, "source_keyword", "keyword", default="")),
            content_type=_infer_content_type(data, media_path),
            tags=_extract_tags(data, title, description),
            hot_score=_number(data.get("hot_score")),
            raw=raw_dict,
        )

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)
