from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pandas as pd

from codex_usage_collector.credits import CreditRate, calculate_credits
from codex_usage_collector.pricing import ModelPricing, calculate_cost_usd
from codex_usage_collector.storage import period_start_for_interval


@dataclass(frozen=True)
class UsageReport:
    rows: list[dict[str, Any]]
    totals: dict[str, Any]
    credit_limit: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": _json_safe(self.rows),
            "totals": _json_safe(self.totals),
            "credit_limit": _json_safe(self.credit_limit),
        }


def build_usage_report(
    dataframe: pd.DataFrame,
    *,
    days: int | None,
    interval: str,
    credit_rates: dict[str, CreditRate],
    model_pricing: dict[str, ModelPricing],
    weekly_credit_limit: float | None = None,
    credit_week_ends_on: str = "Friday",
    credit_reset_time: str = "00:00",
    credit_roll_over: bool = False,
    by_host: bool = False,
    host_filter: str | None = None,
) -> UsageReport:
    prepared = _prepare_dataframe(
        dataframe,
        days=days,
        interval=interval,
        host_filter=host_filter,
        credit_rates=credit_rates,
        model_pricing=model_pricing,
    )
    if prepared.empty:
        return UsageReport(rows=[], totals=_empty_totals(), credit_limit=_credit_limit(weekly_credit_limit, 0))

    rows: list[dict[str, Any]] = []
    period_groups = prepared.groupby("period_start", sort=False, dropna=False)
    for period_start, period_df in period_groups:
        if by_host:
            for host, host_df in period_df.groupby("host", sort=True, dropna=False):
                rows.append(_build_row(str(period_start), host_df, str(host)))
        else:
            rows.append(_build_row(str(period_start), period_df, None))
    _annotate_credit_limit_rows(
        rows,
        prepared=prepared,
        interval=interval,
        weekly_credit_limit=weekly_credit_limit,
        credit_week_ends_on=credit_week_ends_on,
        credit_reset_time=credit_reset_time,
        credit_roll_over=credit_roll_over,
    )

    totals = _build_totals(prepared)
    return UsageReport(
        rows=rows,
        totals=totals,
        credit_limit=_credit_limit(weekly_credit_limit, float(totals["credits"])),
    )


def _prepare_dataframe(
    dataframe: pd.DataFrame,
    *,
    days: int | None,
    interval: str,
    host_filter: str | None,
    credit_rates: dict[str, CreditRate],
    model_pricing: dict[str, ModelPricing],
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    prepared = dataframe.copy()
    for column, default in _defaults().items():
        if column not in prepared.columns:
            prepared[column] = default  # type: ignore[call-overload]

    prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], errors="coerce", utc=True)
    prepared = prepared.dropna(subset=["timestamp"]).copy()
    if days is not None:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
        prepared = prepared.loc[prepared["timestamp"] >= cutoff].copy()
    if host_filter is not None:
        prepared = prepared.loc[prepared["host"] == host_filter].copy()
    if prepared.empty:
        return prepared

    prepared = prepared.sort_values("timestamp").copy()
    if interval == "session":
        prepared["period_start"] = prepared.apply(_session_period_key, axis=1)
    else:
        prepared["period_start"] = period_start_for_interval(
            prepared["timestamp"], interval
        ).dt.strftime("%Y-%m-%d")
    prepared["cost_usd"] = prepared.apply(
        lambda row: _row_cost(row, model_pricing=model_pricing), axis=1
    )
    prepared["credits"] = prepared.apply(
        lambda row: _row_credits(row, credit_rates=credit_rates), axis=1
    )
    return prepared


def _row_cost(row: pd.Series, *, model_pricing: dict[str, ModelPricing]) -> float:
    return calculate_cost_usd(
        model=_optional_string(row.get("model")),
        input_tokens=_int_value(row.get("input_tokens")),
        cached_input_tokens=_int_value(row.get("cached_input_tokens")),
        output_tokens=_int_value(row.get("output_tokens")),
        pricing=model_pricing,
    )


def _row_credits(row: pd.Series, *, credit_rates: dict[str, CreditRate]) -> float:
    return calculate_credits(
        model=_optional_string(row.get("model")),
        input_tokens=_int_value(row.get("input_tokens")),
        cached_input_tokens=_int_value(row.get("cached_input_tokens")),
        output_tokens=_int_value(row.get("output_tokens")),
        rates=credit_rates,
    )


