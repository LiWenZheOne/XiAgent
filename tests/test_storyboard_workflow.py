from __future__ import annotations

from pathlib import Path
from typing import Any

from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes import build_node_registry
from xiagent.nodes.ai.deepseek_structured_json import DeepSeekStructuredJsonNode
from xiagent.nodes.ai.runninghub_image import RunningHubImageToImageNode
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.assemble_segment_context import AssembleSegmentContextNode
from xiagent.nodes.tools.script_split import ScriptSplitNode
from xiagent.nodes.tools.storyboard_prompt import StoryboardPromptAssemblerNode
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.console import ConsoleIO
from xiagent.workflows.testing.runner import WorkflowTestRunner
from xiagent.workflows.validator import validate_workflow_contract

STORYBOARD_WORKFLOW_PATH = Path("workflows/global/storyboard_generation.workflow.yaml")


def test_storyboard_workflow_contract_is_serial_and_uses_expected_nodes(test_settings) -> None:
    contract = load_workflow_file(STORYBOARD_WORKFLOW_PATH)

    assert contract["workflow"]["id"] == "storyboard_generation"
    assert contract["workflow"]["version"] == "1.0.1"
    assert contract["workflow"]["scope"] == "global"
    assert contract["workflow"]["input_schema"]["required"] == ["script"]

    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    assert list(nodes_by_id) == [
        "split_script",
        "analyze_characters",
        "assemble_context",
        "describe_panels",
        "match_characters",
        "collect_assets",
        "assemble_prompt",
        "generate_image",
    ]
    assert {node_id: node["ref"] for node_id, node in nodes_by_id.items()} == {
        "split_script": "tool.script_split.v1",
        "analyze_characters": "ai.deepseek_structured_json.v1",
        "assemble_context": "tool.assemble_segment_context.v1",
        "describe_panels": "ai.deepseek_structured_json.v1",
        "match_characters": "ai.deepseek_structured_json.v1",
        "collect_assets": "system.human_approval.v1",
        "assemble_prompt": "tool.storyboard_prompt_assembler.v1",
        "generate_image": "ai.runninghub_image_to_image.v1",
    }
    assert contract["edges"] == [
        {"from": "START", "to": "split_script"},
        {"from": "split_script", "to": "analyze_characters"},
        {"from": "analyze_characters", "to": "assemble_context"},
        {"from": "assemble_context", "to": "describe_panels"},
        {"from": "describe_panels", "to": "match_characters"},
        {"from": "match_characters", "to": "collect_assets"},
        {"from": "collect_assets", "to": "assemble_prompt"},
        {"from": "assemble_prompt", "to": "generate_image"},
        {"from": "generate_image", "to": "END"},
    ]

    assert nodes_by_id["split_script"]["inputs"]["script"] == {
        "from": "$workflow.input.script"
    }
    assert nodes_by_id["describe_panels"]["inputs"]["prompt"]["vars"]["segments_context"] == {
        "from": "$nodes.assemble_context.output.context_string"
    }
    assert nodes_by_id["collect_assets"]["outputs"]["properties"]["image_urls"] == {
        "type": "array",
        "minItems": 1,
        "items": {"type": "string", "minLength": 1},
    }
    assert nodes_by_id["assemble_prompt"]["inputs"]["image_urls"] == {
        "from": "$nodes.collect_assets.output.image_urls"
    }
    assert nodes_by_id["assemble_prompt"]["inputs"]["description"] == {
        "from": "$nodes.describe_panels.output.segment_descriptions.0.panels.0.description"
    }
    assert nodes_by_id["generate_image"]["inputs"]["prompt"] == {
        "from": "$nodes.assemble_prompt.output.prompt"
    }
    assert nodes_by_id["generate_image"]["inputs"]["image_urls"] == {
        "from": "$nodes.assemble_prompt.output.image_urls"
    }
    assert nodes_by_id["generate_image"]["inputs"]["negative_prompt"] == {
        "from": "$nodes.assemble_prompt.output.negative_prompt"
    }
    assert nodes_by_id["generate_image"]["inputs"]["poll_interval_seconds"] == {"value": 2}
    assert nodes_by_id["generate_image"]["inputs"]["poll_timeout_seconds"] == {"value": 720}

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_storyboard_workflow_declares_structured_llm_output_schemas(test_settings) -> None:
    contract = load_workflow_file(STORYBOARD_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    character_schema = nodes_by_id["analyze_characters"]["outputs"]
    panel_schema = nodes_by_id["describe_panels"]["outputs"]

    assert character_schema["type"] == "object"
    assert "segment_analyses" in character_schema["required"]
    assert character_schema["properties"]["segment_analyses"]["type"] == "array"
    assert panel_schema["type"] == "object"
    assert "segment_descriptions" in panel_schema["required"]
    assert panel_schema["properties"]["segment_descriptions"]["type"] == "array"

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_storyboard_character_prompt_requires_object_root_with_characters() -> None:
    contract = load_workflow_file(STORYBOARD_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    prompt_template = nodes_by_id["analyze_characters"]["inputs"]["prompt"]["template"]
    system_prompt = nodes_by_id["analyze_characters"]["inputs"]["system"]["value"]

    assert "JSON 对象" in prompt_template
    assert "根键" in prompt_template
    assert "segment_analyses" in prompt_template
    assert "不要返回根数组" in prompt_template
    assert "clothing" in prompt_template
    assert "event" in prompt_template
    assert "服装" in system_prompt
    assert "事件" in system_prompt
    assert nodes_by_id["describe_panels"]["inputs"]["prompt"]["vars"]["segments_context"] == {
        "from": "$nodes.assemble_context.output.context_string"
    }


def test_storyboard_character_schema_accepts_common_role_field(test_settings) -> None:
    contract = load_workflow_file(STORYBOARD_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    character_schema = nodes_by_id["analyze_characters"]["outputs"]

    validate_json_value(
        character_schema,
        {
            "segment_analyses": [
                {
                    "index": 0,
                    "thinking": "Paragraph describes a sword-draw scene.",
                    "location": "Mountain gate",
                    "time": "Night",
                    "characters": {
                        "protagonist": {
                            "clothing": "未指定",
                            "event": "在场",
                            "aliases": ["hero"],
                        }
                    },
                }
            ]
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_storyboard_panel_prompt_limits_panel_item_fields() -> None:
    contract = load_workflow_file(STORYBOARD_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    prompt_template = nodes_by_id["describe_panels"]["inputs"]["prompt"]["template"]

    assert "每个分格对象必须包含" in prompt_template
    assert "character_focus" in prompt_template
    assert "environment_details" in prompt_template
    assert "分格对象不得包含上述以外的其他键" in prompt_template
    assert "segment_descriptions" in prompt_template


def test_storyboard_panel_schema_accepts_common_optional_panel_fields(test_settings) -> None:
    contract = load_workflow_file(STORYBOARD_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    panel_schema = nodes_by_id["describe_panels"]["outputs"]

    validate_json_value(
        panel_schema,
        {
            "segment_descriptions": [
                {
                    "index": 0,
                    "segment_title": "Snowy Temple",
                    "thinking": "Cold moonlight vs warm firelight creates tension.",
                    "panels": [
                        {
                            "description": "The protagonist holds position in a snowy temple yard.",
                            "style": "cinematic ink animation",
                            "constraints": "Keep costume, weapon, snow, and fire continuity.",
                            "character_focus": "protagonist with a spear",
                            "environment_details": "snowy temple yard with distant firelight",
                            "shot_type": "wide shot",
                            "camera_angle": "low angle",
                            "lighting": "cold moonlight contrasted with warm firelight",
                            "mood": "tense and decisive",
                            "continuity_notes": "Preserve the same costume and location as references.",
                        }
                    ],
                }
            ]
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


async def test_storyboard_workflow_accepts_panel_segment_title_from_deepseek(
    tmp_path: Path,
    monkeypatch,
) -> None:
    router = FakeStoryboardRouter()
    router._deepseek_responses[1] = (
        '{"segment_descriptions": [{"index": 0, "segment_title": "风雪山神庙", '
        '"thinking": "林冲在雪夜山神庙外，冷色雪夜与暖色火光强对比营造紧张氛围。", '
        '"panels": [{"description": "林冲在雪夜山神庙外按住花枪，远处草料场火光冲天。", '
        '"style": "电影感国风动画，冷色雪夜与暖色火光强对比", '
        '"constraints": "保持林冲服装、花枪和雪夜环境一致，不要添加文字。"}]}]}'
    )
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _storyboard_registry(router),
    )
    workflow_dir = tmp_path / "empty-workflows"
    workflow_dir.mkdir()
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    answers = iter(['["https://assets.test/linchong-reference.png"]'])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
    )

    result = await runner.run_workflow_file(
        STORYBOARD_WORKFLOW_PATH,
        input_data={"script": _long_shuihu_script()},
    )

    assert result.task.status == "succeeded"
    describe_execution = next(
        execution
        for execution in result.node_executions
        if execution.node_id == "describe_panels"
    )
    assert describe_execution.output_snapshot["segment_descriptions"][0]["segment_title"] == "风雪山神庙"
    assert describe_execution.output_snapshot["segment_descriptions"][0]["panels"][0]["description"].startswith("林冲")
    assert describe_execution.output_snapshot["segment_descriptions"][0]["thinking"] == "林冲在雪夜山神庙外，冷色雪夜与暖色火光强对比营造紧张氛围。"


async def test_storyboard_workflow_runs_with_manual_asset_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    router = FakeStoryboardRouter()
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _storyboard_registry(router),
    )
    workflow_dir = tmp_path / "empty-workflows"
    workflow_dir.mkdir()
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    answers = iter(['["https://assets.test/reference.png"]'])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
    )

    result = await runner.run_workflow_file(
        STORYBOARD_WORKFLOW_PATH,
        input_data={"script": "（2）山门前，主角拔剑。"},
    )

    assert result.task.status == "succeeded"
    assert [execution.node_id for execution in result.node_executions] == [
        "split_script",
        "analyze_characters",
        "assemble_context",
        "describe_panels",
        "match_characters",
        "collect_assets",
        "assemble_prompt",
        "generate_image",
    ]
    assert result.node_executions[-1].output_snapshot["image_url"] == (
        "https://cdn.runninghub.test/storyboard.png"
    )
    assert [request.provider for request in router.requests] == [
        "deepseek",
        "deepseek",
        "deepseek",
        "runninghub_image",
    ]
    assert router.requests[-1].metadata["image_urls"] == [
        "https://assets.test/reference.png"
    ]


class FakeStoryboardRouter(ChatModelRouter):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []
        self._deepseek_responses = [
            # analyze_characters
            '{"segment_analyses": [{"index": 0, "thinking": "Paragraph describes protagonist drawing sword.", "location": "山门前", "time": "", "characters": {"主角": {"clothing": "未指定", "event": "在场", "aliases": []}}}]}',
            # describe_panels
            (
                '{"segment_descriptions": [{"index": 0, "segment_title": "山门前拔剑", '
                '"thinking": " protagonist draws sword in rain and mist.", '
                '"panels": [{"description": "主角在山门前拔剑，雨雾压低远山。", '
                '"style": "电影感国风动画", '
                '"constraints": "保持角色服装和发型一致。"}]}]}'
            ),
            # match_characters
            '{"character_matches": [{"script_name": "主角", "matched_asset": null, "reason": "Generic protagonist name.", "confidence": "uncertain"}]}',
        ]

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        if request.provider == "runninghub_image":
            return ChatResponse(
                text="https://cdn.runninghub.test/storyboard.png",
                model=request.model,
                usage={"credits": 1},
                metadata={
                    "provider": request.provider,
                    "results": [{"url": "https://cdn.runninghub.test/storyboard.png"}],
                    "task_id": "storyboard-task-001",
                    "status": "SUCCESS",
                },
            )
        return ChatResponse(
            text=self._deepseek_responses.pop(0),
            model=request.model,
            usage={"completion_tokens": 1},
            metadata={"provider": request.provider},
        )


def _storyboard_registry(router: FakeStoryboardRouter) -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(ScriptSplitNode())
    registry.register(AssembleSegmentContextNode())
    registry.register(StoryboardPromptAssemblerNode())
    registry.register(
        DeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model="deepseek-test-model",
        )
    )
    registry.register(
        RunningHubImageToImageNode(
            model_router=router,
            provider="runninghub_image",
            model="runninghub-image-test-model",
        )
    )
    return registry


def _long_shuihu_script() -> str:
    return (
        "（1）风雪山神庙外，林冲披着旧毡笠踏雪而来，衣角被寒风掀起。"
        "他回头望向远处草料场，火光在雪幕里忽明忽暗，像有人故意点燃。"
        "庙门半掩，供桌积灰，墙上剥落的神像在风声中显得压迫。"
        "林冲听见门外陆谦几人的笑声，慢慢握紧花枪，眼神从隐忍转为决绝。\n\n"
        "（2）火势越来越大，草料场的黑烟翻卷到夜空。"
        "林冲踢开庙门冲入雪地，花枪横扫，逼得仇人连连后退。"
        "风雪、火光、刀影交错，他终于不再退让。"
    )
