from __future__ import annotations

from pathlib import Path
from typing import Any

from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes.ai.runninghub_image import (
    RunningHubImageToImageNode,
    RunningHubTextToImageNode,
)
from xiagent.nodes.registry import NodeRegistry
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
    assert result.node_executions[0].node_id == "generate_image"
    assert result.node_executions[0].output_snapshot["image_url"] == (
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
            "image_urls": [
                "https://www.runninghub.cn/view?filename=174ba2c54b8af1fdd5a01370049dd6407a693d8b05b4717079698e87680e038e.png"
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
    assert result.node_executions[0].node_id == "transform_image"
    assert result.node_executions[0].output_snapshot["results"] == [
        {"url": "https://cdn.runninghub.test/generated.png"}
    ]
    assert router.requests[0].provider == "runninghub_image"
    assert router.requests[0].metadata == {
        "image_urls": [
            "https://www.runninghub.cn/view?filename=174ba2c54b8af1fdd5a01370049dd6407a693d8b05b4717079698e87680e038e.png"
        ],
        "aspect_ratio": "9:16",
        "resolution": "1k",
    }


def _patch_runninghub_registry(monkeypatch, router: FakeRunningHubRouter) -> None:
    def build_test_registry(settings: Any) -> NodeRegistry:
        registry = NodeRegistry()
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
