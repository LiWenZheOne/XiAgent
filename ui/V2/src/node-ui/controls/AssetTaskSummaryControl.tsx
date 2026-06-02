import { useState } from "react";

import { downloadAssetContent, getAsset } from "../../api/assets";
import type { AssetRecord } from "../../api/types";
import { assetNameFromTagNames, assetTagNamesForCatalogAsset, assetTagNamesFromName } from "../../utils/assetNaming";
import type { NodeUiControlProps } from "../types";
import { createStoredZip, extensionFromBlobOrUrl, safeAssetImageFileName } from "./assetZip";

interface SummaryImage {
  assetType: string;
  assetKey: string;
  fullName: string;
  variantName?: string;
  accessories?: string;
  imageUrl: string;
  source?: string;
  assetId?: string;
}

interface ExportImage {
  assetType: string;
  assetKey: string;
  fullName: string;
  variantName?: string;
  accessories?: string;
  imageUrl?: string;
  assetId?: string;
}

export function AssetTaskSummaryControl({ node, projectId }: NodeUiControlProps) {
  const source = summarySource(node.output_snapshot) ?? summarySource(node.input_snapshot) ?? {};
  const images = summaryImages(source);
  const assetIds = createdAssetIds(source);
  const catalogCounts = countCatalogAssets(source);
  const ingestedCount = assetIds.length || images.filter((image) => Boolean(image.assetId) || image.source === "library").length;
  const counts = catalogCounts.total ? catalogCounts : countByType(images);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  async function exportZip() {
    if (exporting) return;
    setExporting(true);
    setExportError("");
    try {
      const exportImages = await resolveExportImages({ images, assetIds, projectId });
      if (!exportImages.length) {
        setExportError("暂无可导出的资产图像。");
        return;
      }
      const files = await Promise.all(exportImages.map(async (image) => {
        const blob = image.assetId
          ? await downloadAssetContent(image.assetId, projectId && projectId !== "global" ? projectId : undefined)
          : await fetchImageBlob(image);
        const bytes = new Uint8Array(await blob.arrayBuffer());
        const ext = extensionFromBlobOrUrl(blob, image.imageUrl ?? "");
        return {
          name: `${safeAssetImageFileName(exportFileBaseName(image))}${ext}`,
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
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "资产压缩包导出失败。");
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="node-ui-readonly asset-task-summary-control">
      <header className="asset-task-summary-header">
        <div>
          <p className="eyebrow">任务完成</p>
          <h3>资产编目已完成</h3>
        </div>
        <button className="secondary-button" disabled={exporting || (!images.length && !assetIds.length)} type="button" onClick={() => void exportZip()}>
          {exporting ? "导出中..." : "导出资产为压缩包"}
        </button>
      </header>
      {exportError ? <p className="form-error">{exportError}</p> : null}
      <div className="asset-task-summary-grid">
        <SummaryMetric label="总资产" value={counts.total} />
        <SummaryMetric label="已入库" value={ingestedCount} />
        <SummaryMetric label="角色" value={counts.character} />
        <SummaryMetric label="地点" value={counts.scene} />
        <SummaryMetric label="道具" value={counts.prop} />
      </div>
    </section>
  );
}

async function resolveExportImages(options: {
  images: SummaryImage[];
  assetIds: string[];
  projectId?: string;
}): Promise<ExportImage[]> {
  const exportImages: ExportImage[] = options.images.map((image, index) => ({
    assetType: image.assetType,
    assetKey: image.assetKey,
    fullName: image.fullName,
    variantName: image.variantName,
    accessories: image.accessories,
    imageUrl: image.imageUrl,
    assetId: image.assetId || options.assetIds[index],
  }));
  const byAssetId = new Map(exportImages.filter((image) => image.assetId).map((image) => [image.assetId as string, image]));
  const missingAssetIds = options.assetIds.filter((assetId) => !byAssetId.has(assetId));
  if (!missingAssetIds.length) return exportImages;
  const assets = await Promise.all(missingAssetIds.map((assetId) => getAsset(assetId, options.projectId && options.projectId !== "global" ? options.projectId : undefined)));
  return [
    ...exportImages,
    ...assets.filter(isImageAsset).map((asset) => ({
      assetType: textValue(asset.metadata?.asset_type) || textValue(asset.metadata?.type) || "asset",
      assetKey: asset.name,
      fullName: asset.name,
      variantName: stringList(asset.metadata?.asset_tags)[0],
      accessories: stringList(asset.metadata?.asset_tags).slice(1).join("、"),
      imageUrl: publicUrlFromAsset(asset),
      assetId: asset.asset_id,
    })),
  ];
}

async function fetchImageBlob(image: ExportImage): Promise<Blob> {
  if (!image.imageUrl) throw new Error(`${image.fullName} 缺少可下载图像。`);
  const response = await fetch(image.imageUrl);
  if (!response.ok) throw new Error(`${image.fullName} 图像下载失败。`);
  return response.blob();
}

function isImageAsset(asset: AssetRecord): boolean {
  return asset.asset_type === "file" && (asset.mime_type?.startsWith("image/") || Boolean(publicUrlFromAsset(asset)));
}

function publicUrlFromAsset(asset: AssetRecord): string {
  return textValue(recordValue(asset.metadata)?.public_url) || "";
}

function exportFileBaseName(image: ExportImage): string {
  const parsedTags = assetTagNamesFromName(image.fullName);
  if (parsedTags.length) return assetNameFromTagNames(parsedTags);
  const group = image.assetType === "character"
    ? "character"
    : image.assetType === "prop"
      ? "prop"
      : image.assetType === "scene"
        ? "scene"
        : "asset";
  const parts = splitAssetName(image.fullName);
  if (group === "character") {
    const name = image.assetKey && !assetTagNamesFromName(image.assetKey).length
      ? image.assetKey
      : parts[0] || image.fullName;
    return assetNameFromTagNames(assetTagNamesForCatalogAsset({
      group,
      name,
      variantName: image.variantName || parts[1] || "默认",
      accessories: image.accessories || parts.slice(2).join("_"),
    }));
  }
  if (group === "scene" || group === "prop") {
    return assetNameFromTagNames(assetTagNamesForCatalogAsset({
      group,
      name: image.assetKey || parts[0] || image.fullName,
      variantName: image.variantName || parts[1],
      accessories: image.accessories || parts.slice(2).join("_"),
    }));
  }
  return image.fullName;
}

function splitAssetName(value: string): string[] {
  const parsedTags = assetTagNamesFromName(value);
  const parts = parsedTags.length ? parsedTags.slice(1) : value.split(/[_＿]/).map((item) => item.trim()).filter(Boolean);
  return parts;
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
      const fullName = textValue(item.asset_name) || textValue(item.name) || `资产_${index + 1}`;
      const assetTags = stringList(item.asset_tags);
      return {
        assetType,
        assetKey: fullName,
        fullName,
        variantName: assetTags[0],
        accessories: assetTags.slice(1).join("、"),
        imageUrl: textValue(item.image_url) || "",
        source: textValue(item.source),
        assetId: textValue(item.asset_id),
      };
    })
    .filter((item) => Boolean(item.imageUrl));
}

function countByType(images: SummaryImage[]): SummaryCounts {
  return images.reduce(
    (counts, image) => {
      const key = image.assetType === "character" ? "character" : image.assetType === "prop" ? "prop" : "scene";
      counts[key] += 1;
      counts.total += 1;
      return counts;
    },
    emptyCounts(),
  );
}

interface SummaryCounts {
  total: number;
  character: number;
  scene: number;
  prop: number;
}

function countCatalogAssets(source: Record<string, unknown>): SummaryCounts {
  const catalog = recordValue(recordValue(source.asset_catalog)?.approved_assets)
    ?? recordValue(source.approved_assets)
    ?? recordValue(source.asset_catalog);
  if (!catalog) return emptyCounts();
  const character = arrayValue(catalog.characters).length;
  const scene = arrayValue(catalog.assets).length + arrayValue(catalog.scenes).length + arrayValue(catalog.locations).length;
  const prop = arrayValue(catalog.props).length;
  return { total: character + scene + prop, character, scene, prop };
}

function emptyCounts(): SummaryCounts {
  return { total: 0, character: 0, scene: 0, prop: 0 };
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

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).map((item) => item.trim());
  if (typeof value === "string") return value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean);
  return [];
}
