# Codex Usage Collector

Collect Codex session JSON files from remote hosts over SSH, normalize them, and write a deduplicated Parquet dataset.

## Setup

```bash
uv sync
```

## Usage

```bash
uv run codex-usage collect --config config.yaml
uv run codex-usage report --config config.yaml --interval daily
```

The default source paths are intended to point at remote Codex session directories such as `~/.codex/sessions` and `~/.codex/archived_sessions`.

## Config

Example configuration:

```yaml
hosts:
	- hostname: sfprom04
	  user: youruser # optional if set in ~/.ssh/config
	  key_path: ~/.ssh/id_rsa # optional if set in ~/.ssh/config
	  port: 22 # optional if set in ~/.ssh/config
paths:
	- ~/.codex/sessions
	- ~/.codex/archived_sessions
local:
	enabled: true
	hostname: local-dev # optional; defaults to the local machine hostname
	paths: # optional; defaults to the shared paths above
		- ~/.codex/sessions
storage:
	type: parquet
	path: ./data/usage.parquet
model_cost:
	url: https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
credit_mapping:
	path: ./data/credit_mapping.json
credit_limit:
	weekly_limit: 2500
	end_of_week: Friday, 16:50
	roll_over: true
```

You can set `hostname` to an SSH alias from `~/.ssh/config`. If `user`, `key_path`, or `port` are omitted, the collector will fall back to the SSH config entry and then to normal SSH defaults.

Local collection is enabled by default for YAML configs. Set `local.enabled: false` to collect only from remote hosts. Use `hosts: []` with `local.enabled: true` for local-only collection; entries such as `hostname: None`, `hostname: local`, or `hostname: localhost` are treated as placeholders and ignored rather than opened over SSH.

`credit_mapping.path` points at a JSON file with per-million-token credit rates by model. The bundled default mapping covers current Codex models and is used when the file is missing or empty. `credit_limit.weekly_limit` is the weekly credit allocation. `credit_limit.end_of_week` accepts a weekday or `Weekday, HH:MM` reset schedule, such as `Friday, 16:50`. When `credit_limit.roll_over` is true, unused balance carries forward and each reset adds another weekly allocation.

## Reporting

Use the `report` command to print aggregated usage from the stored Parquet data:

```bash
uv run codex-usage report --config config.yaml --interval daily
uv run codex-usage report --config config.yaml --days 30 --interval daily
uv run codex-usage report --config config.yaml --days 90 --interval weekly
uv run codex-usage report --config config.yaml --days 365 --interval monthly
uv run codex-usage report --config config.yaml --interval session
uv run codex-usage report --config config.yaml --show credits
uv run codex-usage report --config config.yaml --by-host
uv run codex-usage report --config config.yaml --color
uv run codex-usage report --config config.yaml --host sfprom04 --json
```

By default, the report includes all collected history. Add `--days N` to limit the report to a recent window. Use `--interval daily|weekly|monthly|session` to choose the grouping. The report groups by period and prints sessions, host counts, model names, non-cached input tokens, cached input tokens, output tokens, reasoning tokens, total tokens, credits, USD cost, cache hits, rate-limit hits, license types, statuses, and a total row. Use `--show all|tokens|credits|price` to choose table columns. Use `--by-host` for one row per host and period, or `--host HOSTNAME` to filter to a single machine. Use `--color` to colorize headers and the total row. `--json` emits structured rows with nested `host_breakdown`, aggregate `totals`, and credit-limit usage for dashboard ingestion.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
uv run mypy src
```
