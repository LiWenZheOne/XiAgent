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
    runninghub_image_api_key: str | None
    runninghub_image_base_url: str
    runninghub_image_model: str
    runninghub_image_endpoint: str
    runninghub_image_poll_interval_seconds: float
    runninghub_image_poll_timeout_seconds: float
    runninghub_text_to_image_api_key: str | None
    runninghub_text_to_image_base_url: str
    runninghub_text_to_image_model: str
    runninghub_text_to_image_endpoint: str
    runninghub_text_to_image_poll_interval_seconds: float
    runninghub_text_to_image_poll_timeout_seconds: float
    gemini_api_key: str | None
    gemini_base_url: str
    gemini_model: str


def load_settings() -> Settings:
    model_config = load_model_config()
    return Settings(
        database_path=Path(os.getenv("XIAGENT_DATABASE_PATH", ".data/xiagent.sqlite3")),
        asset_storage_dir=Path(os.getenv("XIAGENT_ASSET_STORAGE_DIR", "storage/assets")),
        workflow_dir=Path(os.getenv("XIAGENT_WORKFLOW_DIR", "workflows")),
        deepseek_api_key=model_config.deepseek.api_key,
        deepseek_base_url=model_config.deepseek.base_url,
        deepseek_model=model_config.deepseek.model,
        runninghub_image_api_key=model_config.runninghub_image.api_key,
        runninghub_image_base_url=model_config.runninghub_image.base_url,
        runninghub_image_model=model_config.runninghub_image.model,
        runninghub_image_endpoint=model_config.runninghub_image.endpoint,
        runninghub_image_poll_interval_seconds=(
            model_config.runninghub_image.poll_interval_seconds
        ),
        runninghub_image_poll_timeout_seconds=model_config.runninghub_image.poll_timeout_seconds,
        runninghub_text_to_image_api_key=model_config.runninghub_text_to_image.api_key,
        runninghub_text_to_image_base_url=model_config.runninghub_text_to_image.base_url,
        runninghub_text_to_image_model=model_config.runninghub_text_to_image.model,
        runninghub_text_to_image_endpoint=model_config.runninghub_text_to_image.endpoint,
        runninghub_text_to_image_poll_interval_seconds=(
            model_config.runninghub_text_to_image.poll_interval_seconds
        ),
        runninghub_text_to_image_poll_timeout_seconds=(
            model_config.runninghub_text_to_image.poll_timeout_seconds
        ),
        gemini_api_key=model_config.gemini.api_key,
        gemini_base_url=model_config.gemini.base_url,
        gemini_model=model_config.gemini.model,
    )
