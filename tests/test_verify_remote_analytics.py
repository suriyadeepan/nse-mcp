"""Regression tests for independent remote analytics verification."""

import asyncio
from datetime import date, datetime, timezone
from contextlib import asynccontextmanager
import json
import math
import re
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.verify_remote_analytics import (
    NUMERIC_FIELDS,
    calculate_expected,
    classify_invalid_symbol_result,
    compare_values,
    inspect_cloudwatch,
    overall_status,
)


@pytest.mark.parametrize(
    "message",
    [
        "unknown symbol: '__KITE_INVALID_SYMBOL__'",
        "invalid symbol: REDACTION_SENTINEL_904",
    ],
)
def test_clean_validation_rejection_passes_without_echoing_server_text(message):
    outcome = classify_invalid_symbol_result(
        SimpleNamespace(is_error=True, content=[SimpleNamespace(text=message)])
    )

    assert outcome == {
        "status": "PASS",
        "reason": "server cleanly rejected the invalid symbol",
    }
    assert "REDACTION_SENTINEL_904" not in str(outcome)


def test_accepted_invalid_symbol_fails():
    outcome = classify_invalid_symbol_result(SimpleNamespace(is_error=False))

    assert outcome["status"] == "FAIL"
    assert "accepted" in outcome["reason"]


@pytest.mark.parametrize(
    "message",
    [
        "Traceback (most recent call last):\n  File '/srv/app.py', line 3",
        "internal server error while validating symbol",
        "Bearer embedded-secret-value",
        "authorization: embedded-secret-value",
        "failure included /Users/dev/app.py:42",
    ],
)
def test_internal_details_and_credentials_fail_without_echoing(message):
    outcome = classify_invalid_symbol_result(
        SimpleNamespace(is_error=True, content=[SimpleNamespace(text=message)]),
        secret_values=("embedded-secret-value",),
    )

    assert outcome["status"] == "FAIL"
    assert message not in str(outcome)
    assert "embedded-secret-value" not in str(outcome)


def test_unrecognized_tool_error_fails_with_generic_reason():
    outcome = classify_invalid_symbol_result(
        SimpleNamespace(
            is_error=True,
            content=[SimpleNamespace(text="backend refused request")],
        )
    )

    assert outcome == {
        "status": "FAIL",
        "reason": "response was not a recognized clean validation rejection",
    }


def test_cloudwatch_matches_only_correlated_events_and_does_not_emit_them(monkeypatch):
    request_id = "d61f7b6e-9f56-489f-8ef8-c4f610de1b2c"
    raw_event = f"MCP request correlation_id={request_id}"
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=0, stdout=json.dumps({"events": [{"message": raw_event}]})
        )

    monkeypatch.setattr(
        "scripts.verify_remote_analytics.subprocess.run",
        fake_run,
    )
    outcome = inspect_cloudwatch(
        {
            "request_id": request_id,
            "started_at": datetime.now(timezone.utc),
        },
        "/aws/lambda/example",
        None,
    )

    assert outcome == {
        "status": "PASS",
        "reason": "correlated invocation events found and scanned",
    }
    assert raw_event not in str(outcome)
    assert commands[0][commands[0].index("--filter-pattern") + 1] == f'"{request_id}"'


def test_cloudwatch_unavailable_or_unmatched_is_not_a_pass(monkeypatch):
    call = {
        "request_id": "d61f7b6e-9f56-489f-8ef8-c4f610de1b2c",
        "started_at": datetime.now(timezone.utc),
    }
    assert inspect_cloudwatch(call, None, None)["status"] == "NOT RUN"
    monkeypatch.setattr(
        "scripts.verify_remote_analytics.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='{"events": []}'),
    )
    monkeypatch.setattr("scripts.verify_remote_analytics.time.sleep", lambda _seconds: None)
    assert inspect_cloudwatch(call, "/aws/lambda/example", None)["status"] == "UNVERIFIED"


