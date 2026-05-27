from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from xiagent.api.dependencies import ApiServices, get_current_user, get_services
from xiagent.users.models import UserRecord

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("")
async def list_workflows(
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> dict:
    if project_id is None:
        return {"items": services.workflows.list_global()}
    await services.users.ensure_project_access(
        user_id=current_user.user_id,
        project_id=project_id,
        action="workflow:list",
    )
    return {"items": services.workflows.list_for_project(project_id)}
