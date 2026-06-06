import { apiRequest, ApiError, getAccessToken } from "./client";
import type { TaskDetailResponse, TaskEvent, TaskRecord } from "./types";

export interface CreateTaskRequest {
  project_id: string;
  contract: Record<string, unknown>;
}

export interface SubmitInteractionRequest {
  project_id: string;
  node_id: string;
  input: Record<string, unknown>;
}

export interface DraftTaskAssetFromDescriptionInput {
  project_id: string;
  node_id: string;
  asset_type?: "auto" | "character" | "scene" | "prop";
  description: string;
  script?: string;
  background?: string;
  current_assets?: Record<string, unknown>;
}

export interface DraftTaskAssetFromDescriptionResult {
  assets?: Array<Record<string, unknown>>;
  asset?: Record<string, unknown>;
  confidence: number;
  reasoning: string;
}

export interface GenerateTaskAssetImageInput {
  project_id: string;
  node_id: string;
  prompt_result: Record<string, unknown>;
  prompt_prefix?: string;
  prompt_suffix?: string;
  aspect_ratio?: string;
  resolution?: string;
}

export interface GeneratedTaskAssetImage {
  full_name?: string;
  card_id?: string;
  image_url: string;
  source?: string;
  runninghub_task_id?: string;
  variant?: string;
  asset_id?: string;
}

export interface GenerateTaskStoryboardPanelImageInput {
  project_id: string;
  node_id: string;
  card_id: string;
  prompt: string;
  image_refs: Array<Record<string, unknown>>;
  negative_prompt?: string;
  aspect_ratio?: string;
  resolution?: string;
}

export interface RegenerateTaskStoryboardPanelPromptInput {
  project_id: string;
  node_id: string;
  card: Record<string, unknown>;
  item: Record<string, unknown>;
  shared_context?: Record<string, unknown>;
  generation_rules?: string;
  negative_prompt?: string;
  aspect_ratio?: string;
  resolution?: string;
}

export interface RegenerateTaskStoryboardPanelPromptResult {
  card: Record<string, unknown>;
  segment_description: Record<string, unknown>;
}

export async function listTasks(projectId: string): Promise<TaskRecord[]> {
  const params = new URLSearchParams({ project_id: projectId });
  const result = await apiRequest<{ items: TaskRecord[] }>(`/api/tasks?${params.toString()}`);
  return result.items;
}

export async function createTask(request: CreateTaskRequest): Promise<TaskRecord> {
  return apiRequest<TaskRecord>("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function getTask(projectId: string, taskId: string): Promise<TaskDetailResponse> {
  const params = new URLSearchParams({ project_id: projectId });
  return apiRequest<TaskDetailResponse>(`/api/tasks/${encodeURIComponent(taskId)}?${params.toString()}`);
}

export async function deleteTask(projectId: string, taskId: string): Promise<void> {
  const params = new URLSearchParams({ project_id: projectId });
  await apiRequest<{ deleted: boolean; task_id: string }>(`/api/tasks/${encodeURIComponent(taskId)}?${params.toString()}`, {
    method: "DELETE",
  });
}

export function streamTaskEvents(
  projectId: string,
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  onError?: (error: unknown) => void,
): () => void {
  const params = new URLSearchParams({ project_id: projectId });
  const controller = new AbortController();
  void readTaskEventStream(
    `/api/tasks/${encodeURIComponent(taskId)}/stream?${params.toString()}`,
    controller.signal,
    onEvent,
  ).catch((error) => {
    if (!controller.signal.aborted) onError?.(error);
  });
  return () => controller.abort();
}

export async function submitInteraction(taskId: string, request: SubmitInteractionRequest): Promise<TaskRecord> {
  return apiRequest<TaskRecord>(`/api/tasks/${encodeURIComponent(taskId)}/interactions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function saveInteractionDraft(taskId: string, request: SubmitInteractionRequest): Promise<TaskRecord> {
  return apiRequest<TaskRecord>(`/api/tasks/${encodeURIComponent(taskId)}/interactions/draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function draftTaskAssetFromDescription(
  taskId: string,
  input: DraftTaskAssetFromDescriptionInput,
): Promise<DraftTaskAssetFromDescriptionResult> {
  return apiRequest<DraftTaskAssetFromDescriptionResult>(`/api/tasks/${encodeURIComponent(taskId)}/interactions/asset-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function generateTaskAssetImage(
  taskId: string,
  input: GenerateTaskAssetImageInput,
): Promise<GeneratedTaskAssetImage> {
  return apiRequest<GeneratedTaskAssetImage>(`/api/tasks/${encodeURIComponent(taskId)}/interactions/generate-asset-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function generateTaskStoryboardPanelImage(
  taskId: string,
  input: GenerateTaskStoryboardPanelImageInput,
): Promise<GeneratedTaskAssetImage> {
  return apiRequest<GeneratedTaskAssetImage>(`/api/tasks/${encodeURIComponent(taskId)}/interactions/storyboard-panel-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function regenerateTaskStoryboardPanelPrompt(
  taskId: string,
  input: RegenerateTaskStoryboardPanelPromptInput,
): Promise<RegenerateTaskStoryboardPanelPromptResult> {
  return apiRequest<RegenerateTaskStoryboardPanelPromptResult>(`/api/tasks/${encodeURIComponent(taskId)}/interactions/storyboard-panel-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function rerunNode(taskId: string, nodeId: string, projectId: string, rerunRevisionNote = ""): Promise<TaskRecord> {
  const body: Record<string, string> = { project_id: projectId };
  const cleanRevisionNote = rerunRevisionNote.trim();
  if (cleanRevisionNote) body.rerun_revision_note = cleanRevisionNote;
  return apiRequest<TaskRecord>(
    `/api/tasks/${encodeURIComponent(taskId)}/nodes/${encodeURIComponent(nodeId)}/rerun`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

async function readTaskEventStream(
  path: string,
  signal: AbortSignal,
  onEvent: (event: TaskEvent) => void,
): Promise<void> {
  const headers = new Headers({ Accept: "text/event-stream" });
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(path, { headers, signal });
  if (!response.ok) {
    throw new ApiError(streamErrorMessage(response.status), response.status);
  }
  if (!response.body) return;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event) onEvent(event);
    }
  }
  const finalText = buffer + decoder.decode();
  const finalEvent = parseSseBlock(finalText);
  if (finalEvent) onEvent(finalEvent);
}

function parseSseBlock(block: string): TaskEvent | null {
  if (!block.trim()) return null;
  let eventType = "message";
  let eventId = "";
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("id:")) eventId = line.slice("id:".length).trim();
    if (line.startsWith("event:")) eventType = line.slice("event:".length).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trim());
  }
  if (!dataLines.length) return null;
  const data = dataLines.join("\n");
  let payload: Record<string, unknown> = {};
  if (data) {
    try {
      const parsed = JSON.parse(data) as unknown;
      if (typeof parsed === "object" && parsed !== null) payload = parsed as Record<string, unknown>;
    } catch {
      payload = { message: data };
    }
  }
  return {
    event_id: eventId || undefined,
    event_type: eventType,
    node_id: typeof payload.node_id === "string" ? payload.node_id : null,
    message: typeof payload.message === "string" ? payload.message : undefined,
    payload,
  };
}

function streamErrorMessage(status: number): string {
  if (status === 401) return "登录状态已失效，请重新登录。";
  if (status === 403) return "当前账号没有权限读取任务事件。";
  return "任务事件连接失败，请刷新后重试。";
}
