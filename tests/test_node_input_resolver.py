from __future__ import annotations

import pytest

from xiagent.core.errors import ValidationError
from xiagent.runtime.input_resolver import resolve_node_inputs


def test_input_resolver_resolves_array_index_in_node_output_path() -> None:
    resolved = resolve_node_inputs(
        {"description": {"from": "$nodes.scene.output.segments.0.description"}},
        node_outputs={
            "scene": {
                "segments": [
                    {"description": "opening shot"},
                    {"description": "wide shot"},
                ]
            }
        },
    )

    assert resolved == {"description": "opening shot"}


@pytest.mark.parametrize(
    "reference",
    [
        "$nodes.scene.output.segments.2.description",
        "$nodes.scene.output.segments.one.description",
    ],
)
def test_input_resolver_rejects_invalid_array_index_in_node_output_path(
    reference: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_node_inputs(
            {"description": {"from": reference}},
            node_outputs={"scene": {"segments": [{"description": "opening shot"}]}},
        )

    assert exc_info.value.code == "workflow_reference_missing_key"


def test_input_resolver_uses_submitted_user_inputs() -> None:
    resolved = resolve_node_inputs(
        {
            "prompt": {"from_user": True},
            "style": {"value": "cinematic"},
        },
        node_outputs={},
        user_input={"prompt": "雨夜城市"},
    )

    assert resolved == {"prompt": "雨夜城市", "style": "cinematic"}


def test_input_resolver_requires_submitted_user_input() -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_node_inputs(
            {"prompt": {"from_user": True}},
            node_outputs={},
        )

    assert exc_info.value.code == "workflow_user_input_required"
