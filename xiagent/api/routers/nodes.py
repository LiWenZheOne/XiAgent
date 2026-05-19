from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from xiagent.api.dependencies import ApiServices, get_services

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
async def list_nodes(services: Annotated[ApiServices, Depends(get_services)]) -> dict:
    descriptors = [node.describe() for node in services.node_registry.list()]
    return {"items": [asdict(descriptor) for descriptor in descriptors]}
