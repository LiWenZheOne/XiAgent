import type { NodeUiControlProps } from "../types";

export function SchemaFormControl({ node }: NodeUiControlProps) {
  return (
    <section className="interaction-panel">
      <p className="muted">Schema 表单控件已注册；当前任务继续使用页面表单渲染。</p>
      <code>{node.node_id}</code>
    </section>
  );
}
