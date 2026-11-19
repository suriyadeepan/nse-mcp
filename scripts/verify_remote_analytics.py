"""Compare one direct remote MCP analytics result with local Parquet rows."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
import time
from typing import Any
from uuid import uuid4

import httpx2
import pyarrow.parquet as pq

from client.discovery import DEFAULT_SERVER_URL, connect_to_server

SYMBOL = "INFY"
TRADING_DATE = date(2025, 1, 1)
TOOL_NAME = "intraday_stats"
INVALID_SYMBOL = "__KITE_INVALID_SYMBOL__"
NUMERIC_FIELDS = (
    "open",
    "close",
    "high",
    "low",
    "total_volume",
    "vwap",
    "absolute_return",
    "percentage_return",
    "bar_count",
)
RAW_COLUMNS = ("timestamp", "trading_date", "open", "high", "low", "close", "volume")
CLOUDWATCH_RETRY_ATTEMPTS = 5
CLOUDWATCH_RETRY_DELAY_SECONDS = 2
def calculate_expected(parquet_path: Path) -> dict[str, int | float | None]:
    """Calculate session metrics from raw Arrow rows using explicit Python formulas."""
    rows = pq.read_table(parquet_path, columns=list(RAW_COLUMNS)).to_pylist()
    session_rows = sorted(
        (row for row in rows if row["trading_date"] == TRADING_DATE),
        key=lambda row: (
            row["timestamp"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"],
        ),
    )
    if not session_rows:
        raise ValueError("the selected symbol and date have no local Parquet rows")

    first, last = session_rows[0], session_rows[-1]
    open_price = float(first["open"])
    close_price = float(last["close"])
    total_volume = sum(int(row["volume"]) for row in session_rows)
    weighted_typical_price = sum(
        ((row["high"] + row["low"] + row["close"]) / 3.0) * row["volume"]
        for row in session_rows
    )
    return {
        "open": open_price,
        "close": close_price,
        "high": max(float(row["high"]) for row in session_rows),
        "low": min(float(row["low"]) for row in session_rows),
        "total_volume": total_volume,
        "vwap": weighted_typical_price / total_volume if total_volume else None,
        "absolute_return": close_price - open_price,
        "percentage_return": (close_price / open_price - 1.0) * 100.0
        if open_price
        else None,
        "bar_count": len(session_rows),
    }


def compare_values(
    expected: dict[str, int | float | None],
    actual: Any,
    tolerance: float,
) -> list[dict[str, Any]]:
    """Return numeric field comparisons; absent and non-finite values fail."""
    comparisons = []
    for field in NUMERIC_FIELDS:
        expected_value = expected[field]
        actual_value = actual.get(field) if isinstance(actual, dict) else None
        valid = (
            isinstance(expected_value, (int, float))
            and not isinstance(expected_value, bool)
            and math.isfinite(float(expected_value))
            and isinstance(actual_value, (int, float))
            and not isinstance(actual_value, bool)
            and math.isfinite(float(actual_value))
            and math.isfinite(float(expected_value))
        )
        difference = abs(float(actual_value) - float(expected_value)) if valid else None
        passed = bool(valid and difference is not None and difference <= tolerance)
        comparisons.append(
            {
                "field": field,
                "expected": expected_value,
                "actual": actual_value if valid else None,
                "difference": difference,
                "tolerance": tolerance,
                "status": "PASS" if passed else "FAIL",
            }
        )
    return comparisons


async def invoke_remote(server_url: str, bearer_token: str | None) -> Any:
    """Call the selected MCP tool directly without discovery or model selection."""
    call = await invoke_tool(
        server_url,
        bearer_token,
        TOOL_NAME,
        {"symbol": SYMBOL, "trading_date": TRADING_DATE.isoformat()},
    )
    result = call["result"]
    return {
        **call,
        "result": result.structured_content,
        "is_error": result.is_error,
    }


async def invoke_tool(
    server_url: str,
    bearer_token: str | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Invoke one tool with a unique propagated ID and capture response IDs."""
    request_id = str(uuid4())
    response_ids: list[str] = []

    async def capture_response_ids(response: Any) -> None:
        for header in ("x-amzn-requestid", "x-amz-apigw-id"):
            value = response.headers.get(header)
            if value and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
                response_ids.append(value)

    headers = {"X-Kite-Request-Id": request_id}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    async with httpx2.AsyncClient(
        headers=headers,
        event_hooks={"response": [capture_response_ids]},
    ) as http_client:
        async with connect_to_server(server_url, http_client=http_client) as client:
            # Timestamp is captured immediately before the single MCP tool request.
            started_at = datetime.now(timezone.utc)
            result = await client.call_tool(tool_name, {"arguments": arguments})
    return {
        "result": result,
        "request_id": request_id,
        "started_at": started_at,
        "response_request_ids": list(dict.fromkeys(response_ids)),
    }


