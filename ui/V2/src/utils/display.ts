import type { JsonSchema, TaskEvent, TaskNodeExecution, TaskRecord, WorkflowNodeSpec, WorkflowSnapshot } from "../api/types";

export type FieldControl = "text" | "textarea" | "number" | "checkbox" | "select" | "asset_images";

export interface SchemaField {
  key: string;
  label: string;
  required: boolean;
  control: FieldControl;
  type?: string;
  description?: string;
  defaultValue?: unknown;
  enumValues?: string[];
}

export interface HumanValue {
  kind: "empty" | "text" | "number" | "boolean" | "list" | "object";
  text: string;
  entries: Array<[string, unknown]>;
}

const fieldLabels: Record<string, string> = {
  topic: "创作主题",
  prompt: "提示词",
  image_url: "参考图片",
  image_urls: "参考图片",
  images: "图片",
  candidates: "候选结果",
  selected_image: "选择结果",
  current_node_id: "当前节点",
  draft_count: "草稿数量",
  aspect_ratio: "画面比例",
  approved: "审批结果",
  comment: "意见",
  notes: "说明",
  usage: "用量",
  results: "结果",
  script: "剧本",
  generate_assets: "生成方式",
  background: "世界背景",
  template_image_url: "模板图片地址",
  answer: "回答",
  question: "问题",
  favorite_color: "喜欢的颜色",
  favorite_food: "喜欢的食物",
  favorite_sport: "喜欢的运动",
  decision: "确认结果",
  text: "文本",
  model: "模型",
  count: "数量",
  characters: "角色",
  character_names: "角色名称",
  prompt_results: "提示词结果",
  ask_color: "颜色偏好",
  ask_food: "食物偏好",
  ask_sport: "运动偏好",
  collect_assets: "补充参考图",
  review_assets: "审核资产匹配",
  upload_images: "上传图片",
  profile: "生成偏好画像",
  generate_prompt: "生成提示词",
  generate_image: "生成图片",
  prepare_prompt: "准备提示词",
  choose_image: "选择图片",
  deepseek_echo: "偏好画像工作流",
  storyboard_generation: "故事板生成",
  asset_catalog: "角色资产编目",
};

const statusLabels: Record<string, string> = {
  created: "已创建",
  pending: "等待中",
  queued: "排队中",
  running: "运行中",
  waiting: "等待用户",
  task_waiting: "等待用户",
  node_waiting: "等待用户",
  succeeded: "成功",
  success: "成功",
  completed: "成功",
  node_succeeded: "成功",
  task_succeeded: "成功",
  failed: "失败",
  error: "失败",
  node_failed: "失败",
  task_failed: "失败",
  human_input_requested: "等待输入",
  interaction_submitted: "已提交",
  task_created: "已创建",
  node_started: "运行中",
  node_running: "运行中",
  canceled: "已取消",
  cancelled: "已取消",
  superseded: "历史版本",
  cleared: "等待重跑",
};

export function buildSchemaFields(schema?: JsonSchema): SchemaField[] {
  const properties = schema?.properties ?? {};
  const required = new Set(schema?.required ?? []);
  return Object.entries(properties).map(([key, property]) => ({
    key,
    label: schemaFieldLabel(key, property.title),
    required: required.has(key),
    control: controlForField(key, property),
    type: property.type,
    description: property.description,
    defaultValue: property.default,
    enumValues: property.enum,
  }));
}

