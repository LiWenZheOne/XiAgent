from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest, ChatResponse
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "image_url": {"type": "string", "minLength": 1},
        "model": {"type": "string"},
        "usage": {"type": "object"},
        "results": {
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
        },
        "task_id": {"type": "string"},
        "status": {"type": "string"},
    },
    "required": ["image_url", "model", "usage", "results"],
    "additionalProperties": False,
}


class _RunningHubImageNodeBase(BaseNode):
    _ref: str
    _name: str
    _description: str
    _input_schema: dict[str, Any]

    def __init__(
        self,
        *,
        model_router: ChatModelRouter,
        provider: str,
        model: str,
    ) -> None:
        if not isinstance(model_router, ChatModelRouter):
            raise TypeError("model_router must be ChatModelRouter")
        self._model_router = model_router
        self._provider = provider
        self._model = model

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref=self._ref,
            name=self._name,
            version="1.0.0",
            kind="ai",
            input_schema=self._input_schema,
            output_schema=_OUTPUT_SCHEMA,
            description=self._description,
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        prompt = _required_text(inputs, "prompt", "runninghub_prompt_required")
        metadata = self._metadata(inputs)
        response = await self._model_router.chat(
            ChatRequest(
                provider=self._provider,
                model=self._model,
                messages=[ChatMessage(role="user", content=prompt)],
                metadata=metadata,
            )
        )
        return NodeResult(
            status="succeeded",
            output=_response_output(response),
            metadata=response.metadata,
        )

    def _metadata(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        aspect_ratio = _optional_text(inputs, "aspect_ratio") or _optional_text(
            inputs, "aspectRatio"
        )
        if aspect_ratio is not None:
            metadata["aspect_ratio"] = aspect_ratio
        resolution = _optional_text(inputs, "resolution")
        if resolution is not None:
            metadata["resolution"] = resolution
        poll_interval_seconds = _optional_number(inputs, "poll_interval_seconds")
        if poll_interval_seconds is not None:
            metadata["poll_interval_seconds"] = poll_interval_seconds
        poll_timeout_seconds = _optional_number(inputs, "poll_timeout_seconds")
        if poll_timeout_seconds is not None:
            metadata["poll_timeout_seconds"] = poll_timeout_seconds
        return metadata


class RunningHubImageToImageNode(_RunningHubImageNodeBase):
    _ref = "ai.runninghub_image_to_image.v1"
    _name = "RunningHub Image To Image"
    _description = "Call RunningHub image-to-image API through the model router."
    _input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "image_urls": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
            },
            "image_url": {"type": "string", "minLength": 1},
            "aspect_ratio": {"type": "string", "minLength": 1},
            "aspectRatio": {"type": "string", "minLength": 1},
            "resolution": {"type": "string", "minLength": 1},
            "poll_interval_seconds": {"type": "number", "minimum": 0},
            "poll_timeout_seconds": {"type": "number", "minimum": 0},
        },
        "required": ["prompt", "image_urls"],
        "additionalProperties": False,
    }

    def _metadata(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        metadata = super()._metadata(inputs)
        metadata["image_urls"] = _image_urls(inputs)
        return metadata


class RunningHubTextToImageNode(_RunningHubImageNodeBase):
    _ref = "ai.runninghub_text_to_image.v1"
    _name = "RunningHub Text To Image"
    _description = "Call RunningHub text-to-image API through the model router."
    _input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "aspect_ratio": {"type": "string", "minLength": 1},
            "aspectRatio": {"type": "string", "minLength": 1},
            "resolution": {"type": "string", "minLength": 1},
            "poll_interval_seconds": {"type": "number", "minimum": 0},
            "poll_timeout_seconds": {"type": "number", "minimum": 0},
        },
        "required": ["prompt"],
        "additionalProperties": False,
    }


def _required_text(inputs: Mapping[str, Any], key: str, code: str) -> str:
    value = inputs.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            code=code,
            message=f"RunningHub {key} cannot be empty",
        )
    return value


def _optional_text(inputs: Mapping[str, Any], key: str) -> str | None:
    value = inputs.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _optional_number(inputs: Mapping[str, Any], key: str) -> int | float | None:
    value = inputs.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int | float) else None


def _image_urls(inputs: Mapping[str, Any]) -> list[str]:
    value = inputs.get("image_urls", inputs.get("imageUrls"))
    if isinstance(value, str) and value.strip():
        return [value]
    if isinstance(value, list):
        image_urls = [item for item in value if isinstance(item, str) and item.strip()]
        if image_urls:
            return image_urls
    image_url = _optional_text(inputs, "image_url")
    if image_url is not None:
        return [image_url]
    raise ValidationError(
        code="runninghub_image_urls_required",
        message="RunningHub image-to-image requires at least one image URL",
    )


def _response_output(response: ChatResponse) -> dict[str, Any]:
    metadata = response.metadata
    results = metadata.get("results")
    output: dict[str, Any] = {
        "image_url": response.text,
        "model": response.model,
        "usage": response.usage,
        "results": _public_results(results),
    }
    task_id = metadata.get("task_id")
    if isinstance(task_id, str):
        output["task_id"] = task_id
    status = metadata.get("status")
    if isinstance(status, str):
        output["status"] = status
    return output


def _public_results(results: Any) -> list[dict[str, str]]:
    if not isinstance(results, list):
        return []
    public_results: list[dict[str, str]] = []
    for result in results:
        if not isinstance(result, Mapping):
            continue
        public_result: dict[str, str] = {}
        url = _mapping_text(result, "url")
        if url is not None:
            public_result["url"] = url
        text = _mapping_text(result, "text")
        if text is not None:
            public_result["text"] = text
        output_type = _mapping_text(result, "output_type") or _mapping_text(result, "outputType")
        if output_type is not None:
            public_result["output_type"] = output_type
        if public_result:
            public_results.append(public_result)
    return public_results


def _mapping_text(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    return item.strip() if isinstance(item, str) and item.strip() else None
