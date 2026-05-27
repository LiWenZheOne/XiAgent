import { type FormEvent, useEffect, useMemo, useState } from "react";

import { createTextAsset, deleteAsset, downloadAssetContent, listAssetCollections, listAssetTags, searchAssets, uploadAsset } from "../api/assets";
import { login, register } from "../api/auth";
import { ApiError, clearAccessToken, getAccessToken } from "../api/client";
import { createProject, listProjects } from "../api/projects";
import { createTask, getTask, listTasks, rerunNode, streamTaskEvents, submitInteraction } from "../api/tasks";
import type {
  AssetRecord,
  AssetCollection,
  AssetTag,
  AuthResponse,
  JsonSchema,
  ProjectRecord,
  TaskDetailResponse,
  TaskEvent,
  TaskNodeExecution,
  TaskRecord,
  WorkflowListItem,
  WorkflowNodeSpec,
  WorkflowSnapshot,
} from "../api/types";
import { listWorkflows } from "../api/workflows";
import { ControlLibraryPage } from "../node-ui/ControlLibraryPage";
import { getNodeUiControl, resolveNodeControlConfig, resolveNodeInteractionConfig } from "../node-ui/registry";
import {
  buildSchemaFields,
  eventText,
  formatDate,
  formatFieldLabel,
  isWaitingNode,
  nodeDisplayKind,
  nodeDisplayTitle,
  statusLabel,
  statusTone,
  taskTime,
  taskTitle,
  type SchemaField,
} from "../utils/display";

type Route = "workbench" | "assets" | "projects" | "controls";

interface SessionState {
  username: string;
}

interface WorkflowTemplate {
  id: string;
  version: string;
  name: string;
  description: string;
  inputSchema: JsonSchema;
  contract: Record<string, unknown>;
  nodes: string[];
}

export function App() {
  const [session, setSession] = useState<SessionState | null>(() => (getAccessToken() ? { username: "已登录用户" } : null));
  const [route, setRoute] = useState<Route>("workbench");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [creatingTask, setCreatingTask] = useState(false);
  const [projectLoading, setProjectLoading] = useState(false);
  const [taskLoading, setTaskLoading] = useState(false);
  const [projectError, setProjectError] = useState("");
  const [taskError, setTaskError] = useState("");
  const [reloadProjectsKey, setReloadProjectsKey] = useState(0);
  const [reloadTasksKey, setReloadTasksKey] = useState(0);

  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );

  function handleUnauthorized(error: unknown): boolean {
    if (error instanceof ApiError && error.status === 401) {
      handleLogout();
      return true;
    }
    return false;
  }

  useEffect(() => {
    if (!session) return;
    let active = true;
    setProjectLoading(true);
    setProjectError("");
    listProjects()
      .then((items) => {
        if (!active) return;
        setProjects(items);
        setSelectedProjectId((current) => (items.some((project) => project.project_id === current) ? current : items[0]?.project_id ?? ""));
      })
      .catch((error) => {
        if (!active) return;
        if (handleUnauthorized(error)) return;
        setProjectError(readableError(error, "项目接口不可用，请检查后端服务。"));
      })
      .finally(() => {
        if (active) setProjectLoading(false);
      });
    return () => {
      active = false;
    };
  }, [session, reloadProjectsKey]);

  useEffect(() => {
    setTasks([]);
    setSelectedTaskId("");
  }, [selectedProjectId]);

  useEffect(() => {
    if (!session || !selectedProjectId) {
      setTasks([]);
      setSelectedTaskId("");
      return;
    }
    let active = true;
    setTaskLoading(true);
    setTaskError("");
    listTasks(selectedProjectId)
      .then((items) => {
        if (!active) return;
        setTasks(items);
        setSelectedTaskId((current) => (items.some((task) => task.task_id === current) ? current : ""));
      })
      .catch((error) => {
        if (!active) return;
        if (handleUnauthorized(error)) return;
        setTaskError(readableError(error, "任务接口不可用，请重试。"));
      })
      .finally(() => {
        if (active) setTaskLoading(false);
      });
    return () => {
      active = false;
    };
  }, [session, selectedProjectId, reloadTasksKey]);

  function handleLogout() {
    clearAccessToken();
    setSession(null);
    setProjects([]);
    setTasks([]);
    setSelectedProjectId("");
    setSelectedTaskId("");
    setProjectError("");
    setTaskError("");
  }

  if (!session) {
    return <AuthPage onAuthenticated={(result) => setSession({ username: result.user.username })} />;
  }

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="brand-lockup">
          <div className="brand-mark">X</div>
          <div>
            <strong>XiAgent</strong>
            <span>工作流任务平台</span>
          </div>
        </div>
        <nav className="topnav" aria-label="主导航">
          <button className={route === "workbench" ? "nav-button active" : "nav-button"} type="button" onClick={() => setRoute("workbench")}>
            任务工作台
          </button>
          <button className={route === "assets" ? "nav-button active" : "nav-button"} type="button" onClick={() => setRoute("assets")}>
            资产库
          </button>
          <button className={route === "projects" ? "nav-button active" : "nav-button"} type="button" onClick={() => setRoute("projects")}>
            项目
          </button>
          <button className={route === "controls" ? "nav-button active" : "nav-button"} type="button" onClick={() => setRoute("controls")}>
            控件库
          </button>
        </nav>
        <div className="topbar-meta">
          <span>{selectedProject?.name ?? "未选择项目"}</span>
          <span>{session.username}</span>
          <button className="ghost-button" type="button" onClick={handleLogout} aria-label="退出登录">
            退出
          </button>
        </div>
      </header>

      {route === "workbench" ? (
        <WorkbenchPage
          projects={projects}
          tasks={tasks}
          selectedProject={selectedProject}
          selectedTaskId={selectedTaskId}
          creatingTask={creatingTask}
          projectLoading={projectLoading}
          taskLoading={taskLoading}
          projectError={projectError}
          taskError={taskError}
          onSelectProject={(projectId) => {
            setSelectedProjectId(projectId);
            setSelectedTaskId("");
            setTasks([]);
            setCreatingTask(false);
          }}
          onCreateProject={() => setRoute("projects")}
          onCreateTask={() => {
            setCreatingTask(true);
            setSelectedTaskId("");
          }}
          onSelectTask={(taskId) => {
            setSelectedTaskId(taskId);
            setCreatingTask(false);
          }}
          onTaskCreated={(task) => {
            setReloadTasksKey((current) => current + 1);
            setSelectedTaskId(task.task_id);
            setCreatingTask(false);
          }}
          onRefreshTasks={() => setReloadTasksKey((current) => current + 1)}
        />
      ) : null}

      {route === "assets" ? (
        <AssetLibraryPage project={selectedProject} onProjectRequired={() => setRoute("projects")} />
      ) : null}

      {route === "projects" ? (
        <ProjectsPage
          projects={projects}
          selectedProjectId={selectedProjectId}
          loading={projectLoading}
          error={projectError}
          onSelectProject={(projectId) => {
            setSelectedProjectId(projectId);
            setSelectedTaskId("");
            setTasks([]);
            setCreatingTask(false);
            setRoute("workbench");
          }}
          onReload={() => setReloadProjectsKey((current) => current + 1)}
          onCreated={(project) => {
            setProjects((current) => [project, ...current]);
            setSelectedProjectId(project.project_id);
            setSelectedTaskId("");
            setTasks([]);
            setCreatingTask(false);
            setRoute("workbench");
          }}
        />
      ) : null}

      {route === "controls" ? <ControlLibraryPage /> : null}
    </div>
  );
}

