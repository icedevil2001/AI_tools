from pathlib import Path
from socket import gethostname

from codex_usage_collector.collector import run_collection
from codex_usage_collector.config import AppConfig, HostConfig, LocalConfig, StorageConfig


class FakeSSHClient:
    def __init__(self, host_config: HostConfig) -> None:
        self.host_config = host_config

    def __enter__(self) -> "FakeSSHClient":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def list_json_files(self, remote_path: str) -> list[str]:
        return [f"{remote_path}/session.json"]

    def read_file(self, remote_path: str) -> str:
        return (
            '{"id":"session-1","model":"gpt-4o","created_at":"2026-05-01T10:11:12Z",'
            '"usage":{"input_tokens":4,"output_tokens":6,"total_tokens":10}}'
        )


class FailingSSHClient:
    def __init__(self, host_config: HostConfig) -> None:
        self.host_config = host_config

    def __enter__(self) -> "FailingSSHClient":
        raise OSError("could not resolve host")

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def list_json_files(self, remote_path: str) -> list[str]:
        return []

    def read_file(self, remote_path: str) -> str:
        return ""


def test_run_collection_writes_deduped_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("codex_usage_collector.collector.RemoteSSHClient", FakeSSHClient)
    config = AppConfig(
        hosts=[HostConfig(hostname="machine1", user="alice", key_path=tmp_path / "id_rsa")],
        paths=["~/.codex/sessions", "~/.codex/archived_sessions"],
        storage=StorageConfig(type="parquet", path=tmp_path / "usage.parquet"),
    )

    result, before_count, after_count = run_collection(config)

    assert before_count == 0
    assert after_count == 1
    assert len(result.records) == 2
    assert result.host_stats[0].files_seen == 2
    assert result.host_stats[0].records_added == 2


def test_run_collection_supports_optional_ssh_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("codex_usage_collector.collector.RemoteSSHClient", FakeSSHClient)
    config = AppConfig(
        hosts=[HostConfig(hostname="ssh-alias")],
        paths=["~/.codex/sessions"],
        storage=StorageConfig(type="parquet", path=tmp_path / "usage.parquet"),
    )

    result, before_count, after_count = run_collection(config)

    assert before_count == 0
    assert after_count == 1
    assert result.host_stats[0].hostname == "ssh-alias"


def test_run_collection_includes_local_machine_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("codex_usage_collector.collector.RemoteSSHClient", FakeSSHClient)
    local_sessions = tmp_path / "sessions"
    local_sessions.mkdir()
    (local_sessions / "session.json").write_text(
        '{"id":"local-session","model":"gpt-5.4","created_at":"2026-05-01T10:11:12Z",'
        '"usage":{"input_tokens":7,"output_tokens":8,"total_tokens":15}}',
        encoding="utf-8",
    )
    config = AppConfig(
        hosts=[HostConfig(hostname="machine1", user="alice", key_path=tmp_path / "id_rsa")],
        paths=["~/.codex/sessions"],
        local=LocalConfig(enabled=True, hostname="local-dev", paths=[str(local_sessions)]),
        storage=StorageConfig(type="parquet", path=tmp_path / "usage.parquet"),
    )

    result, before_count, after_count = run_collection(config)

    assert before_count == 0
    assert after_count == 2
    assert {record.host for record in result.records} == {"machine1", "local-dev"}
    assert {stats.hostname for stats in result.host_stats} == {"machine1", "local-dev"}


def test_run_collection_defaults_local_hostname_when_not_configured(tmp_path: Path) -> None:
    local_sessions = tmp_path / "sessions"
    local_sessions.mkdir()
    (local_sessions / "session.json").write_text(
        '{"id":"local-session","model":"gpt-5.4","created_at":"2026-05-01T10:11:12Z",'
        '"usage":{"input_tokens":7,"output_tokens":8,"total_tokens":15}}',
        encoding="utf-8",
    )
    config = AppConfig(
        hosts=[],
        paths=["unused"],
        local=LocalConfig(enabled=True, paths=[str(local_sessions)]),
        storage=StorageConfig(type="parquet", path=tmp_path / "usage.parquet"),
    )

    result, _, _ = run_collection(config)

    assert result.records[0].host == gethostname()


def test_run_collection_continues_to_local_when_remote_connection_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("codex_usage_collector.collector.RemoteSSHClient", FailingSSHClient)
    local_sessions = tmp_path / "sessions"
    local_sessions.mkdir()
    (local_sessions / "session.json").write_text(
        '{"id":"local-session","model":"gpt-5.4","created_at":"2026-05-01T10:11:12Z",'
        '"usage":{"input_tokens":7,"output_tokens":8,"total_tokens":15}}',
        encoding="utf-8",
    )
    config = AppConfig(
        hosts=[HostConfig(hostname="bad-host")],
        paths=["~/.codex/sessions"],
        local=LocalConfig(enabled=True, hostname="local-dev", paths=[str(local_sessions)]),
        storage=StorageConfig(type="parquet", path=tmp_path / "usage.parquet"),
    )

    result, _, after_count = run_collection(config)

    assert after_count == 1
    assert [record.host for record in result.records] == ["local-dev"]
    failed_remote = next(stat for stat in result.host_stats if stat.hostname == "bad-host")
    assert failed_remote.read_failures == 1


def test_run_collection_does_not_warn_for_valid_sessions_without_usage(
    tmp_path: Path, monkeypatch
) -> None:
    local_sessions = tmp_path / "sessions"
    local_sessions.mkdir()
    (local_sessions / "session.jsonl").write_text(
        "\n".join(
            [
                '{"id":"session-without-usage","timestamp":"2025-09-08T20:18:12.186Z","instructions":null}',
                '{"record_type":"state"}',
                '{"type":"message","role":"user","content":[{"type":"input_text","text":"hi"}]}',
            ]
        ),
        encoding="utf-8",
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        "codex_usage_collector.collector.logger.warning",
        lambda message, *args: warnings.append(message.format(*args)),
    )
    config = AppConfig(
        hosts=[],
        paths=["unused"],
        local=LocalConfig(enabled=True, hostname="local-dev", paths=[str(local_sessions)]),
        storage=StorageConfig(type="parquet", path=tmp_path / "usage.parquet"),
    )

    result, _, after_count = run_collection(config)

    assert after_count == 0
    assert result.host_stats[0].parse_failures == 0
    assert warnings == []
