# ruff: noqa: E501
from __future__ import annotations

from collections import Counter, defaultdict, deque
from html import escape
from typing import Any

from jinja2 import Environment, StrictUndefined, select_autoescape

from backend.app.viewers.document import (
    Block,
    BulletListBlock,
    CalloutBlock,
    ComparisonBlock,
    ComponentMapBlock,
    FlowBlock,
    KeyValueBlock,
    ParagraphBlock,
    SourceEvidenceBlock,
    StateDiagramBlock,
    StepsBlock,
    ViewerDocument,
)

RENDERER_VERSION = "viewer-html-v1"
_ENV = Environment(
    autoescape=select_autoescape(default=True, default_for_string=True),
    undefined=StrictUndefined,
)

_TEMPLATES = {
    "paragraph": "<p>{{ block.text }}</p>",
    "bullet_list": """
<{% if block.ordered %}ol{% else %}ul{% endif %}>
{% for item in block.items %}<li>{{ item }}</li>{% endfor %}
</{% if block.ordered %}ol{% else %}ul{% endif %}>""",
    "key_value": """
<dl>{% for item in block.items %}<div class="viewer-key-value-row"><dt>{{ item.key }}</dt><dd>{{ item.value }}</dd></div>{% endfor %}</dl>""",
    "table": """
<div class="viewer-scroll"><table>{% if block.title %}<caption>{{ block.title }}</caption>{% endif %}<thead><tr>{% for column in block.columns %}<th scope="col">{{ column.label }}</th>{% endfor %}</tr></thead><tbody>{% for row in block.rows %}<tr>{% for cell in row.cells %}<td>{{ cell }}</td>{% endfor %}</tr>{% endfor %}</tbody></table></div>""",
    "code": """
{% if block.caption %}<p class="viewer-code-caption">{{ block.caption }}</p>{% endif %}<div class="viewer-scroll"><pre><code class="language-{{ block.language }}">{{ block.code }}</code></pre></div>""",
    "callout": '<aside class="viewer-callout viewer-callout-{{ block.tone }}" role="note"><p>{{ block.text }}</p></aside>',
    "steps": """
<ol class="viewer-steps">{% for item in block.items %}<li><strong>{{ item.label }}</strong><p>{{ item.description }}</p></li>{% endfor %}</ol>""",
    "comparison": """
<div class="viewer-scroll"><table><thead><tr><th scope="col">観点</th>{% for item in block.series %}<th scope="col">{{ item.label }}</th>{% endfor %}</tr></thead><tbody>{% for row in block.rows %}<tr><th scope="row">{{ row.aspect }}</th>{% for value in row.values %}<td>{{ value }}</td>{% endfor %}</tr>{% endfor %}</tbody></table></div>""",
    "source_evidence": """
<ul class="viewer-evidence">{% for item in block.items %}<li><button type="button" data-source-reference-id="{{ item.source_reference_id }}">根拠を表示</button><span>{{ item.explanation }}</span></li>{% endfor %}</ul>""",
}


def render_viewer_document(document: ViewerDocument) -> str:
    source_map = {source.id: source for source in document.source_references}
    sections: list[str] = []
    for section in document.sections:
        rendered = [_render_block(block, source_map) for block in section.blocks]
        groups = _group_blocks(section.blocks, rendered)
        summary = (
            f'<p class="viewer-section-summary">{escape(section.summary)}</p>'
            if section.summary
            else ""
        )
        sections.append(
            f'<section class="viewer-section" id="{escape(section.id)}">'
            f"<h2>{escape(section.heading)}</h2>{summary}"
            f'<div class="viewer-block-grid">{"".join(groups)}</div></section>'
        )
    limitations = ""
    if document.limitations:
        items = "".join(f"<li>{escape(item)}</li>" for item in document.limitations)
        limitations = (
            '<aside class="viewer-limitations" role="note"><h2>調査上の制約</h2>'
            f"<ul>{items}</ul></aside>"
        )
    return (
        '<article class="viewer-document">'
        f'<p class="viewer-document-summary">{escape(document.summary)}</p>'
        f"{''.join(sections)}{limitations}</article>"
    )


def is_compact(block: Block) -> bool:
    title_length = len((block.title or "").strip())
    if isinstance(block, ParagraphBlock):
        return title_length + len(block.text.strip()) <= 600
    if isinstance(block, BulletListBlock):
        return len(block.items) <= 6 and title_length + sum(map(len, block.items)) <= 600
    if isinstance(block, StepsBlock):
        total = title_length + sum(len(item.label) + len(item.description) for item in block.items)
        return len(block.items) <= 4 and total <= 800
    if isinstance(block, ComparisonBlock):
        total = title_length + sum(len(item.label) for item in block.series)
        total += sum(len(row.aspect) + sum(map(len, row.values)) for row in block.rows)
        return len(block.series) == 2 and len(block.rows) <= 4 and total <= 800
    if isinstance(block, KeyValueBlock):
        total = title_length + sum(len(item.key) + len(item.value) for item in block.items)
        return len(block.items) <= 6 and total <= 800
    if isinstance(block, CalloutBlock):
        return title_length + len(block.text.strip()) <= 500
    if isinstance(block, SourceEvidenceBlock):
        total = title_length + sum(len(item.explanation) for item in block.items)
        return len(block.items) <= 4 and total <= 800
    return False


