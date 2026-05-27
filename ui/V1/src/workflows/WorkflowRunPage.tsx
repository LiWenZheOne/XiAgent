import { FormEvent, useEffect, useMemo, useState } from "react";

import { createTask } from "../api/tasks";
import type { JsonSchema, TaskRecord, WorkflowListItem } from "../api/types";
import { listWorkflows } from "../api/workflows";

export interface ProjectContext {
  id: string;
  name: string;
}

interface WorkflowTemplate {
  id: string;
  version: string;
  name: string;
  description: string;
  source: string;
  nodes: string[];
  inputSchema: JsonSchema;
  contract: Record<string, unknown>;
}

interface WorkflowRunPageProps {
  currentProject: ProjectContext;
  onNavigateToTask: (taskId: string) => void;
}

function workflowListItemToTemplate(item: WorkflowListItem): WorkflowTemplate {
  const nodeIds = item.nodes
    .map((node) => {
      const candidate = node as { id?: unknown } | null;
      return typeof candidate?.id === "string" ? candidate.id : "node";
    })
    .filter(Boolean);

  return {
    id: item.workflow.id,
    version: item.workflow.version,
    name: item.workflow.name,
    description: typeof item.workflow.description === "string"
      ? item.workflow.description
      : `${item.workflow.name} 后端契约，来自 /api/workflows。`,
    source: "/api/workflows",
    nodes: nodeIds.length > 0 ? nodeIds : ["runtime_node"],
    inputSchema: item.workflow.input_schema,
    contract: {
      workflow: item.workflow,
      nodes: item.nodes,
      edges: item.edges ?? [],
    },
  };
}

function schemaProperties(schema?: JsonSchema): Record<string, JsonSchema> {
  return schema?.properties ?? {};
}

function defaultValueFor(property: JsonSchema): string {
  if (typeof property.default === "string") return property.default;
  if (typeof property.default === "number" || typeof property.default === "boolean") return String(property.default);
  return "";
}

function valuesFromSchema(schema?: JsonSchema): Record<string, string> {
  const values: Record<string, string> = {};
  for (const [key, property] of Object.entries(schemaProperties(schema))) {
    values[key] = defaultValueFor(property);
  }
  return values;
}

