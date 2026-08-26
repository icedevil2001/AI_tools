"""Dependency-free foundation for the conversation-exporter plugin."""

from .models import Attachment, Conversation, Entry, Error
from .paths import ArchiveMode, resolve_archive_path
from .schema import ArchiveValidationError, CURRENT_SCHEMA_VERSION, SCHEMA_VERSION, SchemaVersionError, load_conversation
from .storage import atomic_write_json, read_json, write_conversation
from .redaction import REDACTION_RULE_VERSION, RedactionReport, redact_text, redact_value
from .rendering import render_json, render_markdown, render_conversation_json, render_conversation_markdown
from .archive import ARCHIVE_VERSION, ArchiveVersionError, export_archive, verify_archive, write_archive, new_run_root, safe_remove_generated_tree

__all__ = [
    "Attachment",
    "Conversation",
    "Entry",
    "Error",
    "ArchiveMode",
    "resolve_archive_path",
    "atomic_write_json",
    "read_json",
    "write_conversation",
    "CURRENT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "SchemaVersionError",
    "ArchiveValidationError",
    "load_conversation",
    "REDACTION_RULE_VERSION",
    "RedactionReport",
    "redact_text",
    "redact_value",
    "render_json",
    "render_markdown",
    "render_conversation_json",
    "render_conversation_markdown",
    "ARCHIVE_VERSION",
    "ArchiveVersionError",
    "export_archive",
    "verify_archive",
    "write_archive",
    "new_run_root",
    "safe_remove_generated_tree",
]
