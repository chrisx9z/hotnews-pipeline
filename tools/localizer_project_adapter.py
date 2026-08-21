from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def project_python(root: Path) -> Path:
    candidate = root / ".venv" / "Scripts" / "python.exe"
    return candidate if candidate.exists() else Path(sys.executable)


def ensure_project(manifest_path: Path, root: Path, voice_id: str) -> tuple[dict, Path, Path]:
    manifest = load_manifest(manifest_path)
    candidate = manifest["candidate"]
    source = Path(candidate["media_path"]).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Không tìm thấy video nguồn: {source}")
    project_dir_value = manifest.get("localizer_project_dir")
    if project_dir_value:
        project_dir = Path(project_dir_value).resolve()
        project_json = project_dir / "project.json"
        if project_json.exists():
            return manifest, project_dir, source
    sys.path.insert(0, str(root))
    from core.project import VideoProject

    project = VideoProject.create(source)
    project.processing_settings["voice_profile_id"] = voice_id
    project.processing_settings["subtitle_mode"] = "burn"
    project.processing_settings["audio_mode"] = "keep"
    project.processing_settings["original_volume_percent"] = 30
    project.save()
    project_dir = Path(project.project_dir).resolve()
    (project_dir / "source_metadata.json").write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest["localizer_project_dir"] = str(project_dir)
    manifest["artifacts"]["transcript"] = str(project_dir / "subtitles" / "original.srt")
    manifest["artifacts"]["vietsub"] = str(project_dir / "subtitles" / "original.translated.vi.srt")
    manifest["artifacts"]["tts_audio"] = str(project_dir / "audio" / "vietnamese_voice.wav")
    save_manifest(manifest_path, manifest)
    return manifest, project_dir, source


def run_script(root: Path, script_name: str, project_dir: Path, *extra: str) -> None:
    command = [str(project_python(root)), str(root / "scripts" / script_name), str(project_dir), *extra]
    environment = os.environ.copy()
    current_python_path = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(root) + (os.pathsep + current_python_path if current_python_path else "")
    subprocess.run(command, cwd=str(root), env=environment, check=True)


def finalize_manifest(manifest_path: Path, manifest: dict, project_dir: Path) -> None:
    candidates = sorted((project_dir / "output").glob("*/*.mp4"), key=lambda item: item.stat().st_mtime)
    if candidates:
        manifest["artifacts"]["rendered_video"] = str(candidates[-1])
    save_manifest(manifest_path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--localizer-root", type=Path, required=True)
    parser.add_argument("--stage", choices=("transcription", "translation_tts", "finalize"), required=True)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--model-size", default="large-v3-turbo")
    parser.add_argument("--voice-id", default="nghitts:Ngọc Huyền (mới)")
    args = parser.parse_args()
    root = args.localizer_root.resolve()
    manifest_path = args.manifest.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Không tìm thấy AI Video Localizer: {root}")
    manifest, project_dir, _ = ensure_project(manifest_path, root, args.voice_id)
    if args.stage == "transcription":
        run_script(root, "run_project_transcription.py", project_dir, "--model-size", args.model_size, "--language", args.language)
    elif args.stage == "translation_tts":
        run_script(root, "run_project_translation.py", project_dir)
        run_script(root, "run_project_tts.py", project_dir, "--voice-id", args.voice_id, "--full")
    else:
        run_script(root, "run_project_finalize.py", project_dir)
        manifest = load_manifest(manifest_path)
        finalize_manifest(manifest_path, manifest, project_dir)


if __name__ == "__main__":
    main()