def test_cloudwatch_retries_boundedly_for_delayed_event_ingestion(monkeypatch):
    request_id = "d61f7b6e-9f56-489f-8ef8-c4f610de1b2c"
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout='{"events": []}'),
            SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"events": [{"message": f"correlation_id={request_id}"}]}),
            ),
        ]
    )
    attempts = []

    def fake_run(command, **_kwargs):
        attempts.append(command)
        return next(responses)

    monkeypatch.setattr("scripts.verify_remote_analytics.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.verify_remote_analytics.time.sleep", lambda _seconds: None)
    outcome = inspect_cloudwatch(
        {"request_id": request_id, "started_at": datetime.now(timezone.utc)},
        "/aws/lambda/example",
        None,
    )

    assert outcome["status"] == "PASS"
    assert len(attempts) == 2


def test_cloudwatch_fails_if_correlated_log_contains_configured_token(monkeypatch):
    request_id = "d61f7b6e-9f56-489f-8ef8-c4f610de1b2c"
    monkeypatch.setattr(
        "scripts.verify_remote_analytics.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"events": [{"message": f"{request_id} Bearer local-secret-sentinel"}]}
            ),
        ),
    )
    outcome = inspect_cloudwatch(
        {"request_id": request_id, "started_at": datetime.now(timezone.utc)},
        "/aws/lambda/example",
        "local-secret-sentinel",
    )

    assert outcome == {
        "status": "FAIL",
        "reason": "correlated events contain credential-like content",
    }
    assert "local-secret-sentinel" not in str(outcome)


def test_raw_pyarrow_calculation_uses_explicit_formulas_and_tie_order(tmp_path):
    parquet_path = tmp_path / "bars.parquet"
    pq.write_table(
        pa.table(
            {
                "timestamp": [
                    datetime(2025, 1, 1, 3, 45, tzinfo=timezone.utc),
                    datetime(2025, 1, 1, 3, 45, tzinfo=timezone.utc),
                ],
                "trading_date": [date(2025, 1, 1), date(2025, 1, 1)],
                "open": [10.0, 9.0],
                "high": [12.0, 11.0],
                "low": [8.0, 7.0],
                "close": [11.0, 10.0],
                "volume": [2, 3],
            }
        ),
        parquet_path,
    )

    expected = calculate_expected(parquet_path)

    assert expected == {
        "open": 9.0,
        "close": 11.0,
        "high": 12.0,
        "low": 7.0,
        "total_volume": 5,
        "vwap": pytest.approx(((31 / 3) * 2 + (28 / 3) * 3) / 5),
        "absolute_return": 2.0,
        "percentage_return": pytest.approx((11 / 9 - 1) * 100),
        "bar_count": 2,
    }


@pytest.mark.parametrize(
    "actual_value, expected_status",
    [
        (1.0005, "PASS"),
        (1.002, "FAIL"),
        (None, "FAIL"),
        (float("nan"), "FAIL"),
        (float("inf"), "FAIL"),
        (True, "FAIL"),
    ],
)
def test_numeric_comparison_enforces_tolerance_and_finite_numbers(
    actual_value, expected_status
):
    expected = {field: 1.0 for field in NUMERIC_FIELDS}
    actual = {field: 1.0 for field in NUMERIC_FIELDS}
    actual["open"] = actual_value

    comparisons = compare_values(expected, actual, tolerance=0.001)

    assert comparisons[0]["status"] == expected_status
    assert comparisons[0]["actual"] == (
        actual_value if isinstance(actual_value, (int, float)) and math.isfinite(actual_value) and not isinstance(actual_value, bool) else None
    )


@pytest.mark.parametrize(
    "statuses, expected",
    [
        (["PASS", "PASS", "PASS"], "PASS"),
        (["FAIL", "NOT RUN", "PASS"], "FAIL"),
        (["PASS", "UNVERIFIED", "PASS"], "INCOMPLETE"),
        (["PASS", "NOT RUN", "PASS"], "INCOMPLETE"),
    ],
)
def test_overall_status_obeys_smoke_report_rules(statuses, expected):
    assert overall_status(statuses) == expected


