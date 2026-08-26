"""Bounded ChatGPT capture contract and ingestion.

The collector intentionally accepts one browser-produced capture at a time. It
does not log in, call ChatGPT APIs, or attempt to discover conversations.
"""

from __future__ import annotations

import json
import hashlib
import os
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from ..models import Attachment, Conversation, Entry, Error
from ..paths import ArchiveMode
from ..schema import CURRENT_SCHEMA_VERSION
from ..storage import atomic_write_json, read_json
from ..archive import export_archive, new_run_root, _archive_identity
from ..redaction import REDACTION_RULE_VERSION, RedactionReport, redact_value


class CaptureValidationError(ValueError):
    """The bounded browser capture does not satisfy the documented contract."""


CHECKPOINT_VERSION = 1


class CheckpointVersionError(ValueError):
    """Checkpoint was written by a newer incompatible exporter."""


@dataclass(frozen=True)
class IngestResult:
    output_path: Path
    skipped: bool = False
    errors: tuple[Error, ...] = ()
    conversation: Conversation | None = None
    checkpoint_artifacts: Mapping[str, Any] = field(default_factory=dict)


def _require_text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise CaptureValidationError(f"capture {field} must be a non-empty string")
    return value


def validate_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a shallow copy of the ChatGPT capture contract.

    Required top-level fields are ``id``, ``status``, ``source_url``, and
    ``messages``. Message and attachment text is already Markdown/plain text;
    no HTML or executable values are interpreted.
    """

    if not isinstance(capture, Mapping):
        raise CaptureValidationError("capture must be a JSON object")
    value = dict(capture)
    allowed_top_level = {"id", "title", "status", "source_url", "messages", "branches", "attachments", "errors", "complete", "expected_message_count", "expected_branch_count"}
    unknown_top_level = set(value) - allowed_top_level
    if unknown_top_level:
        raise CaptureValidationError(f"capture contains unknown fields: {sorted(unknown_top_level)}")
    conversation_id = _require_text(value.get("id"), "id")
    if conversation_id in {".", ".."} or "/" in conversation_id or "\\" in conversation_id:
        raise CaptureValidationError("capture id must be a single safe path segment")
    status = value.get("status")
    if status not in {"regular", "archived"}:
        raise CaptureValidationError("capture status must be regular or archived")
    source_url = _require_text(value.get("source_url"), "source_url")
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not (hostname == "chatgpt.com" or hostname.endswith(".chatgpt.com")):
        raise CaptureValidationError("capture source_url must be an official HTTPS ChatGPT URL")
    messages = value.get("messages")
    if not isinstance(messages, list):
        raise CaptureValidationError("capture messages must be an array")
    message_ids: set[str] = set()
    for index, message in enumerate(messages):
        if not isinstance(message, Mapping):
            raise CaptureValidationError(f"capture messages[{index}] must be an object")
        unknown_message = set(message) - {"id", "role", "content", "timestamp", "branch_id"}
        if unknown_message:
            raise CaptureValidationError(f"capture messages[{index}] contains unknown fields")
        role = message.get("role")
        if role not in {"user", "assistant", "tool"}:
            raise CaptureValidationError(f"capture messages[{index}].role is not visible")
        _require_text(message.get("content"), f"messages[{index}].content", allow_empty=True)
        if "id" in message:
            message_id = _require_text(message["id"], f"messages[{index}].id")
            if message_id in message_ids:
                raise CaptureValidationError(f"duplicate capture message id: {message_id}")
            message_ids.add(message_id)
        else:
            raise CaptureValidationError(f"capture messages[{index}].id must be a non-empty stable id")
        if "timestamp" in message and message["timestamp"] is not None and not isinstance(message["timestamp"], str):
            raise CaptureValidationError(f"capture messages[{index}].timestamp must be text or null")
        if "branch_id" in message and not isinstance(message["branch_id"], str):
            raise CaptureValidationError(f"capture messages[{index}].branch_id must be text")
    branches = value.get("branches", [])
    if not isinstance(branches, list):
        raise CaptureValidationError("capture branches must be an array")
    branch_ids: set[str] = set()
    for index, branch in enumerate(branches):
        if not isinstance(branch, Mapping) or not isinstance(branch.get("id"), str) or not branch.get("id"):
            raise CaptureValidationError(f"capture branches[{index}] must have an id")
        if set(branch) - {"id", "visible", "title"}:
            raise CaptureValidationError(f"capture branches[{index}] contains unknown fields")
        branch_id = branch["id"]
        if branch_id in branch_ids:
            raise CaptureValidationError(f"duplicate capture branch id: {branch_id}")
        branch_ids.add(branch_id)
        if "visible" in branch and not isinstance(branch["visible"], bool):
            raise CaptureValidationError(f"capture branches[{index}].visible must be boolean")
    for index, message in enumerate(messages):
        branch_id = message.get("branch_id")
        if branch_id is not None and branch_id not in branch_ids:
            raise CaptureValidationError(f"capture messages[{index}].branch_id does not reference a branch")
        if branch_id is not None:
            branch = next(item for item in branches if item["id"] == branch_id)
            if branch.get("visible") is not True:
                raise CaptureValidationError(f"capture messages[{index}].branch_id references a non-visible branch")
    attachments = value.get("attachments", [])
    if not isinstance(attachments, list):
        raise CaptureValidationError("capture attachments must be an array")
    for index, attachment in enumerate(attachments):
        if not isinstance(attachment, Mapping):
            raise CaptureValidationError(f"capture attachments[{index}] must be an object")
        if set(attachment) - {"id", "filename", "media_type", "url", "local_path", "downloaded_path", "size_bytes"}:
            raise CaptureValidationError(f"capture attachments[{index}] contains unknown fields")
        _require_text(attachment.get("filename", f"attachment-{index}"), f"attachments[{index}].filename", allow_empty=False)
        if "media_type" in attachment and not isinstance(attachment["media_type"], str):
            raise CaptureValidationError(f"capture attachments[{index}].media_type must be text")
        for key in ("local_path", "downloaded_path", "url"):
            if key in attachment and attachment[key] is not None and not isinstance(attachment[key], str):
                raise CaptureValidationError(f"capture attachments[{index}].{key} must be text")
    value.setdefault("title", "")
    value.setdefault("branches", [])
    value.setdefault("attachments", [])
    if "complete" not in value:
        raise CaptureValidationError("capture complete is required")
    complete = value["complete"]
    if not isinstance(complete, bool):
        raise CaptureValidationError("capture complete must be boolean")
    if complete and not messages:
        raise CaptureValidationError("complete capture must contain messages")
    for key, actual in (("expected_message_count", len(messages)), ("expected_branch_count", len(branches))):
        if key in value:
            expected = value[key]
            if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
                raise CaptureValidationError(f"capture {key} must be a non-negative integer")
            if complete and expected != actual:
                raise CaptureValidationError(f"capture {key} does not match captured records")
    value["complete"] = complete
    value["branches"] = [{key: branch[key] for key in ("id", "visible", "title") if key in branch} for branch in branches]
    capture_errors = value.get("errors", [])
    if not isinstance(capture_errors, list):
        raise CaptureValidationError("capture errors must be an array")
    for index, error in enumerate(capture_errors):
        if not isinstance(error, Mapping) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
            raise CaptureValidationError(f"capture errors[{index}] must contain code and message")
        if set(error) - {"code", "message", "recoverable", "details"}:
            raise CaptureValidationError(f"capture errors[{index}] contains unknown fields")
        if "recoverable" not in error or not isinstance(error["recoverable"], bool):
            raise CaptureValidationError(f"capture errors[{index}].recoverable must be boolean")
        if "details" in error and not isinstance(error["details"], Mapping):
            raise CaptureValidationError(f"capture errors[{index}].details must be an object")
    return value


def _safe_filename(filename: str, fallback: str) -> str:
    name = Path(filename).name
    if not name or name in {".", ".."}:
        name = fallback
    return name


def _safe_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix and len(suffix) <= 12 and suffix[1:].replace("_", "").isalnum():
        return suffix
    return ".bin"


def _capture_hash(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _checkpoint_records(path: Path) -> list[dict[str, Any]]:
    try:
        payload = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != CHECKPOINT_VERSION:
        raise CheckpointVersionError(f"unsupported checkpoint version {version!r}; expected {CHECKPOINT_VERSION}")
    records = payload.get("completed", [])
    if isinstance(records, list):
        safe_keys = {"conversation_id", "capture_sha256", "conversation_sha256", "mode", "schema_version", "redaction_rule_version", "status"}
        return [redact_value({key: item[key] for key in safe_keys if key in item}) for item in records if isinstance(item, Mapping)]
    # Read the original checkpoint shape, but it cannot authorize a skip
    # because it lacks content hash/path/mode/schema evidence.
    return []


def _write_checkpoint(path: Path, records: list[Mapping[str, Any]]) -> None:
    atomic_write_json(path, {"archive_version": 1, "schema_version": CURRENT_SCHEMA_VERSION, "version": CHECKPOINT_VERSION, "completed": [dict(item) for item in records]})


def _output_conversation_hash(path: Path, conversation_id: str) -> str | None:
    try:
        payload = read_json(path)
        if set(payload) != {"schema_version", "conversation", "checkpoints", "errors"} or payload.get("schema_version") != CURRENT_SCHEMA_VERSION:
            return None
        conversation = payload.get("conversation")
        expected_id = _archive_identity(conversation_id, RedactionReport())
        if not isinstance(conversation, Mapping) or conversation.get("id") != expected_id:
            return None
        canonical = json.dumps(conversation, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _archive_resume_integrity(output_path: Path) -> bool:
    """Require the complete archive artifact graph before checkpoint skip."""
    try:
        from ..archive import verify_archive
        return bool(verify_archive(output_path.parents[2]).get("valid"))
    except (OSError, ValueError, IndexError):
        return False


def _ensure_safe_directory(path: Path) -> None:
    """Create/check a directory without traversing a symlink component."""

    path = path.absolute()
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if current.exists() and current.is_symlink():
            # macOS exposes /var as the system /private/var alias. It is not
            # an archive-controlled component; continue checking below it.
            if current in {Path("/var"), Path("/tmp")} and current.resolve() == Path("/private") / current.name:
                current = current.resolve()
                continue
            raise OSError(f"refusing symlink path component: {current}")
        if not current.exists():
            current.mkdir()
        if not current.is_dir():
            raise OSError(f"path component is not a directory: {current}")


def _approved_source(source: str | Path, download_root: str | Path | None) -> Path | None:
    if not download_root:
        return None
    root = Path(download_root)
    if root.is_symlink():
        raise OSError("download root may not be a symlink")
    root = root.resolve()
    candidate = Path(source)
    lexical = candidate.absolute()
    current = Path(lexical.anchor)
    for component in lexical.parts[1:]:
        current /= component
        if current.exists() and current.is_symlink():
            if current in {Path("/var"), Path("/tmp")} and current.resolve() == Path("/private") / current.name:
                current = current.resolve()
                continue
            raise OSError("attachment source path may not contain symlinks")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        raise OSError("attachment source is outside approved download root")
    info = resolved.stat()
    if not stat.S_ISREG(info.st_mode):
        raise OSError("attachment source is not a regular file")
    if info.st_nlink != 1:
        raise OSError("attachment source may not be a hardlink")
    return resolved


def _copy_attachment_safely(source: Path, destination_dir: Path, extension: str) -> tuple[str, Path]:
    """Stream a regular file into an exclusive random temp then replace atomically."""

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    temporary: Path | None = None
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_nlink != 1:
            raise OSError("attachment source changed to a non-regular or hardlinked file")
        source_hash = hashlib.sha256()
        _ensure_safe_directory(destination_dir)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        for _ in range(20):
            candidate = destination_dir / f".{secrets.token_hex(16)}.tmp"
            try:
                temp_fd = os.open(candidate, flags, 0o600)
                temporary = candidate
                break
            except FileExistsError:
                continue
        else:
            raise OSError("could not create exclusive attachment temporary")
        with os.fdopen(temp_fd, "wb") as target:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                source_hash.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        digest = source_hash.hexdigest()
        destination = destination_dir / f"{digest}{extension}"
        if os.path.lexists(destination):
            destination_stat = destination.lstat()
            if stat.S_ISLNK(destination_stat.st_mode) or destination_stat.st_nlink != 1:
                raise OSError("attachment destination may not be a symlink or hardlink")
        os.replace(temporary, destination)
        temporary = None
        return digest, destination
    finally:
        os.close(source_fd)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def ingest_capture(
    capture: Mapping[str, Any] | str | Path,
    output: str | Path,
    *,
    mode: ArchiveMode | str = ArchiveMode.INCREMENTAL,
    checkpoint_path: str | Path | None = None,
    download_root: str | Path | None = None,
    run_root: str | Path | None = None,
    finalize: bool = True,
) -> IngestResult:
    """Ingest one validated capture, copying only attachments already local."""

    if isinstance(capture, (str, Path)):
        with Path(capture).open("r", encoding="utf-8") as stream:
            capture = json.load(stream)
    value = validate_capture(capture)
    output_root = Path(output)
    _ensure_safe_directory(output_root)
    conversation_id = value["id"]
    archive_mode = ArchiveMode.coerce(mode)
    selected_run_root = Path(run_root) if run_root is not None else None
    if archive_mode is ArchiveMode.SNAPSHOT and selected_run_root is None and finalize:
        selected_run_root = new_run_root(output_root, mode=archive_mode)
    # Checkpoints are archive artifacts, published transactionally with the
    # conversation.  ``checkpoint_path`` is retained for API compatibility but
    # is intentionally ignored so external files cannot authorize a skip.
    checkpoint = (selected_run_root or output_root) / "checkpoints" / "chatgpt.json"
    checkpoint_records = _checkpoint_records(checkpoint)
    # Final archives use one source-partitioned stable path. Resolve it before
    # checking the resumable checkpoint so stale/older layouts cannot skip.
    archive_root = selected_run_root if selected_run_root is not None else output_root
    if selected_run_root is None and archive_mode is ArchiveMode.SNAPSHOT:
        # Snapshot path is selected by export_archive; this pre-check is only
        # for incremental checkpoints and must never point at a date-only dir.
        archive_root = output_root / "snapshots"
    archive_id = _archive_identity(conversation_id, RedactionReport())
    output_path = archive_root / "conversations" / "chatgpt" / f"{archive_id}.json"
    if run_root is not None or archive_mode is ArchiveMode.INCREMENTAL:
        _ensure_safe_directory(output_path.parent)
    if output_path.exists() and output_path.is_symlink():
        raise OSError("archive destination may not be a symlink")
    capture_hash = _capture_hash(value)
    expected = {"conversation_id": conversation_id, "capture_sha256": capture_hash, "mode": archive_mode.value, "schema_version": CURRENT_SCHEMA_VERSION, "redaction_rule_version": REDACTION_RULE_VERSION, "status": "complete"}
    safe_expected = redact_value(expected)
    if output_path.is_file():
        output_hash = _output_conversation_hash(output_path, conversation_id)
        if output_hash and _archive_resume_integrity(output_path) and any(all(record.get(key) == safe_expected[key] for key in safe_expected) for record in checkpoint_records):
            return IngestResult(output_path=output_path, skipped=True)

    errors: list[Error] = []
    archive_attachments: list[Attachment] = []
    for index, item in enumerate(value["attachments"]):
        filename = _safe_filename(str(item.get("filename", item.get("name", ""))), f"attachment-{index}")
        media_type = str(item.get("media_type", item.get("mime_type", "application/octet-stream")))
        metadata = {k: v for k, v in item.items() if k not in {"id", "filename", "name", "media_type", "mime_type", "local_path", "downloaded_path"}}
        source_path = item.get("local_path") or item.get("downloaded_path")
        if source_path:
            try:
                approved_source = _approved_source(source_path, download_root)
                if approved_source is None:
                    raise OSError("no approved download root configured")
                # Leave materialization and redaction to the archive writer;
                # this path is only an approved, validated source reference.
                metadata["copied_from"] = "local_download"
                uri = str(approved_source)
            except OSError as exc:
                uri = None
                metadata["failure_reason"] = f"copy failed: {exc}"
                errors.append(Error("attachment_unavailable", f"Attachment {filename} copy failed: {exc}", True, {"attachment_id": item.get("id", ""), "filename": filename}))
        else:
            uri = item.get("url")
            metadata["failure_reason"] = "not downloaded locally; remote download is outside bounded ingestion"
            errors.append(Error("attachment_unavailable", f"Attachment {filename} not downloaded locally", True, {"attachment_id": item.get("id", ""), "filename": filename}))
        archive_attachments.append(Attachment(str(item.get("id", f"attachment-{index}")), filename, media_type, uri, item.get("size_bytes"), metadata))

    entries = tuple(
        Entry(
            id=str(message["id"]),
            role=str(message["role"]),
            content=str(message["content"]),
            created_at=message.get("timestamp"),
            attachments=(),
            metadata={"branch_id": message.get("branch_id")} if message.get("branch_id") is not None else {},
        )
        for index, message in enumerate(value["messages"])
    )
    timestamps = [entry.created_at for entry in entries if entry.created_at]
    conversation = Conversation(
        id=conversation_id,
        title=str(value.get("title", "")),
        source="chatgpt",
        created_at=timestamps[0] if timestamps else None,
        updated_at=timestamps[-1] if timestamps else None,
        entries=entries,
        attachments=tuple(archive_attachments),
        metadata={"status": value["status"], "source_url": value["source_url"], "branches": value["branches"]},
    )
    capture_errors = [Error(str(item.get("code")), str(item.get("message")), bool(item.get("recoverable", True)), dict(item.get("details", {}))) for item in value.get("errors", [])]
    all_errors = [*errors, *capture_errors]
    if not value["complete"]:
        all_errors.append(Error("capture_incomplete", "capture explicitly marked incomplete", True, {"conversation_id": conversation_id}))
    status = "complete" if value.get("complete", True) and not all_errors else "incomplete"
    merged_records = [record for record in checkpoint_records if isinstance(record, Mapping) and record.get("status") == "complete"]
    if not all_errors and value["complete"]:
        merged_records = [record for record in merged_records if record.get("conversation_id") != safe_expected.get("conversation_id")]
        merged_records.append(safe_expected)
    checkpoint_artifacts = {"chatgpt.json": {"archive_version": 1, "schema_version": CURRENT_SCHEMA_VERSION, "version": CHECKPOINT_VERSION, "completed": merged_records}} if not all_errors and value["complete"] else {}
    if finalize:
        archive_result = export_archive(output_root, [conversation], mode=archive_mode, run_root=selected_run_root, approved_root=download_root, checkpoints=[{"name": "chatgpt_capture", "status": status, "conversation_id": conversation_id}], checkpoint_artifacts=checkpoint_artifacts, errors_by_conversation={f"chatgpt:{conversation_id}": all_errors})
        output_path = Path(archive_result["archive_path"]) / "conversations" / "chatgpt" / f"{archive_id}.json"
    # The checkpoint artifact was supplied to export_archive above and is
    # already included in the published manifest; no post-publication
    # mutation is permitted.
    return IngestResult(output_path=output_path, errors=tuple(all_errors), conversation=conversation, checkpoint_artifacts=checkpoint_artifacts)


ingest_chatgpt_capture = ingest_capture


class ChatGPTCollector:
    """Object wrapper around one-capture ingestion; no browser state is retained."""

    def __init__(self, output: str | Path, *, mode: ArchiveMode | str = ArchiveMode.INCREMENTAL, checkpoint_path: str | Path | None = None, download_root: str | Path | None = None):
        self.output = output
        self.mode = mode
        self.checkpoint_path = checkpoint_path
        self.download_root = download_root

    def ingest(self, capture: Mapping[str, Any] | str | Path) -> IngestResult:
        return ingest_capture(capture, self.output, mode=self.mode, checkpoint_path=self.checkpoint_path, download_root=self.download_root)
