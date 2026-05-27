from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_OBJECT_STORAGE_CONFIG_PATH = Path(__file__).parent.parent / "object_storage.local.toml"
DEFAULT_QINIU_KEY_PREFIX = "xiagent/assets"


@dataclass(frozen=True, slots=True)
class QiniuObjectStorageConfig:
    access_key: str | None
    secret_key: str | None
    bucket: str | None
    region: str | None
    public_base_url: str | None
    key_prefix: str


@dataclass(frozen=True, slots=True)
class ObjectStorageConfig:
    provider: str
    qiniu: QiniuObjectStorageConfig


def load_object_storage_config(
    path: Path = DEFAULT_OBJECT_STORAGE_CONFIG_PATH,
) -> ObjectStorageConfig:
    raw: dict[str, Any] = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))

    object_storage = _section(raw, "object_storage")
    qiniu = _section(object_storage, "qiniu")

    provider = _env_text("XIAGENT_OBJECT_STORAGE_PROVIDER")
    if provider is None:
        provider = _optional_text(object_storage.get("provider")) or "local_public_url"

    key_prefix = (
        _env_text("QINIU_KEY_PREFIX")
        or _optional_text(qiniu.get("key_prefix"))
        or DEFAULT_QINIU_KEY_PREFIX
    )

    return ObjectStorageConfig(
        provider=provider,
        qiniu=QiniuObjectStorageConfig(
            access_key=_env_text("QINIU_ACCESS_KEY") or _optional_text(qiniu.get("access_key")),
            secret_key=_env_text("QINIU_SECRET_KEY") or _optional_text(qiniu.get("secret_key")),
            bucket=_env_text("QINIU_BUCKET") or _optional_text(qiniu.get("bucket")),
            region=_env_text("QINIU_REGION") or _optional_text(qiniu.get("region")),
            public_base_url=_env_text("QINIU_PUBLIC_BASE_URL")
            or _optional_text(qiniu.get("public_base_url")),
            key_prefix=key_prefix.strip("/"),
        ),
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    return value if isinstance(value, dict) else {}


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _env_text(name: str) -> str | None:
    return _optional_text(os.getenv(name))
