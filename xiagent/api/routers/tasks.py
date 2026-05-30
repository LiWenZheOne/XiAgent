from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from xiagent.api.dependencies import ApiServices, get_current_user, get_services
from xiagent.runtime.event_stream import format_sse_event
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
    return {"items": [asdict(task) for task in tasks]}


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    project_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
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
    events = await services.runtime.list_events(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    workflow_snapshot = await services.runtime.get_task_workflow_snapshot(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    return {
        "task": asdict(task),
        "node_executions": [asdict(execution) for execution in node_executions],
        "node_attempts": _group_node_attempts(node_executions),
        "events": [asdict(event) for event in events],
        "workflow_snapshot": workflow_snapshot,
    }


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
) -> StreamingResponse:
    user_id = current_user.user_id

    async def stream_events():
        sent_event_ids: set[str] = set()
        while not await request.is_disconnected():
            events = await services.runtime.list_events(
                user_id=user_id,
                project_id=project_id,
                task_id=task_id,
            )
            new_events = [event for event in events if event.event_id not in sent_event_ids]
            for event in new_events:
                sent_event_ids.add(event.event_id)
                yield format_sse_event(event)
            if any(_task_event_is_terminal(event.event_type) for event in events):
                break
            if not new_events:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream_events(), media_type="text/event-stream")


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


def _task_event_is_terminal(event_type: str) -> bool:
    return event_type in {"task_succeeded", "task_failed", "task_cancelled", "task_canceled", "task_archived"}
