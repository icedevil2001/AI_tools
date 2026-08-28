from datetime import datetime, timezone

import pandas as pd

from codex_usage_collector.credits import load_credit_mapping
from codex_usage_collector.pricing import ModelPricing
from codex_usage_collector.reporting import build_usage_report


def test_build_usage_report_includes_host_breakdown_and_credit_limit() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "session_id": "one",
                "model": "gpt-5.3-codex",
                "input_tokens": 1_000_000,
                "cached_input_tokens": 200_000,
                "output_tokens": 500_000,
                "reasoning_output_tokens": 100_000,
                "total_tokens": 1_500_000,
                "timestamp": datetime(2026, 5, 6, tzinfo=timezone.utc),
                "host": "sfprom04",
                "source_path": "/tmp/one.jsonl",
                "raw_hash": "one",
                "reasoning_effort": "high",
                "cache_hit": True,
                "rate_limit_hit": False,
                "license_type": "enterprise",
                "status": "ok",
                "message_count": 1,
            },
            {
                "session_id": "two",
                "model": "gpt-5.4",
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 50,
                "reasoning_output_tokens": 0,
                "total_tokens": 150,
                "timestamp": datetime(2026, 5, 7, tzinfo=timezone.utc),
                "host": "sfprom03",
                "source_path": "/tmp/two.jsonl",
                "raw_hash": "two",
                "reasoning_effort": "medium",
                "cache_hit": False,
                "rate_limit_hit": True,
                "license_type": "api_key",
                "status": "rate_limited",
                "message_count": 1,
            },
        ]
    )

    report = build_usage_report(
        dataframe,
        days=30,
        interval="weekly",
        credit_rates=load_credit_mapping(None),
        model_pricing={
            "gpt-5.3-codex": ModelPricing(1.25, 0.125, 10),
            "gpt-5.4": ModelPricing(2, 0.2, 12),
        },
        weekly_credit_limit=2500,
    )

    assert len(report.rows) == 1
    row = report.rows[0]
    assert row["hosts"] == 2
    assert row["rate_limit_hits"] == 1
    assert row["cache_hits"] == 1
    assert row["input_tokens"] == 1_000_100
    assert row["cached_input_tokens"] == 200_000
    assert row["non_cached_input_tokens"] == 800_100
    assert "sfprom04" in row["host_breakdown"]
    assert row["host_breakdown"]["sfprom04"]["credits"] > 0
    assert row["host_breakdown"]["sfprom04"]["non_cached_input_tokens"] == 800_000
    assert report.totals["credits"] == row["credits"]
    assert report.credit_limit is not None
    assert report.credit_limit["weekly_limit"] == 2500
    assert report.credit_limit["remaining_percent"] < 100


def test_build_usage_report_can_expand_or_filter_by_host() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "session_id": "one",
                "model": "gpt-5.3-codex",
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 5,
                "reasoning_output_tokens": 0,
                "total_tokens": 15,
                "timestamp": datetime(2026, 5, 6, tzinfo=timezone.utc),
                "host": "sfprom04",
                "source_path": "/tmp/one.jsonl",
                "raw_hash": "one",
            },
            {
                "session_id": "two",
                "model": "gpt-5.4",
                "input_tokens": 20,
                "cached_input_tokens": 0,
                "output_tokens": 10,
                "reasoning_output_tokens": 0,
                "total_tokens": 30,
                "timestamp": datetime(2026, 5, 6, tzinfo=timezone.utc),
                "host": "sfprom03",
                "source_path": "/tmp/two.jsonl",
                "raw_hash": "two",
            },
        ]
    )

    by_host = build_usage_report(
        dataframe,
        days=30,
        interval="daily",
        credit_rates=load_credit_mapping(None),
        model_pricing={},
        by_host=True,
    )
    filtered = build_usage_report(
        dataframe,
        days=30,
        interval="daily",
        credit_rates=load_credit_mapping(None),
        model_pricing={},
        host_filter="sfprom04",
    )

    assert {row["host"] for row in by_host.rows} == {"sfprom04", "sfprom03"}
    assert len(filtered.rows) == 1
    assert set(filtered.rows[0]["host_breakdown"].keys()) == {"sfprom04"}


def test_daily_report_shows_cumulative_remaining_credits_until_week_end() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "session_id": "wednesday",
                "model": "gpt-5.3-codex",
                "input_tokens": 1_000_000,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 1_000_000,
                "timestamp": datetime(2026, 5, 6, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/wednesday.jsonl",
                "raw_hash": "wednesday",
            },
            {
                "session_id": "thursday",
                "model": "gpt-5.3-codex",
                "input_tokens": 1_000_000,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 1_000_000,
                "timestamp": datetime(2026, 5, 7, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/thursday.jsonl",
                "raw_hash": "thursday",
            },
        ]
    )

    report = build_usage_report(
        dataframe,
        days=30,
        interval="daily",
        credit_rates=load_credit_mapping(None),
        model_pricing={},
        weekly_credit_limit=100,
        credit_week_ends_on="Friday",
    )

    assert [row["period_start"] for row in report.rows] == ["2026-05-06", "2026-05-07"]
    assert report.rows[0]["credit_allocated"] == 100
    assert report.rows[0]["credit_used_this_week"] == 43.75
    assert report.rows[0]["credit_remaining"] == 56.25
    assert report.rows[1]["credit_used_this_week"] == 87.5
    assert report.rows[1]["credit_remaining"] == 12.5
    assert report.rows[1]["credit_remaining_percent"] == 12.5


