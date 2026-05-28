from __future__ import annotations

from dataclasses import asdict

import pytest

from xiagent.ui_controls import build_builtin_ui_control_catalog


def test_builtin_ui_controls_have_unique_ids() -> None:
    catalog = build_builtin_ui_control_catalog()
    controls = catalog.list_controls()

    assert len({control.control_id for control in controls}) == len(controls)
    assert "ui.choice.image_three.v1" in {control.control_id for control in controls}
    assert "ui.display.image_viewer.v1" in {control.control_id for control in controls}
    assert "ui.input.schema_form.v1" in {control.control_id for control in controls}
    assert "ui.input.asset_image_picker.v1" in {control.control_id for control in controls}


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
    assert all("readonly" in variant.modes for variant in control.variants)


def test_image_viewer_control_declares_grid_modal_bindings() -> None:
    catalog = build_builtin_ui_control_catalog()
    control = catalog.get("ui.display.image_viewer.v1")
    variant = control.variants[0]

    assert control.kind == "output"
    assert {"image", "viewer", "modal", "readonly"}.issubset(control.tags)
    assert variant.name == "grid_modal"
    assert variant.modes == ("readonly",)
    assert {binding.name for binding in variant.required_bindings} == {
        "items_path",
        "image_url_path",
        "label_path",
    }


def test_approval_control_declares_readonly_mode() -> None:
    catalog = build_builtin_ui_control_catalog()
    control = catalog.get("ui.interaction.approval.v1")

    assert control.kind == "interaction"
    assert "interactive" in control.variants[0].modes
    assert "readonly" in control.variants[0].modes


def test_unknown_ui_control_raises_key_error() -> None:
    catalog = build_builtin_ui_control_catalog()

    with pytest.raises(KeyError):
        catalog.get("ui.missing.v1")


def test_schema_form_and_asset_image_picker_controls_are_registered() -> None:
    catalog = build_builtin_ui_control_catalog()

    schema_form = catalog.get("ui.input.schema_form.v1")
    assert schema_form.kind == "input"
    assert schema_form.variants[0].name == "default"
    assert "input" in schema_form.variants[0].modes
    assert "readonly" in schema_form.variants[0].modes

    asset_picker = catalog.get("ui.input.asset_image_picker.v1")
    assert asset_picker.kind == "input"
    assert asset_picker.variants[0].name == "thumbnails"
    assert "input" in asset_picker.variants[0].modes
    assert asset_picker.variants[0].submit_schema == {
        "type": "object",
        "required": ["value"],
        "properties": {
            "value": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            }
        },
        "additionalProperties": False,
    }


def test_ui_control_descriptor_is_api_serializable() -> None:
    catalog = build_builtin_ui_control_catalog()
    payload = asdict(catalog.get("ui.choice.image_three.v1"))

    assert payload["control_id"] == "ui.choice.image_three.v1"
    assert payload["variants"][0]["required_bindings"]
