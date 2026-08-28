from __future__ import annotations

import json
from socket import gethostname
from typing import Any
from typing import Protocol

from loguru import logger

from codex_usage_collector.config import AppConfig
from codex_usage_collector.config import HostConfig
from codex_usage_collector.local_client import LocalSessionClient
from codex_usage_collector.models import CollectionResult, HostCollectionStats, UsageRecord
from codex_usage_collector.parser import parse_session
from codex_usage_collector.ssh_client import RemoteSSHClient
from codex_usage_collector.storage import load_existing, merge_dedupe, save_parquet


class SessionClient(Protocol):
    def __enter__(self) -> "SessionClient": ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def list_json_files(self, path: str) -> list[str]: ...

    def read_file(self, path: str) -> str: ...


def run_collection(config: AppConfig) -> tuple[CollectionResult, int, int]:
    all_records: list[UsageRecord] = []
    host_stats: list[HostCollectionStats] = []

    for host in config.hosts:
        logger.info("Collecting from {}", host.hostname)
        try:
            records, stats = _collect_from_host(host, config.paths)
        except Exception as exc:
            logger.warning("Failed to connect to {}: {}", host.hostname, exc)
            records = []
            stats = HostCollectionStats(
                hostname=host.hostname,
                files_seen=0,
                records_added=0,
                parse_failures=0,
                read_failures=1,
            )
        all_records.extend(records)
        host_stats.append(stats)

    if config.local.enabled:
        local_hostname = config.local.hostname or gethostname()
        local_paths = config.local.paths or config.paths
        logger.info("Collecting local sessions from {}", local_hostname)
        records, stats = _collect_from_source(
            source_name=local_hostname,
            paths=local_paths,
            client=LocalSessionClient(),
        )
        all_records.extend(records)
        host_stats.append(stats)

    existing_df = load_existing(config.storage.path)
    merged_df = merge_dedupe(existing_df, all_records)
    before_count = len(existing_df.index)
    after_count = len(merged_df.index)
    save_parquet(merged_df, config.storage.path)
    return CollectionResult(records=all_records, host_stats=host_stats), before_count, after_count


def _collect_from_host(host_config: HostConfig, paths: list[str]) -> tuple[list[UsageRecord], HostCollectionStats]:
    return _collect_from_source(
        source_name=host_config.hostname,
        paths=paths,
        client=RemoteSSHClient(host_config),
    )


def _collect_from_source(
    *, source_name: str, paths: list[str], client: SessionClient
) -> tuple[list[UsageRecord], HostCollectionStats]:
    files_seen = 0
    records_added = 0
    parse_failures = 0
    read_failures = 0
    records: list[UsageRecord] = []

    with client:
        for source_path in paths:
            files = client.list_json_files(source_path)
            files_seen += len(files)
            for source_file in files:
                try:
                    content = client.read_file(source_file)
                except Exception as exc:
                    read_failures += 1
                    logger.warning("Failed to read {} on {}: {}", source_file, source_name, exc)
                    continue

                record = parse_session(content, source_name, source_file)
                if record is None:
                    if _contains_valid_json(content):
                        logger.debug(
                            "Skipped session file without token usage {} on {}",
                            source_file,
                            source_name,
                        )
                    else:
                        parse_failures += 1
                        logger.warning(
                            "Skipped malformed session file {} on {}", source_file, source_name
                        )
                    continue

                records.append(record)
                records_added += 1

    stats = HostCollectionStats(
        hostname=source_name,
        files_seen=files_seen,
        records_added=records_added,
        parse_failures=parse_failures,
        read_failures=read_failures,
    )
    return records, stats


def _contains_valid_json(content: str) -> bool:
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError:
        pass

    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            parsed: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return True
    return False
