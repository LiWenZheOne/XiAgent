import { apiRequest } from "./client";
import type { WorkflowListItem } from "./types";

export async function listWorkflows(projectId?: string): Promise<WorkflowListItem[]> {
  const params = projectId ? `?${new URLSearchParams({ project_id: projectId }).toString()}` : "";
  const result = await apiRequest<{ items: WorkflowListItem[] }>(`/api/workflows${params}`);
  return result.items;
}
