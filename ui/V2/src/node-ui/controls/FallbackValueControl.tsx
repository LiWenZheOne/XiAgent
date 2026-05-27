import type { NodeUiControlProps } from "../types";

export function FallbackValueControl({ node }: NodeUiControlProps) {
  return (
    <section className="interaction-panel">
      <p className="muted">该控件尚未在 V2 注册，已使用默认任务交互。</p>
      <code>{node.node_id}</code>
    </section>
  );
}
