export type AssetScope = "global" | "project" | "combined";

export interface AssetMetadata {
  public_url?: string;
  tags?: string[];
  object_storage?: {
    provider: string;
    bucket?: string;
    key: string;
    etag?: string;
  };
}

export interface AssetRecord {
  asset_id: string;
  asset_type: "file" | "text" | string;
  name: string;
  scope: AssetScope;
  project_id?: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  storage_uri?: string | null;
  text_content?: string | null;
  thumbnail_url?: string;
  metadata: AssetMetadata;
  created_by?: string;
  created_at: string;
  updated_at?: string;
  deleted_at?: string | null;
}

export interface AssetCollection {
  collection_id: string;
  name: string;
  parent_id?: string | null;
  asset_count?: number;
}

export interface AssetTag {
  tag_id: string;
  name: string;
  scope: AssetScope;
  asset_count?: number;
}

export interface WorkflowListItem {
  workflow: {
    id: string;
    version: string;
    name: string;
    scope?: string;
    description?: string;
    input_schema: JsonSchema;
    [key: string]: unknown;
  };
  nodes: WorkflowNodeSpec[];
  edges: unknown[];
}

export interface WorkflowNodeSpec {
  id: string;
  ref?: string;
  inputs?: Record<string, unknown>;
  outputs?: JsonSchema | Record<string, unknown>;
  [key: string]: unknown;
}

export interface JsonSchema {
  type?: string;
  required?: string[];
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  enum?: string[];
  default?: unknown;
}

export interface AssetSearchParams {
  keyword?: string;
  scope?: AssetScope;
  project_id?: string;
  asset_type?: string;
  collection_id?: string;
  tag_ids?: string[];
  mime_type?: string;
}

export interface UploadAssetInput {
  file: File;
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  name?: string;
  collection_ids?: string[];
  tag_ids?: string[];
  metadata?: AssetMetadata;
  publish?: boolean;
}

export interface CreateTextAssetInput {
  scope: Exclude<AssetScope, "combined">;
  project_id?: string;
  name: string;
  text: string;
  metadata?: Record<string, unknown>;
}

export interface WorkflowSnapshot {
  workflow?: {
    id?: string;
    version?: string;
    name?: string;
    input_schema?: JsonSchema;
  };
  nodes?: Array<{
    id?: string;
    ref?: string;
    name?: string;
    [key: string]: unknown;
  }>;
  edges?: unknown[];
  [key: string]: unknown;
}

export interface TaskRecord {
  task_id: string;
  project_id?: string;
  workflow_id?: string;
  workflow_name?: string;
  workflow_version?: string;
  status: string;
  current_node_id?: string | null;
  error?: string | null;
  created_at?: string;
  started_at?: string | null;
  updated_at?: string;
  finished_at?: string | null;
  input_data?: Record<string, unknown>;
  contract?: Record<string, unknown>;
}

export interface TaskNodeExecution {
  node_execution_id?: string;
  node_id: string;
  node_ref?: string;
  ref?: string;
  attempt?: number;
  status: string;
  input_snapshot?: unknown;
  output_snapshot?: unknown;
  error?: string | Record<string, unknown> | null;
  asset_refs?: unknown;
  started_at?: string | null;
  finished_at?: string | null;
  [key: string]: unknown;
}

export interface TaskNodeAttempt {
  node_execution_id?: string;
  node_id: string;
  node_ref?: string;
  attempt?: number;
  status?: string;
  input_snapshot?: unknown;
  output_snapshot?: unknown;
  error?: string | Record<string, unknown> | null;
  asset_refs?: unknown;
  started_at?: string | null;
  finished_at?: string | null;
  [key: string]: unknown;
}

export interface TaskEvent {
  event_id?: string;
  event_type?: string;
  type?: string;
  node_id?: string | null;
  message?: string;
  payload?: Record<string, unknown>;
  created_at?: string;
  timestamp?: string;
  [key: string]: unknown;
}

export interface TaskDetailResponse {
  task: TaskRecord;
  workflow_snapshot?: WorkflowSnapshot | null;
  node_executions: TaskNodeExecution[];
  node_attempts: Record<string, TaskNodeAttempt[]>;
  events: TaskEvent[];
}
