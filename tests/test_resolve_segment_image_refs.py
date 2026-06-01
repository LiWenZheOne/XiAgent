from __future__ import annotations

import pytest

from xiagent.nodes.tools.resolve_segment_image_refs import ResolveSegmentImageRefsNode


@pytest.mark.asyncio
async def test_resolve_segment_image_refs_preserves_existing_ref() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [
                        {
                            "full_name": "林冲",
                            "image_ref": {
                                "kind": "data_uri",
                                "data": "data:image/png;base64,bGluY2hvbmc=",
                                "role": "reference",
                            },
                        }
                    ],
                    "key_props": [],
                }
            ],
            "asset_catalog": {},
        },
    )

    character = result.output["segment_assignments"][0]["characters"][0]
    assert character["image_ref"] == {
        "kind": "data_uri",
        "data": "data:image/png;base64,bGluY2hvbmc=",
        "role": "reference",
    }


@pytest.mark.asyncio
async def test_resolve_segment_image_refs_uses_catalog_structured_ref() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [
                        {"full_name": "林冲", "variant": "囚服"},
                        {"full_name": "鲁智深", "variant": "僧衣"},
                    ],
                    "key_props": [],
                }
            ],
            "asset_catalog": {
                "approved_assets": {
                    "characters": [
                        {
                            "name": "林冲",
                            "variant_name": "囚服",
                            "reference_image_ref": {
                                "kind": "asset",
                                "asset_id": "asset-linchong-prisoner",
                                "role": "reference",
                            },
                        },
                        {
                            "name": "鲁智深",
                            "variant_name": "僧衣",
                            "matched_asset_ref": {
                                "kind": "asset",
                                "asset_id": "asset-luzhishen-monk",
                                "role": "reference",
                            },
                        },
                    ],
                },
            },
        },
    )

    characters = result.output["segment_assignments"][0]["characters"]
    assert characters[0]["image_ref"] == {
        "kind": "asset",
        "asset_id": "asset-linchong-prisoner",
        "role": "reference",
    }
    assert characters[1]["image_ref"] == {
        "kind": "asset",
        "asset_id": "asset-luzhishen-monk",
        "role": "reference",
    }


@pytest.mark.asyncio
async def test_resolve_segment_image_refs_falls_back_to_asset_id() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [{"full_name": "武松", "variant": "行者装束"}],
                    "key_props": [],
                }
            ],
            "asset_catalog": {
                "characters": [
                    {
                        "name": "武松",
                        "variant_name": "行者装束",
                        "matched_asset_id": "asset-wusong",
                    }
                ],
            },
        },
    )

    character = result.output["segment_assignments"][0]["characters"][0]
    assert character["image_ref"] == {
        "kind": "asset",
        "asset_id": "asset-wusong",
        "role": "reference",
    }


@pytest.mark.asyncio
async def test_resolve_segment_image_refs_prefers_generated_asset_images() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [{"full_name": "林冲"}],
                    "key_props": [],
                }
            ],
            "asset_catalog": {
                "approved_assets": {
                    "characters": [
                        {
                            "name": "林冲",
                            "variant_name": "囚服",
                            "summary": "八十万禁军教头。",
                        }
                    ],
                },
                "asset_images": [
                    {
                        "full_name": "林冲",
                        "variant": "囚服",
                        "asset_id": "asset-generated-linchong",
                    }
                ],
            },
        },
    )

    character = result.output["segment_assignments"][0]["characters"][0]
    assert character["image_ref"] == {
        "kind": "asset",
        "asset_id": "asset-generated-linchong",
        "role": "reference",
    }


@pytest.mark.asyncio
async def test_resolve_segment_image_refs_leaves_unmatched_character_without_ref() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [{"full_name": "未知角色"}],
                    "key_props": [],
                }
            ],
            "asset_catalog": {"approved_assets": {"characters": []}},
        },
    )

    character = result.output["segment_assignments"][0]["characters"][0]
    assert character == {"full_name": "未知角色"}