async def invoke_invalid_symbol(
    server_url: str, bearer_token: str | None
) -> Any:
    """Submit the fixed invalid symbol using the same MCP tool and endpoint."""
    return await invoke_tool(
        server_url,
        bearer_token,
        TOOL_NAME,
        {"symbol": INVALID_SYMBOL, "trading_date": TRADING_DATE.isoformat()},
    )


def classify_invalid_symbol_result(
    result: Any, secret_values: tuple[str, ...] = ()
) -> dict[str, str]:
    """Classify a rejection without returning or logging raw server text."""
    if not getattr(result, "is_error", False):
        return {"status": "FAIL", "reason": "invalid symbol was accepted"}

    fragments = []
    for item in getattr(result, "content", ()) or ():
        text = getattr(item, "text", None)
        if isinstance(text, str):
            fragments.append(text)
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        fragments.append(json.dumps(structured, default=str))
    error_text = "\n".join(fragments)
    lowered = error_text.lower()

    sensitive_patterns = (
        r"(?i)\bbearer\s+\S+",
        r"(?i)\b(?:authorization|access[_ -]?token|secret|password|api[_ -]?key)\b\s*[:=]",
        r"(?i)\b(?:aws_access_key_id|aws_secret_access_key)\b",
    )
    if any(value and value in error_text for value in secret_values) or any(
        re.search(pattern, error_text) for pattern in sensitive_patterns
    ):
        return {"status": "FAIL", "reason": "rejection exposed credential-like content"}

    internal_patterns = (
        r"(?i)traceback \(most recent call last\)",
        r"(?i)\b(?:exception|stack trace|internal server error)\b",
        r"(?m)(?:^|\s)(?:/[^\s:]+)+\.py:\d+",
        r"(?i)\b(?:arn:aws:|botocore|site-packages|/home/|/users/)\b",
    )
    if any(re.search(pattern, error_text) for pattern in internal_patterns):
        return {"status": "FAIL", "reason": "rejection included internal error details"}
    if "unknown symbol" in lowered or "invalid symbol" in lowered:
        return {"status": "PASS", "reason": "server cleanly rejected the invalid symbol"}
    return {"status": "FAIL", "reason": "response was not a recognized clean validation rejection"}


