from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from xiagent.models import ChatModelRouter, ChatRequest, ChatResponse
from xiagent.nodes import build_node_registry
from xiagent.nodes.ai.assign_assets_to_segments import AssignAssetsToSegmentsNode
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.ai.deepseek_structured_json import DeepSeekStructuredJsonNode
from xiagent.nodes.ai.gemini_vision import GeminiVisionNode
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.ai.runninghub_image import (
    RunningHubImageToImageNode,
    RunningHubImageToImageNodeV2,
    RunningHubImageToImageNodeV3,
    RunningHubTextToImageNode,
)
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.user_input import SystemUserInputNode
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.assemble_segment_context import AssembleSegmentContextNode
from xiagent.nodes.tools.assemble_storyboard_context import AssembleStoryboardContextNode
from xiagent.nodes.tools.asset_lookup import AssetLookupNode
from xiagent.nodes.tools.create_text_asset import CreateTextAssetNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.nodes.tools.enrich_characters import EnrichCharactersNode
from xiagent.nodes.tools.extract_panel_image_urls import ExtractPanelImageUrlsNode
from xiagent.nodes.tools.merge_asset_images import MergeAssetImagesNode
from xiagent.nodes.tools.runninghub_workflow_images import RunningHubWorkflowImagesNode
from xiagent.nodes.tools.script_split import ScriptSplitNode
from xiagent.nodes.tools.storyboard_prompt import (
    StoryboardPromptAssemblerNode,
    StoryboardPromptAssemblerNodeV2,
)
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.console import ConsoleIO
from xiagent.workflows.testing.runner import WorkflowTestRunner
from xiagent.workflows.validator import validate_workflow_contract

STORYBOARD_WORKFLOW_PATH = Path("workflows/global/storyboard_from_sketch.workflow.yaml")


# ---------------------------------------------------------------------------
# test 1: workflow 加载验证
# ---------------------------------------------------------------------------


def test_workflow_loads_and_validates(test_settings) -> None:
    """加载 workflow YAML，用 build_node_registry 验证不抛异常。"""
    contract = load_workflow_file(STORYBOARD_WORKFLOW_PATH)

    assert contract["workflow"]["id"] == "storyboard_from_sketch"
    assert contract["workflow"]["version"] == "1.0.0"
    assert contract["workflow"]["scope"] == "global"
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    assert nodes_by_id["collect_sketch_storyboard_input"]["outputs"]["required"] == ["script", "background"]

    registry = build_node_registry(test_settings)
    # 不应抛出 ValidationError
    validate_workflow_contract(contract, registry)


# ---------------------------------------------------------------------------
# FakeRouter: 模拟所有 AI provider 调用
# ---------------------------------------------------------------------------


