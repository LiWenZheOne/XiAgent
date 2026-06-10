from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from xiagent.api.asset_responses import asset_list_response, asset_response
from xiagent.api.dependencies import ApiServices, get_current_user, get_services
from xiagent.core.errors import ValidationError, XiAgentError
from xiagent.users.models import UserRecord

router = APIRouter(prefix="/api/assets", tags=["assets"])

_STORYBOARD_REFERENCE_IMAGE_LIMIT = 10


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


class UpdateTextAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class GenerateStoryboardPanelImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    card_id: str
    prompt: str
    image_refs: list[dict[str, Any]] = Field(default_factory=list)
    negative_prompt: str | None = None
    aspect_ratio: str = "16:9"
    resolution: str = "2K"


class RegenerateStoryboardPanelPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    card: dict[str, Any]
    item: dict[str, Any]
    shared_context: dict[str, Any] = Field(default_factory=dict)
    generation_rules: str | None = None
    negative_prompt: str | None = None
    aspect_ratio: str = "16:9"
    resolution: str = "2K"


class TransferAssetsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_ids: list[str] = Field(default_factory=list)
    operation: str = "copy"
    target_project_id: str
    source_project_id: str | None = None
    copy_tags: bool = True


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
    return asset_response(asset)


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

    return await services.asset_generations.draft_asset_from_description(
        user_id=current_user.user_id,
        project_id=request.project_id,
        asset_type=request.asset_type,
        description=description,
        script=request.script,
        background=request.background,
        current_assets=request.current_assets,
    )


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

    job = await services.asset_generations.create_asset_image_generation(
        user_id=current_user.user_id,
        project_id=request.project_id,
        input_payload=request.model_dump(mode="json"),
    )
    background_tasks.add_task(
        services.asset_generations.run_asset_image_generation,
        generation_id=job.generation_id,
    )
    return job.to_dict()


@router.post("/storyboard-panel-image")
async def generate_storyboard_panel_image(
    request: GenerateStoryboardPanelImageRequest,
    background_tasks: BackgroundTasks,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    if not request.prompt.strip():
        raise ValidationError(
            code="storyboard_panel_prompt_required",
            message="分镜图像生成需要提示词。",
        )
    if not request.image_refs:
        raise ValidationError(
            code="storyboard_panel_image_refs_required",
            message="分镜图像生成至少需要一张参考图。",
        )
    if len(request.image_refs) > _STORYBOARD_REFERENCE_IMAGE_LIMIT:
        raise ValidationError(
            code="storyboard_panel_image_refs_limit_exceeded",
            message=f"参考图最多 {_STORYBOARD_REFERENCE_IMAGE_LIMIT} 张，请删除多余参考图后再生成。",
            details={"limit": _STORYBOARD_REFERENCE_IMAGE_LIMIT, "count": len(request.image_refs)},
        )

    raise ValidationError(
        code="workflow_ai_requires_runtime",
        message="工作流分镜图像生成必须通过任务交互接口执行。",
    )


@router.post("/storyboard-panel-prompt")
async def regenerate_storyboard_panel_prompt(
    request: RegenerateStoryboardPanelPromptRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    raise ValidationError(
        code="workflow_ai_requires_runtime",
        message="工作流分镜提示词生成必须通过任务交互接口执行。",
    )
@router.get("/generate-image/{generation_id}")
async def get_asset_image_generation(
    generation_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    return services.asset_generations.get_generation(
        user_id=current_user.user_id,
        generation_id=generation_id,
    ).to_dict()


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
    return asset_response(asset)


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
    result = await services.asset_generations.complete_upload_metadata(
        asset_name=clean_name,
        asset_type=asset_type,
        world_background=world_background,
    )
    completed_metadata = result.get("metadata")
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
        "asset": asset_response(updated),
        "confidence": result.get("confidence", 0),
        "reasoning": result.get("reasoning", ""),
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
    return {"items": asset_list_response(result.items), "total": result.total}


@router.post("/transfer")
async def transfer_assets(
    request: TransferAssetsRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    clean_asset_ids = _unique_ids(request.asset_ids)
    if not clean_asset_ids:
        raise ValidationError(
            code="asset_transfer_assets_required",
            message="请选择需要复制或转移的资产。",
        )
    target_project_id = request.target_project_id.strip()
    if not target_project_id:
        raise ValidationError(
            code="asset_transfer_target_project_required",
            message="请选择目标项目。",
        )
    operation = request.operation.strip().lower()
    if operation not in {"copy", "move"}:
        raise ValidationError(
            code="asset_transfer_operation_invalid",
            message="资产操作只能是复制或转移。",
            details={"operation": request.operation},
        )

    items = []
    failures = []
    for asset_id in clean_asset_ids:
        try:
            if operation == "move":
                asset = await services.assets.move_asset(
                    user_id=current_user.user_id,
                    asset_id=asset_id,
                    target_scope="project",
                    target_project_id=target_project_id,
                    source_project_id=request.source_project_id,
                    copy_tags=request.copy_tags,
                )
            else:
                asset = await services.assets.copy_asset(
                    user_id=current_user.user_id,
                    asset_id=asset_id,
                    target_scope="project",
                    target_project_id=target_project_id,
                    source_project_id=request.source_project_id,
                    copy_tags=request.copy_tags,
                )
            items.append(asset_response(asset))
        except XiAgentError as exc:
            failures.append({"asset_id": asset_id, "code": exc.code, "message": exc.message, "details": exc.details})

    return {"items": items, "failures": failures}


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
    return asset_response(asset)


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
    return asset_response(asset)


@router.put("/{asset_id}/text")
async def update_text_asset(
    asset_id: str,
    request: UpdateTextAssetRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    asset = await services.assets.update_text_asset(
        user_id=current_user.user_id,
        asset_id=asset_id,
        name=request.name,
        text=request.text,
        metadata=request.metadata,
    )
    return asset_response(asset)


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
    return asset_response(asset)


@router.get("/{asset_id}/thumbnail")
async def get_asset_thumbnail(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
    size: int = 256,
) -> Response:
    thumbnail = await services.assets.get_asset_thumbnail(
        user_id=current_user.user_id,
        asset_id=asset_id,
        project_id=project_id,
        size=size,
    )
    return Response(
        thumbnail.bytes_content or b"",
        media_type=thumbnail.content_type or "image/png",
        headers={"X-Asset-Thumbnail-Cache": "hit" if thumbnail.cache_hit else "miss"},
    )


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


def _unique_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    clean_values: list[str] = []
    for value in values:
        clean_value = value.strip()
        if clean_value and clean_value not in seen:
            clean_values.append(clean_value)
            seen.add(clean_value)
    return clean_values
