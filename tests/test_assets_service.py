from __future__ import annotations

import sqlite3

import aiosqlite
import pytest

from xiagent.assets.local_storage import LocalAssetStorage
from xiagent.assets.service import SqliteAssetService
from xiagent.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.migrations import migrate
from xiagent.infrastructure.object_storage.base import ObjectStorageService
from xiagent.infrastructure.object_storage.models import StoredObject
from xiagent.users.service import SqliteUserService


class FakeObjectStorage(ObjectStorageService):
    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        return StoredObject(
            provider="fake",
            bucket="test",
            key=key,
            public_url=f"https://cdn.example.test/{key}",
            content_type=content_type,
            size_bytes=len(content),
            etag="fake-etag",
        )

    async def delete_object(self, *, key: str) -> None:
        return None


class FailingObjectStorage(ObjectStorageService):
    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        raise RuntimeError("upload failed")

    async def delete_object(self, *, key: str) -> None:
        return None


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


async def test_get_project_asset_rejects_mismatched_project_context(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project_a = await users.create_project(owner_user_id=user.user_id, name="project A")
    project_b = await users.create_project(owner_user_id=user.user_id, name="project B")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project_a.project_id,
        name="project A notes",
        text="project A only",
        metadata={},
    )

    with pytest.raises(NotFoundError) as asset_exc_info:
        await assets.get_asset(
            user_id=user.user_id,
            asset_id=asset.asset_id,
            project_id=project_b.project_id,
        )
    with pytest.raises(NotFoundError) as content_exc_info:
        await assets.get_asset_content(
            user_id=user.user_id,
            asset_id=asset.asset_id,
            project_id=project_b.project_id,
        )

    assert asset_exc_info.value.code == "asset_not_found"
    assert content_exc_info.value.code == "asset_not_found"


async def test_import_file_asset_rejects_cross_project_collection_and_tag(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project_a = await users.create_project(owner_user_id=user.user_id, name="project A")
    project_b = await users.create_project(owner_user_id=user.user_id, name="project B")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    collection_b = await assets.create_collection_node(
        user_id=user.user_id,
        scope="project",
        project_id=project_b.project_id,
        parent_id=None,
        name="project B collection",
    )
    tag_b = await assets.create_tag(
        user_id=user.user_id,
        scope="project",
        project_id=project_b.project_id,
        name="project B tag",
    )

    with pytest.raises(ValidationError) as collection_exc_info:
        await assets.import_file_asset(
            user_id=user.user_id,
            scope="project",
            project_id=project_a.project_id,
            file_name="hero.png",
            content_type="image/png",
            content=b"fake image",
            metadata={},
            collection_ids=[collection_b.collection_id],
        )
    with pytest.raises(ValidationError) as tag_exc_info:
        await assets.import_file_asset(
            user_id=user.user_id,
            scope="project",
            project_id=project_a.project_id,
            file_name="hero-tag.png",
            content_type="image/png",
            content=b"fake image",
            metadata={},
            tag_ids=[tag_b.tag_id],
        )

    assert collection_exc_info.value.code == "asset_index_scope_mismatch"
    assert tag_exc_info.value.code == "asset_index_scope_mismatch"


async def test_create_collection_rejects_cross_project_parent(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project_a = await users.create_project(owner_user_id=user.user_id, name="project A")
    project_b = await users.create_project(owner_user_id=user.user_id, name="project B")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    parent_b = await assets.create_collection_node(
        user_id=user.user_id,
        scope="project",
        project_id=project_b.project_id,
        parent_id=None,
        name="project B parent",
    )

    with pytest.raises(ValidationError) as exc_info:
        await assets.create_collection_node(
            user_id=user.user_id,
            scope="project",
            project_id=project_a.project_id,
            parent_id=parent_b.collection_id,
            name="project A child",
        )

    assert exc_info.value.code == "asset_collection_scope_mismatch"


async def test_create_text_asset_preserves_original_text_and_size(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    original_text = "  line one\nline two  \n"

    asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        name="notes",
        text=original_text,
        metadata={},
    )
    content = await assets.get_asset_content(user_id=user.user_id, asset_id=asset.asset_id)

    assert asset.size_bytes == len(original_text.encode("utf-8"))
    assert content.text_content == original_text


def test_local_asset_storage_rejects_path_traversal(tmp_path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    storage = LocalAssetStorage(tmp_path / "assets")

    with pytest.raises(ValidationError) as exc_info:
        storage.read_bytes("../outside.txt")

    assert exc_info.value.code == "invalid_storage_uri"


async def test_import_file_asset_cleans_up_storage_when_db_insert_fails(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )

    with pytest.raises((aiosqlite.IntegrityError, sqlite3.IntegrityError)):
        await assets.import_file_asset(
            user_id="user_missing",
            scope="global",
            project_id=None,
            file_name="orphan.txt",
            content_type="text/plain",
            content=b"orphan content",
            metadata={},
        )

    stored_files = [
        item
        for item in test_settings.asset_storage_dir.rglob("*")
        if item.is_file()
    ]
    assert stored_files == []


async def test_import_file_asset_failure_keeps_existing_deduplicated_file(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    existing = await assets.import_file_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        file_name="existing.txt",
        content_type="text/plain",
        content=b"shared content",
        metadata={},
    )

    with pytest.raises((aiosqlite.IntegrityError, sqlite3.IntegrityError)):
        await assets.import_file_asset(
            user_id="user_missing",
            scope="global",
            project_id=None,
            file_name="failed.txt",
            content_type="text/plain",
            content=b"shared content",
            metadata={},
        )
    content = await assets.get_asset_content(user_id=user.user_id, asset_id=existing.asset_id)

    assert content.bytes_content == b"shared content"


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


async def test_import_image_asset_publishes_public_url_and_indexes_tags(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="asset-publisher", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="Image Project")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
        object_storage=FakeObjectStorage(),
    )
    collection = await assets.create_collection_node(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        parent_id=None,
        name="角色参考",
    )
    tag = await assets.create_tag(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        name="主角",
    )

    asset = await assets.import_file_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        file_name="hero.png",
        content_type="image/png",
        content=b"fake image",
        metadata={},
        publish=True,
        collection_ids=[collection.collection_id],
        tag_ids=[tag.tag_id],
    )
    result = await assets.search_assets(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        tag_ids=[tag.tag_id],
        collection_id=collection.collection_id,
    )

    assert asset.metadata["public_url"].startswith("https://cdn.example.test/")
    assert result.items[0].asset_id == asset.asset_id


async def test_search_assets_by_parent_collection_includes_child_collections(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="asset-tree-search", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="Tree Project")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    parent = await assets.create_collection_node(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        parent_id=None,
        name="角色",
    )
    child = await assets.create_collection_node(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        parent_id=parent.collection_id,
        name="主角",
    )
    asset = await assets.import_file_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        file_name="hero.png",
        content_type="image/png",
        content=b"fake image",
        metadata={},
        collection_ids=[child.collection_id],
    )

    result = await assets.search_assets(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        collection_id=parent.collection_id,
    )

    assert [item.asset_id for item in result.items] == [asset.asset_id]


