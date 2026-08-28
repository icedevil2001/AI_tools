from codex_usage_collector.parser import parse_session


def test_parse_session_normalizes_usage_fields() -> None:
    record = parse_session(
        '{"id":"session-1","model":"gpt-4o","created_at":"2026-05-01T10:11:12Z","usage":{"input_tokens":"10","output_tokens":5,"total_tokens":15}}',
        source_host="machine1",
        source_path="/tmp/session.json",
    )

    assert record is not None
    assert record.session_id == "session-1"
    assert record.model == "gpt-4o"
    assert record.input_tokens == 10
    assert record.output_tokens == 5
    assert record.total_tokens == 15
    assert record.host == "machine1"
    assert record.source_path == "/tmp/session.json"
    assert record.timestamp is not None


def test_parse_session_returns_none_for_invalid_json() -> None:
    assert parse_session("not-json", source_host="machine1", source_path="broken.json") is None


def test_parse_session_supports_codex_jsonl_session_files() -> None:
    record = parse_session(
        "\n".join(
            [
                '{"timestamp":"2026-04-20T22:18:20Z","type":"session_meta","payload":{"id":"session-jsonl","timestamp":"2026-04-20T22:18:20Z"}}',
                '{"timestamp":"2026-04-20T22:18:21Z","type":"turn_context","payload":{"model":"gpt-5.4"}}',
                '{"timestamp":"2026-04-20T22:18:31Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":12482,"output_tokens":234,"total_tokens":12716}}}}',
            ]
        ),
        source_host="machine1",
        source_path="/tmp/session.jsonl",
    )

    assert record is not None
    assert record.session_id == "session-jsonl"
    assert record.model == "gpt-5.4"
    assert record.input_tokens == 12482
    assert record.output_tokens == 234
    assert record.cached_input_tokens == 0
    assert record.reasoning_output_tokens == 0
    assert record.total_tokens == 12716
    assert record.source_path == "/tmp/session.jsonl"


def test_parse_session_uses_last_token_usage_delta_and_metadata() -> None:
    record = parse_session(
        "\n".join(
            [
                '{"timestamp":"2026-04-20T22:18:20Z","type":"session_meta","payload":{"id":"session-jsonl","timestamp":"2026-04-20T22:18:20Z","license_type":"enterprise"}}',
                '{"timestamp":"2026-04-20T22:18:21Z","type":"turn_context","payload":{"model":"gpt-5.4","reasoning":{"effort":"high"},"auth_type":"api_key"}}',
                '{"timestamp":"2026-04-20T22:18:31Z","type":"event_msg","payload":{"type":"token_count","status":"ok","info":{"last_token_usage":{"input_tokens":1000,"cached_input_tokens":200,"output_tokens":300,"reasoning_output_tokens":75,"total_tokens":1300},"rate_limit_hit":false}}}',
            ]
        ),
        source_host="machine1",
        source_path="/tmp/session.jsonl",
    )

    assert record is not None
    assert record.model == "gpt-5.4"
    assert record.input_tokens == 1000
    assert record.cached_input_tokens == 200
    assert record.output_tokens == 300
    assert record.reasoning_output_tokens == 75
    assert record.total_tokens == 1300
    assert record.reasoning_effort == "high"
    assert record.cache_hit is True
    assert record.rate_limit_hit is False
    assert record.license_type == "enterprise"
    assert record.status == "ok"
    assert record.message_count == 1


def test_parse_session_differences_cumulative_token_usage() -> None:
    record = parse_session(
        "\n".join(
            [
                '{"timestamp":"2026-04-20T22:18:20Z","type":"session_meta","payload":{"id":"session-jsonl","timestamp":"2026-04-20T22:18:20Z"}}',
                '{"timestamp":"2026-04-20T22:18:21Z","type":"turn_context","payload":{"model":"gpt-5.3-codex"}}',
                '{"timestamp":"2026-04-20T22:18:31Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":1000,"cached_input_tokens":100,"output_tokens":250,"reasoning_output_tokens":50,"total_tokens":1250}}}}',
                '{"timestamp":"2026-04-20T22:18:41Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":1800,"cached_input_tokens":400,"output_tokens":550,"reasoning_output_tokens":125,"total_tokens":2350}}}}',
            ]
        ),
        source_host="machine1",
        source_path="/tmp/session.jsonl",
    )

    assert record is not None
    assert record.input_tokens == 1800
    assert record.cached_input_tokens == 400
    assert record.output_tokens == 550
    assert record.reasoning_output_tokens == 125
    assert record.total_tokens == 2350
    assert record.message_count == 2
