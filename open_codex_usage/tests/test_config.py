from pathlib import Path

from codex_usage_collector.config import load_config


def test_load_config_expands_key_path_and_resolves_storage(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
hosts:
  - hostname: machine1
    user: alice
    key_path: ~/.ssh/id_test
paths:
  - ~/.codex/sessions
storage:
  type: parquet
  path: ./data/usage.parquet
model_cost:
  url: https://example.invalid/prices.json
credit_mapping:
  path: ./data/credit_mapping.json
credit_limit:
  weekly_limit: 2500
  end_of_week: Friday
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.hosts[0].hostname == "machine1"
    assert config.hosts[0].key_path == Path("~/.ssh/id_test").expanduser()
    assert config.storage.path == (tmp_path / "data" / "usage.parquet").resolve()
    assert config.model_cost.url == "https://example.invalid/prices.json"
    assert config.credit_mapping.path == (tmp_path / "data" / "credit_mapping.json").resolve()
    assert config.credit_limit.weekly_limit == 2500
    assert config.credit_limit.end_of_week == "Friday"
    assert config.credit_limit.reset_time == "00:00"
    assert config.credit_limit.roll_over is False
    assert config.local.enabled is True
    assert config.local.paths is None


def test_load_config_parses_credit_rollover_and_reset_time(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
hosts: []
paths:
  - ~/.codex/sessions
local:
  enabled: true
storage:
  type: parquet
  path: ./data/usage.parquet
credit_limit:
  weekly_limit: 2500
  end_of_week: Friday, 16:50
  roll_over: true
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.credit_limit.weekly_limit == 2500
    assert config.credit_limit.end_of_week == "Friday"
    assert config.credit_limit.reset_time == "16:50"
    assert config.credit_limit.roll_over is True


def test_load_config_allows_ssh_alias_only(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
hosts:
  - hostname: sfprom04
paths:
  - ~/.codex/sessions
storage:
  type: parquet
  path: ./data/usage.parquet
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.hosts[0].hostname == "sfprom04"
    assert config.hosts[0].user is None
    assert config.hosts[0].key_path is None
    assert config.hosts[0].port is None


def test_load_config_parses_local_collection_override(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
hosts:
  - hostname: sfprom04
paths:
  - ~/.codex/sessions
local:
  enabled: true
  hostname: workstation
  paths:
    - ./local-sessions
storage:
  type: parquet
  path: ./data/usage.parquet
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.local.enabled is True
    assert config.local.hostname == "workstation"
    assert config.local.paths == ["./local-sessions"]


def test_load_config_allows_local_only_collection(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
hosts: []
paths:
  - ~/.codex/sessions
local:
  enabled: true
storage:
  type: parquet
  path: ./data/usage.parquet
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.hosts == []
    assert config.local.enabled is True


def test_load_config_ignores_local_and_none_host_placeholders(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
hosts:
  - hostname: None
  - hostname: local
  - hostname: sfprom04
paths:
  - ~/.codex/sessions
local:
  enabled: true
storage:
  type: parquet
  path: ./data/usage.parquet
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert [host.hostname for host in config.hosts] == ["sfprom04"]
