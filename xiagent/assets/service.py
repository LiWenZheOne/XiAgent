from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from xiagent.assets.local_storage import LocalAssetStorage
from xiagent.assets.models import AssetContent, AssetRecord, AssetSearchResult
from xiagent.core.errors import NotFoundError, ValidationError
from xiagent.core.ids import new_id
from xiagent.core.services import AssetService, UserService
from xiagent.infrastructure.database import connect_db


class SqliteAssetService(AssetService):
    def __init__(
        self,
        *,
        database_path: Path,
        storage_dir: Path,
        user_service: UserService,
    ) -> None:
        self._database_path = database_path
        self._storage = LocalAssetStorage(storage_dir)
        self._user_service = user_service

    async def create_text_asset(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        name: str,
        text: str,
        metadata: dict[str, Any],
    ) -> AssetRecord:
        await self._validate_write_scope(user_id=user_id, scope=scope, project_id=project_id)
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("asset_name_required", "Asset name must not be empty")
        if not text.strip():
            raise ValidationError("asset_text_required", "Text asset content must not be empty")
        size_bytes = len(text.encode("utf-8"))

        asset_id = new_id("asset")
        now = _utc_now()
        metadata_json = _metadata_json(metadata)
        async with connect_db(self._database_path) as db:
            await db.execute(
                """
                insert into assets (
                  asset_id, scope, project_id, asset_type, name, mime_type, content_hash,
                  size_bytes, storage_uri, text_content, metadata_json, created_by,
                  created_at, updated_at, deleted_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    scope,
                    project_id,
                    "text",
                    clean_name,
                    "text/plain",
                    None,
                    size_bytes,
                    None,
                    text,
                    metadata_json,
                    user_id,
                    now,
                    now,
                    None,
                ),
            )
            await _insert_search_entry(
                db,
                asset_id=asset_id,
                scope=scope,
                project_id=project_id,
                search_text=f"{clean_name}\n{text}\n{metadata_json}",
            )

        return AssetRecord(
            asset_id=asset_id,
            scope=scope,
            project_id=project_id,
            asset_type="text",
            name=clean_name,
            mime_type="text/plain",
            content_hash=None,
            size_bytes=size_bytes,
            storage_uri=None,
            text_content=text,
            metadata=dict(metadata),
            created_by=user_id,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    async def import_file_asset(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        file_name: str,
        content_type: str | None,
        content: bytes,
        metadata: dict[str, Any],
    ) -> AssetRecord:
        await self._validate_write_scope(user_id=user_id, scope=scope, project_id=project_id)
        clean_name = file_name.strip()
        if not clean_name:
            raise ValidationError("asset_file_name_required", "File name must not be empty")
        if not content:
            raise ValidationError("asset_content_required", "File content must not be empty")

        (
            content_hash,
            storage_uri,
            size_bytes,
            storage_created,
        ) = self._storage.put_bytes_with_status(file_name=clean_name, content=content)
        asset_id = new_id("asset")
        now = _utc_now()
        metadata_json = _metadata_json(metadata)
        try:
            async with connect_db(self._database_path) as db:
                await db.execute(
                    """
                    insert into assets (
                      asset_id, scope, project_id, asset_type, name, mime_type, content_hash,
                      size_bytes, storage_uri, text_content, metadata_json, created_by,
                      created_at, updated_at, deleted_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        scope,
                        project_id,
                        "file",
                        clean_name,
                        content_type,
                        content_hash,
                        size_bytes,
                        storage_uri,
                        None,
                        metadata_json,
                        user_id,
                        now,
                        now,
                        None,
                    ),
                )
                await _insert_search_entry(
                    db,
                    asset_id=asset_id,
                    scope=scope,
                    project_id=project_id,
                    search_text=f"{clean_name}\n{metadata_json}",
                )
        except Exception:
            if storage_created:
                self._storage.delete_uri(storage_uri)
            raise

        return AssetRecord(
            asset_id=asset_id,
            scope=scope,
            project_id=project_id,
            asset_type="file",
            name=clean_name,
            mime_type=content_type,
            content_hash=content_hash,
            size_bytes=size_bytes,
            storage_uri=storage_uri,
            text_content=None,
            metadata=dict(metadata),
            created_by=user_id,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    async def get_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None = None,
    ) -> AssetRecord:
        async with connect_db(self._database_path) as db:
            row = await _fetch_one(
                db,
                "select * from assets where asset_id = ? and deleted_at is null",
                (asset_id,),
            )

        if row is None:
            raise NotFoundError("asset_not_found", "Asset was not found", {"asset_id": asset_id})

        asset = _asset_from_row(row)
        if asset.scope == "project":
            if project_id is not None and asset.project_id != project_id:
                raise NotFoundError(
                    "asset_not_found",
                    "Asset was not found",
                    {"asset_id": asset_id},
                )
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=asset.project_id or project_id or "",
                action="asset:read",
            )
        return asset

    async def get_asset_content(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None = None,
    ) -> AssetContent:
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id, project_id=project_id)
        if asset.asset_type == "text":
            return AssetContent(
                asset_id=asset.asset_id,
                asset_type=asset.asset_type,
                content_type=asset.mime_type,
                text_content=asset.text_content,
            )
        if asset.storage_uri is None:
            raise NotFoundError(
                "asset_not_found",
                "Asset content was not found",
                {"asset_id": asset_id},
            )
        return AssetContent(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            content_type=asset.mime_type,
            bytes_content=self._storage.read_bytes(asset.storage_uri),
        )

    async def update_asset_metadata(
        self,
        *,
        user_id: str,
        asset_id: str,
        metadata: dict[str, Any],
    ) -> AssetRecord:
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id)
        if asset.scope == "project":
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=asset.project_id or "",
                action="asset:write",
            )
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            await db.execute(
                "update assets set metadata_json = ?, updated_at = ? where asset_id = ?",
                (_metadata_json(metadata), now, asset_id),
            )
            row = await _fetch_one(
                db,
                "select * from assets where asset_id = ? and deleted_at is null",
                (asset_id,),
            )

        if row is None:
            raise NotFoundError("asset_not_found", "Asset was not found", {"asset_id": asset_id})
        return _asset_from_row(row)

    async def delete_asset(self, *, user_id: str, asset_id: str) -> None:
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id)
        if asset.scope == "project":
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=asset.project_id or "",
                action="asset:write",
            )
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            await db.execute(
                "update assets set deleted_at = ?, updated_at = ? where asset_id = ?",
                (now, now, asset_id),
            )

    async def search_assets(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        keyword: str | None = None,
        asset_type: str | None = None,
        mime_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AssetSearchResult:
        await self._validate_search_scope(user_id=user_id, scope=scope, project_id=project_id)
        where, parameters = _search_filter(
            scope=scope,
            project_id=project_id,
            keyword=keyword,
            asset_type=asset_type,
            mime_type=mime_type,
        )
        async with connect_db(self._database_path) as db:
            total_row = await _fetch_one(
                db,
                f"select count(*) as total from assets where {' and '.join(where)}",
                tuple(parameters),
            )
            cursor = await db.execute(
                f"""
                select *
                from assets
                where {' and '.join(where)}
                order by created_at asc, asset_id asc
                limit ? offset ?
                """,
                (*parameters, limit, offset),
            )
            try:
                rows = await cursor.fetchall()
            finally:
                await cursor.close()

        return AssetSearchResult(
            items=[_asset_from_row(row) for row in rows],
            total=int(total_row["total"]) if total_row is not None else 0,
        )

    async def _validate_write_scope(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
    ) -> None:
        if scope == "global":
            if project_id is not None:
                raise _invalid_scope()
            return
        if scope == "project":
            if project_id is None:
                raise _invalid_scope()
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=project_id,
                action="asset:write",
            )
            return
        raise _invalid_scope()

    async def _validate_search_scope(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
    ) -> None:
        if scope == "global":
            if project_id is not None:
                raise _invalid_scope()
            return
        if scope in {"project", "combined"}:
            if project_id is None:
                raise _invalid_scope()
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=project_id,
                action="asset:read",
            )
            return
        raise _invalid_scope()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _metadata_json(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _invalid_scope() -> ValidationError:
    return ValidationError("invalid_asset_scope", "Asset scope and project_id are inconsistent")


def _search_filter(
    *,
    scope: str,
    project_id: str | None,
    keyword: str | None,
    asset_type: str | None,
    mime_type: str | None,
) -> tuple[list[str], list[str]]:
    where = ["deleted_at is null"]
    parameters: list[str] = []
    if scope == "global":
        where.append("scope = ?")
        parameters.append("global")
    elif scope == "project":
        where.append("scope = ?")
        where.append("project_id = ?")
        parameters.extend(["project", project_id or ""])
    else:
        where.append("(scope = ? or (scope = ? and project_id = ?))")
        parameters.extend(["global", "project", project_id or ""])

    if asset_type is not None:
        where.append("asset_type = ?")
        parameters.append(asset_type)
    if mime_type is not None:
        where.append("mime_type = ?")
        parameters.append(mime_type)
    clean_keyword = keyword.strip() if keyword is not None else ""
    if clean_keyword:
        where.append("(name like ? or text_content like ? or metadata_json like ?)")
        pattern = f"%{clean_keyword}%"
        parameters.extend([pattern, pattern, pattern])
    return where, parameters


async def _insert_search_entry(
    db: aiosqlite.Connection,
    *,
    asset_id: str,
    scope: str,
    project_id: str | None,
    search_text: str,
) -> None:
    await db.execute(
        """
        insert into asset_search_fts (asset_id, scope, project_id, search_text)
        values (?, ?, ?, ?)
        """,
        (asset_id, scope, project_id or "", search_text),
    )


async def _fetch_one(
    db: aiosqlite.Connection,
    query: str,
    parameters: tuple[Any, ...],
) -> aiosqlite.Row | None:
    cursor = await db.execute(query, parameters)
    try:
        return await cursor.fetchone()
    finally:
        await cursor.close()


def _asset_from_row(row: aiosqlite.Row) -> AssetRecord:
    return AssetRecord(
        asset_id=row["asset_id"],
        scope=row["scope"],
        project_id=row["project_id"],
        asset_type=row["asset_type"],
        name=row["name"],
        mime_type=row["mime_type"],
        content_hash=row["content_hash"],
        size_bytes=row["size_bytes"],
        storage_uri=row["storage_uri"],
        text_content=row["text_content"],
        metadata=json.loads(row["metadata_json"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
    )
