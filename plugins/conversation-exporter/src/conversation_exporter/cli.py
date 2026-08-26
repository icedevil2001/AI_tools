"""Command-line interface for bounded conversation collectors."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

from .collectors.chatgpt import CaptureValidationError, ingest_capture, validate_capture
from .collectors.codex import collect_codex_sessions, resolve_codex_home
from .paths import ArchiveMode
from .storage import write_conversation
from .paths import resolve_archive_path
from .archive import export_archive, verify_archive, ArchiveVersionError, new_run_root


def _snapshot_sort_key(path: Path) -> tuple[str, int]:
    match = re.fullmatch(r"(.+?)(?:-(\d+))?", path.name)
    return (match.group(1) if match else path.name, int(match.group(2) or 1) if match else 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conversation-exporter")
    parser.add_argument("command", nargs="?", choices=["init", "export", "verify"], help="operation (export, verify, or optional init)")
    parser.add_argument("--source", required=False, default=None, help="source adapter name (codex, chatgpt, or all)")
    parser.add_argument("--mode", choices=[mode.value for mode in ArchiveMode], default=ArchiveMode.SNAPSHOT.value)
    parser.add_argument("--output", required=True, help="confirmed archive destination directory")
    parser.add_argument("--init", action="store_true", help="create the destination directory")
    parser.add_argument("--dry-run", action="store_true", help="print the planned operation without collecting")
    parser.add_argument("--codex-home", help="Codex home (overrides CODEX_HOME and ~/.codex)")
    parser.add_argument("--codex-attachment-root", action="append", default=[], help="approved Codex attachment directory (repeatable; never inferred from Codex home)")
    parser.add_argument("--capture", help="one bounded ChatGPT capture JSON file")
    parser.add_argument("--download-root", help="approved root for already-downloaded ChatGPT attachments")
    parser.add_argument("--latest-snapshot", action="store_true", help="verify the newest snapshot below --output")
    parser.add_argument("--run-root", help="exact existing snapshot run root to resume")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    if args.command == "verify":
        if args.latest_snapshot:
            snapshots = sorted((item for item in (output / "snapshots").iterdir() if item.is_dir()), key=_snapshot_sort_key) if (output / "snapshots").is_dir() else []
            if not snapshots:
                print(json.dumps({"valid": False, "errors": ["no snapshots found"]}, sort_keys=True))
                return 3
            output = snapshots[-1]
        result = verify_archive(output)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("valid") else 3
    if args.source is None and args.command != "init":
        print("--source is required for collection/export", file=sys.stderr)
        return 2
    if args.run_root:
        run_root_arg = Path(args.run_root)
        try:
            run_root_arg.resolve().relative_to((output / "snapshots").resolve())
        except ValueError:
            print("--run-root must be inside --output/snapshots", file=sys.stderr)
            return 2
        if args.mode == ArchiveMode.SNAPSHOT.value and not run_root_arg.is_dir():
            print("--run-root must name an existing snapshot root", file=sys.stderr)
            return 2
    if (args.init or args.command == "init") and not args.dry_run:
        output.mkdir(parents=True, exist_ok=True)
        if args.command == "init" and args.source is None:
            print(json.dumps({"output": str(output), "initialized": True}, sort_keys=True))
            return 0
    if args.command == "init" and args.source is None:
        print(json.dumps({"output": str(output), "initialized": output.is_dir(), "dry_run": True}, sort_keys=True))
        return 0
    plan = {"source": args.source, "mode": args.mode, "output": str(output), "initialized": output.is_dir()}
    if args.dry_run:
        if args.source == "codex":
            result = collect_codex_sessions(args.codex_home)
            plan.update({"conversation_count": len(result.conversations), "error_count": len(result.errors)})
        elif args.source == "chatgpt":
            if not args.capture:
                print("--capture is required for --source chatgpt", file=sys.stderr)
                return 2
            try:
                with Path(args.capture).open("r", encoding="utf-8") as stream:
                    capture = validate_capture(json.load(stream))
                plan.update({"conversation_count": 1, "message_count": len(capture["messages"]), "attachment_count": len(capture["attachments"]), "error_count": len(capture.get("errors", []))})
            except (OSError, ValueError, json.JSONDecodeError, CaptureValidationError) as exc:
                print(f"invalid capture: {exc}", file=sys.stderr)
                return 2
        elif args.source == "all":
            result = collect_codex_sessions(args.codex_home)
            plan.update({"conversation_count": len(result.conversations), "error_count": len(result.errors)})
            if args.capture:
                try:
                    with Path(args.capture).open("r", encoding="utf-8") as stream:
                        capture = validate_capture(json.load(stream))
                    plan["conversation_count"] += 1
                    plan["message_count"] = len(capture["messages"])
                    plan["error_count"] = plan.get("error_count", 0) + len(capture.get("errors", []))
                except (OSError, ValueError, json.JSONDecodeError, CaptureValidationError) as exc:
                    print(f"invalid capture: {exc}", file=sys.stderr)
                    return 2
        else:
            print(f"unsupported source: {args.source}", file=sys.stderr)
            return 2
        print(json.dumps(plan, sort_keys=True))
        return 4 if plan.get("error_count", 0) else 0
    if args.source in {"codex", "all"}:
        # Keep an uninitialised legacy invocation non-mutating. Callers that
        # intend to export from the default home explicitly opt in with
        # ``--init`` (or provide ``--codex-home``/``CODEX_HOME``).
        if not args.init and args.codex_home is None and "CODEX_HOME" not in __import__("os").environ:
            print("pass --codex-home (or --init to use the default Codex home)", file=sys.stderr)
            return 2
        codex_home = resolve_codex_home(args.codex_home)
        result = collect_codex_sessions(codex_home)
        conversations = list(result.conversations)
        errors = list(result.errors)
        checkpoint_artifacts = {}
        global_errors = []
        errors_by_conversation = {}
        by_session_file = {str(item.metadata.get("session_file")): item for item in conversations}
        for error in errors:
            details = dict(error.details)
            key = details.get("conversation_key")
            if (not key or not any(f"{item.source}:{item.id}" == key for item in conversations)) and details.get("session_file") in by_session_file:
                conversation = by_session_file[str(details["session_file"])]
                key = f"{conversation.source}:{conversation.id}"
            if key and any(f"{item.source}:{item.id}" == key for item in conversations):
                errors_by_conversation.setdefault(str(key), []).append(error)
            else:
                global_errors.append(error)
        run_root = (Path(args.run_root) if args.run_root else new_run_root(output, mode=args.mode)) if args.source == "all" and args.mode == ArchiveMode.SNAPSHOT.value else None
        if args.source == "all" and args.capture:
            try:
                capture_result = ingest_capture(args.capture, output, download_root=args.download_root, run_root=run_root, finalize=False)
                if capture_result.conversation is not None:
                    conversations.append(capture_result.conversation)
                    errors_by_conversation[f"chatgpt:{capture_result.conversation.id}"] = capture_result.errors
                errors.extend(capture_result.errors)
                checkpoint_artifacts.update(capture_result.checkpoint_artifacts)
            except (OSError, ValueError, json.JSONDecodeError, CaptureValidationError) as exc:
                print(f"capture ingestion failed: {exc}", file=sys.stderr)
                return 3
        try:
            # A single archive finalize covers both source adapters in an
            # ``all`` run, sharing one reserved snapshot root.
            summary = export_archive(output, conversations, mode=args.mode, errors=global_errors, errors_by_conversation=errors_by_conversation, run_root=run_root, checkpoint_artifacts=checkpoint_artifacts, approved_roots={"codex": args.codex_attachment_root, "chatgpt": [args.download_root] if args.download_root else []})
            print(json.dumps(summary, sort_keys=True))
        except (OSError, ValueError, TypeError, ArchiveVersionError) as exc:
            print(f"failed to write archive: {exc}", file=sys.stderr)
            return 3
        if errors:
            for error in errors:
                print(error.message, file=sys.stderr)
            return 4
        return 0
    if args.source == "chatgpt":
        if not args.capture:
            print("--capture is required for --source chatgpt", file=sys.stderr)
            return 2
        try:
            result = ingest_capture(args.capture, output, mode=args.mode, download_root=args.download_root, run_root=args.run_root)
        except (OSError, ValueError, json.JSONDecodeError, CaptureValidationError) as exc:
            print(f"capture ingestion failed: {exc}", file=sys.stderr)
            return 3
        for error in result.errors:
            print(error.message, file=sys.stderr)
        print(json.dumps({"output_path": str(result.output_path), "skipped": result.skipped, "error_count": len(result.errors)}, sort_keys=True))
        return 4 if result.errors else 0
    print(f"unsupported source: {args.source}", file=sys.stderr)
    return 2
