from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from xiagent.api.dependencies import ApiServices, get_current_user, get_services
from xiagent.core.errors import ValidationError, XiAgentError
from xiagent.infrastructure.api_logging import sanitize_api_payload
from xiagent.nodes.base import NodeContext
from xiagent.nodes.ai.image_references import resolve_image_ref_with_asset_service
from xiagent.runtime.event_stream import format_sse_event_payload
from xiagent.runtime.models import NodeExecutionRecord
from xiagent.users.models import UserRecord

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    contract: dict[str, Any]


class ResumeTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    node_id: str
    input: dict[str, Any]


class DraftInteractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    node_id: str
    input: dict[str, Any]


class TaskAssetDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    node_id: str
    asset_type: str = "auto"
    description: str
    script: str = ""
    background: str = ""
    current_assets: dict[str, Any] = Field(default_factory=dict)


class TaskGenerateAssetImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    node_id: str
    prompt_result: dict[str, Any]
    prompt_prefix: str | None = None
    prompt_suffix: str | None = None
    aspect_ratio: str = "1:1"
    resolution: str = "2k"


class TaskGenerateStoryboardPanelImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    node_id: str
    card_id: str
    prompt: str
    image_refs: list[dict[str, Any]] = Field(default_factory=list)
    negative_prompt: str | None = None
    aspect_ratio: str = "16:9"
    resolution: str = "2K"


class TaskRegenerateStoryboardPanelPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    node_id: str
    card: dict[str, Any]
    item: dict[str, Any]
    shared_context: dict[str, Any] = Field(default_factory=dict)
    generation_rules: str | None = None
    negative_prompt: str | None = None
    aspect_ratio: str = "16:9"
    resolution: str = "2K"


class RerunNodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    rerun_notice: str = ""
    rerun_revision_note: str = ""


