import { FormEvent, useState } from "react";

import { uploadAsset } from "../api/assets";

interface AssetUploadDialogProps {
  open: boolean;
  projectId?: string;
  onClose: () => void;
  onUploaded?: () => void;
}

export function AssetUploadDialog({ open, projectId, onClose, onUploaded }: AssetUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"project" | "global">("project");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("请选择文件");
      return;
    }
    if (scope === "project" && !projectId) {
      setError("当前项目尚未完成后端映射，无法上传项目资产");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await uploadAsset({
        file,
        scope,
        project_id: scope === "project" ? projectId : undefined,
        name: name || file.name,
        publish: true,
      });
      onUploaded?.();
      onClose();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "上传失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-backdrop">
      <section aria-labelledby="asset-upload-title" className="upload-dialog" role="dialog" aria-modal="true">
        <div className="dialog-header">
          <h2 id="asset-upload-title">上传文件</h2>
          <button className="icon-button" type="button" aria-label="关闭" onClick={onClose}>
            ×
          </button>
        </div>
        <form className="upload-form" onSubmit={handleSubmit}>
          <label>
            文件
            <input
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label>
            资产名称
            <input
              type="text"
              value={name}
              placeholder="例如：角色侧脸参考"
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            作用域
            <select
              value={scope}
              onChange={(event) => setScope(event.target.value as "project" | "global")}
            >
              <option value="project">当前项目</option>
              <option value="global">全局资产</option>
            </select>
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <div className="dialog-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="primary-button" disabled={submitting}>
              {submitting ? "上传中" : "开始上传"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
