from __future__ import annotations

from dataclasses import asdict

import pytest

from xiagent.ui_controls import build_builtin_ui_control_catalog


def test_builtin_ui_controls_have_unique_ids() -> None:
    catalog = build_builtin_ui_control_catalog()
    controls = catalog.list_controls()

    assert len({control.control_id for control in controls}) == len(controls)
    assert "ui.choice.image_three.v1" in {control.control_id for control in controls}


def test_image_three_choice_control_declares_expected_variants() -> None:
    catalog = build_builtin_ui_control_catalog()
    control = catalog.get("ui.choice.image_three.v1")

    assert control.kind == "interaction"
    assert {"image", "choice", "select_one", "candidates_3"}.issubset(control.tags)
    assert {variant.name for variant in control.variants} == {
        "equal_grid",
        "hero_list",
        "hover_focus",
    }


def test_unknown_ui_control_raises_key_error() -> None:
    catalog = build_builtin_ui_control_catalog()

    with pytest.raises(KeyError):
        catalog.get("ui.missing.v1")


def test_ui_control_descriptor_is_api_serializable() -> None:
    catalog = build_builtin_ui_control_catalog()
    payload = asdict(catalog.get("ui.choice.image_three.v1"))

    assert payload["control_id"] == "ui.choice.image_three.v1"
    assert payload["variants"][0]["required_bindings"]