function AuthPage({ onAuthenticated }: { onAuthenticated: (result: AuthResponse) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "register") await register(username.trim(), password);
      onAuthenticated(await login(username.trim(), password));
    } catch (nextError) {
      setError(readableError(nextError, mode === "login" ? "登录失败，请检查账号和密码。" : "注册失败，请换一个用户名后重试。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="brand-mark large">X</div>
        <p className="eyebrow">XiAgent V2</p>
        <h1>{mode === "login" ? "登录 XiAgent" : "注册 XiAgent"}</h1>
        <p>使用你的账号进入项目、资产库和任务运行工作台。</p>
        <div className="segmented-control" role="tablist" aria-label="认证模式">
          <button aria-label="切换到登录" className={mode === "login" ? "active" : ""} type="button" onClick={() => setMode("login")}>
            登录
          </button>
          <button aria-label="切换到注册" className={mode === "register" ? "active" : ""} type="button" onClick={() => setMode("register")}>
            注册
          </button>
        </div>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label>
            <span>用户名</span>
            <input aria-label="用户名" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            <span>密码</span>
            <input aria-label="密码" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="primary-button full-width" disabled={busy || !username.trim() || !password} type="submit">
            {busy ? "处理中" : mode === "login" ? "登录" : "注册并登录"}
          </button>
        </form>
      </section>
    </main>
  );
}

function WorkbenchPage({
  projects,
  tasks,
  selectedProject,
  selectedTaskId,
  creatingTask,
  projectLoading,
  taskLoading,
  projectError,
  taskError,
  onSelectProject,
  onCreateProject,
  onCreateTask,
  onSelectTask,
  onTaskCreated,
  onRefreshTasks,
}: {
  projects: ProjectRecord[];
  tasks: TaskRecord[];
  selectedProject: ProjectRecord | null;
  selectedTaskId: string;
  creatingTask: boolean;
  projectLoading: boolean;
  taskLoading: boolean;
  projectError: string;
  taskError: string;
  onSelectProject: (projectId: string) => void;
  onCreateProject: () => void;
  onCreateTask: () => void;
  onSelectTask: (taskId: string) => void;
  onTaskCreated: (task: TaskRecord) => void;
  onRefreshTasks: () => void;
}) {
  const selectedTask = tasks.find((task) => task.task_id === selectedTaskId) ?? null;

  return (
    <main className="workspace-grid">
      <aside className="workspace-sidebar">
        <section className="sidebar-section">
          <div className="section-title-row">
            <div>
              <p className="eyebrow">项目空间</p>
              <h2>任务工作台</h2>
            </div>
            <button className="icon-button" type="button" onClick={onCreateProject} aria-label="新建项目">
              +
            </button>
          </div>
          {projectLoading ? <p className="muted">正在加载项目...</p> : null}
          {projectError ? <p className="form-error">{projectError}</p> : null}
          {projects.length ? (
            <label className="compact-field">
              <span>当前项目</span>
              <select value={selectedProject?.project_id ?? ""} onChange={(event) => onSelectProject(event.target.value)}>
                {projects.map((project) => (
                  <option key={project.project_id} value={project.project_id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="empty-box">
              <strong>还没有项目</strong>
              <button className="secondary-button" type="button" onClick={onCreateProject}>
                创建项目
              </button>
            </div>
          )}
        </section>

        <section className="sidebar-section grow">
          <div className="section-title-row">
            <div>
              <p className="eyebrow">运行任务</p>
              <h2>任务列表</h2>
            </div>
            <button className="icon-button" type="button" onClick={onRefreshTasks} aria-label="刷新任务">
              ↻
            </button>
          </div>
          <button className={creatingTask ? "task-row create active" : "task-row create"} type="button" onClick={onCreateTask}>
            <strong>创建任务</strong>
            <span>选择工作流并填写运行输入</span>
          </button>
          {taskLoading ? <p className="muted">正在加载任务...</p> : null}
          {taskError ? <p className="form-error">{taskError}</p> : null}
          <div className="task-list">
            {tasks.map((task) => (
              <button
                aria-label={`打开 ${taskTitle(task)}`}
                className={selectedTaskId === task.task_id ? "task-row active" : "task-row"}
                key={task.task_id}
                type="button"
                onClick={() => onSelectTask(task.task_id)}
              >
                <span className={`status-badge ${statusTone(task.status)}`}>{statusLabel(task.status)}</span>
                <strong>{taskTitle(task)}</strong>
                <span>{task.workflow_version ? `版本 ${task.workflow_version}` : statusLabel(task.status)}</span>
                <small>{taskTime(task)}</small>
              </button>
            ))}
          </div>
        </section>
      </aside>

      <section className="workspace-main">
        {creatingTask && selectedProject ? <CreateTaskPanel project={selectedProject} onTaskCreated={onTaskCreated} /> : null}
        {!creatingTask && selectedProject && selectedTask ? (
          <TaskDetailPanel projectId={selectedProject.project_id} taskId={selectedTask.task_id} onTaskChanged={onRefreshTasks} />
        ) : null}
        {!creatingTask && !selectedTask ? (
          <section className="empty-workbench">
            <p className="eyebrow">运行态工作台</p>
            <h1>选择任务或创建新任务</h1>
            <p>左侧任务来自后端运行记录。选择任务后，这里会显示按节点组织的输入、输出、错误、交互和重跑操作。</p>
            <button className="primary-button" type="button" onClick={onCreateTask} disabled={!selectedProject}>
              创建任务
            </button>
          </section>
        ) : null}
      </section>

      <aside className="context-panel">
        <p className="eyebrow">运行上下文</p>
        <h2>{selectedTask ? taskTitle(selectedTask) : "未选择任务"}</h2>
        <dl className="context-list">
          <div>
            <dt>项目</dt>
            <dd>{selectedProject?.name ?? "未选择"}</dd>
          </div>
          <div>
            <dt>任务状态</dt>
            <dd>{selectedTask ? statusLabel(selectedTask.status) : "无"}</dd>
          </div>
          <div>
            <dt>当前节点</dt>
            <dd>{selectedTask?.current_node_id ? formatFieldLabel(selectedTask.current_node_id) : "未记录"}</dd>
          </div>
        </dl>
        <div className="hint-card">
          <strong>用户界面原则</strong>
          <p>工作流契约和任务快照在后台传输，页面只展示字段、媒体、状态和可执行操作。</p>
        </div>
      </aside>
    </main>
  );
}

function CreateTaskPanel({ project, onTaskCreated }: { project: ProjectRecord; onTaskCreated: (task: TaskRecord) => void }) {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [values, setValues] = useState<Record<string, string | boolean | string[]>>({});
  const [imageAssets, setImageAssets] = useState<AssetRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      listWorkflows(project.project_id),
      searchAssets({ scope: "combined", project_id: project.project_id, mime_type: "image/*" }),
    ])
      .then(([workflowItems, assetItems]) => {
        if (!active) return;
        const nextTemplates = workflowItems.map(workflowToTemplate);
        setTemplates(nextTemplates);
        setImageAssets(assetItems.filter((asset) => asset.metadata.public_url));
        setSelectedWorkflowId(nextTemplates[0]?.id ?? "");
        setValues(initialValues(nextTemplates[0]?.inputSchema));
        if (!nextTemplates.length) setError("后端没有返回可运行的工作流。");
      })
      .catch((nextError) => {
        if (active) setError(readableError(nextError, "工作流或资产接口不可用，请稍后重试。"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [project.project_id]);

  const selectedTemplate = templates.find((template) => template.id === selectedWorkflowId) ?? null;
  const fields = useMemo(() => buildSchemaFields(selectedTemplate?.inputSchema), [selectedTemplate]);

  function handleSelectWorkflow(workflowId: string) {
    const template = templates.find((item) => item.id === workflowId);
    setSelectedWorkflowId(workflowId);
    setValues(initialValues(template?.inputSchema));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTemplate) return;
    const validation = validateFields(fields, values);
    if (validation) {
      setError(validation);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const task = await createTask({
        project_id: project.project_id,
        contract: selectedTemplate.contract,
        input_data: buildInputData(fields, values),
      });
      onTaskCreated(task);
    } catch (nextError) {
      setError(readableError(nextError, "任务创建失败，请检查输入后重试。"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel task-create-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">{project.name} / 创建任务</p>
          <h1>新建任务</h1>
          <p>选择后端工作流模板，填写用户输入，系统会保存工作流快照并进入运行详情。</p>
        </div>
      </div>

      {loading ? <p className="muted">正在读取工作流和可用图片资产...</p> : null}
      {error ? <p className="form-error">{error}</p> : null}

      {!loading && selectedTemplate ? (
        <form className="task-create-grid" onSubmit={handleSubmit}>
          <aside className="workflow-picker">
            <h2>工作流模板</h2>
            {templates.map((template) => (
              <button
                className={template.id === selectedWorkflowId ? "workflow-card active" : "workflow-card"}
                key={`${template.id}-${template.version}`}
                type="button"
                onClick={() => handleSelectWorkflow(template.id)}
              >
                <strong>{template.name}</strong>
                <span>{template.description}</span>
                <small>{template.version} · {template.nodes.length} 个节点</small>
              </button>
            ))}
          </aside>

          <section className="workflow-form">
            <h2>运行输入</h2>
            {fields.length === 0 ? <p className="empty-box">这个工作流不需要初始输入。</p> : null}
            {fields.map((field) => (
              <WorkflowInputField
                field={field}
                imageAssets={imageAssets}
                key={field.key}
                value={values[field.key]}
                onChange={(value) => setValues((current) => ({ ...current, [field.key]: value }))}
              />
            ))}
            <button className="primary-button full-width" disabled={saving} type="submit">
              {saving ? "创建中" : "创建并运行"}
            </button>
          </section>
        </form>
      ) : null}
    </section>
  );
}

function WorkflowInputField({
  field,
  value,
  imageAssets,
  onChange,
}: {
  field: SchemaField;
  value: string | boolean | string[] | undefined;
  imageAssets: AssetRecord[];
  onChange: (value: string | boolean | string[]) => void;
}) {
  if (field.control === "asset_images") {
    const selected = Array.isArray(value) ? value : value ? [String(value)] : [];
    return (
      <fieldset className="asset-choice-field">
        <legend>{field.label}{field.required ? " *" : ""}</legend>
        {field.description ? <p>{field.description}</p> : null}
        {imageAssets.length === 0 ? <p className="muted">当前项目没有已发布图片资产，也可以粘贴公开图片地址。</p> : null}
        <div className="asset-check-grid">
          {imageAssets.map((asset) => {
            const url = asset.metadata.public_url ?? "";
            const checked = selected.includes(url);
            return (
              <label className={checked ? "asset-check-card active" : "asset-check-card"} key={asset.asset_id}>
                <input
                  aria-label={`选择资产 ${asset.name}`}
                  checked={checked}
                  type="checkbox"
                  onChange={(event) => {
                    const next = event.target.checked ? [...selected, url] : selected.filter((item) => item !== url);
                    onChange(field.type === "string" ? next[0] ?? "" : next);
                  }}
                />
                <img src={url} alt={asset.name} />
                <span>{asset.name}</span>
              </label>
            );
          })}
        </div>
        <label className="compact-field">
          <span>公开图片地址</span>
          <input
            value={Array.isArray(value) ? "" : String(value ?? "")}
            placeholder="https://..."
            onChange={(event) => onChange(field.type === "array" ? splitLines(event.target.value) : event.target.value)}
          />
        </label>
      </fieldset>
    );
  }

  if (field.control === "select") {
    return (
      <label className="form-field">
        <span>{field.label}{field.required ? " *" : ""}</span>
        <select value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} aria-label={field.label}>
          <option value="">请选择</option>
          {field.enumValues?.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (field.control === "checkbox") {
    return (
      <label className="check-field">
        <input checked={Boolean(value)} type="checkbox" onChange={(event) => onChange(event.target.checked)} />
        <span>{field.label}{field.required ? " *" : ""}</span>
      </label>
    );
  }

  return (
    <label className="form-field">
      <span>{field.label}{field.required ? " *" : ""}</span>
      {field.control === "textarea" ? (
        <textarea aria-label={field.label} value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input
          aria-label={field.label}
          type={field.control === "number" ? "number" : "text"}
          value={String(value ?? "")}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {field.description ? <small>{field.description}</small> : null}
    </label>
  );
}

function TaskDetailPanel({ projectId, taskId, onTaskChanged }: { projectId: string; taskId: string; onTaskChanged: () => void }) {
  const [detail, setDetail] = useState<TaskDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    getTask(projectId, taskId)
      .then((nextDetail) => {
        if (active) setDetail(nextDetail);
      })
      .catch((nextError) => {
        if (active) setError(readableError(nextError, "任务详情接口不可用，请重试。"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, taskId, refreshKey]);

  useEffect(() => {
    return streamTaskEvents(
      projectId,
      taskId,
      () => setRefreshKey((current) => current + 1),
      (nextError) => setError(readableError(nextError, "任务事件连接失败，请刷新后重试。")),
    );
  }, [projectId, taskId]);

  const eventsByNode = useMemo(() => {
    const grouped = new Map<string, TaskEvent[]>();
    for (const event of detail?.events ?? []) {
      const nodeId = event.node_id || (typeof event.payload?.node_id === "string" ? event.payload.node_id : "");
      if (!nodeId) continue;
      grouped.set(nodeId, [...(grouped.get(nodeId) ?? []), event]);
    }
    return grouped;
  }, [detail]);

  const orderedNodes = useMemo(() => orderNodes(detail), [detail]);

  async function handleRerun(nodeId: string) {
    await rerunNode(taskId, nodeId, projectId);
    onTaskChanged();
    setRefreshKey((current) => current + 1);
  }

  async function handleInteraction(nodeId: string, output: Record<string, unknown>) {
    await submitInteraction(taskId, { project_id: projectId, node_id: nodeId, output });
    onTaskChanged();
    setRefreshKey((current) => current + 1);
  }

  return (
    <section className="task-detail" aria-label="任务运行详情">
      {loading ? <section className="panel">正在加载任务详情...</section> : null}
      {error ? <section className="panel form-error">{error}</section> : null}
      {detail ? (
        <>
          <section className="panel task-summary-panel">
            <div>
              <p className="eyebrow">任务详情</p>
              <h1>{taskTitle(detail.task)}</h1>
              <p>创建于 {formatDate(detail.task.created_at)}</p>
            </div>
            <span className={`status-badge ${statusTone(detail.task.status)}`}>{statusLabel(detail.task.status)}</span>
          </section>

          <section className="node-timeline">
            {orderedNodes.map((node, index) => (
              <NodeExecutionCard
                events={eventsByNode.get(node.node_id) ?? []}
                index={index}
                key={node.node_execution_id ?? `${node.node_id}-${index}`}
                node={node}
                snapshot={detail.workflow_snapshot}
                onInteraction={handleInteraction}
                onRerun={handleRerun}
              />
            ))}
            {orderedNodes.length === 0 ? <section className="panel">任务还没有节点执行记录。</section> : null}
          </section>
        </>
      ) : null}
    </section>
  );
}

function NodeExecutionCard({
  node,
  index,
  events,
  snapshot,
  onInteraction,
  onRerun,
}: {
  node: TaskNodeExecution;
  index: number;
  events: TaskEvent[];
  snapshot?: WorkflowSnapshot | null;
  onInteraction: (nodeId: string, output: Record<string, unknown>) => Promise<void>;
  onRerun: (nodeId: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const nodeSpec = snapshot?.nodes?.find((item) => item.id === node.node_id);
  const displayTitle = nodeDisplayTitle(node, snapshot);
  const displayKind = nodeDisplayKind(node, snapshot);
  const canRerun = statusLabel(node.status) === "成功" && nodeSpec?.ui?.actions?.rerun !== false;
  const inputConfig = resolveNodeControlConfig(node, nodeSpec, snapshot, "input");
  const outputConfig = node.error
    ? { control_id: "ui.display.value.v1", variant: "default", mode: "readonly" }
    : resolveNodeControlConfig(node, nodeSpec, snapshot, "output");
  const interactionConfig = resolveNodeInteractionConfig(node, nodeSpec, snapshot);
  const InteractionControl = interactionConfig ? getNodeUiControl(interactionConfig.control_id) : null;
  const inputDefaultOpen = nodeSectionDefaultOpen(snapshot, "input", false);
  const outputDefaultOpen = node.error ? true : nodeSectionDefaultOpen(snapshot, "output", true);
  const eventsDefaultOpen = nodeSectionDefaultOpen(snapshot, "events", false);

  async function withBusy(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="node-card">
      <div className="timeline-dot">{index + 1}</div>
      <div className="node-card-content">
        <header className="node-header">
          <div>
            <p className="eyebrow">{displayKind}</p>
            <h2>{displayTitle}</h2>
          </div>
          <div className="node-actions">
            <span className={`status-badge ${statusTone(node.status)}`}>{statusLabel(node.status)}</span>
            {canRerun ? (
              <button className="secondary-button" disabled={busy} type="button" onClick={() => withBusy(() => onRerun(node.node_id))}>
                重新运行
              </button>
            ) : null}
          </div>
        </header>

        <div className="node-data-stack">
          <NodeDataSection
            config={inputConfig}
            defaultOpen={inputDefaultOpen}
            imageAltPrefix={`${displayTitle} 输入图片`}
            node={node}
            nodeSpec={nodeSpec}
            slot="input"
            snapshot={snapshot}
            title="输入"
            value={node.input_snapshot}
          />
          <NodeDataSection
            config={outputConfig}
            defaultOpen={outputDefaultOpen}
            imageAltPrefix={`${displayTitle} 输出图片`}
            node={node}
            nodeSpec={nodeSpec}
            slot="output"
            snapshot={snapshot}
            title={node.error ? "错误" : "输出"}
            value={node.error ?? node.output_snapshot}
          />
        </div>

        {isWaitingNode(node, snapshot) && interactionConfig && InteractionControl ? (
          <InteractionControl
            busy={busy}
            config={interactionConfig}
            node={node}
            nodeSpec={nodeSpec}
            snapshot={snapshot}
            onSubmit={(output) => withBusy(() => onInteraction(node.node_id, output))}
          />
        ) : null}

        {isWaitingNode(node, snapshot) && !interactionConfig ? (
          <WaitingInteraction busy={busy} node={node} nodeSpec={nodeSpec} onSubmit={(output) => withBusy(() => onInteraction(node.node_id, output))} />
        ) : null}

        <details className="event-strip" open={eventsDefaultOpen}>
          <summary>节点事件</summary>
          {events.length ? (
            <ul>
              {events.map((event, eventIndex) => (
                <li key={event.event_id ?? `${node.node_id}-${eventIndex}`}>{eventText(event)}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">暂无事件。</p>
          )}
        </details>
      </div>
    </article>
  );
}

function NodeDataSection({
  title,
  value,
  node,
  nodeSpec,
  snapshot,
  config,
  slot,
  imageAltPrefix,
  defaultOpen,
}: {
  title: string;
  value: unknown;
  node: TaskNodeExecution;
  nodeSpec?: WorkflowNodeSpec;
  snapshot?: WorkflowSnapshot | null;
  config: ReturnType<typeof resolveNodeControlConfig>;
  slot: "input" | "output";
  imageAltPrefix: string;
  defaultOpen: boolean;
}) {
  const controlConfig = config ?? { control_id: "ui.display.value.v1", variant: "default", mode: "readonly" };
  const Control = getNodeUiControl(controlConfig.control_id);

  return (
    <details className="value-panel node-data-section" open={defaultOpen}>
      <summary>{title}</summary>
      <Control
        config={controlConfig}
        imageAltPrefix={imageAltPrefix}
        node={node}
        nodeSpec={nodeSpec}
        slot={slot}
        snapshot={snapshot}
        title={title}
        value={value}
      />
    </details>
  );
}

function WaitingInteraction({
  node,
  nodeSpec,
  busy,
  onSubmit,
}: {
  node: TaskNodeExecution;
  nodeSpec?: WorkflowNodeSpec;
  busy: boolean;
  onSubmit: (output: Record<string, unknown>) => void;
}) {
  const [text, setText] = useState("");
  const outputSchema = nodeSpec?.outputs && typeof nodeSpec.outputs === "object" ? nodeSpec.outputs as JsonSchema : undefined;
  const outputKeys = Object.keys(outputSchema?.properties ?? {});
  const requiredKeys = outputSchema?.required ?? [];
  const question = readQuestion(node.input_snapshot, nodeSpec);
  const mode = interactionMode(outputKeys, requiredKeys, nodeSpec);
  const answerKey = requiredKeys.find((key) => outputKeys.includes(key)) ?? outputKeys[0] ?? "decision";

  if (mode === "text") {
    return (
      <section className="interaction-panel">
        <div>
          <p className="eyebrow">等待用户输入</p>
          <h3>{question || "请补充信息后继续运行"}</h3>
        </div>
        <label className="form-field">
          <span>{formatFieldLabel(answerKey)}</span>
          <textarea aria-label={formatFieldLabel(answerKey)} value={text} onChange={(event) => setText(event.target.value)} />
        </label>
        <button className="primary-button" disabled={busy || !text.trim()} type="button" onClick={() => onSubmit({ [answerKey]: text.trim() })}>
          提交并继续
        </button>
      </section>
    );
  }

  if (mode === "image_urls") {
    return (
      <section className="interaction-panel">
        <div>
          <p className="eyebrow">等待补充图片</p>
          <h3>{question || "请提供图片地址后继续运行"}</h3>
        </div>
        <label className="form-field">
          <span>图片地址</span>
          <textarea aria-label="图片地址" value={text} onChange={(event) => setText(event.target.value)} placeholder="每行一个公开图片地址" />
        </label>
        <button className="primary-button" disabled={busy || splitLines(text).length === 0} type="button" onClick={() => onSubmit({ [answerKey]: splitLines(text) })}>
          提交图片并继续
        </button>
      </section>
    );
  }

  return (
    <section className="interaction-panel">
      <div>
        <p className="eyebrow">等待人工确认</p>
        <h3>{question || "继续运行需要你的确认"}</h3>
      </div>
      <label className="form-field">
        <span>确认意见</span>
        <textarea aria-label="确认意见" value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <div className="button-row">
        <button className="primary-button" disabled={busy} type="button" onClick={() => onSubmit({ decision: "approved", approved: true, comment: text })}>
          同意并继续
        </button>
        <button className="secondary-button danger" disabled={busy} type="button" onClick={() => onSubmit({ decision: "rejected", approved: false, comment: text })}>
          拒绝
        </button>
      </div>
    </section>
  );
}

function LegacyWaitingInteraction({ nodeId, busy, onSubmit }: { nodeId: string; busy: boolean; onSubmit: (output: Record<string, unknown>) => void }) {
  const [comment, setComment] = useState("");

  return (
    <section className="interaction-panel">
      <div>
        <p className="eyebrow">等待用户</p>
        <h3>继续运行需要你的确认</h3>
      </div>
      <label className="form-field">
        <span>审批意见</span>
        <textarea aria-label="审批意见" value={comment} onChange={(event) => setComment(event.target.value)} />
      </label>
      <div className="button-row">
        <button className="primary-button" disabled={busy} type="button" onClick={() => onSubmit({ approved: true, comment })}>
          同意并继续
        </button>
        <button className="secondary-button danger" disabled={busy} type="button" onClick={() => onSubmit({ approved: false, comment, reason: comment || `节点 ${nodeId} 被拒绝` })}>
          拒绝
        </button>
      </div>
    </section>
  );
}

function ProjectsPage({
  projects,
  selectedProjectId,
  loading,
  error,
  onSelectProject,
  onReload,
  onCreated,
}: {
  projects: ProjectRecord[];
  selectedProjectId: string;
  loading: boolean;
  error: string;
  onSelectProject: (projectId: string) => void;
  onReload: () => void;
  onCreated: (project: ProjectRecord) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      setFormError("请输入项目名称。");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      onCreated(await createProject(name.trim(), description.trim()));
      setName("");
      setDescription("");
    } catch (nextError) {
      setFormError(readableError(nextError, "项目创建失败，请重试。"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="page-grid two-columns">
      <section className="panel">
        <p className="eyebrow">项目管理</p>
        <h1>项目</h1>
        <p>任务、资产和工作流运行记录都需要归属到明确项目。</p>
        {loading ? <p className="muted">正在加载项目...</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        <div className="project-card-grid">
          {projects.map((project) => (
            <button
              className={project.project_id === selectedProjectId ? "project-card active" : "project-card"}
              key={project.project_id}
              type="button"
              onClick={() => onSelectProject(project.project_id)}
            >
              <strong>{project.name}</strong>
              <span>{project.description || "项目工作空间"}</span>
              <small>{formatDate(project.created_at)}</small>
            </button>
          ))}
        </div>
        <button className="secondary-button" type="button" onClick={onReload}>
          刷新项目
        </button>
      </section>
      <section className="panel">
        <p className="eyebrow">新建</p>
        <h2>创建项目</h2>
        <form className="form-stack" onSubmit={handleCreate}>
          <label>
            <span>项目名称</span>
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            <span>项目说明</span>
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          {formError ? <p className="form-error">{formError}</p> : null}
          <button className="primary-button" disabled={saving} type="submit">
            {saving ? "创建中" : "创建项目"}
          </button>
        </form>
      </section>
    </main>
  );
}

function AssetLibraryPage({ project, onProjectRequired }: { project: ProjectRecord | null; onProjectRequired: () => void }) {
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [keyword, setKeyword] = useState("");
  const [scope, setScope] = useState<"combined" | "global">("combined");
  const [collections, setCollections] = useState<AssetCollection[]>([]);
  const [tags, setTags] = useState<AssetTag[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState("");
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [textName, setTextName] = useState("");
  const [textContent, setTextContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (scope === "combined" && !project) return;
    let active = true;
    setLoading(true);
    setMessage("");
    searchAssets({
      scope,
      project_id: scope === "combined" ? project?.project_id : undefined,
      keyword: keyword.trim() || undefined,
      collection_id: selectedCollectionId || undefined,
      tag_ids: selectedTagIds,
    })
      .then((items) => {
        if (!active) return;
        setAssets(items);
        setSelectedAssetId((current) => (items.some((asset) => asset.asset_id === current) ? current : items[0]?.asset_id ?? ""));
      })
      .catch((error) => {
        if (active) setMessage(readableError(error, "资产接口不可用，请稍后重试。"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [keyword, project, reloadKey, scope, selectedCollectionId, selectedTagIds]);

  useEffect(() => {
    if (scope === "combined" && !project) return;
    let active = true;
    Promise.all([
      listAssetCollections(scope, scope === "combined" ? project?.project_id : undefined),
      listAssetTags(scope, scope === "combined" ? project?.project_id : undefined),
    ])
      .then(([nextCollections, nextTags]) => {
        if (!active) return;
        setCollections(nextCollections);
        setTags(nextTags);
        setSelectedCollectionId((current) => (nextCollections.some((item) => item.collection_id === current) ? current : ""));
        setSelectedTagIds((current) => current.filter((tagId) => nextTags.some((tag) => tag.tag_id === tagId)));
      })
      .catch((error) => {
        if (active) setMessage(readableError(error, "资产目录或标签暂时不可用。"));
      });
    return () => {
      active = false;
    };
  }, [project, reloadKey, scope]);

  const selectedAsset = assets.find((asset) => asset.asset_id === selectedAssetId) ?? null;

  async function handleUpload() {
    if (!file) return;
    if (scope === "combined" && !project) {
      onProjectRequired();
      return;
    }
    await uploadAsset({
      file,
      scope: scope === "global" ? "global" : "project",
      project_id: scope === "global" ? undefined : project?.project_id,
      publish: true,
    });
    setFile(null);
    setReloadKey((current) => current + 1);
  }

  async function handleCreateText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!textName.trim() || !textContent.trim()) return;
    await createTextAsset({
      scope: scope === "global" ? "global" : "project",
      project_id: scope === "global" ? undefined : project?.project_id,
      name: textName.trim(),
      text: textContent,
    });
    setTextName("");
    setTextContent("");
    setReloadKey((current) => current + 1);
  }

  async function handleDownload(asset: AssetRecord) {
    const blob = await downloadAssetContent(asset.asset_id, asset.scope === "project" ? asset.project_id ?? project?.project_id : undefined);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = asset.name;
    link.click();
    URL.revokeObjectURL(url);
    setMessage(`已下载：${asset.name}`);
  }

  async function handleDelete(asset: AssetRecord) {
    await deleteAsset(asset.asset_id);
    setReloadKey((current) => current + 1);
  }

  async function handleCopyAssetUrl(asset: AssetRecord) {
    const url = asset.metadata.public_url;
    if (!url) return;
    await navigator.clipboard?.writeText(url);
    setMessage("已复制资产引用地址。");
  }

  return (
    <main className="asset-page">
      <section className="panel asset-toolbar">
        <div>
          <p className="eyebrow">AssetService</p>
          <h1>资产库</h1>
          <p>资产来自后端服务，项目资产和全局资产保持隔离。</p>
        </div>
        <div className="toolbar-actions">
          <button className={scope === "combined" ? "secondary-button active-control" : "secondary-button"} disabled={!project} type="button" onClick={() => setScope("combined")}>
            当前项目 + 全局
          </button>
          <button className={scope === "global" ? "secondary-button active-control" : "secondary-button"} type="button" onClick={() => setScope("global")}>
            全局资产
          </button>
          <input aria-label="搜索资产" placeholder="搜索资产" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
        </div>
        <div className="asset-filter-row">
          <label className="compact-field">
            <span>目录</span>
            <select aria-label="资产目录" value={selectedCollectionId} onChange={(event) => setSelectedCollectionId(event.target.value)}>
              <option value="">全部目录</option>
              {collections.map((collection) => (
                <option key={collection.collection_id} value={collection.collection_id}>
                  {collection.name}{collection.asset_count === undefined ? "" : ` (${collection.asset_count})`}
                </option>
              ))}
            </select>
          </label>
          <div className="tag-filter-group" aria-label="资产标签">
            {tags.length ? tags.map((tag) => {
              const checked = selectedTagIds.includes(tag.tag_id);
              return (
                <label className={checked ? "tag-filter active" : "tag-filter"} key={tag.tag_id}>
                  <input
                    checked={checked}
                    type="checkbox"
                    onChange={(event) => {
                      setSelectedTagIds((current) => event.target.checked ? [...current, tag.tag_id] : current.filter((item) => item !== tag.tag_id));
                    }}
                  />
                  <span>{tag.name}{tag.asset_count === undefined ? "" : ` ${tag.asset_count}`}</span>
                </label>
              );
            }) : <span className="muted">暂无标签</span>}
          </div>
        </div>
      </section>
      {message ? <p className="toast-message">{message}</p> : null}
      <div className="asset-layout">
        <section className="panel">
          <h2>资产列表</h2>
          {loading ? <p className="muted">正在加载资产...</p> : null}
          {!loading && !assets.length ? <p className="empty-box">暂无资产，可以上传文件或创建文字资产。</p> : null}
          <div className="asset-grid">
            {assets.map((asset) => (
              <button className={asset.asset_id === selectedAssetId ? "asset-card active" : "asset-card"} key={asset.asset_id} type="button" onClick={() => setSelectedAssetId(asset.asset_id)}>
                {asset.metadata.public_url && asset.mime_type?.startsWith("image/") ? <img src={asset.metadata.public_url} alt={asset.name} /> : <span className="asset-icon">{asset.asset_type === "text" ? "文" : "档"}</span>}
                <strong>{asset.name}</strong>
                <small>{asset.scope === "global" ? "全局资产" : "项目资产"} · {formatBytes(asset.size_bytes)}</small>
              </button>
            ))}
          </div>
        </section>
        <aside className="panel asset-detail-panel">
          <h2>资产详情</h2>
          {selectedAsset ? (
            <>
              <h3>{selectedAsset.name}</h3>
              <dl className="context-list">
                <div>
                  <dt>类型</dt>
                  <dd>{selectedAsset.mime_type || selectedAsset.asset_type}</dd>
                </div>
                <div>
                  <dt>范围</dt>
                  <dd>{selectedAsset.scope === "global" ? "全局资产" : "项目资产"}</dd>
                </div>
                <div>
                  <dt>大小</dt>
                  <dd>{formatBytes(selectedAsset.size_bytes)}</dd>
                </div>
                <div>
                  <dt>状态</dt>
                  <dd>{selectedAsset.deleted_at ? "已删除" : selectedAsset.metadata.public_url ? "已发布" : "未发布"}</dd>
                </div>
              </dl>
              {selectedAsset.metadata.public_url ? (
                <div className="button-row">
                  <a className="asset-link" href={selectedAsset.metadata.public_url} target="_blank" rel="noreferrer">
                    预览资产
                  </a>
                  <button className="secondary-button" type="button" onClick={() => void handleCopyAssetUrl(selectedAsset)}>
                    复制引用
                  </button>
                </div>
              ) : null}
              <div className="button-row">
                <button className="primary-button" type="button" onClick={() => void handleDownload(selectedAsset)}>
                  下载
                </button>
                <button className="secondary-button danger" type="button" onClick={() => void handleDelete(selectedAsset)}>
                  软删除
                </button>
              </div>
            </>
          ) : (
            <p className="muted">选择资产查看详情。</p>
          )}
          <div className="asset-create-stack">
            <label className="compact-field">
              <span>上传文件</span>
              <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            </label>
            <button className="secondary-button" disabled={!file} type="button" onClick={() => void handleUpload()}>
              上传到资产库
            </button>
            <form className="form-stack compact" onSubmit={handleCreateText}>
              <label>
                <span>文字资产名</span>
                <input value={textName} onChange={(event) => setTextName(event.target.value)} />
              </label>
              <label>
                <span>文字内容</span>
                <textarea value={textContent} onChange={(event) => setTextContent(event.target.value)} />
              </label>
              <button className="secondary-button" type="submit">
                创建文字资产
              </button>
            </form>
          </div>
        </aside>
      </div>
    </main>
  );
}

function workflowToTemplate(item: WorkflowListItem): WorkflowTemplate {
  return {
    id: item.workflow.id,
    version: item.workflow.version,
    name: item.workflow.name,
    description: item.workflow.description || "后端工作流模板",
    inputSchema: item.workflow.input_schema,
    contract: { workflow: item.workflow, nodes: item.nodes, edges: item.edges ?? [] },
    nodes: item.nodes.map((node) => node.id),
  };
}

function initialValues(schema?: JsonSchema): Record<string, string | boolean | string[]> {
  const values: Record<string, string | boolean | string[]> = {};
  for (const field of buildSchemaFields(schema)) {
    if (field.control === "checkbox") values[field.key] = Boolean(field.defaultValue);
    else if (field.control === "asset_images" && field.type === "array") values[field.key] = [];
    else values[field.key] = field.defaultValue === undefined ? "" : String(field.defaultValue);
  }
  return values;
}

function validateFields(fields: SchemaField[], values: Record<string, string | boolean | string[]>): string {
  for (const field of fields) {
    const value = values[field.key];
    const emptyArray = Array.isArray(value) && value.length === 0;
    if (field.required && (value === undefined || value === "" || emptyArray)) {
      return `请填写${field.label}。`;
    }
  }
  return "";
}

function buildInputData(fields: SchemaField[], values: Record<string, string | boolean | string[]>): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.key];
    if (field.control === "asset_images") {
      if (field.type === "string") data[field.key] = Array.isArray(value) ? value[0] ?? "" : value ?? "";
      else data[field.key] = Array.isArray(value) ? value : splitLines(String(value ?? ""));
    } else if (field.type === "number" || field.type === "integer") {
      data[field.key] = value === "" || value === undefined ? null : Number(value);
    } else if (field.type === "boolean") {
      data[field.key] = Boolean(value);
    } else if (field.type === "array") {
      data[field.key] = Array.isArray(value) ? value : splitLines(String(value ?? ""));
    } else {
      data[field.key] = value ?? "";
    }
  }
  return data;
}

function orderNodes(detail: TaskDetailResponse | null): TaskNodeExecution[] {
  if (!detail) return [];
  const byId = new Map(detail.node_executions.map((node) => [node.node_id, node]));
  const ordered = detail.workflow_snapshot?.nodes?.map((node) => byId.get(node.id)).filter(Boolean) as TaskNodeExecution[] | undefined;
  if (!ordered?.length) return detail.node_executions;
  const extras = detail.node_executions.filter((node) => !ordered.some((orderedNode) => orderedNode.node_id === node.node_id));
  return [...ordered, ...extras];
}

function nodeSectionDefaultOpen(snapshot: WorkflowSnapshot | null | undefined, section: "input" | "output" | "events", fallback: boolean): boolean {
  const layout = snapshot?.workflow?.ui?.layout;
  if (layout?.default_expanded_sections?.includes(section)) return true;
  if (layout?.default_collapsed_sections?.includes(section)) return false;
  return fallback;
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function readQuestion(inputSnapshot: unknown, nodeSpec?: WorkflowNodeSpec): string {
  if (typeof inputSnapshot === "object" && inputSnapshot !== null) {
    const input = inputSnapshot as Record<string, unknown>;
    if (typeof input.question === "string") return input.question;
  }
  const question = nodeSpec?.inputs?.question;
  if (typeof question === "object" && question !== null) {
    const record = question as Record<string, unknown>;
    if (typeof record.value === "string") return record.value;
    if (typeof record.template === "string") return record.template;
  }
  return "";
}

function interactionMode(outputKeys: string[], requiredKeys: string[], nodeSpec?: WorkflowNodeSpec): "text" | "image_urls" | "approval" {
  const mode = nodeSpec?.ui?.mode;
  if (mode === "text" || mode === "input") return "text";
  if (mode === "approve_reject") return "approval";
  if (requiredKeys.includes("answer") || outputKeys.includes("answer")) return "text";
  if (requiredKeys.includes("image_urls") || outputKeys.includes("image_urls")) return "image_urls";
  return "approval";
}

function formatBytes(size: number | null): string {
  if (size === null || Number.isNaN(size)) return "未知大小";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function readableError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
