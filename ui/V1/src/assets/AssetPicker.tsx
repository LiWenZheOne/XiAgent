import type { AssetRecord } from "../api/types";

interface AssetPickerProps {
  assets: AssetRecord[];
  selectedUrls: string[];
  onChange(urls: string[]): void;
}

function assetPublicUrl(asset: AssetRecord): string | null {
  return typeof asset.metadata.public_url === "string" && asset.metadata.public_url
    ? asset.metadata.public_url
    : null;
}

export function AssetPicker({ assets, selectedUrls, onChange }: AssetPickerProps) {
  const selectableAssets = assets.filter(
    (asset) => (asset.mime_type ?? "").startsWith("image/") && assetPublicUrl(asset),
  );

  if (selectableAssets.length === 0) {
    return <p className="empty-state">没有可用于工作流的图片 URL，请先上传并发布图片资产。</p>;
  }

  return (
    <div className="asset-picker" aria-label="图片资产选择器">
      {selectableAssets.map((asset) => {
        const publicUrl = assetPublicUrl(asset);
        if (publicUrl === null) return null;
        const selected = selectedUrls.includes(publicUrl);
        return (
          <button
            className={selected ? "picker-card selected" : "picker-card"}
            key={asset.asset_id}
            type="button"
            onClick={() => onChange([publicUrl])}
          >
            <span className="picker-thumb" aria-hidden="true" />
            <span>
              <strong>选择 {asset.name}</strong>
              <small>{selected ? "已选择" : "使用 public_url"}</small>
            </span>
          </button>
        );
      })}
    </div>
  );
}
