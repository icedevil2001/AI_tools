---
name: conversation-exporter
description: Archive Codex or bounded ChatGPT captures as redacted normalized JSON and Markdown.
---

# Conversation Exporter

This skill defines the bounded operational interface for the Codex and ChatGPT collectors.

## Confirm the destination

Before invoking the CLI, ask the user to confirm the output directory. Pass that exact
directory with `--output`; this plugin does not choose a default destination.

## Select a mode

- `snapshot` writes a unique timestamped immutable-looking archive at
  `snapshots/YYYY-MM-DDTHHMMSSZ[-N]/`.
- `incremental` reserves one stable file per conversation at
  `conversations/<source>/<conversation-id>.json` and updates it in place.

Always confirm both the destination and mode with the user before a write. A
dry run performs validation/counting and writes no archive files.

## Inspect without collecting

```bash
PYTHONPATH=src python -m conversation_exporter \
  --source codex --mode snapshot --output ./archive --dry-run
```

Use `--init` when the confirmed destination should be created. `--dry-run` discovers and
counts records without writing archive files or checkpoints. Codex resolves `--codex-home`,
then `CODEX_HOME`, then `~/.codex` and reads `sessions/**/*.jsonl` in stable path order. Use
repeatable `--codex-attachment-root` to explicitly approve attachment directories; the
Codex home itself is never implicitly trusted. Use
`--capture` for one ChatGPT capture JSON at a time; resume reads only the archive-local
`checkpoints/chatgpt.json` artifact.

ChatGPT capture contract: an object with `id`, `status` (`regular` or `archived`),
`source_url`, `messages` (visible `user`, `assistant`, or `tool` messages with a non-empty
stable `id`, text/Markdown `content`, optional timestamps and `branch_id`), optional visible `branches`, and optional
`attachments`, explicit boolean `complete`, and optional `errors` for inaccessible/skipped discovery items. Code and
tables are represented as text/Markdown; no HTML is executed. Pass `--download-root` to
approve local attachment downloads; remote-only attachments remain referenced with a
recoverable failure reason and are retried on the next capture.

Each archive envelope also carries `checkpoints` and `errors` arrays. Collectors can use
checkpoints for resumable progress and structured `Error` values for partial failures.

## Chrome capture procedure

Chrome collection requires the Chrome-control skill and an authenticated tab already showing
the ChatGPT application. The exporter does not control Chrome, inspect cookies, local
storage, passwords, or tokens, and must never claim that its Python CLI does so. Use the
maintained [capture procedure](../../resources/chrome-extraction.md) and pass each bounded
JSON capture to `scripts/chrome_capture_ingest.py` (or `--source chatgpt --capture ...`).
Enumerate normal and archived chat links by stable href/ID while scrolling until no new IDs
appear; load each complete thread and enumerate visible alternate branches. Persist one
capture at a time. A dry run only validates/counts. Deleted, temporary, inaccessible, or
UI-changed chats are explicit limitations and must produce a recoverable error rather than
broadening access.

## Privacy and resume

Credentials are redacted from visible text, tool actions, errors, metadata, and
text-readable attachments before JSON or Markdown is persisted. The manifest
records the redaction rule version and counts; removed values are never stored.
Binary attachments are copied unchanged and marked `unscanned`. Remote URLs are
references only: the bounded importer does not download them. Keep archives and
the approved download directory private.

Incremental exports compare source plus content hash and preserve the last
successful conversation if a refresh fails. Retry the same capture with the
same archive and approved download root to resume failed attachments. Snapshot
exports are date-partitioned independent archives. `verify` checks manifest,
indexes, and conversation files; newer schema/archive versions are rejected.
For `--source all --mode snapshot`, one timestamped run root is reserved and both
sources are finalized into that same root. To resume a bounded snapshot capture,
pass the exact run root used by the initial capture; omitting it intentionally starts
a new independent snapshot run.

Example resume command:

```bash
PYTHONPATH=src python -m conversation_exporter --source chatgpt --mode snapshot \
  --output ./archive --run-root ./archive/snapshots/2026-08-26T120000Z \
  --capture ./capture.json
```

Starter prompts:

- “Confirm `/path/to/archive` and incremental mode, then dry-run Codex collection.”
- “Using this bounded ChatGPT capture, validate and export it to the confirmed destination.”
- “Resume the incomplete export from its checkpoint and report skipped/failed items.”

## Extension points

Collectors belong outside the normalized models and should report non-fatal failures as
structured `Error` values. Renderers can consume `Conversation` values after collection.
