from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from xiagent.models.config import load_model_config


@dataclass(frozen=True)
class Settings:
    database_path: Path
    asset_storage_dir: Path
    workflow_dir: Path
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str


def load_settings() -> Settings:
    model_config = load_model_config()
    return Settings(
        database_path=Path(os.getenv("XIAGENT_DATABASE_PATH", ".data/xiagent.sqlite3")),
        asset_storage_dir=Path(os.getenv("XIAGENT_ASSET_STORAGE_DIR", "storage/assets")),
        workflow_dir=Path(os.getenv("XIAGENT_WORKFLOW_DIR", "workflows")),
        deepseek_api_key=model_config.deepseek.api_key,
        deepseek_base_url=model_config.deepseek.base_url,
        deepseek_model=model_config.deepseek.model,
    )
