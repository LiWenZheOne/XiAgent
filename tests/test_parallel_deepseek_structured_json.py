from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.base import NodeContext, NodeResult


class FakeParallelRouter(ChatModelRouter):
    def __init__(self, responses: list[str]) -> None:
        super().__init__()
        self.requests: list[Any] = []
        self._responses = responses

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            text=self._responses.pop(0),
            model=request.model,
            usage={"completion_tokens": 1},
            metadata={"provider": request.provider},
        )


def test_parallel_node_describe() -> None:
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=FakeParallelRouter([]),
        provider="deepseek",
        model="test-model",
    )
    desc = node.describe()
    assert desc.ref == "ai.parallel_deepseek_structured_json.v1"
    assert desc.input_schema["required"] == ["items", "prompt_template"]
    assert "required_input_fields" in desc.input_schema["properties"]


@pytest.mark.asyncio
async def test_parallel_node_processes_all_items() -> None:
    responses = [
        '{"result": "a"}',
        '{"result": "b"}',
        '{"result": "c"}',
    ]
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [{"id": 1}, {"id": 2}, {"id": 3}],
            "prompt_template": "Process: {item}",
            "max_attempts": 1,
        },
    )

    assert result.status == "succeeded"
    assert result.output["results"] == [
        {"result": "a"},
        {"result": "b"},
        {"result": "c"},
    ]
    assert len(router.requests) == 3
    assert all(request.metadata == {"response_format": {"type": "json_object"}} for request in router.requests)


@pytest.mark.asyncio
async def test_parallel_node_empty_items_raises() -> None:
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=FakeParallelRouter([]),
        provider="deepseek",
        model="test-model",
    )

    with pytest.raises(ValidationError, match="items must be a non-empty array or an object containing non-empty arrays"):
        await node.run(
            None,
            {
                "items": [],
                "prompt_template": "Process: {item}",
            },
        )


@pytest.mark.asyncio
async def test_parallel_node_processes_object_groups_in_asset_order() -> None:
    responses = [
        '{"result": "character"}',
        '{"result": "asset"}',
        '{"result": "prop"}',
    ]
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": {
                "props": [{"name": "官刀"}],
                "characters": [{"name": "林冲"}],
                "assets": [{"name": "山神庙"}],
            },
            "prompt_template": "Process: {item}",
            "max_attempts": 1,
        },
    )

    assert result.status == "succeeded"
    assert result.output["results"] == [
        {"result": "character"},
        {"result": "asset"},
        {"result": "prop"},
    ]
    assert len(router.requests) == 3
    prompts = [request.messages[-1].content for request in router.requests]
    assert "林冲" in prompts[0]
    assert "山神庙" in prompts[1]
    assert "官刀" in prompts[2]


@pytest.mark.asyncio
async def test_parallel_node_missing_template_raises() -> None:
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=FakeParallelRouter([]),
        provider="deepseek",
        model="test-model",
    )

    with pytest.raises(ValidationError, match="prompt_template cannot be empty"):
        await node.run(
            None,
            {
                "items": [{"id": 1}],
                "prompt_template": "",
            },
        )


@pytest.mark.asyncio
async def test_parallel_node_template_interpolation() -> None:
    responses = ['{"name": "test"}']
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    await node.run(
        None,
        {
            "items": [{"full_name": "林冲", "age": "中年"}],
            "prompt_template": "角色：{item}",
            "max_attempts": 1,
        },
    )

    request = router.requests[0]
    assert "林冲" in request.messages[-1].content
    assert "中年" in request.messages[-1].content


@pytest.mark.asyncio
async def test_parallel_node_expands_item_and_shared_context_placeholders() -> None:
    responses = ['{"name": "test"}']
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    await node.run(
        None,
        {
            "items": [{"paragraph_text": "林冲踏雪。", "panel_count": "3-4"}],
            "shared_context": {
                "full_script": "完整剧本",
                "prompt_rules": {
                    "material_rule": "- 不写材质。",
                    "enrich_rule": "- 增加空间深度。",
                },
            },
            "prompt_template": (
                "完整：{full_script}\n"
                "原文：{paragraph_text}\n"
                "建议分格数：{panel_count}\n"
                "{material_rule}\n"
                "{enrich_rule}\n"
                "未知：{missing_value}"
            ),
            "prompt_fields": ["paragraph_text", "panel_count"],
            "max_attempts": 1,
        },
    )

    user_prompt = router.requests[0].messages[-1].content
    assert "完整：完整剧本" in user_prompt
    assert "原文：林冲踏雪。" in user_prompt
    assert "建议分格数：3-4" in user_prompt
    assert "- 不写材质。" in user_prompt
    assert "- 增加空间深度。" in user_prompt
    assert "{missing_value}" in user_prompt


