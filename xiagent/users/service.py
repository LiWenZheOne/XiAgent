from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from xiagent.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from xiagent.core.ids import new_id
from xiagent.core.services import UserService
from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.password import hash_password, verify_password
from xiagent.users.models import AuthResult, ProjectRecord, UserRecord


class SqliteUserService(UserService):
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def create_user(self, *, username: str, password: str) -> UserRecord:
        clean_username = username.strip()
        if not clean_username:
            raise ValidationError("username_required", "Username must not be empty")
        if not password:
            raise ValidationError("password_required", "Password must not be empty")

        now = _utc_now()
        user_id = new_id("user")
        try:
            async with connect_db(self._database_path) as db:
                await db.execute(
                    """
                    insert into users (
                      user_id, username, password_hash, status, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        clean_username,
                        hash_password(password),
                        "active",
                        now,
                        now,
                    ),
                )
        except (aiosqlite.IntegrityError, sqlite3.IntegrityError) as exc:
            raise ConflictError(
                "username_exists",
                "Username already exists",
                {"username": clean_username},
            ) from exc

        return UserRecord(
            user_id=user_id,
            username=clean_username,
            status="active",
            created_at=now,
            updated_at=now,
        )

    async def authenticate(self, *, username: str, password: str) -> AuthResult:
        clean_username = username.strip()
        async with connect_db(self._database_path) as db:
            row = await _fetch_one(
                db,
                "select * from users where username = ?",
                (clean_username,),
            )

        if row is None:
            raise _invalid_credentials()
        if row["status"] != "active":
            raise _invalid_credentials()
        if not verify_password(password, row["password_hash"]):
            raise _invalid_credentials()

        return AuthResult(user=_user_from_row(row))

    async def get_user(self, *, user_id: str) -> UserRecord:
        async with connect_db(self._database_path) as db:
            row = await _fetch_one(
                db,
                "select * from users where user_id = ?",
                (user_id,),
            )

        if row is None:
            raise NotFoundError("user_not_found", "User was not found", {"user_id": user_id})
        return _user_from_row(row)

    async def create_project(
        self,
        *,
        owner_user_id: str,
        name: str,
        description: str | None = None,
    ) -> ProjectRecord:
        owner = await self.get_user(user_id=owner_user_id)
        if owner.status != "active":
            raise PermissionDeniedError(
                "user_inactive",
                "Inactive users cannot create projects",
                {"user_id": owner_user_id},
            )
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("project_name_required", "Project name must not be empty")

        now = _utc_now()
        project_id = new_id("project")
        async with connect_db(self._database_path) as db:
            await db.execute(
                """
                insert into projects (
                  project_id, owner_user_id, name, description, status, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    owner_user_id,
                    clean_name,
                    description,
                    "active",
                    now,
                    now,
                ),
            )

        return ProjectRecord(
            project_id=project_id,
            owner_user_id=owner_user_id,
            name=clean_name,
            description=description,
            status="active",
            created_at=now,
            updated_at=now,
        )

    async def get_project(self, *, user_id: str, project_id: str) -> ProjectRecord:
        await self._ensure_active_user(user_id=user_id)
        async with connect_db(self._database_path) as db:
            row = await _fetch_authorized_active_project(
                db,
                user_id=user_id,
                project_id=project_id,
            )

        if row is None:
            raise _project_access_denied(
                action="project:get",
                project_id=project_id,
            )
        return _project_from_row(row)

    async def list_projects_for_user(self, *, user_id: str) -> list[ProjectRecord]:
        await self._ensure_active_user(user_id=user_id)
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                """
                select *
                from projects
                where owner_user_id = ? and status = 'active'
                order by created_at asc
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()

        return [_project_from_row(row) for row in rows]

    async def ensure_project_access(self, *, user_id: str, project_id: str, action: str) -> None:
        await self._ensure_active_user(user_id=user_id)
        async with connect_db(self._database_path) as db:
            row = await _fetch_authorized_active_project(
                db,
                user_id=user_id,
                project_id=project_id,
            )

        if row is None:
            raise _project_access_denied(action=action, project_id=project_id)

    async def _ensure_active_user(self, *, user_id: str) -> None:
        user = await self.get_user(user_id=user_id)
        if user.status != "active":
            raise PermissionDeniedError(
                "user_inactive",
                "Inactive users cannot access projects",
                {"user_id": user_id},
            )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


async def _fetch_one(
    db: aiosqlite.Connection,
    query: str,
    parameters: tuple[str, ...],
) -> aiosqlite.Row | None:
    cursor = await db.execute(query, parameters)
    try:
        return await cursor.fetchone()
    finally:
        await cursor.close()


async def _fetch_authorized_active_project(
    db: aiosqlite.Connection,
    *,
    user_id: str,
    project_id: str,
) -> aiosqlite.Row | None:
    return await _fetch_one(
        db,
        """
        select *
        from projects
        where project_id = ? and owner_user_id = ? and status = 'active'
        """,
        (project_id, user_id),
    )


def _invalid_credentials() -> PermissionDeniedError:
    return PermissionDeniedError(
        "invalid_credentials",
        "Username or password is invalid",
    )


def _project_access_denied(*, action: str, project_id: str) -> PermissionDeniedError:
    return PermissionDeniedError(
        "project_access_denied",
        "User does not have access to this project",
        {"action": action, "project_id": project_id},
    )


def _user_from_row(row: aiosqlite.Row) -> UserRecord:
    return UserRecord(
        user_id=row["user_id"],
        username=row["username"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _project_from_row(row: aiosqlite.Row) -> ProjectRecord:
    return ProjectRecord(
        project_id=row["project_id"],
        owner_user_id=row["owner_user_id"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
