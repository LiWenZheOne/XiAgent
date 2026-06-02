from __future__ import annotations

from xiagent.nodes.tools.asset_identity import normalize_asset_record


def test_normalize_asset_record_keeps_canonical_identity_only() -> None:
    result = normalize_asset_record(
        {
            "asset_id": "asset-hetao",
            "asset_type": "character",
            "asset_name": "何涛",
            "asset_tags": ["官兵装束", "官帽、佩刀、革带"],
            "image_url": "https://cdn.test/hetao.png",
        }
    )

    assert result["asset_type"] == "character"
    assert result["asset_name"] == "何涛"
    assert result["asset_tags"] == ["官兵装束", "官帽、佩刀、革带"]
    assert "full_name" not in result
    assert "asset_key" not in result


def test_normalize_asset_record_converts_asset_library_tags() -> None:
    result = normalize_asset_record(
        {
            "tags": ["角色", "林冲", "囚服", "毡笠"],
            "name": "角色_林冲_囚服_毡笠",
        }
    )

    assert result["asset_type"] == "character"
    assert result["asset_name"] == "林冲"
    assert result["asset_tags"] == ["囚服", "毡笠"]


def test_normalize_asset_record_prefers_composite_name_over_unordered_tags() -> None:
    result = normalize_asset_record(
        {
            "name": "角色_阮小二_渔民短打_锄头、头巾",
            "tags": ["角色", "渔民短打", "阮小二", "锄头、头巾"],
        }
    )

    assert result["asset_type"] == "character"
    assert result["asset_name"] == "阮小二"
    assert result["asset_tags"] == ["渔民短打", "锄头、头巾"]


def test_normalize_asset_record_does_not_infer_from_removed_fields() -> None:
    result = normalize_asset_record(
        {
            "full_name": "林冲",
            "variant_name": "囚服",
            "accessories": ["毡笠"],
        },
        default_asset_type="character",
    )

    assert result["asset_type"] == "character"
    assert "full_name" not in result
    assert "variant_name" not in result
    assert "accessories" not in result
    assert "asset_name" not in result
    assert "asset_tags" not in result
