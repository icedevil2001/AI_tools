from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MILLION = 1_000_000


@dataclass(frozen=True)
class CreditRate:
    input: float
    cached_input: float
    output: float


DEFAULT_CREDIT_MAPPING: dict[str, CreditRate] = {
    "gpt-5.5": CreditRate(input=125, cached_input=12.5, output=750),
    "gpt-5.4": CreditRate(input=62.5, cached_input=6.25, output=375),
    "gpt-5.4-mini": CreditRate(input=18.75, cached_input=1.875, output=113),
    "gpt-5.3-codex": CreditRate(input=43.75, cached_input=4.375, output=350),
    "gpt-5.2": CreditRate(input=43.75, cached_input=4.375, output=350),
    "gpt-5.2-codex": CreditRate(input=43.75, cached_input=4.375, output=350),
}


def load_credit_mapping(path: Path | None) -> dict[str, CreditRate]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return DEFAULT_CREDIT_MAPPING

    with path.open("r", encoding="utf-8") as handle:
        raw_mapping = json.load(handle)
    if not isinstance(raw_mapping, dict):
        raise ValueError(f"Credit mapping root must be a mapping: {path}")

    parsed = DEFAULT_CREDIT_MAPPING.copy()
    for model, raw_rate in raw_mapping.items():
        if not isinstance(model, str):
            continue
        rate = _parse_rate(raw_rate)
        if rate is not None:
            parsed[_normalize_model(model)] = rate
    return parsed


def calculate_credits(
    *,
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    rates: dict[str, CreditRate],
) -> float:
    if model is None:
        return 0

    rate = rates.get(_normalize_model(model))
    if rate is None:
        return 0

    cached = min(max(cached_input_tokens, 0), max(input_tokens, 0))
    non_cached = max(input_tokens - cached, 0)
    output = max(output_tokens, 0)
    return (
        (non_cached / MILLION) * rate.input
        + (cached / MILLION) * rate.cached_input
        + (output / MILLION) * rate.output
    )


def _parse_rate(raw_rate: Any) -> CreditRate | None:
    if not isinstance(raw_rate, dict):
        return None
    input_rate = _optional_float(raw_rate.get("input"))
    cached_rate = _optional_float(raw_rate.get("cached_input") or raw_rate.get("cachedInput"))
    output_rate = _optional_float(raw_rate.get("output"))
    if input_rate is None or cached_rate is None or output_rate is None:
        return None
    return CreditRate(input=input_rate, cached_input=cached_rate, output=output_rate)


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _normalize_model(model: str) -> str:
    return model.strip().lower()
