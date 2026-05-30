from __future__ import annotations

from xiagent.infrastructure.api_logging import sanitize_api_payload


def test_sanitize_api_payload_truncates_base64_and_redacts_secrets() -> None:
    image_data = "a" * 200
    payload = {
        "api_key": "secret-key",
        "Authorization": "Bearer secret-token",
        "imageUrls": [f"data:image/png;base64,{image_data}"],
        "nested": {"password": "secret-password"},
    }

    sanitized = sanitize_api_payload(payload)

    assert sanitized["api_key"] == "***redacted***"
    assert sanitized["Authorization"] == "***redacted***"
    assert sanitized["nested"]["password"] == "***redacted***"
    assert sanitized["imageUrls"][0].startswith("data:image/png;base64,")
    assert "<base64 truncated 200 chars>" in sanitized["imageUrls"][0]
    assert image_data not in sanitized["imageUrls"][0]
