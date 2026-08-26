#!/usr/bin/env python3
"""Ingest a single capture produced by the Chrome-control skill.

This script intentionally does not control Chrome. It consumes a bounded JSON capture
created in an authenticated tab and delegates validation/persistence to the package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT / "src"))

from conversation_exporter.collectors.chatgpt import CaptureValidationError, ingest_capture, validate_capture  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest one bounded Chrome-produced ChatGPT capture")
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--download-root", type=Path, help="approved root containing local Chrome downloads")
    parser.add_argument("--mode", choices=("snapshot", "incremental"), default="incremental")
    parser.add_argument("--dry-run", action="store_true", help="validate/count without writing")
    args = parser.parse_args(argv)
    try:
        capture = json.loads(args.capture.read_text(encoding="utf-8"))
        capture = validate_capture(capture)
    except (OSError, ValueError, json.JSONDecodeError, CaptureValidationError) as exc:
        print(f"invalid capture: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps({"id": capture["id"], "status": capture["status"], "messages": len(capture["messages"]), "attachments": len(capture["attachments"])}, sort_keys=True))
        return 0
    try:
        result = ingest_capture(capture, args.output, mode=args.mode, download_root=args.download_root)
    except (OSError, ValueError, CaptureValidationError) as exc:
        print(f"capture ingestion failed: {exc}", file=sys.stderr)
        return 3
    for error in result.errors:
        print(error.message, file=sys.stderr)
    return 4 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
