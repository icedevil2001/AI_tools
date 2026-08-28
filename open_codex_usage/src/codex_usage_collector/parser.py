from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from codex_usage_collector.models import UsageRecord


RawUsage = dict[str, int]


def parse_session(json_text: str, source_host: str, source_path: str) -> UsageRecord | None:
    try:
        raw_data = json.loads(json_text)
    except json.JSONDecodeError:
        return _parse_jsonl_session(json_text, source_host, source_path)
    if not isinstance(raw_data, dict):
        return None

    usage = raw_data.get("usage")
    usage_mapping = usage if isinstance(usage, dict) else {}
    timestamp = _parse_timestamp(raw_data.get("created_at"))
    cached_input_tokens = _coerce_int(
        usage_mapping.get("cached_input_tokens", usage_mapping.get("cache_read_input_tokens"))
    )
    return UsageRecord(
        session_id=_optional_string(raw_data.get("id")),
        model=_optional_string(raw_data.get("model")),
        input_tokens=_coerce_int(usage_mapping.get("input_tokens")),
        cached_input_tokens=cached_input_tokens,
        output_tokens=_coerce_int(usage_mapping.get("output_tokens")),
        reasoning_output_tokens=_coerce_int(usage_mapping.get("reasoning_output_tokens")),
        total_tokens=_coerce_int(usage_mapping.get("total_tokens")),
        timestamp=timestamp,
        host=source_host,
        source_path=source_path,
        raw_hash=hashlib.sha256(json_text.encode("utf-8")).hexdigest(),
        reasoning_effort=_extract_reasoning_effort(raw_data),
        cache_hit=_optional_bool(raw_data.get("cache_hit"))
        if _optional_bool(raw_data.get("cache_hit")) is not None
        else cached_input_tokens > 0,
        rate_limit_hit=_extract_rate_limit_hit(raw_data),
        license_type=_extract_license_type(raw_data),
        status=_optional_string(raw_data.get("status")),
        message_count=1 if _coerce_int(usage_mapping.get("total_tokens")) > 0 else 0,
    )


def _parse_jsonl_session(json_text: str, source_host: str, source_path: str) -> UsageRecord | None:
    session_id: str | None = None
    model: str | None = None
    timestamp: datetime | None = None
    previous_total_usage: RawUsage | None = None
    summed_usage: RawUsage = _empty_usage()
    message_count = 0
    reasoning_effort: str | None = None
    cache_hit: bool | None = None
    rate_limit_hit: bool | None = None
    license_type: str | None = None
    status: str | None = None

    for line in json_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        event_type = event.get("type")
        payload = event.get("payload")
        payload_mapping = payload if isinstance(payload, dict) else {}

        if event_type == "session_meta":
            session_id = _optional_string(payload_mapping.get("id")) or session_id
            timestamp = _parse_timestamp(payload_mapping.get("timestamp")) or timestamp
            license_type = license_type or _extract_license_type(payload_mapping)
            status = _optional_string(payload_mapping.get("status")) or status
        elif event_type == "turn_context":
            model = _extract_model(payload_mapping) or model
            reasoning_effort = _extract_reasoning_effort(payload_mapping) or reasoning_effort
            license_type = license_type or _extract_license_type(payload_mapping)
            status = _optional_string(payload_mapping.get("status")) or status
        elif event_type == "event_msg" and payload_mapping.get("type") == "token_count":
            info = payload_mapping.get("info")
            info_mapping = info if isinstance(info, dict) else {}
            delta_usage = _normalize_usage(info_mapping.get("last_token_usage"))
            if isinstance(info, dict):
                total_usage_candidate = info.get("total_token_usage")
                total_usage = _normalize_usage(total_usage_candidate)
                if delta_usage is None and total_usage is not None:
                    delta_usage = _subtract_usage(total_usage, previous_total_usage)
                if total_usage is not None:
                    previous_total_usage = total_usage
                    timestamp = _parse_timestamp(event.get("timestamp")) or timestamp
            if delta_usage is not None and _has_tokens(delta_usage):
                _add_usage(summed_usage, delta_usage)
                message_count += 1
            model = _extract_model({**payload_mapping, "info": info_mapping}) or model
            reasoning_effort = (
                _extract_reasoning_effort(payload_mapping)
                or _extract_reasoning_effort(info_mapping)
                or reasoning_effort
            )
            explicit_cache_hit = _optional_bool(
                payload_mapping.get("cache_hit", info_mapping.get("cache_hit"))
            )
            if explicit_cache_hit is not None:
                cache_hit = explicit_cache_hit
            rate_limit_hit = (
                _extract_rate_limit_hit(payload_mapping)
                if _extract_rate_limit_hit(payload_mapping) is not None
                else rate_limit_hit
            )
            rate_limit_hit = (
                _extract_rate_limit_hit(info_mapping)
                if _extract_rate_limit_hit(info_mapping) is not None
                else rate_limit_hit
            )
            license_type = (
                license_type
                or _extract_license_type(payload_mapping)
                or _extract_license_type(info_mapping)
            )
            status = (
                _optional_string(payload_mapping.get("status"))
                or _optional_string(info_mapping.get("status"))
                or status
            )

    if session_id is None and not _has_tokens(summed_usage):
        return None

    inferred_cache_hit = summed_usage["cached_input_tokens"] > 0
    return UsageRecord(
        session_id=session_id,
        model=model,
        input_tokens=summed_usage["input_tokens"],
        cached_input_tokens=summed_usage["cached_input_tokens"],
        output_tokens=summed_usage["output_tokens"],
        reasoning_output_tokens=summed_usage["reasoning_output_tokens"],
        total_tokens=summed_usage["total_tokens"],
        timestamp=timestamp,
        host=source_host,
        source_path=source_path,
        raw_hash=hashlib.sha256(json_text.encode("utf-8")).hexdigest(),
        reasoning_effort=reasoning_effort,
        cache_hit=cache_hit if cache_hit is not None else inferred_cache_hit,
        rate_limit_hit=rate_limit_hit,
        license_type=license_type,
        status=status,
        message_count=message_count,
    )


