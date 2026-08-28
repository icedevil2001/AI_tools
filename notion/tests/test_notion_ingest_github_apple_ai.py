import importlib.util
import io
import json
import pathlib
import sys
import types
import unittest
import asyncio
from unittest.mock import patch

from click.testing import CliRunner


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "notion_ingest_github_apple_ai.py"


class FakeLogger:
    def __init__(self):
        self.sink = None

    def remove(self, *args, **kwargs):
        self.sink = None

    def add(self, sink, *args, **kwargs):
        self.sink = sink

    def _write(self, level, message, *args):
        if self.sink is None:
            return
        text = message.format(*args)
        self.sink.write(f"{level}: {text}\n")

    def info(self, message, *args):
        self._write("INFO", message, *args)

    def warning(self, message, *args):
        self._write("WARNING", message, *args)

    def debug(self, message, *args):
        self._write("DEBUG", message, *args)


def load_module():
    sys.modules.pop("notion_ingest_github_apple_ai", None)
    sys.modules.setdefault("apple_fm_sdk", types.SimpleNamespace())
    sys.modules.setdefault(
        "loguru",
        types.SimpleNamespace(logger=FakeLogger()),
    )
    spec = importlib.util.spec_from_file_location("notion_ingest_github_apple_ai", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["notion_ingest_github_apple_ai"] = module
    spec.loader.exec_module(module)
    return module


class TestNotionIngestGithubAppleAi(unittest.TestCase):
    def test_mask_secret_redacts_middle_and_reports_length(self):
        module = load_module()

        self.assertEqual(module.mask_secret("ntn_1234567890"), "ntn_...7890 (len=14)")

    def test_dry_run_prints_preview_before_connection_failure(self):
        module = load_module()
        runner = CliRunner()
        db_obj = {
            "properties": {
                "Tags": {
                    "type": "multi_select",
                    "multi_select": {"options": [{"name": "Genomics"}]},
                }
            }
        }
        stderr = io.StringIO()

        async def fake_ai_generate_notes_and_tags(**kwargs):
            return {
                "notes": "Tool summary",
                "selected_tags": ["Genomics"],
                "confidence": 0.9,
                "suggested_tags": [],
            }

        with patch.object(module, "fetch_github_readme", return_value="README"), \
             patch.object(module, "ai_generate_notes_and_tags", side_effect=fake_ai_generate_notes_and_tags), \
             patch.object(module.NotionClient, "get_database", side_effect=[db_obj, RuntimeError("Notion down")]) as get_db:
            module.logger.remove()
            module.logger.add(stderr, level="INFO")
            result = runner.invoke(
                module.main,
                [
                    "https://github.com/WGLab/LongGF",
                    "--notion-token",
                    "ntn_1234567890",
                    "--database-id",
                    "1234567890abcdef1234567890abcdef",
                    "--dry-run",
                ],
            )

        self.assertNotEqual(result.exit_code, 0)
        preview = json.loads(result.stdout)
        self.assertEqual(preview["Notes"], "Tool summary")
        self.assertEqual(preview["Tags"], ["Genomics"])
        self.assertIn("Dry-run Notion validation failed", result.stderr)
        self.assertEqual(get_db.call_count, 2)

    def test_ai_generate_falls_back_when_schema_generation_fails(self):
        module = load_module()
        calls = []

        class FakeModel:
            def __init__(self, use_case=None):
                self.use_case = use_case

            def is_available(self):
                return True, None

        class FakeSession:
            def __init__(self, model=None, instructions=None):
                self.model = model
                self.instructions = instructions

            async def respond(self, prompt, json_schema=None):
                calls.append({"prompt": prompt, "json_schema": json_schema})
                if json_schema is not None:
                    raise RuntimeError(
                        'Generation error (status: 255): Error NSCocoaErrorDomain:4865 - '
                        'The data couldn’t be read because it is missing. UserInfo: '
                        '["NSDebugDescription": "No value associated with key CodingKeys('
                        'stringValue: \\"x-order\\", intValue: nil) (\\"x-order\\").", '
                        '"NSCodingPath": []]'
                    )
                return json.dumps(
                    {
                        "notes": "LongGF detects long gene fusions from sequencing data.",
                        "selected_tags": ["Genomics"],
                        "confidence": 0.92,
                        "suggested_tags": ["Fusion detection"],
                    }
                )

        module.fm = types.SimpleNamespace(
            SystemLanguageModel=FakeModel,
            SystemLanguageModelUseCase=types.SimpleNamespace(CONTENT_TAGGING="CONTENT_TAGGING"),
            LanguageModelSession=FakeSession,
        )

        result = asyncio.run(
            module.ai_generate_notes_and_tags(
                repo_url="https://github.com/WGLab/LongGF",
                readme="# LongGF\nA tool for long-read gene fusion detection.",
                allowed_tags=["Genomics"],
                timeout_s=1.0,
            )
        )

        self.assertEqual(result["selected_tags"], ["Genomics"])
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(calls[0]["json_schema"])
        self.assertIsNone(calls[1]["json_schema"])

    def test_ai_generate_retries_when_fallback_returns_non_json_text(self):
        module = load_module()
        calls = []

        class FakeModel:
            def __init__(self, use_case=None):
                self.use_case = use_case

            def is_available(self):
                return True, None

        class FakeSession:
            def __init__(self, model=None, instructions=None):
                self.model = model
                self.instructions = instructions

            async def respond(self, prompt, json_schema=None):
                calls.append({"prompt": prompt, "json_schema": json_schema})
                if json_schema is not None:
                    raise RuntimeError("schema unsupported")
                if len(calls) == 2:
                    return "This repository appears to be a bioinformatics tool."
                return json.dumps(
                    {
                        "notes": "LongGF detects long gene fusions from sequencing data.",
                        "selected_tags": ["Genomics"],
                        "confidence": 0.92,
                        "suggested_tags": ["Fusion detection"],
                    }
                )

        module.fm = types.SimpleNamespace(
            SystemLanguageModel=FakeModel,
            SystemLanguageModelUseCase=types.SimpleNamespace(CONTENT_TAGGING="CONTENT_TAGGING"),
            LanguageModelSession=FakeSession,
        )

        result = asyncio.run(
            module.ai_generate_notes_and_tags(
                repo_url="https://github.com/WGLab/LongGF",
                readme="# LongGF\nA tool for long-read gene fusion detection.",
                allowed_tags=["Genomics"],
                timeout_s=1.0,
            )
        )

        self.assertEqual(result["selected_tags"], ["Genomics"])
        self.assertEqual(len(calls), 3)
        self.assertIsNone(calls[1]["json_schema"])
        self.assertIsNone(calls[2]["json_schema"])
        self.assertIn("You did not return valid JSON", calls[2]["prompt"])


if __name__ == "__main__":
    unittest.main()
