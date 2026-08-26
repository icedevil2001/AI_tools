"""Dependency-free Codex session JSONL collector.

The Codex on-disk stream contains a great deal of runtime and orchestration
state.  This adapter deliberately uses a small allowlist of user-visible
record kinds instead of attempting to infer visibility from arbitrary JSON.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from ..models import Attachment, Conversation, Entry, Error


@dataclass(frozen=True)
class CollectionResult:
    conversations: tuple[Conversation, ...] = ()
    errors: tuple[Error, ...] = ()


def resolve_codex_home(
    explicit_home: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    user_home: str | Path | None = None,
) -> Path:
    """Resolve Codex home with explicit, environment, then user-home precedence."""

    env = os.environ if environ is None else environ
    value = explicit_home if explicit_home is not None else env.get("CODEX_HOME")
    if value is None:
        value = Path(user_home).expanduser() / ".codex" if user_home else Path.home() / ".codex"
    return Path(value).expanduser()


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping) and item.get("type") in {"input_text", "output_text", "text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if isinstance(value, Mapping):
        # Only explicit visible text fields are allowed. Never serialize a
        # response/tool mapping wholesale (it can contain hidden metadata).
        for key in ("text", "content", "message", "output", "result", "stdout", "stderr"):
            if key in value:
                return _text(value[key])
        return ""
    return ""


def _attachments(value: Any) -> tuple[Attachment, ...]:
    if not isinstance(value, list):
        return ()
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        result.append(
            Attachment(
                id=str(item.get("id", item.get("file_id", ""))),
                filename=str(item.get("filename", item.get("name", ""))),
                media_type=str(item.get("media_type", item.get("mime_type", "application/octet-stream"))),
                uri=item.get("uri", item.get("url")),
                size_bytes=item.get("size_bytes"),
                metadata={**{k: item[k] for k in ("description", "alt", "source_type") if isinstance(item.get(k), str)}, "provenance": "codex"},
            )
        )
    return tuple(result)


def _content_attachments(value: Any) -> tuple[Attachment, ...]:
    """Turn visible image/file content refs into attachment records."""

    if not isinstance(value, list):
        return ()
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or item.get("type") not in {"input_image", "output_image", "file"}:
            continue
        uri = item.get("image_url", item.get("url", item.get("file_url")))
        result.append(Attachment(id=str(item.get("id", f"content-attachment-{index}")), filename=str(item.get("filename", item.get("name", ""))), media_type=str(item.get("media_type", item.get("mime_type", "application/octet-stream"))), uri=uri, metadata={"source_type": item.get("type"), "provenance": "codex"}))
    return tuple(result)


def _entry_content(record: Mapping[str, Any], payload: Mapping[str, Any] | None, kind: str, role: str) -> str:
    candidate = record.get("content")
    if candidate is None and payload is not None:
        candidate = payload.get("content")
    if candidate is None and payload is not None and kind == "user_message":
        candidate = payload.get("message", payload.get("text"))
    if kind in {"function_call", "custom_tool_call", "tool_call", "action"}:
        raw_name = (payload or record).get("name", "tool")
        name = raw_name.strip() if isinstance(raw_name, str) else "tool"
        return name
    if kind in {"function_call_output", "custom_tool_call_output", "tool_result", "action_result"}:
        return _text((payload or record).get("output", (payload or record).get("result", "")))
    if isinstance(candidate, str):
        return candidate
    if isinstance(candidate, list) and kind == "message":
        allowed_types = {"text", "input_text"} if role == "user" else {"text", "output_text"}
        return "".join(item.get("text", "") for item in candidate if isinstance(item, Mapping) and item.get("type") in allowed_types and isinstance(item.get("text"), str))
    return _text(candidate)


def _stable_entry_id(session_id: str, record: Mapping[str, Any], payload: Mapping[str, Any] | None, kind: str, role: str, content: str, created_at: str | None, occurrences: dict[str, int]) -> str:
    source_value = (payload or record).get("id", (payload or record).get("call_id", ""))
    source = str(source_value) if isinstance(source_value, (str, int)) else ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", source):
        source = ""
    if source:
        base = f"source:{source}"
    else:
        fingerprint = json.dumps([kind, role, content, created_at], ensure_ascii=False, separators=(",", ":"))
        base = f"hash:{hashlib.sha256(fingerprint.encode()).hexdigest()[:20]}"
    key = f"{kind}|{role}|{base}"
    occurrences[key] = occurrences.get(key, 0) + 1
    return f"codex:{session_id}:{kind}:{base}:occ-{occurrences[key]}"


def _collect_file(path: Path, relative_path: str | None = None, *, descriptor: int | None = None) -> tuple[Conversation, list[Error]]:
    errors: list[Error] = []
    records: list[tuple[int, Mapping[str, Any]]] = []
    try:
        fd = descriptor if descriptor is not None else os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        stat_result = os.fstat(fd)
        if not __import__("stat").S_ISREG(stat_result.st_mode) or stat_result.st_nlink != 1:
            os.close(fd)
            raise OSError("session file must be a unique regular file")
        stream = os.fdopen(fd, "rb")
    except OSError as exc:
        display_path = relative_path or path.name
        return Conversation(id=path.stem, source="codex", metadata={"session_file": display_path}), [Error("session_unreadable", str(exc), True, {"session_file": display_path})]
    with stream:
        for line_number, raw_line in enumerate(stream, 1):
            if not raw_line.strip():
                continue
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                errors.append(Error("malformed_utf8", f"invalid UTF-8 at line {line_number}", True, {"session_file": relative_path or path.name, "line": line_number, "reason": str(exc)}))
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(Error("malformed_line", f"invalid JSON at line {line_number}: {exc.msg}", True, {"session_file": relative_path or path.name, "line": line_number}))
                continue
            if not isinstance(value, Mapping):
                errors.append(Error("malformed_line", f"JSON line {line_number} is not an object", True, {"session_file": relative_path or path.name, "line": line_number}))
                continue
            records.append((line_number, value))

    first = records[0][1] if records else {}
    first_payload = first.get("payload") if isinstance(first.get("payload"), Mapping) else {}
    raw_session_id = str(first.get("id") or first_payload.get("id") or path.stem)
    session_id = raw_session_id
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", session_id):
        session_id = f"codex-path-{hashlib.sha256((relative_path or path.name).encode('utf-8')).hexdigest()[:32]}"
        errors.append(Error("session_id_normalized", "unsafe session metadata ID normalized to an opaque ID", True, {"session_file": relative_path or path.name, "resolved_id": session_id}))
    session_timestamp = first.get("timestamp") or first_payload.get("timestamp")
    metadata: dict[str, Any] = {"session_file": relative_path or path.name}
    entries: list[Entry] = []
    conversation_attachments: list[Attachment] = []
    occurrences: dict[str, int] = {}
    updated_at = session_timestamp if isinstance(session_timestamp, str) else None
    for line_number, record in records:
        record_type = record.get("type")
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            payload = None
        # A session_meta record is metadata, never a visible message.
        if record_type == "session_meta" and payload is not None:
            metadata.update({k: v for k, v in payload.items() if k in {"cli_version", "context_window", "history_mode", "model_provider", "originator", "source", "status", "thread_source", "timestamp"} and isinstance(v, (str, int, float, bool, type(None)))})
            metadata["session_id"] = session_id
            continue
        if record_type is None and record.get("id"):
            metadata.update({"session_id": session_id})
            continue
        kind = str((payload or record).get("type", record_type or ""))
        role = None
        if record_type == "message" and str(record.get("role")) in {"user", "assistant"}:
            role = str(record["role"])
        elif record_type == "response_item" and kind == "message" and str((payload or {}).get("role")) in {"user", "assistant"}:
            role = str((payload or {})["role"])
        elif record_type == "event_msg" and kind == "user_message":
            role = "user"
        elif record_type == "response_item" and kind in {"function_call", "custom_tool_call", "tool_call", "action"}:
            role = "tool_call"
        elif record_type == "response_item" and kind in {"function_call_output", "custom_tool_call_output", "tool_result", "action_result"}:
            role = "tool_result"
        if role is None:
            continue
        source = payload or record
        created_at = record.get("timestamp", source.get("timestamp"))
        if isinstance(created_at, str):
            updated_at = created_at
        content = _entry_content(record, payload, kind, role)
        atts = _attachments(record.get("attachments", source.get("attachments", []))) + _content_attachments(source.get("content"))
        conversation_attachments.extend(atts)
        metadata_entry = {"source_type": kind, "source_line": line_number}
        for key in ("name", "call_id", "branch_id"):
            if key in source and isinstance(source[key], (str, int)):
                metadata_entry[key] = source[key]
        if kind in {"function_call", "custom_tool_call", "tool_call", "action"} and isinstance(source.get("arguments"), str):
            # Preserve explicit structured arguments without serializing the
            # full response mapping or opaque internal strings.
            try:
                arguments = json.loads(source["arguments"])
            except (TypeError, ValueError):
                arguments = None
            if isinstance(arguments, (dict, list, str, int, float, bool)):
                metadata_entry["arguments"] = arguments
        timestamp = created_at if isinstance(created_at, str) else None
        entries.append(Entry(_stable_entry_id(session_id, record, payload, kind, role, content, timestamp, occurrences), role, content, timestamp, atts, metadata_entry))
    if not entries and not session_id:
        session_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    errors = [replace(error, details={**dict(error.details), "conversation_key": f"codex:{session_id}"}) for error in errors]
    return Conversation(id=session_id, source="codex", created_at=session_timestamp if isinstance(session_timestamp, str) else None, updated_at=updated_at, entries=tuple(entries), attachments=tuple(conversation_attachments), metadata=metadata), errors


def _open_relative(root_fd: int, relative_path: str) -> int:
    """Open a session relative to a held home descriptor, never by pathname."""
    flags_dir = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags_file = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    current = os.dup(root_fd)
    try:
        parts = Path(relative_path).parts
        for component in parts[:-1]:
            nxt = os.open(component, flags_dir, dir_fd=current)
            os.close(current)
            current = nxt
        fd = os.open(parts[-1], flags_file, dir_fd=current)
        return fd
    finally:
        os.close(current)


def collect_codex_sessions(
    codex_home: str | Path | None = None,
    *,
    explicit_home: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> CollectionResult:
    """Collect all ``sessions/**/*.jsonl`` files in deterministic path order."""

    home = resolve_codex_home(explicit_home if explicit_home is not None else codex_home, environ)
    home = home.resolve()
    sessions = home / "sessions"
    if not sessions.exists():
        return CollectionResult((), (Error("sessions_missing", "Codex sessions directory not found", True, {"session_file": "sessions"}),))
    try:
        root_fd = os.open(sessions, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            if not __import__("stat").S_ISDIR(os.fstat(root_fd).st_mode):
                raise OSError("sessions root is not a directory")
        finally:
            os.close(root_fd)
        current = home
        for component in sessions.relative_to(home).parts:
            current = current / component
            if current.is_symlink() or not current.is_dir():
                raise OSError("Codex sessions path contains a symlink or is not a directory")
    except (OSError, ValueError) as exc:
        return CollectionResult((), (Error("session_unsafe", "refusing unsafe Codex sessions directory", True, {"session_file": "sessions", "reason": str(exc)}),))
    if not sessions.is_dir():
        return CollectionResult((), (Error("sessions_missing", "Codex sessions directory not found", True, {"session_file": "sessions"}),))
    paths = sorted((p for p in sessions.glob("**/*.jsonl") if p.suffix == ".jsonl"), key=lambda p: p.relative_to(home).as_posix())
    root_fd = os.open(home, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    collected: list[tuple[Conversation, list[Error], str]] = []
    errors: list[Error] = []
    try:
      for path in paths:
        relative_path = path.relative_to(home).as_posix()
        try:
            descriptor = _open_relative(root_fd, relative_path)
            conversation, file_errors = _collect_file(path, relative_path, descriptor=descriptor)
            collected.append((conversation, file_errors, relative_path))
        except (OSError, ValueError) as exc:
            errors.append(Error("session_unsafe", f"refusing unsafe session file {relative_path}", True, {"session_file": relative_path, "reason": str(exc)}))
    finally:
        os.close(root_fd)
    base_counts: dict[str, int] = {}
    for conversation, _, _ in collected:
        base_counts[conversation.id] = base_counts.get(conversation.id, 0) + 1
    conversations: list[Conversation] = []
    for conversation, file_errors, relative_path in collected:
        if base_counts[conversation.id] > 1:
            digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
            original_id = conversation.id
            unique_id = f"codex-path-{digest}"
            conversation = replace(
                conversation,
                id=unique_id,
                entries=tuple(replace(entry, id=entry.id.replace(f"codex:{original_id}:", f"codex:{unique_id}:", 1)) for entry in conversation.entries),
            )
            file_errors.append(Error("conversation_id_collision", f"duplicate session id {original_id!r}; using deterministic id {unique_id!r}", True, {"session_file": relative_path, "original_id": original_id, "resolved_id": unique_id}))
        conversations.append(conversation)
        errors.extend(file_errors)
    unique_conversations: list[Conversation] = []
    used_ids: set[str] = set()
    for conversation in conversations:
        if conversation.id in used_ids:
            relative_path = str(conversation.metadata.get("session_file", conversation.id))
            ordinal = 2
            candidate = conversation.id
            while candidate in used_ids:
                digest = hashlib.sha256(f"{relative_path}\0{ordinal}".encode("utf-8")).hexdigest()
                candidate = f"codex-path-{digest}"
                ordinal += 1
            conversation = replace(conversation, id=candidate, entries=tuple(replace(entry, id=entry.id.replace(f"codex:{conversation.id}:", f"codex:{candidate}:", 1)) for entry in conversation.entries))
            errors.append(Error("conversation_id_collision", f"duplicate conversation ID; assigned deterministic path ID {candidate!r}", True, {"session_file": relative_path, "resolved_id": candidate}))
        used_ids.add(conversation.id)
        unique_conversations.append(conversation)
    final_ids = [conversation.id for conversation in unique_conversations]
    if len(final_ids) != len(set(final_ids)):
        errors.append(Error("conversation_id_collision_unresolved", "collector produced duplicate conversation IDs", False, {}))
    return CollectionResult(tuple(unique_conversations), tuple(errors))


collect_codex = collect_codex_sessions


class CodexCollector:
    """Small state-free adapter wrapper for callers preferring an object API."""

    def __init__(self, codex_home: str | Path | None = None, *, environ: Mapping[str, str] | None = None):
        self.codex_home = codex_home
        self.environ = environ

    def collect(self) -> CollectionResult:
        return collect_codex_sessions(self.codex_home, environ=self.environ)