def test_report_main_emits_three_truthful_check_statuses(monkeypatch, capsys):
    import scripts.verify_remote_analytics as verifier

    expected = {field: 1.0 for field in NUMERIC_FIELDS}
    call = {
        "result": SimpleNamespace(is_error=False, structured_content=expected),
        "request_id": "d61f7b6e-9f56-489f-8ef8-c4f610de1b2c",
        "started_at": datetime.now(timezone.utc),
        "response_request_ids": [],
    }
    invalid_call = {
        **call,
        "result": SimpleNamespace(
            is_error=True,
            content=[SimpleNamespace(text="unknown symbol: '__KITE_INVALID_SYMBOL__'")],
        ),
    }
    monkeypatch.setattr("sys.argv", ["verify_remote_analytics"])
    monkeypatch.setattr(verifier, "calculate_expected", lambda _path: expected)

    async def fake_remote(*_args):
        return {**call, "result": expected, "is_error": False}

    async def fake_invalid(*_args):
        return invalid_call

    monkeypatch.setattr(verifier, "invoke_remote", fake_remote)
    monkeypatch.setattr(verifier, "invoke_invalid_symbol", fake_invalid)
    monkeypatch.setattr(
        verifier,
        "inspect_cloudwatch",
        lambda *_args: {"status": "NOT RUN", "reason": "logs unavailable"},
    )

    exit_code = verifier.main()
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert report["status"] == "INCOMPLETE"
    assert report["analytics"]["status"] == "PASS"
    assert report["invalid_symbol"]["status"] == "PASS"
    assert report["cloudwatch"]["status"] == "INCOMPLETE"
    assert all(field["status"] == "PASS" for field in report["analytics"]["fields"])


def test_main_reports_remote_unavailability_as_incomplete_without_echoing_errors(
    monkeypatch, capsys
):
    import scripts.verify_remote_analytics as verifier

    expected = {field: 1.0 for field in NUMERIC_FIELDS}
    monkeypatch.setattr("sys.argv", ["verify_remote_analytics"])
    monkeypatch.setenv("MCP_BEARER_TOKEN", "secret-sentinel-777")
    monkeypatch.setattr(verifier, "calculate_expected", lambda _path: expected)

    async def fail_remote(*_args):
        raise RuntimeError("Bearer secret-sentinel-777")

    monkeypatch.setattr(verifier, "invoke_remote", fail_remote)
    monkeypatch.setattr(verifier, "invoke_invalid_symbol", fail_remote)

    exit_code = verifier.main()
    output = capsys.readouterr().out
    report = json.loads(output)

    assert exit_code == 2
    assert report["status"] == "INCOMPLETE"
    assert report["analytics"]["status"] == "NOT RUN"
    assert report["invalid_symbol"]["status"] == "NOT RUN"
    assert report["cloudwatch"]["status"] == "INCOMPLETE"
    assert "secret-sentinel-777" not in output
    assert "Bearer" not in output


def test_invoke_tool_propagates_request_id_and_captures_response_id(monkeypatch):
    import scripts.verify_remote_analytics as verifier

    client = SimpleNamespace(
        call_tool=None,
    )
    calls = []

    async def call_tool(name, arguments):
        calls.append((name, arguments))
        return SimpleNamespace(is_error=False)

    client.call_tool = call_tool

    class FakeHttpClient:
        def __init__(self, *, headers, event_hooks):
            self.headers = headers
            self.event_hooks = event_hooks

        async def __aenter__(self):
            response = SimpleNamespace(
                headers={"x-amzn-requestid": "aws-request-23"}
            )
            for hook in self.event_hooks["response"]:
                await hook(response)
            return self

        async def __aexit__(self, *_args):
            return None

    @asynccontextmanager
    async def fake_connect(_url, *, http_client):
        assert http_client.headers["X-Kite-Request-Id"]
        assert http_client.headers["Authorization"] == "Bearer test-token"
        yield client

    monkeypatch.setattr(verifier.httpx2, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(verifier, "connect_to_server", fake_connect)
    outcome = asyncio.run(
        verifier.invoke_tool(
            "https://mcp.example/mcp",
            "test-token",
            "intraday_stats",
            {"symbol": "INFY", "trading_date": "2025-01-01"},
        )
    )

    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        outcome["request_id"],
    )
    assert outcome["response_request_ids"] == ["aws-request-23"]
    assert outcome["started_at"].tzinfo is not None
    assert calls == [
        (
            "intraday_stats",
            {"arguments": {"symbol": "INFY", "trading_date": "2025-01-01"}},
        )
    ]
