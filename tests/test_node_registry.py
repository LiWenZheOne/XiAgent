from __future__ import annotations

import pytest

from xiagent.core.errors import ConflictError, ValidationError
from xiagent.nodes import build_node_registry
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.system.user_choice import SystemUserChoiceNode
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
        "system.user_choice.v1",
        "system.workflow_input.v1",
        "tool.echo.v1",
        "tool.script_split.v1",
        "tool.assemble_segment_context.v1",
        "tool.assemble_storyboard_context.v1",
        "tool.asset_lookup.v1",
        "tool.create_text_asset.v1",
        "tool.enrich_characters.v1",
        "tool.extract_panel_image_urls.v1",
        "tool.runninghub_workflow_images.v1",
        "tool.storyboard_prompt_assembler.v1",
        "tool.storyboard_prompt_assembler.v2",
        "ai.assign_assets_to_segments.v1",
        "ai.deepseek_chat.v1",
        "ai.deepseek_structured_json.v1",
        "ai.parallel_deepseek_structured_json.v1",
        "ai.runninghub_image_to_image.v1",
        "ai.runninghub_image_to_image.v2",
        "ai.runninghub_image_to_image.v3",
        "ai.runninghub_text_to_image.v1",
        "ai.gemini_vision.v1",
        "tool.merge_asset_images.v1",
    }


class UiDefaultProbeNode(BaseNode):
    def __init__(self, *, ui_defaults: dict | None = None) -> None:
        self._ui_defaults = ui_defaults or {}

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.ui_default_probe.v1",
            name="UI Default Probe",
            version="1.0.0",
            kind="test",
            input_schema={
                "type": "object",
                "properties": {
                    "candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "image_url": {"type": "string"},
                            },
                        },
                    }
                },
            },
            output_schema={"type": "object"},
            ui_defaults=self._ui_defaults,
        )

    async def run(self, ctx: NodeContext | None, inputs: dict) -> NodeResult:
        return NodeResult(status="succeeded", output={})


def test_register_node_with_valid_ui_defaults() -> None:
    registry = NodeRegistry()

    registry.register(
        UiDefaultProbeNode(
            ui_defaults={
                "controls": {
                    "interaction": {
                        "control_id": "ui.choice.image_three.v1",
                        "variant": "equal_grid",
                        "mode": "interactive",
                        "bindings": {
                            "items_path": "$node.input.candidates",
                            "image_url_path": "image_url",
                            "value_path": "id",
                        },
                    }
                }
            }
        )
    )

    assert registry.get("test.ui_default_probe.v1").describe().ui_defaults


def test_register_node_rejects_unknown_ui_default_control() -> None:
    registry = NodeRegistry()

    with pytest.raises(ValidationError) as exc_info:
        registry.register(
            UiDefaultProbeNode(
                ui_defaults={
                    "controls": {
                        "interaction": {
                            "control_id": "ui.missing.v1",
                            "variant": "default",
                            "mode": "interactive",
                            "bindings": {},
                        }
                    }
                }
            )
        )

    assert exc_info.value.code == "unknown_ui_control"


def test_register_node_rejects_ui_default_missing_binding() -> None:
    registry = NodeRegistry()

    with pytest.raises(ValidationError) as exc_info:
        registry.register(
            UiDefaultProbeNode(
                ui_defaults={
                    "controls": {
                        "interaction": {
                            "control_id": "ui.choice.image_three.v1",
                            "variant": "equal_grid",
                            "mode": "interactive",
                            "bindings": {"items_path": "$node.input.candidates"},
                        }
                    }
                }
            )
        )

    assert exc_info.value.code == "missing_ui_binding"


async def test_user_choice_node_waits_with_candidates_metadata() -> None:
    node = SystemUserChoiceNode()
    candidates = [{"id": "a", "image_url": "https://example.test/a.png"}]

    result = await node.run(ctx=None, inputs={"question": "选择一张", "candidates": candidates})

    assert result.status == "waiting"
    assert result.output == {}
    assert result.metadata == {
        "question": "选择一张",
        "candidates": candidates,
        "selection_mode": "single",
    }


async def test_workflow_input_node_waits_with_output_schema_metadata() -> None:
    from xiagent.nodes.base import NodeContext
    from xiagent.nodes.system.workflow_input import WorkflowInputNode

    output_schema = {
        "type": "object",
        "required": ["prompt", "image_urls"],
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "image_urls": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
        },
        "additionalProperties": False,
    }
    ctx = NodeContext(
        user_id="user_1",
        project_id="project_1",
        task_id="task_1",
        node_id="collect_workflow_input",
        node_execution_id="node_exec_1",
        config={"title": "填写运行输入", "description": "提供图生图参数"},
        output_schema=output_schema,
        asset_service=None,
        event_sink=None,
        logger=None,
    )

    result = await WorkflowInputNode().run(ctx, {})
    descriptor = WorkflowInputNode().describe()

    assert result.status == "waiting"
    assert result.output == {}
    assert descriptor.ui_defaults["controls"]["interaction"] == {
        "control_id": "ui.input.schema_form.v1",
        "variant": "default",
        "mode": "input",
    }
    assert result.metadata["input_schema"] == output_schema
    assert result.metadata["title"] == "填写运行输入"
    assert result.metadata["description"] == "提供图生图参数"
    assert result.metadata["requested_inputs"] == {}


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
            runninghub_image_default_aspect_ratio="4:3",
            runninghub_image_default_resolution="2K",
            runninghub_image_poll_interval_seconds=0.1,
            runninghub_image_poll_timeout_seconds=1.0,
            runninghub_text_to_image_api_key="settings-runninghub-key",
            runninghub_text_to_image_base_url="https://settings.runninghub.test",
            runninghub_text_to_image_model="settings-text-model",
            runninghub_text_to_image_endpoint="/settings/text-to-image",
            runninghub_text_to_image_default_aspect_ratio="1:1",
            runninghub_text_to_image_default_resolution="4K",
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

    image_provider = image_node._model_router._providers["runninghub_image"]  # noqa: SLF001
    text_provider = text_node._model_router._providers["runninghub_text_to_image"]  # noqa: SLF001
    assert image_provider._config.default_aspect_ratio == "4:3"  # noqa: SLF001
    assert image_provider._config.default_resolution == "2K"  # noqa: SLF001
    assert text_provider._config.default_aspect_ratio == "1:1"  # noqa: SLF001
    assert text_provider._config.default_resolution == "4K"  # noqa: SLF001


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
