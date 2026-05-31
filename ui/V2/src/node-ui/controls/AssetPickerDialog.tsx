import { useEffect, useMemo, useState } from "react";

import { downloadAssetContent, listAssetTagsForAsset, searchAssets } from "../../api/assets";
import type { AssetRecord } from "../../api/types";
import { assetSearchScopeForProject } from "./assetPicker";

interface AssetPickerDialogProps {
  assetLabel: string;
  emptyText?: string;
  initialAssetId?: string;
  initialAssetName?: string;
  projectId?: string;
  targetName: string;
  tagName?: string;
  onClose: () => void;
  onClear?: () => void;
  onSelect: (asset: AssetRecord) => void;
}

interface PickerAssetItem {
  asset: AssetRecord;
  tagNames: string[];
  nameTag: string;
  variantLabel: string;
}

export function AssetPickerDialog({
  assetLabel,
  emptyText = "没有找到对应类型的资产。",
  initialAssetId,
  initialAssetName,
  projectId,
  targetName,
  tagName,
  onClose,
  onClear,
  onSelect,
}: AssetPickerDialogProps) {
  const [keyword, setKeyword] = useState("");
  const [assetItems, setAssetItems] = useState<PickerAssetItem[]>([]);
  const [initialSelectionApplied, setInitialSelectionApplied] = useState(false);
  const [selectedName, setSelectedName] = useState("");
  const [selectedVariant, setSelectedVariant] = useState("");
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const nameOptions = useMemo(() => buildNameOptions(assetItems), [assetItems]);
  const variantOptions = useMemo(() => buildVariantOptions(assetItems, selectedName), [assetItems, selectedName]);
  const visibleItems = useMemo(() => assetItems.filter((item) => {
    if (selectedName && item.nameTag !== selectedName) return false;
    if (selectedVariant && item.variantLabel !== selectedVariant) return false;
    return isImageAsset(item.asset);
  }), [assetItems, selectedName, selectedVariant]);

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
        return Promise.all((tagName ? items : []).map(async (asset): Promise<PickerAssetItem> => {
          const tagNames = await assetTagNames(asset);
          const naming = assetNaming(asset, tagName, tagNames);
          return {
            asset,
            tagNames,
            nameTag: naming.nameTag,
            variantLabel: naming.variantLabel,
          };
        }));
      })
      .then((items) => {
        if (!active || !items) return;
        setAssetItems(items);
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

  useEffect(() => {
    setInitialSelectionApplied(false);
    setSelectedName("");
    setSelectedVariant("");
  }, [initialAssetName]);

  useEffect(() => {
    let active = true;
    const objectUrls: string[] = [];
    const imageAssets = visibleItems.map((item) => item.asset).filter((asset) => shouldLoadContentPreview(asset));
    if (!imageAssets.length) {
      setPreviewUrls({});
      return () => undefined;
    }

    Promise.all(imageAssets.map(async (asset) => {
      try {
        const blob = await downloadAssetContent(asset.asset_id, contentProjectId(asset, projectId));
        if (!blob.type.startsWith("image/")) return null;
        const url = URL.createObjectURL(blob);
        objectUrls.push(url);
        return [asset.asset_id, url] as const;
      } catch {
        return null;
      }
    })).then((items) => {
      if (!active) return;
      setPreviewUrls(Object.fromEntries(items.filter((item): item is readonly [string, string] => Boolean(item))));
    });

    return () => {
      active = false;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [visibleItems, projectId]);

  useEffect(() => {
    if (!initialSelectionApplied && assetItems.length) {
      const matchedItem = initialAssetId ? assetItems.find((item) => item.asset.asset_id === initialAssetId) : undefined;
      const initial = matchedItem ?? (initialAssetName ? {
        ...assetNaming({ name: initialAssetName, metadata: {} } as AssetRecord, tagName, []),
        asset: null,
        tagNames: [],
      } : null);
      const initialName = initial?.nameTag || targetName;
      const matchedName = nameOptions.find((option) => option.name === initialName)?.name
        ?? nameOptions.find((option) => option.name === targetName)?.name
        ?? "";
      if (matchedName) {
        const variantFromInitial = initial?.variantLabel ?? "";
        const hasVariant = variantFromInitial
          ? buildVariantOptions(assetItems, matchedName).some((option) => option.label === variantFromInitial)
          : false;
        setSelectedName(matchedName);
        setSelectedVariant(hasVariant ? variantFromInitial : "");
      }
      setInitialSelectionApplied(true);
      return;
    }
    if (selectedName && !nameOptions.some((option) => option.name === selectedName)) {
      setSelectedName("");
      setSelectedVariant("");
      return;
    }
    if (selectedVariant && !variantOptions.some((option) => option.label === selectedVariant)) {
      setSelectedVariant("");
    }
  }, [assetItems, initialAssetId, initialAssetName, initialSelectionApplied, nameOptions, selectedName, selectedVariant, tagName, targetName, variantOptions]);

  return (
    <div className="confirm-backdrop" role="presentation">
      <section className="asset-picker-dialog asset-picker-dialog--cards" role="dialog" aria-modal="true" aria-label="选择匹配资产">
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
        <div className="asset-picker-content">
          <aside className="asset-picker-filters" aria-label="资产标签筛选">
            <section>
              <p className="eyebrow">名称</p>
              <div className="asset-picker-filter-list">
                <button className={!selectedName ? "active" : ""} type="button" onClick={() => { setSelectedName(""); setSelectedVariant(""); }}>
                  全部名称 <span>{assetItems.filter((item) => isImageAsset(item.asset)).length}</span>
                </button>
                {nameOptions.map((option) => (
                  <button
                    aria-label={`选择名称 ${option.name}`}
                    className={selectedName === option.name ? "active" : ""}
                    key={option.name}
                    type="button"
                    onClick={() => {
                      setSelectedName(option.name);
                      setSelectedVariant("");
                    }}
                  >
                    {option.name} <span>{option.count}</span>
                  </button>
                ))}
              </div>
            </section>
            <section>
              <p className="eyebrow">变体名</p>
              <div className="asset-picker-filter-list">
                <button className={!selectedVariant ? "active" : ""} type="button" onClick={() => setSelectedVariant("")}>
                  全部变体 <span>{variantOptions.reduce((count, option) => count + option.count, 0)}</span>
                </button>
                {variantOptions.map((option) => (
                  <button
                    aria-label={`选择变体 ${option.label}`}
                    className={selectedVariant === option.label ? "active" : ""}
                    key={option.label}
                    type="button"
                    onClick={() => setSelectedVariant(option.label)}
                  >
                    {option.label} <span>{option.count}</span>
                  </button>
                ))}
              </div>
            </section>
          </aside>
          <div className="asset-picker-list">
            {loading ? <p className="muted">正在搜索...</p> : null}
            {!loading && visibleItems.length ? visibleItems.map(({ asset, variantLabel }) => (
              <button
                aria-label={`选择资产 ${asset.name}`}
                className="asset-picker-option"
                key={asset.asset_id}
                type="button"
                onClick={() => onSelect(asset)}
              >
                <span className="asset-picker-thumb">
                  {assetPreviewUrl(asset, previewUrls) ? (
                    <img alt={`${asset.name} 图像`} src={assetPreviewUrl(asset, previewUrls)} />
                  ) : (
                    <span>{asset.asset_type === "text" ? "文" : "图"}</span>
                  )}
                </span>
                <span className="asset-picker-option-body">
                  <strong className="asset-picker-name">{asset.name}</strong>
                  <span>{variantLabel} · {assetSummary(asset)}</span>
                </span>
              </button>
            )) : null}
            {!loading && !visibleItems.length ? <p className="muted">{assetItems.length ? "当前筛选下没有图像资产。" : emptyText}</p> : null}
          </div>
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

async function assetTagNames(asset: AssetRecord): Promise<string[]> {
  try {
    const tags = await listAssetTagsForAsset(asset.asset_id);
    return uniqueStrings([
      ...tags.map((tag) => tag.name),
      ...metadataTags(asset),
      ...splitAssetName(asset.name),
    ]);
  } catch {
    return uniqueStrings([...metadataTags(asset), ...splitAssetName(asset.name)]);
  }
}

function assetNaming(asset: AssetRecord, typeTag: string | undefined, tagNames: string[]): { nameTag: string; variantLabel: string } {
  const parts = splitAssetName(asset.name);
  if (typeTag && parts[0] === typeTag && parts[1]) {
    return {
      nameTag: parts[1],
      variantLabel: parts[2] || "默认",
    };
  }
  if (parts.length >= 2) {
    return {
      nameTag: parts[0],
      variantLabel: parts[1] || "默认",
    };
  }
  const usefulTags = tagNames.filter((tag) => tag && tag !== typeTag);
  return {
    nameTag: usefulTags[0] || asset.name,
    variantLabel: usefulTags[1] || "默认",
  };
}

function buildNameOptions(items: PickerAssetItem[]): Array<{ name: string; count: number }> {
  const counts = new Map<string, number>();
  for (const item of items) {
    if (!isImageAsset(item.asset)) continue;
    counts.set(item.nameTag, (counts.get(item.nameTag) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((left, right) => left.name.localeCompare(right.name, "zh-Hans-CN"));
}

function buildVariantOptions(items: PickerAssetItem[], selectedName: string): Array<{ label: string; count: number }> {
  const counts = new Map<string, number>();
  for (const item of items) {
    if (!isImageAsset(item.asset)) continue;
    if (selectedName && item.nameTag !== selectedName) continue;
    counts.set(item.variantLabel, (counts.get(item.variantLabel) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => left.label.localeCompare(right.label, "zh-Hans-CN"));
}

function assetSummary(asset: AssetRecord): string {
  const scopeLabel = asset.scope === "project" ? "项目资产" : "全局资产";
  const typeLabel = asset.asset_type === "text" ? "文字" : asset.mime_type?.startsWith("image/") ? "图像" : asset.asset_type;
  return `${scopeLabel} · ${typeLabel}`;
}

function assetPreviewUrl(asset: AssetRecord, previewUrls: Record<string, string>): string {
  if (previewUrls[asset.asset_id]) return previewUrls[asset.asset_id];
  if (shouldLoadContentPreview(asset)) return "";
  const metadata = asset.metadata ?? {};
  const objectStorage = typeof metadata.object_storage === "object" && metadata.object_storage !== null
    ? metadata.object_storage as Record<string, unknown>
    : null;
  const url = asset.thumbnail_url
    || stringValue(metadata.public_url)
    || stringValue(metadata.image_url)
    || stringValue(objectStorage?.public_url);
  return url ?? "";
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function metadataTags(asset: AssetRecord): string[] {
  return Array.isArray(asset.metadata.tags) ? asset.metadata.tags.filter((tag): tag is string => typeof tag === "string" && Boolean(tag.trim())) : [];
}

function splitAssetName(name: string): string[] {
  return name.split("_").map((part) => part.trim()).filter(Boolean);
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function isImageAsset(asset: AssetRecord): boolean {
  return Boolean(asset.mime_type?.startsWith("image/") || assetPreviewFallbackUrl(asset));
}

function assetPreviewFallbackUrl(asset: AssetRecord): string {
  const metadata = asset.metadata ?? {};
  const objectStorage = typeof metadata.object_storage === "object" && metadata.object_storage !== null
    ? metadata.object_storage as Record<string, unknown>
    : null;
  return asset.thumbnail_url
    || stringValue(metadata.public_url)
    || stringValue(metadata.image_url)
    || stringValue(objectStorage?.public_url)
    || "";
}

function shouldLoadContentPreview(asset: AssetRecord): boolean {
  return Boolean(asset.asset_id && asset.asset_type !== "text" && asset.mime_type?.startsWith("image/"));
}

function contentProjectId(asset: AssetRecord, fallbackProjectId?: string): string | undefined {
  if (asset.scope !== "project") return undefined;
  return asset.project_id || (fallbackProjectId && fallbackProjectId !== "global" ? fallbackProjectId : undefined);
}
