import { apiRequest } from "./client";
import type { UiControlDescriptor } from "./types";

export async function listNodeControls(): Promise<UiControlDescriptor[]> {
  const result = await apiRequest<{ items: UiControlDescriptor[] }>("/api/ui/node-controls");
  return result.items;
}
