import { ApprovalControl } from "./controls/ApprovalControl";
import { FallbackValueControl } from "./controls/FallbackValueControl";
import { ImageCandidatesControl } from "./controls/ImageCandidatesControl";
import { ImageChoiceThreeControl } from "./controls/ImageChoiceThreeControl";
import { SchemaFormControl } from "./controls/SchemaFormControl";
import type { NodeUiComponent } from "./types";

export const nodeUiRegistry: Record<string, NodeUiComponent> = {
  "ui.display.value.v1": FallbackValueControl,
  "ui.display.image_candidates.v1": ImageCandidatesControl,
  "ui.choice.image_three.v1": ImageChoiceThreeControl,
  "ui.interaction.approval.v1": ApprovalControl,
  "ui.fallback.schema_form.v1": SchemaFormControl,
};

export function getNodeUiControl(controlId: string): NodeUiComponent {
  return nodeUiRegistry[controlId] ?? FallbackValueControl;
}

export { resolveNodeInteractionConfig } from "./resolve";
