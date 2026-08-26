"""Source-neutral JSON and Markdown renderers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from .models import Conversation, Error
from .schema import CURRENT_SCHEMA_VERSION


def _render_json_raw(
    conversation: Conversation,
    *,
    checkpoints: Iterable[Mapping[str, Any]] = (),
    errors: Iterable[Error | Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the required archive envelope without writing it."""

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "conversation": conversation.to_dict(),
        "checkpoints": [dict(item) for item in checkpoints],
        "errors": [item.to_dict() if isinstance(item, Error) else dict(item) for item in errors],
    }


def _render_markdown_raw(
    conversation: Conversation,
    *,
    checkpoints: Iterable[Mapping[str, Any]] = (),
    errors: Iterable[Error | Mapping[str, Any]] = (),
    attachment_prefix: str = "../../assets",
) -> str:
    """Render a readable, order-preserving conversation transcript."""

    checkpoints = list(checkpoints)
    errors = [item.to_dict() if isinstance(item, Error) else dict(item) for item in errors]
    lines = [f"# {conversation.title or conversation.id}", "", f"- Source: `{conversation.source}`", f"- ID: `{conversation.id}`"]
    if conversation.created_at:
        lines.append(f"- Created: {conversation.created_at}")
    if conversation.updated_at and conversation.updated_at != conversation.created_at:
        lines.append(f"- Updated: {conversation.updated_at}")
    status = conversation.metadata.get("status") if isinstance(conversation.metadata, Mapping) else None
    if status:
        lines.append(f"- Status: **{status}**")
    lines.append("")
    branches = conversation.metadata.get("branches") if isinstance(conversation.metadata, Mapping) else None
    if branches:
        lines.extend(["## Branches", ""])
        for branch in branches if isinstance(branches, list) else []:
            if isinstance(branch, Mapping):
                marker = "visible" if branch.get("visible", True) else "hidden"
                lines.append(f"- `{branch.get('id', '')}` ({marker})")
        lines.append("")
    lines.extend(["## Messages", ""])
    for entry in conversation.entries:
        role = entry.role.replace("_", " ").title()
        heading = f"### {role}"
        if entry.created_at:
            heading += f" — {entry.created_at}"
        branch_id = entry.metadata.get("branch_id") if isinstance(entry.metadata, Mapping) else None
        if branch_id:
            heading += f" (branch `{branch_id}`)"
        lines.extend([heading, ""])
        if entry.role in {"tool_call", "tool_result", "action", "action_result"}:
            name = entry.metadata.get("name") if isinstance(entry.metadata, Mapping) else None
            if name:
                lines.append(f"**Action:** `{name}`")
                lines.append("")
            arguments = entry.metadata.get("arguments") if isinstance(entry.metadata, Mapping) else None
            if arguments is not None:
                lines.extend(["**Arguments:**", "", "```json", json.dumps(arguments, ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
        lines.extend([entry.content, ""])
        if entry.attachments:
            for attachment in entry.attachments:
                label = attachment.filename or attachment.id or "attachment"
                uri = attachment.uri
                if uri and uri.startswith("assets/"):
                    uri = f"{attachment_prefix}/{uri.removeprefix('assets/')}"
                if uri:
                    lines.append(f"- Attachment: [{label}]({uri})")
                else:
                    reason = attachment.metadata.get("failure_reason") if isinstance(attachment.metadata, Mapping) else None
                    lines.append(f"- Attachment: {label} (unavailable{': ' + str(reason) if reason else ''})")
            lines.append("")
    if conversation.attachments:
        lines.extend(["## Attachments", ""])
        for attachment in conversation.attachments:
            label = attachment.filename or attachment.id or "attachment"
            if attachment.uri:
                # Existing URIs are archive-relative; links from the markdown
                # conversation directory need two levels up for assets.
                uri = attachment.uri
                if uri.startswith("assets/"):
                    uri = f"{attachment_prefix}/{uri.removeprefix('assets/')}"
                lines.append(f"- [{label}]({uri})")
            else:
                reason = attachment.metadata.get("failure_reason") if isinstance(attachment.metadata, Mapping) else None
                lines.append(f"- {label} (unavailable{': ' + str(reason) if reason else ''})")
        lines.append("")
    if checkpoints:
        lines.extend(["## Checkpoints", "", "```json", json.dumps(checkpoints, ensure_ascii=False, indent=2), "```", ""])
    if errors:
        lines.extend(["## Errors", ""])
        for error in errors:
            recoverable = error.get("recoverable", True)
            details = error.get("details")
            suffix = f" (recoverable={str(recoverable).lower()}"
            if details:
                suffix += f", details={json.dumps(details, ensure_ascii=False, sort_keys=True)}"
            suffix += ")"
            lines.append(f"- `{error.get('code', 'error')}`: {error.get('message', '')}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(conversation: Conversation, *, checkpoints: Iterable[Mapping[str, Any]] = (), errors: Iterable[Error | Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Privacy-safe public JSON renderer."""
    from .redaction import redact_conversation, redact_errors, RedactionReport, redact_value
    report = RedactionReport()
    clean = redact_conversation(conversation, report)
    clean_checkpoints = [redact_value(dict(item), report) for item in checkpoints]
    clean_errors = redact_errors([item if isinstance(item, Error) else Error.from_dict(item) for item in errors], report)
    return _render_json_raw(clean, checkpoints=clean_checkpoints, errors=clean_errors)


def render_markdown(conversation: Conversation, *, checkpoints: Iterable[Mapping[str, Any]] = (), errors: Iterable[Error | Mapping[str, Any]] = (), attachment_prefix: str = "../../assets") -> str:
    """Privacy-safe public Markdown renderer."""
    from .redaction import redact_conversation, redact_errors, RedactionReport, redact_value
    report = RedactionReport()
    clean = redact_conversation(conversation, report)
    clean_checkpoints = [redact_value(dict(item), report) for item in checkpoints]
    clean_errors = redact_errors([item if isinstance(item, Error) else Error.from_dict(item) for item in errors], report)
    return _render_markdown_raw(clean, checkpoints=clean_checkpoints, errors=clean_errors, attachment_prefix=attachment_prefix)


# Explicit aliases make the renderer API discoverable to adapters while
# keeping the concise names used internally.
render_conversation_json = render_json
render_conversation_markdown = render_markdown