function normalizeInputValue(property: JsonSchema, value: string): unknown {
  if (property.type === "array") {
    return value
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (property.type === "number" || property.type === "integer") return Number(value);
  if (property.type === "boolean") return value === "true";
  return value;
}

function buildContract(template: WorkflowTemplate) {
  return template.contract;
}

export function WorkflowRunPage({ currentProject, onNavigateToTask }: WorkflowRunPageProps) {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [workflowLoading, setWorkflowLoading] = useState(true);
  const [workflowError, setWorkflowError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [taskError, setTaskError] = useState("");
  const [taskSyncState, setTaskSyncState] = useState<"idle" | "syncing" | "synced" | "failed">("idle");
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [createdTask, setCreatedTask] = useState<TaskRecord | null>(null);

  useEffect(() => {
    let active = true;
    setWorkflowLoading(true);
    setWorkflowError("");
    setTemplates([]);
    listWorkflows()
      .then((items) => {
        if (!active) return;
        const nextTemplates = items.map(workflowListItemToTemplate);
        setTemplates(nextTemplates);
        const firstTemplate = nextTemplates[0];
        setSelectedWorkflowId(firstTemplate?.id ?? "");
        setInputValues(valuesFromSchema(firstTemplate?.inputSchema));
        if (nextTemplates.length === 0) setWorkflowError("后端未返回可运行工作流。");
      })
      .catch(() => {
        if (active) setWorkflowError("工作流接口不可用，请重试。");
      })
      .finally(() => {
        if (active) setWorkflowLoading(false);
      });
    return () => {
      active = false;
    };
  }, [reloadKey]);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selectedWorkflowId),
    [selectedWorkflowId, templates],
  );
  const properties = useMemo(() => schemaProperties(selectedTemplate?.inputSchema), [selectedTemplate]);
  const contract = useMemo(() => (selectedTemplate ? buildContract(selectedTemplate) : null), [selectedTemplate]);

  function handleSelectTemplate(templateId: string) {
    const nextTemplate = templates.find((template) => template.id === templateId);
    if (!nextTemplate) return;
    setSelectedWorkflowId(templateId);
    setInputValues(valuesFromSchema(nextTemplate.inputSchema));
    setCreatedTask(null);
    setTaskError("");
    setTaskSyncState("idle");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTemplate || !contract) return;
    const inputData = Object.fromEntries(
      Object.entries(properties).map(([key, property]) => [key, normalizeInputValue(property, inputValues[key] ?? "")]),
    );

    setTaskError("");
    setTaskSyncState("syncing");
    setCreatedTask(null);
    try {
      const task = await createTask({
        project_id: currentProject.id,
        contract,
        input_data: inputData,
      });
      setCreatedTask(task);
      setTaskSyncState("synced");
      onNavigateToTask(task.task_id);
    } catch {
      setTaskSyncState("failed");
      setTaskError("任务创建接口不可用，请重试。");
    }
  }

  return (
    <main className="page workflow-run-page">
      <section className="page-header">
        <div>
          <p className="eyebrow">{currentProject.name} / workflow runtime</p>
          <h1>从工作流创建任务</h1>
          <p>模板来自后端 YAML/JSON 契约，前台只负责选择模板和填写运行输入。</p>
        </div>
        <div className="header-actions">
          <button className="secondary-button" type="button" onClick={() => setReloadKey((current) => current + 1)}>
            刷新工作流
          </button>
          <button className="secondary-button" type="button">
            查看契约
          </button>
        </div>
      </section>

      {workflowLoading ? <section className="panel empty-panel">正在加载后端工作流契约...</section> : null}
      {!workflowLoading && workflowError ? (
        <section className="panel empty-panel">
          <h2>{workflowError}</h2>
          <button className="secondary-button" type="button" onClick={() => setReloadKey((current) => current + 1)}>
            重试加载工作流
          </button>
        </section>
      ) : null}

      {!workflowLoading && !workflowError && selectedTemplate ? (
        <div className="workflow-run-layout">
          <aside className="template-panel">
            <h2>可运行契约</h2>
            <p className="eyebrow">来源：后端 /api/workflows</p>
            <div className="template-list">
              {templates.map((template) => (
                <button
                  aria-label={`选择 ${template.id}`}
                  className={template.id === selectedTemplate.id ? "template-item active" : "template-item"}
                  key={template.id}
                  type="button"
                  onClick={() => handleSelectTemplate(template.id)}
                >
                  <strong>{template.id}</strong>
                  <span>{template.name}</span>
                  <small>
                    {template.version} · {template.nodes.length} nodes
                  </small>
                </button>
              ))}
            </div>
          </aside>

          <section className="panel workflow-preview">
            <div className="section-header compact">
              <div>
                <h2>{selectedTemplate.name}</h2>
                <p>{selectedTemplate.description}</p>
              </div>
              <span className="status info">{selectedTemplate.version}</span>
            </div>
            <dl className="template-meta">
              <div>
                <dt>契约来源</dt>
                <dd>{selectedTemplate.source}</dd>
              </div>
              <div>
                <dt>项目</dt>
                <dd>{currentProject.name}</dd>
              </div>
              <div>
                <dt>节点纵向顺序</dt>
                <dd>{selectedTemplate.nodes.join(" → ")}</dd>
              </div>
              <div>
                <dt>输入引用</dt>
                <dd>{Object.keys(properties).map((input) => `$workflow.input.${input}`).join(" / ") || "无初始输入"}</dd>
              </div>
            </dl>
            <pre>{JSON.stringify(selectedTemplate.inputSchema, null, 2)}</pre>
          </section>

          <section className="panel workflow-form-panel">
            <h2>运行输入</h2>
            <form className="workflow-input-form" onSubmit={handleSubmit}>
              {Object.entries(properties).map(([key, property]) => (
                <label className="workflow-field" key={key}>
                  <span>{key}</span>
                  {property.enum?.length ? (
                    <select
                      aria-label={key}
                      value={inputValues[key] ?? ""}
                      onChange={(event) => setInputValues((current) => ({ ...current, [key]: event.target.value }))}
                    >
                      {property.enum.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      aria-label={key}
                      value={inputValues[key] ?? ""}
                      placeholder={property.type === "array" ? "多个值用换行或英文逗号分隔" : undefined}
                      onChange={(event) => setInputValues((current) => ({ ...current, [key]: event.target.value }))}
                    />
                  )}
                </label>
              ))}
              {Object.keys(properties).length === 0 ? <p className="empty-state">该工作流没有初始输入。</p> : null}
              <div className="form-actions">
                <button className="primary-button full-width" disabled={taskSyncState === "syncing"} type="submit">
                  {taskSyncState === "syncing" ? "创建中" : "创建并运行任务"}
                </button>
              </div>
            </form>

            {taskError ? <p className="form-error">{taskError}</p> : null}
            {createdTask ? (
              <section className="result-panel" aria-live="polite">
                <h2>任务已创建 / {selectedTemplate.id}</h2>
                <p>{createdTask.task_id} · {currentProject.name} · {createdTask.status}</p>
              </section>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}
