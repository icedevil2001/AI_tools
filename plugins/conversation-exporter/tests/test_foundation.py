import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PACKAGE_ROOT))

from conversation_exporter.cli import build_parser, main  # noqa: E402
from conversation_exporter.models import Attachment, Conversation, Entry, Error  # noqa: E402
from conversation_exporter.paths import ArchiveMode, resolve_archive_path  # noqa: E402
from conversation_exporter.schema import (  # noqa: E402
    ArchiveValidationError,
    CURRENT_SCHEMA_VERSION,
    SchemaVersionError,
    load_conversation,
)
from conversation_exporter.storage import atomic_write_json, read_json, write_conversation  # noqa: E402


class ModelsTests(unittest.TestCase):
    def test_models_round_trip_to_normalized_dicts(self):
        attachment = Attachment(id="att-1", filename="diagram.png", media_type="image/png")
        entry = Entry(id="entry-1", role="user", content="Please export this", attachments=(attachment,))
        conversation = Conversation(
            id="conv-1", title="A conversation", source="codex", entries=(entry,), attachments=(attachment,)
        )

        restored = Conversation.from_dict(conversation.to_dict())

        self.assertEqual(restored, conversation)
        self.assertEqual(restored.entries[0].attachments[0].filename, "diagram.png")

    def test_error_model_is_serializable(self):
        error = Error(code="collector_error", message="not found", recoverable=True)
        self.assertEqual(error, Error.from_dict(error.to_dict()))

    def test_error_model_rejects_non_boolean_recoverable_values(self):
        with self.assertRaises(TypeError):
            Error.from_dict({"code": "bad", "message": "bad", "recoverable": "false"})


class SchemaTests(unittest.TestCase):
    def test_load_conversation_rejects_unknown_schema_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conversation.json"
            atomic_write_json(path, {"schema_version": CURRENT_SCHEMA_VERSION + 1, "conversation": {}})

            with self.assertRaises(SchemaVersionError):
                load_conversation(path)

    def test_load_conversation_rejects_boolean_schema_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conversation.json"
            atomic_write_json(path, {"schema_version": True, "conversation": {}})

            with self.assertRaises(SchemaVersionError):
                load_conversation(path)

    def test_load_conversation_wraps_malformed_nested_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conversation.json"
            atomic_write_json(
                path,
                {"schema_version": CURRENT_SCHEMA_VERSION, "conversation": {"entries": [None]}},
            )

            with self.assertRaises(ArchiveValidationError) as context:
                load_conversation(path)
            self.assertIn("conversation", str(context.exception))

    def test_load_conversation_rejects_malformed_archive_progress_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conversation.json"
            atomic_write_json(
                path,
                {
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "conversation": {},
                    "checkpoints": [None],
                    "errors": [{"recoverable": "false"}],
                },
            )

            with self.assertRaises(ArchiveValidationError) as context:
                load_conversation(path)
            self.assertIn("checkpoints", str(context.exception))

    def test_write_and_load_conversation_preserves_schema_version(self):
        conversation = Conversation(id="conv-1", title="Title", source="chatgpt")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conversation.json"
            write_conversation(
                path,
                conversation,
                checkpoints=[{"name": "collection", "status": "complete"}],
                errors=[Error(code="partial", message="one attachment skipped")],
            )
            payload = read_json(path)

            self.assertEqual(payload["schema_version"], CURRENT_SCHEMA_VERSION)
            self.assertEqual(payload["checkpoints"][0]["status"], "complete")
            self.assertEqual(payload["errors"][0]["code"], "partial")
            self.assertEqual(load_conversation(path), conversation)


class StorageTests(unittest.TestCase):
    def test_atomic_write_creates_parent_and_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "archive.json"
            atomic_write_json(path, {"ok": True})
            self.assertEqual(read_json(path), {"ok": True})
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_atomic_write_overwrites_existing_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.json"
            atomic_write_json(path, {"version": 1})
            atomic_write_json(path, {"version": 2})
            self.assertEqual(read_json(path), {"version": 2})
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])


class PathsTests(unittest.TestCase):
    def test_snapshot_layout_uses_utc_date(self):
        path = resolve_archive_path(
            "/tmp/archive", "conv-1", ArchiveMode.SNAPSHOT, source="codex", timestamp=datetime(2026, 8, 26, tzinfo=timezone.utc)
        )
        self.assertEqual(path, Path("/tmp/archive/snapshots/2026-08-26T000000Z/conversations/codex/conv-1.json"))

    def test_incremental_layout_is_stable_per_conversation(self):
        path = resolve_archive_path("/tmp/archive", "conv-1", "incremental", source="codex")
        self.assertEqual(path, Path("/tmp/archive/conversations/codex/conv-1.json"))
        with self.assertRaises(ValueError):
            resolve_archive_path("/tmp/archive", "conv-1", "incremental")

    def test_path_rejects_traversal(self):
        with self.assertRaises(ValueError):
            resolve_archive_path("/tmp/archive", "../escape", "snapshot")


class CliTests(unittest.TestCase):
    def test_parser_exposes_source_mode_output_and_flags(self):
        args = build_parser().parse_args(
            ["--source", "codex", "--mode", "incremental", "--output", "/tmp/archive", "--dry-run"]
        )
        self.assertEqual((args.source, args.mode, args.output), ("codex", "incremental", "/tmp/archive"))
        self.assertTrue(args.dry_run)

    def test_dry_run_including_init_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "archive"
            codex_home = Path(directory) / "codex-home"
            (codex_home / "sessions").mkdir(parents=True)
            with patch("conversation_exporter.collectors.codex.Path.home", side_effect=AssertionError("default Codex home must not be used by foundation tests")):
                first_plan = io.StringIO()
                with redirect_stdout(first_plan):
                    self.assertEqual(main(["--source", "codex", "--output", str(output), "--codex-home", str(codex_home), "--init", "--dry-run"]), 0)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(first_plan.getvalue())["conversation_count"], 0)
            self.assertEqual(list(output.rglob("*.json")), [])
            with patch("conversation_exporter.collectors.codex.Path.home", side_effect=AssertionError("default Codex home must not be used by foundation tests")):
                second_plan = io.StringIO()
                with redirect_stdout(second_plan):
                    self.assertEqual(main(["--source", "codex", "--output", str(output), "--codex-home", str(codex_home), "--dry-run"]), 0)
            self.assertEqual(json.loads(second_plan.getvalue())["conversation_count"], 0)

    def test_non_dry_run_returns_nonzero_until_collectors_exist(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = main(["--source", "codex", "--output", directory, "--codex-home", str(Path(directory) / "empty-codex")])
        self.assertNotEqual(result, 0)


class FixtureTests(unittest.TestCase):
    def test_synthetic_fixture_directories_are_present(self):
        fixtures = Path(__file__).parent / "fixtures"
        self.assertTrue((fixtures / "snapshot" / "conversation.json").is_file())
        self.assertTrue((fixtures / "incremental" / "conversation.json").is_file())
        for fixture in (fixtures / "snapshot" / "conversation.json", fixtures / "incremental" / "conversation.json"):
            payload = json.loads(fixture.read_text())
            self.assertIsInstance(payload, dict)
            self.assertEqual(set(payload), {"schema_version", "conversation", "checkpoints", "errors"})
            self.assertIsInstance(payload["checkpoints"], list)
            self.assertIsInstance(payload["errors"], list)


if __name__ == "__main__":
    unittest.main()
