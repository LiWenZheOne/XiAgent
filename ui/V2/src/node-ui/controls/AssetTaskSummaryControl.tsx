import { type PointerEvent, type WheelEvent, useEffect, useRef, useState } from "react";

import { downloadAssetContent, downloadAssetThumbnail, getAsset } from "../../api/assets";
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
  const generationSummary = readGenerationSummary(source);
  const ingestedCount = assetIds.length || images.filter((image) => Boolean(image.assetId) || image.source === "library").length;
  const counts = catalogCounts.total ? catalogCounts : countByType(images);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [previewImage, setPreviewImage] = useState<SummaryImage | null>(null);

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
        <SummaryMetric label="新增" value={generationSummary?.newAssetCount ?? Math.max(counts.total - ingestedCount, 0)} />
        <SummaryMetric label="已匹配" value={generationSummary?.matchedAssetCount ?? ingestedCount} />
        <SummaryMetric label="已入库" value={ingestedCount} />
        <SummaryMetric label="角色" value={counts.character} />
        <SummaryMetric label="地点" value={counts.scene} />
        <SummaryMetric label="道具" value={counts.prop} />
      </div>
      {images.length ? (
        <div className="asset-task-summary-list" aria-label="最终资产图像">
          {images.map((image, index) => (
            <article key={`${image.assetId ?? image.imageUrl}-${index}`}>
              <div className="asset-task-summary-thumb">
                <SummaryImagePreview image={image} projectId={projectId} />
                <button
                  aria-label="全屏查看图像"
                  className="asset-zoom-button"
                  title="全屏查看"
                  type="button"
                  onClick={() => setPreviewImage(image)}
                >
                  ⛶
                </button>
              </div>
              <div>
                <strong>{image.fullName}</strong>
                <span>{summaryImageMeta(image)}</span>
              </div>
            </article>
          ))}
        </div>
      ) : null}
      {previewImage ? (
        <SummaryImageFullscreenViewer image={previewImage} projectId={projectId} onClose={() => setPreviewImage(null)} />
      ) : null}
    </section>
  );
}

function SummaryImagePreview({ image, projectId }: { image: SummaryImage; projectId?: string }) {
  const [objectUrl, setObjectUrl] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setObjectUrl("");
    setFailed(false);
    if (!image.assetId || typeof URL.createObjectURL !== "function") return;
    let active = true;
    downloadAssetThumbnail(image.assetId, assetProjectId(projectId))
      .then((blob) => {
        const nextUrl = URL.createObjectURL(blob);
        if (!active) {
          URL.revokeObjectURL(nextUrl);
          return;
        }
        setObjectUrl(nextUrl);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [image.assetId, projectId]);

  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [objectUrl]);

  const src = objectUrl || (failed || !image.assetId ? image.imageUrl : "");
  return src ? <img alt={`${image.fullName} 图像`} loading="lazy" src={src} /> : <span className="asset-task-summary-image-loading">加载缩略图...</span>;
}

function SummaryImageFullscreenViewer({ image, projectId, onClose }: { image: SummaryImage; projectId?: string; onClose: () => void }) {
  const [imageUrl, setImageUrl] = useState("");
  const [objectUrl, setObjectUrl] = useState("");
  const [loading, setLoading] = useState(Boolean(image.assetId));
  const [error, setError] = useState("");
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef({ pointerId: -1, startX: 0, startY: 0, originX: 0, originY: 0 });

  useEffect(() => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
    setImageUrl(image.assetId ? "" : image.imageUrl);
    setObjectUrl("");
    setError("");
    setLoading(Boolean(image.assetId));
    if (!image.assetId) return;
    let active = true;
    downloadAssetContent(image.assetId, assetProjectId(projectId))
      .then((blob) => {
        const nextUrl = URL.createObjectURL(blob);
        if (!active) {
          URL.revokeObjectURL(nextUrl);
          return;
        }
        setObjectUrl(nextUrl);
        setImageUrl(nextUrl);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        if (image.imageUrl) {
          setImageUrl(image.imageUrl);
        } else {
          setError("无法加载原图");
        }
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [image.assetId, image.imageUrl, projectId]);

  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [objectUrl]);

  useEffect(() => {
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function handleWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    setScale((current) => clamp(current * (event.deltaY < 0 ? 1.12 : 0.88), 0.2, 8));
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!imageUrl || event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: offset.x,
      originY: offset.y,
    };
    setDragging(true);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragging || dragRef.current.pointerId !== event.pointerId) return;
    setOffset({
      x: dragRef.current.originX + event.clientX - dragRef.current.startX,
      y: dragRef.current.originY + event.clientY - dragRef.current.startY,
    });
  }

  function handlePointerEnd(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current.pointerId === event.pointerId) {
      setDragging(false);
      dragRef.current.pointerId = -1;
    }
  }

  return (
    <div aria-label={`全屏查看 ${image.fullName}`} aria-modal="true" className="asset-fullscreen-viewer" role="dialog" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div className="asset-fullscreen-toolbar" onMouseDown={(event) => event.stopPropagation()}>
        <strong>{image.fullName}</strong>
        <span>{Math.round(scale * 100)}%</span>
        <button className="secondary-button" type="button" onClick={() => {
          setScale(1);
          setOffset({ x: 0, y: 0 });
        }}>
          100%
        </button>
        <button className="secondary-button" type="button" onClick={onClose}>
          关闭
        </button>
      </div>
      <div
        className={dragging ? "asset-fullscreen-stage dragging" : "asset-fullscreen-stage"}
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose();
          event.stopPropagation();
        }}
        onPointerCancel={handlePointerEnd}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onWheel={handleWheel}
      >
        {loading ? <p>正在加载原图...</p> : null}
        {error ? <p>{error}</p> : null}
        {imageUrl ? (
          <img
            alt={image.fullName}
            draggable={false}
            src={imageUrl}
            style={{ transform: `translate3d(${offset.x}px, ${offset.y}px, 0) scale(${scale})` }}
          />
        ) : null}
      </div>
    </div>
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

function summaryImageMeta(image: SummaryImage): string {
  const typeLabel = image.assetType === "character" ? "角色" : image.assetType === "prop" ? "道具" : image.assetType === "scene" ? "地点" : "资产";
  const details = [image.variantName, image.accessories].filter(Boolean).join(" · ");
  return details ? `${typeLabel} · ${details}` : typeLabel;
}

function assetProjectId(projectId?: string): string | undefined {
  return projectId && projectId !== "global" ? projectId : undefined;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
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

function readGenerationSummary(source: Record<string, unknown>): { newAssetCount: number; matchedAssetCount: number } | null {
  const summary = recordValue(source.generation_summary)
    ?? recordValue(recordValue(source.asset_catalog)?.generation_summary);
  if (!summary) return null;
  return {
    newAssetCount: numberValue(summary.new_asset_count),
    matchedAssetCount: numberValue(summary.matched_asset_count),
  };
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

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).map((item) => item.trim());
  if (typeof value === "string") return value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean);
  return [];
}
