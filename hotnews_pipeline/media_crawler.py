from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


# Canonical platform names and all directory aliases used by MediaCrawler
# for JSONL (`store/*/_store_impl.py`) and Media (`media_platform/*/core.py`).
PLATFORM_ALIASES: dict[str, str] = {
    "dy": "douyin",
    "douyin": "douyin",
    "xhs": "xhs",
    "xiaohongshu": "xhs",
    "rednote": "xhs",
    "bili": "bilibili",
    "bilibili": "bilibili",
    "ks": "kuaishou",
    "kuaishou": "kuaishou",
    "wb": "weibo",
    "weibo": "weibo",
    "tieba": "tieba",
    "zhihu": "zhihu",
}

JSONL_DIR_CANDIDATES: dict[str, tuple[str, ...]] = {
    "douyin": ("douyin", "dy"),
    "xhs": ("xhs",),
    "bilibili": ("bili", "bilibili"),
    "kuaishou": ("kuaishou", "ks"),
    "weibo": ("weibo", "wb"),
    "tieba": ("tieba",),
    "zhihu": ("zhihu",),
}

MEDIA_DIR_CANDIDATES: dict[str, tuple[str, ...]] = {
    "douyin": ("dy", "douyin"),
    "xhs": ("xhs",),
    "bilibili": ("bili", "bilibili"),
    "kuaishou": ("ks", "kuaishou"),
    "weibo": ("wb", "weibo"),
    "tieba": ("tieba",),
    "zhihu": ("zhihu",),
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".flv", ".avi", ".m4v"}
_ILLEGAL_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_WINDOWS_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)
_DURATION_CACHE: dict[tuple[str, int, int], float] = {}


def _sanitize_component(value: str) -> str:
    """Match MediaCrawler's `media_downloader/paths.py:sanitize_component`."""
    raw = (value or "").strip()
    cleaned = _ILLEGAL_CHARS.sub("_", raw).lstrip(".").replace("..", "_")[:64]
    if not cleaned:
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    if cleaned.split(".")[0].upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def probe_video_duration(media_path: str | Path) -> float:
    """Probe local video duration in seconds via ffprobe (returns 0.0 if unavailable)."""
    if not media_path:
        return 0.0
    path = Path(media_path)
    try:
        if not path.is_file():
            return 0.0
        stat = path.stat()
        if stat.st_size <= 0:
            return 0.0
        cache_key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if cache_key in _DURATION_CACHE:
            return _DURATION_CACHE[cache_key]
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return 0.0
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            **kwargs,
        )
        if proc.returncode != 0:
            return 0.0
        duration = round(max(0.0, float(proc.stdout.strip() or 0.0)), 3)
        _DURATION_CACHE[cache_key] = duration
        return duration
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _video_priority(item: Path) -> tuple[int, float, int]:
    """Prioritize primary videos (`video.mp4`, `video-durl.mp4`) before live-photo clips (`*_live.mp4`)."""
    name = item.name.lower()
    if name == "video.mp4":
        tier = 3
    elif name.startswith("video"):
        tier = 2
    elif not name.endswith("_live.mp4"):
        tier = 1
    else:
        tier = 0
    try:
        stat = item.stat()
        return (tier, stat.st_mtime, stat.st_size)
    except OSError:
        return (tier, 0.0, 0)


def _find_video_file(data_root: Path, canonical_platform: str, identity: str) -> str:
    if not identity:
        return ""
    safe_id = _sanitize_component(identity)
    id_candidates = tuple(dict.fromkeys((safe_id, identity)))
    media_dirs = MEDIA_DIR_CANDIDATES.get(canonical_platform, (canonical_platform,))

    search_folders: list[Path] = []
    for platform_dir in media_dirs:
        for cid in id_candidates:
            # New MediaCrawler unified media directory (`0ca7b29`+): data/{platform}/media/{content_id}/
            search_folders.append(data_root / platform_dir / "media" / cid)
            # Legacy MediaCrawler directory: data/{platform}/videos/{content_id}/
            search_folders.append(data_root / platform_dir / "videos" / cid)

    for folder in search_folders:
        if not folder.exists():
            continue
        files = sorted(
            (
                item
                for item in folder.rglob("*")
                if item.is_file()
                and item.suffix.lower() in VIDEO_EXTENSIONS
                and not item.name.endswith(".part")
            ),
            key=_video_priority,
            reverse=True,
        )
        if files:
            return str(files[0].resolve())
    return ""


def _fallback_source_url(canonical_platform: str, identity: str) -> str:
    if not identity:
        return ""
    if canonical_platform == "douyin":
        return f"https://www.douyin.com/video/{identity}"
    if canonical_platform == "bilibili":
        prefix = "" if identity.lower().startswith(("bv", "av")) else "av"
        return f"https://www.bilibili.com/video/{prefix}{identity}"
    if canonical_platform == "kuaishou":
        return f"https://www.kuaishou.com/short-video/{identity}"
    if canonical_platform == "xhs":
        return f"https://www.xiaohongshu.com/explore/{identity}"
    if canonical_platform == "weibo":
        return f"https://m.weibo.cn/detail/{identity}"
    return ""


