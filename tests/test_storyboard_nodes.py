from __future__ import annotations

import json
from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes import build_node_registry
from xiagent.nodes.base import NodeContext


class FakeStructuredJsonRouter(ChatModelRouter):
    def __init__(self, responses: list[str]) -> None:
        super().__init__()
        self._responses = list(responses)
        self.requests: list[Any] = []

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        text = self._responses.pop(0)
        return ChatResponse(
            text=text,
            model=request.model,
            usage={"completion_tokens": 1},
            metadata={"provider": request.provider},
        )


def test_storyboard_nodes_are_registered(test_settings) -> None:
    registry = build_node_registry(test_settings)
    refs = {node.describe().ref for node in registry.list()}

    assert {
        "tool.script_split.v1",
        "ai.deepseek_structured_json.v1",
        "tool.storyboard_prompt_assembler.v1",
        "tool.assemble_segment_context.v1",
    }.issubset(refs)


async def test_script_split_parses_marked_and_unmarked_segments(test_settings) -> None:
    node = build_node_registry(test_settings).get("tool.script_split.v1")

    result = await node.run(
        ctx=None,
        inputs={
            "script": (
                "（2）山门前，主角拔剑。\n\n"
                "(2-3) The chase crosses the market.\n\n"
                "没有标记的收束段落。"
            )
        },
    )

    assert result.status == "succeeded"
    assert result.output == {
        "count": 3,
        "segments": [
            {
                "index": 0,
                "text": "山门前，主角拔剑。",
                "panel_hint": "2",
                "panel_count_min": 2,
                "panel_count_max": 2,
            },
            {
                "index": 1,
                "text": "The chase crosses the market.",
                "panel_hint": "2-3",
                "panel_count_min": 2,
                "panel_count_max": 3,
            },
            {
                "index": 2,
                "text": "没有标记的收束段落。",
                "panel_hint": "1",
                "panel_count_min": 1,
                "panel_count_max": 1,
            },
        ],
    }


async def test_script_split_uses_blank_lines_for_unmarked_script(test_settings) -> None:
    node = build_node_registry(test_settings).get("tool.script_split.v1")

    result = await node.run(ctx=None, inputs={"script": "第一段\n\n第二段\n\n第三段"})

    assert result.output["count"] == 3
    assert [segment["index"] for segment in result.output["segments"]] == [0, 1, 2]
    assert [segment["panel_hint"] for segment in result.output["segments"]] == ["1", "1", "1"]


async def test_storyboard_prompt_assembler_builds_prompt_and_defaults(test_settings) -> None:
    node = build_node_registry(test_settings).get("tool.storyboard_prompt_assembler.v1")
    image_urls = ["https://assets.test/character.png"]

    result = await node.run(
        ctx=None,
        inputs={
            "description": "主角在雨夜码头回头，远处灯火映在水面。",
            "style": "电影感国风动画",
            "constraints": "保持角色服装和发型一致，不要添加文字。",
            "generation_rules": "风格指令\n参考《罗小黑战记》。\n角色一致性约束\n- 达摩/不倒翁体型。",
            "negative_prompt": "low quality",
            "image_urls": image_urls,
        },
    )

    assert result.status == "succeeded"
    assert result.output["image_urls"] == image_urls
    assert result.output["aspect_ratio"] == "16:9"
    assert result.output["resolution"] == "2K"
    assert "negative_prompt" in result.output
    assert "low quality" in result.output["negative_prompt"]
    prompt = result.output["prompt"]
    assert "分镜描述" in prompt
    assert "主角在雨夜码头回头" in prompt
    assert "画风" in prompt
    assert "电影感国风动画" in prompt
    assert "额外约束" in prompt
    assert "保持角色服装和发型一致" in prompt
    assert "固定图像生成规则" in prompt
    assert "风格指令" in prompt
    assert "罗小黑战记" in prompt
    assert "角色一致性约束" in prompt
    assert "达摩/不倒翁体型" in prompt
    assert "负面提示词" not in prompt


