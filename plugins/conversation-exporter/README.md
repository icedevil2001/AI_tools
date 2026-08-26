# Conversation Exporter

This plugin exports Codex sessions and bounded ChatGPT browser captures into a
source-neutral archive. It is dependency-free and does not log into or control a browser.

## Interface

Run the CLI from the plugin source tree:

```bash
PYTHONPATH=src python -m conversation_exporter \
  --source codex --mode snapshot --output ./archive --init --dry-run
```

`--source`, `--mode`, and `--output` are explicit inputs. The destination is never guessed;
the calling skill or user confirms it before running an export. `--init` creates it, and
`--dry-run` discovers/counts without writing. Codex accepts `--codex-home` and otherwise
resolves `CODEX_HOME`, then `~/.codex`; malformed JSONL lines become recoverable errors.
Codex attachments remain metadata-only unless beneath an explicitly approved repeatable
`--codex-attachment-root`; `--codex-home` is never implicitly trusted.
ChatGPT accepts one `--capture` JSON at a time; resume uses only the archive-local
`checkpoints/chatgpt.json` artifact.
Every captured message must have a non-empty stable `id` (taken from a stable DOM attribute
or deterministic visible-content hash, never an array index); branch IDs must be unique and
message branch references must resolve.
Captures must explicitly set boolean `complete`; incomplete captures remain retryable and
are never completion-checkpointed.
Use `--download-root` to approve the directory containing local attachment downloads;
source files outside it or traversing symlinks are rejected. Attachment failures produce an
incomplete, retryable archive and do not checkpoint the conversation.

Exit status `0` means complete, `2` means invalid CLI/capture input or an uninitialized
default-source invocation, `3` means ingestion
failure, and `4` means a partial result with recoverable collector errors.

Use `conversation-exporter verify --output ./archive` to validate an existing archive.
Only `init`, `export`, and `verify` commands are accepted
for scripting clarity; source input remains explicitly bounded (`codex`, `chatgpt`, or `all`).

The documented ChatGPT capture contract is in `resources/chrome-extraction.md`. Browser
enumeration requires the Chrome-control skill and an authenticated tab; the maintained
`scripts/chrome_capture_ingest.py` only validates and persists a capture and never claims
to control Chrome.

Snapshot archives are independent timestamped directories at
`snapshots/YYYY-MM-DDTHHMMSSZ[-N]/`; incremental archives keep one stable
`conversations/<source>/<conversation-id>.json` and matching Markdown file. Every
conversation JSON has `schema_version: 1` and a `conversation` object plus
`checkpoints` and `errors` arrays. Archive roots also contain `manifest.json`,
`index.json`, `index.md`, `errors.json`, `checkpoints/`, and content-addressed
`assets/`. Unknown schema/archive versions are rejected.

Before durable output, visible text, tool actions, metadata, errors, and text
attachments are redacted for common API keys, bearer credentials, private-key
blocks, secret assignments, and URL credentials. The manifest records the rule
version and per-rule counts. Binary attachments remain byte-for-byte unchanged
and are marked `unscanned`; remote references are not downloaded. Incremental
refreshes preserve a prior successful file when a new capture has failures.
An `all` snapshot reserves one timestamped run root and finalizes both sources
together; resuming a snapshot requires passing that exact run root.

Archive updates are assembled in a validated sibling staging directory and
published with atomic directory renames. Incremental updates first move the
previous root to a uniquely named sibling `.archive.backup-*` recovery point;
the newest backup is retained as the sole recovery point after a successful
publish. If the
publish rename fails, the previous root is restored atomically and the failed
staging directory is safely removed after the error is preserved. A failure
while building or verifying a stage leaves the current published root
byte-for-byte unchanged. Transaction names carry a short hash of their
intended archive root, so cleanup only removes backups belonging to that root;
adjacent roots and legacy unowned backup names remain untouched for manual
recovery.

The Python package exposes normalized `Conversation`, `Entry`, `Attachment`, and `Error`
models, source collectors, path resolution, schema loading, and atomic JSON storage. Codex
collection uses an explicit visibility allowlist: user/assistant messages, visible tool
calls/results, session metadata, and attachment references; system/developer/bootstrap,
reasoning, and internal orchestration records are excluded.
