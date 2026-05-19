from __future__ import annotations

import aiosqlite
import pytest

from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.migrations import migrate


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


async def _insert_user_and_project(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        insert into users (
          user_id, username, password_hash, status, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?)
        """,
        ("user_1", "alice", "hash", "active", "2026-05-19T00:00:00", "2026-05-19T00:00:00"),
    )
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