def _build_row(period_start: str, dataframe: pd.DataFrame, host: str | None) -> dict[str, Any]:
    host_breakdown = {
        str(host_name): _build_totals(host_df)
        for host_name, host_df in dataframe.groupby("host", sort=True, dropna=False)
    }
    row = _build_totals(dataframe)
    row["period_start"] = period_start
    row["host"] = host
    row["session_file"] = _single_value(dataframe["source_path"])
    row["host_breakdown"] = host_breakdown
    return row


def _build_totals(dataframe: pd.DataFrame) -> dict[str, Any]:
    if dataframe.empty:
        return _empty_totals()
    return {
        "sessions": int(dataframe["raw_hash"].nunique()),
        "hosts": int(dataframe["host"].nunique()),
        "last_timestamp": dataframe["timestamp"].max().to_pydatetime(),
        "models": _unique_strings(dataframe["model"]),
        "input_tokens": _sum_int(dataframe["input_tokens"]),
        "cached_input_tokens": _sum_int(dataframe["cached_input_tokens"]),
        "non_cached_input_tokens": _non_cached_input_tokens(dataframe),
        "output_tokens": _sum_int(dataframe["output_tokens"]),
        "reasoning_output_tokens": _sum_int(dataframe["reasoning_output_tokens"]),
        "total_tokens": _sum_int(dataframe["total_tokens"]),
        "credits": float(dataframe["credits"].sum()),
        "cost_usd": float(dataframe["cost_usd"].sum()),
        "cache_hits": _sum_true(dataframe["cache_hit"]),
        "rate_limit_hits": _sum_true(dataframe["rate_limit_hit"]),
        "reasoning_efforts": _unique_strings(dataframe["reasoning_effort"]),
        "license_types": _unique_strings(dataframe["license_type"]),
        "statuses": _unique_strings(dataframe["status"]),
    }


def _empty_totals() -> dict[str, Any]:
    return {
        "sessions": 0,
        "hosts": 0,
        "last_timestamp": None,
        "models": [],
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "non_cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
        "credits": 0.0,
        "cost_usd": 0.0,
        "cache_hits": 0,
        "rate_limit_hits": 0,
        "reasoning_efforts": [],
        "license_types": [],
        "statuses": [],
    }


def _credit_limit(weekly_credit_limit: float | None, used_credits: float) -> dict[str, Any] | None:
    if weekly_credit_limit is None or weekly_credit_limit <= 0:
        return None
    remaining = max(weekly_credit_limit - used_credits, 0)
    return {
        "weekly_limit": weekly_credit_limit,
        "used": used_credits,
        "remaining": remaining,
        "remaining_percent": (remaining / weekly_credit_limit) * 100,
    }


def _annotate_credit_limit_rows(
    rows: list[dict[str, Any]],
    *,
    prepared: pd.DataFrame,
    interval: str,
    weekly_credit_limit: float | None,
    credit_week_ends_on: str,
    credit_reset_time: str,
    credit_roll_over: bool,
) -> None:
    if weekly_credit_limit is None or weekly_credit_limit <= 0:
        return

    ledger = _build_credit_ledger(
        prepared,
        weekly_credit_limit=weekly_credit_limit,
        credit_week_ends_on=credit_week_ends_on,
        credit_reset_time=credit_reset_time,
        credit_roll_over=credit_roll_over,
    )
    for row in rows:
        row_end = _row_period_end(row, interval)
        row.update(_ledger_state_at(ledger, row_end, weekly_credit_limit))


def _set_row_credit_limit(row: dict[str, Any], weekly_credit_limit: float, used_credits: float) -> None:
    remaining = max(weekly_credit_limit - used_credits, 0)
    row["credit_used_this_week"] = used_credits
    row["credit_remaining"] = remaining
    row["credit_remaining_percent"] = (remaining / weekly_credit_limit) * 100


def _build_credit_ledger(
    prepared: pd.DataFrame,
    *,
    weekly_credit_limit: float,
    credit_week_ends_on: str,
    credit_reset_time: str,
    credit_roll_over: bool,
) -> list[dict[str, Any]]:
    reset_time = _parse_time(credit_reset_time)
    ledger_rows = prepared.sort_values("timestamp").copy()
    first_timestamp = ledger_rows["timestamp"].iloc[0].to_pydatetime()
    last_timestamp = ledger_rows["timestamp"].iloc[-1].to_pydatetime()
    reset_points = _reset_points_between(
        first_timestamp,
        last_timestamp,
        week_ends_on=credit_week_ends_on,
        reset_time=reset_time,
    )
    events: list[tuple[datetime, str, float]] = [
        (reset_point, "allocation", weekly_credit_limit) for reset_point in reset_points
    ]
    for _, row in ledger_rows.iterrows():
        events.append((row["timestamp"].to_pydatetime(), "usage", float(row["credits"])))
    events.sort(key=lambda event: (event[0], 0 if event[1] == "allocation" else 1))

    balance = 0.0
    allocated = 0.0
    used = 0.0
    ledger: list[dict[str, Any]] = []
    for event_time, event_type, amount in events:
        if event_type == "allocation":
            allocated += amount
            balance = balance + amount if credit_roll_over else amount
        else:
            used += amount
            balance = max(balance - amount, 0)
        ledger.append(
            {
                "timestamp": event_time,
                "credit_allocated": allocated,
                "credit_used_this_week": used,
                "credit_remaining": balance,
                "credit_remaining_percent": (balance / weekly_credit_limit) * 100,
            }
        )
    return ledger


