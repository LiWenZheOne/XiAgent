import { useState } from "react";

import type { NodeUiControlProps } from "../types";

export function ApprovalControl({ busy = false, config, node, onSubmit }: NodeUiControlProps) {
  const readonly = config.mode === "readonly";
  const submitted = readSubmittedApproval(node.output_snapshot);
  const [comment, setComment] = useState(submitted.comment);
  return (
    <section className="interaction-panel">
      <div>
        <p className="eyebrow">{readonly ? "已提交确认" : "等待人工确认"}</p>
        <h3>继续运行需要你的确认</h3>
      </div>
      <label className="form-field">
        <span>确认意见</span>
        <textarea aria-label="确认意见" readOnly={readonly} value={readonly ? submitted.comment : comment} onChange={(event) => setComment(event.target.value)} />
      </label>
      <div className="button-row">
        <button className="primary-button" disabled={busy || readonly} type="button" onClick={() => onSubmit?.({ decision: "approved", approved: true, comment })}>
          同意并继续
        </button>
        <button className="secondary-button danger" disabled={busy || readonly} type="button" onClick={() => onSubmit?.({ decision: "rejected", approved: false, comment })}>
          拒绝
        </button>
      </div>
    </section>
  );
}

function readSubmittedApproval(value: unknown): { approved: boolean | null; comment: string } {
  if (typeof value !== "object" || value === null) return { approved: null, comment: "" };
  const record = value as Record<string, unknown>;
  return {
    approved: typeof record.approved === "boolean" ? record.approved : null,
    comment: typeof record.comment === "string" ? record.comment : "",
  };
}
