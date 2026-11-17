"""Shared input validation for analytical query entry points."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone

from .config import ANALYTICS_CONFIG
from .data import list_symbols

INDICATORS = ("SMA", "EMA", "RSI", "ATR")
VOLUME_BUCKETS = ("hourly", "daily")
COMPARISON_INTERVALS = ("daily",)


class AnalyticsInputError(ValueError):
    """Raised when an analytics input is malformed or outside configured limits."""


def _available_symbols() -> frozenset[str]:
    """Read the allowlist from configured processed Parquet files."""
    return frozenset(list_symbols(ANALYTICS_CONFIG.processed_data_dir))


def validate_symbol(symbol: object) -> str:
    """Require a symbol present in the configured processed-data allowlist."""
    if not isinstance(symbol, str) or not symbol:
        raise AnalyticsInputError("symbol must be a non-empty string")
    if symbol not in _available_symbols():
        raise AnalyticsInputError(f"unknown symbol: {symbol!r}")
    return symbol


def validate_symbols(
    symbols: Iterable[object], *, minimum: int = 1
) -> tuple[str, ...]:
    """Validate a symbol collection once against the configured allowlist."""
    if isinstance(symbols, (str, bytes)):
        raise AnalyticsInputError("symbols must be a collection of symbol strings")
    try:
        values = tuple(symbols)
    except TypeError as exc:
        raise AnalyticsInputError("symbols must be iterable") from exc
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise AnalyticsInputError("minimum symbol count must be a positive integer")
    if len(values) < minimum:
        raise AnalyticsInputError(f"at least {minimum} symbol(s) are required")
    if any(not isinstance(value, str) or not value for value in values):
        raise AnalyticsInputError("each symbol must be a non-empty string")
    if len(set(values)) != len(values):
        raise AnalyticsInputError("symbols must not contain duplicates")

    available = _available_symbols()
    validated: list[str] = []
    for value in values:
        if value not in available:
            raise AnalyticsInputError(f"unknown symbol: {value!r}")
        validated.append(value)
    return tuple(validated)


def validate_datetime(value: object, *, name: str) -> datetime:
    """Parse an aware datetime or ISO-8601 timestamp and normalize it to UTC."""
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AnalyticsInputError(f"{name} must be an ISO-8601 timestamp") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise AnalyticsInputError(f"{name} must be an aware datetime or ISO-8601 string")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AnalyticsInputError(f"{name} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def validate_datetime_range(
    start_datetime: object,
    end_datetime: object,
    *,
    max_days: int | None = None,
) -> tuple[datetime, datetime]:
    """Validate ordered UTC bounds and enforce the configured maximum span."""
    start = validate_datetime(start_datetime, name="start_datetime")
    end = validate_datetime(end_datetime, name="end_datetime")
    if end < start:
        raise AnalyticsInputError("end_datetime must be on or after start_datetime")

    allowed_days = (
        ANALYTICS_CONFIG.max_date_range_days if max_days is None else max_days
    )
    if isinstance(allowed_days, bool) or not isinstance(allowed_days, int) or allowed_days < 0:
        raise AnalyticsInputError("maximum date range must be a non-negative integer")
    if end - start > timedelta(days=allowed_days):
        raise AnalyticsInputError(
            f"date range exceeds the configured maximum of {allowed_days} days"
        )
    return start, end


def validate_trading_date(value: object) -> date:
    """Parse an IST calendar date without accepting timestamp values."""
    if isinstance(value, datetime):
        raise AnalyticsInputError("trading_date must be a calendar date")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise AnalyticsInputError("trading_date must use YYYY-MM-DD format") from exc
    raise AnalyticsInputError("trading_date must be a date or YYYY-MM-DD string")


def validate_limit(limit: object, *, maximum: int | None = None) -> int:
    """Require a positive row limit within the configured maximum."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise AnalyticsInputError("limit must be a positive integer")
    allowed = ANALYTICS_CONFIG.max_returned_rows if maximum is None else maximum
    if isinstance(allowed, bool) or not isinstance(allowed, int) or allowed < 1:
        raise AnalyticsInputError("maximum row limit must be a positive integer")
    if limit > allowed:
        raise AnalyticsInputError(f"limit cannot exceed the configured maximum of {allowed}")
    return limit


def validate_enum(value: object, *, name: str, choices: Sequence[str]) -> str:
    """Return the canonical choice for a case-insensitive enumerated input."""
    if not isinstance(value, str):
        raise AnalyticsInputError(f"{name} must be one of: {', '.join(choices)}")
    canonical = {choice.casefold(): choice for choice in choices}
    try:
        return canonical[value.casefold()]
    except KeyError as exc:
        raise AnalyticsInputError(f"{name} must be one of: {', '.join(choices)}") from exc


def validate_bucket(bucket: object) -> str:
    """Validate and canonicalize a volume aggregation bucket."""
    return validate_enum(bucket, name="bucket", choices=VOLUME_BUCKETS)


def validate_interval(interval: object) -> str:
    """Validate and canonicalize a comparison interval."""
    return validate_enum(interval, name="interval", choices=COMPARISON_INTERVALS)


def validate_indicators(indicators: Iterable[object]) -> tuple[str, ...]:
    """Validate indicator names and return uppercase canonical values."""
    if isinstance(indicators, (str, bytes)):
        raise AnalyticsInputError("indicators must be a collection of indicator names")
    try:
        values = tuple(indicators)
    except TypeError as exc:
        raise AnalyticsInputError("indicators must be iterable") from exc
    validated = tuple(
        validate_enum(value, name="indicator", choices=INDICATORS) for value in values
    )
    if len(set(validated)) != len(validated):
        raise AnalyticsInputError("indicators must not contain duplicates")
    return validated


def validate_indicator_parameters(
    indicators: Sequence[str], parameters: object = None
) -> dict[str, int]:
    """Validate period parameters keyed by requested indicator name."""
    if parameters is None:
        supplied: Mapping[object, object] = {}
    elif isinstance(parameters, Mapping):
        supplied = parameters
    else:
        raise AnalyticsInputError("parameters must map indicator names to periods")

    normalized: dict[str, int] = {}
    requested = set(indicators)
    for name, period in supplied.items():
        indicator = validate_enum(name, name="indicator parameter", choices=INDICATORS)
        if indicator not in requested:
            raise AnalyticsInputError(
                f"parameters include unrequested indicator: {indicator}"
            )
        if indicator in normalized:
            raise AnalyticsInputError(
                f"parameters contain duplicate indicator: {indicator}"
            )
        maximum = ANALYTICS_CONFIG.indicator_warmup_limit
        if (
            isinstance(period, bool)
            or not isinstance(period, int)
            or not 1 <= period <= maximum
        ):
            raise AnalyticsInputError(
                f"{indicator} period must be an integer from 1 to {maximum}"
            )
        normalized[indicator] = period
    return normalized
