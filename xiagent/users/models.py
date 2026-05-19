from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserRecord:
    user_id: str
    username: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    project_id: str
    owner_user_id: str
    name: str
    description: str | None
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: UserRecord