@pytest.mark.asyncio
async def test_parallel_node_merges_shared_context_into_prompt_item() -> None:
    responses = ['{"name": "test"}']
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    await node.run(
        None,
        {
            "items": [{"index": 1, "current_segment": {"text": "当前段"}}],
            "shared_context": {
                "full_script": "完整剧本",
                "all_segments": [{"index": 0, "text": "前一段"}],
            },
            "prompt_template": "Process: {item}",
            "prompt_fields": ["index", "current_segment"],
            "max_attempts": 1,
        },
    )

    user_prompt = router.requests[0].messages[-1].content
    assert "完整剧本" in user_prompt
    assert "前一段" in user_prompt
    assert "当前段" in user_prompt


@pytest.mark.asyncio
async def test_parallel_node_filters_prompt_fields_and_passthroughs_program_fields() -> None:
    responses = ['{"asset_name": "乡民", "prompt": "黑灰短发，眉眼锋利"}']
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )
    ctx = NodeContext(
        user_id="user-1",
        project_id="project-1",
        task_id="task-1",
        node_id="generate_prompt",
        node_execution_id="exec-1",
        config={},
        output_schema={
            "type": "object",
            "required": ["results"],
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                            "required": ["asset_name", "prompt", "reference_image_ref"],
                            "properties": {
                            "asset_name": {"type": "string"},
                            "prompt": {"type": "string"},
                            "reference_image_ref": {
                                "type": "object",
                                "required": ["kind", "asset_id"],
                                "properties": {
                                    "kind": {"type": "string"},
                                    "asset_id": {"type": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    },
                }
            },
            "additionalProperties": False,
        },
        asset_service=None,
        event_sink=None,
        logger=None,
    )

    result = await node.run(
        ctx,
        {
            "items": [
                {
                        "asset_name": "村民",
                    "appearance_description": "黑灰短发，眉眼锋利。",
                    "reference_image_ref": {"kind": "asset", "asset_id": "template-character"},
                }
            ],
            "prompt_template": "Process: {item}",
                "prompt_fields": ["asset_name", "appearance_description"],
                "passthrough_fields": ["asset_name", "reference_image_ref"],
            "max_attempts": 1,
        },
    )

    assert result.output["results"] == [
        {
            "asset_name": "村民",
            "prompt": "黑灰短发，眉眼锋利",
            "reference_image_ref": {"kind": "asset", "asset_id": "template-character"},
        }
    ]
    user_prompt = router.requests[0].messages[-1].content
    schema_prompt = router.requests[0].messages[0].content
    assert "full_name" not in schema_prompt
    assert "reference_image_ref" not in user_prompt
    assert "reference_image_ref" not in schema_prompt
    assert "appearance_description" in user_prompt


@pytest.mark.asyncio
async def test_parallel_node_with_system_prompt() -> None:
    responses = ['{"result": "ok"}']
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    await node.run(
        None,
        {
            "items": [{"id": 1}],
            "prompt_template": "Process: {item}",
            "system": "You are a helpful assistant.",
            "max_attempts": 1,
        },
    )

    request = router.requests[0]
    system_msg = request.messages[0]
    assert system_msg.role == "system"
    assert "You are a helpful assistant" in system_msg.content


@pytest.mark.asyncio
async def test_parallel_node_retry_on_parse_failure() -> None:
    responses = [
        "not json",
        '{"result": "ok"}',
    ]
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [{"id": 1}],
            "prompt_template": "Process: {item}",
            "max_attempts": 2,
        },
    )

    assert result.status == "succeeded"
    assert result.output["results"] == [{"result": "ok"}]
    assert len(router.requests) == 2


@pytest.mark.asyncio
async def test_parallel_node_can_continue_after_single_item_failure() -> None:
    responses = [
        '{"result": "ok"}',
        "not json",
    ]
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [{"index": 0, "name": "成功段"}, {"index": 1, "name": "失败段"}],
            "prompt_template": "Process: {item}",
            "passthrough_fields": ["index", "name"],
            "max_attempts": 1,
            "continue_on_item_error": True,
        },
    )

    assert result.status == "succeeded"
    assert result.output["results"][0] == {"result": "ok", "index": 0, "name": "成功段"}
    failed = result.output["results"][1]
    assert failed["index"] == 1
    assert failed["name"] == "失败段"
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "structured_json_parse_failed"
    assert failed["error"]["message"] == "DeepSeek response is not valid JSON"


@pytest.mark.asyncio
async def test_parallel_node_fails_item_when_required_input_field_missing() -> None:
    router = FakeParallelRouter(['{"result": "unused"}'])
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [{"index": 0, "name": "缺场景"}],
            "prompt_template": "Process: {item}",
            "passthrough_fields": ["index", "name"],
            "required_input_fields": ["scene_layout", "panel_plan"],
            "continue_on_item_error": True,
            "max_attempts": 1,
        },
    )

    failed = result.output["results"][0]
    assert failed["index"] == 0
    assert failed["name"] == "缺场景"
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "parallel_llm_required_input_missing"
    assert failed["error"]["details"]["missing_fields"] == ["scene_layout", "panel_plan"]
    assert router.requests == []
