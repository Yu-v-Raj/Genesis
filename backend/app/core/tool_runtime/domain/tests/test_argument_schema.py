"""The argument validator accepts exactly what a tool declares, and nothing else."""

import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.argument_schema import matches_schema, schema_problems
from backend.app.core.tool_runtime.domain.exceptions import ToolNotFoundError, ToolSchemaError
from backend.app.core.tool_runtime.domain.tool import Tool, builtin_tools
from backend.app.core.tool_runtime.domain.tool_metadata import ToolMetadata


SCHEMAS = {tool.name: tool.definition.parameters for tool in builtin_tools()}

# What the Tools page and the workflow builder send today (frontend/lib/tools.ts).
FRONTEND_PAYLOADS = {
    "echo": {"message": "Hello Genesis"},
    "calculator": {"expression": "2 + 5 * 10"},
    "uuid": {},
    "random_number": {"min": 1, "max": 100},
    "delay": {"seconds": 2},
}


@pytest.mark.parametrize("tool_name", sorted(FRONTEND_PAYLOADS))
def test_every_current_payload_still_validates(tool_name: str) -> None:
    assert matches_schema(FRONTEND_PAYLOADS[tool_name], SCHEMAS[tool_name])
    assert matches_schema({"seconds": 0.5}, SCHEMAS["delay"])


@pytest.mark.parametrize("tool_name", sorted(FRONTEND_PAYLOADS))
def test_an_undeclared_argument_is_rejected_for_every_builtin(tool_name: str) -> None:
    assert not matches_schema({**FRONTEND_PAYLOADS[tool_name], "unexpected": "x"}, SCHEMAS[tool_name])


def test_missing_required_wrong_types_and_bounds_are_rejected() -> None:
    assert not matches_schema({}, SCHEMAS["echo"])
    assert not matches_schema({"message": 5}, SCHEMAS["echo"])
    assert not matches_schema({"min": 1.5, "max": 2}, SCHEMAS["random_number"])
    assert not matches_schema({"min": True, "max": 2}, SCHEMAS["random_number"])
    assert not matches_schema({"seconds": 61}, SCHEMAS["delay"])
    assert not matches_schema({"seconds": "2"}, SCHEMAS["delay"])
    assert not matches_schema(["message"], SCHEMAS["echo"])


NESTED = {
    "type": "object",
    "properties": {
        "recipient": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "count": {"type": "integer", "minimum": 1, "maximum": 3},
    },
    "required": ["recipient"],
}


def test_nested_objects_arrays_and_integer_bounds_are_checked() -> None:
    assert matches_schema({"recipient": {"name": "Ada"}, "tags": ["a"], "count": 2}, NESTED)
    assert not matches_schema({"recipient": {"name": "Ada", "role": "x"}}, NESTED)  # nested extra key
    assert not matches_schema({"recipient": {}}, NESTED)
    assert not matches_schema({"recipient": {"name": "Ada"}, "tags": ["a", 1]}, NESTED)
    assert not matches_schema({"recipient": {"name": "Ada"}, "count": 4}, NESTED)


def test_extra_keys_are_allowed_only_when_the_schema_says_so() -> None:
    open_schema = {"type": "object", "properties": {}, "additionalProperties": True}
    typed_extras = {"type": "object", "properties": {}, "additionalProperties": {"type": "string"}}

    assert matches_schema({"anything": [1]}, open_schema)
    assert matches_schema({"a": "x"}, typed_extras)
    assert not matches_schema({"a": 1}, typed_extras)
    assert not matches_schema({"a": 1}, {"type": "object"})  # no properties declared: nothing accepted


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "pattern": "^a$"},  # a constraint this validator can't enforce
        {"type": "string", "enum": ["a"]},
        {"properties": {}},  # no type
        {"type": "date"},
        {"type": "number", "minimum": "0"},
        {"type": "object", "properties": {}, "additionalProperties": "yes"},
    ],
)
def test_schemas_the_validator_cannot_enforce_reject_everything(schema: dict) -> None:
    assert not matches_schema("a", schema)
    assert not matches_schema({}, schema)
    assert not matches_schema(1, schema)


def test_annotations_do_not_restrict() -> None:
    assert matches_schema("a", {"type": "string", "description": "A name.", "title": "Name"})


# --------------------------------------------------------- non-finite numbers


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected_even_without_bounds(value: float) -> None:
    assert not matches_schema(value, {"type": "number"})
    assert not matches_schema({"seconds": value}, SCHEMAS["delay"])
    assert matches_schema(1.5, {"type": "number"})


# ------------------------------------------------------ schema registration


@pytest.mark.parametrize("tool_name", sorted(SCHEMAS))
def test_every_builtin_schema_is_registrable(tool_name: str) -> None:
    assert schema_problems(SCHEMAS[tool_name]) == []


@pytest.mark.parametrize(
    ("schema", "problem"),
    [
        ({"type": "object", "properties": {}, "required": ["to"]}, "isn't declared in properties"),
        ({"type": "object", "properties": {"a": {"type": "string", "pattern": "x"}}}, "unsupported keyword 'pattern'"),
        ({"type": "object", "properties": {"a": {"type": "string"}}, "enum": [1]}, "unsupported keyword 'enum'"),
        ({"properties": {}}, "needs a supported type"),
        ({"type": ["string", "null"]}, "needs a supported type"),
        ("object", "must be an object"),
        ({"type": "object", "properties": []}, "properties must be an object"),
        ({"type": "object", "properties": {"a": "string"}}, "parameters.properties.a must be an object"),
        ({"type": "object", "required": "a", "properties": {"a": {"type": "string"}}}, "required must be a list"),
        ({"type": "object", "required": ["a", "a"], "properties": {"a": {"type": "string"}}}, "lists a name twice"),
        ({"type": "object", "additionalProperties": "yes"}, "additionalProperties must be"),
        ({"type": "object", "additionalProperties": {"type": "date"}}, "additionalProperties needs a supported type"),
        ({"type": "array", "items": {"type": "string", "minLength": 1}}, "items uses unsupported keyword"),
        ({"type": "number", "minimum": 5, "maximum": 1}, "minimum greater than maximum"),
        ({"type": "number", "maximum": float("inf")}, "must be a finite number"),
        ({"type": "integer", "minimum": True}, "must be a finite number"),
    ],
)
def test_unenforceable_schemas_are_reported(schema: object, problem: str) -> None:
    assert any(problem in message for message in schema_problems(schema)), schema_problems(schema)


@pytest.mark.asyncio
async def test_registration_refuses_a_tool_whose_schema_cannot_be_enforced() -> None:
    bus = EventBus()
    registry = ToolRegistry(bus)
    for tool in builtin_tools():
        await registry.register(tool)  # every built-in is valid

    async def handler(_):
        raise AssertionError("never called")

    broken = Tool(
        definition=ToolMetadata(
            name="send_email",
            description="d",
            parameters={"type": "object", "properties": {"to": {"type": "string", "format": "email"}}, "required": ["to", "subject"]},
        ),
        handler=handler,
    )
    with pytest.raises(ToolSchemaError) as raised:
        await registry.register(broken)

    assert len(raised.value.problems) == 2  # the unsupported "format" and the undeclared "subject"
    with pytest.raises(ToolNotFoundError):
        registry.get("send_email")
    assert [tool.name for tool in registry.list()] == [tool.name for tool in builtin_tools()]
