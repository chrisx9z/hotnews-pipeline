from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from .models import Candidate
from .media_crawler import normalize as normalize_media_crawler
from .catalog import write_catalog
from .ranking import rank


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


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    output = []
    for candidate in candidates:
        key = candidate.source_url.strip().lower()
        if not key:
            key = sha256(f"{candidate.platform}|{candidate.title}|{candidate.author}".encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output


def ingest(input_path: Path, output_path: Path, max_duration: float) -> list[Candidate]:
    candidates = [Candidate.from_mapping(row) for row in read_jsonl(input_path)]
    candidates = [item for item in dedupe(candidates) if 0 < item.duration_sec <= max_duration or item.duration_sec == 0]
    result = rank(candidates)
    write_jsonl(output_path, [item.as_mapping() for item in result])
    return result


def create_jobs(candidates: list[Candidate], jobs_dir: Path, limit: int, allow_missing_media: bool = False) -> list[Path]:
    jobs_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for candidate in candidates[:limit]:
        if not allow_missing_media and (not candidate.media_path or not Path(candidate.media_path).expanduser().exists()):
            raise FileNotFoundError(
                f"Không tìm thấy media_path của {candidate.candidate_id}: {candidate.media_path}. Kiểm tra input thật hoặc dùng --allow-missing-media chỉ để tạo manifest xem trước."
            )
        job_id = f"{candidate.platform}-{candidate.candidate_id}"
        job_dir = jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "candidate": candidate.as_mapping(),
            "stages": {"whisper": "pending", "vietsub_tts": "pending", "localizer": "pending", "render": "pending", "publish": "pending"},
            "artifacts": {"transcript": str(job_dir / "transcript.json"), "vietsub": str(job_dir / "vietsub.json"), "tts_audio": str(job_dir / "tts.wav"), "localized_video": str(job_dir / "localized.mp4"), "rendered_video": str(job_dir / "rendered.mp4")},
        }
        manifest_path = job_dir / "manifest.json"
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
            manifest["errors"] = {key: value for key, value in manifest["errors"].items() if manifest.get("stages", {}).get(key) != "completed"}
            if not manifest["errors"]:
                manifest.pop("errors")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        candidate = manifest["candidate"]
        values = {"input": candidate["media_path"], "manifest": str(manifest_path), "transcript": manifest["artifacts"]["transcript"], "vietsub": manifest["artifacts"]["vietsub"], "tts_audio": manifest["artifacts"]["tts_audio"], "localized_video": manifest["artifacts"]["localized_video"], "rendered_video": manifest["artifacts"]["rendered_video"]}
        for stage, command_key in (("whisper", "whisper"), ("vietsub_tts", "vietsub_tts"), ("localizer", "localizer"), ("render", "render")):
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
    ingest_parser.add_argument("--max-duration", type=float, default=1800)
    jobs_parser = subparsers.add_parser("jobs")
    jobs_parser.add_argument("--ranked", type=Path, required=True)
    jobs_parser.add_argument("--output-dir", type=Path, required=True)
    jobs_parser.add_argument("--limit", type=int, default=10)
    jobs_parser.add_argument("--allow-missing-media", action="store_true")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--jobs-dir", type=Path, required=True)
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--limit", type=int, default=0)
    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.add_argument("--crawler-root", type=Path, required=True)
    normalize_parser.add_argument("--platform", required=True)
    normalize_parser.add_argument("--output", type=Path, required=True)
    normalize_parser.add_argument("--source", type=Path)
    catalog_parser = subparsers.add_parser("catalog")
    catalog_parser.add_argument("--ranked", type=Path, required=True)
    catalog_parser.add_argument("--output", type=Path, required=True)
    catalog_parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if args.command == "catalog":
        candidates = [Candidate.from_mapping(row) for row in read_jsonl(args.ranked)]
        print(f"Đã tạo catalog: {write_catalog(candidates, args.output, args.limit)}")
    elif args.command == "normalize":
        count = normalize_media_crawler(args.crawler_root.resolve(), args.platform, args.output, args.source.resolve() if args.source else None)
        print(f"Đã chuẩn hóa {count} bản ghi: {args.output}")
    elif args.command == "ingest":
        ingest(args.input, args.output, args.max_duration)
    elif args.command == "jobs":
        candidates = [Candidate.from_mapping(row) for row in read_jsonl(args.ranked)]
        create_jobs(candidates, args.output_dir, args.limit, args.allow_missing_media)
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
