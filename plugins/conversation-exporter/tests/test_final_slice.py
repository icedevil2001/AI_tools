import json
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_exporter.models import Attachment, Conversation, Entry, Error
from conversation_exporter.redaction import REDACTION_RULE_VERSION, redact_text
from conversation_exporter.rendering import render_json, render_markdown
from conversation_exporter.archive import export_archive, verify_archive, ArchiveVersionError, safe_remove_generated_tree
from conversation_exporter.archive import new_run_root
import conversation_exporter.archive as archive_module
from conversation_exporter.cli import build_parser


class RedactionTests(unittest.TestCase):
    def test_redacts_known_credentials_with_typed_placeholders_and_counts(self):
        text = "key sk-proj-abcdefghijklmnopqrstuvwxyz123456 password='hunter2' Authorization: Bearer eyJabc.DEFghi"
        redacted, report = redact_text(text)
        self.assertNotIn("sk-proj-abcdefghijklmnopqrstuvwxyz123456", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("eyJabc.DEFghi", redacted)
        self.assertIn("[REDACTED:openai_api_key]", redacted)
        self.assertIn("[REDACTED:password]", redacted)
        self.assertIn("[REDACTED:bearer_token]", redacted)
        self.assertGreaterEqual(report.counts["openai_api_key"], 1)
        self.assertEqual(report.rule_version, REDACTION_RULE_VERSION)

    def test_does_not_redact_boundaries_or_prose(self):
        redacted, report = redact_text("tokenization, secretive, sk-short, password reset instructions")
        self.assertEqual(redacted, "tokenization, secretive, sk-short, password reset instructions")
        self.assertEqual(sum(report.counts.values()), 0)

    def test_existing_placeholder_is_idempotent_and_not_counted(self):
        redacted, report = redact_text("password=[REDACTED:password]")
        self.assertEqual(redacted, "password=[REDACTED:password]")
        self.assertEqual(sum(report.counts.values()), 0)

    def test_structured_quoted_assignments_are_redacted(self):
        redacted, report = redact_text('{"api_key": "super-secret-value", "password": \'pw-value\'}')
        self.assertNotIn("super-secret-value", redacted)
        self.assertNotIn("pw-value", redacted)
        self.assertGreaterEqual(report.counts["api_key"], 1)

    def test_public_renderers_redact_by_default(self):
        conversation = Conversation("safe", "T", "codex", entries=(Entry("m", "user", "password=hunter2"),))
        self.assertNotIn("hunter2", json.dumps(render_json(conversation)))
        self.assertNotIn("hunter2", render_markdown(conversation))


class RenderingTests(unittest.TestCase):
    def test_rendering_preserves_order_timestamps_branches_actions_and_links(self):
        conversation = Conversation(
            id="abc", source="codex", title="T", entries=(
                Entry("1", "user", "hello", "2026-01-01T00:00:00Z", metadata={"branch_id": "main"}),
                Entry("2", "tool_call", "ls", "2026-01-01T00:01:00Z", metadata={"name": "ls", "branch_id": "main"}),
                Entry("3", "assistant", "result", "2026-01-01T00:02:00Z", metadata={"branch_id": "main"}),
            ), attachments=(Attachment("a", "note.txt", "text/plain", "assets/abc/hash.txt"),),
            metadata={"branches": [{"id": "main", "visible": True}], "status": "incomplete"},
        )
        payload = render_json(conversation, checkpoints=[{"status": "incomplete"}], errors=[Error("x", "failed")])
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual([e["role"] for e in payload["conversation"]["entries"]], ["user", "tool_call", "assistant"])
        md = render_markdown(conversation, checkpoints=[{"status": "incomplete"}], errors=[Error("x", "failed")])
        self.assertLess(md.index("hello"), md.index("ls"))
        self.assertIn("[note.txt](../../assets/abc/hash.txt)", md)
        self.assertIn("incomplete", md.lower())

    def test_action_arguments_are_rendered(self):
        conversation = Conversation("action", "T", "codex", entries=(Entry("a", "tool_call", "run", metadata={"arguments": {"path": "x"}}),))
        self.assertIn('"path": "x"', render_markdown(conversation))

    def test_entry_attachments_render_and_are_redacted_or_marked_binary(self):
        conversation = Conversation(
            id="entry-att", source="chatgpt", entries=(Entry(
                "m", "user", "hello", attachments=(
                    Attachment("t", "secret.txt", "text/plain", "assets/entry-att/t.txt", metadata={"note": "password=hunter2"}),
                    Attachment("b", "image.bin", "application/octet-stream", "assets/entry-att/b.bin"),
                ),
            ),),
        )
        md = render_markdown(conversation)
        self.assertIn("secret.txt", md)
        self.assertIn("image.bin", md)


class ArchiveTests(unittest.TestCase):
    def test_sequential_incremental_exports_retain_exactly_one_backup(self):
        conversation = Conversation("retained", "Title", "codex", entries=(Entry("m", "user", "ok"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, [conversation])
            export_archive(root, [conversation])
            export_archive(root, [conversation])
            backups = sorted(path for path in root.parent.iterdir() if re.fullmatch(r"\.archive\.backup-[0-9a-f]{16}-[0-9a-f]{32}", path.name))
            self.assertEqual(len(backups), 1)
            self.assertTrue(verify_archive(backups[0])["valid"])

    def test_generated_tree_cleanup_refuses_symlink_hardlink_and_similar_names(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            outside = parent / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            owner = "c" * 16
            symlink_tree = parent / (".archive.backup-" + owner + "-" + "a" * 32)
            symlink_tree.mkdir()
            (symlink_tree / "link").symlink_to(outside)
            with self.assertRaises(OSError):
                safe_remove_generated_tree(symlink_tree, parent, "backup", expected_owner=owner)
            self.assertTrue(symlink_tree.exists())
            hardlink_tree = parent / (".archive.stage-" + owner + "-" + "b" * 32)
            hardlink_tree.mkdir()
            (hardlink_tree / "hard").hardlink_to(outside)
            with self.assertRaises(OSError):
                safe_remove_generated_tree(hardlink_tree, parent, "stage", expected_owner=owner)
            self.assertTrue(hardlink_tree.exists())
            similar = parent / ".archive.backup-not-a-uuid"
            similar.mkdir()
            with self.assertRaises(OSError):
                safe_remove_generated_tree(similar, parent, "backup", expected_owner=owner)
            self.assertTrue(similar.exists())

    def test_late_build_failure_preserves_incremental_root_and_cleans_stage(self):
        conversation = Conversation("atomic", "Title", "codex", entries=(Entry("m", "user", "before"),))
        replacement = Conversation("atomic", "Title", "codex", entries=(Entry("m", "user", "after"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, [conversation], mode="incremental")
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            original_write = archive_module.atomic_write_text

            def fail_index(path, value):
                if Path(path).name == "index.md":
                    raise OSError("injected late build failure")
                return original_write(path, value)

            with mock.patch("conversation_exporter.archive.atomic_write_text", side_effect=fail_index):
                with self.assertRaises(OSError):
                    export_archive(root, [replacement], mode="incremental")
            after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(any(path.name.startswith(".archive.stage-") for path in root.parent.iterdir()))

    def test_publish_failure_restores_incremental_root_and_cleans_stage(self):
        conversation = Conversation("atomic", "Title", "codex", entries=(Entry("m", "user", "before"),))
        replacement = Conversation("atomic", "Title", "codex", entries=(Entry("m", "user", "after"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, [conversation], mode="incremental")
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            real_replace = archive_module.os.replace
            failed = False

            def fail_publish(source, destination):
                nonlocal failed
                if Path(destination) == root and ".stage-" in Path(source).name and not failed:
                    failed = True
                    raise OSError("injected publish failure")
                return real_replace(source, destination)

            with mock.patch("conversation_exporter.archive.os.replace", side_effect=fail_publish):
                with self.assertRaises(OSError):
                    export_archive(root, [replacement], mode="incremental")
            after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(any(path.name.startswith(".archive.stage-") for path in root.parent.iterdir()))

    def test_concurrent_snapshot_exports_get_unique_final_roots(self):
        conversation = Conversation("same", "Title", "codex", entries=(Entry("m", "user", "ok"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            timestamp = datetime(2026, 8, 26, tzinfo=timezone.utc)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: export_archive(root, [conversation], mode="snapshot", timestamp=timestamp), range(4)))
            paths = [result["archive_path"] for result in results]
            self.assertEqual(len(paths), len(set(paths)))
            self.assertTrue(all(verify_archive(path)["valid"] for path in paths))

    def test_snapshot_symlinked_final_candidate_is_rejected(self):
        conversation = Conversation("candidate", "Title", "codex")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            snapshots = root / "snapshots"
            snapshots.mkdir(parents=True)
            candidate = snapshots / "2026-08-26T000000Z"
            outside = Path(directory) / "outside"
            outside.mkdir()
            candidate.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(OSError):
                export_archive(root, [conversation], mode="snapshot", timestamp=datetime(2026, 8, 26, tzinfo=timezone.utc))

    def test_archive_layout_and_verification(self):
        conversation = Conversation("abc", "Title", "codex", entries=(Entry("m", "user", "hello"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            result = export_archive(root, [conversation], mode="incremental")
            self.assertEqual(result["written"], 1)
            for name in ("manifest.json", "index.json", "index.md", "errors.json"):
                self.assertTrue((root / name).is_file())
            self.assertTrue((root / "conversations" / "codex" / "abc.json").is_file())
            self.assertTrue(verify_archive(root)["valid"])

    def test_snapshot_runs_are_unique_and_manifest_tampering_is_detected(self):
        conversation = Conversation("abc", "Title", "codex", entries=(Entry("m", "user", "hello"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            first = export_archive(root, [conversation], mode="snapshot")
            second = export_archive(root, [conversation], mode="snapshot")
            self.assertNotEqual(first["archive_path"], second["archive_path"])
            manifest = Path(second["archive_path"]) / "manifest.json"
            data = json.loads(manifest.read_text())
            data["archive_version"] = 99
            manifest.write_text(json.dumps(data))
            self.assertFalse(verify_archive(second["archive_path"])["valid"])

    def test_sources_can_share_one_snapshot_run_root(self):
        conversations = [Conversation("a", "A", "codex", entries=(Entry("m", "user", "a"),)), Conversation("b", "B", "chatgpt", entries=(Entry("m", "user", "b"),))]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            run_root = root / "snapshots" / "2026-08-26T120000Z"
            first = export_archive(root, [conversations[0]], mode="snapshot", run_root=run_root)
            second = export_archive(root, [conversations[1]], mode="snapshot", run_root=run_root)
            self.assertEqual(first["archive_path"], second["archive_path"])
            self.assertEqual(len(json.loads((run_root / "index.json").read_text())["conversations"]), 2)

    def test_snapshot_run_root_is_exact_for_resume(self):
        conversation = Conversation("resume", "R", "chatgpt", entries=(Entry("m", "user", "r"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            run_root = new_run_root(root)
            first = export_archive(root, [conversation], mode="snapshot", run_root=run_root)
            second = export_archive(root, [conversation], mode="snapshot", run_root=run_root)
            self.assertEqual(first["archive_path"], str(run_root))
            self.assertEqual(second["skipped"], 1)
            published = [
                path for path in (root / "snapshots").iterdir()
                if path.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{6}Z(?:-\d+)?", path.name)
            ]
            coordination = [path for path in (root / "snapshots").iterdir() if path not in published]
            self.assertEqual(published, [run_root])
            self.assertTrue(all(path.name.startswith(".") for path in coordination))

    def test_absolute_attachment_requires_approved_root(self):
        conversation = Conversation("prov", "P", "chatgpt", attachments=(Attachment("a", "x.txt", "text/plain", "/tmp/not-approved.txt"),))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                export_archive(Path(directory) / "archive", [conversation])

    def test_assets_directory_exists_and_root_checkpoint_does_not(self):
        conversation = Conversation("layout", "L", "codex")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, [conversation])
            self.assertTrue((root / "assets").is_dir())
            self.assertFalse((root / "checkpoints.json").exists())

    def test_unrelated_global_error_does_not_mark_each_conversation(self):
        conversations = [Conversation("a", "A", "codex", entries=(Entry("m", "user", "a"),)), Conversation("b", "B", "codex", entries=(Entry("m", "user", "b"),))]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, conversations)
            result = export_archive(root, conversations, errors=[Error("global", "only a collector warning")])
            self.assertEqual(result["skipped"], 2)
            a = json.loads((root / "conversations/codex/a.json").read_text())
            self.assertEqual(a["conversation"]["id"], "a")

    def test_errors_by_conversation_uses_source_and_id(self):
        conversations = [Conversation("same", "A", "codex", entries=(Entry("m", "user", "a"),)), Conversation("same", "B", "chatgpt", entries=(Entry("m", "user", "b"),))]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, conversations, errors_by_conversation={"chatgpt:same": [Error("only-chatgpt", "chat failure")]})
            codex = json.loads((root / "conversations/codex/same.json").read_text())
            chatgpt = json.loads((root / "conversations/chatgpt/same.json").read_text())
            self.assertFalse(codex["errors"])
            self.assertEqual(chatgpt["errors"][0]["code"], "only-chatgpt")

    def test_incremental_success_rewrites_prior_incomplete_state(self):
        conversation = Conversation("retry", "R", "chatgpt", entries=(Entry("m", "user", "r"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, [conversation], errors_by_conversation={"chatgpt:retry": [Error("temporary", "failed")]})
            result = export_archive(root, [conversation])
            payload = json.loads((root / "conversations/chatgpt/retry.json").read_text())
            self.assertEqual(result["written"], 1)
            self.assertFalse(payload["errors"])
            self.assertEqual(json.loads((root / "manifest.json").read_text())["conversations"][0]["status"], "complete")

    def test_run_root_is_exposed_for_snapshot_resume(self):
        args = build_parser().parse_args(["--source", "chatgpt", "--output", "/tmp/archive", "--run-root", "/tmp/archive/snapshots/run"])
        self.assertEqual(args.run_root, "/tmp/archive/snapshots/run")

    def test_index_markdown_tampering_is_detected(self):
        conversation = Conversation("idx", "Title", "codex", entries=(Entry("m", "user", "hello"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, [conversation])
            (root / "index.md").write_text("tampered\n")
            checked = verify_archive(root)
            self.assertFalse(checked["valid"])

    def test_existing_checkpoint_fields_are_sanitized_and_asset_counts_are_manifested(self):
        conversation = Conversation("cp", "Title", "chatgpt", entries=(Entry("m", "user", "hello"),), attachments=(Attachment("a", "secret.txt", "text/plain", "secret.txt"),))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            (root / "secret.txt").write_text("password=hunter2")
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(json.dumps({"version": 1, "completed": [{"conversation_id": "old", "note": "password=hunter2"}]}))
            result = export_archive(root, [conversation], checkpoints=[{"note": "password=hunter2"}])
            self.assertGreaterEqual(json.loads((root / "manifest.json").read_text())["redaction"]["counts"].get("password", 0), 1)

    def test_missing_archive_version_fails_closed(self):
        conversation = Conversation("version", "V", "codex")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            export_archive(root, [conversation])
            manifest = json.loads((root / "manifest.json").read_text())
            del manifest["archive_version"]
            (root / "manifest.json").write_text(json.dumps(manifest))
            checked = verify_archive(root)
            self.assertFalse(checked["valid"])

    def test_text_sniffing_scans_env_and_readme_but_binary_is_exact(self):
        conversation = Conversation("files", "F", "codex", attachments=(
            Attachment("e", ".env", "", "envfile"),
            Attachment("r", "README", "application/octet-stream", "readmefile"),
            Attachment("b", "blob", "", "binaryfile"),
        ))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            (root).mkdir()
            (root / "envfile").write_text("TOKEN=secret-value\n", encoding="utf-8")
            (root / "readmefile").write_text("password=readme-secret\n", encoding="utf-8")
            binary = b"\x00password=binary-secret\xff"
            (root / "binaryfile").write_bytes(binary)
            export_archive(root, [conversation])
            payload = json.loads((root / "conversations/codex/files.json").read_text())
            atts = payload["conversation"]["attachments"]
            self.assertIn("[REDACTED:token]", (root / atts[0]["uri"]).read_text())
            self.assertIn("[REDACTED:password]", (root / atts[1]["uri"]).read_text())
            self.assertEqual((root / atts[2]["uri"]).read_bytes(), binary)

    def test_archive_rejects_symlinked_components_and_credential_ids_in_paths(self):
        conversation = Conversation("sk-proj-abcdefghijklmnopqrstuvwxyz123456", "T", "codex")
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "real"
            parent.mkdir()
            output = Path(directory) / "link"
            output.symlink_to(parent, target_is_directory=True)
            with self.assertRaises(OSError):
                export_archive(output, [conversation])
            safe = parent / "archive"
            export_archive(safe, [conversation])
            paths = list((safe / "conversations/codex").iterdir())
            self.assertTrue(paths)
            self.assertNotIn("sk-proj-", paths[0].name)

    def test_archive_local_checkpoint_version_missing_is_rejected(self):
        from conversation_exporter.collectors.chatgpt import CheckpointVersionError, ingest_capture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            capture = {"id": "c", "status": "regular", "source_url": "https://chatgpt.com/c/c", "messages": [{"id": "m", "role": "user", "content": "x"}], "complete": True}
            ingest_capture(capture, root)
            (root / "checkpoints/chatgpt.json").write_text(json.dumps({"completed": []}))
            with self.assertRaises(CheckpointVersionError):
                ingest_capture(capture, root)


if __name__ == "__main__":
    unittest.main()
