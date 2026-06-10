from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from io import BytesIO
import json
from pathlib import Path
import shutil
from typing import Any

import aiosqlite
from PIL import Image, UnidentifiedImageError

from xiagent.assets.local_storage import LocalAssetStorage
from xiagent.assets.models import (
    AssetCollectionRecord,
    AssetContent,
    AssetRecord,
    AssetSearchResult,
    AssetTagRecord,
)
from xiagent.core.errors import ConflictError, NotFoundError, ValidationError
from xiagent.core.ids import new_id
from xiagent.core.services import AssetService, UserService
from xiagent.infrastructure.database import connect_db
from xiagent.users.global_project import GLOBAL_PROJECT_ID


class SqliteAssetService(AssetService):
    def __init__(
        self,
        *,
        database_path: Path,
        storage_dir: Path,
        user_service: UserService,
        object_storage: Any | None = None,
    ) -> None:
        self._database_path = database_path
        self._storage = LocalAssetStorage(storage_dir)
        self._thumbnail_dir = (storage_dir / "_thumbnails").resolve()
        self._user_service = user_service
        self._object_storage = object_storage

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
            await _ensure_asset_name_available(
                db,
                scope=scope,
                project_id=project_id,
                name=clean_name,
            )
            try:
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
            except aiosqlite.IntegrityError as exc:
                _raise_asset_name_conflict_from_integrity(
                    exc,
                    scope=scope,
                    project_id=project_id,
                    name=clean_name,
                )
            await _insert_search_entry(
                db,
                asset_id=asset_id,
                scope=scope,
                project_id=project_id,
                search_text=f"{clean_name}\n{text}\n{metadata_json}",
            )
            await _ensure_episode_metadata_tag_entry(
                db,
                user_id=user_id,
                asset_id=asset_id,
                scope=scope,
                project_id=project_id,
                metadata=metadata,
                search_text=clean_name,
                now=now,
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
        publish: bool = False,
        collection_ids: list[str] | None = None,
        tag_ids: list[str] | None = None,
    ) -> AssetRecord:
        await self._validate_write_scope(user_id=user_id, scope=scope, project_id=project_id)
        clean_name = file_name.strip()
        if not clean_name:
            raise ValidationError("asset_file_name_required", "File name must not be empty")
        if not content:
            raise ValidationError("asset_content_required", "File content must not be empty")

        clean_collection_ids = _clean_string_list(collection_ids)
        clean_tag_ids = _clean_string_list(tag_ids)
        async with connect_db(self._database_path) as db:
            await _ensure_asset_name_available(
                db,
                scope=scope,
                project_id=project_id,
                name=clean_name,
            )
            await _validate_index_targets(
                db,
                scope=scope,
                project_id=project_id,
                collection_ids=clean_collection_ids,
                tag_ids=clean_tag_ids,
            )

        (
            content_hash,
            storage_uri,
            size_bytes,
            storage_created,
        ) = self._storage.put_bytes_with_status(file_name=clean_name, content=content)
        asset_id = new_id("asset")
        now = _utc_now()
        stored_object = None
        clean_metadata = dict(metadata)
        try:
            if publish:
                if self._object_storage is None:
                    raise ValidationError(
                        "object_storage_not_configured",
                        "Object storage must be configured before publishing file assets",
                    )
                stored_object = await self._object_storage.put_object(
                    key=_object_key(storage_uri),
                    content=content,
                    content_type=content_type,
                )
                clean_metadata["public_url"] = stored_object.public_url
                clean_metadata["object_storage"] = asdict(stored_object)

            metadata_json = _metadata_json(clean_metadata)
            async with connect_db(self._database_path) as db:
                try:
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
                except aiosqlite.IntegrityError as exc:
                    _raise_asset_name_conflict_from_integrity(
                        exc,
                        scope=scope,
                        project_id=project_id,
                        name=clean_name,
                    )
                await _insert_search_entry(
                    db,
                    asset_id=asset_id,
                    scope=scope,
                    project_id=project_id,
                    search_text=f"{clean_name}\n{metadata_json}",
                )
                for collection_id in clean_collection_ids:
                    await _insert_index_entry(
                        db,
                        asset_id=asset_id,
                        scope=scope,
                        project_id=project_id,
                        collection_id=collection_id,
                        tag_id=None,
                        search_text=clean_name,
                        now=now,
                    )
                for tag_id in clean_tag_ids:
                    await _insert_index_entry(
                        db,
                        asset_id=asset_id,
                        scope=scope,
                        project_id=project_id,
                        collection_id=None,
                        tag_id=tag_id,
                        search_text=clean_name,
                        now=now,
                    )
        except Exception:
            if stored_object is not None:
                await self._object_storage.delete_object(key=stored_object.key)
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
            metadata=clean_metadata,
            created_by=user_id,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    async def copy_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        target_scope: str,
        target_project_id: str | None,
        source_project_id: str | None = None,
        copy_tags: bool = True,
    ) -> AssetRecord:
        if target_scope != "project":
            raise ValidationError(
                "asset_transfer_target_project_required",
                "资产复制目标必须是项目资产库。",
                {"target_scope": target_scope, "target_project_id": target_project_id},
            )
        if not target_project_id:
            raise ValidationError(
                "asset_transfer_target_project_required",
                "资产复制需要选择目标项目。",
            )

        source = await self.get_asset(user_id=user_id, asset_id=asset_id, project_id=source_project_id)
        await self._validate_write_scope(user_id=user_id, scope=target_scope, project_id=target_project_id)
        content = await self.get_asset_content(
            user_id=user_id,
            asset_id=source.asset_id,
            project_id=source_project_id,
        )
        metadata = _metadata_without_publish_fields(source.metadata)
        metadata["copied_from_asset_id"] = source.asset_id
        metadata["copied_from_scope"] = source.scope
        if source.project_id:
            metadata["copied_from_project_id"] = source.project_id

        if source.asset_type == "text":
            copied = await self.create_text_asset(
                user_id=user_id,
                scope=target_scope,
                project_id=target_project_id,
                name=source.name,
                text=content.text_content or source.text_content or "",
                metadata=metadata,
            )
        else:
            if content.bytes_content is None:
                raise NotFoundError(
                    "asset_content_not_found",
                    "Asset content was not found",
                    {"asset_id": source.asset_id},
                )
            copied = await self.import_file_asset(
                user_id=user_id,
                scope=target_scope,
                project_id=target_project_id,
                file_name=source.name,
                content_type=content.content_type or source.mime_type,
                content=content.bytes_content,
                metadata=metadata,
                publish=False,
            )

        if copy_tags:
            await self._copy_asset_tags(
                user_id=user_id,
                source_asset_id=source.asset_id,
                target_asset_id=copied.asset_id,
                target_scope=target_scope,
                target_project_id=target_project_id,
            )
        return copied

    async def move_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        target_scope: str,
        target_project_id: str | None,
        source_project_id: str | None = None,
        copy_tags: bool = True,
    ) -> AssetRecord:
        source = await self.get_asset(user_id=user_id, asset_id=asset_id, project_id=source_project_id)
        if source.scope != "project":
            raise ValidationError(
                "asset_global_move_not_supported",
                "全局资产不能转移到项目；如需在项目中使用，请复制全局资产。",
                {"asset_id": source.asset_id, "scope": source.scope},
            )
        copied = await self.copy_asset(
            user_id=user_id,
            asset_id=source.asset_id,
            target_scope=target_scope,
            target_project_id=target_project_id,
            source_project_id=source_project_id,
            copy_tags=copy_tags,
        )
        await self.delete_asset(user_id=user_id, asset_id=source.asset_id)
        return copied

    async def _copy_asset_tags(
        self,
        *,
        user_id: str,
        source_asset_id: str,
        target_asset_id: str,
        target_scope: str,
        target_project_id: str | None,
    ) -> None:
        source_tags = await self.list_asset_tags(user_id=user_id, asset_id=source_asset_id)
        if not source_tags:
            return
        target_tags = await self.list_tags(user_id=user_id, scope=target_scope, project_id=target_project_id)
        target_by_name = {tag.name: tag for tag in target_tags}
        for source_tag in source_tags:
            target_tag = target_by_name.get(source_tag.name)
            if target_tag is None:
                target_tag = await self.create_tag(
                    user_id=user_id,
                    scope=target_scope,
                    project_id=target_project_id,
                    name=source_tag.name,
                    description=source_tag.description,
                )
                target_by_name[target_tag.name] = target_tag
            await self.attach_asset_tag(user_id=user_id, asset_id=target_asset_id, tag_id=target_tag.tag_id)

    async def create_collection_node(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        parent_id: str | None,
        name: str,
        description: str | None = None,
    ) -> AssetCollectionRecord:
        await self._validate_write_scope(user_id=user_id, scope=scope, project_id=project_id)
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError(
                "asset_collection_name_required",
                "Asset collection name must not be empty",
            )
        collection_id = new_id("collection")
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            if parent_id is not None:
                await _validate_collection_scope(
                    db,
                    collection_id=parent_id,
                    scope=scope,
                    project_id=project_id,
                    mismatch_code="asset_collection_scope_mismatch",
                )
            await db.execute(
                """
                insert into asset_collections (
                  collection_id, scope, project_id, parent_id, name, description,
                  sort_order, created_by, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    collection_id,
                    scope,
                    project_id,
                    parent_id,
                    clean_name,
                    description,
                    0,
                    user_id,
                    now,
                    now,
                ),
            )
            row = await _fetch_one(
                db,
                "select * from asset_collections where collection_id = ?",
                (collection_id,),
            )
        assert row is not None
        return _collection_from_row(row)

    async def list_collection_nodes(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
    ) -> list[AssetCollectionRecord]:
        await self._validate_search_scope(user_id=user_id, scope=scope, project_id=project_id)
        where, parameters = _scope_filter(scope=scope, project_id=project_id)
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                f"""
                select *
                from asset_collections
                where {' and '.join(where)}
                order by sort_order asc, created_at asc, collection_id asc
                """,
                tuple(parameters),
            )
            try:
                rows = await cursor.fetchall()
            finally:
                await cursor.close()
        return [_collection_from_row(row) for row in rows]

    async def update_collection_node(
        self,
        *,
        user_id: str,
        collection_id: str,
        name: str,
        description: str | None = None,
    ) -> AssetCollectionRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError(
                "asset_collection_name_required",
                "Asset collection name must not be empty",
            )
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            existing = await _fetch_one(
                db,
                "select * from asset_collections where collection_id = ?",
                (collection_id,),
            )
            if existing is None:
                raise NotFoundError(
                    "asset_collection_not_found",
                    "Asset collection was not found",
                    {"collection_id": collection_id},
                )
            await self._validate_write_scope(
                user_id=user_id,
                scope=existing["scope"],
                project_id=existing["project_id"],
            )
            await db.execute(
                """
                update asset_collections
                set name = ?, description = ?, updated_at = ?
                where collection_id = ?
                """,
                (clean_name, description, now, collection_id),
            )
            row = await _fetch_one(
                db,
                "select * from asset_collections where collection_id = ?",
                (collection_id,),
            )
        assert row is not None
        return _collection_from_row(row)

    async def delete_collection_node(self, *, user_id: str, collection_id: str) -> None:
        async with connect_db(self._database_path) as db:
            existing = await _fetch_one(
                db,
                "select * from asset_collections where collection_id = ?",
                (collection_id,),
            )
            if existing is None:
                raise NotFoundError(
                    "asset_collection_not_found",
                    "Asset collection was not found",
                    {"collection_id": collection_id},
                )
            await self._validate_write_scope(
                user_id=user_id,
                scope=existing["scope"],
                project_id=existing["project_id"],
            )
            cursor = await db.execute(
                """
                with recursive collection_tree(collection_id, depth) as (
                  select collection_id, 0
                  from asset_collections
                  where collection_id = ?
                  union all
                  select child.collection_id, parent.depth + 1
                  from asset_collections child
                  join collection_tree parent on child.parent_id = parent.collection_id
                )
                select collection_id
                from collection_tree
                order by depth desc
                """,
                (collection_id,),
            )
            try:
                rows = await cursor.fetchall()
            finally:
                await cursor.close()
            collection_ids = [row["collection_id"] for row in rows]
            if not collection_ids:
                return
            placeholders = ", ".join("?" for _ in collection_ids)
            await db.execute(
                f"delete from asset_index_entries where collection_id in ({placeholders})",
                tuple(collection_ids),
            )
            for child_collection_id in collection_ids:
                await db.execute(
                    "delete from asset_collections where collection_id = ?",
                    (child_collection_id,),
                )

    async def create_tag(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        name: str,
        description: str | None = None,
    ) -> AssetTagRecord:
        await self._validate_write_scope(user_id=user_id, scope=scope, project_id=project_id)
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("asset_tag_name_required", "Asset tag name must not be empty")
        tag_id = new_id("tag")
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            await _ensure_asset_tag_name_available(
                db,
                scope=scope,
                project_id=project_id,
                name=clean_name,
            )
            try:
                await db.execute(
                    """
                    insert into asset_tags (
                      tag_id, scope, project_id, name, description, created_by, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tag_id, scope, project_id, clean_name, description, user_id, now, now),
                )
            except aiosqlite.IntegrityError as exc:
                _raise_asset_tag_name_conflict_from_integrity(
                    exc,
                    scope=scope,
                    project_id=project_id,
                    name=clean_name,
                )
            row = await _fetch_one(db, "select * from asset_tags where tag_id = ?", (tag_id,))
        assert row is not None
        return _tag_from_row(row)

    async def list_tags(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
    ) -> list[AssetTagRecord]:
        await self._validate_search_scope(user_id=user_id, scope=scope, project_id=project_id)
        where, parameters = _qualified_scope_filter("tag", scope=scope, project_id=project_id)
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                f"""
                select tag.*, count(distinct idx.asset_id) as asset_count
                from asset_tags tag
                left join asset_index_entries idx on idx.tag_id = tag.tag_id
                where {' and '.join(where)}
                group by tag.tag_id
                order by tag.created_at asc, tag.tag_id asc
                """,
                tuple(parameters),
            )
            try:
                rows = await cursor.fetchall()
            finally:
                await cursor.close()
        return [_tag_from_row(row) for row in rows]

    async def update_tag(
        self,
        *,
        user_id: str,
        tag_id: str,
        name: str,
        description: str | None = None,
    ) -> AssetTagRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("asset_tag_name_required", "Asset tag name must not be empty")
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            existing = await _fetch_one(
                db,
                "select * from asset_tags where tag_id = ?",
                (tag_id,),
            )
            if existing is None:
                raise NotFoundError("asset_tag_not_found", "Asset tag was not found", {"tag_id": tag_id})
            await self._validate_write_scope(
                user_id=user_id,
                scope=existing["scope"],
                project_id=existing["project_id"],
            )
            await _ensure_asset_tag_name_available(
                db,
                scope=existing["scope"],
                project_id=existing["project_id"],
                name=clean_name,
                exclude_tag_id=tag_id,
            )
            try:
                await db.execute(
                    """
                    update asset_tags
                    set name = ?, description = ?, updated_at = ?
                    where tag_id = ?
                    """,
                    (clean_name, description, now, tag_id),
                )
            except aiosqlite.IntegrityError as exc:
                _raise_asset_tag_name_conflict_from_integrity(
                    exc,
                    scope=existing["scope"],
                    project_id=existing["project_id"],
                    name=clean_name,
                )
            row = await _fetch_one(db, "select * from asset_tags where tag_id = ?", (tag_id,))
        assert row is not None
        return _tag_from_row(row)

    async def delete_tag(self, *, user_id: str, tag_id: str) -> None:
        async with connect_db(self._database_path) as db:
            existing = await _fetch_one(
                db,
                "select * from asset_tags where tag_id = ?",
                (tag_id,),
            )
            if existing is None:
                raise NotFoundError("asset_tag_not_found", "Asset tag was not found", {"tag_id": tag_id})
            await self._validate_write_scope(
                user_id=user_id,
                scope=existing["scope"],
                project_id=existing["project_id"],
            )
            usage = await _fetch_one(
                db,
                "select count(distinct asset_id) as asset_count from asset_index_entries where tag_id = ?",
                (tag_id,),
            )
            asset_count = int(usage["asset_count"]) if usage is not None else 0
            if asset_count:
                raise ValidationError(
                    "asset_tag_not_empty",
                    "Asset tag is still assigned to assets",
                    {"tag_id": tag_id, "asset_count": asset_count},
                )
            await db.execute("delete from asset_tags where tag_id = ?", (tag_id,))

    async def list_asset_tags(
        self,
        *,
        user_id: str,
        asset_id: str,
    ) -> list[AssetTagRecord]:
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id)
        async with connect_db(self._database_path) as db:
            rows = await _fetch_asset_tag_rows(db, asset_id=asset.asset_id)
        return [_tag_from_row(row) for row in rows]

    async def attach_asset_tag(
        self,
        *,
        user_id: str,
        asset_id: str,
        tag_id: str,
    ) -> list[AssetTagRecord]:
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id)
        if asset.scope == "project":
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=asset.project_id or "",
                action="asset:write",
            )
        async with connect_db(self._database_path) as db:
            await _validate_tag_scope(
                db,
                tag_id=tag_id,
                scope=asset.scope,
                project_id=asset.project_id,
            )
            existing = await _fetch_one(
                db,
                "select entry_id from asset_index_entries where asset_id = ? and tag_id = ?",
                (asset.asset_id, tag_id),
            )
            if existing is None:
                await _insert_index_entry(
                    db,
                    asset_id=asset.asset_id,
                    scope=asset.scope,
                    project_id=asset.project_id,
                    collection_id=None,
                    tag_id=tag_id,
                    search_text=asset.name,
                    now=_utc_now(),
                )
            rows = await _fetch_asset_tag_rows(db, asset_id=asset.asset_id)
        return [_tag_from_row(row) for row in rows]

    async def detach_asset_tag(
        self,
        *,
        user_id: str,
        asset_id: str,
        tag_id: str,
    ) -> list[AssetTagRecord]:
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id)
        if asset.scope == "project":
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=asset.project_id or "",
                action="asset:write",
            )
        async with connect_db(self._database_path) as db:
            await _validate_tag_scope(
                db,
                tag_id=tag_id,
                scope=asset.scope,
                project_id=asset.project_id,
            )
            await db.execute(
                "delete from asset_index_entries where asset_id = ? and tag_id = ?",
                (asset.asset_id, tag_id),
            )
            rows = await _fetch_asset_tag_rows(db, asset_id=asset.asset_id)
        return [_tag_from_row(row) for row in rows]

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

    async def get_asset_thumbnail(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None = None,
        size: int = 256,
    ) -> AssetContent:
        target_size = _thumbnail_size(size)
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id, project_id=project_id)
        if not asset.mime_type or not asset.mime_type.startswith("image/"):
            raise ValidationError(
                "asset_thumbnail_unsupported",
                "Only image assets can have thumbnails",
                {"asset_id": asset_id, "mime_type": asset.mime_type},
            )
        if asset.storage_uri is None or asset.content_hash is None:
            raise NotFoundError(
                "asset_not_found",
                "Asset content was not found",
                {"asset_id": asset_id},
            )

        cache_path = self._thumbnail_path(
            asset_id=asset.asset_id,
            content_hash=asset.content_hash,
            size=target_size,
        )
        if cache_path.exists():
            return AssetContent(
                asset_id=asset.asset_id,
                asset_type=asset.asset_type,
                content_type="image/png",
                bytes_content=cache_path.read_bytes(),
                cache_hit=True,
            )

        source = self._storage.read_bytes(asset.storage_uri)
        thumbnail = _make_png_thumbnail(source, size=target_size)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(thumbnail)
        return AssetContent(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            content_type="image/png",
            bytes_content=thumbnail,
            cache_hit=False,
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
            await _ensure_episode_metadata_tag_entry(
                db,
                user_id=user_id,
                asset_id=asset_id,
                scope=asset.scope,
                project_id=asset.project_id,
                metadata=metadata,
                search_text=asset.name,
                now=now,
            )
            row = await _fetch_one(
                db,
                "select * from assets where asset_id = ? and deleted_at is null",
                (asset_id,),
            )

        if row is None:
            raise NotFoundError("asset_not_found", "Asset was not found", {"asset_id": asset_id})
        return _asset_from_row(row)

    async def update_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("asset_name_required", "Asset name must not be empty")
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id)
        if asset.scope == "project":
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=asset.project_id or "",
                action="asset:write",
            )
        now = _utc_now()
        next_metadata = dict(asset.metadata)
        if metadata is not None:
            next_metadata = dict(metadata)
        metadata_json = _metadata_json(next_metadata)
        search_text = f"{clean_name}\n{asset.text_content or ''}\n{metadata_json}"
        async with connect_db(self._database_path) as db:
            await _ensure_asset_name_available(
                db,
                scope=asset.scope,
                project_id=asset.project_id,
                name=clean_name,
                exclude_asset_id=asset_id,
            )
            try:
                await db.execute(
                    "update assets set name = ?, metadata_json = ?, updated_at = ? where asset_id = ?",
                    (clean_name, metadata_json, now, asset_id),
                )
            except aiosqlite.IntegrityError as exc:
                _raise_asset_name_conflict_from_integrity(
                    exc,
                    scope=asset.scope,
                    project_id=asset.project_id,
                    name=clean_name,
                )
            await db.execute(
                "update asset_search_fts set search_text = ? where asset_id = ?",
                (search_text, asset_id),
            )
            await db.execute(
                "update asset_index_entries set search_text = ?, updated_at = ? where asset_id = ?",
                (clean_name, now, asset_id),
            )
            await _ensure_episode_metadata_tag_entry(
                db,
                user_id=user_id,
                asset_id=asset_id,
                scope=asset.scope,
                project_id=asset.project_id,
                metadata=next_metadata,
                search_text=clean_name,
                now=now,
            )
            row = await _fetch_one(
                db,
                "select * from assets where asset_id = ? and deleted_at is null",
                (asset_id,),
            )

        if row is None:
            raise NotFoundError("asset_not_found", "Asset was not found", {"asset_id": asset_id})
        return _asset_from_row(row)

    async def update_text_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        name: str,
        text: str,
        metadata: dict[str, Any],
    ) -> AssetRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("asset_name_required", "Asset name must not be empty")
        if not text.strip():
            raise ValidationError("asset_text_required", "Text asset content must not be empty")
        asset = await self.get_asset(user_id=user_id, asset_id=asset_id)
        if asset.asset_type != "text":
            raise ValidationError("asset_not_text", "Only text assets can be updated with text content")
        if asset.scope == "project":
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=asset.project_id or "",
                action="asset:write",
            )
        size_bytes = len(text.encode("utf-8"))
        now = _utc_now()
        metadata_json = _metadata_json(metadata)
        search_text = f"{clean_name}\n{text}\n{metadata_json}"
        async with connect_db(self._database_path) as db:
            await _ensure_asset_name_available(
                db,
                scope=asset.scope,
                project_id=asset.project_id,
                name=clean_name,
                exclude_asset_id=asset_id,
            )
            try:
                await db.execute(
                    """
                    update assets
                    set name = ?, text_content = ?, size_bytes = ?, metadata_json = ?, updated_at = ?
                    where asset_id = ? and asset_type = 'text' and deleted_at is null
                    """,
                    (clean_name, text, size_bytes, metadata_json, now, asset_id),
                )
            except aiosqlite.IntegrityError as exc:
                _raise_asset_name_conflict_from_integrity(
                    exc,
                    scope=asset.scope,
                    project_id=asset.project_id,
                    name=clean_name,
                )
            await db.execute(
                "update asset_search_fts set search_text = ? where asset_id = ?",
                (search_text, asset_id),
            )
            await db.execute(
                "update asset_index_entries set search_text = ?, updated_at = ? where asset_id = ?",
                (clean_name, now, asset_id),
            )
            await _ensure_episode_metadata_tag_entry(
                db,
                user_id=user_id,
                asset_id=asset_id,
                scope=asset.scope,
                project_id=asset.project_id,
                metadata=metadata,
                search_text=clean_name,
                now=now,
            )
            row = await _fetch_one(
                db,
                "select * from assets where asset_id = ? and deleted_at is null",
                (asset_id,),
            )

        if row is None:
            raise NotFoundError("asset_not_found", "Asset was not found", {"asset_id": asset_id})
        return _asset_from_row(row)

    async def replace_asset_file(
        self,
        *,
        user_id: str,
        asset_id: str,
        file_name: str,
        content_type: str | None,
        content: bytes,
    ) -> AssetRecord:
        clean_name = file_name.strip()
        if not clean_name:
            raise ValidationError("asset_file_name_required", "File name must not be empty")
        if not content:
            raise ValidationError("asset_content_required", "File content must not be empty")

        asset = await self.get_asset(user_id=user_id, asset_id=asset_id)
        if asset.asset_type != "file":
            raise ValidationError(
                "asset_file_replace_unsupported",
                "Only file assets can replace file content",
                {"asset_id": asset_id, "asset_type": asset.asset_type},
            )
        if asset.scope == "project":
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=asset.project_id or "",
                action="asset:write",
            )

        (
            content_hash,
            storage_uri,
            size_bytes,
            _storage_created,
        ) = self._storage.put_bytes_with_status(file_name=clean_name, content=content)
        now = _utc_now()
        next_metadata = dict(asset.metadata)
        stored_object = None
        should_publish = "public_url" in next_metadata or "object_storage" in next_metadata
        if should_publish and self._object_storage is not None:
            stored_object = await self._object_storage.put_object(
                key=_object_key(storage_uri),
                content=content,
                content_type=content_type,
            )
            next_metadata["public_url"] = stored_object.public_url
            next_metadata["object_storage"] = asdict(stored_object)
        metadata_json = _metadata_json(next_metadata)
        search_text = f"{asset.name}\n{metadata_json}"
        async with connect_db(self._database_path) as db:
            await db.execute(
                """
                update assets
                set mime_type = ?, content_hash = ?, size_bytes = ?, storage_uri = ?,
                    metadata_json = ?, updated_at = ?
                where asset_id = ?
                """,
                (
                    content_type,
                    content_hash,
                    size_bytes,
                    storage_uri,
                    metadata_json,
                    now,
                    asset_id,
                ),
            )
            await db.execute(
                "update asset_search_fts set search_text = ? where asset_id = ?",
                (search_text, asset_id),
            )
            row = await _fetch_one(
                db,
                "select * from assets where asset_id = ? and deleted_at is null",
                (asset_id,),
            )

        if row is None:
            raise NotFoundError("asset_not_found", "Asset was not found", {"asset_id": asset_id})
        self._clear_asset_thumbnail_cache(asset_id)
        return _asset_from_row(row)

    def _thumbnail_path(self, *, asset_id: str, content_hash: str, size: int) -> Path:
        safe_asset_id = _safe_cache_segment(asset_id)
        safe_hash = _safe_cache_segment(content_hash)
        target = (self._thumbnail_dir / safe_asset_id / f"{safe_hash}-{size}.png").resolve()
        if not target.is_relative_to(self._thumbnail_dir):
            raise ValidationError(
                "invalid_thumbnail_cache_path",
                "Thumbnail cache path must stay inside asset storage root",
            )
        return target

    def _clear_asset_thumbnail_cache(self, asset_id: str) -> None:
        target = (self._thumbnail_dir / _safe_cache_segment(asset_id)).resolve()
        if not target.is_relative_to(self._thumbnail_dir):
            raise ValidationError(
                "invalid_thumbnail_cache_path",
                "Thumbnail cache path must stay inside asset storage root",
            )
        if target.exists():
            shutil.rmtree(target)

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
        names: list[str] | None = None,
        tag_ids: list[str] | None = None,
        tag_names: list[str] | None = None,
        collection_id: str | None = None,
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
            names=names,
            tag_ids=tag_ids,
            tag_names=tag_names,
            collection_id=collection_id,
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


