from datetime import datetime, timezone
from pathlib import Path

from click.testing import CliRunner

from codex_usage_collector.main import cli
from codex_usage_collector.models import UsageRecord
from codex_usage_collector.storage import load_existing, merge_dedupe, save_parquet


def test_report_json_includes_rows_host_breakdown_and_totals(tmp_path: Path) -> None:
    data_path = tmp_path / "usage.parquet"
    config_path = tmp_path / "config.yaml"
    save_parquet(
        merge_dedupe(
            load_existing(data_path),
            [
                UsageRecord(
                    session_id="one",
                    model="gpt-5.3-codex",
                    input_tokens=1_000_000,
                    cached_input_tokens=0,
                    output_tokens=500_000,
                    reasoning_output_tokens=0,
                    total_tokens=1_500_000,
                    timestamp=datetime.now(timezone.utc),
                    host="sfprom04",
                    source_path="/tmp/one.jsonl",
                    raw_hash="one",
                )
            ],
        ),
        data_path,
    )
    config_path.write_text(
        f"""
hosts:
  - hostname: sfprom04
paths:
  - ~/.codex/sessions
storage:
  type: parquet
  path: {data_path}
credit_limit:
  weekly_limit: 2500
""".strip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["report", "--config", str(config_path), "--json"])

    assert result.exit_code == 0
    assert '"rows"' in result.output
    assert '"host_breakdown"' in result.output
    assert '"totals"' in result.output


def test_report_by_host_and_show_tokens_renders_host_column(tmp_path: Path) -> None:
    data_path = tmp_path / "usage.parquet"
    config_path = tmp_path / "config.yaml"
    save_parquet(
        merge_dedupe(
            load_existing(data_path),
            [
                UsageRecord(
                    session_id="one",
                    model="gpt-5.3-codex",
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    timestamp=datetime.now(timezone.utc),
                    host="sfprom04",
                    source_path="/tmp/one.jsonl",
                    raw_hash="one",
                )
            ],
        ),
        data_path,
    )
    config_path.write_text(
        f"""
hosts:
  - hostname: sfprom04
paths:
  - ~/.codex/sessions
storage:
  type: parquet
  path: {data_path}
""".strip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli,
        ["report", "--config", str(config_path), "--show", "tokens", "--by-host"],
    )

    assert result.exit_code == 0
    assert "Host" in result.output
    assert "sfprom04" in result.output
    assert "Total Tokens" in result.output


def test_report_tokens_table_displays_non_cached_input(tmp_path: Path) -> None:
    data_path = tmp_path / "usage.parquet"
    config_path = tmp_path / "config.yaml"
    save_parquet(
        merge_dedupe(
            load_existing(data_path),
            [
                UsageRecord(
                    session_id="one",
                    model="gpt-5.4",
                    input_tokens=4_011_446,
                    cached_input_tokens=3_669_504,
                    output_tokens=30_371,
                    total_tokens=4_041_817,
                    timestamp=datetime.now(timezone.utc),
                    host="local",
                    source_path="/tmp/one.jsonl",
                    raw_hash="one",
                )
            ],
        ),
        data_path,
    )
    config_path.write_text(
        f"""
hosts: []
paths:
  - ~/.codex/sessions
local:
  enabled: true
storage:
  type: parquet
  path: {data_path}
""".strip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["report", "--config", str(config_path), "--show", "tokens"])

    assert result.exit_code == 0
    assert "341,942" in result.output
    assert "3,669,504" in result.output
    assert "4,011,446" not in result.output


def test_report_defaults_to_all_collected_history(tmp_path: Path) -> None:
    data_path = tmp_path / "usage.parquet"
    config_path = tmp_path / "config.yaml"
    save_parquet(
        merge_dedupe(
            load_existing(data_path),
            [
                UsageRecord(
                    session_id="old",
                    model="gpt-5.3-codex",
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    host="local",
                    source_path="/tmp/old.jsonl",
                    raw_hash="old",
                )
            ],
        ),
        data_path,
    )
    config_path.write_text(
        f"""
hosts: []
paths:
  - ~/.codex/sessions
local:
  enabled: true
storage:
  type: parquet
  path: {data_path}
""".strip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["report", "--config", str(config_path), "--show", "tokens"])

    assert result.exit_code == 0
    assert "all collected history" in result.output
    assert "2026-01-01" in result.output


def test_report_supports_session_interval_total_row_and_color(tmp_path: Path) -> None:
    data_path = tmp_path / "usage.parquet"
    config_path = tmp_path / "config.yaml"
    save_parquet(
        merge_dedupe(
            load_existing(data_path),
            [
                UsageRecord(
                    session_id="session-a",
                    model="gpt-5.5",
                    input_tokens=100,
                    cached_input_tokens=20,
                    output_tokens=10,
                    total_tokens=110,
                    timestamp=datetime.now(timezone.utc),
                    host="local",
                    source_path="/tmp/session-a.jsonl",
                    raw_hash="session-a",
                ),
                UsageRecord(
                    session_id="session-b",
                    model="gpt-5.4",
                    input_tokens=200,
                    cached_input_tokens=40,
                    output_tokens=20,
                    total_tokens=220,
                    timestamp=datetime.now(timezone.utc),
                    host="local",
                    source_path="/tmp/session-b.jsonl",
                    raw_hash="session-b",
                ),
            ],
        ),
        data_path,
    )
    config_path.write_text(
        f"""
hosts: []
paths:
  - ~/.codex/sessions
local:
  enabled: true
storage:
  type: parquet
  path: {data_path}
""".strip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli,
        [
            "report",
            "--config",
            str(config_path),
            "--interval",
            "session",
            "--show",
            "tokens",
            "--color",
        ],
        color=True,
    )

    assert result.exit_code == 0
    assert "session-a" in result.output
    assert "Total" in result.output
    assert "240" in result.output
    assert "\x1b[" in result.output
