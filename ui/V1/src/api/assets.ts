import { apiRequest } from "./client";
import { ApiError, getAccessToken } from "./client";
import type {
  AssetCollection,
  AssetRecord,
  AssetSearchParams,
  AssetTag,
  CreateTextAssetInput,
  UploadAssetInput
} from "./types";

function appendSearchParam(params: URLSearchParams, key: string, value: string | string[] | undefined) {
  if (!value) return;
  if (Array.isArray(value)) {
    if (value.length > 0) params.set(key, value.join(","));
    return;
  }
  params.set(key, value);
}

export async function searchAssets(filters: AssetSearchParams = {}): Promise<AssetRecord[]> {
  const params = new URLSearchParams();
  appendSearchParam(params, "keyword", filters.keyword);
  appendSearchParam(params, "scope", filters.scope ?? "combined");
  appendSearchParam(params, "project_id", filters.project_id);
  appendSearchParam(params, "asset_type", filters.asset_type);
  appendSearchParam(params, "collection_id", filters.collection_id);
  appendSearchParam(params, "tag_ids", filters.tag_ids);
  appendSearchParam(params, "mime_type", filters.mime_type);

  const query = params.toString();
  const result = await apiRequest<{ items: AssetRecord[] }>(
    `/api/assets/search${query ? `?${query}` : ""}`,
  );
  return result.items;
}

export async function listAssetCollections(
  scope: AssetSearchParams["scope"] = "combined",
  projectId?: string,
): Promise<AssetCollection[]> {
  const params = new URLSearchParams({ scope });
  if (projectId) params.set("project_id", projectId);
  const result = await apiRequest<{ items: AssetCollection[] }>(
    `/api/assets/collections?${params.toString()}`,
  );
  return result.items;
}

export async function listAssetTags(
  scope: AssetSearchParams["scope"] = "combined",
  projectId?: string,
): Promise<AssetTag[]> {
  const params = new URLSearchParams({ scope });
  if (projectId) params.set("project_id", projectId);
  const result = await apiRequest<{ items: AssetTag[] }>(`/api/assets/tags?${params.toString()}`);
  return result.items;
}

export async function uploadAsset(input: UploadAssetInput): Promise<AssetRecord> {
  const form = new FormData();
  form.set("file", input.file);
  form.set("scope", input.scope);
  form.set("publish", String(input.publish ?? true));

  if (input.project_id) form.set("project_id", input.project_id);
  if (input.name) form.set("name", input.name);
  if (input.metadata) form.set("metadata_json", JSON.stringify(input.metadata));
  if (input.collection_ids?.length) form.set("collection_ids", input.collection_ids.join(","));
  if (input.tag_ids?.length) form.set("tag_ids", input.tag_ids.join(","));

  return apiRequest<AssetRecord>("/api/assets/files", {
    method: "POST",
    body: form
  });
}

export async function createTextAsset(input: CreateTextAssetInput): Promise<AssetRecord> {
  return apiRequest<AssetRecord>("/api/assets/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scope: input.scope,
      project_id: input.project_id,
      name: input.name,
      text: input.text,
      metadata: input.metadata ?? {},
    }),
  });
}

export async function downloadAssetContent(assetId: string, projectId?: string): Promise<Blob> {
  const response = await fetch(assetContentPath(assetId, projectId), {
    headers: authorizedAssetHeaders("application/octet-stream"),
  });
  if (!response.ok) {
    throw new ApiError(`请求失败：${response.status}`, response.status, await response.text());
  }
  return response.blob();
}

export async function readAssetTextContent(assetId: string, projectId?: string): Promise<string> {
  const response = await fetch(assetContentPath(assetId, projectId), {
    headers: authorizedAssetHeaders("text/plain"),
  });
  if (!response.ok) {
    throw new ApiError(`请求失败：${response.status}`, response.status, await response.text());
  }
  return response.text();
}

export async function deleteAsset(assetId: string): Promise<void> {
  await apiRequest<void>(`/api/assets/${encodeURIComponent(assetId)}`, {
    method: "DELETE"
  });
}

function assetContentPath(assetId: string, projectId?: string): string {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const query = params.toString();
  return `/api/assets/${encodeURIComponent(assetId)}/content${query ? `?${query}` : ""}`;
}

function authorizedAssetHeaders(accept: string): Headers {
  const headers = new Headers({ Accept: accept });
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}