def _normalize_row(
    row: dict[str, Any],
    canonical_platform: str,
    data_root: Path,
    probe_duration: bool = True,
) -> dict[str, Any]:
    identity = str(_first(row, "aweme_id", "note_id", "bvid", "video_id", "content_id", "id"))
    direct_path = str(_first(row, "media_path", "local_path", "video_path", "file_path"))
    media_path = (
        str(Path(direct_path).resolve())
        if direct_path
        else _find_video_file(data_root, canonical_platform, identity)
    )
    source_url = str(_first(row, "aweme_url", "note_url", "video_url", "content_url", "source_url", "url"))
    if not source_url and identity:
        source_url = _fallback_source_url(canonical_platform, identity)

    raw_duration = _first(row, "duration_sec", "duration", "video_duration")
    duration_sec: Any = raw_duration
    if probe_duration and (not raw_duration or str(raw_duration).strip() in {"0", "0.0"}) and media_path:
        probed = probe_video_duration(media_path)
        if probed > 0:
            duration_sec = probed

    return {
        "candidate_id": identity,
        "platform": canonical_platform,
        "source_url": source_url,
        "media_path": media_path,
        "title": str(_first(row, "title", "desc", "description", "content")),
        "description": str(_first(row, "desc", "description", "content")),
        "author": str(_first(row, "nickname", "user_nickname", "author", "author_name")),
        "published_at": _first(
            row,
            "create_time",
            "time",
            "published_at",
            "pubdate",
            "publish_time",
            "create_date_time",
        ),
        "likes": _first(row, "liked_count", "like_count", "likes", "attitudes_count"),
        "comments": _first(row, "comment_count", "comments_count", "video_comment", "comments", "reply_count"),
        "shares": _first(row, "share_count", "shared_count", "video_share_count", "shares", "reposts_count"),
        "collects": _first(row, "collected_count", "video_favorite_count", "favorite_count", "collects"),
        "views": _first(row, "video_play_count", "viewd_count", "view_count", "views"),
        "duration_sec": duration_sec,
        "thumbnail_url": str(_first(row, "cover_url", "video_cover_url", "thumbnail_url", "cover")),
        "source_keyword": str(_first(row, "source_keyword", "keyword")),
        "tag_list": _first(row, "tag_list", "tags"),
        "raw": row,
    }


def find_contents_files(root: Path, platform: str, all_files: bool = False) -> list[Path]:
    canonical = PLATFORM_ALIASES.get(platform.lower(), platform.lower())
    data_root = root / "data" if (root / "data").exists() else root
    jsonl_dirs = JSONL_DIR_CANDIDATES.get(canonical, (canonical,))
    files: list[Path] = []
    for folder_name in jsonl_dirs:
        jsonl_dir = data_root / folder_name / "jsonl"
        if jsonl_dir.exists():
            files.extend(jsonl_dir.glob("*_contents_*.jsonl"))
    files = sorted(set(files), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        checked = ", ".join(str(data_root / d / "jsonl") for d in jsonl_dirs)
        raise FileNotFoundError(f"Không tìm thấy JSONL contents cho '{platform}' trong: {checked}")
    return files if all_files else [files[0]]


def find_latest_contents(root: Path, platform: str) -> Path:
    return find_contents_files(root, platform, all_files=False)[0]


def normalize(
    root: Path,
    platform: str,
    output: Path,
    source: Path | None = None,
    *,
    all_files: bool = False,
    probe_duration: bool = True,
) -> int:
    data_root = root / "data" if (root / "data").exists() else root
    if platform.lower() == "all" and source is None:
        platforms = tuple(JSONL_DIR_CANDIDATES.keys())
        rows: list[dict[str, Any]] = []
        for plat in platforms:
            try:
                source_files = find_contents_files(root, plat, all_files=all_files)
            except FileNotFoundError:
                continue
            for src_file in source_files:
                with src_file.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        if line.strip():
                            rows.append(_normalize_row(json.loads(line), plat, data_root, probe_duration=probe_duration))
        if not rows:
            raise FileNotFoundError(f"Không tìm thấy bất kỳ file JSONL contents nào trong {data_root}")
    else:
        canonical = PLATFORM_ALIASES.get(platform.lower(), platform.lower())
        source_files = [source] if source else find_contents_files(root, platform, all_files=all_files)
        rows = []
        for src_file in source_files:
            with src_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        rows.append(_normalize_row(json.loads(line), canonical, data_root, probe_duration=probe_duration))

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)