def _empty_usage() -> RawUsage:
    return {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }


def _normalize_usage(value: Any) -> RawUsage | None:
    if not isinstance(value, dict):
        return None
    input_tokens = _coerce_int(value.get("input_tokens"))
    cached_input_tokens = _coerce_int(
        value.get("cached_input_tokens", value.get("cache_read_input_tokens"))
    )
    output_tokens = _coerce_int(value.get("output_tokens"))
    reasoning_output_tokens = _coerce_int(value.get("reasoning_output_tokens"))
    total_tokens = _coerce_int(value.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": total_tokens,
    }


def _subtract_usage(current: RawUsage, previous: RawUsage | None) -> RawUsage:
    previous_usage = previous or _empty_usage()
    return {
        key: max(current[key] - previous_usage[key], 0)
        for key in _empty_usage()
    }


def _add_usage(target: RawUsage, delta: RawUsage) -> None:
    for key, value in delta.items():
        target[key] += value


def _has_tokens(usage: RawUsage) -> bool:
    return any(value > 0 for value in usage.values())


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _extract_model(payload: dict[str, Any]) -> str | None:
    direct_model = _optional_string(payload.get("model")) or _optional_string(payload.get("model_name"))
    if direct_model is not None:
        return direct_model
    info = payload.get("info")
    if isinstance(info, dict):
        info_model = _optional_string(info.get("model")) or _optional_string(info.get("model_name"))
        if info_model is not None:
            return info_model
        metadata = info.get("metadata")
        if isinstance(metadata, dict):
            return _optional_string(metadata.get("model"))
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return _optional_string(metadata.get("model"))
    return None


def _extract_reasoning_effort(payload: dict[str, Any]) -> str | None:
    direct = _optional_string(payload.get("reasoning_effort"))
    if direct is not None:
        return direct
    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict):
        effort = _optional_string(reasoning.get("effort"))
        if effort is not None:
            return effort
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return _extract_reasoning_effort(metadata)
    return None


def _extract_rate_limit_hit(payload: dict[str, Any]) -> bool | None:
    for key in ("rate_limit_hit", "hit_rate_limit", "rate_limited"):
        value = _optional_bool(payload.get(key))
        if value is not None:
            return value
    status = _optional_string(payload.get("status"))
    if status is not None and "rate" in status.lower() and "limit" in status.lower():
        return True
    return None


def _extract_license_type(payload: dict[str, Any]) -> str | None:
    for key in ("license_type", "license", "auth_type", "auth_mode", "account_type"):
        value = _optional_string(payload.get(key))
        if value is not None:
            return _normalize_license(value)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return _extract_license_type(metadata)
    return None


def _normalize_license(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"api_key", "apikey", "openai_api_key"}:
        return "api_key"
    if "enterprise" in normalized:
        return "enterprise"
    return normalized