async def test_search_assets_ignores_collection_index_entries_outside_scope(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="asset-index-scope", password="secret-123")
    project_a = await users.create_project(owner_user_id=user.user_id, name="project A")
    project_b = await users.create_project(owner_user_id=user.user_id, name="project B")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    asset_a = await assets.create_text_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project_a.project_id,
        name="project A asset",
        text="project A content",
        metadata={},
    )
    collection_b = await assets.create_collection_node(
        user_id=user.user_id,
        scope="project",
        project_id=project_b.project_id,
        parent_id=None,
        name="project B collection",
    )
    async with connect_db(test_settings.database_path) as db:
        await db.execute(
            """
            insert into asset_index_entries (
              entry_id, scope, project_id, asset_id, collection_id, tag_id,
              search_text, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "asset_index_cross_project",
                "project",
                project_a.project_id,
                asset_a.asset_id,
                collection_b.collection_id,
                None,
                asset_a.name,
                "2026-05-29T00:00:00+00:00",
                "2026-05-29T00:00:00+00:00",
            ),
        )

    result = await assets.search_assets(
        user_id=user.user_id,
        scope="project",
        project_id=project_a.project_id,
        collection_id=collection_b.collection_id,
    )

    assert result.items == []
    assert result.total == 0


async def test_import_file_asset_cleans_local_file_when_publish_fails(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="publish-failure", password="secret-123")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
        object_storage=FailingObjectStorage(),
    )

    with pytest.raises(RuntimeError, match="upload failed"):
        await assets.import_file_asset(
            user_id=user.user_id,
            scope="global",
            project_id=None,
            file_name="hero.png",
            content_type="image/png",
            content=b"fake image",
            metadata={},
            publish=True,
        )

    stored_files = [item for item in test_settings.asset_storage_dir.rglob("*") if item.is_file()]
    assert stored_files == []
