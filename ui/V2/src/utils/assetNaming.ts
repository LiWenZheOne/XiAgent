export type CatalogAssetGroup = "character" | "scene" | "prop" | "episode_metadata" | "asset";

export const catalogAssetTypeTags: Record<CatalogAssetGroup, string> = {
  character: "角色",
  scene: "地点",
  prop: "道具",
  episode_metadata: "集元数据",
  asset: "资产",
};

const namingTypeTags = new Set(Object.values(catalogAssetTypeTags));

export function cleanAssetTagNames(tags: Array<string | undefined | null>): string[] {
  return tags
    .map((tag) => tag?.trim() ?? "")
    .filter(Boolean);
}

export function assetNameFromTagNames(tags: Array<string | undefined | null>): string {
  return cleanAssetTagNames(tags).join("_");
}

export function assetTagNamesFromName(name: string): string[] {
  const parts = cleanAssetTagNames(name.split(/[_＿]/));
  if (parts.length < 2 || !namingTypeTags.has(parts[0])) return [];
  return parts;
}

export function assetTagNamesForCatalogAsset(options: {
  group: CatalogAssetGroup;
  name: string;
  variantName?: string;
  accessories?: string;
}): string[] {
  const typeTag = catalogAssetTypeTags[options.group] || catalogAssetTypeTags.asset;
  if (options.group === "character") {
    return cleanAssetTagNames([
      typeTag,
      options.name,
      options.variantName || "默认",
      options.accessories,
    ]);
  }
  if (options.group === "scene") {
    return cleanAssetTagNames([typeTag, options.name, options.variantName]);
  }
  if (options.group === "prop") {
    return cleanAssetTagNames([typeTag, options.name, options.variantName, options.accessories]);
  }
  return cleanAssetTagNames([typeTag, options.name]);
}
