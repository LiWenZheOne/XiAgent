from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.ai import ImageGenerationCapability
from xiagent.core.errors import ValidationError
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes.ai.image_references import (
    image_ref_schema,
    image_refs_schema,
    resolve_image_ref,
    resolve_image_refs,
)
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

_ASSET_IMAGES_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["asset_images"],
    "properties": {
        "asset_images": {"type": "array"},
    },
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
        image_refs = metadata.pop("image_refs", None)
        capability = ImageGenerationCapability(
            model_router=self._model_router,
            provider=self._provider,
            model=self._model,
        )
        if image_refs is None:
            result = await capability.generate_text_to_image(prompt=prompt, **metadata)
        else:
            result = await capability.generate_image_to_image(
                prompt=prompt,
                image_refs=image_refs,
                image_ref_resolver=_ctx_image_ref_resolver(ctx),
                **metadata,
            )
        return NodeResult(
            status="succeeded",
            output=result.output,
            metadata=result.metadata,
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
        temperature = _optional_number(inputs, "temperature")
        if temperature is not None:
            metadata["temperature"] = temperature
        return metadata


class RunningHubImageToImageNode(_RunningHubImageNodeBase):
    _ref = "ai.runninghub_image_to_image.v1"
    _name = "RunningHub Image To Image"
    _description = "Call RunningHub image-to-image API through the model router."
    _input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "image_refs": image_refs_schema(),
            "aspect_ratio": {"type": "string", "minLength": 1},
            "aspectRatio": {"type": "string", "minLength": 1},
            "resolution": {"type": "string", "minLength": 1},
            "temperature": {"type": "number", "minimum": 0},
            "poll_interval_seconds": {"type": "number", "minimum": 0},
            "poll_timeout_seconds": {"type": "number", "minimum": 0},
        },
        "required": ["prompt", "image_refs"],
        "additionalProperties": False,
    }

    def _metadata(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        metadata = super()._metadata(inputs)
        metadata["image_refs"] = _image_refs(inputs)
        return metadata


class RunningHubImageToImageNodeV2(BaseNode):
    _ref = "ai.runninghub_image_to_image.v2"
    _name = "RunningHub Image To Image V2"
    _description = "Batch image-to-image generation: one RunningHub call per character from prompt_results array."
    _input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "asset_type": {"type": "string", "minLength": 1},
                        "asset_name": {"type": "string", "minLength": 1},
                        "asset_tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "prompt": {"type": "string", "minLength": 1},
                        "reference_image_ref": image_ref_schema(),
                    },
                    "required": ["asset_type", "asset_name", "prompt", "reference_image_ref"],
                    "additionalProperties": True,
                },
                "minItems": 1,
            },
            "aspect_ratio": {"type": "string", "minLength": 1},
            "aspectRatio": {"type": "string", "minLength": 1},
            "prompt_prefix": {"type": "string"},
            "prompt_suffix": {"type": "string"},
            "resolution": {"type": "string", "minLength": 1},
            "poll_interval_seconds": {"type": "number", "minimum": 0},
            "poll_timeout_seconds": {"type": "number", "minimum": 0},
        },
        "required": ["prompt_results"],
        "additionalProperties": False,
    }

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
            output_schema=_ASSET_IMAGES_OUTPUT_SCHEMA,
            description=self._description,
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        result = await ImageGenerationCapability(
            model_router=self._model_router,
            provider=self._provider,
            model=self._model,
        ).generate_asset_images(
            prompt_results=inputs.get("prompt_results"),
            image_ref_resolver=_ctx_image_ref_resolver(ctx),
            prompt_prefix=inputs.get("prompt_prefix"),
            prompt_suffix=inputs.get("prompt_suffix"),
            aspect_ratio=inputs.get("aspect_ratio") or inputs.get("aspectRatio"),
            resolution=inputs.get("resolution"),
            poll_interval_seconds=inputs.get("poll_interval_seconds"),
            poll_timeout_seconds=inputs.get("poll_timeout_seconds"),
        )
        return NodeResult(
            status="succeeded",
            output=result.output,
            metadata=result.metadata,
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


def _image_to_image_prompt(prompt: str, inputs: Mapping[str, Any]) -> str:
    prefix = _optional_text(inputs, "prompt_prefix") or ""
    suffix = _optional_text(inputs, "prompt_suffix") or ""
    body = f"{prefix.strip()}{prompt.strip()}" if prefix else prompt.strip()
    body = _strip_trailing_prompt_punctuation(body)
    suffix = _strip_trailing_prompt_punctuation(suffix)
    return f"{body}，{suffix}" if suffix else body


def _strip_trailing_prompt_punctuation(value: str) -> str:
    return value.strip().rstrip("。．.，,、；;：:")


async def _metadata_with_resolved_images(
    ctx: NodeContext | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    image_refs = metadata.get("image_refs")
    if image_refs is None:
        return metadata
    resolved = dict(metadata)
    resolved.pop("image_refs", None)
    resolved["images"] = await resolve_image_refs(ctx, image_refs)
    return resolved


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


def _required_prompt_results(inputs: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = inputs.get("prompt_results")
    if not isinstance(value, list) or len(value) == 0:
        raise ValidationError(
            code="runninghub_prompt_results_required",
            message="prompt_results must be a non-empty array",
        )
    return value


def _image_refs(inputs: Mapping[str, Any]) -> list[Any]:
    value = inputs.get("image_refs")
    if isinstance(value, list) and value:
        return value
    raise ValidationError(
        code="image_refs_required",
        message="RunningHub image-to-image requires at least one image reference",
    )


class RunningHubImageToImageNodeV3(BaseNode):
    _ref = "ai.runninghub_image_to_image.v3"
    _name = "RunningHub Image To Image V3 (Workflow)"
    _description = "Call RunningHub ComfyUI workflow API via nodeInfoList format."
    _input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "image_urls": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
            },
            "node_mapping": {
                "type": "object",
                "properties": {
                    "images": {"type": "array", "items": {"type": "string"}},
                    "text": {
                        "type": "object",
                        "properties": {
                            "nodeId": {"type": "string"},
                            "fieldName": {"type": "string"},
                        },
                    },
                    "select": {
                        "type": "object",
                        "properties": {
                            "nodeIds": {"type": "array", "items": {"type": "string"}},
                            "fieldName": {"type": "string"},
                        },
                    },
                },
            },
            "poll_interval_seconds": {"type": "number", "minimum": 0},
            "poll_timeout_seconds": {"type": "number", "minimum": 0},
        },
        "required": ["prompt", "image_urls", "node_mapping"],
        "additionalProperties": False,
    }

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
        result = await ImageGenerationCapability(
            model_router=self._model_router,
            provider=self._provider,
            model=self._model,
        ).generate_runninghub_workflow_image(
            prompt=inputs.get("prompt"),
            image_urls=inputs.get("image_urls"),
            node_mapping=inputs.get("node_mapping"),
            poll_interval_seconds=inputs.get("poll_interval_seconds"),
            poll_timeout_seconds=inputs.get("poll_timeout_seconds"),
        )
        return NodeResult(
            status="succeeded",
            output=result.output,
            metadata=result.metadata,
        )


def _ctx_image_ref_resolver(ctx: NodeContext | None):
    async def resolver(image_ref: Any) -> str:
        return await resolve_image_ref(ctx, image_ref)

    return resolver
