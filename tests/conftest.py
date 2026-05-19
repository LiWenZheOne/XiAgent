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
    )
