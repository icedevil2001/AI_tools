"""Small atomic JSON persistence helpers."""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import Conversation, Error
from .schema import CURRENT_SCHEMA_VERSION


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Write JSON through a same-directory temporary file and atomic replace."""

    destination = Path(path)
    _ensure_safe_directory(destination.parent)
    _ensure_safe_destination(destination)
    temporary_name: Path | None = None
    try:
        fd, temporary = _open_random_temporary(destination)
        temporary_name = temporary
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
        _fsync_parent_directory(destination.parent)
    finally:
        if temporary_name is not None:
            try:
                temporary_name.unlink()
            except FileNotFoundError:
                pass


def atomic_write_text(path: str | Path, value: str) -> None:
    """Atomically persist UTF-8 text using the same-directory temp strategy."""
    destination = Path(path)
    _ensure_safe_directory(destination.parent)
    _ensure_safe_destination(destination)
    temporary_name: Path | None = None
    try:
        fd, temporary = _open_random_temporary(destination)
        temporary_name = temporary
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
        _fsync_parent_directory(destination.parent)
    finally:
        if temporary_name is not None:
            try:
                temporary_name.unlink()
            except FileNotFoundError:
                pass


def _ensure_safe_directory(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.exists() and current.is_symlink():
            if current in {Path("/var"), Path("/tmp")} and current.resolve() == Path("/private") / current.name:
                current = current.resolve()
                continue
            raise OSError(f"refusing symlink path component: {current}")
        if current.exists() and not current.is_dir():
            raise OSError(f"path component is not a directory: {current}")
        if not current.exists():
            current.mkdir()


def _ensure_safe_destination(path: Path) -> None:
    if not os.path.lexists(path):
        return
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
        raise OSError(f"refusing unsafe archive destination: {path}")


def _open_random_temporary(destination: Path) -> tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(20):
        candidate = destination.parent / f".{destination.name}.{secrets.token_hex(16)}.tmp"
        try:
            return os.open(candidate, flags, 0o600), candidate
        except FileExistsError:
            continue
    raise OSError("could not create exclusive archive temporary")


def _fsync_parent_directory(directory: Path) -> None:
    """Durably flush the directory entry where supported by the platform."""

    directory_flag = getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, os.O_RDONLY | directory_flag)
    except (AttributeError, OSError):
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            # Some filesystems permit opening a directory but do not support fsync.
            return
    finally:
        os.close(descriptor)


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError("archive JSON must contain an object")
    return value


def write_conversation(
    path: str | Path,
    conversation: Conversation,
    *,
    checkpoints: Iterable[Mapping[str, Any]] = (),
    errors: Iterable[Error | Mapping[str, Any]] = (),
) -> None:
    """Persist a normalized conversation and stable progress/error collections."""

    # Keep this low-level helper safe for callers that bypass ArchiveWriter.
    # Archive assembly adds the redaction report to its manifest.
    from .redaction import RedactionReport, redact_conversation, redact_errors, redact_value
    report = RedactionReport()
    conversation = redact_conversation(conversation, report)
    normalized_errors_model = [item if isinstance(item, Error) else Error.from_dict(item) for item in errors]
    normalized_errors = [item.to_dict() for item in redact_errors(normalized_errors_model, report)]
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "conversation": conversation.to_dict(),
        "checkpoints": [redact_value(dict(item), report) for item in checkpoints],
        "errors": normalized_errors,
    }
    atomic_write_json(path, payload)
