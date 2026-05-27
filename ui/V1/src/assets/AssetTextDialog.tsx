import { FormEvent, useState } from "react";

import { createTextAsset } from "../api/assets";

interface AssetTextDialogProps {
  open: boolean;
  projectId?: string;
  onClose: () => void;
  onCreated?: () => void;
}

export function AssetTextDialog({ open, projectId, onClose, onCreated }: AssetTextDialogProps) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [scope, setScope] = useState<"project" | "global">("project");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanName = name.trim();
    const cleanText = text.trim();
    if (!cleanName) {
      setError("请输入资产名称");
      return;
    }
    if (!cleanText) {
      setError("请输入文字内容");
      return;
    }
    if (scope === "project" && !projectId) {
      setError("当前项目尚未完成后端映射，无法创建项目资产");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await createTextAsset({
        scope,
        project_id: scope === "project" ? projectId : undefined,
        name: cleanName,
        text: cleanText,
        metadata: { source: "ui" },
      });
      onCreated?.();
      onClose();
      setName("");
      setText("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "创建文字资产失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-backdrop">
      <section aria-labelledby="asset-text-title" className="upload-dialog asset-text-dialog" role="dialog" aria-modal="true">
        <div className="dialog-header">
          <h2 id="asset-text-title">新建文字资产</h2>
          <button className="icon-button" type="button" aria-label="关闭" onClick={onClose}>
            ×
          </button>
        </div>
        <form className="upload-form" onSubmit={handleSubmit}>
          <label>
            资产名称
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：角色设定片段" />
          </label>
          <label>
            作用域
            <select value={scope} onChange={(event) => setScope(event.target.value as "project" | "global")}>
              <option value="project">当前项目</option>
              <option value="global">全局资产</option>
            </select>
          </label>
          <label>
            文字内容
            <textarea value={text} onChange={(event) => setText(event.target.value)} rows={8} />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <div className="dialog-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="primary-button" disabled={submitting}>
              {submitting ? "创建中" : "创建文字资产"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
