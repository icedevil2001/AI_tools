from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class UsageRecord:
    session_id: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    timestamp: datetime | None
    host: str
    source_path: str
    raw_hash: str
    cached_input_tokens: int = 0
    reasoning_output_tokens: int = 0
    reasoning_effort: str | None = None
    cache_hit: bool | None = None
    rate_limit_hit: bool | None = None
    license_type: str | None = None
    status: str | None = None
    message_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostCollectionStats:
    hostname: str
    files_seen: int
    records_added: int
    parse_failures: int
    read_failures: int


@dataclass(frozen=True)
class CollectionResult:
    records: list[UsageRecord]
    host_stats: list[HostCollectionStats]