def _metadata_without_publish_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    copied = dict(metadata)
    copied.pop("public_url", None)
    copied.pop("object_storage", None)
    return copied


def _invalid_scope() -> ValidationError:
    return ValidationError("invalid_asset_scope", "Asset scope and project_id are inconsistent")


def _search_filter(
    *,
    scope: str,
    project_id: str | None,
    keyword: str | None,
    asset_type: str | None,
    mime_type: str | None,
    names: list[str] | None,
    tag_ids: list[str] | None,
    tag_names: list[str] | None,
    collection_id: str | None,
) -> tuple[list[str], list[str]]:
    scope_where, parameters = _scope_filter(scope=scope, project_id=project_id)
    where = ["deleted_at is null", *scope_where]

    if asset_type is not None:
        where.append("asset_type = ?")
        parameters.append(asset_type)
    if mime_type is not None:
        if mime_type.endswith("/*"):
            where.append("mime_type like ?")
            parameters.append(f"{mime_type[:-1]}%")
        else:
            where.append("mime_type = ?")
            parameters.append(mime_type)
    clean_keyword = keyword.strip() if keyword is not None else ""
    if clean_keyword:
        where.append("(name like ? or text_content like ? or metadata_json like ?)")
        pattern = f"%{clean_keyword}%"
        parameters.extend([pattern, pattern, pattern])
    clean_names = _clean_string_list(names)
    if clean_names:
        placeholders = ", ".join("?" for _ in clean_names)
        where.append(f"name in ({placeholders})")
        parameters.extend(clean_names)
    clean_tag_ids = _clean_string_list(tag_ids)
    if clean_tag_ids:
        placeholders = ", ".join("?" for _ in clean_tag_ids)
        index_where, index_parameters = _qualified_scope_filter(
            "idx",
            scope=scope,
            project_id=project_id,
        )
        tag_where, tag_parameters = _qualified_scope_filter(
            "tag",
            scope=scope,
            project_id=project_id,
        )
        where.append(
            "asset_id in ("
            "select idx.asset_id from asset_index_entries idx "
            "join asset_tags tag on tag.tag_id = idx.tag_id "
            f"where idx.tag_id in ({placeholders}) "
            f"and {' and '.join(index_where)} "
            f"and {' and '.join(tag_where)} "
            "group by idx.asset_id having count(distinct idx.tag_id) = ?"
            ")"
        )
        parameters.extend(clean_tag_ids)
        parameters.extend(index_parameters)
        parameters.extend(tag_parameters)
        parameters.append(len(clean_tag_ids))
    clean_tag_names = _clean_string_list(tag_names)
    if clean_tag_names:
        placeholders = ", ".join("?" for _ in clean_tag_names)
        index_where, index_parameters = _qualified_scope_filter(
            "idx",
            scope=scope,
            project_id=project_id,
        )
        tag_where, tag_parameters = _qualified_scope_filter(
            "tag",
            scope=scope,
            project_id=project_id,
        )
        where.append(
            "asset_id in ("
            "select idx.asset_id from asset_index_entries idx "
            "join asset_tags tag on tag.tag_id = idx.tag_id "
            f"where tag.name in ({placeholders}) "
            f"and {' and '.join(index_where)} "
            f"and {' and '.join(tag_where)} "
            "group by idx.asset_id having count(distinct tag.name) = ?"
            ")"
        )
        parameters.extend(clean_tag_names)
        parameters.extend(index_parameters)
        parameters.extend(tag_parameters)
        parameters.append(len(set(clean_tag_names)))
    if collection_id is not None and collection_id.strip():
        start_where, start_parameters = _qualified_scope_filter(
            "start",
            scope=scope,
            project_id=project_id,
        )
        child_where, child_parameters = _qualified_scope_filter(
            "child",
            scope=scope,
            project_id=project_id,
        )
        index_where, index_parameters = _qualified_scope_filter(
            "idx",
            scope=scope,
            project_id=project_id,
        )
        where.append(
            "asset_id in ("
            "with recursive collection_tree(collection_id) as ("
            "select start.collection_id from asset_collections start "
            f"where start.collection_id = ? and {' and '.join(start_where)} "
            "union all "
            "select child.collection_id from asset_collections child "
            "join collection_tree parent on child.parent_id = parent.collection_id "
            f"where {' and '.join(child_where)}"
            ") "
            "select idx.asset_id from asset_index_entries idx "
            f"where idx.collection_id in (select collection_id from collection_tree) "
            f"and {' and '.join(index_where)}"
            ")"
        )
        parameters.append(collection_id.strip())
        parameters.extend(start_parameters)
        parameters.extend(child_parameters)
        parameters.extend(index_parameters)
    return where, parameters


