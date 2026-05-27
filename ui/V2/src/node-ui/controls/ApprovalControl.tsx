import { useState } from "react";

import type { NodeUiControlProps } from "../types";

export function ApprovalControl({ busy = false, onSubmit }: NodeUiControlProps) {
  const [comment, setComment] = useState("");
  return (
    <section className="interaction-panel">
      <div>
        <p className="eyebrow">等待人工确认</p>
        <h3>继续运行需要你的确认</h3>
      </div>
      <label className="form-field">
        <span>确认意见</span>
        <textarea aria-label="确认意见" value={comment} onChange={(event) => setComment(event.target.value)} />
      </label>
      <div className="button-row">
        <button className="primary-button" disabled={busy} type="button" onClick={() => onSubmit?.({ decision: "approved", approved: true, comment })}>
          同意并继续
        </button>
        <button className="secondary-button danger" disabled={busy} type="button" onClick={() => onSubmit?.({ decision: "rejected", approved: false, comment })}>
          拒绝
        </button>
      </div>
    </section>
  );
}
