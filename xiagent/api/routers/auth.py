from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from xiagent.api.dependencies import ApiServices, get_services

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
async def register_user(
    request: AuthRequest,
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    user = await services.users.create_user(username=request.username, password=request.password)
    return asdict(user)


@router.post("/login")
async def login(
    request: AuthRequest,
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict:
    result = await services.users.authenticate(username=request.username, password=request.password)
    return asdict(result)
