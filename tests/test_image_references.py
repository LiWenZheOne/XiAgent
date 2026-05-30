from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.nodes.ai.image_references import resolve_image_ref, resolve_image_refs
from xiagent.nodes.base import NodeContext


class FakeAssetService:
    async def get_asset_content(self, **kwargs: Any) -> Any:
        if kwargs["asset_id"] == "missing-bytes":
            return SimpleNamespace(bytes_content=None, content_type="image/png")
        return SimpleNamespace(bytes_content=b"image-bytes", content_type="image/png")


def _ctx() -> NodeContext:
    return NodeContext(
        user_id="user-1",
        project_id="project-1",
        task_id="task-1",
        node_id="node-1",
        node_execution_id="exec-1",
        config={},
        output_schema={},
        asset_service=FakeAssetService(),  # type: ignore[arg-type]
        event_sink=None,
        logger=None,
    )


async def test_resolve_image_ref_returns_data_uri_unchanged() -> None:
    data_uri = "data:image/png;base64,aW1hZ2U="

    assert await resolve_image_ref(None, {"kind": "data_uri", "data": data_uri}) == data_uri


async def test_resolve_image_ref_reads_asset_bytes() -> None:
    data_uri = await resolve_image_ref(_ctx(), {"kind": "asset", "asset_id": "asset-1"})

    assert data_uri == "data:image/png;base64,aW1hZ2UtYnl0ZXM="


async def test_resolve_image_refs_rejects_bare_urls() -> None:
    with pytest.raises(ValidationError) as exc:
        await resolve_image_refs(_ctx(), ["https://example.test/image.png"])

    assert exc.value.code == "image_ref_invalid"


async def test_resolve_image_ref_requires_asset_service_for_asset_refs() -> None:
    with pytest.raises(ValidationError) as exc:
        await resolve_image_ref(None, {"kind": "asset", "asset_id": "asset-1"})

    assert exc.value.code == "image_ref_service_missing"


async def test_resolve_image_ref_rejects_assets_without_file_bytes() -> None:
    with pytest.raises(ValidationError) as exc:
        await resolve_image_ref(_ctx(), {"kind": "asset", "asset_id": "missing-bytes"})

    assert exc.value.code == "image_ref_content_missing"
