from __future__ import annotations

from pathlib import Path
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes.ai.runninghub_image import (
    RunningHubImageToImageNode,
    RunningHubImageToImageNodeV3,
    RunningHubTextToImageNode,
)
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.user_input import SystemUserInputNode
from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.console import ConsoleIO
from xiagent.workflows.testing.runner import WorkflowTestRunner


class FakeRunningHubRouter(ChatModelRouter):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            text="https://cdn.runninghub.test/generated.png",
            model=request.model,
            usage={"credits": 1},
            metadata={
                "provider": request.provider,
                "task_id": "runninghub-task-001",
                "status": "SUCCESS",
                "results": [{"url": "https://cdn.runninghub.test/generated.png"}],
            },
        )


async def test_runninghub_text_to_image_workflow_runs_with_user_level_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    router = FakeRunningHubRouter()
    _patch_runninghub_registry(monkeypatch, router)
    session = await _session(tmp_path)
    runner = WorkflowTestRunner(session=session, console=ConsoleIO())

    result = await runner.run_workflow_file(
        Path("workflows/global/runninghub_text_to_image_test.workflow.yaml"),
        input_data={
            "prompt": (
                "A group of monkeys frantically competing for a tiny banana in a dense, "
                "sun-dappled tropical forest. The banana is comically small compared to "
                "the monkeys, who are leaping, grabbing, and reaching with exaggerated "
                "expressions of urgency and desire. Lush green foliage, dynamic poses, "
                "chaotic yet playful atmosphere, natural lighting, vibrant colors."
            ),
            "aspect_ratio": "9:16",
            "resolution": "1k",
        },
    )

    assert result.task.status == "succeeded"
    executions = {execution.node_id: execution for execution in result.node_executions}
    assert executions["generate_image"].output_snapshot["image_url"] == (
        "https://cdn.runninghub.test/generated.png"
    )
    assert router.requests[0].provider == "runninghub_text_to_image"
    assert router.requests[0].metadata == {
        "aspect_ratio": "9:16",
        "resolution": "1k",
    }


async def test_runninghub_image_to_image_workflow_runs_with_user_level_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    router = FakeRunningHubRouter()
    _patch_runninghub_registry(monkeypatch, router)
    session = await _session(tmp_path)
    runner = WorkflowTestRunner(session=session, console=ConsoleIO())

    result = await runner.run_workflow_file(
        Path("workflows/global/runninghub_image_to_image_test.workflow.yaml"),
        input_data={
            "image_refs": [
                {"kind": "data_uri", "data": "data:image/png;base64,aW1hZ2UtYnl0ZXM="}
            ],
            "prompt": (
                "Transform this sketch into a detailed, full-color illustration in the "
                "style of Ming Dynasty ink-wash Wuxia. Strictly retain man's pose and "
                "the shape of the black crow, but replace the background with a snowy "
                "bamboo forest. Enhance the ink-wash bleeding textures and apply a cool "
                "color palette to create a solemn atmosphere."
            ),
            "aspect_ratio": "9:16",
            "resolution": "1k",
        },
    )

    assert result.task.status == "succeeded"
    executions = {execution.node_id: execution for execution in result.node_executions}
    assert executions["transform_image"].output_snapshot["results"] == [
        {"url": "https://cdn.runninghub.test/generated.png"}
    ]
    assert router.requests[0].provider == "runninghub_image"
    assert router.requests[0].metadata == {
        "images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="],
        "aspect_ratio": "9:16",
        "resolution": "1k",
    }


def _patch_runninghub_registry(monkeypatch, router: FakeRunningHubRouter) -> None:
    def build_test_registry(settings: Any) -> NodeRegistry:
        registry = NodeRegistry()
        registry.register(SystemUserInputNode())
        registry.register(
            RunningHubTextToImageNode(
                model_router=router,
                provider="runninghub_text_to_image",
                model="runninghub-text-test-model",
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

    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        build_test_registry,
    )


async def _session(tmp_path: Path):
    workflow_dir = tmp_path / "empty-workflows"
    workflow_dir.mkdir()
    return await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )


def test_runninghub_workflow_image_parameters_expose_fixed_options() -> None:
    from xiagent.workflows.loader import load_workflow_file

    expected_aspect_ratios = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"]
    expected_resolutions = ["1k", "2k", "4k"]
    workflow_paths = [
        Path("workflows/global/runninghub_text_to_image_test.workflow.yaml"),
        Path("workflows/global/runninghub_image_to_image_test.workflow.yaml"),
    ]

    for workflow_path in workflow_paths:
        contract = load_workflow_file(workflow_path)
        first_node = contract["nodes"][0]
        properties = {
            name: input_spec["schema"]
            for name, input_spec in first_node["inputs"].items()
            if input_spec.get("from_user") is True
        }
        assert properties["aspect_ratio"]["enum"] == expected_aspect_ratios
        assert properties["resolution"]["enum"] == expected_resolutions
        assert properties["aspect_ratio"]["description"]
        assert properties["resolution"]["description"]


# ── V3 Node Tests ──────────────────────────────────────────────


def test_v3_node_describe_has_correct_ref() -> None:
    node = RunningHubImageToImageNodeV3(
        model_router=FakeRunningHubRouter(),
        provider="runninghub_workflow",
        model="runninghub-workflow-test-model",
    )
    descriptor = node.describe()
    assert descriptor.ref == "ai.runninghub_image_to_image.v3"


