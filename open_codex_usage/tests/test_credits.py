from pathlib import Path

from codex_usage_collector.credits import calculate_credits, load_credit_mapping


def test_calculate_credits_uses_cached_input_rate() -> None:
    credits = calculate_credits(
        model="gpt-5.3-codex",
        input_tokens=1_000_000,
        cached_input_tokens=200_000,
        output_tokens=500_000,
        rates=load_credit_mapping(Path("missing.json")),
    )

    expected = (800_000 / 1_000_000) * 43.75
    expected += (200_000 / 1_000_000) * 4.375
    expected += (500_000 / 1_000_000) * 350
    assert credits == expected


def test_calculate_credits_returns_zero_for_unknown_models() -> None:
    credits = calculate_credits(
        model="gpt-unknown",
        input_tokens=1_000_000,
        cached_input_tokens=0,
        output_tokens=500_000,
        rates=load_credit_mapping(Path("missing.json")),
    )

    assert credits == 0
