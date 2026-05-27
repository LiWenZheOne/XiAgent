import { ApiError, apiRequest, getAccessToken } from "./client";
import type { AssetCollection, AssetRecord, AssetScope, AssetTag } from "./types";

export interface AssetSearchParams {
  keyword?: string;
  scope?: AssetScope;
  project_id?: string;
  asset_type?: string;
  collection_id?: string;
  tag_ids?: string[];
  mime_type?: string;
}

function appendParam(params: URLSearchParams, key: string, value: string | string[] | undefined) {
  if (!value) return;
  if (Array.isArray(value)) {
    if (value.length) params.set(key, value.join(","));
    return;
  }
  params.set(key, value);
}

export async function searchAssets(filters: AssetSearchParams = {}): Promise<AssetRecord[]> {
  const params = new URLSearchParams();
  appendParam(params, "keyword", filters.keyword);
  appendParam(params, "scope", filters.scope ?? "combined");
  appendParam(params, "project_id", filters.project_id);
  appendParam(params, "asset_type", filters.asset_type);
  appendParam(params, "collection_id", filters.collection_id);
  appendParam(params, "tag_ids", filters.tag_ids);
  appendParam(params, "mime_type", filters.mime_type);

  const query = params.toString();
  const result = await apiRequest<{ items: AssetRecord[] }>(`/api/assets/search${query ? `?${query}` : ""}`);
  return result.items;
}

export async function listAssetCollections(scope: AssetScope = "combined", projectId?: string): Promise<AssetCollection[]> {
  const params = new URLSearchParams({ scope });
  if (projectId) params.set("project_id", projectId);
  const result = await apiRequest<{ items: AssetCollection[] }>(`/api/assets/collections?${params.toString()}`);
  return result.items;
}

export async function listAssetTags(scope: AssetScope = "combined", projectId?: string): Promise<AssetTag[]> {
  const params = new URLSearchParams({ scope });
  if (projectId) params.set("project_id", projectId);
  const result = await apiRequest<{ items: AssetTag[] }>(`/api/assets/tags?${params.toString()}`);
  return result.items;
}

export async function uploadAsset(input: {
  file: File;
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  name?: string;
  publish?: boolean;
}): Promise<AssetRecord> {
  const form = new FormData();
  form.set("file", input.file);
  form.set("scope", input.scope);
  form.set("publish", String(input.publish ?? true));
  if (input.project_id) form.set("project_id", input.project_id);
  if (input.name) form.set("name", input.name);
  return apiRequest<AssetRecord>("/api/assets/files", { method: "POST", body: form });
}

export async function createTextAsset(input: {
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  name: string;
  text: string;
}): Promise<AssetRecord> {
  return apiRequest<AssetRecord>("/api/assets/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, metadata: {} }),
  });
}

export async function deleteAsset(assetId: string): Promise<void> {
  await apiRequest<void>(`/api/assets/${encodeURIComponent(assetId)}`, { method: "DELETE" });
}

export async function downloadAssetContent(assetId: string, projectId?: string): Promise<Blob> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const token = getAccessToken();
  const headers = new Headers({ Accept: "application/octet-stream" });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const query = params.toString();
  const response = await fetch(`/api/assets/${encodeURIComponent(assetId)}/content${query ? `?${query}` : ""}`, { headers });
  if (!response.ok) throw new ApiError(`资产下载失败，状态码 ${response.status}`, response.status, await response.text());
  return response.blob();
}
