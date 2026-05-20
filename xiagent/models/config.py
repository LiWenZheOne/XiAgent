from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from xiagent.models.types import (
    DeepSeekModelConfig,
    ModelConfig,
    RunningHubImageModelConfig,
    RunningHubTextToImageModelConfig,
)

DEFAULT_MODEL_CONFIG_PATH = Path(__file__).with_name("local_config.toml")


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value or None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value:
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    return value if isinstance(value, dict) else {}


def _config_float(
    *,
    env_name: str,
    section: dict[str, Any],
    key: str,
    default: float,
) -> float:
    env_value = _optional_float(os.getenv(env_name))
    if env_value is not None:
        return env_value
    local_value = _optional_float(section.get(key))
    if local_value is not None:
        return local_value
    return default


def load_model_config(path: Path = DEFAULT_MODEL_CONFIG_PATH) -> ModelConfig:
    raw: dict[str, Any] = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

    deepseek = _section(raw, "deepseek")
    runninghub_image = _section(raw, "runninghub_image")
    runninghub_text_to_image = _section(raw, "runninghub_text_to_image")

    api_key = _optional_text(deepseek.get("api_key"))
    base_url = _optional_text(deepseek.get("base_url")) or "https://api.deepseek.com"
    model = _optional_text(deepseek.get("model")) or "deepseek-v4-flash"

    api_key = os.getenv("DEEPSEEK_API_KEY") or api_key
    base_url = os.getenv("DEEPSEEK_BASE_URL") or base_url
    model = os.getenv("DEEPSEEK_MODEL") or model

    runninghub_api_key_env = os.getenv("RUNNINGHUB_API_KEY")
    runninghub_base_url_env = os.getenv("RUNNINGHUB_BASE_URL")

    runninghub_api_key = _optional_text(runninghub_image.get("api_key"))
    runninghub_base_url = (
        _optional_text(runninghub_image.get("base_url")) or "https://www.runninghub.ai"
    )
    runninghub_model = (
        _optional_text(runninghub_image.get("model"))
        or "nano-banana2-gemini31flash/image-to-image-channel-low-price"
    )
    runninghub_endpoint = (
        _optional_text(runninghub_image.get("endpoint"))
        or "/rhart-image-n-g31-flash/image-to-image"
    )
    runninghub_poll_interval_seconds = _config_float(
        env_name="RUNNINGHUB_POLL_INTERVAL_SECONDS",
        section=runninghub_image,
        key="poll_interval_seconds",
        default=2.0,
    )
    runninghub_poll_timeout_seconds = _config_float(
        env_name="RUNNINGHUB_POLL_TIMEOUT_SECONDS",
        section=runninghub_image,
        key="poll_timeout_seconds",
        default=180.0,
    )

    runninghub_api_key = runninghub_api_key_env or runninghub_api_key
    runninghub_base_url = runninghub_base_url_env or runninghub_base_url
    runninghub_model = os.getenv("RUNNINGHUB_IMAGE_MODEL") or runninghub_model
    runninghub_endpoint = os.getenv("RUNNINGHUB_IMAGE_ENDPOINT") or runninghub_endpoint

    runninghub_text_api_key = (
        runninghub_api_key_env
        or _optional_text(runninghub_text_to_image.get("api_key"))
        or runninghub_api_key
    )
    runninghub_text_base_url = (
        runninghub_base_url_env
        or _optional_text(runninghub_text_to_image.get("base_url"))
        or "https://www.runninghub.ai"
    )
    runninghub_text_model = (
        os.getenv("RUNNINGHUB_TEXT_TO_IMAGE_MODEL")
        or _optional_text(runninghub_text_to_image.get("model"))
        or "nano-banana-pro/text-to-image-channel-low-price"
    )
    runninghub_text_endpoint = (
        os.getenv("RUNNINGHUB_TEXT_TO_IMAGE_ENDPOINT")
        or _optional_text(runninghub_text_to_image.get("endpoint"))
        or "/rhart-image-n-pro/text-to-image"
    )
    runninghub_text_poll_interval_seconds = _config_float(
        env_name="RUNNINGHUB_POLL_INTERVAL_SECONDS",
        section=runninghub_text_to_image,
        key="poll_interval_seconds",
        default=2.0,
    )
    runninghub_text_poll_timeout_seconds = _config_float(
        env_name="RUNNINGHUB_POLL_TIMEOUT_SECONDS",
        section=runninghub_text_to_image,
        key="poll_timeout_seconds",
        default=180.0,
    )

    return ModelConfig(
        deepseek=DeepSeekModelConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
        ),
        runninghub_image=RunningHubImageModelConfig(
            api_key=runninghub_api_key,
            base_url=runninghub_base_url,
            model=runninghub_model,
            endpoint=runninghub_endpoint,
            poll_interval_seconds=runninghub_poll_interval_seconds,
            poll_timeout_seconds=runninghub_poll_timeout_seconds,
        ),
        runninghub_text_to_image=RunningHubTextToImageModelConfig(
            api_key=runninghub_text_api_key,
            base_url=runninghub_text_base_url,
            model=runninghub_text_model,
            endpoint=runninghub_text_endpoint,
            poll_interval_seconds=runninghub_text_poll_interval_seconds,
            poll_timeout_seconds=runninghub_text_poll_timeout_seconds,
        ),
    )
