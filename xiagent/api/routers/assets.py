from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from xiagent.api.dependencies import ApiServices, get_current_user, get_services
from xiagent.core.errors import XiAgentError, ValidationError
from xiagent.nodes.base import NodeContext
from xiagent.users.models import UserRecord

router = APIRouter(prefix="/api/assets", tags=["assets"])


class CreateTextAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    project_id: str | None = None
    name: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateCollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    project_id: str | None = None
    parent_id: str | None = None
    name: str
    description: str | None = None


class UpdateCollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None


class CreateTagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    project_id: str | None = None
    name: str
    description: str | None = None


class UpdateTagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None


class UpdateAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    metadata: dict[str, Any] | None = None


class DraftAssetFromDescriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    asset_type: str = "auto"
    description: str
    script: str = ""
    background: str = ""
    current_assets: dict[str, Any] = Field(default_factory=dict)


class GenerateAssetImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    prompt_result: dict[str, Any]
    prompt_prefix: str | None = None
    prompt_suffix: str | None = None
    aspect_ratio: str = "1:1"
    resolution: str = "2k"


@router.post("/text")
async def create_text_asset(
    request: CreateTextAssetRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    asset = await services.assets.create_text_asset(
        user_id=current_user.user_id,
        scope=request.scope,
        project_id=request.project_id,
        name=request.name,
        text=request.text,
        metadata=request.metadata,
    )
    return asdict(asset)


@router.post("/draft-from-description")
async def draft_asset_from_description(
    request: DraftAssetFromDescriptionRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    description = request.description.strip()
    if not description:
        raise ValidationError(
            code="asset_draft_description_required",
            message="请先描述需要新增的资产特征。",
        )

    node = services.node_registry.get("ai.asset_draft_from_description.v1")
    result = await node.run(
        NodeContext(
            user_id=current_user.user_id,
            project_id=request.project_id or "global",
            task_id="asset_draft_preview",
            node_id="draft_asset_from_description",
            node_execution_id="asset_draft_preview",
            config={},
            output_schema=node.describe().output_schema,
            asset_service=services.assets,
            event_sink=None,
            logger=None,
        ),
        {
            "asset_type": request.asset_type,
            "description": description,
            "script": request.script,
            "background": request.background,
            "current_assets": request.current_assets,
            "max_attempts": 2,
        },
    )
    return result.output


@router.post("/generate-image")
async def generate_asset_image(
    request: GenerateAssetImageRequest,
    background_tasks: BackgroundTasks,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    if not request.prompt_result:
        raise ValidationError(
            code="asset_image_prompt_result_required",
            message="资产图像生成需要提示词信息。",
        )

    project_id = request.project_id or "global"
    job = services.image_generations.create(
        user_id=current_user.user_id,
        project_id=project_id,
        input_payload=request.model_dump(mode="json"),
    )
    background_tasks.add_task(
        _run_asset_image_generation,
        generation_id=job.generation_id,
        request_payload=request.model_dump(mode="json"),
        services=services,
        user_id=current_user.user_id,
        project_id=project_id,
    )
    return job.to_dict()


@router.get("/generate-image/{generation_id}")
async def get_asset_image_generation(
    generation_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    return services.image_generations.get(
        user_id=current_user.user_id,
        generation_id=generation_id,
    ).to_dict()


async def _run_asset_image_generation(
    *,
    generation_id: str,
    request_payload: dict[str, Any],
    services: ApiServices,
    user_id: str,
    project_id: str,
) -> None:
    services.image_generations.mark_running(generation_id)
    node = services.node_registry.get("ai.runninghub_image_to_image.v2")
    try:
        result = await node.run(
            NodeContext(
                user_id=user_id,
                project_id=project_id,
                task_id="asset_image_preview",
                node_id="generate_asset_image_preview",
                node_execution_id=generation_id,
                config={},
                output_schema=node.describe().output_schema,
                asset_service=services.assets,
                event_sink=None,
                logger=None,
            ),
            {
                "prompt_results": [request_payload["prompt_result"]],
                "prompt_prefix": request_payload.get("prompt_prefix") or "",
                "prompt_suffix": request_payload.get("prompt_suffix") or "",
                "aspect_ratio": request_payload.get("aspect_ratio", "1:1"),
                "resolution": request_payload.get("resolution", "2k"),
            },
        )
        images = result.output.get("asset_images")
        if not isinstance(images, list) or not images:
            raise ValidationError(
                code="asset_image_generation_empty",
                message="资产图像生成没有返回图像。",
            )
        image = images[0]
        if not isinstance(image, dict):
            raise ValidationError(
                code="asset_image_generation_invalid",
                message="资产图像生成返回了无效结果。",
            )
        services.image_generations.mark_succeeded(generation_id, image)
    except XiAgentError as exc:
        services.image_generations.mark_failed(
            generation_id,
            {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive background task guard
        services.image_generations.mark_failed(
            generation_id,
            {
                "code": "asset_image_generation_failed",
                "message": str(exc) or "资产图像生成失败。",
                "details": {},
            },
        )


@router.post("/files")
async def import_file_asset(
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    scope: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    metadata_json: Annotated[str, Form()] = "{}",
    collection_ids: Annotated[str | None, Form()] = None,
    tag_ids: Annotated[str | None, Form()] = None,
    publish: Annotated[bool, Form()] = True,
) -> dict:
    metadata = _metadata_from_json(metadata_json)
    content = await file.read()
    asset = await services.assets.import_file_asset(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
        file_name=name or file.filename or "asset.bin",
        content_type=file.content_type,
        content=content,
        metadata=metadata,
        publish=publish,
        collection_ids=_split_ids(collection_ids),
        tag_ids=_split_ids(tag_ids),
    )
    return asdict(asset)


@router.post("/files/intelligent")
async def import_file_asset_with_metadata_completion(
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    scope: Annotated[str, Form()],
    asset_type: Annotated[str, Form()],
    world_background: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    metadata_json: Annotated[str, Form()] = "{}",
    publish: Annotated[bool, Form()] = True,
) -> dict:
    clean_name = (name or file.filename or "asset.bin").strip()
    if not clean_name:
        raise ValidationError(
            code="asset_upload_name_required",
            message="资产名称不能为空。",
        )
    metadata = _metadata_from_json(metadata_json)
    content = await file.read()
    asset = await services.assets.import_file_asset(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
        file_name=clean_name,
        content_type=file.content_type,
        content=content,
        metadata=metadata,
        publish=publish,
    )
    node = services.node_registry.get("ai.asset_metadata_from_upload.v1")
    result = await node.run(
        NodeContext(
            user_id=current_user.user_id,
            project_id=project_id or "global",
            task_id="asset_upload_metadata_completion",
            node_id="asset_metadata_from_upload",
            node_execution_id=f"asset_upload_metadata_{asset.asset_id}",
            config={},
            output_schema=node.describe().output_schema,
            asset_service=services.assets,
            event_sink=None,
            logger=None,
        ),
        {
            "asset_id": asset.asset_id,
            "asset_name": clean_name,
            "asset_type": asset_type,
            "world_background": world_background,
            "max_attempts": 2,
        },
    )
    completed_metadata = result.output.get("metadata")
    if not isinstance(completed_metadata, dict):
        raise ValidationError(
            code="asset_upload_metadata_invalid",
            message="资产上传信息补全没有返回 metadata。",
        )
    next_metadata = {
        **asset.metadata,
        **completed_metadata,
        "metadata_source": "llm_upload_completion",
    }
    updated = await services.assets.update_asset(
        user_id=current_user.user_id,
        asset_id=asset.asset_id,
        name=clean_name,
        metadata=next_metadata,
    )
    tag = await _ensure_asset_type_tag(
        services=services,
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
        asset_type=str(next_metadata.get("type") or asset_type),
    )
    await services.assets.attach_asset_tag(
        user_id=current_user.user_id,
        asset_id=asset.asset_id,
        tag_id=tag.tag_id,
    )
    return {
        "asset": asdict(updated),
        "confidence": result.output.get("confidence", 0),
        "reasoning": result.output.get("reasoning", ""),
    }


@router.post("/collections")
async def create_collection_node(
    request: CreateCollectionRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    collection = await services.assets.create_collection_node(
        user_id=current_user.user_id,
        scope=request.scope,
        project_id=request.project_id,
        parent_id=request.parent_id,
        name=request.name,
        description=request.description,
    )
    return asdict(collection)


@router.get("/collections")
async def list_collection_nodes(
    scope: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> dict:
    collections = await services.assets.list_collection_nodes(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
    )
    return {"items": [asdict(collection) for collection in collections]}


@router.patch("/collections/{collection_id}")
async def update_collection_node(
    collection_id: str,
    request: UpdateCollectionRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    collection = await services.assets.update_collection_node(
        user_id=current_user.user_id,
        collection_id=collection_id,
        name=request.name,
        description=request.description,
    )
    return asdict(collection)


@router.delete("/collections/{collection_id}")
async def delete_collection_node(
    collection_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    await services.assets.delete_collection_node(
        user_id=current_user.user_id,
        collection_id=collection_id,
    )
    return {"deleted": True}


@router.post("/tags")
async def create_tag(
    request: CreateTagRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    tag = await services.assets.create_tag(
        user_id=current_user.user_id,
        scope=request.scope,
        project_id=request.project_id,
        name=request.name,
        description=request.description,
    )
    return asdict(tag)


@router.get("/tags")
async def list_tags(
    scope: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> dict:
    tags = await services.assets.list_tags(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
    )
    return {"items": [asdict(tag) for tag in tags]}


@router.patch("/tags/{tag_id}")
async def update_tag(
    tag_id: str,
    request: UpdateTagRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    tag = await services.assets.update_tag(
        user_id=current_user.user_id,
        tag_id=tag_id,
        name=request.name,
        description=request.description,
    )
    return asdict(tag)


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    await services.assets.delete_tag(
        user_id=current_user.user_id,
        tag_id=tag_id,
    )
    return {"deleted": True}


@router.get("/search")
async def search_assets(
    scope: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
    keyword: str | None = None,
    asset_type: str | None = None,
    mime_type: str | None = None,
    names: str | None = None,
    collection_id: str | None = None,
    tag_ids: str | None = None,
    tag_names: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    result = await services.assets.search_assets(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
        keyword=keyword,
        asset_type=asset_type,
        mime_type=mime_type,
        names=_split_ids(names),
        collection_id=collection_id,
        tag_ids=_split_ids(tag_ids),
        tag_names=_split_ids(tag_names),
        limit=limit,
        offset=offset,
    )
    return {"items": [asdict(asset) for asset in result.items], "total": result.total}


@router.get("/{asset_id}/tags")
async def list_asset_tags(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    tags = await services.assets.list_asset_tags(
        user_id=current_user.user_id,
        asset_id=asset_id,
    )
    return {"items": [asdict(tag) for tag in tags]}


@router.post("/{asset_id}/tags/{tag_id}")
async def attach_asset_tag(
    asset_id: str,
    tag_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    tags = await services.assets.attach_asset_tag(
        user_id=current_user.user_id,
        asset_id=asset_id,
        tag_id=tag_id,
    )
    return {"items": [asdict(tag) for tag in tags]}


@router.delete("/{asset_id}/tags/{tag_id}")
async def detach_asset_tag(
    asset_id: str,
    tag_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    tags = await services.assets.detach_asset_tag(
        user_id=current_user.user_id,
        asset_id=asset_id,
        tag_id=tag_id,
    )
    return {"items": [asdict(tag) for tag in tags]}


@router.get("/{asset_id}")
async def get_asset(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> dict:
    asset = await services.assets.get_asset(
        user_id=current_user.user_id,
        asset_id=asset_id,
        project_id=project_id,
    )
    return asdict(asset)


@router.patch("/{asset_id}")
async def update_asset(
    asset_id: str,
    request: UpdateAssetRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    asset = await services.assets.update_asset(
        user_id=current_user.user_id,
        asset_id=asset_id,
        name=request.name,
        metadata=request.metadata,
    )
    return asdict(asset)


@router.put("/{asset_id}/file")
async def replace_asset_file(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
) -> dict:
    content = await file.read()
    asset = await services.assets.replace_asset_file(
        user_id=current_user.user_id,
        asset_id=asset_id,
        file_name=file.filename or "asset.bin",
        content_type=file.content_type,
        content=content,
    )
    return asdict(asset)


@router.get("/{asset_id}/content")
async def get_asset_content(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> Response:
    content = await services.assets.get_asset_content(
        user_id=current_user.user_id,
        asset_id=asset_id,
        project_id=project_id,
    )
    if content.text_content is not None:
        return Response(content.text_content, media_type=content.content_type or "text/plain")
    return Response(content.bytes_content or b"", media_type=content.content_type)


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    await services.assets.delete_asset(user_id=current_user.user_id, asset_id=asset_id)
    return {"deleted": True}


def _metadata_from_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "invalid_asset_metadata",
            "Asset metadata_json must be a valid JSON object",
        ) from exc
    if not isinstance(parsed, dict):
        raise ValidationError(
            "invalid_asset_metadata",
            "Asset metadata_json must be a valid JSON object",
        )
    return parsed


async def _ensure_asset_type_tag(
    *,
    services: ApiServices,
    user_id: str,
    scope: str,
    project_id: str | None,
    asset_type: str,
):
    tag_name = _asset_type_tag_name(asset_type)
    tags = await services.assets.list_tags(
        user_id=user_id,
        scope=scope,
        project_id=project_id,
    )
    for tag in tags:
        if tag.name == tag_name and tag.scope == scope and (tag.project_id or None) == (project_id or None):
            return tag
    return await services.assets.create_tag(
        user_id=user_id,
        scope=scope,
        project_id=project_id,
        name=tag_name,
    )


def _asset_type_tag_name(asset_type: str) -> str:
    normalized = asset_type.strip().lower()
    if normalized in {"character", "role", "角色"}:
        return "角色"
    if normalized in {"location", "scene", "地点", "场景"}:
        return "地点"
    if normalized in {"prop", "item", "道具"}:
        return "道具"
    if normalized in {"episode_metadata", "episode", "episode_meta", "集元数据", "集信息资产", "集信息", "集"}:
        return "集元数据"
    raise ValidationError(
        code="asset_upload_type_invalid",
        message="资产类型只能是角色、地点、道具或集元数据。",
        details={"asset_type": asset_type},
    )


def _split_ids(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
