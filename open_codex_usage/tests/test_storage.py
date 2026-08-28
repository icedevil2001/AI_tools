from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

from codex_usage_collector.models import UsageRecord
from codex_usage_collector.storage import load_existing, merge_dedupe, save_parquet, summarize_usage


def test_merge_dedupe_keeps_unique_hashes(tmp_path: Path) -> None:
    path = tmp_path / "usage.parquet"
    first_record = UsageRecord(
        session_id="one",
        model="gpt-4o",
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        timestamp=datetime(2026, 5, 1, 10, 0, 0),
        host="machine1",
        source_path="/tmp/one.json",
        raw_hash="hash-1",
    )
    duplicate_record = UsageRecord(
        session_id="one-again",
        model="gpt-4o",
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        timestamp=datetime(2026, 5, 1, 10, 0, 0),
        host="machine1",
        source_path="/tmp/one-duplicate.json",
        raw_hash="hash-1",
    )

    merged = merge_dedupe(load_existing(path), [first_record, duplicate_record])
    save_parquet(merged, path)

    reloaded = load_existing(path)
    assert len(reloaded.index) == 1
    assert reloaded.iloc[0]["raw_hash"] == "hash-1"


def test_merge_dedupe_keeps_latest_version_of_growing_session_file(tmp_path: Path) -> None:
    path = tmp_path / "usage.parquet"
    early_record = UsageRecord(
        session_id="session-1",
        model="gpt-5.5",
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        timestamp=datetime(2026, 5, 8, 9, 0, 0, tzinfo=timezone.utc),
        host="local",
        source_path="/tmp/session.jsonl",
        raw_hash="early-hash",
    )
    later_record = UsageRecord(
        session_id="session-1",
        model="gpt-5.5",
        input_tokens=200,
        output_tokens=20,
        total_tokens=220,
        timestamp=datetime(2026, 5, 8, 10, 0, 0, tzinfo=timezone.utc),
        host="local",
        source_path="/tmp/session.jsonl",
        raw_hash="later-hash",
    )

    merged = merge_dedupe(load_existing(path), [early_record, later_record])
    save_parquet(merged, path)

    reloaded = load_existing(path)
    assert len(reloaded.index) == 1
    assert reloaded.iloc[0]["raw_hash"] == "later-hash"
    assert int(reloaded.iloc[0]["total_tokens"]) == 220


def test_summarize_usage_groups_recent_records_by_day(tmp_path: Path) -> None:
    path = tmp_path / "usage.parquet"
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord(
            session_id="recent-1",
            model="gpt-4o",
            input_tokens=10,
            output_tokens=15,
            total_tokens=25,
            timestamp=now - timedelta(days=1),
            host="machine1",
            source_path="/tmp/recent-1.json",
            raw_hash="recent-1",
        ),
        UsageRecord(
            session_id="recent-2",
            model="gpt-4o",
            input_tokens=3,
            output_tokens=4,
            total_tokens=7,
            timestamp=now - timedelta(days=1, hours=2),
            host="machine2",
            source_path="/tmp/recent-2.json",
            raw_hash="recent-2",
        ),
        UsageRecord(
            session_id="old",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=200,
            total_tokens=300,
            timestamp=now - timedelta(days=45),
            host="machine1",
            source_path="/tmp/old.json",
            raw_hash="old",
        ),
    ]

    save_parquet(merge_dedupe(load_existing(path), records), path)
    summary = summarize_usage(path, days=30, interval="daily")

    assert len(summary.index) == 1
    assert int(summary.iloc[0]["sessions"]) == 2
    assert int(summary.iloc[0]["hosts"]) == 2
    assert int(summary.iloc[0]["total_tokens"]) == 32
