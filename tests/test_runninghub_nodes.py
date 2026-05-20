from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.models import ChatModelRouter


def _node_classes() -> tuple[type, type]:
    try:
        from xiagent.nodes.ai.runninghub_image import (
            RunningHubImageToImageNode,
            RunningHubTextToImageNode,
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"RunningHub image nodes module is missing: {exc}")
    return RunningHubImageToImageNode, RunningHubTextToImageNode


class FakeRouter(ChatModelRouter):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []

    async def chat(self, request: Any) -> Any:
        from xiagent.models import ChatResponse

        self.requests.append(request)
        return ChatResponse(
            text="https://cdn.runninghub.test/output.png",
            model=request.model,
            usage={"credits": 1},
            metadata={
                "provider": request.provider,
                "task_id": "task_123",
                "status": "SUCCESS",
                "results": [{"url": "https://cdn.runninghub.test/output.png"}],
            },
        )


class FailingRouter(ChatModelRouter):
    def __init__(self) -> None:
        super().__init__()

    async def chat(self, request: Any) -> Any:
        raise ExternalServiceError(
            code="runninghub_image_request_failed",
            message="RunningHub image request failed",
            details={"provider": request.provider},
        )


def test_runninghub_node_constructors_require_router_keyword_arguments() -> None:
    RunningHubImageToImageNode, RunningHubTextToImageNode = _node_classes()

    for node_cls in (RunningHubImageToImageNode, RunningHubTextToImageNode):
        signature = inspect.signature(node_cls)

        assert signature.parameters["model_router"].kind is inspect.Parameter.KEYWORD_ONLY
        assert signature.parameters["provider"].kind is inspect.Parameter.KEYWORD_ONLY
        assert signature.parameters["model"].kind is inspect.Parameter.KEYWORD_ONLY
        assert "api_key" not in signature.parameters
        assert "base_url" not in signature.parameters
        with pytest.raises(TypeError):
            node_cls(FakeRouter(), "runninghub_image", "runninghub-test-model")  # type: ignore[misc]


def test_runninghub_nodes_reject_invalid_router() -> None:
    RunningHubImageToImageNode, RunningHubTextToImageNode = _node_classes()

    for node_cls in (RunningHubImageToImageNode, RunningHubTextToImageNode):
        with pytest.raises(TypeError):
            node_cls(
                model_router=object(),  # type: ignore[arg-type]
                provider="runninghub_image",
                model="runninghub-test-model",
            )


async def test_image_to_image_node_converts_inputs_to_chat_request_and_calls_router() -> None:
    from xiagent.models import ChatRequest

    RunningHubImageToImageNode, _ = _node_classes()
    router = FakeRouter()
    node = RunningHubImageToImageNode(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "Transform this sketch into Ming Dynasty ink-wash Wuxia.",
            "image_urls": ["https://runninghub.test/input.png"],
            "aspect_ratio": "9:16",
            "resolution": "1k",
        },
    )

    assert len(router.requests) == 1
    request = router.requests[0]
    assert isinstance(request, ChatRequest)
    assert request.provider == "runninghub_image"
    assert request.model == "runninghub-image-model"
    assert [(message.role, message.content) for message in request.messages] == [
        ("user", "Transform this sketch into Ming Dynasty ink-wash Wuxia.")
    ]
    assert request.metadata == {
        "image_urls": ["https://runninghub.test/input.png"],
        "aspect_ratio": "9:16",
        "resolution": "1k",
    }
    assert result.status == "succeeded"
    assert result.output == {
        "image_url": "https://cdn.runninghub.test/output.png",
        "model": "runninghub-image-model",
        "usage": {"credits": 1},
        "results": [{"url": "https://cdn.runninghub.test/output.png"}],
        "task_id": "task_123",
        "status": "SUCCESS",
    }
    assert result.metadata["provider"] == "runninghub_image"


