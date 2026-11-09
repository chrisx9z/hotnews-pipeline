from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from .catalog import write_catalog
from .media_crawler import normalize as normalize_media_crawler, probe_video_duration
from .models import Candidate
from .ranking import rank


_HASHTAG_CLEAN_RE = re.compile(r"#([^#\s]+)")
_NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fff]+")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy input: {path}. Hãy xuất dữ liệu MediaCrawler thành JSONL hoặc dùng examples/crawler.example.jsonl."
        )
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _title_fingerprint(title: str) -> str:
    without_tags = _HASHTAG_CLEAN_RE.sub("", title or "")
    cleaned = _NON_WORD_RE.sub("", without_tags).lower()
    return cleaned if len(cleaned) >= 12 else ""


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen_urls: set[str] = set()
    seen_media: set[str] = set()
    seen_titles: set[str] = set()
    output: list[Candidate] = []
    for candidate in candidates:
        url_key = candidate.source_url.strip().lower()
        if not url_key:
            url_key = sha256(f"{candidate.platform}|{candidate.title}|{candidate.author}".encode()).hexdigest()
        if url_key in seen_urls:
            continue

        media_key = ""
        if candidate.media_path:
            try:
                media_key = str(Path(candidate.media_path).resolve()).lower()
            except OSError:
                media_key = candidate.media_path.strip().lower()
        if media_key and media_key in seen_media:
            continue

        title_key = _title_fingerprint(candidate.title)
        if title_key and title_key in seen_titles:
            continue

        seen_urls.add(url_key)
        if media_key:
            seen_media.add(media_key)
        if title_key:
            seen_titles.add(title_key)
        output.append(candidate)
    return output


def _completed_candidate_ids(jobs_dir: Path | None) -> set[str]:
    if not jobs_dir or not jobs_dir.exists():
        return set()
    completed: set[str] = set()
    for manifest_path in jobs_dir.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stages = manifest.get("stages", {})
        if stages.get("render") == "completed" or stages.get("publish") == "completed":
            cid = str(manifest.get("candidate", {}).get("candidate_id", "")).strip()
            if cid:
                completed.add(cid)
    return completed


def ingest(
    input_path: Path,
    output_path: Path,
    max_duration: float = 1800,
    *,
    min_duration: float = 0.0,
    require_media: bool = False,
    keywords: Sequence[str] | None = None,
    exclude_jobs_dir: Path | None = None,
) -> list[Candidate]:
    candidates = [Candidate.from_mapping(row) for row in read_jsonl(input_path)]
    for item in candidates:
        if item.duration_sec <= 0 and item.media_path:
            probed = probe_video_duration(item.media_path)
            if probed > 0:
                item.duration_sec = probed

    excluded_ids = _completed_candidate_ids(exclude_jobs_dir)
    filtered: list[Candidate] = []
    for item in dedupe(candidates):
        if item.candidate_id in excluded_ids:
            continue
        if require_media and (not item.media_path or not Path(item.media_path).expanduser().exists()):
            continue
        if item.duration_sec > 0:
            if item.duration_sec > max_duration or item.duration_sec < min_duration:
                continue
        elif min_duration > 0 and require_media:
            continue
        filtered.append(item)

    result = rank(filtered, keywords=keywords)
    write_jsonl(output_path, [item.as_mapping() for item in result])
    return result


