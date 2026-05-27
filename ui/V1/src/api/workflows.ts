import { apiRequest } from "./client";
import type { WorkflowListItem } from "./types";

export async function listWorkflows(): Promise<WorkflowListItem[]> {
  const result = await apiRequest<{ items: WorkflowListItem[] }>("/api/workflows");
  return result.items;
}
