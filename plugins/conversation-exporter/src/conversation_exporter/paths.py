"""Archive destination layout resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path


class ArchiveMode(StrEnum):
    SNAPSHOT = "snapshot"
    INCREMENTAL = "incremental"

    @classmethod
    def coerce(cls, value: "ArchiveMode | str") -> "ArchiveMode":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except ValueError as exc:
            raise ValueError(f"unsupported archive mode: {value!r}") from exc


def resolve_archive_path(
    output: str | Path,
    conversation_id: str,
    mode: ArchiveMode | str,
    *,
    timestamp: datetime | None = None,
    source: str | None = None,
) -> Path:
    """Return the deterministic JSON path for a conversation archive.

    Snapshot archives are date-partitioned; incremental archives keep one stable
    path per conversation so future collectors can update it atomically.
    """

    if not conversation_id or conversation_id in {".", ".."} or "/" in conversation_id or "\\" in conversation_id:
        raise ValueError("conversation_id must be a single safe path segment")

    output_path = Path(output)
    archive_mode = ArchiveMode.coerce(mode)
    if source is None:
        raise ValueError("source is required for archive paths")
    if not source or "/" in source or "\\" in source or source in {".", ".."}:
        raise ValueError("source must be a single safe path segment")
    if archive_mode is ArchiveMode.INCREMENTAL:
        return output_path / "conversations" / source / f"{conversation_id}.json"

    moment = timestamp or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    date = moment.astimezone(timezone.utc).date().isoformat()
    stamp = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    return output_path / "snapshots" / stamp / "conversations" / source / f"{conversation_id}.json"
