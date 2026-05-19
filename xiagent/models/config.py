from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from xiagent.models.types import DeepSeekModelConfig, ModelConfig

DEFAULT_MODEL_CONFIG_PATH = Path(__file__).with_name("local_config.toml")


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value or None


def load_model_config(path: Path = DEFAULT_MODEL_CONFIG_PATH) -> ModelConfig:
    raw: dict[str, Any] = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

    deepseek = raw.get("deepseek", {})
    if not isinstance(deepseek, dict):
        deepseek = {}

    api_key = _optional_text(deepseek.get("api_key"))
    base_url = _optional_text(deepseek.get("base_url")) or "https://api.deepseek.com"
    model = _optional_text(deepseek.get("model")) or "deepseek-v4-flash"

    api_key = os.getenv("DEEPSEEK_API_KEY") or api_key
    base_url = os.getenv("DEEPSEEK_BASE_URL") or base_url
    model = os.getenv("DEEPSEEK_MODEL") or model

    return ModelConfig(
        deepseek=DeepSeekModelConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    )