def inspect_cloudwatch(
    call: dict[str, Any], log_group: str | None, bearer_token: str | None
) -> dict[str, str]:
    """Read only events matching a propagated request ID in a bounded window."""
    request_id = call.get("request_id")
    started_at = call.get("started_at")
    if not log_group:
        return {"status": "NOT RUN", "reason": "Lambda log group is not configured"}
    if not isinstance(request_id, str) or not isinstance(started_at, datetime):
        return {"status": "UNVERIFIED", "reason": "request correlation ID is unavailable"}

    start_ms = int((started_at - timedelta(minutes=2)).timestamp() * 1000)
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    matched: list[str] = []
    for attempt in range(CLOUDWATCH_RETRY_ATTEMPTS):
        try:
            completed = subprocess.run(
                [
                    "aws",
                    "logs",
                    "filter-log-events",
                    "--log-group-name",
                    log_group,
                    "--start-time",
                    str(start_ms),
                    "--end-time",
                    str(end_ms),
                    "--filter-pattern",
                    f'"{request_id}"',
                    "--output",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {"status": "NOT RUN", "reason": "CloudWatch query could not be executed"}
        if completed.returncode != 0:
            return {"status": "NOT RUN", "reason": "CloudWatch query was unavailable"}
        try:
            payload = json.loads(completed.stdout)
            events = payload.get("events", [])
        except (json.JSONDecodeError, AttributeError):
            return {"status": "NOT RUN", "reason": "CloudWatch response was unreadable"}
        if not isinstance(events, list):
            return {"status": "NOT RUN", "reason": "CloudWatch response was unreadable"}

        matched = [
            event.get("message", "")
            for event in events
            if isinstance(event, dict)
            and isinstance(event.get("message"), str)
            and request_id in event["message"]
        ]
        if matched:
            break
        if attempt + 1 < CLOUDWATCH_RETRY_ATTEMPTS:
            time.sleep(CLOUDWATCH_RETRY_DELAY_SECONDS)
    if not matched:
        return {
            "status": "UNVERIFIED",
            "reason": "no correlated invocation events found in the bounded window",
        }
    sensitive_patterns = (
        r"(?i)\bbearer\s+\S+",
        r"(?i)\b(?:authorization|access[_ -]?token|secret|password|api[_ -]?key)\b\s*[:=]",
        r"(?i)\b(?:aws_access_key_id|aws_secret_access_key)\b",
    )
    if any(
        (bearer_token and bearer_token in message)
        or any(re.search(pattern, message) for pattern in sensitive_patterns)
        for message in matched
    ):
        return {"status": "FAIL", "reason": "correlated events contain credential-like content"}
    return {"status": "PASS", "reason": "correlated invocation events found and scanned"}


def overall_status(statuses: list[str]) -> str:
    """Combine required checks: assertions fail; unavailable evidence is incomplete."""
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if statuses and all(status == "PASS" for status in statuses):
        return "PASS"
    return "INCOMPLETE"


def call_metadata(call: dict[str, Any]) -> dict[str, Any]:
    """Expose only non-secret correlation metadata from one tool call."""
    return {
        "started_at": call["started_at"].isoformat(),
        "request_id": call["request_id"],
        "response_request_ids": call["response_request_ids"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server",
        default=None,
        help="Streamable HTTP MCP endpoint (defaults to MCP_SERVER_URL or localhost)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/processed"),
        help="Local processed-data Hive partition root",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-6,
        help="Maximum absolute numeric difference (default: 1e-6)",
    )
    args = parser.parse_args()
    if not math.isfinite(args.tolerance) or args.tolerance < 0:
        parser.error("--tolerance must be a finite, non-negative number")

    server_url = args.server or os.environ.get("MCP_SERVER_URL") or DEFAULT_SERVER_URL
    bearer_token = os.environ.get("MCP_BEARER_TOKEN")
    log_group = os.environ.get("MCP_LAMBDA_LOG_GROUP")
    if not log_group and os.environ.get("MCP_LAMBDA_FUNCTION_NAME"):
        log_group = f"/aws/lambda/{os.environ['MCP_LAMBDA_FUNCTION_NAME']}"
    parquet_path = (
        args.data_dir
        / "interval=1m"
        / "year=2025"
        / "month=01"
        / f"symbol={SYMBOL}"
        / "part.parquet"
    )
    report: dict[str, Any] = {
        "inputs": {"tool": TOOL_NAME, "symbol": SYMBOL, "trading_date": TRADING_DATE.isoformat()},
        "tolerance": args.tolerance,
    }
    calls: dict[str, dict[str, Any] | None] = {"analytics": None, "invalid_symbol": None}
    try:
        expected = calculate_expected(parquet_path)
    except Exception:
        expected = None
        report["analytics"] = {
            "status": "NOT RUN",
            "reason": "local Parquet reference values are unavailable",
        }
    if expected is not None:
        try:
            analytics_call = asyncio.run(invoke_remote(server_url, bearer_token))
            calls["analytics"] = analytics_call
            if analytics_call["is_error"]:
                report["analytics"] = {
                    "status": "FAIL",
                    "reason": "remote analytics tool returned an error",
                    "expected": expected,
                    "actual": None,
                    "fields": [],
                    "call": call_metadata(analytics_call),
                }
            else:
                actual = analytics_call["result"]
                fields = compare_values(expected, actual, args.tolerance)
                field_statuses = [field["status"] for field in fields]
                all_fields_pass = all(s == "PASS" for s in field_statuses)
                report["analytics"] = {
                    "status": "PASS" if all_fields_pass else "FAIL",
                    "reason": "all numeric fields are within tolerance"
                    if all_fields_pass
                    else "one or more numeric fields are missing, non-finite, or outside tolerance",
                    "expected": expected,
                    "actual": {
                        field: actual[field]
                        for field in NUMERIC_FIELDS
                        if isinstance(actual, dict)
                        and isinstance(actual.get(field), (int, float))
                        and not isinstance(actual.get(field), bool)
                        and math.isfinite(float(actual[field]))
                    }
                    if isinstance(actual, dict)
                    else None,
                    "fields": fields,
                    "call": call_metadata(analytics_call),
                }
        except Exception:
            report["analytics"] = {
                "status": "NOT RUN",
                "reason": "remote MCP analytics call was unavailable",
                "expected": expected,
                "actual": None,
                "fields": [],
            }

    try:
        invalid_call = asyncio.run(invoke_invalid_symbol(server_url, bearer_token))
        calls["invalid_symbol"] = invalid_call
        report["invalid_symbol"] = classify_invalid_symbol_result(
            invalid_call["result"], (bearer_token,) if bearer_token else ()
        )
        report["invalid_symbol"]["call"] = call_metadata(invalid_call)
    except Exception:
        report["invalid_symbol"] = {
            "status": "NOT RUN",
            "reason": "invalid-symbol MCP request was unavailable",
        }

    cloudwatch_checks = {}
    for name, call in calls.items():
        cloudwatch_checks[name] = (
            inspect_cloudwatch(call, log_group, bearer_token)
            if call is not None
            else {"status": "NOT RUN", "reason": "corresponding MCP call did not run"}
        )
    report["cloudwatch"] = {
        **cloudwatch_checks,
        "status": overall_status([check["status"] for check in cloudwatch_checks.values()]),
        "reason": "CloudWatch checks summarized from both invocations",
    }
    report["status"] = overall_status(
        [
            report["analytics"]["status"],
            report["invalid_symbol"]["status"],
            report["cloudwatch"]["status"],
        ]
    )
    print(json.dumps(report, indent=2, allow_nan=False))
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
