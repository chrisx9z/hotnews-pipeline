import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hotnews_pipeline.catalog import write_catalog
from hotnews_pipeline.media_crawler import _find_video_file, normalize
from hotnews_pipeline.models import Candidate
from hotnews_pipeline.pipeline import dedupe, ingest, print_jobs_status
from hotnews_pipeline.ranking import score


def test_dedupe_by_url_and_cross_platform_title():
    first = Candidate.from_mapping({"platform": "xhs", "source_url": "https://x/1", "title": "a"})
    second = Candidate.from_mapping({"platform": "xhs", "source_url": "https://x/1", "title": "b"})
    assert len(dedupe([first, second])) == 1

    repost_dy = Candidate.from_mapping(
        {"platform": "dy", "source_url": "https://douyin.com/video/1", "title": "AI大模型最新突破引发全网热议 #人工智能"}
    )
    repost_xhs = Candidate.from_mapping(
        {"platform": "xhs", "source_url": "https://xiaohongshu.com/explore/2", "title": "AI大模型最新突破引发全网热议!"}
    )
    assert len(dedupe([repost_dy, repost_xhs])) == 1


def test_candidate_from_mapping_avoids_recursive_raw_and_parses_cn_units():
    first = Candidate.from_mapping(
        {
            "platform": "dy",
            "aweme_id": "7627770304823610665",
            "title": "大模型智能体爆发 #AI #科技",
            "liked_count": "1.2万",
            "collected_count": "3500",
            "comment_count": "800+",
            "share_count": "1.5k",
            "video_play_count": "25w",
            "source_keyword": "人工智能",
            "tag_list": "大模型,Agent",
            "create_time": "1755200000",
        }
    )
    assert first.likes == 12000
    assert first.collects == 3500
    assert first.comments == 800
    assert first.shares == 1500
    assert first.views == 250000
    assert first.source_keyword == "人工智能"
    assert "AI" in first.tags
    assert "大模型" in first.tags

    roundtrip = Candidate.from_mapping(first.as_mapping())
    assert "raw" not in roundtrip.raw
    assert roundtrip.likes == 12000
    assert roundtrip.collects == 3500


def test_recent_video_scores_higher_and_keywords_boost():
    now = datetime.now(timezone.utc)
    recent = Candidate.from_mapping(
        {"source_url": "https://x/1", "title": "AI智能体新闻", "published_at": now.isoformat(), "duration_sec": 60, "likes": 1000}
    )
    old = Candidate.from_mapping(
        {
            "source_url": "https://x/2",
            "title": "普通视频",
            "published_at": (now - timedelta(days=7)).isoformat(),
            "duration_sec": 60,
            "likes": 1000,
        }
    )
    assert score(recent, now) > score(old, now)
    assert score(recent, now, keywords=["AI", "智能体"]) > score(recent, now)


def test_ingest_filters_duration_and_excludes_existing_jobs(tmp_path: Path):
    source = tmp_path / "input.jsonl"
    target = tmp_path / "ranked.jsonl"
    jobs_dir = tmp_path / "jobs"
    completed_job = jobs_dir / "001_done"
    completed_job.mkdir(parents=True)
    done_candidate = Candidate.from_mapping({"source_url": "https://x/done", "title": "already done", "duration_sec": 45})
    (completed_job / "manifest.json").write_text(
        json.dumps(
            {
                "job_id": "001_done",
                "stages": {"render": "completed"},
                "candidate": done_candidate.as_mapping(),
            }
        ),
        encoding="utf-8",
    )

    source.write_text(
        "\n".join(
            [
                json.dumps({"source_url": "https://x/1", "title": "short", "duration_sec": 60}),
                json.dumps({"source_url": "https://x/2", "title": "long", "duration_sec": 1801}),
                json.dumps({"source_url": "https://x/done", "title": "already done", "duration_sec": 45}),
            ]
        ),
        encoding="utf-8",
    )
    result = ingest(source, target, 1800, exclude_jobs_dir=jobs_dir)
    assert len(result) == 1
    assert result[0].source_url == "https://x/1"
    assert target.exists()


def test_media_crawler_normalize_unified_media_and_legacy_layout(tmp_path: Path):
    crawler_root = tmp_path / "MediaCrawler"
    dy_jsonl_dir = crawler_root / "data" / "douyin" / "jsonl"
    dy_jsonl_dir.mkdir(parents=True)

    # New upstream MediaCrawler unified layout: data/dy/media/{id}/video.mp4
    new_media_dir = crawler_root / "data" / "dy" / "media" / "111"
    new_media_dir.mkdir(parents=True)
    new_video = new_media_dir / "video.mp4"
    new_video.write_bytes(b"fake-mp4-1")

    # Legacy MediaCrawler layout: data/douyin/videos/{id}/video.mp4
    legacy_media_dir = crawler_root / "data" / "douyin" / "videos" / "222"
    legacy_media_dir.mkdir(parents=True)
    legacy_video = legacy_media_dir / "video.mp4"
    legacy_video.write_bytes(b"fake-mp4-2")

    jsonl_path = dy_jsonl_dir / "search_contents_2026-11-09.jsonl"
    jsonl_path.write_text(
        "\n".join(
            [
                json.dumps({"aweme_id": "111", "title": "New layout video", "liked_count": "5000", "create_time": 1755200000}),
                json.dumps({"aweme_id": "222", "title": "Legacy layout video", "liked_count": "2000", "create_time": 1755200100}),
            ]
        ),
        encoding="utf-8",
    )

    assert _find_video_file(crawler_root / "data", "douyin", "111") == str(new_video.resolve())
    assert _find_video_file(crawler_root / "data", "douyin", "222") == str(legacy_video.resolve())

    output_jsonl = tmp_path / "normalized.jsonl"
    count = normalize(crawler_root, "dy", output_jsonl, probe_duration=False)
    assert count == 2
    rows = [json.loads(line) for line in output_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["media_path"] == str(new_video.resolve())
    assert rows[1]["media_path"] == str(legacy_video.resolve())


def test_catalog_and_job_summary(tmp_path: Path):
    catalog_html = tmp_path / "catalog.html"
    candidate = Candidate.from_mapping(
        {
            "platform": "dy",
            "source_url": "https://www.douyin.com/video/123",
            "media_path": "D:/fake/video.mp4",
            "title": "测试热点视频",
            "author": "作者A",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "likes": 8800,
            "collects": 1200,
            "comments": 300,
            "shares": 450,
            "duration_sec": 75,
            "hot_score": 18.5,
            "tags": ["热点", "AI"],
        }
    )
    out_path = write_catalog([candidate], catalog_html, limit=10)
    assert out_path == catalog_html
    html_text = catalog_html.read_text(encoding="utf-8")
    assert "Hot News China Catalog" in html_text
    assert "Copy lệnh chạy Localizer" in html_text

    jobs_dir = tmp_path / "jobs"
    job_a = jobs_dir / "001_a"
    job_a.mkdir(parents=True)
    (job_a / "manifest.json").write_text(
        json.dumps(
            {
                "job_id": "001_a",
                "stages": {"whisper": "completed", "vietsub_tts": "completed", "render": "completed"},
                "candidate": {"platform": "dy", "title": "测试热点视频", "hot_score": 18.5},
                "artifacts": {"rendered_video": "D:/out.mp4"},
            }
        ),
        encoding="utf-8",
    )
    summaries = print_jobs_status(jobs_dir)
    assert len(summaries) == 1
    assert summaries[0]["render"] == "completed"
