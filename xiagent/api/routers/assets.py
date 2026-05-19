from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from xiagent.api.dependencies import ApiServices, get_current_user, get_services
from xiagent.users.models import UserRecord

router = APIRouter(prefix="/api/assets", tags=["assets"])


class CreateTextAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    project_id: str | None = None
    name: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


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


@router.get("/search")
async def search_assets(
    scope: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
    keyword: str | None = None,
    asset_type: str | None = None,
    mime_type: str | None = None,
) -> dict:
    result = await services.assets.search_assets(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
        keyword=keyword,
        asset_type=asset_type,
        mime_type=mime_type,
    )
    return {"items": [asdict(asset) for asset in result.items], "total": result.total}