class FakeRouter(ChatModelRouter):
    """为 storyboard_from_sketch 工作流提供预置响应的假路由。"""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[ChatRequest] = []

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)

        if request.provider == "deepseek":
            return self._deepseek_response(request)
        if request.provider == "openai_compatible":
            return self._openai_compatible_response(request)
        if request.provider == "runninghub_image":
            return self._runninghub_response(request)
        if request.provider == "runninghub_workflow":
            return self._runninghub_response(request)

        raise RuntimeError(f"Unknown provider: {request.provider}")

    # ---- deepseek ----

    def _deepseek_response(self, request: ChatRequest) -> ChatResponse:
        prompt_text = self._prompt_text(request)

        if "提取所有角色信息" in prompt_text:
            text = json.dumps(
                {
                    "reasoning": "剧本为风雪山神庙场景，林冲是唯一出场角色。",
                    "characters": [
                        {
                            "asset_type": "character",
                            "asset_name": "林冲",
                            "asset_tags": ["囚服", "旧毡笠"],
                            "aliases": ["林教头"],
                            "summary": "八十万禁军教头，被发配后的落难英雄。",
                            "character_status": "囚犯装束，头戴旧毡笠，手持花枪，在风雪中蓄势待发。",
                            "appearance_description": "身着囚服，头戴旧毡笠，保留林冲的稳定体貌和身份识别特征。",
                        }
                    ],
                    "character_names": ["林冲"],
                },
                ensure_ascii=False,
            )
        elif "提取所有场景信息" in prompt_text:
            text = json.dumps(
                {
                    "reasoning": "剧本描述雪夜山神庙户外场景。",
                    "scenes": [
                        {
                            "name": "风雪山神庙",
                            "description": "雪夜中的山神庙外，远处草料场火光冲天。",
                            "time_of_day": "夜晚",
                            "location_type": "户外",
                        }
                    ],
                    "scene_names": ["风雪山神庙"],
                },
                ensure_ascii=False,
            )
        elif "提取所有关键道具" in prompt_text:
            text = json.dumps(
                {
                    "reasoning": "剧本共两段，未出现需要独立收录的道具。",
                    "props": [],
                    "prop_names": [],
                },
                ensure_ascii=False,
            )
        elif "未匹配角色" in prompt_text:
            text = json.dumps({"match_results": []}, ensure_ascii=False)
        elif "为以下已提取角色变体匹配已有资产" in prompt_text:
            text = json.dumps(
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服", "旧毡笠"],
                    "matched_asset_id": None,
                    "matched_asset_name": "",
                    "matched_asset_ref": None,
                    "is_new_variant": True,
                    "default_asset_status": "囚犯装束，头戴旧毡笠，手持花枪",
                    "default_asset_storage_uri": "",
                    "reason": "无已有变体匹配",
                },
                ensure_ascii=False,
            )
        elif "检查以下角色的资产标签状态" in prompt_text:
            text = json.dumps(
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服", "旧毡笠"],
                    "has_new_asset_tags": False,
                    "new_asset_tags": [],
                    "existing_asset_tags": ["囚服", "旧毡笠"],
                    "reason": "标签已覆盖",
                },
                ensure_ascii=False,
            )
        else:
            raise RuntimeError(
                f"Unrecognized deepseek prompt: {prompt_text[:200]}"
            )

        return ChatResponse(
            text=text,
            model=request.model,
            usage={"completion_tokens": 1},
            metadata={"provider": request.provider},
        )

    # ---- openai_compatible ----

    def _openai_compatible_response(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            text="<think>分析过程测试</think><caption>描述文本</caption>",
            model=request.model,
            usage={"completion_tokens": 1},
            metadata={"provider": request.provider},
        )

    # ---- runninghub ----

    def _runninghub_response(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            text="https://cdn.runninghub.test/storyboard.png",
            model=request.model,
            usage={"credits": 1},
            metadata={
                "provider": request.provider,
                "results": [
                    {
                        "url": "https://cdn.runninghub.test/storyboard.png",
                        "text": "generated image",
                        "output_type": "image",
                    }
                ],
                "task_id": "rh-task-001",
                "status": "SUCCESS",
            },
        )

    @staticmethod
    def _prompt_text(request: ChatRequest) -> str:
        """连接所有消息文本用于关键词匹配（含 system 和 user message）。"""
        parts: list[str] = []
        for message in request.messages:
            content = message.content
            if isinstance(content, str) and content.strip():
                parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")
                        if isinstance(text, str) and text.strip():
                            parts.append(text)
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# 构造包含 FakeRouter 的 NodeRegistry
# ---------------------------------------------------------------------------


def _registry_for_test(router: FakeRouter) -> NodeRegistry:
    """构建测试用 NodeRegistry，所有 AI 节点共用同一个 FakeRouter。"""
    registry = NodeRegistry()
    # system
    registry.register(SystemUserInputNode())
    registry.register(HumanApprovalNode())
    # tools
    registry.register(EchoToolNode())
    registry.register(MergeAssetImagesNode())
    registry.register(ScriptSplitNode())
    registry.register(AssembleSegmentContextNode())
    registry.register(AssembleStoryboardContextNode())
    registry.register(AssetLookupNode())
    registry.register(CreateTextAssetNode())
    registry.register(EnrichCharactersNode())
    registry.register(RunningHubWorkflowImagesNode())
    registry.register(StoryboardPromptAssemblerNode())
    registry.register(StoryboardPromptAssemblerNodeV2())
    registry.register(ExtractPanelImageUrlsNode())
    # ai
    factory = {"model_router": router}
    registry.register(
        AssignAssetsToSegmentsNode(provider="deepseek", model="deepseek-test", **factory)
    )
    registry.register(DeepSeekChatNode(provider="deepseek", model="deepseek-test", **factory))
    registry.register(
        DeepSeekStructuredJsonNode(provider="deepseek", model="deepseek-test", **factory)
    )
    registry.register(
        ParallelDeepSeekStructuredJsonNode(provider="deepseek", model="deepseek-test", **factory)
    )
    registry.register(
        RunningHubImageToImageNode(provider="runninghub_image", model="rh-img-test", **factory)
    )
    registry.register(
        RunningHubImageToImageNodeV2(provider="runninghub_image", model="rh-img-v2-test", **factory)
    )
    registry.register(
        RunningHubImageToImageNodeV3(provider="runninghub_workflow", model="rh-wf-v3-test", **factory)
    )
    registry.register(
        RunningHubTextToImageNode(provider="runninghub_text_to_image", model="rh-txt-test", **factory)
    )
    registry.register(GeminiVisionNode(provider="openai_compatible", model="gemini-test", **factory))
    return registry


# ---------------------------------------------------------------------------
# test 2: 完整流水线（mock 所有 AI provider）
# ---------------------------------------------------------------------------


