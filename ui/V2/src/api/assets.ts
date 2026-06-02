import { ApiError, apiRequest, getAccessToken } from "./client";
import type { AssetCollection, AssetRecord, AssetScope, AssetTag } from "./types";

export interface AssetSearchParams {
  keyword?: string;
  scope?: AssetScope;
  project_id?: string;
  asset_type?: string;
  collection_id?: string;
  names?: string[];
  tag_ids?: string[];
  tag_names?: string[];
  mime_type?: string;
  limit?: number;
  offset?: number;
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
  appendParam(params, "names", filters.names);
  appendParam(params, "tag_ids", filters.tag_ids);
  appendParam(params, "tag_names", filters.tag_names);
  appendParam(params, "mime_type", filters.mime_type);
  if (typeof filters.limit === "number") params.set("limit", String(filters.limit));
  if (typeof filters.offset === "number") params.set("offset", String(filters.offset));

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

export async function createAssetTag(input: {
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  name: string;
  description?: string | null;
}): Promise<AssetTag> {
  return apiRequest<AssetTag>("/api/assets/tags", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function updateAssetTag(input: {
  tag_id: string;
  name: string;
  description?: string | null;
}): Promise<AssetTag> {
  return apiRequest<AssetTag>(`/api/assets/tags/${encodeURIComponent(input.tag_id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: input.name, description: input.description ?? null }),
  });
}

export async function deleteAssetTag(tagId: string): Promise<void> {
  await apiRequest<void>(`/api/assets/tags/${encodeURIComponent(tagId)}`, { method: "DELETE" });
}

export async function listAssetTagsForAsset(assetId: string): Promise<AssetTag[]> {
  const result = await apiRequest<{ items: AssetTag[] }>(`/api/assets/${encodeURIComponent(assetId)}/tags`);
  return result.items;
}

export async function attachAssetTag(assetId: string, tagId: string): Promise<AssetTag[]> {
  const result = await apiRequest<{ items: AssetTag[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/tags/${encodeURIComponent(tagId)}`,
    { method: "POST" },
  );
  return result.items;
}

export async function detachAssetTag(assetId: string, tagId: string): Promise<AssetTag[]> {
  const result = await apiRequest<{ items: AssetTag[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/tags/${encodeURIComponent(tagId)}`,
    { method: "DELETE" },
  );
  return result.items;
}

export async function createAssetCollection(input: {
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  parent_id?: string | null;
  name: string;
  description?: string | null;
}): Promise<AssetCollection> {
  return apiRequest<AssetCollection>("/api/assets/collections", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function updateAssetCollection(input: {
  collection_id: string;
  name: string;
  description?: string | null;
}): Promise<AssetCollection> {
  return apiRequest<AssetCollection>(`/api/assets/collections/${encodeURIComponent(input.collection_id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: input.name, description: input.description ?? null }),
  });
}

export async function deleteAssetCollection(collectionId: string): Promise<void> {
  await apiRequest<void>(`/api/assets/collections/${encodeURIComponent(collectionId)}`, { method: "DELETE" });
}

export async function uploadAsset(input: {
  file: File;
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  name?: string;
  metadata?: Record<string, unknown>;
  publish?: boolean;
  collection_ids?: string[];
  tag_ids?: string[];
}): Promise<AssetRecord> {
  const form = new FormData();
  form.set("file", input.file);
  form.set("scope", input.scope);
  form.set("publish", String(input.publish ?? true));
  if (input.project_id) form.set("project_id", input.project_id);
  if (input.name) form.set("name", input.name);
  if (input.metadata) form.set("metadata_json", JSON.stringify(input.metadata));
  if (input.collection_ids?.length) form.set("collection_ids", input.collection_ids.join(","));
  if (input.tag_ids?.length) form.set("tag_ids", input.tag_ids.join(","));
  return apiRequest<AssetRecord>("/api/assets/files", { method: "POST", body: form });
}

export interface IntelligentAssetUploadResult {
  asset: AssetRecord;
  confidence: number;
  reasoning: string;
}

export async function uploadAssetWithMetadataCompletion(input: {
  file: File;
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  name: string;
  asset_type: "character" | "location" | "prop";
  world_background: string;
  publish?: boolean;
}): Promise<IntelligentAssetUploadResult> {
  const form = new FormData();
  form.set("file", input.file);
  form.set("scope", input.scope);
  form.set("publish", String(input.publish ?? true));
  form.set("name", input.name);
  form.set("asset_type", input.asset_type);
  form.set("world_background", input.world_background);
  if (input.project_id) form.set("project_id", input.project_id);
  return apiRequest<IntelligentAssetUploadResult>("/api/assets/files/intelligent", { method: "POST", body: form });
}

export async function createTextAsset(input: {
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  name: string;
  text: string;
  metadata?: Record<string, unknown>;
}): Promise<AssetRecord> {
  return apiRequest<AssetRecord>("/api/assets/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, metadata: input.metadata ?? {} }),
  });
}

export interface DraftAssetFromDescriptionInput {
  project_id?: string;
  asset_type?: "auto" | "character" | "scene" | "prop";
  description: string;
  script?: string;
  background?: string;
  current_assets?: Record<string, unknown>;
}

export interface DraftAssetFromDescriptionResult {
  assets?: Array<Record<string, unknown>>;
  asset?: Record<string, unknown>;
  confidence: number;
  reasoning: string;
}

export async function draftAssetFromDescription(input: DraftAssetFromDescriptionInput): Promise<DraftAssetFromDescriptionResult> {
  return apiRequest<DraftAssetFromDescriptionResult>("/api/assets/draft-from-description", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export interface GenerateAssetImageInput {
  project_id?: string;
  prompt_result: Record<string, unknown>;
  prompt_prefix?: string;
  prompt_suffix?: string;
  aspect_ratio?: string;
  resolution?: string;
}

export interface GeneratedAssetImage {
  full_name?: string;
  card_id?: string;
  image_url: string;
  source?: string;
  runninghub_task_id?: string;
  variant?: string;
  asset_id?: string;
}

interface ImageGenerationJob {
  generation_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  result?: GeneratedAssetImage;
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
}

export async function generateAssetImage(input: GenerateAssetImageInput): Promise<GeneratedAssetImage> {
  const job = await apiRequest<ImageGenerationJob>("/api/assets/generate-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return waitForGeneratedAssetImage(job.generation_id);
}

export interface GenerateStoryboardPanelImageInput {
  project_id?: string;
  card_id: string;
  prompt: string;
  image_refs: Array<Record<string, unknown>>;
  negative_prompt?: string;
  aspect_ratio?: string;
  resolution?: string;
}

export async function generateStoryboardPanelImage(input: GenerateStoryboardPanelImageInput): Promise<GeneratedAssetImage> {
  const job = await apiRequest<ImageGenerationJob>("/api/assets/storyboard-panel-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return waitForGeneratedAssetImage(job.generation_id);
}

export interface RegenerateStoryboardPanelPromptInput {
  project_id?: string;
  card: Record<string, unknown>;
  item: Record<string, unknown>;
  shared_context?: Record<string, unknown>;
  generation_rules?: string;
  negative_prompt?: string;
  aspect_ratio?: string;
  resolution?: string;
}

export interface RegenerateStoryboardPanelPromptResult {
  card: Record<string, unknown>;
  segment_description: Record<string, unknown>;
}

export async function regenerateStoryboardPanelPrompt(
  input: RegenerateStoryboardPanelPromptInput,
): Promise<RegenerateStoryboardPanelPromptResult> {
  return apiRequest<RegenerateStoryboardPanelPromptResult>("/api/assets/storyboard-panel-prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

async function waitForGeneratedAssetImage(generationId: string): Promise<GeneratedAssetImage> {
  const timeoutAt = Date.now() + 4 * 60 * 1000;
  while (Date.now() < timeoutAt) {
    const job = await apiRequest<ImageGenerationJob>(`/api/assets/generate-image/${encodeURIComponent(generationId)}`);
    if (job.status === "succeeded" && job.result) return job.result;
    if (job.status === "failed") {
      throw new ApiError(job.error?.message || "资产图像生成失败。", 500, job.error?.code || "asset_image_generation_failed");
    }
    await delay(1800);
  }
  throw new ApiError("资产图像生成超时，请稍后重试。", 504, "asset_image_generation_poll_timeout");
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function updateAsset(input: {
  asset_id: string;
  name: string;
  metadata?: Record<string, unknown>;
}): Promise<AssetRecord> {
  return apiRequest<AssetRecord>(`/api/assets/${encodeURIComponent(input.asset_id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: input.name, metadata: input.metadata }),
  });
}

export async function getAsset(assetId: string, projectId?: string): Promise<AssetRecord> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const query = params.toString();
  return apiRequest<AssetRecord>(`/api/assets/${encodeURIComponent(assetId)}${query ? `?${query}` : ""}`);
}

export async function replaceAssetFile(input: {
  asset_id: string;
  file: File;
}): Promise<AssetRecord> {
  const form = new FormData();
  form.set("file", input.file);
  return apiRequest<AssetRecord>(`/api/assets/${encodeURIComponent(input.asset_id)}/file`, {
    method: "PUT",
    body: form,
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

export async function downloadAssetThumbnail(assetId: string, projectId?: string, size = 256): Promise<Blob> {
  const params = new URLSearchParams({ size: String(size) });
  if (projectId) params.set("project_id", projectId);
  const token = getAccessToken();
  const headers = new Headers({ Accept: "image/png" });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`/api/assets/${encodeURIComponent(assetId)}/thumbnail?${params.toString()}`, { headers });
  if (!response.ok) throw new ApiError(`资产缩略图加载失败，状态码 ${response.status}`, response.status, await response.text());
  return response.blob();
}
