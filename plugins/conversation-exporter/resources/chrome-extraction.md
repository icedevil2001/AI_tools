# Chrome extraction resource

This is a procedure for the Chrome-control skill, not a standalone browser controller.
It requires an authenticated ChatGPT tab. Do not inspect or export cookies, local storage,
passwords, tokens, or hidden page state.

1. Enumerate normal-chat links from the visible navigation. Record stable conversation IDs
   from hrefs (prefer `/c/<id>` or an equivalent stable ID) and the href itself.
2. Scroll the list, recording IDs in a set, until a full scroll adds no IDs. Open the archive
   view and repeat the same bounded scan; mark each capture `status: "regular"` or
   `status: "archived"`.
3. Open one link at a time and wait for the complete thread. Record visible user,
   assistant, and tool messages in display order. Keep code and tables as plain text or
   Markdown. Record visible alternate branch IDs and messages; do not infer hidden branches.
   Generate each message ID from a stable DOM attribute when available (or a deterministic
   hash of visible message/branch data), never from an array index.
4. For each visible attachment, record metadata and a local download path only when Chrome
   successfully downloaded it. Otherwise preserve its URL and a failure reason.
5. Write one capture matching the contract below and immediately pass it to the bounded
   ingestion command. When a capture includes `local_path`, pass the approved download
   directory explicitly; the path must be beneath that directory and must not be a symlink.
   Never accumulate unbounded page history in one capture.

```bash
python scripts/chrome_capture_ingest.py --capture ./capture.json \
  --output ./archive --download-root ./downloads
```

Only files already downloaded beneath the approved `--download-root` are copied. The
ingestion command does not download remote URLs.

```json
{
  "id": "stable-id",
  "title": "visible title",
  "status": "regular",
  "complete": true,
  "source_url": "https://chatgpt.com/c/stable-id",
  "messages": [{"id": "m1", "role": "user", "content": "text", "timestamp": null, "branch_id": "main"}],
  "branches": [{"id": "main", "visible": true}],
  "attachments": [{"id": "a1", "filename": "file.txt", "media_type": "text/plain", "local_path": "./downloads/file.txt"}]
}
```

Deleted, temporary, or inaccessible chats may not have stable IDs or complete content and
are skipped with a recoverable error. UI changes that remove expected links, archive views,
thread content, or branch controls are reported as extraction failures; do not fall back to
cookies, storage, or private APIs.