def create_jobs(candidates: list[Candidate], jobs_dir: Path, limit: int, allow_missing_media: bool = False) -> list[Path]:
    jobs_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    selected = candidates[:limit] if limit > 0 else candidates
    for candidate in selected:
        if not allow_missing_media and (not candidate.media_path or not Path(candidate.media_path).expanduser().exists()):
            raise FileNotFoundError(
                f"Không tìm thấy media_path của {candidate.candidate_id}: {candidate.media_path}. Kiểm tra input thật hoặc dùng --allow-missing-media chỉ để tạo manifest xem trước."
            )
        job_id = f"{candidate.platform}-{candidate.candidate_id}"
        job_dir = jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = job_dir / "manifest.json"
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                existing["candidate"] = candidate.as_mapping()
                manifest_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
                manifests.append(manifest_path)
                continue
            except (OSError, json.JSONDecodeError):
                pass
        manifest = {
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "candidate": candidate.as_mapping(),
            "stages": {
                "whisper": "pending",
                "vietsub_tts": "pending",
                "localizer": "pending",
                "render": "pending",
                "publish": "pending",
            },
            "artifacts": {
                "transcript": str(job_dir / "transcript.json"),
                "vietsub": str(job_dir / "vietsub.json"),
                "tts_audio": str(job_dir / "tts.wav"),
                "localized_video": str(job_dir / "localized.mp4"),
                "rendered_video": str(job_dir / "rendered.mp4"),
            },
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifests.append(manifest_path)
    return manifests


def run_command(command: str, values: dict[str, str]) -> None:
    formatted = command.format(**values)
    subprocess.run(shlex.split(formatted, posix=False), check=True)


def run_jobs(manifests: list[Path], config: dict[str, Any]) -> None:
    commands = config.get("commands", {})
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("errors"):
            manifest["errors"] = {
                key: value
                for key, value in manifest["errors"].items()
                if manifest.get("stages", {}).get(key) != "completed"
            }
            if not manifest["errors"]:
                manifest.pop("errors")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        candidate = manifest["candidate"]
        values = {
            "input": candidate["media_path"],
            "manifest": str(manifest_path),
            "transcript": manifest["artifacts"]["transcript"],
            "vietsub": manifest["artifacts"]["vietsub"],
            "tts_audio": manifest["artifacts"]["tts_audio"],
            "localized_video": manifest["artifacts"]["localized_video"],
            "rendered_video": manifest["artifacts"]["rendered_video"],
        }
        for stage, command_key in (
            ("whisper", "whisper"),
            ("vietsub_tts", "vietsub_tts"),
            ("localizer", "localizer"),
            ("render", "render"),
        ):
            if manifest.get("stages", {}).get(stage) == "completed":
                continue
            command = commands.get(command_key)
            if not command:
                continue
            try:
                run_command(command, values)
            except Exception as error:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["stages"][stage] = "failed"
                manifest["errors"] = {**manifest.get("errors", {}), stage: str(error)}
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                raise
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["stages"][stage] = "completed"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def print_jobs_status(jobs_dir: Path) -> list[dict[str, Any]]:
    if not jobs_dir.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục jobs: {jobs_dir}")
    manifests = sorted(jobs_dir.glob("*/manifest.json"))
    summaries: list[dict[str, Any]] = []
    for manifest_path in manifests:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        stages = data.get("stages", {})
        candidate = data.get("candidate", {})
        rendered = data.get("artifacts", {}).get("rendered_video", "")
        summary = {
            "job_id": data.get("job_id", manifest_path.parent.name),
            "platform": candidate.get("platform", ""),
            "title": (candidate.get("title") or "")[:50],
            "hot_score": candidate.get("hot_score", 0.0),
            "whisper": stages.get("whisper", "pending"),
            "vietsub_tts": stages.get("vietsub_tts", "pending"),
            "render": stages.get("render", "pending"),
            "rendered_video": rendered if rendered and Path(rendered).exists() else "",
            "errors": data.get("errors", {}),
        }
        summaries.append(summary)
        status_str = f"W:{summary['whisper']} | T:{summary['vietsub_tts']} | R:{summary['render']}"
        print(f"[{summary['job_id']}] ({status_str}) Hot={summary['hot_score']:.1f} :: {summary['title']}")
        if summary["rendered_video"]:
            print(f"   -> Output: {summary['rendered_video']}")
        if summary["errors"]:
            print(f"   -> Errors: {summary['errors']}")
    return summaries


def run_crawler(
    crawler_root: Path,
    platform: str,
    keywords: str,
    max_notes: int = 15,
    login_type: str = "qrcode",
    crawler_type: str = "search",
    headless: bool = False,
) -> None:
    root = crawler_root.resolve()
    main_py = root / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(f"Không tìm thấy MediaCrawler main.py tại: {main_py}")
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    cmd: list[str]
    if venv_python.exists():
        cmd = [str(venv_python), "main.py"]
    else:
        cmd = ["uv", "run", "main.py"]
    cmd.extend(
        [
            "--platform",
            platform,
            "--lt",
            login_type,
            "--type",
            crawler_type,
            "--keywords",
            keywords,
            "--save_data_option",
            "jsonl",
            "--get_media",
            "yes",
            "--crawler_max_notes_count",
            str(max_notes),
            "--headless",
            "yes" if headless else "no",
        ]
    )
    subprocess.run(cmd, cwd=str(root), check=True)


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="hotnews-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--input", type=Path, required=True)
    ingest_parser.add_argument("--output", type=Path, required=True)
    ingest_parser.add_argument("--min-duration", type=float, default=0.0)
    ingest_parser.add_argument("--max-duration", type=float, default=1800)
    ingest_parser.add_argument("--require-media", action="store_true")
    ingest_parser.add_argument("--keywords", default="", help="Danh sách từ khóa ưu tiên chấm điểm, cách nhau bằng dấu phẩy")
    ingest_parser.add_argument("--exclude-jobs-dir", type=Path, default=None)

    jobs_parser = subparsers.add_parser("jobs")
    jobs_parser.add_argument("--ranked", type=Path, required=True)
    jobs_parser.add_argument("--output-dir", type=Path, required=True)
    jobs_parser.add_argument("--limit", type=int, default=10)
    jobs_parser.add_argument("--allow-missing-media", action="store_true")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--jobs-dir", type=Path, required=True)
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--limit", type=int, default=0)

    run_selected_parser = subparsers.add_parser("run-selected")
    run_selected_parser.add_argument("--selected", type=Path, required=True)
    run_selected_parser.add_argument("--jobs-dir", type=Path, default=Path("jobs-selected"))
    run_selected_parser.add_argument("--config", type=Path, default=Path("config.example.json"))
    run_selected_parser.add_argument("--limit", type=int, default=0)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--jobs-dir", type=Path, required=True)

    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.add_argument("--crawler-root", type=Path, default=Path("work/MediaCrawler"))
    normalize_parser.add_argument("--platform", required=True, help="dy, xhs, bili, ks, wb, tieba, zhihu hoặc all")
    normalize_parser.add_argument("--output", type=Path, required=True)
    normalize_parser.add_argument("--source", type=Path)
    normalize_parser.add_argument("--all-files", action="store_true", help="Gộp toàn bộ các file *_contents_*.jsonl thay vì chỉ file mới nhất")

    catalog_parser = subparsers.add_parser("catalog")
    catalog_parser.add_argument("--ranked", type=Path, required=True)
    catalog_parser.add_argument("--output", type=Path, required=True)
    catalog_parser.add_argument("--limit", type=int, default=50)

    crawl_parser = subparsers.add_parser("crawl")
    crawl_parser.add_argument("--crawler-root", type=Path, default=Path("work/MediaCrawler"))
    crawl_parser.add_argument("--platform", default="dy", choices=("dy", "xhs", "bili", "ks", "wb", "tieba", "zhihu"))
    crawl_parser.add_argument("--keywords", default="热点新闻")
    crawl_parser.add_argument("--max-notes", type=int, default=15)
    crawl_parser.add_argument("--lt", default="qrcode", choices=("qrcode", "phone", "cookie"))
    crawl_parser.add_argument("--type", default="search", choices=("search", "detail", "creator"))
    crawl_parser.add_argument("--headless", action="store_true")
    crawl_parser.add_argument("--normalized-output", type=Path, default=Path("crawler-real.jsonl"))
    crawl_parser.add_argument("--ranked-output", type=Path, default=Path("ranked-real.jsonl"))
    crawl_parser.add_argument("--catalog-output", type=Path, default=Path("hot-catalog.html"))

    args = parser.parse_args()
    if args.command == "catalog":
        candidates = [Candidate.from_mapping(row) for row in read_jsonl(args.ranked)]
        print(f"Đã tạo catalog: {write_catalog(candidates, args.output, args.limit)}")
    elif args.command == "normalize":
        count = normalize_media_crawler(
            args.crawler_root.resolve(),
            args.platform,
            args.output,
            args.source.resolve() if args.source else None,
            all_files=args.all_files,
        )
        print(f"Đã chuẩn hóa {count} bản ghi: {args.output}")
    elif args.command == "ingest":
        kw_list = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else None
        result = ingest(
            args.input,
            args.output,
            args.max_duration,
            min_duration=args.min_duration,
            require_media=args.require_media,
            keywords=kw_list,
            exclude_jobs_dir=args.exclude_jobs_dir,
        )
        print(f"Đã xếp hạng {len(result)} ứng viên: {args.output}")
    elif args.command == "jobs":
        candidates = [Candidate.from_mapping(row) for row in read_jsonl(args.ranked)]
        manifests = create_jobs(candidates, args.output_dir, args.limit, args.allow_missing_media)
        print(f"Đã tạo {len(manifests)} job trong: {args.output_dir}")
    elif args.command == "run-selected":
        candidates = [Candidate.from_mapping(row) for row in read_jsonl(args.selected)]
        manifests = create_jobs(candidates, args.jobs_dir, args.limit, allow_missing_media=False)
        print(f"Đã tạo {len(manifests)} job từ danh sách chọn. Bắt đầu chạy Localizer...")
        run_jobs(manifests, load_config(args.config))
    elif args.command == "status":
        print_jobs_status(args.jobs_dir)
    elif args.command == "crawl":
        run_crawler(
            args.crawler_root,
            args.platform,
            args.keywords,
            max_notes=args.max_notes,
            login_type=args.lt,
            crawler_type=args.type,
            headless=args.headless,
        )
        count = normalize_media_crawler(args.crawler_root.resolve(), args.platform, args.normalized_output, all_files=False)
        kw_list = [k.strip() for k in args.keywords.split(",") if k.strip()]
        ranked = ingest(args.normalized_output, args.ranked_output, 1800, keywords=kw_list)
        catalog_path = write_catalog(ranked, args.catalog_output, limit=50)
        print(f"Đã crawl {count} bản ghi, xếp hạng {len(ranked)} video và tạo catalog: {catalog_path}")
    else:
        manifests = sorted(args.jobs_dir.glob("*/manifest.json"))
        if args.limit > 0:
            manifests = manifests[:args.limit]
        if not manifests:
            raise FileNotFoundError(
                f"Không có job manifest trong {args.jobs_dir}. Hãy chạy ingest rồi jobs trước."
            )
        run_jobs(manifests, load_config(args.config))


if __name__ == "__main__":
    main()
