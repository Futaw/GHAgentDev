from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from backend.app.viewers.document import ViewerDocument, parse_viewer_document
from backend.app.viewers.renderer import diagram_uses_table, is_compact, render_viewer_document
from backend.app.viewers.sanitizer import sanitize_viewer_html


def document_payload() -> dict[str, object]:
    source = "src-main"
    common = {"title": None, "source_reference_ids": [source]}
    blocks = [
        {"id": "paragraph", "type": "paragraph", **common, "text": "概要です。"},
        {"id": "bullets", "type": "bullet_list", **common, "ordered": False, "items": ["a", "b"]},
        {
            "id": "key-values",
            "type": "key_value",
            **common,
            "items": [{"key": "key", "value": "value"}],
        },
        {
            "id": "table",
            "type": "table",
            **common,
            "columns": [{"id": "name", "label": "Name"}],
            "rows": [{"cells": ["row"]}],
        },
        {
            "id": "code",
            "type": "code",
            **common,
            "language": "python",
            "code": "print('<safe>')",
            "caption": None,
        },
        {"id": "callout", "type": "callout", **common, "tone": "warning", "text": "注意"},
        {
            "id": "steps",
            "type": "steps",
            **common,
            "items": [{"id": "step-one", "label": "開始", "description": "実行"}],
        },
        {
            "id": "flow",
            "type": "flow",
            **common,
            "nodes": [
                {"id": "start", "label": "開始", "description": None, "kind": "start"},
                {"id": "end", "label": "終了", "description": None, "kind": "end"},
            ],
            "edges": [{"from": "start", "to": "end", "label": None}],
        },
        {
            "id": "states",
            "type": "state_diagram",
            **common,
            "states": [
                {"id": "initial", "label": "初期", "description": None, "kind": "initial"},
                {"id": "success", "label": "成功", "description": None, "kind": "success"},
            ],
            "transitions": [{"from": "initial", "to": "success", "label": "完了"}],
        },
        {
            "id": "comparison",
            "type": "comparison",
            **common,
            "series": [{"id": "before", "label": "Before"}, {"id": "after", "label": "After"}],
            "rows": [{"aspect": "状態", "values": ["旧", "新"]}],
        },
        {
            "id": "components",
            "type": "component_map",
            **common,
            "components": [
                {
                    "id": "api",
                    "label": "API",
                    "description": None,
                    "kind": "backend",
                    "group": "Server",
                },
                {
                    "id": "db",
                    "label": "DB",
                    "description": None,
                    "kind": "database",
                    "group": "Data",
                },
            ],
            "relations": [{"from": "api", "to": "db", "kind": "writes", "label": None}],
        },
        {
            "id": "evidence",
            "type": "source_evidence",
            **common,
            "items": [{"source_reference_id": source, "explanation": "実装根拠"}],
        },
    ]
    return {
        "schema_version": "1.0",
        "title": "Viewer",
        "summary": "12種類のblockを確認します。",
        "sections": [{"id": "overview", "heading": "概要", "summary": None, "blocks": blocks}],
        "source_references": [
            {
                "id": source,
                "path": "src/main.py",
                "start_line": 1,
                "end_line": 1,
                "description": "実装",
            }
        ],
        "limitations": [],
    }


def test_all_twelve_blocks_validate_render_and_escape() -> None:
    document = ViewerDocument.model_validate(document_payload())
    assert len(document.sections[0].blocks) == 12
    html = render_viewer_document(document)
    assert html.count("data-block-type=") == 12
    assert "&lt;safe&gt;" in html
    assert "<safe>" not in html
    cleaned = sanitize_viewer_html(html, "https://github.com/example/repo")
    assert "script" not in cleaned
    assert 'data-source-reference-id="src-main"' in cleaned


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["sections"][0]["blocks"][0].update({"unknown": True}), "extra"),
        (lambda value: value["sections"][0]["blocks"][0].update({"type": "html"}), "union"),
        (
            lambda value: value["sections"][0]["blocks"][0].update(
                {"source_reference_ids": ["missing"]}
            ),
            "source",
        ),
        (lambda value: value["source_references"][0].update({"end_line": 0}), "line"),
    ],
)
def test_invalid_documents_are_rejected(mutation, message: str) -> None:  # type: ignore[no-untyped-def]
    payload = document_payload()
    mutation(payload)
    with pytest.raises(ValidationError) as error:
        ViewerDocument.model_validate(payload)
    assert message or error.value


def test_byte_limit_is_checked_before_parse() -> None:
    raw = json.dumps(document_payload(), ensure_ascii=False)
    with pytest.raises(ValueError, match="byte limit"):
        parse_viewer_document(raw, max_bytes=10)


def test_graph_constraints_and_compact_boundaries() -> None:
    payload = document_payload()
    flow = payload["sections"][0]["blocks"][7]  # type: ignore[index]
    flow["edges"].append({"from": "end", "to": "start", "label": None})  # type: ignore[index]
    with pytest.raises(ValidationError, match="cycle|degree"):
        ViewerDocument.model_validate(payload)

    base = document_payload()
    document = ViewerDocument.model_validate(base)
    paragraph = document.sections[0].blocks[0]
    assert is_compact(paragraph)
    long = copy.deepcopy(base)
    long["sections"][0]["blocks"][0]["text"] = "x" * 601  # type: ignore[index]
    assert not is_compact(ViewerDocument.model_validate(long).sections[0].blocks[0])


def test_diagram_fallback_boundary() -> None:
    payload = document_payload()
    component = payload["sections"][0]["blocks"][10]  # type: ignore[index]
    component["components"] = [
        {
            "id": f"node-{index}",
            "label": str(index),
            "description": None,
            "kind": "other",
            "group": "one" if index % 2 else "two",
        }
        for index in range(12)
    ]
    component["relations"] = []
    block = ViewerDocument.model_validate(payload).sections[0].blocks[10]
    assert not diagram_uses_table(block)  # type: ignore[arg-type]
    component["components"].append(
        {"id": "node-12", "label": "12", "description": None, "kind": "other", "group": "one"}
    )
    block = ViewerDocument.model_validate(payload).sections[0].blocks[10]
    assert diagram_uses_table(block)  # type: ignore[arg-type]
