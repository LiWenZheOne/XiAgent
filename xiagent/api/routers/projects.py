from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from xiagent.api.dependencies import ApiServices, get_services

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    user_id: str
    name: str
    description: str | None = None


@router.post("")
async def create_project(
    request: CreateProjectRequest,
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    project = await services.users.create_project(
        owner_user_id=request.user_id,
        name=request.name,
        description=request.description,
    )
    return asdict(project)


@router.get("")
async def list_projects(
    user_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    projects = await services.users.list_projects_for_user(user_id=user_id)
    return {"items": [asdict(project) for project in projects]}
