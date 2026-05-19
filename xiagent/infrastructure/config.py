from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    asset_storage_dir: Path
    workflow_dir: Path
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str


def load_settings() -> Settings:
    return Settings(
        database_path=Path(os.getenv("XIAGENT_DATABASE_PATH", ".data/xiagent.sqlite3")),
        asset_storage_dir=Path(os.getenv("XIAGENT_ASSET_STORAGE_DIR", "storage/assets")),
        workflow_dir=Path(os.getenv("XIAGENT_WORKFLOW_DIR", "workflows")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    )
