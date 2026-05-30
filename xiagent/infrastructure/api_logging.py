from __future__ import annotations

import copy
import json
import logging
from collections.abc import Mapping
from typing import Any

LOGGER = logging.getLogger("xiagent.external_api")
BASE64_PREVIEW_CHARS = 96


def log_api_request(*, provider: str, url: str, payload: Mapping[str, Any]) -> None:
    sanitized = sanitize_api_payload(payload)
    LOGGER.info(
        "external_api_request %s",
        json.dumps(
            {"provider": provider, "url": url, "payload": sanitized},
            ensure_ascii=False,
            default=str,
        ),
        extra={
            "provider": provider,
            "url": url,
            "payload": sanitized,
        },
    )


def log_api_response(*, provider: str, url: str, payload: Any) -> None:
    sanitized = sanitize_api_payload(payload)
    LOGGER.info(
        "external_api_response %s",
        json.dumps(
            {"provider": provider, "url": url, "payload": sanitized},
            ensure_ascii=False,
            default=str,
        ),
        extra={
            "provider": provider,
            "url": url,
            "payload": sanitized,
        },
    )


def sanitize_api_payload(value: Any) -> Any:
    return _sanitize(copy.deepcopy(value))


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_sensitive_value(str(key), item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _truncate_data_uri(value)
    return value


def _sanitize_sensitive_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered in {"authorization", "api_key", "apikey", "token", "access_token", "password"}:
        return "***redacted***"
    return _sanitize(value)


def _truncate_data_uri(value: str) -> str:
    if not value.startswith("data:image/"):
        return value
    header, separator, data = value.partition(",")
    if not separator:
        return value[:BASE64_PREVIEW_CHARS] + "...<truncated>"
    return f"{header},{data[:BASE64_PREVIEW_CHARS]}...<base64 truncated {len(data)} chars>"