async def test_storyboard_prompt_assembler_allows_render_options(test_settings) -> None:
    node = build_node_registry(test_settings).get("tool.storyboard_prompt_assembler.v1")

    result = await node.run(
        ctx=None,
        inputs={
            "description": "近景，角色握紧信物。",
            "style": "写实厚涂",
            "constraints": "低饱和度",
            "negative_prompt": "low quality",
            "image_urls": ["https://assets.test/reference.png"],
            "aspect_ratio": "9:16",
            "resolution": "1K",
        },
    )

    assert result.output["aspect_ratio"] == "9:16"
    assert result.output["resolution"] == "1K"


async def test_storyboard_prompt_assembler_rejects_empty_image_urls(test_settings) -> None:
    node = build_node_registry(test_settings).get("tool.storyboard_prompt_assembler.v1")

    with pytest.raises(ValidationError) as exc:
        await node.run(
            ctx=None,
            inputs={
                "description": "近景，角色握紧信物。",
                "style": "写实厚涂",
                "constraints": "低饱和度",
                "image_urls": [],
            },
        )

    assert exc.value.code == "image_urls_required"


async def test_deepseek_structured_json_parses_plain_json(test_settings) -> None:
    router = FakeStructuredJsonRouter(['{"characters": [{"name": "阿宁"}]}'])
    node = _structured_node(test_settings, router)
    schema = {
        "type": "object",
        "properties": {
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["characters"],
        "additionalProperties": False,
    }

    result = await node.run(
        ctx=_ctx(schema),
        inputs={"prompt": "extract characters", "system": "return json only"},
    )

    assert result.status == "succeeded"
    assert result.output == {"characters": [{"name": "阿宁"}]}
    assert router.requests[0].messages[0].role == "system"
    assert router.requests[0].messages[-1].content == "extract characters"


async def test_deepseek_structured_json_includes_output_schema_in_model_instruction(
    test_settings,
) -> None:
    router = FakeStructuredJsonRouter(['{"characters": [{"name": "Aning"}]}'])
    node = _structured_node(test_settings, router)
    schema = {
        "type": "object",
        "properties": {
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["characters"],
        "additionalProperties": False,
    }

    await node.run(ctx=_ctx(schema), inputs={"prompt": "extract characters"})

    schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    system_messages = [
        message.content for message in router.requests[0].messages if message.role == "system"
    ]
    assert system_messages
    assert "Target JSON Schema" in system_messages[0]
    assert schema_text in system_messages[0]


async def test_deepseek_structured_json_parses_markdown_json_fence(test_settings) -> None:
    router = FakeStructuredJsonRouter(['```json\n{"panels": [{"description": "wide shot"}]}\n```'])
    node = _structured_node(test_settings, router)
    schema = {
        "type": "object",
        "properties": {
            "panels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"description": {"type": "string"}},
                    "required": ["description"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["panels"],
        "additionalProperties": False,
    }

    result = await node.run(ctx=_ctx(schema), inputs={"prompt": "describe panels"})

    assert result.output == {"panels": [{"description": "wide shot"}]}


async def test_deepseek_structured_json_retries_invalid_json(test_settings) -> None:
    router = FakeStructuredJsonRouter(["not json", '{"ok": true}'])
    node = _structured_node(test_settings, router)
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }

    result = await node.run(ctx=_ctx(schema), inputs={"prompt": "return ok", "max_attempts": 2})

    assert result.output == {"ok": True}
    assert len(router.requests) == 2


async def test_deepseek_structured_json_raises_when_schema_mismatch(test_settings) -> None:
    router = FakeStructuredJsonRouter(['{"ok": "yes"}'])
    node = _structured_node(test_settings, router)
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }

    with pytest.raises(ValidationError):
        await node.run(ctx=_ctx(schema), inputs={"prompt": "return ok", "max_attempts": 1})


def _structured_node(test_settings, router: FakeStructuredJsonRouter):
    node = build_node_registry(test_settings).get("ai.deepseek_structured_json.v1")
    node._model_router = router
    node._provider = "deepseek"
    node._model = "deepseek-test-model"
    return node


def _ctx(output_schema: dict[str, Any]) -> NodeContext:
    return NodeContext(
        user_id="user_1",
        project_id="project_1",
        task_id="task_1",
        node_id="node_1",
        node_execution_id="node_execution_1",
        config={},
        output_schema=output_schema,
        asset_service=None,
        event_sink=None,
        logger=None,
    )
