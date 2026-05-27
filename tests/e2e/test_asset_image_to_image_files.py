from __future__ import annotations

from pathlib import Path


def test_asset_image_to_image_e2e_files_exist() -> None:
    assert Path("ui/V1/playwright.config.ts").exists()
    assert Path("ui/V1/tests/e2e/image-to-image-asset.spec.ts").exists()