def _scope_filter(*, scope: str, project_id: str | None) -> tuple[list[str], list[str]]:
    if scope == "project":
        return ["scope = ?", "project_id = ?"], ["project", project_id or ""]
    return ["scope = ?", "project_id in (?, ?)"], ["project", GLOBAL_PROJECT_ID, project_id or ""]


def _qualified_scope_filter(
    alias: str,
    *,
    scope: str,
    project_id: str | None,
) -> tuple[list[str], list[str]]:
    if scope == "project":
        return [f"{alias}.scope = ?", f"{alias}.project_id = ?"], ["project", project_id or ""]
    return [f"{alias}.scope = ?", f"{alias}.project_id in (?, ?)"], ["project", GLOBAL_PROJECT_ID, project_id or ""]


async def _validate_index_targets(
    db: aiosqlite.Connection,
    *,
    scope: str,
    project_id: str | None,
    collection_ids: list[str],
    tag_ids: list[str],
) -> None:
    for collection_id in collection_ids:
        await _validate_collection_scope(
            db,
            collection_id=collection_id,
            scope=scope,
            project_id=project_id,
            mismatch_code="asset_index_scope_mismatch",
        )
    for tag_id in tag_ids:
        await _validate_tag_scope(
            db,
            tag_id=tag_id,
            scope=scope,
            project_id=project_id,
        )


