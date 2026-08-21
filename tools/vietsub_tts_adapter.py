from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--vietsub", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--command", default=None)
    args = parser.parse_args()
    if not args.command:
        raise SystemExit("Set --command to the local translation/TTS runner, or configure commands.vietsub_tts")
    values = {"transcript": str(args.transcript), "vietsub": str(args.vietsub), "audio": str(args.audio)}
    subprocess.run(args.command.format(**values), shell=True, check=True)


if __name__ == "__main__":
    main()
