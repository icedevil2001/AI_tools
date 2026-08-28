from codex_usage_collector.pricing import ModelPricing, calculate_cost_usd


def test_calculate_cost_uses_alias_when_direct_pricing_is_zero() -> None:
    cost = calculate_cost_usd(
        model="gpt-5.3-codex",
        input_tokens=1_000_000,
        cached_input_tokens=0,
        output_tokens=500_000,
        pricing={
            "gpt-5.3-codex": ModelPricing(0, 0, 0),
            "gpt-5.2-codex": ModelPricing(1.25, 0.125, 10),
        },
    )

    assert cost == 6.25