def test_daily_report_applies_reset_time_and_rollover() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "session_id": "before-reset",
                "model": "gpt-5.3-codex",
                "input_tokens": 1_000_000,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 1_000_000,
                "timestamp": datetime(2026, 5, 8, 16, 0, 0, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/before.jsonl",
                "raw_hash": "before-reset",
            },
            {
                "session_id": "after-reset",
                "model": "gpt-5.3-codex",
                "input_tokens": 1_000_000,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 1_000_000,
                "timestamp": datetime(2026, 5, 8, 17, 0, 0, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/after.jsonl",
                "raw_hash": "after-reset",
            },
        ]
    )

    report = build_usage_report(
        dataframe,
        days=None,
        interval="daily",
        credit_rates=load_credit_mapping(None),
        model_pricing={},
        weekly_credit_limit=100,
        credit_week_ends_on="Friday",
        credit_reset_time="16:50",
        credit_roll_over=True,
    )

    assert len(report.rows) == 1
    assert report.rows[0]["credit_allocated"] == 200
    assert report.rows[0]["credit_used_this_week"] == 87.5
    assert report.rows[0]["credit_remaining"] == 112.5
    assert report.rows[0]["credit_remaining_percent"] == 112.5


def test_monthly_report_rolls_over_weekly_allocations() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "session_id": "week-one",
                "model": "gpt-5.3-codex",
                "input_tokens": 1_000_000,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 1_000_000,
                "timestamp": datetime(2026, 5, 1, 17, 0, 0, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/week-one.jsonl",
                "raw_hash": "week-one",
            },
            {
                "session_id": "week-two",
                "model": "gpt-5.3-codex",
                "input_tokens": 1_000_000,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 1_000_000,
                "timestamp": datetime(2026, 5, 8, 17, 0, 0, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/week-two.jsonl",
                "raw_hash": "week-two",
            },
        ]
    )

    report = build_usage_report(
        dataframe,
        days=None,
        interval="monthly",
        credit_rates=load_credit_mapping(None),
        model_pricing={},
        weekly_credit_limit=100,
        credit_week_ends_on="Friday",
        credit_reset_time="16:50",
        credit_roll_over=True,
    )

    assert len(report.rows) == 1
    assert report.rows[0]["credit_allocated"] == 200
    assert report.rows[0]["credits"] == 87.5
    assert report.rows[0]["credit_remaining"] == 112.5


def test_build_usage_report_includes_all_history_when_days_is_none() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "session_id": "old",
                "model": "gpt-5.3-codex",
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 5,
                "reasoning_output_tokens": 0,
                "total_tokens": 15,
                "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/old.jsonl",
                "raw_hash": "old",
            },
            {
                "session_id": "new",
                "model": "gpt-5.3-codex",
                "input_tokens": 20,
                "cached_input_tokens": 0,
                "output_tokens": 10,
                "reasoning_output_tokens": 0,
                "total_tokens": 30,
                "timestamp": datetime.now(timezone.utc),
                "host": "local",
                "source_path": "/tmp/new.jsonl",
                "raw_hash": "new",
            },
        ]
    )

    report = build_usage_report(
        dataframe,
        days=None,
        interval="daily",
        credit_rates=load_credit_mapping(None),
        model_pricing={},
    )

    assert [row["period_start"] for row in report.rows][0] == "2026-01-01"
    assert report.totals["sessions"] == 2


def test_build_usage_report_can_group_by_session() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "session_id": "session-a",
                "model": "gpt-5.5",
                "input_tokens": 100,
                "cached_input_tokens": 20,
                "output_tokens": 10,
                "reasoning_output_tokens": 2,
                "total_tokens": 110,
                "timestamp": datetime(2026, 5, 8, 9, 0, 0, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/session-a.jsonl",
                "raw_hash": "session-a",
            },
            {
                "session_id": "session-b",
                "model": "gpt-5.4",
                "input_tokens": 200,
                "cached_input_tokens": 40,
                "output_tokens": 20,
                "reasoning_output_tokens": 4,
                "total_tokens": 220,
                "timestamp": datetime(2026, 5, 8, 10, 0, 0, tzinfo=timezone.utc),
                "host": "local",
                "source_path": "/tmp/session-b.jsonl",
                "raw_hash": "session-b",
            },
        ]
    )

    report = build_usage_report(
        dataframe,
        days=None,
        interval="session",
        credit_rates=load_credit_mapping(None),
        model_pricing={},
    )

    assert [row["period_start"] for row in report.rows] == ["session-a", "session-b"]
    assert report.rows[0]["session_file"] == "/tmp/session-a.jsonl"
    assert report.rows[0]["non_cached_input_tokens"] == 80
