import { apiRequest } from "./client";
import type { TaskDetailResponse, TaskRecord } from "./types";

export interface CreateTaskRequest {
  project_id: string;
  contract: Record<string, unknown>;
  input_data: Record<string, unknown>;
}

export interface SubmitInteractionRequest {
  project_id: string;
  node_id?: string;
  interaction_id?: string;
  output: Record<string, unknown>;
}

export interface RerunNodeRequest {
  project_id: string;
}

export async function createTask(request: CreateTaskRequest): Promise<TaskRecord> {
  return apiRequest<TaskRecord>("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function listTasks(projectId: string): Promise<TaskRecord[]> {
  const params = new URLSearchParams({ project_id: projectId });
  const result = await apiRequest<{ items: TaskRecord[] }>(`/api/tasks?${params.toString()}`);
  return result.items;
}

export async function getTask(projectId: string, taskId: string): Promise<TaskDetailResponse> {
  const params = new URLSearchParams({ project_id: projectId });
  return apiRequest<TaskDetailResponse>(`/api/tasks/${encodeURIComponent(taskId)}?${params.toString()}`);
}

export function streamTaskEvents(projectId: string, taskId: string): EventSource {
  const params = new URLSearchParams({ project_id: projectId });
  return new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/stream?${params.toString()}`);
}

export async function submitInteraction(taskId: string, request: SubmitInteractionRequest): Promise<TaskRecord> {
  return apiRequest<TaskRecord>(`/api/tasks/${encodeURIComponent(taskId)}/interactions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function rerunNode(taskId: string, nodeId: string, request: RerunNodeRequest): Promise<TaskRecord> {
  return apiRequest<TaskRecord>(
    `/api/tasks/${encodeURIComponent(taskId)}/nodes/${encodeURIComponent(nodeId)}/rerun`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
}