async def _ensure_asset_name_available(
    db: aiosqlite.Connection,
    *,
    scope: str,
    project_id: str | None,
    name: str,
    exclude_asset_id: str | None = None,
) -> None:
    query = """
        select asset_id
        from assets
        where scope = ? and project_id is ? and name = ? and deleted_at is null
    """
    parameters: list[Any] = [scope, project_id, name]
    if exclude_asset_id:
        query += " and asset_id != ?"
        parameters.append(exclude_asset_id)
    query += " limit 1"
    existing = await _fetch_one(db, query, tuple(parameters))
    if existing is None:
        return
    raise ConflictError(
        "asset_name_conflict",
        "同一资产库中已存在同名资产。",
        {"scope": scope, "project_id": project_id, "name": name},
    )


def _raise_asset_name_conflict_from_integrity(
    exc: aiosqlite.IntegrityError,
    *,
    scope: str,
    project_id: str | None,
    name: str,
) -> None:
    if "idx_assets_live_scope_project_name" in str(exc):
        raise ConflictError(
            "asset_name_conflict",
            "同一资产库中已存在同名资产。",
            {"scope": scope, "project_id": project_id, "name": name},
        ) from exc
    raise exc


async def _ensure_asset_tag_name_available(
    db: aiosqlite.Connection,
    *,
    scope: str,
    project_id: str | None,
    name: str,
    exclude_tag_id: str | None = None,
) -> None:
    query = """
        select tag_id
        from asset_tags
        where scope = ? and project_id is ? and name = ?
    """
    parameters: list[Any] = [scope, project_id, name]
    if exclude_tag_id:
        query += " and tag_id != ?"
        parameters.append(exclude_tag_id)
    query += " limit 1"
    existing = await _fetch_one(db, query, tuple(parameters))
    if existing is None:
        return
    raise ConflictError(
        "asset_tag_name_conflict",
        "同一资产库中已存在同名标签。",
        {"scope": scope, "project_id": project_id, "name": name},
    )


