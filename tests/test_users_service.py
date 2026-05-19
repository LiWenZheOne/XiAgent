from __future__ import annotations

import pytest

from xiagent.core.errors import ConflictError, PermissionDeniedError
from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.migrations import migrate
from xiagent.users.service import SqliteUserService


async def test_user_can_create_project_and_access_it(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    user = await service.create_user(username="alice", password="secret-123")
    auth = await service.authenticate(username="alice", password="secret-123")
    project = await service.create_project(owner_user_id=user.user_id, name="漫画项目A")

    assert auth.user.user_id == user.user_id
    assert project.owner_user_id == user.user_id
    await service.ensure_project_access(
        user_id=user.user_id,
        project_id=project.project_id,
        action="task:create",
    )


async def test_user_cannot_access_other_users_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    alice = await service.create_user(username="alice", password="secret-123")
    bob = await service.create_user(username="bob", password="secret-456")
    project = await service.create_project(owner_user_id=alice.user_id, name="漫画项目A")

    with pytest.raises(PermissionDeniedError):
        await service.ensure_project_access(
            user_id=bob.user_id,
            project_id=project.project_id,
            action="task:create",
        )


async def test_inactive_project_access_is_denied_for_owner(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    alice = await service.create_user(username="alice", password="secret-123")
    project = await service.create_project(owner_user_id=alice.user_id, name="Project A")

    async with connect_db(test_settings.database_path) as db:
        await db.execute(
            "update projects set status = 'deleted' where project_id = ?",
            (project.project_id,),
        )

    with pytest.raises(PermissionDeniedError) as exc_info:
        await service.ensure_project_access(
            user_id=alice.user_id,
            project_id=project.project_id,
            action="task:create",
        )

    assert exc_info.value.code == "project_access_denied"
    assert exc_info.value.details == {
        "action": "task:create",
        "project_id": project.project_id,
    }


async def test_get_project_denies_other_users_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    alice = await service.create_user(username="alice", password="secret-123")
    bob = await service.create_user(username="bob", password="secret-456")
    project = await service.create_project(owner_user_id=alice.user_id, name="Project A")

    with pytest.raises(PermissionDeniedError) as exc_info:
        await service.get_project(user_id=bob.user_id, project_id=project.project_id)

    assert exc_info.value.code == "project_access_denied"


async def test_get_project_denies_inactive_project_for_owner(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    alice = await service.create_user(username="alice", password="secret-123")
    project = await service.create_project(owner_user_id=alice.user_id, name="Project A")

    async with connect_db(test_settings.database_path) as db:
        await db.execute(
            "update projects set status = 'archived' where project_id = ?",
            (project.project_id,),
        )

    with pytest.raises(PermissionDeniedError) as exc_info:
        await service.get_project(user_id=alice.user_id, project_id=project.project_id)

    assert exc_info.value.code == "project_access_denied"
    assert exc_info.value.details == {
        "action": "project:get",
        "project_id": project.project_id,
    }


async def test_inactive_user_cannot_create_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    alice = await service.create_user(username="alice", password="secret-123")

    async with connect_db(test_settings.database_path) as db:
        await db.execute(
            "update users set status = 'disabled' where user_id = ?",
            (alice.user_id,),
        )

    with pytest.raises(PermissionDeniedError) as exc_info:
        await service.create_project(owner_user_id=alice.user_id, name="X")

    assert exc_info.value.code == "user_inactive"
    assert exc_info.value.details == {"user_id": alice.user_id}


async def test_duplicate_username_raises_conflict(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    await service.create_user(username="alice", password="secret-123")

    with pytest.raises(ConflictError) as exc_info:
        await service.create_user(username="alice", password="secret-456")

    assert exc_info.value.code == "username_exists"


async def test_wrong_password_raises_permission_denied(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    await service.create_user(username="alice", password="secret-123")

    with pytest.raises(PermissionDeniedError) as exc_info:
        await service.authenticate(username="alice", password="wrong-password")

    assert exc_info.value.code == "invalid_credentials"


async def test_list_projects_for_user_returns_only_owned_active_projects(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    alice = await service.create_user(username="alice", password="secret-123")
    bob = await service.create_user(username="bob", password="secret-456")
    first = await service.create_project(owner_user_id=alice.user_id, name="漫画项目A")
    second = await service.create_project(owner_user_id=alice.user_id, name="漫画项目B")
    await service.create_project(owner_user_id=bob.user_id, name="Bob 项目")

    async with connect_db(test_settings.database_path) as db:
        await db.execute(
            "update projects set status = 'deleted' where project_id = ?",
            (second.project_id,),
        )

    projects = await service.list_projects_for_user(user_id=alice.user_id)

    assert [project.project_id for project in projects] == [first.project_id]
