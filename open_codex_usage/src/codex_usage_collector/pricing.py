from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from loguru import logger

MILLION = 1_000_000
MODEL_ALIASES = {
    "gpt-5-codex": "gpt-5",
    "gpt-5.3-codex": "gpt-5.2-codex",
}


@dataclass(frozen=True)
class ModelPricing:
    input_cost_per_mtoken: float
    cached_input_cost_per_mtoken: float
    output_cost_per_mtoken: float


def load_model_pricing(url: str | None) -> dict[str, ModelPricing]:
    if url is None:
        return {}
    try:
        with urlopen(url, timeout=10) as response:
            raw_data = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        logger.warning("Could not load model pricing from {}: {}", url, exc)
        return {}

    if not isinstance(raw_data, dict):
        return {}

    pricing: dict[str, ModelPricing] = {}
    for model, raw_pricing in raw_data.items():
        if not isinstance(model, str) or not isinstance(raw_pricing, dict):
            continue
        pricing[_normalize_model(model)] = ModelPricing(
            input_cost_per_mtoken=_per_million(raw_pricing.get("input_cost_per_token")),
            cached_input_cost_per_mtoken=_per_million(
                raw_pricing.get("cache_read_input_token_cost"),
                fallback=raw_pricing.get("input_cost_per_token"),
            ),
            output_cost_per_mtoken=_per_million(raw_pricing.get("output_cost_per_token")),
        )
    return pricing


def calculate_cost_usd(
    *,
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    pricing: dict[str, ModelPricing],
) -> float:
    if model is None:
        return 0
    model_pricing = _lookup_pricing(model, pricing)
    if model_pricing is None:
        return 0

    cached = min(max(cached_input_tokens, 0), max(input_tokens, 0))
    non_cached = max(input_tokens - cached, 0)
    output = max(output_tokens, 0)
    return (
        (non_cached / MILLION) * model_pricing.input_cost_per_mtoken
        + (cached / MILLION) * model_pricing.cached_input_cost_per_mtoken
        + (output / MILLION) * model_pricing.output_cost_per_mtoken
    )


def _per_million(value: Any, fallback: Any = None) -> float:
    candidate = value if value is not None else fallback
    if isinstance(candidate, bool):
        return 0
    if isinstance(candidate, int | float):
        return float(candidate) * MILLION
    return 0


def _normalize_model(model: str) -> str:
    return model.strip().lower()


def _lookup_pricing(model: str, pricing: dict[str, ModelPricing]) -> ModelPricing | None:
    normalized = _normalize_model(model)
    direct = pricing.get(normalized)
    if direct is not None and _has_nonzero_pricing(direct):
        return direct
    alias = MODEL_ALIASES.get(normalized)
    if alias is not None:
        alias_pricing = pricing.get(alias)
        if alias_pricing is not None and _has_nonzero_pricing(alias_pricing):
            return alias_pricing
    return direct


def _has_nonzero_pricing(pricing: ModelPricing) -> bool:
    return (
        pricing.input_cost_per_mtoken > 0
        or pricing.cached_input_cost_per_mtoken > 0
        or pricing.output_cost_per_mtoken > 0
    )
