from __future__ import annotations

from xiagent.ui_controls.models import (
    UiControlBindingRequirement,
    UiControlDescriptor,
    UiControlVariant,
)


class UiControlCatalog:
    def __init__(self, controls: list[UiControlDescriptor]) -> None:
        self._controls = {control.control_id: control for control in controls}
        if len(self._controls) != len(controls):
            raise ValueError("UI control IDs must be unique")

    def list_controls(self) -> list[UiControlDescriptor]:
        return list(self._controls.values())

    def get(self, control_id: str) -> UiControlDescriptor:
        try:
            return self._controls[control_id]
        except KeyError as exc:
            raise KeyError(control_id) from exc


def build_builtin_ui_control_catalog() -> UiControlCatalog:
    image_choice_bindings = (
        UiControlBindingRequirement(
            name="items_path",
            binding_kind="schema_path",
            schema_constraints={"type": "array", "minItems": 1},
        ),
        UiControlBindingRequirement(
            name="image_url_path",
            binding_kind="item_field",
            accepted_sources=("item",),
            schema_constraints={"type": "string"},
        ),
        UiControlBindingRequirement(
            name="value_path",
            binding_kind="item_field",
            accepted_sources=("item",),
        ),
    )
    image_choice_submit_schema = {
        "type": "object",
        "required": ["selected_id", "selected_item"],
        "properties": {
            "selected_id": {"type": "string"},
            "selected_index": {"type": "integer", "minimum": 0},
            "selected_item": {"type": "object", "additionalProperties": True},
            "selected_image_url": {"type": "string"},
        },
        "additionalProperties": True,
    }
    return UiControlCatalog(
        [
            UiControlDescriptor(
                control_id="ui.display.value.v1",
                version="1.0.0",
                name="Value Display",
                kind="output",
                tags=("value", "fallback", "readonly"),
                variants=(
                    UiControlVariant(
                        name="default",
                        label="默认值展示",
                        modes=("readonly",),
                    ),
                ),
                description="通用值展示 fallback 控件。",
            ),
            UiControlDescriptor(
                control_id="ui.display.image_candidates.v1",
                version="1.0.0",
                name="Image Candidates",
                kind="output",
                tags=("image", "list", "candidates", "readonly"),
                variants=(
                    UiControlVariant(
                        name="grid",
                        label="网格",
                        modes=("readonly",),
                        required_bindings=(
                            UiControlBindingRequirement(
                                name="items_path",
                                schema_constraints={"type": "array", "minItems": 1},
                            ),
                            UiControlBindingRequirement(
                                name="image_url_path",
                                binding_kind="item_field",
                                accepted_sources=("item",),
                                schema_constraints={"type": "string"},
                            ),
                        ),
                    ),
                ),
                description="图片候选列表展示控件。",
            ),
            UiControlDescriptor(
                control_id="ui.choice.image_three.v1",
                version="1.0.0",
                name="Image Three Choice",
                kind="interaction",
                tags=("image", "choice", "select_one", "candidates_3", "interactive"),
                variants=(
                    UiControlVariant(
                        name="equal_grid",
                        label="三图等宽",
                        tags=("equal_grid",),
                        modes=("interactive", "readonly"),
                        required_bindings=image_choice_bindings,
                        submit_schema=image_choice_submit_schema,
                    ),
                    UiControlVariant(
                        name="hero_list",
                        label="首图大列表",
                        tags=("hero_list",),
                        modes=("interactive", "readonly"),
                        required_bindings=image_choice_bindings,
                        submit_schema=image_choice_submit_schema,
                    ),
                    UiControlVariant(
                        name="hover_focus",
                        label="悬停放大",
                        tags=("hover_focus",),
                        modes=("interactive", "readonly"),
                        required_bindings=image_choice_bindings,
                        submit_schema=image_choice_submit_schema,
                    ),
                ),
                description="图片候选三选一控件，支持等宽、首图大和悬停放大变体。",
            ),
            UiControlDescriptor(
                control_id="ui.interaction.approval.v1",
                version="1.0.0",
                name="Approval",
                kind="interaction",
                tags=("approval", "human", "interactive"),
                variants=(
                    UiControlVariant(
                        name="default",
                        label="默认审批",
                        modes=("interactive",),
                    ),
                ),
                description="人工审批交互控件。",
            ),
            UiControlDescriptor(
                control_id="ui.fallback.schema_form.v1",
                version="1.0.0",
                name="Schema Form",
                kind="input",
                tags=("schema", "form", "fallback"),
                variants=(
                    UiControlVariant(
                        name="default",
                        label="默认表单",
                        modes=("input",),
                    ),
                ),
                description="基于 JSON Schema 的输入表单 fallback 控件。",
            ),
        ]
    )
