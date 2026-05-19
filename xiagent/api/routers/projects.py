from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from xiagent.api.dependencies import ApiServices, get_current_user, get_services
from xiagent.users.models import UserRecord

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None


@router.post("")
async def create_project(
    request: CreateProjectRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    project = await services.users.create_project(
        owner_user_id=current_user.user_id,
        name=request.name,
        description=request.description,
    )
    return asdict(project)


@router.get("")
async def list_projects(
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    projects = await services.users.list_projects_for_user(user_id=current_user.user_id)
    return {"items": [asdict(project) for project in projects]}
