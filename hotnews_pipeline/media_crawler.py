from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PLATFORM_DIRS = {
    "dy": "douyin",
    "douyin": "douyin",
    "xhs": "xhs",
    "bili": "bilibili",
    "bilibili": "bilibili",
    "ks": "kuaishou",
    "kuaishou": "kuaishou",
    "wb": "weibo",
    "weibo": "weibo",
    "tieba": "tieba",
    "zhihu": "zhihu",
}


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _video_path(video_root: Path, identity: str) -> str:
    if not identity:
        return ""
    folder = video_root / identity
    if not folder.exists():
        return ""
    extensions = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    files = sorted((item for item in folder.rglob("*") if item.is_file() and item.suffix.lower() in extensions), key=lambda item: item.stat().st_mtime, reverse=True)
    return str(files[0].resolve()) if files else ""


def _normalize_row(row: dict[str, Any], platform: str, video_root: Path) -> dict[str, Any]:
    identity = str(_first(row, "aweme_id", "note_id", "bvid", "video_id", "id"))
    direct_path = str(_first(row, "media_path", "local_path", "video_path", "file_path"))
    media_path = str(Path(direct_path).resolve()) if direct_path else _video_path(video_root, identity)
    source_url = str(_first(row, "aweme_url", "note_url", "source_url", "url"))
    if not source_url and platform == "bilibili" and identity:
        source_url = f"https://www.bilibili.com/video/{identity}"
    return {
        "candidate_id": identity,
        "platform": platform,
        "source_url": source_url,
        "media_path": media_path,
        "title": str(_first(row, "title", "desc", "description")),
        "description": str(_first(row, "desc", "description", "content")),
        "author": str(_first(row, "nickname", "author", "author_name")),
        "published_at": _first(row, "create_time", "time", "published_at", "pubdate"),
        "likes": _first(row, "liked_count", "like_count", "likes"),
        "comments": _first(row, "comment_count", "comments"),
        "shares": _first(row, "share_count", "shares", "video_share_count"),
        "duration_sec": _first(row, "duration_sec", "duration", "video_duration"),
        "thumbnail_url": str(_first(row, "cover_url", "thumbnail_url", "cover")),
        "raw": row,
    }


def find_latest_contents(root: Path, platform: str) -> Path:
    platform_dir = PLATFORM_DIRS.get(platform.lower(), platform.lower())
    files = sorted((root / "data" / platform_dir / "jsonl").glob("*_contents_*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"Không tìm thấy JSONL contents trong {root / 'data' / platform_dir / 'jsonl'}")
    return files[0]


def normalize(root: Path, platform: str, output: Path, source: Path | None = None) -> int:
    platform_dir = PLATFORM_DIRS.get(platform.lower(), platform.lower())
    source_path = source or find_latest_contents(root, platform)
    video_root = root / "data" / platform_dir / "videos"
    rows = []
    with source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(_normalize_row(json.loads(line), platform_dir, video_root))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)
