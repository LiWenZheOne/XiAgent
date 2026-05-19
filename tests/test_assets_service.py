from __future__ import annotations

import pytest

from xiagent.assets.service import SqliteAssetService
from xiagent.core.errors import PermissionDeniedError, ValidationError
from xiagent.infrastructure.migrations import migrate
from xiagent.users.service import SqliteUserService


async def test_create_text_asset_and_search_project_scope(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )

    asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        name="女主设定",
        text="女主是调查记者，冷静、敏锐。",
        metadata={"kind": "character"},
    )
    result = await assets.search_assets(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        keyword="调查记者",
    )

    assert asset.asset_type == "text"
    assert [item.asset_id for item in result.items] == [asset.asset_id]


async def test_import_file_asset_deduplicates_by_hash(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )

    first = await assets.import_file_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        file_name="role.txt",
        content_type="text/plain",
        content=b"shared asset",
        metadata={},
    )
    second = await assets.import_file_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        file_name="role-copy.txt",
        content_type="text/plain",
        content=b"shared asset",
        metadata={},
    )

    assert first.content_hash == second.content_hash
    assert first.storage_uri == second.storage_uri


@pytest.mark.parametrize(
    ("scope", "project_id"),
    [
        ("global", "project-123"),
        ("project", None),
    ],
)
async def test_invalid_asset_scope_raises_validation_error(
    test_settings,
    scope: str,
    project_id: str | None,
) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )

    with pytest.raises(ValidationError) as exc_info:
        await assets.create_text_asset(
            user_id=user.user_id,
            scope=scope,
            project_id=project_id,
            name="素材",
            text="内容",
            metadata={},
        )

    assert exc_info.value.code == "invalid_asset_scope"


async def test_another_user_cannot_create_project_asset(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    owner = await users.create_user(username="alice", password="secret-123")
    other = await users.create_user(username="bob", password="secret-123")
    project = await users.create_project(owner_user_id=owner.user_id, name="漫画项目A")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )

    with pytest.raises(PermissionDeniedError) as exc_info:
        await assets.create_text_asset(
            user_id=other.user_id,
            scope="project",
            project_id=project.project_id,
            name="女主设定",
            text="女主是调查记者。",
            metadata={},
        )

    assert exc_info.value.code == "project_access_denied"


async def test_get_asset_content_returns_text_and_file_content(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )

    text_asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        name="设定",
        text="文字内容",
        metadata={},
    )
    file_asset = await assets.import_file_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        file_name="role.txt",
        content_type="text/plain",
        content=b"file content",
        metadata={},
    )

    text_content = await assets.get_asset_content(
        user_id=user.user_id,
        asset_id=text_asset.asset_id,
    )
    file_content = await assets.get_asset_content(
        user_id=user.user_id,
        asset_id=file_asset.asset_id,
    )

    assert text_content.text_content == "文字内容"
    assert text_content.bytes_content is None
    assert file_content.bytes_content == b"file content"
    assert file_content.text_content is None


async def test_delete_asset_soft_deletes_and_search_excludes_it(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        name="可删除素材",
        text="会被软删除的内容",
        metadata={},
    )

    await assets.delete_asset(user_id=user.user_id, asset_id=asset.asset_id)
    result = await assets.search_assets(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        keyword="软删除",
    )

    assert result.items == []
    assert result.total == 0


async def test_combined_search_returns_global_and_current_project_only(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    other_project = await users.create_project(owner_user_id=user.user_id, name="漫画项目B")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    global_asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        name="通用调查记者素材",
        text="调查记者通用模板",
        metadata={},
    )
    project_asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        name="项目A调查记者素材",
        text="调查记者只属于项目A",
        metadata={},
    )
    await assets.create_text_asset(
        user_id=user.user_id,
        scope="project",
        project_id=other_project.project_id,
        name="项目B调查记者素材",
        text="调查记者只属于项目B",
        metadata={},
    )

    result = await assets.search_assets(
        user_id=user.user_id,
        scope="combined",
        project_id=project.project_id,
        keyword="调查记者",
    )

    assert {item.asset_id for item in result.items} == {
        global_asset.asset_id,
        project_asset.asset_id,
    }
    assert result.total == 2
