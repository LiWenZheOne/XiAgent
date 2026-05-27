import { apiRequest } from "./client";
import type { ProjectRecord } from "./types";

export async function listProjects(): Promise<ProjectRecord[]> {
  const result = await apiRequest<{ items: ProjectRecord[] }>("/api/projects");
  return result.items;
}

export async function createProject(name: string, description?: string): Promise<ProjectRecord> {
  return apiRequest<ProjectRecord>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description: description || null }),
  });
}
