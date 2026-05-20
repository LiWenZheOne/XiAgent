from __future__ import annotations

from pathlib import Path

import pytest

from xiagent.infrastructure.config import Settings


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "xiagent-test.sqlite3",
        asset_storage_dir=tmp_path / "assets",
        workflow_dir=tmp_path / "workflows",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        runninghub_image_api_key=None,
        runninghub_image_base_url="https://www.runninghub.ai",
        runninghub_image_model="nano-banana2-gemini31flash/image-to-image-channel-low-price",
        runninghub_image_endpoint="/rhart-image-n-g31-flash/image-to-image",
        runninghub_image_poll_interval_seconds=2.0,
        runninghub_image_poll_timeout_seconds=180.0,
        runninghub_text_to_image_api_key=None,
        runninghub_text_to_image_base_url="https://www.runninghub.ai",
        runninghub_text_to_image_model="nano-banana-pro/text-to-image-channel-low-price",
        runninghub_text_to_image_endpoint="/rhart-image-n-pro/text-to-image",
        runninghub_text_to_image_poll_interval_seconds=2.0,
        runninghub_text_to_image_poll_timeout_seconds=180.0,
    )