def _raise_asset_tag_name_conflict_from_integrity(
    exc: aiosqlite.IntegrityError,
    *,
    scope: str,
    project_id: str | None,
    name: str,
) -> None:
    if "idx_asset_tags_scope_project_name" in str(exc):
        raise ConflictError(
            "asset_tag_name_conflict",
            "同一资产库中已存在同名标签。",
            {"scope": scope, "project_id": project_id, "name": name},
        ) from exc
    raise exc


async def _validate_collection_scope(
    db: aiosqlite.Connection,
    *,
    collection_id: str,
    scope: str,
    project_id: str | None,
    mismatch_code: str,
) -> None:
    row = await _fetch_one(
        db,
        "select scope, project_id from asset_collections where collection_id = ?",
        (collection_id,),
    )
    if row is None:
        raise NotFoundError(
            "asset_collection_not_found",
            "Asset collection was not found",
            {"collection_id": collection_id},
        )
    if not _same_scope(row, scope=scope, project_id=project_id):
        raise ValidationError(
            mismatch_code,
            "Asset collection scope does not match asset scope",
            {"collection_id": collection_id, "scope": scope, "project_id": project_id},
        )


async def _validate_tag_scope(
    db: aiosqlite.Connection,
    *,
    tag_id: str,
    scope: str,
    project_id: str | None,
) -> None:
    row = await _fetch_one(
        db,
        "select scope, project_id from asset_tags where tag_id = ?",
        (tag_id,),
    )
    if row is None:
        raise NotFoundError("asset_tag_not_found", "Asset tag was not found", {"tag_id": tag_id})
    if not _same_scope(row, scope=scope, project_id=project_id):
        raise ValidationError(
            "asset_index_scope_mismatch",
            "Asset tag scope does not match asset scope",
            {"tag_id": tag_id, "scope": scope, "project_id": project_id},
        )


