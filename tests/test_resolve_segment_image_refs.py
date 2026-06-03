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
                            "asset_type": "character",
                            "asset_name": "林冲",
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
                        {"asset_type": "character", "asset_name": "林冲", "asset_tags": ["囚服"]},
                        {"asset_type": "character", "asset_name": "鲁智深", "asset_tags": ["僧衣"]},
                    ],
                    "key_props": [],
                }
            ],
            "asset_catalog": {
                "approved_assets": {
                    "characters": [
                        {
                            "name": "角色_林冲_囚服",
                            "tags": ["角色", "林冲", "囚服"],
                            "reference_image_ref": {
                                "kind": "asset",
                                "asset_id": "asset-linchong-prisoner",
                                "role": "reference",
                            },
                        },
                        {
                            "name": "角色_鲁智深_僧衣",
                            "tags": ["角色", "鲁智深", "僧衣"],
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
async def test_resolve_segment_image_refs_resolves_location_and_props() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "location": "野猪林",
                    "characters": [],
                    "key_props": ["花枪"],
                }
            ],
            "asset_catalog": {
                "approved_assets": {
                    "assets": [
                        {
                            "name": "地点_野猪林",
                            "tags": ["地点", "野猪林"],
                            "description": "野猪林雪路狭窄，两侧密林压迫，前景树干可作遮挡。",
                            "reference_image_ref": {
                                "kind": "asset",
                                "asset_id": "asset-boar-forest",
                                "role": "reference",
                            },
                            "public_url": "https://cdn.test/forest.png",
                        }
                    ],
                    "props": [
                        {
                            "name": "道具_花枪",
                            "tags": ["道具", "花枪"],
                            "asset_id": "asset-spear",
                            "image_url": "https://cdn.test/spear.png",
                        }
                    ],
                },
            },
        },
    )

    assignment = result.output["segment_assignments"][0]
    assert assignment["location_asset"] == {
        "asset_type": "scene",
        "asset_name": "野猪林",
        "description": "野猪林雪路狭窄，两侧密林压迫，前景树干可作遮挡。",
        "image_ref": {"kind": "asset", "asset_id": "asset-boar-forest", "role": "reference"},
        "image_url": "https://cdn.test/forest.png",
    }
    assert assignment["prop_assets"] == [
        {
            "asset_type": "prop",
            "asset_name": "花枪",
            "image_ref": {"kind": "asset", "asset_id": "asset-spear", "role": "reference"},
            "image_url": "https://cdn.test/spear.png",
        }
    ]


@pytest.mark.asyncio
async def test_resolve_segment_image_refs_falls_back_to_asset_id() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [{"asset_type": "character", "asset_name": "武松", "asset_tags": ["行者装束"]}],
                    "key_props": [],
                }
            ],
            "asset_catalog": {
                "characters": [
                    {
                        "name": "角色_武松_行者装束",
                        "tags": ["角色", "武松", "行者装束"],
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
                    "characters": [{"asset_type": "character", "asset_name": "林冲"}],
                    "key_props": [],
                }
            ],
            "asset_catalog": {
                "approved_assets": {
                    "characters": [
                        {
                            "name": "角色_林冲_囚服",
                            "tags": ["角色", "林冲", "囚服"],
                            "summary": "八十万禁军教头。",
                        }
                    ],
                },
                "asset_images": [
                    {
                        "asset_type": "character",
                        "asset_name": "林冲",
                        "asset_tags": ["囚服"],
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
async def test_resolve_segment_image_refs_matches_asset_images_by_canonical_identity() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [{"asset_type": "character", "asset_name": "何涛", "asset_tags": ["官兵装束"]}],
                    "key_props": [],
                }
            ],
            "asset_catalog": {
                "approved_assets": {
                    "characters": [
                        {
                            "name": "角色_何涛_官兵装束",
                            "tags": ["角色", "何涛", "官兵装束"],
                        }
                    ],
                },
                "asset_images": [
                    {
                        "asset_id": "asset-hetao",
                        "asset_type": "character",
                        "asset_name": "何涛",
                        "asset_tags": ["官兵装束", "官帽、佩刀、革带"],
                        "image_url": "https://cdn.test/hetao.png",
                    }
                ],
            },
        },
    )

    character = result.output["segment_assignments"][0]["characters"][0]
    assert character["image_ref"] == {
        "kind": "asset",
        "asset_id": "asset-hetao",
        "role": "reference",
    }
    assert character["image_url"] == "https://cdn.test/hetao.png"


@pytest.mark.asyncio
async def test_resolve_segment_image_refs_leaves_unmatched_character_without_ref() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [{"asset_type": "character", "asset_name": "未知角色"}],
                    "key_props": [],
                }
            ],
            "asset_catalog": {"approved_assets": {"characters": []}},
        },
    )

    character = result.output["segment_assignments"][0]["characters"][0]
    assert character == {
        "asset_type": "character",
        "asset_name": "未知角色",
    }
