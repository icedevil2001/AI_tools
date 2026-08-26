"""Normalized, source-neutral conversation models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


def _require_mapping(value: Any, model_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{model_name} must be a JSON object")
    return value


@dataclass(frozen=True)
class Attachment:
    """A file or media item associated with an entry or conversation."""

    id: str = ""
    filename: str = ""
    media_type: str = "application/octet-stream"
    uri: str | None = None
    size_bytes: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Attachment":
        value = _require_mapping(value, "attachment")
        return cls(
            id=str(value.get("id", "")),
            filename=str(value.get("filename", "")),
            media_type=str(value.get("media_type", "application/octet-stream")),
            uri=value.get("uri"),
            size_bytes=value.get("size_bytes"),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class Entry:
    """One role-bearing message in a normalized conversation."""

    id: str = ""
    role: str = "user"
    content: str = ""
    created_at: str | None = None
    attachments: tuple[Attachment, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["attachments"] = [attachment.to_dict() for attachment in self.attachments]
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Entry":
        value = _require_mapping(value, "entry")
        attachments = value.get("attachments", [])
        if not isinstance(attachments, (list, tuple)):
            raise TypeError("entry.attachments must be an array")
        return cls(
            id=str(value.get("id", "")),
            role=str(value.get("role", "user")),
            content=str(value.get("content", "")),
            created_at=value.get("created_at"),
            attachments=tuple(Attachment.from_dict(item) for item in attachments),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class Conversation:
    """A source-neutral conversation ready for archive serialization."""

    id: str = ""
    title: str = ""
    source: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    entries: tuple[Entry, ...] = ()
    attachments: tuple[Attachment, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["entries"] = [entry.to_dict() for entry in self.entries]
        value["attachments"] = [attachment.to_dict() for attachment in self.attachments]
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Conversation":
        value = _require_mapping(value, "conversation")
        entries = value.get("entries", [])
        attachments = value.get("attachments", [])
        if not isinstance(entries, (list, tuple)):
            raise TypeError("conversation.entries must be an array")
        if not isinstance(attachments, (list, tuple)):
            raise TypeError("conversation.attachments must be an array")
        return cls(
            id=str(value.get("id", "")),
            title=str(value.get("title", "")),
            source=str(value.get("source", "")),
            created_at=value.get("created_at"),
            updated_at=value.get("updated_at"),
            entries=tuple(Entry.from_dict(item) for item in entries),
            attachments=tuple(Attachment.from_dict(item) for item in attachments),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class Error:
    """A structured, non-fatal archive error."""

    code: str = ""
    message: str = ""
    recoverable: bool = True
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Error":
        value = _require_mapping(value, "error")
        recoverable = value.get("recoverable", True)
        if not isinstance(recoverable, bool):
            raise TypeError("error.recoverable must be a boolean")
        return cls(
            code=str(value.get("code", "")),
            message=str(value.get("message", "")),
            recoverable=recoverable,
            details=dict(value.get("details", {})),
        )
