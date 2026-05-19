from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from xiagent.api.dependencies import ApiServices, get_services

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    user_id: str
    project_id: str
    contract: dict[str, Any]
    input_data: dict[str, Any]


class ResumeTaskRequest(BaseModel):
    user_id: str
    project_id: str
    node_id: str
    output: dict[str, Any]


@router.post("")
async def create_task(
    request: CreateTaskRequest,
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    task = await services.runtime.create_task_from_contract(
        user_id=request.user_id,
        project_id=request.project_id,
        contract=request.contract,
        input_data=request.input_data,
    )
    return asdict(task)


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    user_id: str,
    project_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    task = await services.runtime.get_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task_id,
    )
    node_executions = await services.runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task_id,
    )
    events = await services.runtime.list_events(
        user_id=user_id,
        project_id=project_id,
        task_id=task_id,
    )
    return {
        "task": asdict(task),
        "node_executions": [asdict(execution) for execution in node_executions],
        "events": [asdict(event) for event in events],
    }


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    request: ResumeTaskRequest,
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    task = await services.runtime.resume_task(
        user_id=request.user_id,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        output=request.output,
    )
    return asdict(task)