async def test_v3_node_rejects_missing_prompt() -> None:
    router = FakeRunningHubRouter()
    node = RunningHubImageToImageNodeV3(
        model_router=router,
        provider="runninghub_workflow",
        model="runninghub-workflow-test-model",
    )
    try:
        await node.run(None, {"prompt": ""})
        raise AssertionError("Expected ValidationError")
    except ValidationError as exc:
        assert exc.code == "runninghub_v3_prompt_required"


async def test_v3_node_rejects_missing_image_urls() -> None:
    router = FakeRunningHubRouter()
    node = RunningHubImageToImageNodeV3(
        model_router=router,
        provider="runninghub_workflow",
        model="runninghub-workflow-test-model",
    )
    try:
        await node.run(None, {"prompt": "a valid prompt", "image_urls": []})
        raise AssertionError("Expected ValidationError")
    except ValidationError as exc:
        assert exc.code == "runninghub_v3_image_urls_required"


async def test_v3_node_rejects_missing_node_mapping() -> None:
    router = FakeRunningHubRouter()
    node = RunningHubImageToImageNodeV3(
        model_router=router,
        provider="runninghub_workflow",
        model="runninghub-workflow-test-model",
    )
    try:
        await node.run(
            None,
            {
                "prompt": "a valid prompt",
                "image_urls": ["https://example.com/image1.png"],
            },
        )
        raise AssertionError("Expected ValidationError")
    except ValidationError as exc:
        assert exc.code == "runninghub_v3_node_mapping_required"


async def test_v3_node_calls_workflow_provider() -> None:
    router = FakeRunningHubRouter()
    node = RunningHubImageToImageNodeV3(
        model_router=router,
        provider="runninghub_workflow",
        model="runninghub-workflow-test-model",
    )
    result = await node.run(
        None,
        {
            "prompt": "generate an image with line art",
            "image_urls": ["https://example.com/lineart.png", "https://example.com/image1.png"],
            "node_mapping": {
                "images": ["81", "141", "139", "140", "176", "182"],
                "text": {"nodeId": "150", "fieldName": "text"},
                "select": {"nodeIds": ["190", "191"], "fieldName": "select"},
            },
        },
    )
    assert result.status == "succeeded"
    assert result.output["image_url"] == "https://cdn.runninghub.test/generated.png"
    assert router.requests[0].provider == "runninghub_workflow"


# ── Regression Tests ────────────────────────────────────────────────


async def test_v1_node_still_works() -> None:
    """Verify V1 RunningHubImageToImageNode still functions with provider='runninghub_image'."""
    router = FakeRunningHubRouter()
    node = RunningHubImageToImageNode(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    result = await node.run(
        None,
        {
            "prompt": "Transform this sketch into Ming Dynasty ink-wash Wuxia.",
            "image_refs": [{"kind": "data_uri", "data": "data:image/png;base64,aW1hZ2UtYnl0ZXM="}],
            "aspect_ratio": "9:16",
            "resolution": "1k",
        },
    )

    assert result.status == "succeeded"
    assert result.output["image_url"] == "https://cdn.runninghub.test/generated.png"
    assert result.output["model"] == "runninghub-image-model"
    assert result.output["results"] == [
        {"url": "https://cdn.runninghub.test/generated.png"}
    ]
    assert router.requests[0].provider == "runninghub_image"
    # V1 input/output schema unchanged
    assert router.requests[0].metadata == {
        "images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="],
        "aspect_ratio": "9:16",
        "resolution": "1k",
    }


def test_existing_workflows_still_load(test_settings) -> None:
    """Validate asset_storyboard_generation workflow contracts — V1/V2 refs still recognized."""
    from xiagent.nodes import build_node_registry
    from xiagent.workflows.loader import load_workflow_file
    from xiagent.workflows.validator import validate_workflow_contract

    contract = load_workflow_file(
        Path("workflows/global/asset_storyboard_generation.workflow.yaml")
    )
    registry = build_node_registry(test_settings)

    # Must not raise — all V1/V2 refs recognized
    validate_workflow_contract(contract, registry)

    # Spot-check: V1 and V2 refs are present
    node_refs = {n["ref"] for n in contract["nodes"]}
    assert "ai.runninghub_image_to_image.v1" in node_refs
    assert "ai.runninghub_image_to_image.v2" in node_refs


def test_storyboard_from_sketch_uses_v3(test_settings) -> None:
    """Verify storyboard_from_sketch.workflow.yaml uses V3 node with explicit node_mapping."""
    from xiagent.nodes import build_node_registry
    from xiagent.workflows.loader import load_workflow_file
    from xiagent.workflows.validator import validate_workflow_contract

    contract = load_workflow_file(
        Path("workflows/global/storyboard_from_sketch.workflow.yaml")
    )
    registry = build_node_registry(test_settings)

    # Full contract validation must pass
    validate_workflow_contract(contract, registry)

    # Locate generate_storyboard_image node
    gen_node = next(
        n for n in contract["nodes"] if n["id"] == "generate_storyboard_image"
    )
    assert gen_node["ref"] == "ai.runninghub_image_to_image.v3"
    assert gen_node["inputs"]["image_urls"]["from"] == "$nodes.prepare_runninghub_images.output.image_urls"
    assert "node_mapping" in gen_node["inputs"]
