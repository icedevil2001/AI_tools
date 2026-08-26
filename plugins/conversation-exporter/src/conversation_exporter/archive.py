"""Atomic archive assembly, indexing, and verification."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import secrets
import shutil
import stat
import re
from collections import Counter
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import Attachment, Conversation, Entry, Error
from .paths import ArchiveMode
from .redaction import RedactionReport, redact_conversation, redact_errors, redact_text, redact_value
from .rendering import _render_json_raw, _render_markdown_raw
from .schema import CURRENT_SCHEMA_VERSION, SchemaVersionError
from .storage import atomic_write_json, atomic_write_text, read_json

ARCHIVE_VERSION = 1


class ArchiveVersionError(ValueError):
    """An existing archive was created by a newer incompatible writer."""


def _lock_path(root: Path, mode: ArchiveMode | str) -> Path:
    """Return a lock outside the published tree so directory swaps stay locked."""
    return root.parent / f".{root.name}.archive.lock"


def _safe_segment(value: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"unsafe archive path segment: {value!r}")
    return value


def _archive_identity(identifier: str, report: RedactionReport) -> str:
    """Return a stable filename-safe ID without placing a credential in paths."""

    safe, _ = redact_text(identifier, report)
    if safe != identifier:
        return "id-" + hashlib.sha256(identifier.encode("utf-8", "surrogatepass")).hexdigest()[:24]
    return identifier


def _canonical_identifier(identifier: str, kind: str, report: RedactionReport) -> str:
    """Keep ordinary IDs readable while preventing secrets/path syntax in data."""

    safe, _ = redact_text(identifier, report)
    if safe != identifier or not identifier or identifier in {".", ".."} or "/" in identifier or "\\" in identifier:
        report.add("identifier")
        return f"{kind}-id-{hashlib.sha256(identifier.encode('utf-8', 'surrogatepass')).hexdigest()[:24]}"
    return identifier


def _canonicalize_conversation(conversation: Conversation, report: RedactionReport) -> Conversation:
    def attachment(item: Attachment) -> Attachment:
        return replace(item, id=_canonical_identifier(item.id, "attachment", report))
    entries = tuple(replace(item, id=_canonical_identifier(item.id, "entry", report), attachments=tuple(attachment(a) for a in item.attachments)) for item in conversation.entries)
    return replace(conversation, entries=entries, attachments=tuple(attachment(a) for a in conversation.attachments))


def _canonicalize_errors(errors: list[Error], report: RedactionReport) -> list[Error]:
    return [replace(item, code=_canonical_identifier(item.code, "error", report)) for item in errors]


def _extension(filename: str, media_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix and len(suffix) <= 12 and suffix[1:].replace("_", "").isalnum():
        return suffix
    return mimetypes.guess_extension(media_type) or ".bin"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_attachment_once(source: Path, root: Path, approved_roots: Iterable[Path] = ()) -> bytes:
    """Open through a verified root descriptor, then read that descriptor.

    In particular, do not validate an absolute pathname and subsequently open
    that pathname: the path can be swapped between those operations.  The
    relative walk below makes root membership part of the open operation.
    """
    roots = [root, *list(approved_roots)]
    source_real = source.resolve(strict=False)
    membership: tuple[Path, Path] | None = None
    for allowed in roots:
        allowed_real = allowed.resolve(strict=False)
        if _is_beneath(source_real, allowed_real):
            membership = (allowed, source_real.relative_to(allowed_real))
            break
    if membership is None or not membership[1].parts:
        raise OSError("attachment descriptor membership could not be established")
    parent, relative = membership
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.open(parent, flags | getattr(os, "O_DIRECTORY", 0))
    except (OSError, TypeError) as exc:
        raise OSError("attachment descriptor membership could not be established") from exc
    fd = root_fd
    try:
        for component in relative.parts:
            try:
                next_fd = os.open(component, flags, dir_fd=fd)
            except (OSError, TypeError) as exc:
                raise OSError("attachment descriptor membership could not be established") from exc
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OSError("attachment source is not a unique regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def _conversation_files_valid(root: Path, item: Mapping[str, Any]) -> bool:
    """Check the files represented by one index item before incremental skip."""

    try:
        json_path = root / str(item["json"])
        markdown_path = root / str(item["markdown"])
        json_path.resolve().relative_to(root.resolve())
        markdown_path.resolve().relative_to(root.resolve())
        envelope = read_json(json_path)
        if set(envelope) != {"schema_version", "conversation", "checkpoints", "errors"} or envelope.get("schema_version") != CURRENT_SCHEMA_VERSION:
            return False
        conversation = envelope["conversation"]
        digest = _sha256_bytes(json.dumps(conversation, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
        if digest != item.get("content_sha256") or not markdown_path.is_file():
            return False
        return isinstance(item.get("markdown_sha256"), str) and _sha256_file(markdown_path) == item["markdown_sha256"]
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _is_text_attachment(attachment: Attachment) -> bool:
    if attachment.media_type.lower().startswith("text/"):
        return True
    name = Path(attachment.filename).name.lower()
    return name in {".env", "readme", "license", "makefile", "dockerfile"} or Path(name).suffix in {
        ".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".xml", ".html", ".htm", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".config", ".properties", ".rst", ".tex", ".log", ".py", ".js", ".ts", ".sh", ".pem", ".key"
    }


def _ensure_safe_directory(path: Path) -> None:
    """Create a directory graph without traversing attacker-controlled links."""

    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.exists() and current.is_symlink():
            # macOS commonly exposes /var as an alias for /private/var.
            if current in {Path("/var"), Path("/tmp")} and current.resolve() == Path("/private") / current.name:
                current = current.resolve()
                continue
            raise OSError(f"refusing symlink path component: {current}")
        if current.exists() and not current.is_dir():
            raise OSError(f"path component is not a directory: {current}")
        if not current.exists():
            try:
                current.mkdir()
            except FileExistsError:
                # Another snapshot allocator may have created this ordinary
                # directory between the existence check and mkdir.
                if current.is_symlink() or not current.is_dir():
                    raise OSError(f"path component is not a directory: {current}")


def _reject_symlink_components(path: Path) -> None:
    """Validate an existing path graph without creating anything."""

    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.exists() and current.is_symlink():
            if current in {Path("/var"), Path("/tmp")} and current.resolve() == Path("/private") / current.name:
                current = current.resolve()
                continue
            raise OSError(f"refusing symlink path component: {current}")


def _validate_archive_tree(root: Path) -> None:
    """Reject links in an existing archive before it is used as a stage base."""

    for directory, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            candidate = Path(directory) / name
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise OSError(f"archive tree contains a symlink: {candidate}")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise OSError(f"archive tree contains a hardlink: {candidate}")


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    _ensure_safe_directory(path.parent)
    if os.path.lexists(path):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
            raise OSError(f"refusing unsafe archive destination: {path}")
    temporary: Path | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        for _ in range(20):
            candidate = path.parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
            try:
                fd = os.open(candidate, flags, 0o600)
                temporary = candidate
                break
            except FileExistsError:
                continue
        else:
            raise OSError("could not create exclusive archive temporary")
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _attachment_source(uri: str, root: Path, approved_root: Path | Iterable[Path] | None, *, require_approved: bool = False) -> Path | None:
    # URLs and other remote references are retained as unscanned metadata.
    if "://" in uri:
        return None
    candidate = Path(uri)
    originally_absolute = candidate.is_absolute()
    lexical = candidate.absolute()
    current = Path(lexical.anchor)
    for component in lexical.parts[1:]:
        current /= component
        if current.exists() and current.is_symlink():
            if current in {Path("/var"), Path("/tmp")} and current.resolve() == Path("/private") / current.name:
                current = current.resolve()
                continue
            raise ValueError("attachment source path may not contain symlinks")
    if not candidate.is_absolute():
        if require_approved:
            raise ValueError("relative attachment source requires approved_root")
        candidate = (root / candidate).resolve(strict=False)
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError("relative attachment source escapes archive root") from exc
    else:
        candidate = candidate.resolve(strict=False)
    if originally_absolute and approved_root is not None:
        approved_values = [approved_root] if isinstance(approved_root, Path) else list(approved_root)
        if not any(_is_beneath(candidate, item.resolve()) for item in approved_values):
            # Existing archive assets are also safe, since they are already
            # inside the destination root and never escape it.
            if not _is_beneath(candidate, root.resolve()):
                raise ValueError("attachment source is outside approved root")
    elif originally_absolute:
        raise ValueError("absolute attachment source requires approved_root")
    if not candidate.is_file() or candidate.is_symlink():
        return None
    info = candidate.stat()
    if info.st_nlink != 1:
        raise ValueError("attachment source may not be hardlinked")
    return candidate


def _is_beneath(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _materialize_attachments(conversation: Conversation, archive_root: Path, report: RedactionReport, approved_root: Path | Iterable[Path] | None = None) -> tuple[Conversation, list[Error]]:
    errors: list[Error] = []
    asset_dir = archive_root / "assets" / _safe_segment(conversation.id)
    def materialize(attachment: Attachment) -> Attachment:
        metadata = dict(attachment.metadata)
        uri = attachment.uri
        try:
            require_approved = conversation.source == "codex" and metadata.get("provenance") == "codex" and isinstance(uri, str) and "://" not in uri
            source = _attachment_source(uri, archive_root, approved_root, require_approved=require_approved) if isinstance(uri, str) else None
        except ValueError as exc:
            # A caller that supplied provenance gets a recoverable per-file
            # failure; missing provenance remains a hard rejection so raw
            # absolute paths can never silently enter an archive.
            if conversation.source != "codex" and "requires approved_root" in str(exc):
                raise
            metadata["failure_reason"] = str(exc)
            errors.append(Error("attachment_unavailable", f"Attachment {attachment.filename} unavailable: {exc}", True, {"attachment_id": attachment.id, "filename": attachment.filename}))
            return Attachment(attachment.id, attachment.filename, attachment.media_type, None, attachment.size_bytes, metadata)
        if source is None:
            if uri and (uri.startswith("assets/") or "://" in uri):
                metadata.setdefault("scan_status", "unscanned")
                metadata.setdefault("scanned", False)
                return Attachment(attachment.id, attachment.filename, attachment.media_type, uri, attachment.size_bytes, metadata)
            if not uri:
                metadata.setdefault("scan_status", "unscanned")
            return Attachment(attachment.id, attachment.filename, attachment.media_type, uri, attachment.size_bytes, metadata)
        try:
            approved_values = [approved_root] if isinstance(approved_root, Path) else list(approved_root or ())
            raw = _read_attachment_once(source, archive_root, approved_values)
            known_text = _is_text_attachment(attachment)
            # Unknown extensions are text unless there is affirmative binary
            # evidence (NUL/control bytes or invalid UTF-8). This catches
            # extensionless exported notes while preserving actual binaries.
            if known_text or (b"\x00" not in raw and len(raw) <= 8 * 1024 * 1024):
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    metadata["scan_status"] = "unscanned"
                    metadata["scanned"] = False
                else:
                    control_count = sum(1 for ch in text if ord(ch) < 32 and ch not in "\t\n\r\f")
                    sniffed_text = known_text or control_count == 0
                    if sniffed_text:
                        clean, _ = redact_text(text, report)
                        raw = clean.encode("utf-8")
                        metadata["scan_status"] = "scanned"
                        metadata["scanned"] = True
                    else:
                        metadata["scan_status"] = "unscanned"
                        metadata["scanned"] = False
            else:
                metadata["scan_status"] = "unscanned"
                metadata["scanned"] = False
            digest = hashlib.sha256(raw).hexdigest()
            _ensure_safe_directory(asset_dir)
            destination = asset_dir / f"{digest}{_extension(attachment.filename, attachment.media_type)}"
            if os.path.lexists(destination):
                info = destination.lstat()
                if stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
                    raise OSError("attachment destination may not be a symlink or hardlink")
            if not destination.exists():
                _atomic_write_bytes(destination, raw)
            uri = f"assets/{conversation.id}/{destination.name}"
            metadata["content_sha256"] = digest
            return Attachment(attachment.id, attachment.filename, attachment.media_type, uri, len(raw), metadata)
        except OSError as exc:
            metadata["failure_reason"] = str(exc)
            errors.append(Error("attachment_unavailable", f"Attachment {attachment.filename} unavailable: {exc}", True, {"attachment_id": attachment.id, "filename": attachment.filename}))
            return Attachment(attachment.id, attachment.filename, attachment.media_type, None, attachment.size_bytes, metadata)
    conversation_attachments = tuple(materialize(item) for item in conversation.attachments)
    entries = tuple(Entry(entry.id, entry.role, entry.content, entry.created_at, tuple(materialize(item) for item in entry.attachments), entry.metadata) for entry in conversation.entries)
    return Conversation(
        conversation.id, conversation.title, conversation.source, conversation.created_at,
        conversation.updated_at, entries, conversation_attachments, conversation.metadata,
    ), errors


def _root_for_mode(output: Path, mode: ArchiveMode | str, timestamp: datetime | None, *, reserve: bool = False) -> Path:
    archive_mode = ArchiveMode.coerce(mode)
    if archive_mode is ArchiveMode.INCREMENTAL:
        return output
    moment = timestamp or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    base = output / "snapshots" / moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    if reserve:
        _ensure_safe_directory(base.parent)
    candidate = base
    suffix = 2
    while True:
        if candidate.is_symlink():
            raise OSError(f"snapshot candidate is a symlink: {candidate}")
        if candidate.exists():
            candidate = base.with_name(f"{base.name}-{suffix}")
            suffix += 1
            continue
        if reserve:
            # Reserve the name without creating the final directory.  The
            # marker closes the race with another caller while allowing the
            # completed staging directory to be published with rename.
            marker = candidate.parent / f".{candidate.name}.reserve"
            try:
                fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                candidate = base.with_name(f"{base.name}-{suffix}")
                suffix += 1
                continue
            else:
                os.close(fd)
        return candidate


def new_run_root(output: str | Path, *, mode: ArchiveMode | str = ArchiveMode.SNAPSHOT, timestamp: datetime | None = None) -> Path:
    """Reserve the root for one export run (shared by ``source=all``)."""
    return _root_for_mode(Path(output), mode, timestamp, reserve=True)


_TRANSACTION_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_TRANSACTION_OWNER = re.compile(r"^[0-9a-f]{16}$")
_GENERATED_TREE = re.compile(r"^\.archive\.(backup|stage)-([0-9a-f]{16})-([0-9a-f]{32})$")


def _transaction_owner(parent: Path, stem: str) -> str:
    target = (Path(parent) / stem).resolve()
    return hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:16]


def _validate_transaction_path(path: Path, parent: Path, *, stem: str, kind: str, expected_owner: str | None = None, allow_existing: bool = False) -> None:
    """Validate a transaction path before it participates in a rename."""

    path = Path(path)
    parent = Path(parent)
    if path.parent != parent:
        raise OSError(f"transaction path is not a direct child of its parent: {path}")
    if kind in {"staging", "backup"}:
        generated_kind = "stage" if kind == "staging" else kind
        if expected_owner is None or not _TRANSACTION_OWNER.fullmatch(expected_owner):
            raise OSError("transaction owner is invalid")
        prefix = f".archive.{generated_kind}-{expected_owner}-"
        tail = path.name[len(prefix):] if path.name.startswith(prefix) else ""
        if not _TRANSACTION_TOKEN.fullmatch(tail):
            raise OSError(f"transaction {kind} name was not generated internally: {path.name}")
    elif path.name != stem:
        raise OSError(f"transaction final name is invalid: {path.name}")
    if path.is_symlink():
        raise OSError(f"transaction path may not be a symlink: {path}")
    if not allow_existing and os.path.lexists(path):
        raise OSError(f"transaction destination already exists: {path}")


def _new_transaction_directory(parent: Path, stem: str, kind: str, expected_owner: str) -> Path:
    _ensure_safe_directory(parent)
    while True:
        generated_kind = "stage" if kind == "staging" else kind
        candidate = parent / f".archive.{generated_kind}-{expected_owner}-{secrets.token_hex(16)}"
        _validate_transaction_path(candidate, parent, stem=stem, kind=kind, expected_owner=expected_owner)
        try:
            os.mkdir(candidate)
        except FileExistsError:
            continue
        _validate_transaction_path(candidate, parent, stem=stem, kind=kind, expected_owner=expected_owner, allow_existing=True)
        return candidate


def _new_transaction_path(parent: Path, stem: str, kind: str, expected_owner: str) -> Path:
    """Choose an unused internally generated sibling path without creating it."""

    _ensure_safe_directory(parent)
    while True:
        candidate = parent / f".archive.{kind}-{expected_owner}-{secrets.token_hex(16)}"
        try:
            _validate_transaction_path(candidate, parent, stem=stem, kind=kind, expected_owner=expected_owner)
        except OSError as exc:
            if os.path.lexists(candidate):
                if candidate.is_symlink():
                    raise
                continue
            raise exc
        return candidate


def safe_remove_generated_tree(path: str | Path, expected_parent: str | Path, marker: str, expected_owner: str | None = None) -> None:
    """Remove one generated transaction tree after a complete safety preflight.

    ``marker`` is either ``backup`` or ``stage``.  No caller-provided path is
    accepted beyond the exact generated basename and direct-parent checks.
    """

    candidate = Path(path)
    parent = Path(expected_parent)
    if candidate.parent != parent or candidate.resolve().parent != parent.resolve():
        raise OSError(f"generated tree is not a direct child of its expected parent: {candidate}")
    match = _GENERATED_TREE.fullmatch(candidate.name)
    if marker not in {"backup", "stage"} or match is None or match.group(1) != marker:
        raise OSError(f"refusing non-generated transaction tree: {candidate}")
    if expected_owner is None or not _TRANSACTION_OWNER.fullmatch(expected_owner) or match.group(2) != expected_owner:
        raise OSError("generated tree owner does not match expected archive")
    info = candidate.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise OSError(f"generated tree is not a real directory: {candidate}")
    for directory, directories, files in os.walk(candidate, followlinks=False):
        for name in (*directories, *files):
            child = Path(directory) / name
            child_info = child.lstat()
            if stat.S_ISLNK(child_info.st_mode):
                raise OSError(f"generated tree contains a symlink: {child}")
            if stat.S_ISREG(child_info.st_mode) and child_info.st_nlink != 1:
                raise OSError(f"generated tree contains a hardlink: {child}")
    shutil.rmtree(candidate)


def _copy_archive_base(source: Path, destination: Path) -> None:
    """Copy a validated archive into a stage without following links."""

    if not source.exists():
        return
    _validate_archive_tree(source)
    shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)
    _validate_archive_tree(destination)


def _existing_manifest(root: Path) -> dict[str, Any] | None:
    path = root / "manifest.json"
    if not path.exists():
        return None
    payload = read_json(path)
    archive_version = payload.get("archive_version")
    if isinstance(archive_version, bool) or not isinstance(archive_version, int) or archive_version != ARCHIVE_VERSION:
        raise ArchiveVersionError(f"unsupported archive version {archive_version!r}; expected {ARCHIVE_VERSION}")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != CURRENT_SCHEMA_VERSION:
        raise SchemaVersionError(f"unsupported schema version {schema_version!r}; expected {CURRENT_SCHEMA_VERSION}")
    return payload


def _export_archive_impl(
    output: str | Path,
    conversations: Iterable[Conversation],
    *,
    mode: ArchiveMode | str = ArchiveMode.INCREMENTAL,
    errors: Iterable[Error | Mapping[str, Any]] = (),
    errors_by_conversation: Mapping[str, Iterable[Error | Mapping[str, Any]]] | None = None,
    checkpoints: Iterable[Mapping[str, Any]] = (),
    checkpoint_artifacts: Mapping[str, bytes | Mapping[str, Any]] | None = None,
    timestamp: datetime | None = None,
    run_root: str | Path | None = None,
    approved_root: str | Path | None = None,
    approved_roots: Mapping[str, Iterable[str | Path]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write one complete archive and return a deterministic summary."""
    output_path = Path(output)
    conversations = list(conversations)
    checkpoints = list(checkpoints)
    # Sanitize checkpoint artifact mappings before they enter any durable
    # writer. Bytes are opaque and remain unchanged; JSON-like records are
    # copied so callers' mutable objects are never persisted by reference.
    safe_checkpoint_artifacts: dict[str, bytes | Mapping[str, Any]] = {}
    safe_checkpoint_reports: dict[str, RedactionReport] = {}
    for name, item in (checkpoint_artifacts or {}).items():
        if isinstance(item, Mapping):
            artifact_report = RedactionReport()
            safe_checkpoint_artifacts[str(name)] = redact_value(dict(item), artifact_report)
            safe_checkpoint_reports[str(name)] = artifact_report
        else:
            safe_checkpoint_artifacts[str(name)] = item
    checkpoint_artifacts = safe_checkpoint_artifacts
    if run_root is not None:
        root = Path(run_root)
        if ArchiveMode.coerce(mode) is ArchiveMode.SNAPSHOT:
            try:
                root.resolve().relative_to((output_path / "snapshots").resolve())
            except ValueError as exc:
                raise ValueError("snapshot run_root must be below output/snapshots") from exc
    else:
        root = _root_for_mode(output_path, mode, timestamp, reserve=not dry_run)
    existing = _existing_manifest(root) if root.exists() else None
    # ``approved_root`` is retained for callers of the old single-source API.
    roots: dict[str, list[Path]] = {}
    if approved_roots:
        for source_name, values in approved_roots.items():
            for value in values:
                roots.setdefault(str(source_name), []).append(Path(value))
    if approved_root is not None:
        roots.setdefault("*", []).append(Path(approved_root))
    for approved_group in roots.values():
        for approved_input in approved_group:
            try:
                _reject_symlink_components(approved_input)
            except OSError as exc:
                raise ValueError("approved attachment root may not contain symlinks") from exc
            approved = approved_input.resolve()
            if not approved.is_dir():
                raise ValueError("approved attachment root must be an existing directory")
            _ensure_safe_directory(approved)
    if not dry_run:
        _ensure_safe_directory(root)
    errors = list(errors)
    all_errors = [item if isinstance(item, Error) else Error.from_dict(item) for item in errors]
    scoped_errors = errors_by_conversation or {}
    report = RedactionReport()
    current_conversation_keys = {f"{item.source}:{item.id}" for item in conversations}
    prior_redaction_counts: Mapping[str, Any] = {}
    prior_redaction_by_conversation: Mapping[str, Any] = {}
    prior_global_counts: Mapping[str, Any] = {}
    prior_global_artifacts: Mapping[str, Any] = {}
    if existing:
        prior_redaction = (existing.get("redaction") or {}).get("counts", {})
        if isinstance(prior_redaction, Mapping):
            prior_redaction_counts = prior_redaction
        prior_map = (existing.get("redaction") or {}).get("by_conversation", {})
        if isinstance(prior_map, Mapping):
            prior_redaction_by_conversation = prior_map
        previous_global = (existing.get("redaction") or {}).get("global_counts", {})
        if isinstance(previous_global, Mapping):
            prior_global_counts = previous_global
        previous_artifacts = (existing.get("redaction") or {}).get("global_artifacts", {})
        if isinstance(previous_artifacts, Mapping):
            prior_global_artifacts = previous_artifacts
        # A refresh must retain prior diagnostics, including diagnostics for
        # conversations not present in this source batch.  Re-sanitize before
        # writing in case an older archive predates the redaction pass.
        try:
            previous_errors_payload = read_json(root / "errors.json")
            previous_errors = [Error.from_dict(item) for item in previous_errors_payload.get("errors", []) if isinstance(item, Mapping)]
            retained_errors = []
            for previous_error in previous_errors:
                previous_key = dict(previous_error.details).get("conversation_key")
                # A successful refresh supersedes the old diagnostics for
                # that conversation; a failed refresh contributes its current
                # diagnostics below. Unscoped and untouched-source errors are
                # retained for auditability.
                if previous_key in current_conversation_keys:
                    continue
                retained_errors.append(previous_error)
            all_errors.extend(redact_errors(retained_errors, report))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    clean_checkpoints = [redact_value(dict(item), report) for item in checkpoints]
    # Count global durable values independently.  A shared report cannot
    # distinguish two errors using the same rule, and would count an unchanged
    # retry again.  Positional identities are stable within the global error
    # and export checkpoint artifacts; replacement at that position replaces
    # its contribution.
    global_artifacts: dict[str, dict[str, int]] = {}
    for item in errors:
        value = item.to_dict() if isinstance(item, Error) else dict(item)
        local_report = RedactionReport()
        safe_value = redact_value(value, local_report)
        identity = hashlib.sha256(("error:" + json.dumps(safe_value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))).encode("utf-8")).hexdigest()[:32]
        global_artifacts[f"error:{identity}"] = dict(local_report.counts)
    for item in checkpoints:
        local_report = RedactionReport()
        safe_value = redact_value(dict(item), local_report)
        identity = hashlib.sha256(("checkpoint:" + json.dumps(safe_value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))).encode("utf-8")).hexdigest()[:32]
        global_artifacts[f"checkpoint:{identity}"] = dict(local_report.counts)
    for name, item in (checkpoint_artifacts or {}).items():
        if isinstance(item, Mapping):
            safe_value = safe_checkpoint_artifacts[str(name)]
            local_report = safe_checkpoint_reports[str(name)]
            identity = hashlib.sha256(json.dumps(safe_value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]
            global_artifacts[f"checkpoint:{name}:{identity}"] = dict(local_report.counts)
    redacted: list[tuple[Conversation, list[Error], str, str]] = []
    redaction_by_conversation: dict[str, dict[str, int]] = {}
    for original in conversations:
        # Preserve the source URI only in memory while provenance is checked
        # and the attachment is copied.  Redaction happens before the model is
        # hashed or persisted, but must not corrupt a source path containing a
        # credential-like segment.
        report_before = Counter(report.counts)
        original_id = original.id
        archive_id = _archive_identity(original_id, report)
        prepared = original
        if archive_id != original_id:
            metadata = dict(original.metadata)
            metadata["source_id"] = redact_text(original_id, report)[0]
            prepared = replace(original, id=archive_id, metadata=metadata)
        source_approved = roots.get(prepared.source, roots.get("*"))
        if source_approved is not None:
            # Keep the verified root descriptors' original paths.  The read
            # path is opened relative to these roots; resolving them here
            # would turn provenance into a path-only check.
            source_approved = list(source_approved)
        prepared, attachment_errors = (prepared, []) if dry_run else _materialize_attachments(prepared, root, report, source_approved)
        clean = redact_conversation(prepared, report)
        clean = _canonicalize_conversation(clean, report)
        scoped_records = scoped_errors.get(f"{original.source}:{original.id}", ())
        scoped = [item if isinstance(item, Error) else Error.from_dict(item) for item in scoped_records]
        conversation_key = f"{original.source}:{original.id}"
        local_errors = redact_errors([
            replace(item, details={**dict(item.details), "conversation_key": conversation_key})
            for item in [*scoped, *attachment_errors]
        ], report)
        local_errors = _canonicalize_errors(local_errors, report)
        delta = Counter(report.counts)
        delta.subtract(report_before)
        redaction_by_conversation[f"{clean.source}:{clean.id}"] = {key: amount for key, amount in delta.items() if amount > 0}
        digest = hashlib.sha256(json.dumps(clean.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        state_digest = hashlib.sha256(json.dumps({"conversation": clean.to_dict(), "errors": [item.to_dict() for item in local_errors], "status": "incomplete" if local_errors else "complete"}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        redacted.append((clean, local_errors, digest, state_digest))
        all_errors.extend(local_errors)
    all_errors = [item if isinstance(item, Error) else Error.from_dict(item) for item in all_errors]
    all_errors = redact_errors(all_errors, report)
    all_errors = _canonicalize_errors(all_errors, report)
    unique_errors: list[Error] = []
    seen_errors: set[str] = set()
    for item in all_errors:
        key = json.dumps(item.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if key not in seen_errors:
            seen_errors.add(key)
            unique_errors.append(item)
    all_errors = unique_errors
    prior = {str(item.get("source")) + ":" + str(item.get("id")): item for item in (existing or {}).get("conversations", []) if isinstance(item, Mapping)}
    written = skipped = 0
    index_items: list[dict[str, Any]] = []
    if not dry_run:
        for clean, conv_errors, digest, state_digest in redacted:
            source = _safe_segment(clean.source or "unknown")
            cid = _safe_segment(clean.id)
            base = root / "conversations" / source
            json_path, md_path = base / f"{cid}.json", base / f"{cid}.md"
            key = f"{clean.source}:{clean.id}"
            previous = prior.get(key)
            refresh_failed = bool(conv_errors)
            prior_successful = bool((previous or {}).get("last_successful", (previous or {}).get("status") == "complete"))
            if previous and prior_successful and refresh_failed and json_path.is_file() and md_path.is_file():
                # A failed refresh must never destroy the last known-good
                # conversation. Errors are still recorded at archive level.
                skipped += 1
                digest = str(previous.get("content_sha256", digest))
                try:
                    preserved_envelope = read_json(json_path)
                    state_digest = _sha256_bytes(json.dumps({"conversation": preserved_envelope["conversation"], "errors": preserved_envelope.get("errors", []), "status": "incomplete" if preserved_envelope.get("errors") else "complete"}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
                except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                    state_digest = str(previous.get("state_sha256", state_digest))
            elif previous and previous.get("state_sha256") == state_digest and _conversation_files_valid(root, previous):
                skipped += 1
            else:
                envelope = _render_json_raw(clean, checkpoints=clean_checkpoints, errors=conv_errors)
                atomic_write_json(json_path, envelope)
                atomic_write_text(md_path, _render_markdown_raw(clean, checkpoints=clean_checkpoints, errors=conv_errors))
                written += 1
            status = "incomplete" if conv_errors else "complete"
            markdown_hash = _sha256_file(md_path) if md_path.is_file() else str(previous.get("markdown_sha256", "")) if previous else ""
            index_item = {"id": clean.id, "source": clean.source, "title": clean.title, "status": status, "content_sha256": digest, "state_sha256": state_digest, "json": f"conversations/{source}/{cid}.json", "markdown": f"conversations/{source}/{cid}.md", "markdown_sha256": markdown_hash, "last_successful": prior_successful if refresh_failed else True}
            if clean.updated_at:
                index_item["updated_at"] = clean.updated_at
            index_items.append(index_item)
        # Incremental refreshes are additive: a source invocation must not
        # erase conversations collected by another source in an earlier run.
        if existing:
            current_keys = {(str(item.get("source")), str(item.get("id"))) for item in index_items}
            for item in existing.get("conversations", []):
                if isinstance(item, Mapping) and (str(item.get("source")), str(item.get("id"))) not in current_keys:
                    retained = dict(item)
                    retained_path = root / str(retained.get("markdown", ""))
                    if retained_path.is_file():
                        retained["markdown_sha256"] = _sha256_file(retained_path)
                    retained.setdefault("last_successful", retained.get("status") == "complete")
                    index_items.append(retained)
        _ensure_safe_directory(root)
        _ensure_safe_directory(root / "conversations")
        _ensure_safe_directory(root / "assets")
        _ensure_safe_directory(root / "checkpoints")
        for artifact_name, artifact_payload in (checkpoint_artifacts or {}).items():
            artifact_path = root / "checkpoints" / str(artifact_name)
            if artifact_path.parent != root / "checkpoints" or artifact_path.name in {".", ".."}:
                raise ValueError("checkpoint artifact must be a direct safe filename")
            if isinstance(artifact_payload, Mapping):
                atomic_write_json(artifact_path, artifact_payload)
            elif isinstance(artifact_payload, bytes):
                _atomic_write_bytes(artifact_path, artifact_payload)
            else:
                raise TypeError("checkpoint artifact must be bytes or a JSON object")
        # One checkpoint file per export batch; names are stable, so retries do
        # not accumulate duplicate progress records.
        atomic_write_json(root / "checkpoints" / "export.json", {"archive_version": ARCHIVE_VERSION, "schema_version": CURRENT_SCHEMA_VERSION, "version": 1, "records": clean_checkpoints})
        atomic_write_json(root / "errors.json", {"archive_version": ARCHIVE_VERSION, "schema_version": CURRENT_SCHEMA_VERSION, "errors": [item.to_dict() for item in all_errors]})
        md_lines = ["# Conversation archive", ""]
        for item in index_items:
            md_lines.append(f"- [{item['title'] or item['id']}]({item['markdown']}) — `{item['source']}` ({item['status']})")
        index_markdown = "\n".join(md_lines) + "\n"
        atomic_write_text(root / "index.md", index_markdown)
        errors_hash = _sha256_file(root / "errors.json")
        checkpoint_hash = _sha256_file(root / "checkpoints" / "export.json")
        for item in index_items:
            item["markdown_sha256"] = _sha256_file(root / str(item["markdown"])) if (root / str(item["markdown"])).is_file() else item.get("markdown_sha256", "")
        index = {"archive_version": ARCHIVE_VERSION, "schema_version": CURRENT_SCHEMA_VERSION, "conversations": index_items}
        atomic_write_json(root / "index.json", index)
        checkpoint_hashes = {"checkpoints/export.json": checkpoint_hash}
        checkpoint_directory = root / "checkpoints"
        for checkpoint_path in checkpoint_directory.iterdir():
            if checkpoint_path.is_file() and not checkpoint_path.is_symlink():
                checkpoint_hashes[f"checkpoints/{checkpoint_path.name}"] = _sha256_file(checkpoint_path)
        # Recompute counts from the complete durable state. Current source
        # conversations contribute fresh deltas; retained conversations reuse
        # their own prior deltas, avoiding both max-under-counting and retry
        # double-counting.
        current_keys = set(redaction_by_conversation)
        complete_map: dict[str, dict[str, int]] = dict(redaction_by_conversation)
        if prior_redaction_by_conversation:
            for key, counts in prior_redaction_by_conversation.items():
                if key not in current_keys and isinstance(counts, Mapping):
                    complete_map[str(key)] = {str(rule): int(amount) for rule, amount in counts.items() if isinstance(rule, str) and isinstance(amount, int) and amount > 0}
        merged_counts = Counter()
        for counts in complete_map.values():
            merged_counts.update(counts)
        # Counts from checkpoints/global errors are not associated with a
        # conversation and must remain part of the report.
        associated = Counter()
        for counts in redaction_by_conversation.values():
            associated.update(counts)
        global_counts = Counter()
        # Retain per-artifact counts only for durable global artifacts which
        # remain in the archive. Current artifacts replace the same identity.
        merged_artifacts: dict[str, dict[str, int]] = {
            str(key): {str(rule): int(amount) for rule, amount in value.items() if isinstance(rule, str) and isinstance(amount, int) and amount > 0}
            for key, value in prior_global_artifacts.items() if isinstance(value, Mapping)
        }
        # Errors are durable diagnostics and the incremental path retains
        # prior global errors in errors.json.  Therefore their prior stable
        # identities remain authoritative until that durable record is truly
        # removed; current values replace only an identical identity.  The
        # same rule applies to checkpoint artifacts retained in the stage.
        for name in (checkpoint_artifacts or {}):
            prefix = f"checkpoint:{name}:"
            merged_artifacts = {key: value for key, value in merged_artifacts.items() if not key.startswith(prefix)}
        merged_artifacts.update(global_artifacts)
        for counts in merged_artifacts.values():
            global_counts.update(counts)
        merged_counts.update({key: amount for key, amount in global_counts.items() if amount > 0})
        if not prior_redaction_by_conversation and not complete_map:
            merged_counts.update({str(rule): int(amount) for rule, amount in prior_redaction_counts.items() if isinstance(rule, str) and isinstance(amount, int) and amount > 0})
        report.counts.clear()
        report.counts.update(merged_counts)
        manifest = {"archive_version": ARCHIVE_VERSION, "schema_version": CURRENT_SCHEMA_VERSION, "mode": ArchiveMode.coerce(mode).value, "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "redaction": {**report.to_dict(), "global_counts": dict(sorted({key: amount for key, amount in global_counts.items() if amount > 0}.items())), "global_artifacts": merged_artifacts, "by_conversation": complete_map}, "conversations": index_items, "index_md_sha256": _sha256_bytes(index_markdown.encode("utf-8")), "errors_sha256": errors_hash, "checkpoint_files": checkpoint_hashes}
        atomic_write_json(root / "manifest.json", manifest)
    return {"archive_path": str(root), "written": written, "skipped": skipped, "conversation_count": len(redacted), "error_count": len(all_errors), "dry_run": dry_run, "errors": [item.to_dict() for item in all_errors]}


def export_archive(
    output: str | Path,
    conversations: Iterable[Conversation],
    *,
    mode: ArchiveMode | str = ArchiveMode.INCREMENTAL,
    errors: Iterable[Error | Mapping[str, Any]] = (),
    errors_by_conversation: Mapping[str, Iterable[Error | Mapping[str, Any]]] | None = None,
    checkpoints: Iterable[Mapping[str, Any]] = (),
    checkpoint_artifacts: Mapping[str, bytes | Mapping[str, Any]] | None = None,
    timestamp: datetime | None = None,
    run_root: str | Path | None = None,
    approved_root: str | Path | None = None,
    approved_roots: Mapping[str, Iterable[str | Path]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Finalize one archive transaction under an exclusive per-root lock."""

    archive_mode = ArchiveMode.coerce(mode)
    output_path = Path(output)
    selected_root = Path(run_root) if run_root is not None else None
    if dry_run:
        return _export_archive_impl(output_path, conversations, mode=mode, errors=errors, errors_by_conversation=errors_by_conversation, checkpoints=checkpoints, checkpoint_artifacts=checkpoint_artifacts, timestamp=timestamp, run_root=selected_root, approved_root=approved_root, approved_roots=approved_roots, dry_run=True)

    # The lock is a sibling of the published root.  New snapshot runs use the
    # atomically reserved final root, so concurrent calls can proceed with
    # independent sibling locks while still selecting unique destinations.
    lock_root = selected_root if selected_root is not None else output_path
    parent = output_path.parent if archive_mode is ArchiveMode.INCREMENTAL else output_path / "snapshots"
    _ensure_safe_directory(parent)
    if archive_mode is ArchiveMode.SNAPSHOT and selected_root is None:
        selected_root = _root_for_mode(output_path, mode, timestamp, reserve=True)
        lock_root = selected_root
    lock_path = _lock_path(lock_root, archive_mode)
    lock_fd: int | None = None
    try:
        lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError as exc:
        raise OSError("archive root is already being finalized") from exc
    try:
        if archive_mode is ArchiveMode.SNAPSHOT:
            if selected_root is None:
                selected_root = _root_for_mode(output_path, mode, timestamp, reserve=True)
            try:
                selected_root.resolve().relative_to(parent.resolve())
            except ValueError as exc:
                raise ValueError("snapshot run_root must be below output/snapshots") from exc
            if selected_root.parent != parent:
                raise ValueError("snapshot run_root must be a direct child of output/snapshots")
            stem = selected_root.name
        else:
            selected_root = output_path
            stem = selected_root.name
        owner = _transaction_owner(parent, stem)
        _validate_transaction_path(selected_root, parent, stem=stem, kind="final", allow_existing=True)
        if selected_root.exists() and not selected_root.is_dir():
            raise OSError(f"archive root is not a directory: {selected_root}")
        if selected_root.exists():
            _validate_archive_tree(selected_root)

        staging = _new_transaction_directory(parent, stem, "staging", owner)
        _copy_archive_base(selected_root, staging)
        try:
            result = _export_archive_impl(output_path, conversations, mode=mode, errors=errors, errors_by_conversation=errors_by_conversation, checkpoints=checkpoints, checkpoint_artifacts=checkpoint_artifacts, timestamp=timestamp, run_root=staging, approved_root=approved_root, approved_roots=approved_roots, dry_run=False)
            checked = verify_archive(staging)
            if not checked.get("valid"):
                raise OSError("staged archive verification failed: " + "; ".join(str(item) for item in checked.get("errors", [])))
        except BaseException as exc:
            try:
                safe_remove_generated_tree(staging, parent, "stage", expected_owner=owner)
            except OSError as cleanup_error:
                exc.add_note(f"stage cleanup warning: {cleanup_error}")
            raise

        backup: Path | None = None
        if selected_root.exists():
            cleanup_warnings: list[str] = []
            for sibling in parent.iterdir():
                sibling_match = _GENERATED_TREE.fullmatch(sibling.name)
                if sibling_match is not None and sibling_match.group(1) == "backup" and sibling_match.group(2) == owner:
                    try:
                        safe_remove_generated_tree(sibling, parent, "backup", expected_owner=owner)
                    except OSError as cleanup_error:
                        cleanup_warnings.append(str(cleanup_error))
            backup = _new_transaction_path(parent, stem, "backup", owner)
            _validate_transaction_path(selected_root, parent, stem=stem, kind="final", allow_existing=True)
            _validate_transaction_path(backup, parent, stem=stem, kind="backup", expected_owner=owner)
            os.replace(selected_root, backup)
            if cleanup_warnings:
                result.setdefault("cleanup_warnings", []).extend(cleanup_warnings)
                result.setdefault("errors", []).extend({
                    "code": "backup_cleanup",
                    "message": warning,
                    "recoverable": True,
                    "details": {},
                } for warning in cleanup_warnings)
                result["error_count"] = int(result.get("error_count", 0)) + len(cleanup_warnings)
        try:
            _validate_transaction_path(staging, parent, stem=stem, kind="staging", expected_owner=owner, allow_existing=True)
            _validate_transaction_path(selected_root, parent, stem=stem, kind="final")
            os.replace(staging, selected_root)
        except BaseException as exc:
            try:
                if backup is not None and backup.exists() and not selected_root.exists():
                    _validate_transaction_path(backup, parent, stem=stem, kind="backup", expected_owner=owner, allow_existing=True)
                    _validate_transaction_path(selected_root, parent, stem=stem, kind="final")
                    os.replace(backup, selected_root)
            finally:
                try:
                    safe_remove_generated_tree(staging, parent, "stage", expected_owner=owner)
                except OSError as cleanup_error:
                    exc.add_note(f"stage cleanup warning: {cleanup_error}")
            raise
        # A marker belongs to new_run_root's reservation, not to the archive
        # itself. Remove only that empty marker after a successful publish;
        # recovery backups are intentionally never removed.
        reservation = parent / f".{selected_root.name}.reserve"
        if reservation.is_file() and not reservation.is_symlink():
            reservation.unlink()
        result["archive_path"] = str(selected_root)
        return result
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def verify_archive(output: str | Path) -> dict[str, Any]:
    root = Path(output)
    problems: list[str] = []
    try:
        _reject_symlink_components(root)
    except OSError as exc:
        return {"valid": False, "errors": [str(exc)]}
    try:
        manifest = _existing_manifest(root)
    except (OSError, ValueError, SchemaVersionError, ArchiveVersionError) as exc:
        return {"valid": False, "errors": [str(exc)]}
    if manifest is None:
        return {"valid": False, "errors": ["manifest.json is missing"]}
    manifest_conversations = manifest.get("conversations", [])
    if not isinstance(manifest_conversations, list):
        return {"valid": False, "errors": ["manifest conversations must be an array"]}
    try:
        _validate_archive_tree(root)
    except OSError as exc:
        problems.append(str(exc))
    for directory_name in ("conversations", "assets", "checkpoints"):
        directory = root / directory_name
        if directory.is_symlink() or not directory.is_dir():
            problems.append(f"{directory_name} directory is missing or unsafe")
    for name in ("index.json", "index.md", "errors.json"):
        if (root / name).is_symlink() or not (root / name).is_file():
            problems.append(f"{name} is missing")
    try:
        index_payload = read_json(root / "index.json")
        if (index_payload.get("archive_version") != ARCHIVE_VERSION or index_payload.get("schema_version") != CURRENT_SCHEMA_VERSION or not isinstance(index_payload.get("conversations"), list)):
            problems.append("index schema/version is invalid")
        elif index_payload["conversations"] != manifest_conversations:
            # Index and manifest are intentionally identical entries so either
            # can be used as a fast listing without ambiguity.
            problems.append("index and manifest conversation listings differ")
    except (OSError, ValueError):
        problems.append("index.json is invalid")
    index_md_path = root / "index.md"
    if index_md_path.is_file():
        expected_index_hash = manifest.get("index_md_sha256")
        actual_index_hash = hashlib.sha256(index_md_path.read_bytes()).hexdigest()
        if not isinstance(expected_index_hash, str) or actual_index_hash != expected_index_hash:
            problems.append("index.md hash mismatch")
    try:
        errors_payload = read_json(root / "errors.json")
        if (errors_payload.get("archive_version") != ARCHIVE_VERSION or errors_payload.get("schema_version") != CURRENT_SCHEMA_VERSION or not isinstance(errors_payload.get("errors"), list)):
            problems.append("errors.json shape is invalid")
    except (OSError, ValueError):
        problems.append("errors.json is invalid")
    expected_errors_hash = manifest.get("errors_sha256")
    if not isinstance(expected_errors_hash, str) or not (root / "errors.json").is_file() or _sha256_file(root / "errors.json") != expected_errors_hash:
        problems.append("errors.json hash mismatch")
    checkpoint_files = manifest.get("checkpoint_files")
    if not isinstance(checkpoint_files, Mapping) or not checkpoint_files:
        problems.append("checkpoint file hashes are missing")
    else:
        listed_checkpoints = {str(item) for item in checkpoint_files}
        checkpoint_directory = root / "checkpoints"
        if checkpoint_directory.is_symlink():
            problems.append("checkpoints directory is a symlink")
        elif checkpoint_directory.is_dir():
            for checkpoint_path in checkpoint_directory.iterdir():
                relative = f"checkpoints/{checkpoint_path.name}"
                if checkpoint_path.is_symlink() or relative not in listed_checkpoints:
                    problems.append(f"unhashed checkpoint file: {relative}")
        for relative, expected_hash in checkpoint_files.items():
            checkpoint_path = root / str(relative)
            try:
                checkpoint_path.resolve().relative_to(root.resolve())
            except ValueError:
                problems.append(f"checkpoint path escapes archive: {relative}")
                continue
            if checkpoint_path.is_symlink() or not checkpoint_path.is_file() or not isinstance(expected_hash, str) or _sha256_file(checkpoint_path) != expected_hash:
                problems.append(f"checkpoint hash mismatch: {relative}")
            elif relative == "checkpoints/export.json":
                try:
                    checkpoint_payload = read_json(checkpoint_path)
                    if checkpoint_payload.get("archive_version") != ARCHIVE_VERSION or checkpoint_payload.get("schema_version") != CURRENT_SCHEMA_VERSION or checkpoint_payload.get("version") != 1 or not isinstance(checkpoint_payload.get("records"), list):
                        problems.append("checkpoint schema/version is invalid")
                except (OSError, ValueError):
                    problems.append("checkpoint file is invalid")
            else:
                try:
                    checkpoint_payload = read_json(checkpoint_path)
                    if checkpoint_payload.get("archive_version") != ARCHIVE_VERSION or checkpoint_payload.get("schema_version") != CURRENT_SCHEMA_VERSION or checkpoint_payload.get("version") != 1:
                        problems.append(f"checkpoint schema/version is invalid: {relative}")
                except (OSError, ValueError):
                    problems.append(f"checkpoint file is invalid: {relative}")
    for item in manifest_conversations:
        if not isinstance(item, Mapping):
            problems.append("manifest contains a non-object conversation")
            continue
        for field in ("json", "markdown"):
            path = root / str(item.get(field, ""))
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                problems.append(f"conversation path escapes archive: {path}")
                continue
            if not path.is_file():
                problems.append(f"missing conversation file: {path}")
            elif path.is_symlink():
                problems.append(f"conversation file is a symlink: {path}")
        json_path = root / str(item.get("json", ""))
        if json_path.is_file():
            try:
                envelope = read_json(json_path)
                if set(envelope) != {"schema_version", "conversation", "checkpoints", "errors"}:
                    problems.append(f"invalid envelope keys: {json_path}")
                elif envelope.get("schema_version") != CURRENT_SCHEMA_VERSION:
                    problems.append(f"invalid schema version: {json_path}")
                else:
                    digest = hashlib.sha256(json.dumps(envelope["conversation"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                    if digest != item.get("content_sha256"):
                        problems.append(f"conversation hash mismatch: {json_path}")
                    computed_state = hashlib.sha256(json.dumps({"conversation": envelope["conversation"], "errors": envelope.get("errors", []), "status": "incomplete" if envelope.get("errors") else "complete"}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                    if item.get("state_sha256") != computed_state:
                        problems.append(f"conversation state hash mismatch: {json_path}")
                    conversation = envelope.get("conversation", {})
                    attachments = list(conversation.get("attachments", [])) if isinstance(conversation, Mapping) else []
                    for entry in conversation.get("entries", []) if isinstance(conversation, Mapping) else []:
                        if isinstance(entry, Mapping):
                            attachments.extend(entry.get("attachments", []))
                    for attachment in attachments:
                        if not isinstance(attachment, Mapping) or not isinstance(attachment.get("uri"), str) or not attachment["uri"].startswith("assets/"):
                            continue
                        asset = root / attachment["uri"]
                        try:
                            asset.resolve().relative_to(root.resolve())
                        except ValueError:
                            problems.append(f"attachment path escapes archive: {asset}")
                            continue
                        if asset.is_symlink() or not asset.is_file():
                            problems.append(f"missing attachment asset: {asset}")
                        else:
                            actual = hashlib.sha256(asset.read_bytes()).hexdigest()
                            expected = asset.name.split(".", 1)[0]
                            if asset.stat().st_nlink != 1:
                                problems.append(f"attachment hardlink is not allowed: {asset}")
                            if actual != expected:
                                problems.append(f"attachment hash mismatch: {asset}")
            except (OSError, ValueError, TypeError):
                problems.append(f"invalid conversation JSON: {json_path}")
        markdown_path = root / str(item.get("markdown", ""))
        expected_markdown_hash = item.get("markdown_sha256")
        if markdown_path.is_file() and (not isinstance(expected_markdown_hash, str) or _sha256_file(markdown_path) != expected_markdown_hash):
            problems.append(f"conversation markdown hash mismatch: {markdown_path}")
    return {"valid": not problems, "errors": problems, "conversation_count": len(manifest_conversations)}


write_archive = export_archive
