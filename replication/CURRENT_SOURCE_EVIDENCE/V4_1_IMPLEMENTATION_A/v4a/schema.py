"""Small self-contained validator for the frozen V4 result schema vocabulary."""

import re
from typing import Any, Dict, List


class SchemaValidationError(ValueError):
    pass


def _fail(path: str, message: str) -> None:
    raise SchemaValidationError("{}: {}".format(path, message))


def _validate(instance: Any, schema: Dict[str, Any], path: str) -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(instance, dict):
            _fail(path, "expected object")
        required = schema.get("required", [])
        missing = [key for key in required if key not in instance]
        if missing:
            _fail(path, "missing required keys {}".format(sorted(missing)))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(instance) - set(properties))
            if extra:
                _fail(path, "unexpected keys {}".format(extra))
        for key, value in instance.items():
            if key in properties:
                _validate(value, properties[key], "{}.{}".format(path, key))
    elif expected_type == "array":
        if not isinstance(instance, list):
            _fail(path, "expected array")
        item_schema = schema.get("items")
        if item_schema:
            for index, value in enumerate(instance):
                _validate(value, item_schema, "{}[{}]".format(path, index))
    elif expected_type == "string":
        if not isinstance(instance, str):
            _fail(path, "expected string")
    elif expected_type == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            _fail(path, "expected integer")
    elif expected_type == "boolean":
        if not isinstance(instance, bool):
            _fail(path, "expected boolean")

    if "const" in schema and instance != schema["const"]:
        _fail(path, "does not match const")
    if "enum" in schema and instance not in schema["enum"]:
        _fail(path, "not in enum")
    if "pattern" in schema:
        if not isinstance(instance, str) or re.search(schema["pattern"], instance) is None:
            _fail(path, "does not match pattern")
    if "minimum" in schema:
        if not isinstance(instance, int) or instance < schema["minimum"]:
            _fail(path, "below minimum")


def validate_result(instance: Dict[str, Any], schema: Dict[str, Any]) -> None:
    _validate(instance, schema, "$")


def collect_validation_errors(instance: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    try:
        validate_result(instance, schema)
    except SchemaValidationError as exc:
        return [str(exc)]
    return []
