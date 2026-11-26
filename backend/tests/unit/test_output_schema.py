from typing import Any

import pytest

from backend.app.viewers.document import ViewerDocument, viewer_document_json_schema
from backend.tests.unit.test_viewer_document import document_payload


def assert_output_schema_contract(value: Any) -> None:
    """Check the provider constraints that the former Fake accepted unchecked."""
    if isinstance(value, dict):
        assert "oneOf" not in value
        assert "discriminator" not in value
        if value.get("type") == "object":
            assert value["additionalProperties"] is False
            assert set(value["required"]) == set(value["properties"])
        for child in value.values():
            assert_output_schema_contract(child)
    elif isinstance(value, list):
        for child in value:
            assert_output_schema_contract(child)


def test_viewer_output_schema_preserves_twelve_disjoint_typed_blocks():
    schema = viewer_document_json_schema()
    assert schema["type"] == "object"
    assert "anyOf" not in schema
    assert_output_schema_contract(schema)
    choices = schema["$defs"]["Section"]["properties"]["blocks"]["items"]["anyOf"]
    branches = [schema["$defs"][choice["$ref"].rsplit("/", 1)[1]] for choice in choices]
    tags = [branch["properties"]["type"]["const"] for branch in branches]
    payload = document_payload()
    assert len(tags) == len(set(tags)) == 12
    assert set(tags) == {block["type"] for block in payload["sections"][0]["blocks"]}
    assert all("type" in branch["required"] for branch in branches)
    assert schema["$defs"]["ParagraphBlock"]["properties"]["text"]["maxLength"] == 6000
    assert schema["$defs"]["SourceReference"]["properties"]["start_line"]["minimum"] == 1
    assert ViewerDocument.model_validate(payload).model_dump(mode="json", by_alias=True) == payload


def test_provider_schema_does_not_mutate_local_validation_schema():
    original = ViewerDocument.model_json_schema()
    viewer_document_json_schema()
    assert ViewerDocument.model_json_schema() == original
    items = original["$defs"]["Section"]["properties"]["blocks"]["items"]
    assert "oneOf" in items
    assert items["discriminator"]["propertyName"] == "type"


def test_fake_contract_rejects_the_former_provider_schema():
    with pytest.raises(AssertionError):
        assert_output_schema_contract(ViewerDocument.model_json_schema())
