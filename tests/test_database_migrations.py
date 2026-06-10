from __future__ import annotations

import aiosqlite
import pytest

from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.migrations import SCHEMA_SQL, migrate
from xiagent.users.global_project import GLOBAL_PROJECT_ID


async def test_migrate_creates_core_tables(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with aiosqlite.connect(test_settings.database_path) as db:
        cursor = await db.execute(
            "select name from sqlite_master where type='table' and name='users'"
        )
        row = await cursor.fetchone()
    assert row == ("users",)


async def test_migrate_enables_asset_search_fts(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with aiosqlite.connect(test_settings.database_path) as db:
        cursor = await db.execute(
            "select name from sqlite_master where type='table' and name='asset_search_fts'"
        )
        row = await cursor.fetchone()
    assert row == ("asset_search_fts",)


async def test_migrate_normalizes_legacy_global_asset_scope(test_settings) -> None:
    now = "2026-05-19T00:00:00"
    async with connect_db(test_settings.database_path) as db:
        await db.executescript(SCHEMA_SQL)
        await _insert_user(db, user_id="legacy_user")
        await db.execute(
            """
            insert into users (
              user_id, username, password_hash, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?)
            """,
            ("system", "__xiagent_system__", "hash", "system", now, now),
        )
        await db.execute(
            """
            insert into projects (
              project_id, owner_user_id, name, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (GLOBAL_PROJECT_ID, "system", "全局项目", "active", now, now),
        )
        await db.execute(
            """
            insert into assets (
              asset_id, scope, project_id, asset_type, name, metadata_json, created_by,
              created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("asset_legacy_global", "global", None, "text", "角色模板", "{}", "legacy_user", now, now),
        )
        await db.execute(
            """
            insert into asset_tags (
              tag_id, scope, project_id, name, created_by, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            ("tag_legacy_global", "global", None, "角色", "legacy_user", now, now),
        )
        await db.execute(
            """
            insert into asset_index_entries (
              entry_id, scope, project_id, asset_id, tag_id, search_text, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("entry_legacy_global", "global", None, "asset_legacy_global", "tag_legacy_global", "角色模板", now, now),
        )
        await db.execute(
            "insert into asset_search_fts(asset_id, scope, project_id, search_text) values (?, ?, ?, ?)",
            ("asset_legacy_global", "global", "", "角色模板"),
        )

    await migrate(test_settings.database_path)

    async with connect_db(test_settings.database_path) as db:
        assets_count = await _count_rows(db, "assets", "scope = 'global'")
        tags_count = await _count_rows(db, "asset_tags", "scope = 'global'")
        index_count = await _count_rows(db, "asset_index_entries", "scope = 'global'")
        fts_count = await _count_rows(db, "asset_search_fts", "scope = 'global'")
        cursor = await db.execute(
            "select scope, project_id from assets where asset_id = ?",
            ("asset_legacy_global",),
        )
        asset_row = await cursor.fetchone()

    assert assets_count == 0
    assert tags_count == 0
    assert index_count == 0
    assert fts_count == 0
    assert tuple(asset_row) == ("project", GLOBAL_PROJECT_ID)


async def test_project_scoped_asset_requires_existing_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with connect_db(test_settings.database_path) as db:
        await db.execute(
            """
            insert into users (
              user_id, username, password_hash, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?)
            """,
            ("user_1", "alice", "hash", "active", "2026-05-19T00:00:00", "2026-05-19T00:00:00"),
        )

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                insert into assets (
                  asset_id, scope, project_id, asset_type, name, metadata_json, created_by,
                  created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "asset_1",
                    "project",
                    "missing",
                    "text",
                    "Asset",
                    "{}",
                    "user_1",
                    "2026-05-19T00:00:00",
                    "2026-05-19T00:00:00",
                ),
            )


async def test_asset_collection_requires_existing_parent(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with connect_db(test_settings.database_path) as db:
        await _insert_user_and_project(db)

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                insert into asset_collections (
                  collection_id, scope, project_id, parent_id, name, created_by,
                  created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "collection_1",
                    "project",
                    "project_1",
                    "missing",
                    "Collection",
                    "user_1",
                    "2026-05-19T00:00:00",
                    "2026-05-19T00:00:00",
                ),
            )


async def test_asset_collection_requires_existing_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with connect_db(test_settings.database_path) as db:
        await _insert_user(db, user_id="user_collection_project")

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                insert into asset_collections (
                  collection_id, scope, project_id, name, created_by, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "collection_missing_project",
                    "project",
                    "missing_project",
                    "Collection",
                    "user_collection_project",
                    "2026-05-19T00:00:00",
                    "2026-05-19T00:00:00",
                ),
            )


async def test_asset_tag_requires_existing_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with connect_db(test_settings.database_path) as db:
        await _insert_user(db, user_id="user_tag_project")

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                insert into asset_tags (
                  tag_id, scope, project_id, name, created_by, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "tag_missing_project",
                    "project",
                    "missing_project",
                    "Tag",
                    "user_tag_project",
                    "2026-05-19T00:00:00",
                    "2026-05-19T00:00:00",
                ),
            )


async def test_asset_index_entries_require_existing_collection_and_tag(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with connect_db(test_settings.database_path) as db:
        await _insert_user_and_project(db)
        await db.execute(
            """
            insert into assets (
              asset_id, scope, project_id, asset_type, name, metadata_json, created_by,
              created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "asset_1",
                "project",
                "project_1",
                "text",
                "Asset",
                "{}",
                "user_1",
                "2026-05-19T00:00:00",
                "2026-05-19T00:00:00",
            ),
        )

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                insert into asset_index_entries (
                  entry_id, scope, project_id, asset_id, collection_id, search_text,
                  created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "entry_1",
                    "project",
                    "project_1",
                    "asset_1",
                    "missing",
                    "search",
                    "2026-05-19T00:00:00",
                    "2026-05-19T00:00:00",
                ),
            )

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                insert into asset_index_entries (
                  entry_id, scope, project_id, asset_id, tag_id, search_text,
                  created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "entry_2",
                    "project",
                    "project_1",
                    "asset_1",
                    "missing",
                    "search",
                    "2026-05-19T00:00:00",
                    "2026-05-19T00:00:00",
                ),
            )


async def test_asset_index_entry_requires_existing_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with connect_db(test_settings.database_path) as db:
        await _insert_user_and_project(db)
        await _insert_asset(db, asset_id="asset_index_project", project_id="project_1")

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                insert into asset_index_entries (
                  entry_id, scope, project_id, asset_id, search_text, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "entry_missing_project",
                    "project",
                    "missing_project",
                    "asset_index_project",
                    "search",
                    "2026-05-19T00:00:00",
                    "2026-05-19T00:00:00",
                ),
            )


async def test_workflow_template_requires_existing_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with connect_db(test_settings.database_path) as db:
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                insert into workflow_templates (
                  template_id, workflow_id, version, scope, project_id, name, contract_json,
                  status, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "template_missing_project",
                    "workflow_missing_project",
                    "1.0.0",
                    "project",
                    "missing_project",
                    "Workflow",
                    "{}",
                    "active",
                    "2026-05-19T00:00:00",
                    "2026-05-19T00:00:00",
                ),
            )


async def _insert_user(db: aiosqlite.Connection, *, user_id: str = "user_1") -> None:
    await db.execute(
        """
        insert into users (
          user_id, username, password_hash, status, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            user_id,
            "hash",
            "active",
            "2026-05-19T00:00:00",
            "2026-05-19T00:00:00",
        ),
    )


async def _count_rows(db: aiosqlite.Connection, table_name: str, where_sql: str) -> int:
    cursor = await db.execute(f"select count(*) from {table_name} where {where_sql}")
    row = await cursor.fetchone()
    return int(row[0])


async def _insert_user_and_project(db: aiosqlite.Connection) -> None:
    await _insert_user(db)
    await db.execute(
        """
        insert into projects (
          project_id, owner_user_id, name, status, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?)
        """,
        (
            "project_1",
            "user_1",
            "Project",
            "active",
            "2026-05-19T00:00:00",
            "2026-05-19T00:00:00",
        ),
    )


async def _insert_asset(
    db: aiosqlite.Connection,
    *,
    asset_id: str,
    project_id: str,
) -> None:
    await db.execute(
        """
        insert into assets (
          asset_id, scope, project_id, asset_type, name, metadata_json, created_by,
          created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            "project",
            project_id,
            "text",
            "Asset",
            "{}",
            "user_1",
            "2026-05-19T00:00:00",
            "2026-05-19T00:00:00",
        ),
    )
