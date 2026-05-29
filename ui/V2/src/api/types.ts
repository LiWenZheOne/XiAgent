export type AssetScope = "global" | "project" | "combined";

export interface UserRecord {
  user_id: string;
  username: string;
}

export interface AuthResponse {
  user: UserRecord;
  access_token: string;
  token_type: string;
}

export interface ProjectRecord {
  project_id: string;
  name: string;
  description?: string | null;
  owner_user_id: string;
  created_at?: string;
  updated_at?: string;
}

export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  required?: string[];
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  enum?: string[];
  default?: unknown;
  format?: string;
  additionalProperties?: boolean | JsonSchema;
}

export type NodeUiControlMode = "readonly" | "interactive" | "input";

export interface NodeUiControlConfig {
  control_id: string;
  variant?: string;
  mode?: NodeUiControlMode | string;
  bindings?: Record<string, string>;
  options?: Record<string, unknown>;
}

export interface NodeUiConfig {
  mode?: string;
  layout?: {
    node_io?: string;
    default_collapsed_sections?: string[];
    default_expanded_sections?: string[];
  };
  defaults?: Record<string, NodeUiConfig>;
  metadata_schema?: JsonSchema | Record<string, unknown>;
  controls?: {
    input?: NodeUiControlConfig;
    output?: NodeUiControlConfig;
    interaction?: NodeUiControlConfig;
    detail?: NodeUiControlConfig;
  };
  sections?: Record<string, unknown>;
  actions?: Record<string, unknown>;
  bindings?: Record<string, unknown>;
}

export interface UiControlDescriptor {
  control_id: string;
  version: string;
  name: string;
  kind: string;
  tags: string[];
  variants: Array<{
    name: string;
    label: string;
    tags: string[];
    modes: string[];
    required_bindings: unknown[];
    submit_schema?: Record<string, unknown>;
  }>;
  description?: string | null;
}

export interface WorkflowNodeSpec {
  id: string;
  ref?: string;
  name?: string;
  inputs?: Record<string, unknown>;
  outputs?: JsonSchema | Record<string, unknown>;
  ui?: NodeUiConfig;
  [key: string]: unknown;
}

export interface WorkflowListItem {
  workflow: {
    id: string;
    version: string;
    name: string;
    scope?: string;
    description?: string;
    input_schema?: JsonSchema;
    [key: string]: unknown;
  };
  nodes: WorkflowNodeSpec[];
  edges: unknown[];
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

export interface WorkflowSnapshot {
  workflow?: {
    id?: string;
    version?: string;
    name?: string;
    description?: string;
    input_schema?: JsonSchema;
    ui?: NodeUiConfig;
  };
  nodes?: WorkflowNodeSpec[];
  edges?: unknown[];
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
  metadata?: Record<string, unknown>;
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
  node_attempts: Record<string, TaskNodeExecution[]>;
  events: TaskEvent[];
}

export interface AssetMetadata {
  public_url?: string;
  tags?: string[];
  object_storage?: {
    provider: string;
    bucket?: string;
    key?: string;
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
  project_id?: string | null;
  description?: string | null;
  asset_count?: number;
}
