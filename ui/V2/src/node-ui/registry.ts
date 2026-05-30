import { ApprovalControl } from "./controls/ApprovalControl";
import { AssetImageCardsControl } from "./controls/AssetImageCardsControl";
import { AssetSummaryTableControl } from "./controls/AssetSummaryTableControl";
import { AssetTaskSummaryControl } from "./controls/AssetTaskSummaryControl";
import { FallbackValueControl } from "./controls/FallbackValueControl";
import { ImageCandidatesControl } from "./controls/ImageCandidatesControl";
import { ImageChoiceThreeControl } from "./controls/ImageChoiceThreeControl";
import { ImageViewerControl } from "./controls/ImageViewerControl";
import { SchemaFormControl } from "./controls/SchemaFormControl";
import { ScriptTextInputControl } from "./controls/ScriptTextInputControl";
import { ValueDisplayControl } from "./controls/ValueDisplayControl";
import type { NodeUiComponent } from "./types";

export const nodeUiRegistry: Record<string, NodeUiComponent> = {
  "ui.display.value.v1": ValueDisplayControl,
  "ui.display.image_candidates.v1": ImageCandidatesControl,
  "ui.display.image_viewer.v1": ImageViewerControl,
  "ui.choice.image_three.v1": ImageChoiceThreeControl,
  "ui.interaction.approval.v1": ApprovalControl,
  "ui.interaction.asset_image_cards.v1": AssetImageCardsControl,
  "ui.interaction.asset_summary_table.v1": AssetSummaryTableControl,
  "ui.display.asset_task_summary.v1": AssetTaskSummaryControl,
  "ui.input.schema_form.v1": SchemaFormControl,
  "ui.input.script_text.v1": ScriptTextInputControl,
  "ui.fallback.schema_form.v1": SchemaFormControl,
};

export function getNodeUiControl(controlId: string): NodeUiComponent {
  return nodeUiRegistry[controlId] ?? FallbackValueControl;
}

export { resolveNodeControlConfig, resolveNodeInteractionConfig } from "./resolve";
