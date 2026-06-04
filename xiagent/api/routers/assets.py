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

_STORYBOARD_WORKFLOW_ID = "asset_storyboard_generation"
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

    project_id = request.project_id or "global"
    job = services.image_generations.create(
        user_id=current_user.user_id,
        project_id=project_id,
        input_payload=request.model_dump(mode="json"),
    )
    background_tasks.add_task(
        _run_storyboard_panel_image_generation,
        generation_id=job.generation_id,
        request_payload=request.model_dump(mode="json"),
        services=services,
        user_id=current_user.user_id,
        project_id=project_id,
    )
    return job.to_dict()


@router.post("/storyboard-panel-prompt")
async def regenerate_storyboard_panel_prompt(
    request: RegenerateStoryboardPanelPromptRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    item = request.item
    if not item:
        raise ValidationError(
            code="storyboard_panel_item_required",
            message="重新生成分镜提示词需要当前段落上下文。",
        )
    if "reference_images" in request.card:
        item = {
            **item,
            "segment_assignment": _segment_assignment_with_reference_images(
                {"segment_index": item.get("index")},
                _object_list(request.card.get("reference_images")),
            ),
        }
    else:
        current_reference_images = _object_list(item.get("reference_images"))
        if current_reference_images:
            item = {
                **item,
                "segment_assignment": _segment_assignment_with_reference_images(
                    item.get("segment_assignment"),
                    current_reference_images,
                ),
            }
    project_id = request.project_id or "global"
    workflow_nodes = _workflow_nodes_by_id(services.workflows.get(_STORYBOARD_WORKFLOW_ID))
    context_base = {
        "user_id": current_user.user_id,
        "project_id": project_id,
        "task_id": "storyboard_panel_prompt_preview",
        "asset_service": services.assets,
    }

    layout_result = await _run_workflow_node(
        services=services,
        context_base=context_base,
        workflow_node=workflow_nodes["analyze_scene_layout"],
        execution_suffix=f"{request.card.get('card_id', 'preview')}_layout",
        inputs=_parallel_storyboard_inputs(
            workflow_nodes["analyze_scene_layout"],
            items=[item],
            shared_context=request.shared_context,
        ),
    )
    layout_items = _result_items(layout_result, node_id="analyze_scene_layout")

    plan_result = await _run_workflow_node(
        services=services,
        context_base=context_base,
        workflow_node=workflow_nodes["plan_storyboard_panels"],
        execution_suffix=f"{request.card.get('card_id', 'preview')}_plan",
        inputs=_parallel_storyboard_inputs(
            workflow_nodes["plan_storyboard_panels"],
            items=layout_items,
            shared_context=request.shared_context,
        ),
    )
    plan_items = _result_items(plan_result, node_id="plan_storyboard_panels")

    plan_review_result = await _run_workflow_node(
        services=services,
        context_base=context_base,
        workflow_node=workflow_nodes["review_and_refine_storyboard_plan"],
        execution_suffix=f"{request.card.get('card_id', 'preview')}_plan_review",
        inputs=_review_storyboard_inputs(
            workflow_nodes["review_and_refine_storyboard_plan"],
            items=plan_items,
            storyboard_items=[item],
            shared_context=request.shared_context,
        ),
    )
    reviewed_plan_items = _result_items(plan_review_result, node_id="review_and_refine_storyboard_plan")

    prompt_result = await _run_workflow_node(
        services=services,
        context_base=context_base,
        workflow_node=workflow_nodes["convert_storyboard_plan_to_image_prompt"],
        execution_suffix=f"{request.card.get('card_id', 'preview')}_prompt",
        inputs=_parallel_storyboard_inputs(
            workflow_nodes["convert_storyboard_plan_to_image_prompt"],
            items=reviewed_plan_items,
            shared_context=request.shared_context,
        ),
    )
    prompt_items = _result_items(prompt_result, node_id="convert_storyboard_plan_to_image_prompt")

    prompt_review_result = await _run_workflow_node(
        services=services,
        context_base=context_base,
        workflow_node=workflow_nodes["review_and_refine_image_prompt"],
        execution_suffix=f"{request.card.get('card_id', 'preview')}_prompt_review",
        inputs=_review_storyboard_inputs(
            workflow_nodes["review_and_refine_image_prompt"],
            items=prompt_items,
            storyboard_items=[item],
            shared_context=request.shared_context,
        ),
    )
    results = _result_items(prompt_review_result, node_id="review_and_refine_image_prompt")

    panel_node = services.node_registry.get("tool.prepare_storyboard_panel_cards.v1")
    panel_result = await panel_node.run(
        NodeContext(
            user_id=current_user.user_id,
            project_id=project_id,
            task_id="storyboard_panel_prompt_preview",
            node_id="prepare_storyboard_panel_prompt_preview",
            node_execution_id=f"storyboard_panel_card_{request.card.get('card_id', 'preview')}",
            config={},
            output_schema=panel_node.describe().output_schema,
            asset_service=services.assets,
            event_sink=None,
            logger=None,
        ),
        {
            "segment_descriptions": results,
            "segment_assignments": [item.get("segment_assignment") or {}],
            "storyboard_items": [item],
            "shared_context": request.shared_context,
            "generation_rules": request.generation_rules or "",
            "negative_prompt": request.negative_prompt or "",
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
        },
    )
    cards = panel_result.output.get("panel_cards")
    panel_index = request.card.get("panel_index")
    if not isinstance(cards, list):
        cards = []
    matched = next(
        (
            card
            for card in cards
            if isinstance(card, dict)
            and card.get("panel_index") == panel_index
            and card.get("segment_index") == request.card.get("segment_index")
        ),
        cards[0] if cards else None,
    )
    if not isinstance(matched, dict):
        raise ValidationError(
            code="storyboard_panel_prompt_card_missing",
            message="重新生成分镜提示词没有找到目标分格。",
        )
    return {"card": matched, "segment_description": results[0]}


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


async def _run_storyboard_panel_image_generation(
    *,
    generation_id: str,
    request_payload: dict[str, Any],
    services: ApiServices,
    user_id: str,
    project_id: str,
) -> None:
    services.image_generations.mark_running(generation_id)
    node = services.node_registry.get("ai.runninghub_image_to_image.v1")
    try:
        result = await node.run(
            NodeContext(
                user_id=user_id,
                project_id=project_id,
                task_id="storyboard_panel_image_preview",
                node_id="generate_storyboard_panel_image_preview",
                node_execution_id=generation_id,
                config={},
                output_schema=node.describe().output_schema,
                asset_service=services.assets,
                event_sink=None,
                logger=None,
            ),
            {
                "prompt": request_payload["prompt"],
                "image_refs": request_payload.get("image_refs") or [],
                "aspect_ratio": request_payload.get("aspect_ratio", "16:9"),
                "resolution": request_payload.get("resolution", "2K"),
                "temperature": 0.2,
                "poll_interval_seconds": 2,
                "poll_timeout_seconds": 720,
            },
        )
        image_url = result.output.get("image_url")
        if not isinstance(image_url, str) or not image_url:
            raise ValidationError(
                code="storyboard_panel_image_generation_empty",
                message="分镜图像生成没有返回图像。",
            )
        image = {
            "card_id": request_payload.get("card_id", ""),
            "image_url": image_url,
            "source": "ai_generated",
            "runninghub_task_id": result.output.get("task_id", ""),
        }
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
                "code": "storyboard_panel_image_generation_failed",
                "message": str(exc) or "分镜图像生成失败。",
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


def _workflow_nodes_by_id(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in contract.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("id"), str)}


