from __future__ import annotations

import pickle

from xiagent.core.errors import ValidationError
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


def test_core_error_initializes_exception_args() -> None:
    exc = ValidationError(code="sample", message="Sample message", details={"x": 1})

    assert exc.args == ("sample", "Sample message")
    assert str(exc) == "sample: Sample message"


def test_core_error_pickle_roundtrip_preserves_fields_and_args() -> None:
    exc = ValidationError(code="sample", message="Sample message", details={"x": 1})

    restored = pickle.loads(pickle.dumps(exc))

    assert restored.code == "sample"
    assert restored.message == "Sample message"
    assert restored.details == {"x": 1}
    assert restored.args == ("sample", "Sample message")
