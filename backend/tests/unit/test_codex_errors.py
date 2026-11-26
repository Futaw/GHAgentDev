import pytest

from backend.app.codex.errors import classify_turn_error


@pytest.mark.parametrize(
    "message",
    [
        "Invalid schema for response_format 'codex_output_schema': oneOf is not supported",
        'HTTP 400: {"error":{"code":"invalid_json_schema"}}',
    ],
)
def test_output_schema_rejection_is_classified_without_exposing_details(message):
    assert classify_turn_error({"message": message}) == "invalid_output_schema"


@pytest.mark.parametrize(
    "error", [None, [], {}, {"message": {}}, {"message": "provider unavailable"}]
)
def test_unknown_provider_errors_keep_generic_classification(error):
    assert classify_turn_error(error) == "turn_failed"
