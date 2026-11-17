"""Tests for the Pydantic MCP tool argument schemas."""

from src.server.validation import TOOL_ARGUMENT_MODELS, TOOL_DESCRIPTIONS
from src.server.config import ANALYTICS_CONFIG


EXPECTED_TOOL_FIELDS = {
    "get_bars": {"symbol", "start_datetime", "end_datetime", "limit"},
    "intraday_stats": {"symbol", "trading_date"},
    "get_price_extremes": {"symbol", "start_datetime", "end_datetime"},
    "get_volume_stats": {"symbol", "start_datetime", "end_datetime", "bucket"},
    "compute_indicators": {
        "symbol",
        "start_datetime",
        "end_datetime",
        "indicators",
        "parameters",
    },
    "compare_symbols": {
        "symbols",
        "start_datetime",
        "end_datetime",
        "interval",
    },
}


def test_all_analytics_tools_have_documented_strict_json_schemas():
    assert set(TOOL_ARGUMENT_MODELS) == set(EXPECTED_TOOL_FIELDS)
    assert set(TOOL_DESCRIPTIONS) == set(EXPECTED_TOOL_FIELDS)

    for name, model in TOOL_ARGUMENT_MODELS.items():
        schema = model.model_json_schema()

        assert TOOL_DESCRIPTIONS[name]
        assert schema["type"] == "object"
        assert schema["description"]
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == EXPECTED_TOOL_FIELDS[name]
        assert all(
            field_schema.get("description")
            for field_schema in schema["properties"].values()
        )


def test_json_schemas_include_input_constraints():
    bars_schema = TOOL_ARGUMENT_MODELS["get_bars"].model_json_schema()
    assert (
        bars_schema["properties"]["limit"]["maximum"]
        == ANALYTICS_CONFIG.max_returned_rows
    )

    volume_schema = TOOL_ARGUMENT_MODELS["get_volume_stats"].model_json_schema()
    assert volume_schema["properties"]["bucket"]["enum"] == ["hourly", "daily"]

    indicator_schema = TOOL_ARGUMENT_MODELS["compute_indicators"].model_json_schema()
    assert indicator_schema["properties"]["indicators"]["minItems"] == 1
    assert indicator_schema["properties"]["indicators"]["uniqueItems"] is True

    comparison_schema = TOOL_ARGUMENT_MODELS["compare_symbols"].model_json_schema()
    assert comparison_schema["properties"]["symbols"]["minItems"] == 2
    assert (
        comparison_schema["properties"]["symbols"]["maxItems"]
        == ANALYTICS_CONFIG.max_returned_rows
    )
    assert comparison_schema["properties"]["symbols"]["uniqueItems"] is True
    assert comparison_schema["properties"]["interval"]["const"] == "daily"