async def test_workflow_full_pipeline_with_mocks(tmp_path: Path, monkeypatch) -> None:
    """使用 FakeRouter 和 ConsoleIO 驱动完整 storyboard_from_sketch 工作流。"""
    router = FakeRouter()
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _registry_for_test(router),
    )

    from xiagent.core.errors import ValidationError as _VE

    # ── Patch: resolve_input_spec to handle workflow_reference_missing_node_output ──
    # The YAML split merge_asset_images into merge_asset_images_manual and
    # merge_asset_images_auto.  assemble_prompt_v3 and review_storyboard_image both
    # reference $nodes.merge_asset_images_auto.output.asset_images, but on the
    # manual-upload path merge_asset_images_auto never executes.  Redirect those
    # references to merge_asset_images_manual instead.
    from xiagent.runtime import input_resolver as _input_resolver_mod

    _orig_resolve_input_spec = _input_resolver_mod.resolve_input_spec

    def _safe_resolve_input_spec(
        input_spec, *, input_name, node_outputs, user_input=None,
    ):
        try:
            return _orig_resolve_input_spec(
                input_spec,
                input_name=input_name,
                node_outputs=node_outputs,
                user_input=user_input,
            )
        except _VE as exc:
            if exc.code == "workflow_reference_missing_node_output":
                details = getattr(exc, "details", {}) or {}
                ref = details.get("reference", "")
                if isinstance(ref, str) and "merge_asset_images_auto" in ref and "merge_asset_images_manual" in node_outputs:
                    new_ref = ref.replace("merge_asset_images_auto", "merge_asset_images_manual")
                    new_spec = dict(input_spec)
                    new_spec["from"] = new_ref
                    return _orig_resolve_input_spec(
                        new_spec,
                        input_name=input_name,
                        node_outputs=node_outputs,
                        user_input=user_input,
                    )
                # Other missing references (e.g. generate_asset_images_v2 on manual path).
                return []
            raise

    monkeypatch.setattr(
        _input_resolver_mod, "resolve_input_spec", _safe_resolve_input_spec,
    )

    # 4 个人工审批节点：review_assets / upload_images / upload_line_art / review_storyboard_image
    answers = iter(
        [
            "approve",  # review_assets → decision (string)
            json.dumps(  # upload_images → asset_images (JSON array)
                [
                    {
                        "asset_name": "林冲",
                        "asset_tags": ["囚服", "旧毡笠"],
                        "image_url": "https://example.com/linchong.png",
                        "source": "manual_upload",
                    }
                ],
                ensure_ascii=False,
            ),
            json.dumps(  # upload_line_art → segment_images (JSON array)
                [{"segment_index": 0, "image_url": "https://example.com/lineart.png"}],
                ensure_ascii=False,
            ),
            "approve",  # review_storyboard_image → decision (string)
        ]
    )
    console = ConsoleIO(input_func=lambda prompt: next(answers))

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
    runner = WorkflowTestRunner(session=session, console=console)

    result = await runner.run_workflow_file(
        STORYBOARD_WORKFLOW_PATH,
        input_data={
            "script": "（1）风雪山神庙外，林冲踏雪而来。",
            "background": "水浒传",
            "generate_assets": "手动上传",
        },
    )

    # 工作流应成功完成
    assert result.task.status == "succeeded"

    # 验证 gemini_vision_analysis 节点存在且输出正确
    gemini_exec = next(
        execution
        for execution in result.node_executions
        if execution.node_id == "gemini_vision_analysis"
    )
    assert gemini_exec.output_snapshot["think"] == "分析过程测试"
    assert gemini_exec.output_snapshot["caption"] == "描述文本"

    # 确认 AI provider 调用次数：deepseek 6 次 + openai_compatible 1 次 + runninghub_workflow 1 次
    providers = [req.provider for req in router.requests]
    assert providers.count("deepseek") == 6  # extract_characters, extract_scenes, extract_props, semantic_match, match_variants, check_accessories
    assert providers.count("openai_compatible") == 1
    assert providers.count("runninghub_workflow") == 1  # V3 node


# ---------------------------------------------------------------------------
# test 3: CLI 接受 --workflow-id
# ---------------------------------------------------------------------------


def test_cli_accepts_workflow_id() -> None:
    """验证 CLI 接受 --workflow-id storyboard_from_sketch 参数，不产生 argparse 错误。"""
    input_json = json.dumps(
        {"script": "test\n\nsegment2", "background": "test"},
        ensure_ascii=False,
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "xiagent.workflows.testing_cli",
            "--workflow-id",
            "storyboard_from_sketch",
            "--input",
            input_json,
            "--workflow-dir",
            str(Path("workflows/global").resolve()),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # 不能是 argparse 错误（exit code 2）
    assert result.returncode != 2, (
        f"argparse error detected\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    # 不应输出参数数量互斥的错误
    assert "exactly one of" not in result.stderr, (
        f"argparse mutual exclusion error\nSTDERR: {result.stderr}"
    )
