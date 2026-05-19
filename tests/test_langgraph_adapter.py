from __future__ import annotations

import inspect
from collections.abc import Callable

from xiagent.adapters.langgraph.adapter import LangGraphAdapter


def test_adapter_exposes_engine_name() -> None:
    adapter = LangGraphAdapter()
    assert adapter.engine_name == "langgraph"


def test_adapter_describe_reports_boundary_status() -> None:
    adapter = LangGraphAdapter()
    assert adapter.describe() == {
        "engine": "langgraph",
        "status": "boundary_only",
    }


def test_public_method_annotations_do_not_expose_langgraph_types() -> None:
    public_methods = [
        member
        for name, member in inspect.getmembers(LangGraphAdapter)
        if not name.startswith("_") and isinstance(member, Callable)
    ]

    for method in public_methods:
        signature = inspect.signature(method)
        annotations = [
            signature.return_annotation,
            *(parameter.annotation for parameter in signature.parameters.values()),
        ]

        assert all("langgraph" not in str(annotation).lower() for annotation in annotations)
