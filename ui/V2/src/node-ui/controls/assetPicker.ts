import type { AssetScope } from "../../api/types";

export interface AssetSearchScope {
  scope: AssetScope;
  project_id?: string;
}

export function assetSearchScopeForProject(projectId?: string): AssetSearchScope {
  if (projectId) {
    return { scope: "combined", project_id: projectId };
  }
  return { scope: "global" };
}
