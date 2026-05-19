from __future__ import annotations

import aiosqlite

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
