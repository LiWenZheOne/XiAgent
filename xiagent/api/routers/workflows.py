from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from xiagent.api.dependencies import ApiServices, get_services

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("")
async def list_workflows(services: Annotated[ApiServices, Depends(get_services)]) -> dict:
    return {"items": services.workflows.list()}
