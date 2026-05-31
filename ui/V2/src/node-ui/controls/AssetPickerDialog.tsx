import { useEffect, useState } from "react";

import { searchAssets } from "../../api/assets";
import type { AssetRecord } from "../../api/types";
import { assetSearchScopeForProject } from "./assetPicker";

interface AssetPickerDialogProps {
  assetLabel: string;
  emptyText?: string;
  projectId?: string;
  targetName: string;
  tagName?: string;
  onClose: () => void;
  onClear?: () => void;
  onSelect: (asset: AssetRecord) => void;
}

export function AssetPickerDialog({
  assetLabel,
  emptyText = "没有找到对应类型的资产。",
  projectId,
  targetName,
  tagName,
  onClose,
  onClear,
  onSelect,
}: AssetPickerDialogProps) {
  const [keyword, setKeyword] = useState("");
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const searchScope = assetSearchScopeForProject(projectId);
    searchAssets({
      ...searchScope,
      keyword: keyword.trim() || undefined,
      tag_names: tagName ? [tagName] : undefined,
    })
      .then((items) => {
        if (!active) return;
        setAssets(tagName ? items : []);
      })
      .catch((nextError) => {
        if (active) setError(nextError instanceof Error ? nextError.message : "资产搜索失败。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [keyword, projectId, tagName]);

  return (
    <div className="confirm-backdrop" role="presentation">
      <section className="asset-picker-dialog" role="dialog" aria-modal="true" aria-label="选择匹配资产">
        <header>
          <div>
            <p className="eyebrow">选择{assetLabel}资产</p>
            <h3>{targetName}</h3>
          </div>
          <button className="secondary-button" type="button" onClick={onClose}>关闭</button>
        </header>
        <label className="asset-picker-search">
          <span>搜索资产</span>
          <input autoFocus placeholder={`搜索${assetLabel}资产`} value={keyword} onChange={(event) => setKeyword(event.target.value)} />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="asset-picker-list">
          {loading ? <p className="muted">正在搜索...</p> : null}
          {!loading && assets.length ? assets.map((asset) => (
            <button
              className="asset-picker-option"
              key={asset.asset_id}
              type="button"
              onClick={() => onSelect(asset)}
            >
              <strong>{asset.name}</strong>
              <span>{assetSummary(asset)}</span>
            </button>
          )) : null}
          {!loading && !assets.length ? <p className="muted">{emptyText}</p> : null}
        </div>
        {onClear ? (
          <div className="button-row end">
            <button className="secondary-button" type="button" onClick={onClear}>
              标记为未匹配
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function assetSummary(asset: AssetRecord): string {
  return asset.scope === "project" ? "项目资产" : "全局资产";
}
