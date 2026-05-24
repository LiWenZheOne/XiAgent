from __future__ import annotations

import pytest

from xiagent.core.errors import ConflictError
from xiagent.nodes import build_node_registry
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode


def test_register_and_get_node() -> None:
    registry = NodeRegistry()
    node = HumanApprovalNode()
    registry.register(node)
    assert registry.get("system.human_approval.v1") is node


def test_duplicate_node_ref_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    with pytest.raises(ConflictError):
        registry.register(HumanApprovalNode())


def test_registering_non_base_node_is_rejected() -> None:
    registry = NodeRegistry()

    with pytest.raises(TypeError):
        registry.register(object())  # type: ignore[arg-type]


def test_list_returns_nodes_in_registration_order() -> None:
    registry = NodeRegistry()
    human_node = HumanApprovalNode()
    echo_node = EchoToolNode()

    registry.register(human_node)
    registry.register(echo_node)

    assert registry.list() == [human_node, echo_node]


def test_build_node_registry_registers_builtin_nodes(test_settings) -> None:
    registry = build_node_registry(test_settings)

    refs = {node.describe().ref for node in registry.list()}

    assert refs == {
        "system.human_approval.v1",
        "tool.echo.v1",
        "tool.script_split.v1",
        "tool.assemble_segment_context.v1",
        "tool.asset_lookup.v1",
        "tool.storyboard_prompt_assembler.v1",
        "ai.deepseek_chat.v1",
        "ai.deepseek_structured_json.v1",
        "ai.parallel_deepseek_structured_json.v1",
        "ai.runninghub_image_to_image.v1",
        "ai.runninghub_text_to_image.v1",
    }


def test_build_node_registry_uses_settings_deepseek_model(test_settings) -> None:
    from dataclasses import replace

    registry = build_node_registry(
        replace(
            test_settings,
            deepseek_api_key="settings-test-key",
            deepseek_base_url="https://settings.deepseek.test",
            deepseek_model="settings-model",
        )
    )

    deepseek_node = registry.get("ai.deepseek_chat.v1")

    assert deepseek_node._model == "settings-model"  # noqa: SLF001


def test_build_node_registry_uses_settings_runninghub_models(test_settings) -> None:
    from dataclasses import replace

    registry = build_node_registry(
        replace(
            test_settings,
            runninghub_image_api_key="settings-runninghub-key",
            runninghub_image_base_url="https://settings.runninghub.test",
            runninghub_image_model="settings-image-model",
            runninghub_image_endpoint="/settings/image-to-image",
            runninghub_image_poll_interval_seconds=0.1,
            runninghub_image_poll_timeout_seconds=1.0,
            runninghub_text_to_image_api_key="settings-runninghub-key",
            runninghub_text_to_image_base_url="https://settings.runninghub.test",
            runninghub_text_to_image_model="settings-text-model",
            runninghub_text_to_image_endpoint="/settings/text-to-image",
            runninghub_text_to_image_poll_interval_seconds=0.1,
            runninghub_text_to_image_poll_timeout_seconds=1.0,
        )
    )

    image_node = registry.get("ai.runninghub_image_to_image.v1")
    text_node = registry.get("ai.runninghub_text_to_image.v1")

    assert image_node._provider == "runninghub_image"  # noqa: SLF001
    assert image_node._model == "settings-image-model"  # noqa: SLF001
    assert text_node._provider == "runninghub_text_to_image"  # noqa: SLF001
    assert text_node._model == "settings-text-model"  # noqa: SLF001


def test_node_context_asset_service_is_core_service_interface() -> None:
    from typing import get_type_hints

    from xiagent.core.services import AssetService
    from xiagent.nodes.base import NodeContext

    hints = get_type_hints(NodeContext)

    assert hints["asset_service"] == AssetService | None


async def test_human_approval_returns_waiting_with_requested_inputs() -> None:
    node = HumanApprovalNode()
    inputs = {"question": "Approve?", "context": {"risk": "low"}}

    result = await node.run(ctx=None, inputs=inputs)

    assert result.status == "waiting"
    assert result.output == {}
    assert result.metadata["requested_inputs"] == inputs


async def test_echo_tool_returns_inputs() -> None:
    node = EchoToolNode()
    inputs = {"message": "hello", "count": 2}

    result = await node.run(ctx=None, inputs=inputs)

    assert result.status == "succeeded"
    assert result.output == {"echo": inputs}
