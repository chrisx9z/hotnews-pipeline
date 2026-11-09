from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


DEFAULT_LOCALIZER_ROOT = Path(os.environ.get("AI_VIDEO_LOCALIZER_ROOT", r"D:\AI-Video-Localizer"))


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_localizer_root(configured_root: Path | None) -> Path:
    if configured_root is not None:
        candidate = configured_root.expanduser()
        if candidate.exists():
            return candidate.resolve()
    if DEFAULT_LOCALIZER_ROOT.exists():
        return DEFAULT_LOCALIZER_ROOT.resolve()
    if configured_root is not None:
        return configured_root.resolve()
    return DEFAULT_LOCALIZER_ROOT


def project_python(root: Path) -> Path:
    candidate = root / ".venv" / "Scripts" / "python.exe"
    return candidate if candidate.exists() else Path(sys.executable)


def _sync_basic_transcription_fingerprint(root: Path, project_dir: Path, source: Path) -> None:
    """Keep `original.basic.json` settings_fingerprint in sync if settings change after transcription."""
    original_srt = project_dir / "subtitles" / "original.srt"
    basic_json = original_srt.with_suffix(".basic.json")
    if not original_srt.exists() or not basic_json.exists():
        return
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from core.basic_workflow import record_basic_transcription

        basic_json.unlink(missing_ok=True)
        record_basic_transcription(source, original_srt)
    except Exception:
        pass


def ensure_project(
    manifest_path: Path,
    root: Path,
    *,
    voice_id: str,
    workflow_profile: str = "basic",
    basic_gap_recheck: bool = True,
    crop_preset: str = "original",
    audio_mode: str = "custom",
    original_volume_percent: int = 27,
    remove_source_subtitle: bool = False,
    remove_source_logo: bool = False,
) -> tuple[dict, Path, Path]:
    manifest = load_manifest(manifest_path)
    candidate = manifest["candidate"]
    source = Path(candidate["media_path"]).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Không tìm thấy video nguồn: {source}")

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from core.project import VideoProject

    project_dir_value = manifest.get("localizer_project_dir")
    if project_dir_value:
        project_dir = Path(project_dir_value).resolve()
        project_json = project_dir / "project.json"
        if project_json.exists():
            project = VideoProject.load(project_json)
            changed = False
            if voice_id and project.processing_settings.get("voice_profile_id") != voice_id:
                project.processing_settings["voice_profile_id"] = voice_id
                changed = True
            if project.processing_settings.get("workflow_profile") != workflow_profile:
                project.processing_settings["workflow_profile"] = workflow_profile
                changed = True
            if project.processing_settings.get("basic_gap_recheck") != basic_gap_recheck:
                project.processing_settings["basic_gap_recheck"] = basic_gap_recheck
                changed = True
            if changed:
                project.save()
                _sync_basic_transcription_fingerprint(root, project_dir, source)
            return manifest, project_dir, source

    project = VideoProject.create(source)
    project.processing_settings["workflow_profile"] = workflow_profile
    project.processing_settings["basic_gap_recheck"] = basic_gap_recheck
    project.processing_settings["voice_profile_id"] = voice_id
    project.processing_settings["subtitle_mode"] = "burn"
    project.processing_settings["audio_mode"] = audio_mode
    project.processing_settings["original_volume_percent"] = original_volume_percent
    project.processing_settings["tts_fit_to_subtitle_slot"] = True
    project.processing_settings["tts_max_fit_speed"] = 1.15
    project.processing_settings["crop_preset"] = crop_preset
    project.processing_settings["remove_source_subtitle"] = remove_source_subtitle
    project.processing_settings["remove_source_logo"] = remove_source_logo
    project.stages["video_edit"] = "skipped"
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
    environment["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(command, cwd=str(root), env=environment, check=True)


def finalize_manifest(manifest_path: Path, manifest: dict, project_dir: Path) -> None:
    candidates = sorted((project_dir / "output").glob("*/*.mp4"), key=lambda item: item.stat().st_mtime)
    if candidates:
        latest_mp4 = candidates[-1]
        manifest["artifacts"]["rendered_video"] = str(latest_mp4)
        sidecar = latest_mp4.with_suffix(".manifest.json")
        if sidecar.exists():
            manifest["artifacts"]["export_manifest"] = str(sidecar)
            try:
                export_meta = json.loads(sidecar.read_text(encoding="utf-8"))
                manifest["output_duration_seconds"] = export_meta.get("output_duration_seconds")
                manifest["voice_presence_check"] = export_meta.get("voice_presence_check")
            except (OSError, json.JSONDecodeError):
                pass
    save_manifest(manifest_path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--localizer-root", type=Path, default=None)
    parser.add_argument(
        "--stage",
        choices=("transcription", "translation_tts", "finalize", "end_to_end"),
        required=True,
    )
    parser.add_argument("--language", default="zh")
    parser.add_argument("--model-size", default="large-v3-turbo")
    parser.add_argument("--voice-id", default="podcast1")
    parser.add_argument("--workflow-profile", choices=("basic", "audited"), default="basic")
    parser.add_argument("--no-gap-recheck", action="store_true")
    parser.add_argument("--crop-preset", default="original")
    parser.add_argument("--audio-mode", default="custom", choices=("custom", "keep", "mute"))
    parser.add_argument("--original-volume", type=int, default=27)
    parser.add_argument("--remove-source-subtitle", action="store_true")
    parser.add_argument("--remove-source-logo", action="store_true")
    parser.add_argument("--isolated", action="store_true")
    args = parser.parse_args()

    root = resolve_localizer_root(args.localizer_root)
    manifest_path = args.manifest.resolve()
    if not root.exists():
        raise FileNotFoundError(
            f"Không tìm thấy AI Video Localizer: {root}. Hãy truyền --localizer-root hoặc đặt biến môi trường AI_VIDEO_LOCALIZER_ROOT."
        )

    manifest, project_dir, _ = ensure_project(
        manifest_path,
        root,
        voice_id=args.voice_id,
        workflow_profile=args.workflow_profile,
        basic_gap_recheck=not args.no_gap_recheck,
        crop_preset=args.crop_preset,
        audio_mode=args.audio_mode,
        original_volume_percent=args.original_volume,
        remove_source_subtitle=args.remove_source_subtitle,
        remove_source_logo=args.remove_source_logo,
    )

    if args.stage == "transcription":
        run_script(
            root,
            "run_project_transcription.py",
            project_dir,
            "--model-size",
            args.model_size,
            "--language",
            args.language,
        )
    elif args.stage == "translation_tts":
        translate_args = ["--isolated"] if args.isolated else []
        run_script(root, "run_project_translation.py", project_dir, *translate_args)
        run_script(root, "run_project_tts.py", project_dir, "--voice-id", args.voice_id, "--full")
    elif args.stage == "end_to_end":
        run_script(
            root,
            "run_project_transcription.py",
            project_dir,
            "--model-size",
            args.model_size,
            "--language",
            args.language,
        )
        translate_args = ["--isolated"] if args.isolated else []
        run_script(root, "run_project_translation.py", project_dir, *translate_args)
        run_script(root, "run_project_tts.py", project_dir, "--voice-id", args.voice_id, "--full")
        run_script(root, "run_project_finalize.py", project_dir)
        manifest = load_manifest(manifest_path)
        finalize_manifest(manifest_path, manifest, project_dir)
    else:
        run_script(root, "run_project_finalize.py", project_dir)
        manifest = load_manifest(manifest_path)
        finalize_manifest(manifest_path, manifest, project_dir)


if __name__ == "__main__":
    main()
