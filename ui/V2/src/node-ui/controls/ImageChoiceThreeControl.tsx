import { useMemo, useState } from "react";

import { readImageChoiceItems } from "../resolve";
import type { ImageChoiceItem, NodeUiControlProps } from "../types";

export function ImageChoiceThreeControl({ config, node, busy = false, preview = false, onSubmit }: NodeUiControlProps) {
  const [selectedId, setSelectedId] = useState("");
  const items = useMemo(() => readImageChoiceItems(config, node), [config, node]);
  const variant = config.variant ?? "equal_grid";
  const readonly = config.mode === "readonly";
  const submittedId = useMemo(() => readSubmittedChoiceId(node, items), [items, node]);
  const activeSelectedId = readonly ? submittedId : selectedId;

  function handleSelect(item: ImageChoiceItem) {
    if (readonly) return;
    setSelectedId(item.id);
    if (!preview) {
      onSubmit?.({
        selected_id: item.id,
        selected_index: item.index,
        selected_item: item.raw,
        selected_image_url: item.imageUrl,
      });
    }
  }

  if (!items.length) {
    return (
      <section className="interaction-panel">
        <p className="muted">当前节点没有可选择的图片候选。</p>
      </section>
    );
  }

  return (
    <section className="interaction-panel node-ui-choice" aria-label="图片三选一">
      <div>
        <p className="eyebrow">{readonly ? "已提交选择" : "等待用户选择"}</p>
        <h3>{readQuestion(node) || "请选择一张图片继续运行"}</h3>
      </div>
      <div className={`image-choice-grid ${variant}`}>
        {items.map((item) => (
          <button
            aria-label={`选择 ${item.label}`}
            className={activeSelectedId === item.id ? "image-choice-card active" : "image-choice-card"}
            disabled={busy || readonly}
            key={`${item.id}-${item.index}`}
            type="button"
            onClick={() => handleSelect(item)}
          >
            <img alt={item.label} src={item.imageUrl} />
            <span>{item.label}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function readQuestion(node: NodeUiControlProps["node"]): string {
  const metadataQuestion = node.metadata?.question;
  if (typeof metadataQuestion === "string") return metadataQuestion;
  const input = node.input_snapshot;
  if (typeof input === "object" && input !== null) {
    const question = (input as Record<string, unknown>).question;
    if (typeof question === "string") return question;
  }
  return "";
}

function readSubmittedChoiceId(node: NodeUiControlProps["node"], items: ImageChoiceItem[]): string {
  const output = node.output_snapshot;
  if (typeof output !== "object" || output === null) return "";
  const record = output as Record<string, unknown>;
  if (typeof record.selected_id === "string") return record.selected_id;
  if (typeof record.selected_image_url === "string") {
    const matched = items.find((item) => item.imageUrl === record.selected_image_url);
    if (matched) return matched.id;
  }
  if (typeof record.selected_index === "number") return items[record.selected_index]?.id ?? "";
  return "";
}
