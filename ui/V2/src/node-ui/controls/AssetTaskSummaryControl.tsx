import type { NodeUiControlProps } from "../types";
import { createStoredZip, extensionFromBlobOrUrl, safeAssetImageFileName } from "./assetZip";

interface SummaryImage {
  assetType: string;
  assetKey: string;
  fullName: string;
  imageUrl: string;
  source?: string;
  assetId?: string;
}

const typeLabels: Record<string, string> = {
  character: "角色",
  scene: "地点",
  asset: "地点",
  location: "地点",
  prop: "道具",
};

export function AssetTaskSummaryControl({ node }: NodeUiControlProps) {
  const source = summarySource(node.output_snapshot) ?? summarySource(node.input_snapshot) ?? {};
  const images = summaryImages(source);
  const ingestedCount = createdAssetIds(source).length || images.filter((image) => Boolean(image.assetId) || image.source === "library").length;
  const counts = countByType(images);

  async function exportZip() {
    const files = await Promise.all(images.map(async (image) => {
      const response = await fetch(image.imageUrl);
      if (!response.ok) throw new Error(`${image.fullName} 图像下载失败。`);
      const blob = await response.blob();
      const bytes = new Uint8Array(await blob.arrayBuffer());
      const ext = extensionFromBlobOrUrl(blob, image.imageUrl);
      return {
        name: `${safeAssetImageFileName(image.fullName)}${ext}`,
        bytes,
      };
    }));
    const zipBytes = createStoredZip(files);
    const zipBlob = new Blob([Uint8Array.from(zipBytes).buffer], { type: "application/zip" });
    const url = URL.createObjectURL(zipBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "资产图像.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="node-ui-readonly asset-task-summary-control">
      <header className="asset-task-summary-header">
        <div>
          <p className="eyebrow">任务完成</p>
          <h3>资产编目已完成</h3>
        </div>
        <button className="secondary-button" disabled={!images.length} type="button" onClick={() => void exportZip()}>
          导出资产为压缩包
        </button>
      </header>
      <div className="asset-task-summary-grid">
        <SummaryMetric label="总资产" value={images.length} />
        <SummaryMetric label="已入库" value={ingestedCount} />
        <SummaryMetric label="角色" value={counts.character} />
        <SummaryMetric label="地点" value={counts.scene} />
        <SummaryMetric label="道具" value={counts.prop} />
      </div>
      {images.length ? (
        <div className="asset-task-summary-list">
          {images.map((image) => (
            <article key={`${image.assetType}-${image.assetKey}-${image.imageUrl}`}>
              <img src={image.imageUrl} alt={`${image.fullName} 图像`} />
              <div>
                <strong>{image.fullName}</strong>
                <span>{typeLabels[image.assetType] ?? "资产"}</span>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted">暂无可导出的资产图像。</p>
      )}
    </section>
  );
}

function SummaryMetric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function summarySource(value: unknown): Record<string, unknown> | null {
  const record = recordValue(value);
  if (!record) return null;
  return recordValue(record.echo) ?? record;
}

function summaryImages(source: Record<string, unknown>): SummaryImage[] {
  const assetImages = arrayValue(source.asset_images);
  const nestedAssetImages = arrayValue(recordValue(source.asset_catalog)?.asset_images);
  return (assetImages.length ? assetImages : nestedAssetImages)
    .map((item) => recordValue(item))
    .filter((item): item is Record<string, unknown> => Boolean(item))
    .map((item, index) => {
      const assetType = textValue(item.asset_type) || "asset";
      const fullName = textValue(item.full_name) || textValue(item.name) || textValue(item.asset_key) || `资产_${index + 1}`;
      return {
        assetType,
        assetKey: textValue(item.asset_key) || fullName,
        fullName,
        imageUrl: textValue(item.image_url) || "",
        source: textValue(item.source),
        assetId: textValue(item.asset_id),
      };
    })
    .filter((item) => Boolean(item.imageUrl));
}

function countByType(images: SummaryImage[]): Record<"character" | "scene" | "prop", number> {
  return images.reduce(
    (counts, image) => {
      const key = image.assetType === "character" ? "character" : image.assetType === "prop" ? "prop" : "scene";
      counts[key] += 1;
      return counts;
    },
    { character: 0, scene: 0, prop: 0 },
  );
}

function createdAssetIds(source: Record<string, unknown>): string[] {
  return arrayValue(source.created_asset_ids).filter((item): item is string => typeof item === "string" && Boolean(item.trim()));
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : null;
}

function textValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}
