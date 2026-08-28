from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

from codex_usage_collector.models import UsageRecord


def load_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=_record_columns())
    dataframe = pd.read_parquet(path)
    return _dedupe_records(_ensure_record_columns(dataframe))


def merge_dedupe(existing_df: pd.DataFrame, records: list[UsageRecord]) -> pd.DataFrame:
    new_df = pd.DataFrame([record.to_dict() for record in records], columns=_record_columns())
    if existing_df.empty:
        return _dedupe_records(_ensure_record_columns(new_df))
    if new_df.empty:
        return _dedupe_records(_ensure_record_columns(existing_df))
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    return _dedupe_records(_ensure_record_columns(combined))


def save_parquet(dataframe: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_parquet(path, index=False)


def summarize_usage(path: Path, days: int, interval: str) -> pd.DataFrame:
    dataframe = load_existing(path)
    if dataframe.empty:
        return pd.DataFrame(columns=_summary_columns())

    timestamps = pd.to_datetime(dataframe["timestamp"], errors="coerce", utc=True)
    summary_df = dataframe.assign(timestamp=timestamps).dropna(subset=["timestamp"]).copy()
    if summary_df.empty:
        return pd.DataFrame(columns=_summary_columns())

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    summary_df = summary_df.loc[summary_df["timestamp"] >= cutoff]
    if summary_df.empty:
        return pd.DataFrame(columns=_summary_columns())

    period_values = period_start_for_interval(summary_df["timestamp"], interval)
    grouped = (
        summary_df.assign(period_start=period_values)
        .groupby("period_start", as_index=False)
        .agg(
            sessions=("raw_hash", "nunique"),
            hosts=("host", "nunique"),
            input_tokens=("input_tokens", "sum"),
            cached_input_tokens=("cached_input_tokens", "sum"),
            output_tokens=("output_tokens", "sum"),
            reasoning_output_tokens=("reasoning_output_tokens", "sum"),
            total_tokens=("total_tokens", "sum"),
        )
        .sort_values("period_start")
        .reset_index(drop=True)
    )
    grouped["period_start"] = grouped["period_start"].dt.strftime("%Y-%m-%d")
    return grouped


def _record_columns() -> list[str]:
    return [
        "session_id",
        "model",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "timestamp",
        "host",
        "source_path",
        "raw_hash",
        "reasoning_effort",
        "cache_hit",
        "rate_limit_hit",
        "license_type",
        "status",
        "message_count",
    ]


def _summary_columns() -> list[str]:
    return [
        "period_start",
        "sessions",
        "hosts",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ]


def _ensure_record_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    for column in _record_columns():
        if column not in dataframe.columns:
            dataframe[column] = _default_value_for_column(column)  # type: ignore[call-overload]
    return dataframe[_record_columns()].copy()


def _dedupe_records(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.reset_index(drop=True)

    deduped = dataframe.copy()
    deduped["__timestamp_for_dedupe"] = pd.to_datetime(
        deduped["timestamp"], errors="coerce", utc=True
    )
    deduped = deduped.sort_values("__timestamp_for_dedupe", na_position="first")
    deduped = deduped.drop_duplicates(subset=["raw_hash"], keep="last")
    deduped = deduped.drop_duplicates(subset=["host", "source_path"], keep="last")
    deduped = deduped.drop(columns=["__timestamp_for_dedupe"])
    return deduped.reset_index(drop=True)


def _default_value_for_column(column: str) -> object:
    if column in {
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "message_count",
    }:
        return 0
    if column in {"cache_hit", "rate_limit_hit"}:
        return None
    return None


def period_start_for_interval(series: pd.Series, interval: str) -> pd.Series:
    naive_series = series.dt.tz_convert("UTC").dt.tz_localize(None)
    frequency_map = {"daily": "D", "weekly": "W-MON", "monthly": "M"}
    try:
        frequency = frequency_map[interval]
    except KeyError as exc:
        raise ValueError(f"Unsupported interval: {interval}") from exc
    return cast(pd.Series, naive_series.dt.to_period(frequency).dt.start_time)