def _same_scope(row: aiosqlite.Row, *, scope: str, project_id: str | None) -> bool:
    return row["scope"] == scope and row["project_id"] == project_id


def _clean_string_list(values: list[str] | None) -> list[str]:
    if values is None:
        return []
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def _object_key(storage_uri: str) -> str:
    return storage_uri.strip("/")


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


async def _insert_index_entry(
    db: aiosqlite.Connection,
    *,
    asset_id: str,
    scope: str,
    project_id: str | None,
    collection_id: str | None,
    tag_id: str | None,
    search_text: str,
    now: str,
) -> None:
    await db.execute(
        """
        insert into asset_index_entries (
          entry_id, scope, project_id, asset_id, collection_id, tag_id,
          search_text, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("asset_index"),
            scope,
            project_id,
            asset_id,
            collection_id,
            tag_id,
            search_text,
            now,
            now,
        ),
    )


async def _ensure_episode_metadata_tag_entry(
    db: aiosqlite.Connection,
    *,
    user_id: str,
    asset_id: str,
    scope: str,
    project_id: str | None,
    metadata: dict[str, Any],
    search_text: str,
    now: str,
) -> None:
    if not _is_episode_metadata(metadata):
        return

    tag = await _fetch_one(
        db,
        """
        select * from asset_tags
        where scope = ? and project_id is ? and name = ?
        order by created_at asc, tag_id asc
        limit 1
        """,
        (scope, project_id, _EPISODE_METADATA_TAG_NAME),
    )
    if tag is None:
        tag_id = new_id("tag")
        await db.execute(
            """
            insert into asset_tags (
              tag_id, scope, project_id, name, description, created_by, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tag_id, scope, project_id, _EPISODE_METADATA_TAG_NAME, None, user_id, now, now),
        )
    else:
        tag_id = tag["tag_id"]

    existing = await _fetch_one(
        db,
        "select entry_id from asset_index_entries where asset_id = ? and tag_id = ?",
        (asset_id, tag_id),
    )
    if existing is not None:
        return

    await _insert_index_entry(
        db,
        asset_id=asset_id,
        scope=scope,
        project_id=project_id,
        collection_id=None,
        tag_id=tag_id,
        search_text=search_text,
        now=now,
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


async def _fetch_asset_tag_rows(db: aiosqlite.Connection, *, asset_id: str) -> list[aiosqlite.Row]:
    cursor = await db.execute(
        """
        select tag.*, count(distinct all_idx.asset_id) as asset_count
        from asset_tags tag
        join asset_index_entries idx on idx.tag_id = tag.tag_id
        left join asset_index_entries all_idx on all_idx.tag_id = tag.tag_id
        where idx.asset_id = ?
        group by tag.tag_id
        order by tag.created_at asc, tag.tag_id asc
        """,
        (asset_id,),
    )
    try:
        return await cursor.fetchall()
    finally:
        await cursor.close()


def _thumbnail_size(size: int) -> int:
    if size < 32 or size > 1024:
        raise ValidationError(
            "asset_thumbnail_size_invalid",
            "Thumbnail size must be between 32 and 1024",
            {"size": size},
        )
    return size


def _make_png_thumbnail(content: bytes, *, size: int) -> bytes:
    try:
        with Image.open(BytesIO(content)) as image:
            image.thumbnail((size, size))
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except UnidentifiedImageError as exc:
        raise ValidationError(
            "asset_thumbnail_unsupported",
            "Asset content is not a readable image",
        ) from exc


def _safe_cache_segment(value: str) -> str:
    return "".join(char for char in value if char.isalnum() or char in ("-", "_")) or "unknown"


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


def _collection_from_row(row: aiosqlite.Row) -> AssetCollectionRecord:
    return AssetCollectionRecord(
        collection_id=row["collection_id"],
        scope=row["scope"],
        project_id=row["project_id"],
        parent_id=row["parent_id"],
        name=row["name"],
        description=row["description"],
        sort_order=row["sort_order"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _tag_from_row(row: aiosqlite.Row) -> AssetTagRecord:
    asset_count = row["asset_count"] if "asset_count" in row.keys() else 0
    return AssetTagRecord(
        tag_id=row["tag_id"],
        scope=row["scope"],
        project_id=row["project_id"],
        name=row["name"],
        description=row["description"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        asset_count=int(asset_count or 0),
    )


_EPISODE_METADATA_TAG_NAME = "集元数据"
_EPISODE_METADATA_TYPE_ALIASES = {
    "episode_metadata",
    "episode",
    "episode_meta",
    "集元数据",
    "集信息资产",
    "集信息",
    "集",
}


def _is_episode_metadata(metadata: dict[str, Any]) -> bool:
    for key in ("type", "asset_type"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip().lower() in _EPISODE_METADATA_TYPE_ALIASES:
            return True
    tags = metadata.get("tags")
    if isinstance(tags, list):
        return any(
            isinstance(tag, str) and tag.strip().lower() in _EPISODE_METADATA_TYPE_ALIASES
            for tag in tags
        )
    return False
