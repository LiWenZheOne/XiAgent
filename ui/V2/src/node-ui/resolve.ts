import type { NodeUiControlConfig, TaskNodeExecution, WorkflowNodeSpec } from "../api/types";
import type { ImageChoiceItem } from "./types";

const defaultUserChoiceInteraction: NodeUiControlConfig = {
  control_id: "ui.choice.image_three.v1",
  variant: "equal_grid",
  mode: "interactive",
  bindings: {
    items_path: "$node.input.candidates",
    image_url_path: "image_url",
    value_path: "id",
  },
};

export function resolveNodeInteractionConfig(node: TaskNodeExecution, nodeSpec?: WorkflowNodeSpec): NodeUiControlConfig | null {
  if (nodeSpec?.ui?.controls?.interaction) return nodeSpec.ui.controls.interaction;
  if ((node.node_ref ?? node.ref) === "system.user_choice.v1") return defaultUserChoiceInteraction;
  return null;
}

export function readImageChoiceItems(config: NodeUiControlConfig, node: TaskNodeExecution): ImageChoiceItem[] {
  const bindings = config.bindings ?? {};
  const source = readBindingValue(bindings.items_path ?? "$node.input.candidates", node);
  const items = Array.isArray(source) ? source : [];
  const imageField = bindings.image_url_path ?? "image_url";
  const valueField = bindings.value_path ?? "id";
  return items
    .map((item, index) => normalizeChoiceItem(item, index, imageField, valueField))
    .filter((item): item is ImageChoiceItem => item !== null);
}

export function readBindingValue(path: string, node: TaskNodeExecution): unknown {
  if (path.startsWith("$node.input.")) return readObjectPath(node.input_snapshot, path.slice("$node.input.".length));
  if (path.startsWith("$node.output.")) return readObjectPath(node.output_snapshot, path.slice("$node.output.".length));
  if (path.startsWith("$node.metadata.")) return readObjectPath(node.metadata, path.slice("$node.metadata.".length));
  return undefined;
}

function normalizeChoiceItem(item: unknown, index: number, imageField: string, valueField: string): ImageChoiceItem | null {
  if (typeof item !== "object" || item === null) return null;
  const raw = item as Record<string, unknown>;
  const imageUrl = readStringField(raw, imageField) ?? readStringField(raw, "public_url") ?? readStringField(raw, "url");
  if (!imageUrl) return null;
  const value = readStringField(raw, valueField) ?? readStringField(raw, "id") ?? String(index);
  const label = readStringField(raw, "label") ?? readStringField(raw, "name") ?? `候选 ${index + 1}`;
  return { id: value, label, imageUrl, raw, index };
}

function readStringField(value: Record<string, unknown>, path: string): string | null {
  const next = readObjectPath(value, path);
  return typeof next === "string" && next ? next : null;
}

function readObjectPath(value: unknown, path: string): unknown {
  if (!path) return value;
  let current = value;
  for (const part of path.split(".")) {
    if (current === null || typeof current !== "object") return undefined;
    if (Array.isArray(current)) {
      const index = Number(part);
      if (!Number.isInteger(index)) return undefined;
      current = current[index];
    } else {
      current = (current as Record<string, unknown>)[part];
    }
  }
  return current;
}