async def test_image_to_image_node_accepts_single_image_url_alias() -> None:
    RunningHubImageToImageNode, _ = _node_classes()
    router = FakeRouter()
    node = RunningHubImageToImageNode(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    await node.run(
        ctx=None,
        inputs={
            "prompt": "colorize",
            "image_url": "https://runninghub.test/input.png",
        },
    )

    assert router.requests[0].metadata["image_urls"] == ["https://runninghub.test/input.png"]


async def test_text_to_image_node_converts_inputs_to_chat_request_and_calls_router() -> None:
    from xiagent.models import ChatRequest

    _, RunningHubTextToImageNode = _node_classes()
    router = FakeRouter()
    node = RunningHubTextToImageNode(
        model_router=router,
        provider="runninghub_text_to_image",
        model="runninghub-text-model",
    )

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "A dramatic fantasy landscape.",
            "aspect_ratio": "9:16",
            "resolution": "1k",
        },
    )

    assert len(router.requests) == 1
    request = router.requests[0]
    assert isinstance(request, ChatRequest)
    assert request.provider == "runninghub_text_to_image"
    assert request.model == "runninghub-text-model"
    assert [(message.role, message.content) for message in request.messages] == [
        ("user", "A dramatic fantasy landscape.")
    ]
    assert request.metadata == {
        "aspect_ratio": "9:16",
        "resolution": "1k",
    }
    assert result.output["image_url"] == "https://cdn.runninghub.test/output.png"
    assert result.output["results"] == [{"url": "https://cdn.runninghub.test/output.png"}]


@pytest.mark.parametrize("node_name", ["image_to_image", "text_to_image"])
async def test_runninghub_nodes_require_non_empty_prompt(node_name: str) -> None:
    RunningHubImageToImageNode, RunningHubTextToImageNode = _node_classes()
    node_cls = (
        RunningHubImageToImageNode
        if node_name == "image_to_image"
        else RunningHubTextToImageNode
    )
    router = FakeRouter()
    node = node_cls(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-test-model",
    )

    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": " "})

    assert exc.value.code == "runninghub_prompt_required"
    assert router.requests == []


async def test_image_to_image_node_requires_image_urls() -> None:
    RunningHubImageToImageNode, _ = _node_classes()
    router = FakeRouter()
    node = RunningHubImageToImageNode(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": "colorize"})

    assert exc.value.code == "runninghub_image_urls_required"
    assert router.requests == []


async def test_runninghub_node_propagates_router_errors() -> None:
    RunningHubImageToImageNode, _ = _node_classes()
    node = RunningHubImageToImageNode(
        model_router=FailingRouter(),
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    with pytest.raises(ExternalServiceError) as exc:
        await node.run(
            ctx=None,
            inputs={
                "prompt": "colorize",
                "image_url": "https://runninghub.test/input.png",
            },
        )

    assert exc.value.code == "runninghub_image_request_failed"
    assert exc.value.details == {"provider": "runninghub_image"}


def test_runninghub_descriptors_expose_stable_workflow_contracts() -> None:
    RunningHubImageToImageNode, RunningHubTextToImageNode = _node_classes()

    image_node = RunningHubImageToImageNode(
        model_router=FakeRouter(),
        provider="runninghub_image",
        model="runninghub-image-model",
    )
    text_node = RunningHubTextToImageNode(
        model_router=FakeRouter(),
        provider="runninghub_text_to_image",
        model="runninghub-text-model",
    )

    image_descriptor = image_node.describe()
    text_descriptor = text_node.describe()

    assert image_descriptor.ref == "ai.runninghub_image_to_image.v1"
    assert text_descriptor.ref == "ai.runninghub_text_to_image.v1"
    assert image_descriptor.input_schema["required"] == ["prompt", "image_urls"]
    assert text_descriptor.input_schema["required"] == ["prompt"]
    assert image_descriptor.output_schema["required"] == [
        "image_url",
        "model",
        "usage",
        "results",
    ]
    assert text_descriptor.output_schema["required"] == [
        "image_url",
        "model",
        "usage",
        "results",
    ]


def test_runninghub_node_source_does_not_import_provider_or_http_client() -> None:
    source = Path("xiagent/nodes/ai/runninghub_image.py").read_text(encoding="utf-8")

    assert "urlopen" not in source
    assert "RunningHubImageProvider" not in source
    assert "RunningHubTextToImageProvider" not in source
