from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from xiagent.api.dependencies import ApiServices, get_services

router = APIRouter(prefix="/api/ui", tags=["ui"])


@router.get("/node-controls")
async def list_node_controls(
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    return {"items": [asdict(control) for control in services.ui_controls.list_controls()]}


@router.get("/node-controls/{control_id}")
async def get_node_control(
    control_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    try:
        return {"item": asdict(services.ui_controls.get(control_id))}
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_ui_control", "control_id": control_id},
        ) from exc
