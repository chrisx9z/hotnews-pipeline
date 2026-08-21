from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default=None)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit("Install the adapter dependency with: uv pip install 'faster-whisper>=1.1.0'") from exc
    device = args.device
    compute_type = "float16" if device in {"auto", "cuda"} else "int8"
    model = WhisperModel(args.model, device=device, compute_type=compute_type)
    segments, info = model.transcribe(str(args.input), language=args.language, vad_filter=True, beam_size=5)
    result = {
        "source": str(args.input),
        "language": info.language,
        "language_probability": info.language_probability,
        "segments": [{"start": segment.start, "end": segment.end, "text": segment.text.strip()} for segment in segments],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