export function formatFieldLabel(key: string): string {
  if (fieldLabels[key]) return fieldLabels[key];
  const normalized = key.replace(/_id$/, "").replace(/_/g, " ");
  return normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function statusLabel(status?: string): string {
  if (!status) return "未知";
  const normalized = status.toLowerCase();
  if (statusLabels[normalized]) return statusLabels[normalized];
  if (normalized.includes("wait")) return "等待用户";
  if (normalized.includes("success") || normalized.includes("done")) return "成功";
  if (normalized.includes("fail") || normalized.includes("error")) return "失败";
  if (normalized.includes("run") || normalized.includes("start")) return "运行中";
  return status;
}

export function statusTone(status?: string): "neutral" | "info" | "success" | "warning" | "danger" {
  const label = statusLabel(status);
  if (label === "成功") return "success";
  if (label === "失败") return "danger";
  if (label === "等待用户" || label === "等待中") return "warning";
  if (label === "运行中") return "info";
  return "neutral";
}

export function humanizeValue(value: unknown): HumanValue {
  if (value === null || value === undefined || value === "") {
    return { kind: "empty", text: "暂无内容", entries: [] };
  }
  if (typeof value === "string") return { kind: "text", text: value, entries: [] };
  if (typeof value === "number") return { kind: "number", text: String(value), entries: [] };
  if (typeof value === "boolean") return { kind: "boolean", text: value ? "是" : "否", entries: [] };
  if (Array.isArray(value)) {
    return { kind: "list", text: `${value.length} 项内容`, entries: value.map((item, index) => [`第 ${index + 1} 项`, item]) };
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return { kind: "object", text: `${entries.length} 个字段`, entries };
  }
  return { kind: "text", text: String(value), entries: [] };
}

export function extractImageUrls(value: unknown): string[] {
  const urls = new Set<string>();
  collectImageUrls(value, urls);
  return [...urls];
}

export function taskTitle(task: TaskRecord): string {
  return task.workflow_name || (task.workflow_id ? formatFieldLabel(task.workflow_id) : "未命名任务");
}

export function taskTime(task: TaskRecord): string {
  return formatDate(task.started_at || task.created_at || task.updated_at);
}

export function formatDate(value?: string | null): string {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}

export function nodeRef(node: TaskNodeExecution, snapshot?: WorkflowSnapshot | null): string {
  if (node.node_ref) return node.node_ref;
  if (node.ref) return node.ref;
  const spec = snapshot?.nodes?.find((item) => item.id === node.node_id);
  return spec?.ref || spec?.name || "运行节点";
}

export function nodeDisplayTitle(node: TaskNodeExecution, snapshot?: WorkflowSnapshot | null): string {
  const spec = snapshot?.nodes?.find((item) => item.id === node.node_id);
  const title = spec?.ui && typeof spec.ui["title" as keyof typeof spec.ui] === "string" ? String(spec.ui["title" as keyof typeof spec.ui]) : "";
  if (title) return title;
  if (spec?.name) return spec.name;
  const outputKeys = schemaKeys(spec?.outputs);
  if (outputKeys.includes("answer")) return formatFieldLabel(node.node_id);
  if (outputKeys.includes("image_urls")) return "补充参考图";
  if (outputKeys.includes("decision")) return "人工确认";
  return formatFieldLabel(node.node_id);
}

export function nodeDisplayKind(node: TaskNodeExecution, snapshot?: WorkflowSnapshot | null): string {
  const spec = snapshot?.nodes?.find((item) => item.id === node.node_id);
  const outputKeys = schemaKeys(spec?.outputs);
  if (isWaitingNode(node, snapshot) || isHumanInteractionRef(nodeRef(node, snapshot))) {
    if (outputKeys.includes("answer")) return "用户输入";
    if (outputKeys.includes("image_urls")) return "图片补充";
    if (outputKeys.some((key) => key.startsWith("selected_"))) return "用户选择";
    return "人工确认";
  }
  if (nodeRef(node, snapshot).startsWith("ai.")) return "智能生成";
  if (nodeRef(node, snapshot).startsWith("tool.")) return "数据处理";
  return "运行节点";
}

export function eventText(event: TaskEvent): string {
  const type = readableEventType(event.event_type || event.type);
  const message = event.message ? ` · ${event.message}` : "";
  return `${type}${message}`;
}

export function isWaitingNode(node: TaskNodeExecution, snapshot?: WorkflowSnapshot | null): boolean {
  const waiting = statusLabel(node.status) === "等待用户";
  if (!waiting) return false;
  return nodeRef(node, snapshot).includes("human_approval") || nodeRef(node, snapshot).includes("user_approval") || waiting;
}

function schemaFieldLabel(key: string, title?: string): string {
  if (!title) return formatFieldLabel(key);
  if (isGenericEnglishTitle(key, title)) return formatFieldLabel(key);
  return title;
}

function isGenericEnglishTitle(key: string, title: string): boolean {
  if (!/^[\w\s-]+$/.test(title)) return false;
  const normalizedTitle = title.toLowerCase().replace(/[\s-]+/g, "_");
  return normalizedTitle === key.toLowerCase() || Boolean(fieldLabels[key]);
}

function readableEventType(type?: string): string {
  const label = statusLabel(type);
  return label.includes("_") ? "状态更新" : label;
}

function isHumanInteractionRef(ref: string): boolean {
  return ref.includes("human_approval") || ref.includes("user_approval") || ref.includes("user_choice");
}

function controlForField(key: string, property: JsonSchema): FieldControl {
  const normalized = key.toLowerCase();
  if (property.enum?.length) return "select";
  if (normalized.includes("image_url") || normalized === "images" || property.format === "uri") return "asset_images";
  if (property.type === "number" || property.type === "integer") return "number";
  if (property.type === "boolean") return "checkbox";
  if (property.type === "array" && normalized.includes("image")) return "asset_images";
  if (property.type === "array") return "textarea";
  if (normalized.includes("prompt") || normalized.includes("description") || normalized.includes("text") || normalized.includes("script")) return "textarea";
  return "text";
}

function collectImageUrls(value: unknown, urls: Set<string>) {
  if (typeof value === "string") {
    if (isImageUrl(value)) urls.add(value);
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectImageUrls(item, urls);
    return;
  }
  if (typeof value === "object" && value !== null) {
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      if (["public_url", "url", "thumbnail_url", "image_url"].includes(key) && typeof child === "string" && isImageUrl(child)) {
        urls.add(child);
      } else {
        collectImageUrls(child, urls);
      }
    }
  }
}

function schemaKeys(schema: WorkflowNodeSpec["outputs"]): string[] {
  if (!schema || typeof schema !== "object") return [];
  const outputSchema = schema as JsonSchema;
  return Object.keys(outputSchema.properties ?? {});
}

function isImageUrl(value: string): boolean {
  return /^https?:\/\/.+\.(png|jpe?g|webp|gif)(\?.*)?$/i.test(value);
}
