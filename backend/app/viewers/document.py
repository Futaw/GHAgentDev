from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

ID_PATTERN = r"^[a-z][a-z0-9-]{0,63}$"
MAX_DOCUMENT_BYTES = 1_048_576


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceReference(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    path: str = Field(min_length=1, max_length=500)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_range(self) -> SourceReference:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class BlockBase(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    type: str
    title: str | None = Field(max_length=120)
    source_reference_ids: list[str] = Field(max_length=20)

    @field_validator("source_reference_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source_reference_ids must be unique")
        return value


class ParagraphBlock(BlockBase):
    type: Literal["paragraph"]
    text: str = Field(min_length=1, max_length=6000)


class BulletListBlock(BlockBase):
    type: Literal["bullet_list"]
    ordered: bool
    items: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(
        min_length=1, max_length=30
    )


class KeyValueItem(StrictModel):
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)


class KeyValueBlock(BlockBase):
    type: Literal["key_value"]
    items: list[KeyValueItem] = Field(min_length=1, max_length=30)


class TableColumn(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)


class TableRow(StrictModel):
    cells: list[Annotated[str, Field(max_length=1000)]]


class TableBlock(BlockBase):
    type: Literal["table"]
    columns: list[TableColumn] = Field(min_length=1, max_length=12)
    rows: list[TableRow] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_table(self) -> TableBlock:
        ids = [column.id for column in self.columns]
        if len(ids) != len(set(ids)):
            raise ValueError("column ids must be unique")
        if any(len(row.cells) != len(self.columns) for row in self.rows):
            raise ValueError("table cell count must match columns")
        return self


class CodeBlock(BlockBase):
    type: Literal["code"]
    language: str = Field(min_length=1, max_length=40)
    code: str = Field(min_length=1, max_length=20000)
    caption: str | None = Field(max_length=500)

    @field_validator("code")
    @classmethod
    def line_limit(cls, value: str) -> str:
        if len(value.splitlines()) > 200:
            raise ValueError("code must contain at most 200 lines")
        return value


class CalloutBlock(BlockBase):
    type: Literal["callout"]
    tone: Literal["info", "warning", "limitation"]
    text: str = Field(min_length=1, max_length=2000)


class StepItem(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)


class StepsBlock(BlockBase):
    type: Literal["steps"]
    items: list[StepItem] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_ids(self) -> StepsBlock:
        _ensure_unique([item.id for item in self.items], "step ids")
        return self


class Edge(StrictModel):
    from_: str = Field(alias="from", pattern=ID_PATTERN)
    to: str = Field(pattern=ID_PATTERN)
    label: str | None = Field(max_length=1000)


class FlowNode(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    description: str | None = Field(max_length=1000)
    kind: Literal["start", "process", "decision", "end"]


class FlowBlock(BlockBase):
    type: Literal["flow"]
    nodes: list[FlowNode] = Field(min_length=2, max_length=30)
    edges: list[Edge] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def valid_graph(self) -> FlowBlock:
        _validate_graph(self.nodes, self.edges)
        starts = [node.id for node in self.nodes if node.kind == "start"]
        ends = {node.id for node in self.nodes if node.kind == "end"}
        if len(starts) != 1 or not ends:
            raise ValueError("flow requires exactly one start and at least one end")
        incoming, outgoing = _degrees(self.nodes, self.edges)
        if incoming[starts[0]] or any(outgoing[item] for item in ends):
            raise ValueError("flow start/end degree is invalid")
        for node in self.nodes:
            if node.kind == "decision":
                branches = [edge for edge in self.edges if edge.from_ == node.id]
                if len(branches) < 2 or any(not edge.label for edge in branches):
                    raise ValueError("decision requires at least two labelled branches")
        order = _topological_order(self.nodes, self.edges)
        if order is None:
            raise ValueError("flow must not contain cycles")
        reachable = _reachable(starts[0], self.edges)
        if reachable != {node.id for node in self.nodes}:
            raise ValueError("all flow nodes must be reachable from start")
        reverse = [
            Edge.model_validate({"from": edge.to, "to": edge.from_, "label": edge.label})
            for edge in self.edges
        ]
        reaching_end: set[str] = set()
        for end in ends:
            reaching_end |= _reachable(end, reverse)
        if reaching_end != {node.id for node in self.nodes}:
            raise ValueError("all flow nodes must reach an end")
        return self


class StateNode(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    description: str | None = Field(max_length=1000)
    kind: Literal["initial", "normal", "success", "failure"]


class StateDiagramBlock(BlockBase):
    type: Literal["state_diagram"]
    states: list[StateNode] = Field(min_length=2, max_length=30)
    transitions: list[Edge] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def valid_graph(self) -> StateDiagramBlock:
        _validate_graph(self.states, self.transitions)
        initials = [state.id for state in self.states if state.kind == "initial"]
        if len(initials) != 1:
            raise ValueError("state diagram requires exactly one initial state")
        if _reachable(initials[0], self.transitions) != {state.id for state in self.states}:
            raise ValueError("all states must be reachable from initial")
        return self


class ComparisonSeries(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)


class ComparisonRow(StrictModel):
    aspect: str = Field(min_length=1, max_length=120)
    values: list[Annotated[str, Field(max_length=1000)]]


class ComparisonBlock(BlockBase):
    type: Literal["comparison"]
    series: list[ComparisonSeries] = Field(min_length=2, max_length=4)
    rows: list[ComparisonRow] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def valid_comparison(self) -> ComparisonBlock:
        _ensure_unique([item.id for item in self.series], "series ids")
        if any(len(row.values) != len(self.series) for row in self.rows):
            raise ValueError("comparison value count must match series")
        return self


class ComponentNode(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    description: str | None = Field(max_length=1000)
    kind: Literal["frontend", "backend", "database", "external", "process", "other"]
    group: str | None = Field(max_length=120)


class ComponentRelation(StrictModel):
    from_: str = Field(alias="from", pattern=ID_PATTERN)
    to: str = Field(pattern=ID_PATTERN)
    kind: Literal["calls", "reads", "writes", "depends_on", "publishes", "subscribes"]
    label: str | None = Field(max_length=1000)


class ComponentMapBlock(BlockBase):
    type: Literal["component_map"]
    components: list[ComponentNode] = Field(min_length=2, max_length=30)
    relations: list[ComponentRelation] = Field(max_length=60)

    @model_validator(mode="after")
    def valid_graph(self) -> ComponentMapBlock:
        _validate_graph(self.components, self.relations)
        return self


class SourceEvidenceItem(StrictModel):
    source_reference_id: str = Field(pattern=ID_PATTERN)
    explanation: str = Field(min_length=1, max_length=500)


class SourceEvidenceBlock(BlockBase):
    type: Literal["source_evidence"]
    items: list[SourceEvidenceItem] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def same_sources(self) -> SourceEvidenceBlock:
        if {item.source_reference_id for item in self.items} != set(self.source_reference_ids):
            raise ValueError("source_evidence ids must equal source_reference_ids")
        return self


Block = Annotated[
    ParagraphBlock
    | BulletListBlock
    | KeyValueBlock
    | TableBlock
    | CodeBlock
    | CalloutBlock
    | StepsBlock
    | FlowBlock
    | StateDiagramBlock
    | ComparisonBlock
    | ComponentMapBlock
    | SourceEvidenceBlock,
    Field(discriminator="type"),
]


class Section(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    heading: str = Field(min_length=1, max_length=120)
    summary: str | None = Field(max_length=500)
    blocks: list[Block] = Field(min_length=1, max_length=30)


class ViewerDocument(StrictModel):
    schema_version: Literal["1.0"]
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    sections: list[Section] = Field(min_length=1, max_length=20)
    source_references: list[SourceReference] = Field(min_length=1, max_length=100)
    limitations: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(max_length=20)

    @model_validator(mode="after")
    def valid_document(self) -> ViewerDocument:
        _ensure_unique([section.id for section in self.sections], "section ids")
        blocks = [block for section in self.sections for block in section.blocks]
        if len(blocks) > 100:
            raise ValueError("document must contain at most 100 blocks")
        _ensure_unique([block.id for block in blocks], "block ids")
        _ensure_unique([source.id for source in self.source_references], "source ids")
        source_ids = {source.id for source in self.source_references}
        used: set[str] = set()
        for block in blocks:
            refs = set(block.source_reference_ids)
            if not refs <= source_ids:
                raise ValueError("block references an unknown source")
            if not refs and not (isinstance(block, CalloutBlock) and block.tone == "limitation"):
                raise ValueError("factual blocks require a source reference")
            used |= refs
        if used != source_ids:
            raise ValueError("all source references must be used")
        ranges = [(item.path, item.start_line, item.end_line) for item in self.source_references]
        _ensure_unique(ranges, "source path ranges")
        return self


def parse_viewer_document(raw: str, max_bytes: int = MAX_DOCUMENT_BYTES) -> ViewerDocument:
    if len(raw.encode("utf-8")) > min(max_bytes, MAX_DOCUMENT_BYTES):
        raise ValueError("ViewerDocument exceeds the byte limit")
    return ViewerDocument.model_validate_json(raw)


def viewer_document_json_schema() -> dict[str, object]:
    return TypeAdapter(ViewerDocument).json_schema()


def canonical_document_json(document: ViewerDocument) -> dict[str, object]:
    return json.loads(document.model_dump_json(by_alias=True))


def _ensure_unique(values: list[object], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _validate_graph(nodes: list[object], edges: list[object]) -> None:
    node_ids = [node.id for node in nodes]
    _ensure_unique(node_ids, "node ids")
    node_set = set(node_ids)
    edge_keys: list[tuple[str, str, str | None]] = []
    for edge in edges:
        from_id, to_id = edge.from_, edge.to
        if from_id == to_id:
            raise ValueError("self edges are not allowed")
        if from_id not in node_set or to_id not in node_set:
            raise ValueError("edge references an unknown node")
        edge_keys.append((from_id, to_id, getattr(edge, "label", None)))
    _ensure_unique(edge_keys, "edges")


def _degrees(nodes: list[object], edges: list[object]) -> tuple[Counter[str], Counter[str]]:
    incoming: Counter[str] = Counter({node.id: 0 for node in nodes})
    outgoing: Counter[str] = Counter({node.id: 0 for node in nodes})
    for edge in edges:
        incoming[edge.to] += 1
        outgoing[edge.from_] += 1
    return incoming, outgoing


def _reachable(start: str, edges: list[object]) -> set[str]:
    adjacent: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacent[edge.from_].append(edge.to)
    seen = {start}
    pending = [start]
    while pending:
        for target in adjacent[pending.pop()]:
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return seen


def _topological_order(nodes: list[object], edges: list[object]) -> list[str] | None:
    incoming, _ = _degrees(nodes, edges)
    adjacent: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacent[edge.from_].append(edge.to)
    queue = deque(node.id for node in nodes if incoming[node.id] == 0)
    result: list[str] = []
    while queue:
        current = queue.popleft()
        result.append(current)
        for target in adjacent[current]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    return result if len(result) == len(nodes) else None