def _ledger_state_at(
    ledger: list[dict[str, Any]], timestamp: datetime, weekly_credit_limit: float
) -> dict[str, Any]:
    state: dict[str, Any] | None = None
    for item in ledger:
        if item["timestamp"] <= timestamp:
            state = item
        else:
            break
    if state is None:
        return {
            "credit_allocated": weekly_credit_limit,
            "credit_used_this_week": 0.0,
            "credit_remaining": weekly_credit_limit,
            "credit_remaining_percent": 100.0,
        }
    return {key: value for key, value in state.items() if key != "timestamp"}


def _row_period_end(row: dict[str, Any], interval: str) -> datetime:
    timestamp = row.get("last_timestamp")
    if timestamp is not None:
        return pd.Timestamp(timestamp).to_pydatetime()
    if interval == "session":
        return pd.Timestamp(str(row.get("period_start"))).to_pydatetime()
    period_start = date.fromisoformat(str(row["period_start"]))
    return datetime.combine(period_start + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _reset_points_between(
    start: datetime, end: datetime, *, week_ends_on: str, reset_time: time
) -> list[datetime]:
    start_date = start.date() - timedelta(days=7)
    end_date = end.date() + timedelta(days=7)
    reset_weekday = _weekday_index(week_ends_on)
    points: list[datetime] = []
    current = start_date
    while current <= end_date:
        if current.weekday() == reset_weekday:
            reset_at = datetime.combine(current, reset_time, tzinfo=start.tzinfo)
            if reset_at <= end:
                points.append(reset_at)
        current += timedelta(days=1)
    prior_points = [point for point in points if point <= start]
    starting_point = max(prior_points) if prior_points else None
    future_points = [point for point in points if point > start]
    if starting_point is None:
        return future_points
    return [starting_point, *future_points]


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def _credit_week_bounds(value: date, week_ends_on: str) -> tuple[date, date]:
    end_weekday = _weekday_index(week_ends_on)
    start_weekday = (end_weekday + 1) % 7
    days_since_start = (value.weekday() - start_weekday) % 7
    week_start = value - timedelta(days=days_since_start)
    return week_start, week_start + timedelta(days=6)


def _weekday_index(weekday: str) -> int:
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    try:
        return weekdays[weekday.strip().lower()]
    except KeyError as exc:
        raise ValueError("credit_week_ends_on must be a weekday name") from exc


def _defaults() -> dict[str, object]:
    return {
        "cached_input_tokens": 0,
        "reasoning_output_tokens": 0,
        "reasoning_effort": None,
        "cache_hit": None,
        "rate_limit_hit": None,
        "license_type": None,
        "status": None,
        "message_count": 0,
    }


def _sum_int(series: pd.Series) -> int:
    return int(pd.to_numeric(series, errors="coerce").fillna(0).sum())


def _sum_true(series: pd.Series) -> int:
    return int(sum(value is True for value in series))


def _non_cached_input_tokens(dataframe: pd.DataFrame) -> int:
    input_tokens = pd.to_numeric(dataframe["input_tokens"], errors="coerce").fillna(0)
    cached_tokens = pd.to_numeric(dataframe["cached_input_tokens"], errors="coerce").fillna(0)
    return int((input_tokens - cached_tokens).clip(lower=0).sum())


def _unique_strings(series: pd.Series) -> list[str]:
    values = {_optional_string(value) for value in series}
    return sorted(value for value in values if value is not None)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _session_period_key(row: pd.Series) -> str:
    session_id = _optional_string(row.get("session_id"))
    if session_id is not None:
        return session_id
    source_path = _optional_string(row.get("source_path"))
    if source_path is not None:
        return source_path
    return str(row.get("raw_hash", "unknown-session"))


def _single_value(series: pd.Series) -> str | None:
    values = _unique_strings(series)
    if len(values) == 1:
        return values[0]
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
