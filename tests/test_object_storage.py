from __future__ import annotations

from pathlib import Path

import pytest

import xiagent.infrastructure.object_storage.qiniu as qiniu_adapter
from xiagent.infrastructure.object_storage.config import (
    DEFAULT_OBJECT_STORAGE_CONFIG_PATH,
    QiniuObjectStorageConfig,
    load_object_storage_config,
)
from xiagent.infrastructure.object_storage.qiniu import QiniuObjectStorageService
from xiagent.infrastructure.object_storage.router import (
    DisabledObjectStorageService,
    ObjectStorageRouter,
)


def test_load_object_storage_config_prefers_local_file(tmp_path: Path) -> None:
    config_path = tmp_path / "object_storage.local.toml"
    config_path.write_text(
        """
[object_storage]
provider = "qiniu"

[object_storage.qiniu]
access_key = "ak"
secret_key = "sk"
bucket = "bucket"
region = "z0"
public_base_url = "https://cdn.example.com"
key_prefix = "xiagent/assets"
""".lstrip(),
        encoding="utf-8",
    )

    config = load_object_storage_config(config_path)

    assert config.provider == "qiniu"
    assert config.qiniu.access_key == "ak"
    assert config.qiniu.secret_key == "sk"
    assert config.qiniu.bucket == "bucket"
    assert config.qiniu.region == "z0"
    assert config.qiniu.public_base_url == "https://cdn.example.com"
    assert config.qiniu.key_prefix == "xiagent/assets"


def test_load_object_storage_config_accepts_utf8_sig_local_file(tmp_path: Path) -> None:
    config_path = tmp_path / "object_storage.local.toml"
    config_path.write_text(
        """
[object_storage]
provider = "qiniu"

[object_storage.qiniu]
access_key = "ak"
secret_key = "sk"
bucket = "bucket"
region = "z0"
public_base_url = "https://cdn.example.com"
key_prefix = "xiagent/assets"
""".lstrip(),
        encoding="utf-8-sig",
    )

    config = load_object_storage_config(config_path)

    assert config.provider == "qiniu"
    assert config.qiniu.access_key == "ak"


def test_default_object_storage_config_path_matches_ignored_local_file() -> None:
    assert DEFAULT_OBJECT_STORAGE_CONFIG_PATH.as_posix().endswith(
        "xiagent/infrastructure/object_storage.local.toml"
    )


def test_load_object_storage_config_prefers_environment_over_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "object_storage.local.toml"
    config_path.write_text(
        """
[object_storage]
provider = "qiniu"

[object_storage.qiniu]
access_key = "file-ak"
secret_key = "file-sk"
bucket = "file-bucket"
region = "z0"
public_base_url = "https://file-cdn.example.com"
key_prefix = "/file/prefix/"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("XIAGENT_OBJECT_STORAGE_PROVIDER", "local_none")
    monkeypatch.setenv("QINIU_ACCESS_KEY", "env-ak")
    monkeypatch.setenv("QINIU_SECRET_KEY", "env-sk")
    monkeypatch.setenv("QINIU_BUCKET", "env-bucket")
    monkeypatch.setenv("QINIU_REGION", "z1")
    monkeypatch.setenv("QINIU_PUBLIC_BASE_URL", "https://env-cdn.example.com")
    monkeypatch.setenv("QINIU_KEY_PREFIX", "/env/prefix/")

    config = load_object_storage_config(config_path)

    assert config.provider == "local_none"
    assert config.qiniu.access_key == "env-ak"
    assert config.qiniu.secret_key == "env-sk"
    assert config.qiniu.bucket == "env-bucket"
    assert config.qiniu.region == "z1"
    assert config.qiniu.public_base_url == "https://env-cdn.example.com"
    assert config.qiniu.key_prefix == "env/prefix"


def test_object_storage_router_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported object storage provider"):
        ObjectStorageRouter(provider="missing", services={}).current()


async def test_disabled_object_storage_rejects_upload() -> None:
    service = DisabledObjectStorageService()

    with pytest.raises(RuntimeError, match="Object storage is not configured"):
        await service.put_object(key="asset.png", content=b"data", content_type="image/png")


async def test_qiniu_upload_uses_prefixed_object_key_for_token_and_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, str | None] = {}

    class FakeAuth:
        def __init__(self, access_key: str, secret_key: str) -> None:
            calls["access_key"] = access_key
            calls["secret_key"] = secret_key

        def upload_token(self, bucket: str, key: str) -> str:
            calls["token_bucket"] = bucket
            calls["token_key"] = key
            return "token"

    class FakeInfo:
        status_code = 200

    def fake_put_data(
        token: str,
        key: str,
        data: bytes,
        params=None,
        mime_type: str | None = None,
        check_crc: bool = False,
        progress_handler=None,
        fname=None,
        hostscache_dir=None,
        metadata=None,
        regions=None,
        accelerate_uploading: bool = False,
    ) -> tuple[dict[str, str], FakeInfo]:
        calls["upload_token"] = token
        calls["upload_key"] = key
        calls["mime_type"] = mime_type
        calls["data"] = data.decode("utf-8")
        calls["region_up_host"] = getattr(regions[0], "up_host", None) if regions else None
        return {"hash": "etag"}, FakeInfo()

    monkeypatch.setattr(qiniu_adapter, "Auth", FakeAuth)
    monkeypatch.setattr(qiniu_adapter, "put_data", fake_put_data)
    service = QiniuObjectStorageService(
        QiniuObjectStorageConfig(
            access_key="ak",
            secret_key="sk",
            bucket="bucket",
            region="z2",
            public_base_url="https://cdn.example.com",
            key_prefix="xiagent/assets",
        )
    )

    stored_object = await service.put_object(
        key="hero.png",
        content=b"image",
        content_type="image/png",
    )

    assert calls["token_key"] == "xiagent/assets/hero.png"
    assert calls["upload_key"] == "xiagent/assets/hero.png"
    assert calls["region_up_host"] == "up-z2.qiniup.com"
    assert stored_object.key == "xiagent/assets/hero.png"
    assert stored_object.public_url == "https://cdn.example.com/xiagent/assets/hero.png"
