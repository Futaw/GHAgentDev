"""Schema generation for Codex Structured Outputs, separate from local validation."""

from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue
from pydantic_core import core_schema


class CodexOutputSchema(GenerateJsonSchema):
    def tagged_union_schema(self, schema: core_schema.TaggedUnionSchema) -> JsonSchemaValue:
        generated = super().tagged_union_schema(schema)
        # Pydantic's tagged choices have disjoint Literal discriminators. anyOf
        # therefore accepts the same values, without unsupported OpenAPI metadata.
        generated["anyOf"] = generated.pop("oneOf")
        generated.pop("discriminator", None)
        return generated


def codex_output_schema(model: type[BaseModel]) -> dict[str, object]:
    return TypeAdapter(model).json_schema(schema_generator=CodexOutputSchema)
