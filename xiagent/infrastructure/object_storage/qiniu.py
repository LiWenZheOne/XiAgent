from __future__ import annotations

import anyio
from qiniu import Auth, BucketManager, Region, put_data

from xiagent.infrastructure.object_storage.base import ObjectStorageService
from xiagent.infrastructure.object_storage.config import QiniuObjectStorageConfig
from xiagent.infrastructure.object_storage.models import StoredObject


class QiniuObjectStorageService(ObjectStorageService):
    def __init__(self, config: QiniuObjectStorageConfig) -> None:
        self._config = config

    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        self._validate_config()
        assert self._config.access_key is not None
        assert self._config.secret_key is not None
        assert self._config.bucket is not None
        assert self._config.public_base_url is not None

        object_key = self._object_key(key)
        auth = Auth(self._config.access_key, self._config.secret_key)
        token = auth.upload_token(self._config.bucket, object_key)

        upload_regions = self._upload_regions()

        def upload() -> tuple[dict, object]:
            return put_data(
                token,
                object_key,
                content,
                mime_type=content_type,
                regions=upload_regions,
            )

        ret, info = await anyio.to_thread.run_sync(upload)
        if getattr(info, "status_code", None) not in {200, 201}:
            raise RuntimeError(f"Qiniu upload failed: {getattr(info, 'text_body', info)}")

        return StoredObject(
            provider="qiniu",
            bucket=self._config.bucket,
            key=object_key,
            public_url=f"{self._config.public_base_url.rstrip('/')}/{object_key}",
            content_type=content_type,
            size_bytes=len(content),
            etag=ret.get("hash") if isinstance(ret, dict) else None,
        )

    async def delete_object(self, *, key: str) -> None:
        self._validate_config()
        assert self._config.access_key is not None
        assert self._config.secret_key is not None
        assert self._config.bucket is not None

        auth = Auth(self._config.access_key, self._config.secret_key)
        bucket = BucketManager(auth)
        object_key = self._object_key(key)

        def delete() -> tuple[object, object]:
            return bucket.delete(self._config.bucket, object_key)

        _, info = await anyio.to_thread.run_sync(delete)
        if getattr(info, "status_code", None) not in {200, 612}:
            raise RuntimeError(f"Qiniu delete failed: {getattr(info, 'text_body', info)}")

    def _object_key(self, key: str) -> str:
        clean_key = key.strip("/")
        if not self._config.key_prefix:
            return clean_key
        prefix = self._config.key_prefix.strip("/")
        if clean_key == prefix or clean_key.startswith(f"{prefix}/"):
            return clean_key
        return f"{prefix}/{clean_key}"

    def _upload_regions(self) -> list[Region] | None:
        if self._config.region is None:
            return None
        region_id = self._config.region.strip()
        upload_hosts = {
            "z0": ("up-z0.qiniup.com", "upload-z0.qiniup.com"),
            "cn-east-2": ("up-cn-east-2.qiniup.com", "upload-cn-east-2.qiniup.com"),
            "z1": ("up-z1.qiniup.com", "upload-z1.qiniup.com"),
            "z2": ("up-z2.qiniup.com", "upload-z2.qiniup.com"),
            "na0": ("up-na0.qiniup.com", "upload-na0.qiniup.com"),
            "as0": ("up-as0.qiniup.com", "upload-as0.qiniup.com"),
            "ap-southeast-2": ("up-ap-southeast-2.qiniup.com", "upload-ap-southeast-2.qiniup.com"),
            "ap-southeast-3": ("up-ap-southeast-3.qiniup.com", "upload-ap-southeast-3.qiniup.com"),
        }
        hosts = upload_hosts.get(region_id)
        if hosts is None:
            raise RuntimeError(f"Unsupported Qiniu object storage region: {region_id}")
        return [Region(up_host=hosts[0], up_host_backup=hosts[1], scheme="https")]

    def _validate_config(self) -> None:
        missing = [
            name
            for name, value in {
                "access_key": self._config.access_key,
                "secret_key": self._config.secret_key,
                "bucket": self._config.bucket,
                "public_base_url": self._config.public_base_url,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Qiniu object storage config is missing: {', '.join(missing)}")
