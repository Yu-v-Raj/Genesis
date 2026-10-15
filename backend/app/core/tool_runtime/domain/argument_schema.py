"""The authoritative check of tool arguments against a tool's declared parameters.

Supports the JSON Schema subset tool declarations use: ``type`` (object, string, integer,
number, boolean, array), ``properties``, ``required``, ``additionalProperties``,
``items``, and ``minimum``/``maximum``. The check is closed by default:

- an object accepts only its declared ``properties`` unless ``additionalProperties`` is
  ``true`` (any value) or a schema (each extra value must match it);
- a schema that uses a constraint this validator does not understand (``pattern``,
  ``enum``, ...) rejects every value, so an unenforced restriction never silently passes;
- numbers must be finite (no NaN or infinity).

``schema_problems`` checks a schema itself against the same subset. Tool registration uses
it, so a tool whose schema could never accept a call fails at startup instead of appearing
usable and refusing every invocation.
"""

import math
from collections.abc import Mapping

# Keywords that describe a value without constraining it.
_ANNOTATIONS = frozenset({"title", "description", "default", "examples"})
_SUPPORTED = {
    "object": frozenset({"type", "properties", "required", "additionalProperties"}),
    "array": frozenset({"type", "items"}),
    "string": frozenset({"type"}),
    "boolean": frozenset({"type"}),
    "integer": frozenset({"type", "minimum", "maximum"}),
    "number": frozenset({"type", "minimum", "maximum"}),
}


def matches_schema(value: object, schema: Mapping[str, object]) -> bool:
    """Whether ``value`` satisfies ``schema``. Unknown types or constraints fail."""
    if not isinstance(schema, Mapping):
        return False
    schema_type = schema.get("type")
    if not isinstance(schema_type, str) or schema_type not in _SUPPORTED:
        return False
    if any(key not in _SUPPORTED[schema_type] and key not in _ANNOTATIONS for key in schema):
        return False
    if schema_type == "object":
        return _matches_object(value, schema)
    if schema_type == "array":
        items = schema.get("items")
        if not isinstance(value, list):
            return False
        return items is None or (isinstance(items, Mapping) and all(matches_schema(item, items) for item in value))
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if isinstance(value, bool) or not isinstance(value, int if schema_type == "integer" else (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return _within_bounds(value, schema)


def _matches_object(value: object, schema: Mapping[str, object]) -> bool:
    if not isinstance(value, Mapping):
        return False
    required = schema.get("required", ())
    properties = schema.get("properties", {})
    extra_schema = schema.get("additionalProperties", False)
    if not isinstance(required, (list, tuple)) or not isinstance(properties, Mapping):
        return False
    if not isinstance(extra_schema, (bool, Mapping)):
        return False
    if any(not isinstance(name, str) or name not in value for name in required):
        return False
    for name, item in value.items():
        if not isinstance(name, str):
            return False
        if name in properties:
            if not matches_schema(item, properties[name]):
                return False
        elif extra_schema is False:
            return False  # an argument the tool never declared
        elif isinstance(extra_schema, Mapping) and not matches_schema(item, extra_schema):
            return False
    return True


def _within_bounds(value: int | float, schema: Mapping[str, object]) -> bool:
    minimum, maximum = schema.get("minimum"), schema.get("maximum")
    for bound in (minimum, maximum):
        if bound is not None and (isinstance(bound, bool) or not isinstance(bound, (int, float)) or not math.isfinite(bound)):
            return False  # a malformed bound can't be enforced
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def schema_problems(schema: object, path: str = "parameters") -> list[str]:
    """Why ``schema`` can't be enforced as written; an empty list means it is valid."""
    if not isinstance(schema, Mapping):
        return [f"{path} must be an object."]
    schema_type = schema.get("type")
    if not isinstance(schema_type, str) or schema_type not in _SUPPORTED:
        return [f"{path} needs a supported type ({', '.join(sorted(_SUPPORTED))})."]
    unsupported = sorted(str(key) for key in schema if key not in _SUPPORTED[schema_type] and key not in _ANNOTATIONS)
    problems = [f"{path} uses unsupported keyword {key!r}." for key in unsupported]
    if schema_type == "object":
        problems += _object_problems(schema, path)
    elif schema_type == "array" and "items" in schema:
        problems += schema_problems(schema["items"], f"{path}.items")
    elif schema_type in {"integer", "number"}:
        problems += _bound_problems(schema, path)
    return problems


def _object_problems(schema: Mapping[str, object], path: str) -> list[str]:
    problems: list[str] = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    extra = schema.get("additionalProperties", False)
    if not isinstance(properties, Mapping):
        problems.append(f"{path}.properties must be an object.")
        properties = {}
    for name, item in properties.items():
        if not isinstance(name, str) or not name:
            problems.append(f"{path}.properties has a name that isn't a non-empty string.")
        else:
            problems += schema_problems(item, f"{path}.properties.{name}")
    if not isinstance(required, (list, tuple)):
        problems.append(f"{path}.required must be a list.")
    else:
        names = [name for name in required if isinstance(name, str)]
        if len(names) != len(required):
            problems.append(f"{path}.required must contain only names.")
        if len(set(names)) != len(names):
            problems.append(f"{path}.required lists a name twice.")
        problems += [f"{path}.required names {name!r}, which isn't declared in properties." for name in names if name not in properties]
    if isinstance(extra, Mapping):
        problems += schema_problems(extra, f"{path}.additionalProperties")
    elif not isinstance(extra, bool):
        problems.append(f"{path}.additionalProperties must be true, false, or a schema.")
    return problems


def _bound_problems(schema: Mapping[str, object], path: str) -> list[str]:
    problems: list[str] = []
    bounds = {key: schema[key] for key in ("minimum", "maximum") if key in schema}
    for key, bound in bounds.items():
        if isinstance(bound, bool) or not isinstance(bound, (int, float)) or not math.isfinite(bound):
            problems.append(f"{path}.{key} must be a finite number.")
    minimum, maximum = bounds.get("minimum"), bounds.get("maximum")
    if not problems and minimum is not None and maximum is not None and minimum > maximum:
        problems.append(f"{path} has minimum greater than maximum, so no value is allowed.")
    return problems
