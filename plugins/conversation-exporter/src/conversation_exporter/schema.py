"""Archive schema versioning and normalized conversation loading."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from typing import Any

from .models import Conversation, Error

CURRENT_SCHEMA_VERSION = 1
# Public short alias for adapters that prefer a schema constant without the
# ``CURRENT_`` qualifier.
SCHEMA_VERSION = CURRENT_SCHEMA_VERSION


class SchemaVersionError(ValueError):
    """Raised when an archive was written by an unsupported schema version."""


class ArchiveValidationError(ValueError):
    """Raised when an archive has the right version but malformed content."""


def validate_schema_version(payload: Mapping[str, Any]) -> None:
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != CURRENT_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"unsupported schema version {version!r}; expected {CURRENT_SCHEMA_VERSION}"
        )


def load_conversation(path: str | Path) -> Conversation:
    from .storage import read_json

    payload = read_json(path)
    validate_schema_version(payload)
    for field in ("checkpoints", "errors"):
        if field in payload and not isinstance(payload[field], list):
            raise ArchiveValidationError(f"archive {field} must be an array")
    checkpoints = payload.get("checkpoints", [])
    for index, checkpoint in enumerate(checkpoints):
        if not isinstance(checkpoint, Mapping):
            raise ArchiveValidationError(f"archive checkpoints[{index}] must be an object")
    errors = payload.get("errors", [])
    for index, error in enumerate(errors):
        try:
            Error.from_dict(error)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ArchiveValidationError(f"invalid archive errors[{index}]: {exc}") from exc
    value = payload.get("conversation")
    if not isinstance(value, dict):
        raise ArchiveValidationError("archive JSON must contain a conversation object")
    try:
        return Conversation.from_dict(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ArchiveValidationError(f"invalid conversation payload: {exc}") from exc
