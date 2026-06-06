from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
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


class ProviderShapeRouter(ChatModelRouter):
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
                "task_id": "task_456",
                "status": "SUCCESS",
                "results": [
                    {
                        "url": "https://cdn.runninghub.test/output.png",
                        "outputType": "png",
                        "providerOnly": "not-public-contract",
                    },
                    {
                        "text": "fallback text",
                        "outputType": "text",
                        "providerOnly": "not-public-contract",
                    },
                ],
            },
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
            "image_refs": [{"kind": "data_uri", "data": "data:image/png;base64,aW1hZ2UtYnl0ZXM="}],
            "aspect_ratio": "9:16",
            "resolution": "1k",
            "poll_interval_seconds": 0,
            "poll_timeout_seconds": 600,
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
        "images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="],
        "aspect_ratio": "9:16",
        "resolution": "1k",
        "poll_interval_seconds": 0,
        "poll_timeout_seconds": 600,
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


async def test_image_to_image_node_resolves_image_refs() -> None:
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
            "image_refs": [{"kind": "data_uri", "data": "data:image/png;base64,aW1hZ2UtYnl0ZXM="}],
        },
    )

    assert router.requests[0].metadata["images"] == ["data:image/png;base64,aW1hZ2UtYnl0ZXM="]


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


async def test_image_to_image_v2_wraps_prompt_with_fixed_prefix_and_suffix() -> None:
    from xiagent.nodes.ai.runninghub_image import RunningHubImageToImageNodeV2

    router = FakeRouter()
    node = RunningHubImageToImageNodeV2(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    result = await node.run(
        ctx=None,
        inputs={
            "prompt_results": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "prompt": "深灰粗布囚服，旧毡笠，面部轮廓清晰，保留八十万禁军教头的挺拔体态。",
                    "reference_image_ref": {"kind": "data_uri", "data": "data:image/png;base64,aW1hZ2UtYnl0ZXM="},
                }
            ],
            "prompt_prefix": "将图中角色改成",
            "prompt_suffix": "保持风格和其它特征不变。。",
        },
    )

    assert result.output["asset_images"][0]["asset_name"] == "林冲"
    assert result.output["asset_images"][0]["asset_tags"] == ["囚服"]
    assert router.requests[0].messages[0].content == (
        "将图中角色改成深灰粗布囚服，旧毡笠，面部轮廓清晰，保留八十万禁军教头的挺拔体态，保持风格和其它特征不变"
    )


async def test_image_to_image_v2_converts_asset_reference_to_base64_image() -> None:
    from xiagent.nodes.ai.runninghub_image import RunningHubImageToImageNodeV2
    from xiagent.nodes.base import NodeContext

    class FakeAssetService:
        async def search_assets(self, **_: Any) -> Any:
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        asset_id="asset-ref",
                        project_id=None,
                        storage_uri="aa/bb/reference.png",
                        metadata={
                            "public_url": "https://assets.local.invalid/aa/bb/reference.png"
                        },
                    )
                ],
                total=1,
            )

        async def get_asset(self, **_: Any) -> Any:
            return SimpleNamespace(
                asset_id="asset-ref",
                project_id=None,
                storage_uri="aa/bb/reference.png",
                metadata={"public_url": "https://assets.local.invalid/aa/bb/reference.png"},
            )

        async def get_asset_content(self, **_: Any) -> Any:
            return SimpleNamespace(
                bytes_content=b"image-bytes",
                content_type="image/png",
            )

    router = FakeRouter()
    node = RunningHubImageToImageNodeV2(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    await node.run(
        ctx=NodeContext(
            user_id="user-1",
            project_id="global",
            task_id="task-1",
            node_id="generate_images",
            node_execution_id="exec-1",
            config={},
            output_schema=node.describe().output_schema,
            asset_service=FakeAssetService(),  # type: ignore[arg-type]
            event_sink=None,
            logger=None,
        ),
        inputs={
            "prompt_results": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "prompt": "深灰粗布囚服。",
                    "reference_image_ref": {"kind": "asset", "asset_id": "asset-ref"},
                }
            ],
        },
    )

    request_metadata = router.requests[0].metadata
    assert request_metadata["images"] == ["data:image/png;base64,aW1hZ2UtYnl0ZXM="]
    assert "image_urls" not in request_metadata
    assert request_metadata["reference_image_ref"] == {"kind": "asset", "asset_id": "asset-ref"}


async def test_image_to_image_v2_rejects_unresolved_reference_url() -> None:
    from xiagent.nodes.ai.runninghub_image import RunningHubImageToImageNodeV2

    router = FakeRouter()
    node = RunningHubImageToImageNodeV2(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    with pytest.raises(ValidationError) as exc:
        await node.run(
            ctx=None,
            inputs={
                "prompt_results": [
                    {
                        "asset_type": "character",
                        "asset_name": "林冲",
                        "asset_tags": ["囚服"],
                        "prompt": "深灰粗布囚服。",
                        "reference_image_ref": "https://runninghub.test/linchong.png",
                    }
                ],
            },
        )

    assert exc.value.code == "image_ref_invalid"
    assert router.requests == []


async def test_runninghub_node_standardizes_provider_results_in_public_output() -> None:
    RunningHubImageToImageNode, _ = _node_classes()
    node = RunningHubImageToImageNode(
        model_router=ProviderShapeRouter(),
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "colorize",
            "image_refs": [{"kind": "data_uri", "data": "data:image/png;base64,aW1hZ2UtYnl0ZXM="}],
        },
    )

    assert result.output["results"] == [
        {
            "url": "https://cdn.runninghub.test/output.png",
            "output_type": "png",
        },
        {
            "text": "fallback text",
            "output_type": "text",
        },
    ]


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


async def test_image_to_image_node_requires_image_refs() -> None:
    RunningHubImageToImageNode, _ = _node_classes()
    router = FakeRouter()
    node = RunningHubImageToImageNode(
        model_router=router,
        provider="runninghub_image",
        model="runninghub-image-model",
    )

    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": "colorize"})

    assert exc.value.code == "image_refs_required"
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
                "image_refs": [{"kind": "data_uri", "data": "data:image/png;base64,aW1hZ2UtYnl0ZXM="}],
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
    assert image_descriptor.input_schema["required"] == ["prompt", "image_refs"]
    assert text_descriptor.input_schema["required"] == ["prompt"]
    assert image_descriptor.input_schema["properties"]["poll_timeout_seconds"] == {
        "type": "number",
        "minimum": 0,
    }
    assert text_descriptor.input_schema["properties"]["poll_timeout_seconds"] == {
        "type": "number",
        "minimum": 0,
    }
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
    assert image_descriptor.output_schema["properties"]["image_url"] == {
        "type": "string",
        "minLength": 1,
    }
    assert text_descriptor.output_schema["properties"]["image_url"] == {
        "type": "string",
        "minLength": 1,
    }
    assert image_descriptor.output_schema["properties"]["results"] == {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "minLength": 1},
                "text": {"type": "string", "minLength": 1},
                "output_type": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
    }
    assert text_descriptor.output_schema["properties"]["results"] == (
        image_descriptor.output_schema["properties"]["results"]
    )


def test_runninghub_node_source_does_not_import_provider_or_http_client() -> None:
    source = Path("xiagent/nodes/ai/runninghub_image.py").read_text(encoding="utf-8")

    assert "urlopen" not in source
    assert "RunningHubImageProvider" not in source
    assert "RunningHubTextToImageProvider" not in source