@router.post("")
async def create_task(
    request: CreateTaskRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    task = await services.runtime.create_task_from_contract(
        user_id=current_user.user_id,
        project_id=request.project_id,
        contract=request.contract,
        input_data={},
    )
    return asdict(task)


@router.get("")
async def list_tasks(
    project_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    tasks = await services.runtime.list_tasks(
        user_id=current_user.user_id,
        project_id=project_id,
    )
    items = []
    for task in tasks:
        item = asdict(task)
        if _task_uses_episode_summary(task.workflow_id):
            node_executions = await services.runtime.list_node_executions(
                user_id=current_user.user_id,
                project_id=project_id,
                task_id=task.task_id,
            )
            _attach_task_episode_summary(item, node_executions)
        items.append(item)
    return {"items": items}


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    project_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    return await _load_task_detail_payload(
        services=services,
        current_user=current_user,
        project_id=project_id,
        task_id=task_id,
    )


@router.get("/{task_id}/debug-export")
async def export_task_debug_package(
    task_id: str,
    project_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> JSONResponse:
    generated_at = datetime.now(UTC).isoformat()
    payload = await _load_task_detail_payload(
        services=services,
        current_user=current_user,
        project_id=project_id,
        task_id=task_id,
        full_events=True,
    )
    export_payload = {
        "export_version": "task_debug_export.v1",
        "generated_at": generated_at,
        **payload,
    }
    return JSONResponse(
        content=export_payload,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{_task_debug_export_filename(task_id, generated_at)}"',
        },
    )


async def _load_task_detail_payload(
    *,
    services: ApiServices,
    current_user: UserRecord,
    project_id: str,
    task_id: str,
    full_events: bool = False,
) -> dict[str, Any]:
    task = await services.runtime.get_task(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    node_executions = await services.runtime.list_node_executions(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    if full_events:
        events = [
            asdict(event)
            for event in await services.runtime.list_events(
                user_id=current_user.user_id,
                project_id=project_id,
                task_id=task_id,
            )
        ]
    else:
        events = await services.runtime.list_event_summaries(
            user_id=current_user.user_id,
            project_id=project_id,
            task_id=task_id,
        )
    workflow_snapshot = await services.runtime.get_task_workflow_snapshot(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    task_item = asdict(task)
    if _task_uses_episode_summary(task.workflow_id):
        _attach_task_episode_summary(task_item, node_executions)
    return {
        "task": task_item,
        "node_executions": [asdict(execution) for execution in node_executions],
        "node_attempts": _group_node_attempts(node_executions),
        "events": events,
        "workflow_snapshot": workflow_snapshot,
    }


def _task_debug_export_filename(task_id: str, generated_at: str) -> str:
    safe_task_id = _safe_filename_part(task_id)
    safe_timestamp = (
        generated_at.replace("+00:00", "Z")
        .replace(":", "-")
        .replace("/", "-")
    )
    return f"xiagent-task-{safe_task_id}-debug-{safe_timestamp}.json"


def _safe_filename_part(value: str) -> str:
    safe = "".join(
        char if char.isascii() and (char.isalnum() or char in {"-", "_", "."}) else "_"
        for char in value
    ).strip("._")
    return safe[:96] or "task"


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    project_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    await services.runtime.delete_task(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    return {"deleted": True, "task_id": task_id}


@router.get("/{task_id}/stream")
async def stream_task_events(
    task_id: str,
    project_id: str,
    request: Request,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    since_event_id: str | None = None,
) -> StreamingResponse:
    user_id = current_user.user_id

    async def stream_events():
        cursor_event_id = (
            since_event_id
            or request.headers.get("last-event-id")
            or await services.runtime.latest_event_id(
                user_id=user_id,
                project_id=project_id,
                task_id=task_id,
            )
        )
        while not await request.is_disconnected():
            events = await services.runtime.list_event_summaries(
                user_id=user_id,
                project_id=project_id,
                task_id=task_id,
                since_event_id=cursor_event_id,
            )
            for event in events:
                cursor_event_id = str(event["event_id"])
                yield format_sse_event_payload(
                    event_id=str(event["event_id"]),
                    event_type=str(event["event_type"]),
                    payload=_event_summary_stream_payload(event),
                )
            task = await services.runtime.get_task(
                user_id=user_id,
                project_id=project_id,
                task_id=task_id,
            )
            if task.status in {"succeeded", "failed", "archived"}:
                break
            if not events:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream_events(), media_type="text/event-stream")


def _event_summary_stream_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "node_id": event.get("node_id"),
            "message": event.get("message"),
            "changed_keys": event.get("changed_keys"),
            "created_at": event.get("created_at"),
        }.items()
        if value not in (None, "", [])
    }


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    request: ResumeTaskRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    task = await services.runtime.resume_task(
        user_id=current_user.user_id,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        input=request.input,
    )
    return asdict(task)


@router.post("/{task_id}/interactions")
async def create_task_interaction(
    task_id: str,
    request: ResumeTaskRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    task = await services.runtime.resume_task(
        user_id=current_user.user_id,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        input=request.input,
    )
    return asdict(task)


@router.put("/{task_id}/interactions/draft")
async def save_task_interaction_draft(
    task_id: str,
    request: DraftInteractionRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    task = await services.runtime.save_waiting_node_draft(
        user_id=current_user.user_id,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        input=request.input,
    )
    return asdict(task)


@router.post("/{task_id}/interactions/asset-draft")
async def draft_task_asset_from_description(
    task_id: str,
    request: TaskAssetDraftRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    description = request.description.strip()
    if not description:
        raise ValidationError(
            code="asset_draft_description_required",
            message="请先描述需要新增的资产特征。",
        )

    async def run() -> dict[str, Any]:
        result = await services.asset_generations.prompt_draft_capability.draft_asset_from_description(
            asset_type=request.asset_type,
            description=description,
            script=request.script,
            background=request.background,
            current_assets=_sanitize_business_input(request.current_assets),
            max_attempts=2,
        )
        return result.output

    return await _run_task_ai_interaction(
        services=services,
        current_user=current_user,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        operation="asset_draft_from_description",
        run=run,
        draft_patch=lambda result: {"ai_draft_result": result},
    )


@router.post("/{task_id}/interactions/generate-asset-image")
async def generate_task_asset_image(
    task_id: str,
    request: TaskGenerateAssetImageRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    if not request.prompt_result:
        raise ValidationError(
            code="asset_image_prompt_result_required",
            message="资产图像生成需要提示词信息。",
        )

    async def run() -> dict[str, Any]:
        result = await services.asset_generations.image_generation_capability.generate_asset_images(
            prompt_results=[request.prompt_result],
            prompt_prefix=request.prompt_prefix or "",
            prompt_suffix=request.prompt_suffix or "",
            aspect_ratio=request.aspect_ratio,
            resolution=request.resolution,
            image_ref_resolver=_task_image_ref_resolver(
                services=services,
                user_id=current_user.user_id,
                project_id=request.project_id,
            ),
        )
        images = result.output.get("asset_images")
        if not isinstance(images, list) or not images or not isinstance(images[0], dict):
            raise ValidationError(
                code="asset_image_generation_empty",
                message="资产图像生成没有返回图像。",
            )
        return images[0]

    return await _run_task_ai_interaction(
        services=services,
        current_user=current_user,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        operation="asset_image_generation",
        run=run,
        draft_patch=lambda result: {"ai_generated_asset_image": result},
    )


@router.post("/{task_id}/interactions/storyboard-panel-image")
async def generate_task_storyboard_panel_image(
    task_id: str,
    request: TaskGenerateStoryboardPanelImageRequest,
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

    async def run() -> dict[str, Any]:
        result = await services.asset_generations.image_generation_capability.generate_image_to_image(
            prompt=request.prompt,
            image_refs=request.image_refs,
            image_ref_resolver=_task_image_ref_resolver(
                services=services,
                user_id=current_user.user_id,
                project_id=request.project_id,
            ),
            aspect_ratio=request.aspect_ratio,
            resolution=request.resolution,
            temperature=0.2,
            poll_interval_seconds=2,
            poll_timeout_seconds=720,
        )
        image_url = result.output.get("image_url")
        if not isinstance(image_url, str) or not image_url:
            raise ValidationError(
                code="storyboard_panel_image_generation_empty",
                message="分镜图像生成没有返回图像。",
            )
        return {
            "card_id": request.card_id,
            "image_url": image_url,
            "source": "ai_generated",
            "runninghub_task_id": result.output.get("task_id", ""),
        }

    return await _run_task_ai_interaction(
        services=services,
        current_user=current_user,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        operation="storyboard_panel_image_generation",
        run=run,
        draft_patch=lambda result: {"ai_generated_storyboard_panel_image": result},
    )


@router.post("/{task_id}/interactions/storyboard-panel-prompt")
async def regenerate_task_storyboard_panel_prompt(
    task_id: str,
    request: TaskRegenerateStoryboardPanelPromptRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    if not request.item:
        raise ValidationError(
            code="storyboard_panel_item_required",
            message="重新生成分镜提示词需要当前段落上下文。",
        )
    await _validate_asset_refs_in_value(
        services=services,
        user_id=current_user.user_id,
        project_id=request.project_id,
        value={"card": request.card, "item": request.item},
    )

    async def run() -> dict[str, Any]:
        return await _regenerate_storyboard_panel_prompt_for_task(
            services=services,
            current_user=current_user,
            project_id=request.project_id,
            task_id=task_id,
            node_id=request.node_id,
            request=request,
        )

    return await _run_task_ai_interaction(
        services=services,
        current_user=current_user,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        operation="storyboard_panel_prompt_generation",
        run=run,
        draft_patch=lambda result: {"ai_generated_storyboard_panel_prompt": result},
    )


@router.post("/{task_id}/nodes/{node_id}/rerun")
async def rerun_task_node(
    task_id: str,
    node_id: str,
    request: RerunNodeRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    task = await services.runtime.rerun_node(
        user_id=current_user.user_id,
        project_id=request.project_id,
        task_id=task_id,
        node_id=node_id,
        rerun_revision_note=request.rerun_revision_note or request.rerun_notice,
    )
    return asdict(task)


def _group_node_attempts(executions: list[NodeExecutionRecord]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for execution in executions:
        grouped.setdefault(execution.node_id, []).append(asdict(execution))
    return grouped


async def _run_task_ai_interaction(
    *,
    services: ApiServices,
    current_user: UserRecord,
    project_id: str,
    task_id: str,
    node_id: str,
    operation: str,
    run: Callable[[], Awaitable[dict[str, Any]]],
    draft_patch: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    await _record_task_ai_event(
        services=services,
        current_user=current_user,
        project_id=project_id,
        task_id=task_id,
        node_id=node_id,
        event_type="node_ai_interaction_started",
        payload={"operation": operation},
    )
    try:
        result = await run()
        patch = draft_patch(result)
        await services.runtime.save_waiting_node_draft(
            user_id=current_user.user_id,
            project_id=project_id,
            task_id=task_id,
            node_id=node_id,
            input=patch,
        )
        await _record_task_ai_event(
            services=services,
            current_user=current_user,
            project_id=project_id,
            task_id=task_id,
            node_id=node_id,
            event_type="node_ai_interaction_succeeded",
            payload={
                "operation": operation,
                "result": sanitize_api_payload(result),
                "draft_patch": sanitize_api_payload(patch),
            },
        )
        return result
    except XiAgentError as exc:
        await _record_task_ai_event(
            services=services,
            current_user=current_user,
            project_id=project_id,
            task_id=task_id,
            node_id=node_id,
            event_type="node_ai_interaction_failed",
            payload={
                "operation": operation,
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            },
        )
        raise
    except Exception as exc:
        await _record_task_ai_event(
            services=services,
            current_user=current_user,
            project_id=project_id,
            task_id=task_id,
            node_id=node_id,
            event_type="node_ai_interaction_failed",
            payload={
                "operation": operation,
                "error": {
                    "code": "node_ai_interaction_failed",
                    "message": str(exc),
                    "details": {},
                },
            },
        )
        raise


async def _record_task_ai_event(
    *,
    services: ApiServices,
    current_user: UserRecord,
    project_id: str,
    task_id: str,
    node_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    await services.runtime.record_waiting_node_interaction_event(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
        node_id=node_id,
        event_type=event_type,
        payload=payload,
    )


def _task_image_ref_resolver(*, services: ApiServices, user_id: str, project_id: str):
    async def resolver(image_ref: Any) -> str:
        return await resolve_image_ref_with_asset_service(
            user_id=user_id,
            project_id=project_id,
            asset_service=services.assets,
            image_ref=image_ref,
        )

    return resolver


async def _validate_asset_refs_in_value(
    *,
    services: ApiServices,
    user_id: str,
    project_id: str,
    value: Any,
) -> None:
    if isinstance(value, dict):
        if value.get("kind") == "asset":
            asset_id = value.get("asset_id")
            if not isinstance(asset_id, str) or not asset_id.strip():
                raise ValidationError(
                    code="image_ref_invalid",
                    message="Asset image reference requires asset_id",
                )
            await services.assets.get_asset(
                user_id=user_id,
                asset_id=asset_id.strip(),
                project_id=project_id,
            )
        for item in value.values():
            await _validate_asset_refs_in_value(
                services=services,
                user_id=user_id,
                project_id=project_id,
                value=item,
            )
    elif isinstance(value, list):
        for item in value:
            await _validate_asset_refs_in_value(
                services=services,
                user_id=user_id,
                project_id=project_id,
                value=item,
            )


async def _regenerate_storyboard_panel_prompt_for_task(
    *,
    services: ApiServices,
    current_user: UserRecord,
    project_id: str,
    task_id: str,
    node_id: str,
    request: TaskRegenerateStoryboardPanelPromptRequest,
) -> dict[str, Any]:
    item = request.item
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

    workflow_snapshot = await services.runtime.get_task_workflow_snapshot(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    workflow_nodes = _workflow_nodes_by_id(workflow_snapshot)
    required_nodes = [
        "analyze_scene_layout",
        "plan_storyboard_panels",
        "review_and_refine_storyboard_plan",
        "convert_storyboard_plan_to_image_prompt",
        "review_and_refine_image_prompt",
    ]
    missing_nodes = [node for node in required_nodes if node not in workflow_nodes]
    if missing_nodes:
        raise ValidationError(
            code="storyboard_panel_workflow_nodes_missing",
            message="当前任务工作流不支持分镜提示词重生成。",
            details={"missing_nodes": missing_nodes},
        )
    waiting_execution = await _waiting_execution(
        services=services,
        current_user=current_user,
        project_id=project_id,
        task_id=task_id,
        node_id=node_id,
    )
    context_base = {
        "user_id": current_user.user_id,
        "project_id": project_id,
        "task_id": task_id,
        "node_id": node_id,
        "node_execution_id": waiting_execution.node_execution_id,
        "asset_service": services.assets,
    }
    manual_panel_count = _manual_panel_count(item.get("panel_count"))

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

    plan_inputs = _parallel_storyboard_inputs(
        workflow_nodes["plan_storyboard_panels"],
        items=layout_items,
        shared_context=request.shared_context,
    )
    _apply_manual_panel_count_override(plan_inputs, manual_panel_count, review=False)
    plan_result = await _run_workflow_node(
        services=services,
        context_base=context_base,
        workflow_node=workflow_nodes["plan_storyboard_panels"],
        execution_suffix=f"{request.card.get('card_id', 'preview')}_plan",
        inputs=plan_inputs,
    )
    plan_items = _result_items(plan_result, node_id="plan_storyboard_panels")

    plan_review_inputs = _review_storyboard_inputs(
        workflow_nodes["review_and_refine_storyboard_plan"],
        items=plan_items,
        storyboard_items=[item],
        shared_context=request.shared_context,
    )
    _apply_manual_panel_count_override(plan_review_inputs, manual_panel_count, review=True)

    plan_review_result = await _run_workflow_node(
        services=services,
        context_base=context_base,
        workflow_node=workflow_nodes["review_and_refine_storyboard_plan"],
        execution_suffix=f"{request.card.get('card_id', 'preview')}_plan_review",
        inputs=plan_review_inputs,
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
            task_id=task_id,
            node_id=node_id,
            node_execution_id=f"{waiting_execution.node_execution_id}:prepare_storyboard_panel_prompt",
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
    requested_card_id = request.card.get("card_id")
    panel_index = request.card.get("panel_index")
    if not isinstance(cards, list):
        cards = []
    matched = next(
        (
            card
            for card in cards
            if isinstance(card, dict)
            and requested_card_id
            and card.get("card_id") == requested_card_id
        ),
        None,
    )
    matched = matched or next(
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


async def _waiting_execution(
    *,
    services: ApiServices,
    current_user: UserRecord,
    project_id: str,
    task_id: str,
    node_id: str,
) -> NodeExecutionRecord:
    executions = await services.runtime.list_node_executions(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    for execution in executions:
        if execution.node_id == node_id and execution.status == "waiting":
            return execution
    raise ValidationError(
        code="waiting_node_not_found",
        message="Waiting node execution was not found",
        details={"task_id": task_id, "node_id": node_id},
    )


def _workflow_nodes_by_id(workflow_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = workflow_snapshot.get("nodes")
    if not isinstance(nodes, list):
        raise ValidationError(
            code="workflow_snapshot_nodes_invalid",
            message="Workflow snapshot nodes are not available",
        )
    return {str(node["id"]): node for node in nodes if isinstance(node, dict) and "id" in node}


def _segment_assignment_with_reference_images(
    assignment: Any,
    reference_images: list[dict[str, Any]],
) -> dict[str, Any]:
    base = assignment if isinstance(assignment, dict) else {}
    next_assignment = dict(base)
    characters = list(_object_list(next_assignment.get("characters")))
    prop_assets = list(_object_list(next_assignment.get("prop_assets")))
    location_asset = next_assignment.get("location_asset")
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
        next_assignment["characters"] = characters
    if location_asset is not None:
        next_assignment["location_asset"] = location_asset
    if prop_assets:
        next_assignment["prop_assets"] = prop_assets
    return next_assignment


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
        "image_ref": _public_image_ref(image_ref),
    }
    asset_tags = [tag for tag in reference.get("asset_tags", []) if isinstance(tag, str) and tag]
    if asset_tags:
        item["asset_tags"] = asset_tags
    return item


def _public_image_ref(image_ref: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": image_ref.get("kind")}
    asset_id = _text(image_ref.get("asset_id"))
    if asset_id:
        result["asset_id"] = asset_id
    role = _text(image_ref.get("role"))
    if role:
        result["role"] = role
    if result.get("kind") == "data_uri":
        data = _text(image_ref.get("data"))
        if data:
            result["data"] = data
    return result


async def _run_workflow_node(
    *,
    services: ApiServices,
    context_base: dict[str, Any],
    workflow_node: dict[str, Any],
    execution_suffix: str,
    inputs: dict[str, Any],
) -> Any:
    node = services.node_registry.get(str(workflow_node["ref"]))
    return await node.run(
        NodeContext(
            user_id=str(context_base["user_id"]),
            project_id=str(context_base["project_id"]),
            task_id=str(context_base["task_id"]),
            node_id=str(context_base["node_id"]),
            node_execution_id=f"{context_base['node_execution_id']}:{execution_suffix}",
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


def _manual_panel_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.casefold() == "auto":
        return None
    return int(text) if text.isdigit() and int(text) > 0 else None


def _apply_manual_panel_count_override(
    inputs: dict[str, Any],
    panel_count: int | None,
    *,
    review: bool,
) -> None:
    if panel_count is None:
        return
    if review:
        instruction = (
            f"\n\n人工覆盖分格数：用户手动指定目标分格数为 {panel_count}。"
            f"审查和修订时必须要求 panel_plan.panel_count 等于 {panel_count}，"
            f"且 panel_plan.panels 数量也等于 {panel_count}。"
        )
        for key in ("review_prompt_template", "revision_prompt_template"):
            if isinstance(inputs.get(key), str):
                inputs[key] += instruction
        return

    instruction = (
        f"\n\n人工覆盖分格数：用户手动指定目标分格数为 {panel_count}。"
        f"本次重新生成必须让 panel_plan.panel_count 等于 {panel_count}，"
        f"并且 panel_plan.panels 数量也等于 {panel_count}；不要自行改成其他分格数。"
    )
    if isinstance(inputs.get("prompt_template"), str):
        inputs["prompt_template"] += instruction


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


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


_UNTRUSTED_REFERENCE_KEYS = {
    "storage_uri",
    "public_url",
    "preview_url",
    "content_url",
    "thumbnail_url",
    "url",
    "image_url",
    "default_variant_storage_uri",
}


def _sanitize_business_input(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_business_input(item)
            for key, item in value.items()
            if key not in _UNTRUSTED_REFERENCE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_business_input(item) for item in value]
    return value


def _attach_task_episode_summary(item: dict[str, Any], node_executions: list[NodeExecutionRecord]) -> None:
    episode_name = _task_episode_name(node_executions)
    if not episode_name:
        return
    current_view = item.get("current_view")
    if not isinstance(current_view, dict):
        current_view = {}
        item["current_view"] = current_view
    summary = current_view.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        current_view["summary"] = summary
    summary["episode_name"] = episode_name


def _task_uses_episode_summary(workflow_id: str) -> bool:
    return workflow_id in {"asset_catalog", "asset_storyboard_generation"}


def _task_episode_name(node_executions: list[NodeExecutionRecord]) -> str:
    for execution in reversed(node_executions):
        for snapshot in (execution.output_snapshot, execution.input_snapshot):
            if not isinstance(snapshot, dict):
                continue
            episode_name = snapshot.get("episode_name")
            if isinstance(episode_name, str) and episode_name.strip():
                return episode_name.strip()
    return ""
