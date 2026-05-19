from __future__ import annotations

from xiagent.core.ids import new_id
from xiagent.core.schemas import validate_json_schema
from xiagent.core.types import Scope


def test_new_id_has_prefix() -> None:
    value = new_id("task")
    assert value.startswith("task_")
    assert len(value) > len("task_")


def test_validate_json_schema_accepts_object_schema() -> None:
    validate_json_schema({"type": "object", "properties": {"name": {"type": "string"}}})


def test_scope_values_are_stable() -> None:
    assert Scope.GLOBAL == "global"
    assert Scope.PROJECT == "project"
    assert Scope.COMBINED == "combined"