def _segment_assignment_with_reference_images(
    value: Any,
    reference_images: list[dict[str, Any]],
) -> dict[str, Any]:
    assignment = dict(value) if isinstance(value, dict) else {}
    characters: list[dict[str, Any]] = []
    prop_assets: list[dict[str, Any]] = []
    location_asset: dict[str, Any] | None = None
    for reference in reference_images:
        reference_asset = _reference_image_as_assignment_asset(reference)
        if reference_asset is None:
            continue
        asset_type = str(reference_asset.get("asset_type") or "")
        if asset_type == "character":
            characters.append({**reference_asset, "presence": "present"})
        elif asset_type in {"scene", "location"} and location_asset is None:
            location_asset = reference_asset
        elif asset_type == "prop":
            prop_assets.append(reference_asset)
    if characters:
        assignment["characters"] = characters
    if location_asset is not None:
        assignment["location_asset"] = location_asset
    if prop_assets:
        assignment["prop_assets"] = prop_assets
    return assignment


def _reference_image_as_assignment_asset(reference: dict[str, Any]) -> dict[str, Any] | None:
    image_ref = reference.get("image_ref")
    if not isinstance(image_ref, dict):
        return None
    asset_name = _text(reference.get("asset_name")) or _text(reference.get("label"))
    if not asset_name:
        return None
    item: dict[str, Any] = {
        "asset_type": _text(reference.get("asset_type")) or "character",
        "asset_name": asset_name,
        "image_ref": dict(image_ref),
    }
    asset_tags = [tag for tag in reference.get("asset_tags", []) if isinstance(tag, str) and tag]
    if asset_tags:
        item["asset_tags"] = asset_tags
    preview_url = _text(reference.get("preview_url"))
    if preview_url:
        item["image_url"] = preview_url
    return item


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


