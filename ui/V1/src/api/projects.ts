import { apiRequest } from "./client";

export interface ProjectRecord {
  project_id: string;
  owner_user_id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export async function listProjects(): Promise<ProjectRecord[]> {
  const result = await apiRequest<{ items: ProjectRecord[] }>("/api/projects");
  return result.items;
}

export async function createProject(name: string): Promise<ProjectRecord> {
  return apiRequest<ProjectRecord>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}