def diagram_uses_table(block: FlowBlock | StateDiagramBlock | ComponentMapBlock) -> bool:
    nodes, edges = _diagram_parts(block)
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    for edge in edges:
        outgoing[edge.from_] += 1
        incoming[edge.to] += 1
    maximum_degree = max(
        max(incoming.values(), default=0),
        max(outgoing.values(), default=0),
    )
    if len(nodes) >= 13 or len(edges) >= 19 or maximum_degree >= 4:
        return True
    if isinstance(block, FlowBlock):
        return _flow_stage_count(block) >= 9
    if isinstance(block, ComponentMapBlock):
        groups = Counter(node.group or "未分類" for node in nodes)
        return len(groups) >= 5 or max(groups.values(), default=0) >= 9
    return False


def _group_blocks(blocks: list[Block], rendered: list[str]) -> list[str]:
    output: list[str] = []
    index = 0
    while index < len(blocks):
        if is_compact(blocks[index]) and index + 1 < len(blocks) and is_compact(blocks[index + 1]):
            output.append(
                f'<div class="viewer-compact-pair">{rendered[index]}{rendered[index + 1]}</div>'
            )
            index += 2
        else:
            output.append(rendered[index])
            index += 1
    return output


def _render_block(block: Block, source_map: dict[str, Any]) -> str:
    heading = f"<h3>{escape(block.title)}</h3>" if block.title else ""
    if isinstance(block, (FlowBlock, StateDiagramBlock, ComponentMapBlock)):
        body = _render_diagram(block)
    else:
        body = _ENV.from_string(_TEMPLATES[block.type]).render(block=block)
    sources = ""
    if block.source_reference_ids and not isinstance(block, SourceEvidenceBlock):
        buttons = "".join(
            '<li><button type="button" data-source-reference-id="'
            f'{escape(source_id)}">{escape(source_map[source_id].description)}</button></li>'
            for source_id in block.source_reference_ids
        )
        sources = (
            f'<nav class="viewer-sources" aria-label="根拠となるソース"><ul>{buttons}</ul></nav>'
        )
    return (
        f'<section class="viewer-block viewer-block-{escape(block.type)}" '
        f'data-block-type="{escape(block.type)}">{heading}{body}{sources}</section>'
    )


def _render_diagram(block: FlowBlock | StateDiagramBlock | ComponentMapBlock) -> str:
    nodes, edges = _diagram_parts(block)
    node_map = {node.id: node for node in nodes}
    if diagram_uses_table(block):
        rows: list[str] = []
        for edge in edges:
            source, target = node_map[edge.from_], node_map[edge.to]
            relation = getattr(edge, "kind", "")
            target_kind = getattr(target, "kind", "")
            extra = relation or target_kind
            groups = ""
            if isinstance(block, ComponentMapBlock):
                groups = f"{source.group or '未分類'} → {target.group or '未分類'}"
            rows.append(
                f"<tr><td>{escape(source.label)}</td><td>{escape(target.label)}</td>"
                f"<td>{escape(edge.label or '')}</td><td>{escape(extra)}</td>"
                f"<td>{escape(groups or target.description or '')}</td></tr>"
            )
        return (
            '<div class="viewer-scroll"><table class="viewer-diagram-table"><thead><tr>'
            '<th scope="col">接続元</th><th scope="col">接続先</th><th scope="col">ラベル</th>'
            '<th scope="col">種類</th><th scope="col">詳細</th></tr></thead><tbody>'
            f"{''.join(rows)}</tbody></table></div>"
        )
    cards = "".join(
        '<div class="viewer-diagram-node">'
        f"<span>{escape(getattr(node, 'kind', ''))}</span><strong>{escape(node.label)}</strong>"
        f"{f'<p>{escape(node.description)}</p>' if node.description else ''}</div>"
        for node in nodes
    )
    relations = "".join(
        f"<li><strong>{escape(node_map[edge.from_].label)}</strong> → "
        f"<strong>{escape(node_map[edge.to].label)}</strong>"
        f"{f': {escape(edge.label)}' if edge.label else ''}</li>"
        for edge in edges
    )
    return (
        f'<div class="viewer-diagram-cards">{cards}</div>'
        f'<ol class="viewer-diagram-relations">{relations}</ol>'
    )


def _diagram_parts(
    block: FlowBlock | StateDiagramBlock | ComponentMapBlock,
) -> tuple[list[Any], list[Any]]:
    if isinstance(block, FlowBlock):
        return block.nodes, block.edges
    if isinstance(block, StateDiagramBlock):
        return block.states, block.transitions
    return block.components, block.relations


def _flow_stage_count(block: FlowBlock) -> int:
    incoming = Counter({node.id: 0 for node in block.nodes})
    adjacent: dict[str, list[str]] = defaultdict(list)
    for edge in block.edges:
        incoming[edge.to] += 1
        adjacent[edge.from_].append(edge.to)
    queue = deque((node.id, 1) for node in block.nodes if incoming[node.id] == 0)
    highest = 0
    stages: dict[str, int] = {}
    while queue:
        node_id, stage = queue.popleft()
        stages[node_id] = max(stages.get(node_id, 0), stage)
        highest = max(highest, stage)
        for target in adjacent[node_id]:
            incoming[target] -= 1
            if incoming[target] == 0:
                parent_stages = [stages[edge.from_] for edge in block.edges if edge.to == target]
                queue.append((target, max(parent_stages) + 1))
    return highest