async def _run_workflow_node(
    *,
    services: ApiServices,
    context_base: dict[str, Any],
    workflow_node: dict[str, Any],
    execution_suffix: str,
    inputs: dict[str, Any],
) -> Any:
    node_id = str(workflow_node["id"])
    node = services.node_registry.get(str(workflow_node["ref"]))
    return await node.run(
        NodeContext(
            user_id=str(context_base["user_id"]),
            project_id=str(context_base["project_id"]),
            task_id=str(context_base["task_id"]),
            node_id=node_id,
            node_execution_id=f"storyboard_panel_prompt_{execution_suffix}",
            config={},
            output_schema=workflow_node.get("outputs", node.describe().output_schema),
            asset_service=context_base["asset_service"],
            event_sink=None,
            logger=None,
        ),
        inputs,
    )


def _parallel_storyboard_inputs(
    workflow_node: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    shared_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inputs = workflow_node.get("inputs", {})
    payload: dict[str, Any] = {"items": items}
    for key in [
        "system",
        "prompt_template",
        "prompt_fields",
        "passthrough_fields",
        "required_input_fields",
        "max_attempts",
        "continue_on_item_error",
    ]:
        value = _literal_input(inputs, key)
        if value is not None:
            payload[key] = value
    if shared_context is not None:
        payload["shared_context"] = shared_context
    return payload


def _review_storyboard_inputs(
    workflow_node: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    storyboard_items: list[dict[str, Any]],
    shared_context: dict[str, Any],
) -> dict[str, Any]:
    inputs = workflow_node.get("inputs", {})
    payload: dict[str, Any] = {
        "items": items,
        "storyboard_items": storyboard_items,
        "shared_context": shared_context,
    }
    for key in [
        "review_system",
        "review_prompt_template",
        "revision_system",
        "revision_prompt_template",
        "review_output_field",
        "review_history_output_field",
        "required_input_fields",
        "max_revision_rounds",
        "max_attempts",
        "continue_on_item_error",
    ]:
        value = _literal_input(inputs, key)
        if value is not None:
            payload[key] = value
    return payload


def _literal_input(inputs: Any, key: str) -> Any:
    if not isinstance(inputs, dict):
        return None
    value = inputs.get(key)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    if isinstance(value, dict) and "from" in value:
        return None
    return value


def _result_items(result: Any, *, node_id: str) -> list[dict[str, Any]]:
    output = getattr(result, "output", {})
    results = output.get("results") if isinstance(output, dict) else None
    if not isinstance(results, list) or not results:
        raise ValidationError(
            code="storyboard_panel_prompt_empty",
            message="重新生成分镜提示词没有返回段落结果。",
            details={"node_id": node_id},
        )
    return [item for item in results if isinstance(item, dict)]
