"""Deterministic, local redaction of credentials before archive persistence."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Mapping

from .models import Attachment, Conversation, Entry, Error

REDACTION_RULE_VERSION = "2026-08-26.v1"


@dataclass
class RedactionReport:
    rule_version: str = REDACTION_RULE_VERSION
    counts: Counter[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.counts is None:
            self.counts = Counter()

    def add(self, rule: str, amount: int = 1) -> None:
        self.counts[rule] += amount

    def merge(self, other: "RedactionReport") -> None:
        self.counts.update(other.counts)

    def to_dict(self) -> dict[str, Any]:
        return {"rule_version": self.rule_version, "counts": dict(sorted(self.counts.items()))}


# Keep credential prefixes bounded and require a realistic token length. This
# intentionally does not treat ordinary words containing "token" or "secret"
# as secrets.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.I | re.S)),
    ("bearer_token", re.compile(r"(?i)(\b(?:authorization|proxy-authorization)\s*:\s*bearer\s+|\bbearer\s+)([A-Za-z0-9._~+/=-]{10,})")),
    ("openai_api_key", re.compile(r"\bsk-(?:proj-|live-|admin-)?[A-Za-z0-9_-]{20,}\b")),
    ("known_api_key", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{15,}|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|glpat-[A-Za-z0-9_-]{20,}|npm_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|r8_[A-Za-z0-9]{20,})\b")),
    ("url_credential", re.compile(r"(?i)(://)([^/@\s:]+):([^/@\s]+)(@)")),
    ("secret_assignment", re.compile(r'''(?ix)(["']?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|secret|token)\b["']?\s*(?:=|:)\s*)(?P<q>["']?)(?!\[REDACTED:])(?P<value>[^\s,;&}"']{4,})(?P=q)''')),
)


def redact_text(text: str, report: RedactionReport | None = None) -> tuple[str, RedactionReport]:
    """Replace credential values with typed placeholders and count each rule."""

    if not isinstance(text, str):
        raise TypeError("redact_text expects text")
    result = report or RedactionReport()
    placeholders: list[str] = []
    def hide_placeholder(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"ZZZPLACEHOLDER{len(placeholders) - 1}ZZZ"
    text = re.sub(r"\[REDACTED:[A-Za-z0-9_-]+\]", hide_placeholder, text)
    for rule, pattern in _RULES:
        def replace_match(match: re.Match[str], _rule: str = rule) -> str:
            if _rule != "secret_assignment":
                result.add(_rule)
            if _rule == "private_key":
                return "[REDACTED:private_key]"
            if _rule == "bearer_token":
                return match.group(1) + "[REDACTED:bearer_token]"
            if _rule == "url_credential":
                return match.group(1) + "[REDACTED:url_credential]" + match.group(4)
            if _rule == "secret_assignment":
                raw_value = match.group("value")
                if "ZZZPLACEHOLDER" in raw_value:
                    return match.group(0)
                # Bare prose such as ``token: this`` is not a credential. Bare
                # assignments need a realistic token shape; quoted values are
                # explicit and are redacted even when short (passwords often
                # are).
                key_match = re.search(r"[A-Za-z][A-Za-z_-]*", match.group(1))
                key_name = key_match.group(0).lower() if key_match else "secret"
                if key_name == "token" and not match.group("q") and len(raw_value) < 12 and not re.search(r"[0-9._/+=-]", raw_value):
                    return match.group(0)
                key = (key_match.group(0).lower().replace("-", "_") if key_match else "secret")
                result.add(key)
                return match.group(1) + f"[REDACTED:{key}]"
            return f"[REDACTED:{_rule}]"
        text = pattern.sub(replace_match, text)
    for index, placeholder in enumerate(placeholders):
        text = text.replace(f"ZZZPLACEHOLDER{index}ZZZ", placeholder)
    return text, result


def redact_value(value: Any, report: RedactionReport | None = None) -> Any:
    """Recursively sanitize JSON-compatible values without retaining secrets."""

    result = report or RedactionReport()
    if isinstance(value, str):
        return redact_text(value, result)[0]
    if isinstance(value, list):
        return [redact_value(item, result) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item, result) for item in value)
    if isinstance(value, Mapping):
        return {str(key): redact_value(item, result) for key, item in value.items()}
    return value


def redact_conversation(conversation: Conversation, report: RedactionReport | None = None) -> Conversation:
    """Return a sanitized model while preserving IDs, ordering, and structure."""

    result = report or RedactionReport()
    def clean_attachment(attachment: Attachment) -> Attachment:
        return replace(
            attachment,
            filename=redact_text(attachment.filename, result)[0],
            uri=redact_text(attachment.uri, result)[0] if isinstance(attachment.uri, str) else attachment.uri,
            metadata=redact_value(attachment.metadata, result),
        )

    entries = tuple(replace(
        entry,
        content=redact_text(entry.content, result)[0],
        attachments=tuple(clean_attachment(item) for item in entry.attachments),
        metadata=redact_value(entry.metadata, result),
    ) for entry in conversation.entries)
    attachments = tuple(clean_attachment(item) for item in conversation.attachments)
    return replace(
        conversation,
        title=redact_text(conversation.title, result)[0],
        entries=entries,
        attachments=attachments,
        metadata=redact_value(conversation.metadata, result),
    )


def redact_errors(errors: list[Error], report: RedactionReport | None = None) -> list[Error]:
    result = report or RedactionReport()
    return [replace(item, message=redact_text(item.message, result)[0], details=redact_value(item.details, result)) for item in errors]
