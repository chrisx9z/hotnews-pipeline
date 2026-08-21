import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hotnews_pipeline.models import Candidate
from hotnews_pipeline.pipeline import dedupe, ingest
from hotnews_pipeline.ranking import score


def test_dedupe_by_url():
    first = Candidate.from_mapping({"platform": "xhs", "source_url": "https://x/1", "title": "a"})
    second = Candidate.from_mapping({"platform": "xhs", "source_url": "https://x/1", "title": "b"})
    assert len(dedupe([first, second])) == 1


def test_recent_video_scores_higher():
    now = datetime.now(timezone.utc)
    recent = Candidate.from_mapping({"source_url": "https://x/1", "title": "a", "published_at": now.isoformat(), "duration_sec": 60, "likes": 1000})
    old = Candidate.from_mapping({"source_url": "https://x/2", "title": "b", "published_at": (now - timedelta(days=7)).isoformat(), "duration_sec": 60, "likes": 1000})
    assert score(recent, now) > score(old, now)


def test_ingest_filters_long_videos(tmp_path: Path):
    source = tmp_path / "input.jsonl"
    target = tmp_path / "ranked.jsonl"
    source.write_text("\n".join([
        json.dumps({"source_url": "https://x/1", "title": "short", "duration_sec": 60}),
        json.dumps({"source_url": "https://x/2", "title": "long", "duration_sec": 1801}),
    ]), encoding="utf-8")
    result = ingest(source, target, 1800)
    assert len(result) == 1
    assert target.exists()
