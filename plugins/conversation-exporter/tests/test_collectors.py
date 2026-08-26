import json
import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PACKAGE_ROOT))

from conversation_exporter.collectors.chatgpt import CaptureValidationError, CheckpointVersionError, ingest_capture, validate_capture
from conversation_exporter.collectors.codex import collect_codex_sessions, resolve_codex_home
from conversation_exporter.cli import build_parser, main


class CodexCollectorTests(unittest.TestCase):
    def _session(self, root, name, lines):
        path = root / "sessions" / "2026" / "08" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            for line in lines:
                stream.write(line if isinstance(line, str) else json.dumps(line))
                stream.write("\n")
        return path

    def test_home_resolution_and_deterministic_allowlisted_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "codex"
            self._session(home, "b.jsonl", [
                {"id": "session-b", "timestamp": "2026-08-26T00:00:00Z"}, "not json",
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "later"}]},
                {"type": "reasoning", "summary": [{"type": "summary_text", "text": "hidden"}]},
                {"type": "response_item", "payload": {"type": "function_call", "call_id": "call-1", "name": "ls", "arguments": "{}"}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": "ok"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "internal"}},
            ])
            self._session(home, "a.jsonl", [
                {"id": "session-a", "timestamp": "2026-08-26T00:00:00Z"},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]},
            ])
            result = collect_codex_sessions(explicit_home=home)
            self.assertEqual([c.id for c in result.conversations], ["session-a", "session-b"])
            self.assertEqual([e.content for e in result.conversations[1].entries], ["later", "ls", "ok"])
            self.assertEqual(result.conversations[1].entries[1].metadata["arguments"], {})
            self.assertTrue(any(error.code == "malformed_line" for error in result.errors))
            self.assertFalse(any("hidden" in e.content or "internal" in e.content for c in result.conversations for e in c.entries))
            self.assertEqual(resolve_codex_home(home, {"CODEX_HOME": "/wrong"}), home)
            self.assertEqual(resolve_codex_home(None, {"CODEX_HOME": str(home)}), home)

    def test_codex_content_part_allowlist_excludes_reasoning_and_hidden_mappings(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._session(home, "parts.jsonl", [
                {"id": "parts"},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "visible"}, {"type": "reasoning_text", "text": "hidden"}, {"type": "metadata", "text": "also hidden"}]},
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "answer"}, {"type": "analysis", "text": "hidden"}]},
            ])
            entries = collect_codex_sessions(home).conversations[0].entries
            self.assertEqual([entry.content for entry in entries], ["visible", "answer"])

    def test_codex_session_symlink_is_rejected_and_other_session_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory); sessions = home / "sessions"; sessions.mkdir()
            self._session(home, "good.jsonl", [{"id": "good"}, {"type": "message", "role": "user", "content": "ok"}])
            outside = Path(directory).parent / "outside-session.jsonl"; outside.write_text('{"id":"outside"}\n', encoding="utf-8")
            (sessions / "bad.jsonl").symlink_to(outside)
            result = collect_codex_sessions(home)
            self.assertEqual([c.id for c in result.conversations], ["good"])
            self.assertTrue(any(error.code == "session_unsafe" for error in result.errors))

    def test_missing_timestamps_and_attachment_refs_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._session(home, "one.jsonl", [
                {"id": "s", "timestamp": "2026-08-26T00:00:00Z"},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "see file"}], "attachments": [{"id": "f1", "filename": "x.txt"}]},
            ])
            conversation = collect_codex_sessions(explicit_home=home).conversations[0]
            self.assertIsNone(conversation.entries[0].created_at)
            self.assertEqual(conversation.entries[0].attachments[0].id, "f1")

    def test_hidden_codex_metadata_is_not_serialized_into_visible_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._session(home, "one.jsonl", [
                {"type": "session_meta", "payload": {"id": "s", "cwd": "/private/secret", "base_instructions": "HIDDEN"}},
                {"type": "response_item", "payload": {"type": "function_call", "call_id": "c", "name": "visible", "arguments": "SECRET"}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c", "output": {"text": "visible result", "secret": "HIDDEN"}}},
            ])
            conversation = collect_codex_sessions(home).conversations[0]
            self.assertNotIn("cwd", conversation.metadata)
            self.assertNotIn("base_instructions", conversation.metadata)
            self.assertEqual([entry.content for entry in conversation.entries], ["visible", "visible result"])
            self.assertNotIn("SECRET", repr(conversation.entries))

    def test_tool_call_and_result_ids_are_unique_and_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._session(home, "one.jsonl", [
                {"id": "s", "timestamp": "2026-08-26T00:00:00Z"},
                {"type": "response_item", "payload": {"type": "function_call", "call_id": "same", "name": "ls"}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "same", "output": "ok"}},
            ])
            entries = collect_codex_sessions(home).conversations[0].entries
            self.assertEqual(len({entry.id for entry in entries}), 2)
            self.assertNotEqual(entries[0].id, entries[1].id)
            again = collect_codex_sessions(home).conversations[0].entries
            self.assertEqual([entry.id for entry in entries], [entry.id for entry in again])

    def test_colliding_session_metadata_ids_get_deterministic_unique_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._session(home, "a.jsonl", [{"id": "same"}, {"type": "message", "role": "user", "content": "a"}])
            self._session(home, "b.jsonl", [{"id": "same"}, {"type": "message", "role": "user", "content": "b"}])
            result = collect_codex_sessions(home)
            self.assertEqual(len({c.id for c in result.conversations}), 2)
            self.assertTrue(any(error.code == "conversation_id_collision" for error in result.errors))
            first_ids = [c.id for c in result.conversations]
            before_b_c = {c.metadata["session_file"]: c.id for c in result.conversations}
            self._session(home, "0.jsonl", [{"id": "same"}, {"type": "message", "role": "user", "content": "zero"}])
            target = home / "sessions" / "2026" / "08" / "a.jsonl"
            target.write_text(target.read_text(encoding="utf-8").replace('"content": "a"', '"content": "changed"'), encoding="utf-8")
            after = {c.metadata["session_file"]: c.id for c in collect_codex_sessions(home).conversations}
            self.assertEqual(before_b_c["sessions/2026/08/a.jsonl"], after["sessions/2026/08/a.jsonl"])
            self.assertEqual(before_b_c["sessions/2026/08/b.jsonl"], after["sessions/2026/08/b.jsonl"])

    def test_collision_namespace_cannot_overwrite_legitimate_id(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._session(home, "a.jsonl", [{"id": "same"}, {"type": "message", "role": "user", "content": "a"}])
            self._session(home, "b.jsonl", [{"id": "same"}, {"type": "message", "role": "user", "content": "b"}])
            old_fallback = "same-" + hashlib.sha256("sessions/2026/08/a.jsonl".encode()).hexdigest()[:16]
            self._session(home, "c.jsonl", [{"id": old_fallback}, {"type": "message", "role": "user", "content": "c"}])
            result = collect_codex_sessions(home)
            self.assertEqual(len(result.conversations), len({c.id for c in result.conversations}))
            self.assertTrue(all(c.id.startswith("codex-path-") or c.id == old_fallback for c in result.conversations if c.metadata["session_file"] in {"sessions/2026/08/a.jsonl", "sessions/2026/08/b.jsonl", "sessions/2026/08/c.jsonl"}))

    def test_invalid_utf8_is_recoverable_and_later_lines_are_collected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions" / "bad.jsonl"
            path.parent.mkdir()
            path.write_bytes(b'{"id":"s"}\n\xff\n{"type":"message","role":"assistant","content":"later"}\n')
            result = collect_codex_sessions(directory)
            self.assertTrue(any(error.code == "malformed_utf8" for error in result.errors))
            self.assertEqual(result.conversations[0].entries[0].content, "later")
            self.assertEqual(result.errors[0].details.get("conversation_key"), "codex:s")


class ChatGPTCaptureTests(unittest.TestCase):
    def _capture(self, **overrides):
        payload = {"id": "chat-1", "title": "A title", "status": "archived", "source_url": "https://chatgpt.com/c/chat-1",
                   "messages": [{"id": "m1", "role": "user", "content": "hello", "timestamp": None, "branch_id": "main"},
                                {"id": "m2", "role": "assistant", "content": "| x |\n|---|\n| y |", "timestamp": "2026-08-26T00:00:00Z", "branch_id": "main"}],
                   "branches": [{"id": "main", "visible": True}], "attachments": [], "complete": True}
        payload.update(overrides)
        return payload

    def test_contract_validates_branches_markdown_and_status(self):
        self.assertEqual(validate_capture(self._capture())["status"], "archived")
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(status="gone"))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(messages=[{"role": "assistant", "content": ["not text"]}]))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(id="../escape"))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(messages=[{"id": "m", "role": "user", "content": "a"}, {"id": "m", "role": "assistant", "content": "b"}]))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(messages=[{"role": "user", "content": "a", "branch_id": "missing"}]))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(messages=[{"role": "user", "content": "a"}]))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(errors=[{"code": "x", "message": "y", "recoverable": "yes"}]))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(errors=[{"code": "x", "message": "y", "details": []}]))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(source_url="https://evil.example/c/chat-1"))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(foo="hidden"))
        with self.assertRaises(CaptureValidationError): validate_capture(self._capture(complete=True, messages=[]))

    def test_ingestion_copies_local_attachment_and_resumes_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); local = root / "download.bin"; local.write_bytes(b"payload")
            capture = self._capture(attachments=[{"id": "a1", "filename": "download.bin", "media_type": "application/octet-stream", "local_path": str(local)}])
            output = root / "archive"; checkpoint = root / "checkpoint.json"
            first = ingest_capture(capture, output, download_root=root)
            self.assertFalse(first.skipped); self.assertTrue(first.output_path.is_file()); self.assertEqual(json.loads((output / "checkpoints/chatgpt.json").read_text(encoding="utf-8"))["completed"][0]["conversation_id"], "chat-1")
            self.assertTrue(ingest_capture(capture, output, download_root=root).skipped)

    def test_stale_checkpoint_reingests_and_attachment_failure_is_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "archive"; checkpoint = root / "checkpoint.json"
            source = root / "later.txt"
            capture = self._capture(attachments=[{"id": "a", "filename": "later.txt", "local_path": str(source)}])
            first = ingest_capture(capture, output, download_root=root)
            self.assertFalse(first.skipped)
            payload = json.loads(first.output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["checkpoints"][0]["status"], "incomplete")
            source.write_text("available", encoding="utf-8")
            second = ingest_capture(capture, output, download_root=root)
            self.assertFalse(second.skipped)
            changed = json.loads(second.output_path.read_text(encoding="utf-8"))
            self.assertEqual(changed["checkpoints"][0]["status"], "complete")

    def test_attachment_download_root_and_symlink_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); approved = root / "downloads"; approved.mkdir(); source = approved / "x.txt"; source.write_text("x", encoding="utf-8")
            capture = self._capture(attachments=[{"id": "a", "filename": "x.txt", "local_path": str(source)}])
            result = ingest_capture(capture, root / "archive", download_root=approved)
            self.assertTrue(result.output_path.is_file())
            outside = root / "outside.txt"; outside.write_text("outside", encoding="utf-8")
            bad = self._capture(id="chat-2", attachments=[{"id": "a", "filename": "x.txt", "local_path": str(outside)}])
            failed = ingest_capture(bad, root / "archive", download_root=approved)
            self.assertEqual(failed.errors[0].code, "attachment_unavailable")
            hardlink = approved / "hard.txt"; hardlink.hardlink_to(source)
            hard_capture = self._capture(id="chat-hard", attachments=[{"id": "a", "filename": "hard.txt", "local_path": str(hardlink)}])
            hard_result = ingest_capture(hard_capture, root / "archive", download_root=approved)
            self.assertEqual(hard_result.errors[0].code, "attachment_unavailable")
            source_link = approved / "link.txt"; source_link.symlink_to(source)
            link_capture = self._capture(id="chat-link", attachments=[{"id": "a", "filename": "link.txt", "local_path": str(source_link)}])
            link_result = ingest_capture(link_capture, root / "archive", download_root=approved)
            self.assertEqual(link_result.errors[0].code, "attachment_unavailable")
            unsafe_parent = root / "unsafe-parent"; unsafe_parent.symlink_to(root / "outside-dir", target_is_directory=True)
            with self.assertRaises(OSError):
                ingest_capture(self._capture(id="chat-3"), unsafe_parent / "archive")

    def test_checkpoint_hash_change_does_not_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "archive"; checkpoint = root / "checkpoint.json"
            capture = self._capture()
            first = ingest_capture(capture, output)
            changed = dict(capture); changed["messages"] = [*capture["messages"], {"id": "m3", "role": "user", "content": "changed"}]
            second = ingest_capture(changed, output)
            self.assertFalse(first.skipped)
            self.assertFalse(second.skipped)

    def test_incomplete_empty_capture_is_not_checkpointed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._capture(id="empty", complete=False, messages=[])
            result = ingest_capture(capture, root / "archive")
            self.assertFalse(result.skipped)
            self.assertFalse((root / "archive" / "checkpoints" / "chatgpt.json").exists())

    def test_archive_local_checkpoint_version_is_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "archive"
            ingest_capture(self._capture(), output)
            checkpoint = output / "checkpoints/chatgpt.json"
            checkpoint.write_text(json.dumps({"version": 99, "completed": []}))
            with self.assertRaises(CheckpointVersionError):
                ingest_capture(self._capture(), output)

    def test_same_name_attachments_are_content_addressed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one.txt"; first.write_text("one", encoding="utf-8")
            second = root / "two.txt"; second.write_text("two", encoding="utf-8")
            capture = self._capture(attachments=[
                {"id": "a1", "filename": "same.txt", "local_path": str(first)},
                {"id": "a2", "filename": "same.txt", "local_path": str(second)},
            ])
            result = ingest_capture(capture, root / "archive", download_root=root)
            payload = json.loads(result.output_path.read_text(encoding="utf-8"))
            uris = [item["uri"] for item in payload["conversation"]["attachments"]]
            self.assertEqual(len(set(uris)), 2)
            self.assertTrue(all("same-" not in uri for uri in uris))

    def test_missing_attachment_is_recoverable_with_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = self._capture(attachments=[{"id": "a1", "filename": "missing.bin", "url": "https://example.invalid/a"}])
            result = ingest_capture(capture, Path(directory) / "archive")
            payload = json.loads(result.output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["errors"][0]["code"], "attachment_unavailable")
            self.assertIn("not downloaded", payload["errors"][0]["message"])

    def test_cli_exposes_collector_inputs_and_codex_dry_run_counts(self):
        args = build_parser().parse_args(["--source", "codex", "--output", "/tmp/archive", "--codex-home", "/tmp/codex"])
        self.assertEqual(args.codex_home, "/tmp/codex")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._capture_path = root / "capture.json"
            self._capture_path.write_text(json.dumps(self._capture()), encoding="utf-8")
            self.assertEqual(main(["--source", "chatgpt", "--output", str(root / "out"), "--capture", str(self._capture_path), "--dry-run"]), 0)
            self.assertFalse((root / "out" / "checkpoints.json").exists())

    def test_codex_dry_run_returns_partial_failure_for_collection_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "codex"
            path = home / "sessions" / "one.jsonl"; path.parent.mkdir(parents=True)
            path.write_text("not-json\n" + json.dumps({"type": "message", "role": "user", "content": "ok"}) + "\n", encoding="utf-8")
            self.assertEqual(main(["--source", "codex", "--output", str(Path(directory) / "out"), "--codex-home", str(home), "--dry-run"]), 4)

    def test_all_dry_run_aggregates_codex_and_capture_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); home = root / "codex"; (home / "sessions").mkdir(parents=True)
            (home / "sessions" / "bad.jsonl").write_text("not-json\n", encoding="utf-8")
            capture = root / "capture.json"
            capture.write_text(json.dumps(self._capture(errors=[{"code": "capture_warning", "message": "skipped", "recoverable": True}])), encoding="utf-8")
            self.assertEqual(main(["--source", "all", "--output", str(root / "out"), "--codex-home", str(home), "--capture", str(capture), "--dry-run"]), 4)

    def test_all_export_keys_chatgpt_errors_and_reports_partial_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); home = root / "codex"; (home / "sessions").mkdir(parents=True)
            (home / "sessions" / "ok.jsonl").write_text(json.dumps({"id": "codex-1", "type": "message", "role": "user", "content": "ok"}) + "\n", encoding="utf-8")
            capture = root / "capture.json"
            capture.write_text(json.dumps(self._capture(id="chat-err", errors=[{"code": "capture_warning", "message": "capture incomplete", "recoverable": True}])), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["--source", "all", "--output", str(root / "out"), "--codex-home", str(home), "--capture", str(capture)]), 4)
            summary = json.loads(output.getvalue().strip().splitlines()[-1])
            self.assertGreater(summary["error_count"], 0)
            archive = Path(summary["archive_path"])
            payload = json.loads((archive / "conversations/chatgpt/chat-err.json").read_text())
            self.assertTrue(payload["errors"])
            self.assertTrue(json.loads((archive / "errors.json").read_text())["errors"])

    def test_chrome_ingest_script_reports_invalid_capture_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); capture = root / "bad.json"; capture.write_text("{}", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(Path(__file__).parents[1] / "scripts" / "chrome_capture_ingest.py"), "--capture", str(capture), "--output", str(root / "out")], text=True, capture_output=True)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn("Traceback", proc.stderr)

    def test_cli_invalid_capture_id_returns_controlled_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); capture = root / "bad.json"
            capture.write_text(json.dumps(self._capture(id="../escape")), encoding="utf-8")
            self.assertEqual(main(["--source", "chatgpt", "--output", str(root / "out"), "--capture", str(capture)]), 3)


if __name__ == "__main__": unittest.main()
