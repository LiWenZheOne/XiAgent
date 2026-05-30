import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  attachAssetTag,
  createAssetCollection,
  createAssetTag,
  deleteAsset,
  deleteAssetCollection,
  deleteAssetTag,
  detachAssetTag,
  downloadAssetContent,
  listAssetCollections,
  listAssetTags,
  listAssetTagsForAsset,
  searchAssets,
  updateAsset,
  updateAssetCollection,
  uploadAsset,
} from "../api/assets";
import { getCurrentUser, login, register } from "../api/auth";
import { ApiError, clearAccessToken, getAccessToken } from "../api/client";
import { createProject, listProjects } from "../api/projects";
import { createTask, deleteTask, getTask, listTasks, rerunNode, saveInteractionDraft, streamTaskEvents, submitInteraction } from "../api/tasks";
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
  WorkflowUiStage,
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
  nodeDisplayTitle,
  statusLabel,
  statusTone,
  taskTime,
  taskTitle,
} from "../utils/display";

type Route = "workbench" | "assets" | "projects" | "controls";

interface SessionState {
  username: string;
}

interface TaskRuntimeContext {
  status: string;
  currentNodeLabel: string;
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
  const [session, setSession] = useState<SessionState | null>(null);
  const [recoveringSession, setRecoveringSession] = useState(() => Boolean(getAccessToken()));
  const [route, setRoute] = useState<Route>("projects");
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

  useEffect(() => {
    if (!getAccessToken()) {
      setRecoveringSession(false);
      return;
    }
    let active = true;
    setRecoveringSession(true);
    getCurrentUser()
      .then((user) => {
        if (active) setSession({ username: user.username });
      })
      .catch((error) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          handleLogout();
          return;
        }
        handleLogout();
      })
      .finally(() => {
        if (active) setRecoveringSession(false);
      });
    return () => {
      active = false;
    };
  }, []);

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
    setRecoveringSession(false);
    setProjects([]);
    setTasks([]);
    setSelectedProjectId("");
    setSelectedTaskId("");
    setProjectError("");
    setTaskError("");
  }

  if (recoveringSession) {
    return (
      <main className="auth-page">
        <section className="auth-card">
          <div className="brand-mark large">X</div>
          <p className="eyebrow">XiAgent V2</p>
          <h1>恢复登录</h1>
          <p>正在确认当前账号。</p>
        </section>
      </main>
    );
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
          <button className={route === "projects" ? "nav-button active" : "nav-button"} type="button" onClick={() => setRoute("projects")}>
            项目
          </button>
          <button className={route === "workbench" ? "nav-button active" : "nav-button"} type="button" onClick={() => setRoute("workbench")}>
            任务工作台
          </button>
          <button className={route === "assets" ? "nav-button active" : "nav-button"} type="button" onClick={() => setRoute("assets")}>
            资产库
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
          tasks={tasks}
          selectedProject={selectedProject}
          selectedTaskId={selectedTaskId}
          creatingTask={creatingTask}
          taskLoading={taskLoading}
          taskError={taskError}
          onBackToProjects={() => setRoute("projects")}
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
          onTaskUpdated={(task) => {
            setTasks((current) => current.map((item) => (item.task_id === task.task_id ? { ...item, ...task } : item)));
          }}
          onDeleteTask={async (task) => {
            if (!selectedProjectId) return;
            await deleteTask(selectedProjectId, task.task_id);
            setTasks((current) => current.filter((item) => item.task_id !== task.task_id));
            if (selectedTaskId === task.task_id) setSelectedTaskId("");
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
            setReloadTasksKey((current) => current + 1);
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
  tasks,
  selectedProject,
  selectedTaskId,
  creatingTask,
  taskLoading,
  taskError,
  onBackToProjects,
  onCreateTask,
  onSelectTask,
  onTaskCreated,
  onTaskUpdated,
  onDeleteTask,
  onRefreshTasks,
}: {
  tasks: TaskRecord[];
  selectedProject: ProjectRecord | null;
  selectedTaskId: string;
  creatingTask: boolean;
  taskLoading: boolean;
  taskError: string;
  onBackToProjects: () => void;
  onCreateTask: () => void;
  onSelectTask: (taskId: string) => void;
  onTaskCreated: (task: TaskRecord) => void;
  onTaskUpdated: (task: TaskRecord) => void;
  onDeleteTask: (task: TaskRecord) => Promise<void>;
  onRefreshTasks: () => void;
}) {
  const selectedTask = tasks.find((task) => task.task_id === selectedTaskId) ?? null;
  const [runtimeContext, setRuntimeContext] = useState<TaskRuntimeContext | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<TaskRecord | null>(null);
  const [deletingTaskId, setDeletingTaskId] = useState("");
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    setRuntimeContext(null);
  }, [selectedTaskId, selectedProject?.project_id]);

  const contextStatus = runtimeContext?.status ?? selectedTask?.status ?? "";
  const contextCurrentNode = runtimeContext?.currentNodeLabel
    ?? (selectedTask?.current_node_id ? formatFieldLabel(selectedTask.current_node_id) : "未记录");

  async function handleConfirmDelete() {
    if (!deleteCandidate) return;
    setDeletingTaskId(deleteCandidate.task_id);
    setDeleteError("");
    try {
      await onDeleteTask(deleteCandidate);
      setDeleteCandidate(null);
    } catch (nextError) {
      setDeleteError(readableError(nextError, "任务删除失败，请刷新后重试。"));
    } finally {
      setDeletingTaskId("");
    }
  }

  return (
    <main className="workspace-grid">
      <aside className="workspace-sidebar">
        <section className="sidebar-section">
          <div className="section-title-row">
            <div>
              <p className="eyebrow">当前项目</p>
              <h2>{selectedProject?.name ?? "未选择项目"}</h2>
            </div>
            <button className="secondary-button compact" type="button" onClick={onBackToProjects}>
              返回项目
            </button>
          </div>
          {selectedProject ? (
            <dl className="project-summary-list">
              <div>
                <dt>说明</dt>
                <dd>{selectedProject.description || "项目工作空间"}</dd>
              </div>
              <div>
                <dt>创建时间</dt>
                <dd>{formatDate(selectedProject.created_at)}</dd>
              </div>
            </dl>
          ) : (
            <div className="empty-box">
              <strong>先选择项目</strong>
              <button className="secondary-button" type="button" onClick={onBackToProjects}>
                返回项目页
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
            <span>选择工作流并创建任务</span>
          </button>
          {taskLoading ? <p className="muted">正在加载任务...</p> : null}
          {taskError ? <p className="form-error">{taskError}</p> : null}
          <div className="task-list">
            {tasks.map((task) => (
              <div className="task-row-shell" key={task.task_id}>
                <button
                  aria-label={`打开 ${taskTitle(task)}`}
                  className={selectedTaskId === task.task_id ? "task-row active" : "task-row"}
                  type="button"
                  onClick={() => onSelectTask(task.task_id)}
                >
                  <span className={`status-badge ${statusTone(task.status)}`}>{statusLabel(task.status)}</span>
                  <strong>{taskTitle(task)}</strong>
                  <span>{task.workflow_version ? `版本 ${task.workflow_version}` : statusLabel(task.status)}</span>
                  <small>{taskTime(task)}</small>
                </button>
                <button
                  aria-label={`删除任务 ${task.task_id}`}
                  className="task-delete-button"
                  type="button"
                  onClick={() => {
                    setDeleteError("");
                    setDeleteCandidate(task);
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          {deleteCandidate ? (
            <div className="confirm-backdrop" role="presentation">
              <section className="confirm-dialog" role="dialog" aria-modal="true" aria-label="确认删除任务">
                <h2>确认删除任务</h2>
                <p>删除后，这个任务实例、节点执行记录和事件记录将从当前项目中移除。</p>
                <strong>{taskTitle(deleteCandidate)}</strong>
                {deleteError ? <p className="form-error">{deleteError}</p> : null}
                <div className="button-row end">
                  <button className="secondary-button" type="button" onClick={() => setDeleteCandidate(null)} disabled={Boolean(deletingTaskId)}>
                    取消
                  </button>
                  <button className="primary-button danger" type="button" onClick={handleConfirmDelete} disabled={Boolean(deletingTaskId)}>
                    {deletingTaskId ? "删除中" : "确认删除"}
                  </button>
                </div>
              </section>
            </div>
          ) : null}
        </section>
      </aside>

      <section className="workspace-main">
        {creatingTask && selectedProject ? <CreateTaskPanel project={selectedProject} onTaskCreated={onTaskCreated} /> : null}
        {!creatingTask && selectedProject && selectedTask ? (
          <TaskDetailPanel
            projectId={selectedProject.project_id}
            taskId={selectedTask.task_id}
            onRuntimeContextChange={setRuntimeContext}
            onTaskChanged={onRefreshTasks}
            onTaskUpdated={onTaskUpdated}
          />
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
            <dd>{contextStatus ? statusLabel(contextStatus) : "无"}</dd>
          </div>
          <div>
            <dt>当前节点</dt>
            <dd>{selectedTask ? contextCurrentNode : "未记录"}</dd>
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
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    listWorkflows(project.project_id)
      .then((workflowItems) => {
        if (!active) return;
        const nextTemplates = workflowItems.map(workflowToTemplate);
        setTemplates(nextTemplates);
        setSelectedWorkflowId(nextTemplates[0]?.id ?? "");
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
    setSelectedWorkflowId(workflowId);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTemplate) return;
    setSaving(true);
    setError("");
    try {
      const task = await createTask({
        project_id: project.project_id,
        contract: selectedTemplate.contract,
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
          <p>选择后端工作流模板，查看启动说明和输入项摘要。任务创建后进入详情，由第一个输入节点收集参数。</p>
        </div>
      </div>

      {loading ? <p className="muted">正在读取工作流模板...</p> : null}
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
            <h2>启动信息</h2>
            {fields.length === 0 ? <p className="empty-box">这个工作流不需要起始输入。</p> : null}
            {fields.map((field) => (
              <div className="workflow-field-summary" key={field.key}>
                <strong>{field.label}{field.required ? " *" : ""}</strong>
                <span>{field.description || field.type}</span>
              </div>
            ))}
            {fields.length ? <p className="muted">这些参数将在任务详情的第一个输入节点中填写。</p> : null}
            <button className="primary-button full-width" disabled={saving} type="submit">
              {saving ? "创建中" : "创建并运行"}
            </button>
          </section>
        </form>
      ) : null}
    </section>
  );
}

function TaskDetailPanel({
  projectId,
  taskId,
  onRuntimeContextChange,
  onTaskChanged,
  onTaskUpdated,
}: {
  projectId: string;
  taskId: string;
  onRuntimeContextChange: (context: TaskRuntimeContext | null) => void;
  onTaskChanged: () => void;
  onTaskUpdated: (task: TaskRecord) => void;
}) {
  const [detail, setDetail] = useState<TaskDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [rerunCandidateNodeId, setRerunCandidateNodeId] = useState<string | null>(null);
  const [rerunRevisionNote, setRerunRevisionNote] = useState("");
  const [rerunningNodeId, setRerunningNodeId] = useState("");
  const [rerunError, setRerunError] = useState("");
  const [liveEvents, setLiveEvents] = useState<TaskEvent[]>([]);
  const [revealedNodeOrder, setRevealedNodeOrder] = useState<Record<string, number>>({});
  const [pendingTransitionNodeId, setPendingTransitionNodeId] = useState<string | null>(null);
  const revealSequenceRef = useRef(0);
  const revealedNodeOrderRef = useRef<Record<string, number>>({});
  const stepRevealModeRef = useRef(false);
  const liveRevealDelayRef = useRef(0);
  const scheduledRevealIdsRef = useRef<Set<string>>(new Set());
  const baselineEventIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    setLiveEvents([]);
    setRevealedNodeOrder({});
    revealSequenceRef.current = 0;
    revealedNodeOrderRef.current = {};
    stepRevealModeRef.current = false;
    liveRevealDelayRef.current = 0;
    scheduledRevealIdsRef.current = new Set();
    baselineEventIdsRef.current = new Set();
    setPendingTransitionNodeId(null);
  }, [projectId, taskId]);

  function revealNodeStep(nodeId: string | null | undefined, delayMs = 0) {
    if (!nodeId) return;
    if (delayMs > 0) {
      window.setTimeout(() => revealNodeStep(nodeId), delayMs);
      return;
    }
    setRevealedNodeOrder((current) => {
      if (current[nodeId] !== undefined) return current;
      const next = { ...current, [nodeId]: revealSequenceRef.current++ };
      revealedNodeOrderRef.current = next;
      return next;
    });
  }

  function scheduleNodeStepReveal(nodeId: string | null | undefined) {
    if (!nodeId || revealedNodeOrderRef.current[nodeId] !== undefined || scheduledRevealIdsRef.current.has(nodeId)) return;
    scheduledRevealIdsRef.current.add(nodeId);
    const delay = liveRevealDelayRef.current;
    liveRevealDelayRef.current = Math.min(delay + 180, 2200);
    revealNodeStep(nodeId, delay);
  }

  function clearRevealedNodeSteps(nodeIds: Set<string>) {
    if (!nodeIds.size) return;
    scheduledRevealIdsRef.current = new Set([...scheduledRevealIdsRef.current].filter((nodeId) => !nodeIds.has(nodeId)));
    const next = { ...revealedNodeOrderRef.current };
    let changed = false;
    for (const nodeId of nodeIds) {
      if (next[nodeId] === undefined) continue;
      delete next[nodeId];
      changed = true;
    }
    if (!changed) return;
    revealedNodeOrderRef.current = next;
    setRevealedNodeOrder(next);
  }

  function rememberCurrentEventsAsBaseline() {
    baselineEventIdsRef.current = new Set([
      ...baselineEventIdsRef.current,
      ...mergeTaskEvents(detail?.events ?? [], liveEvents).map(taskEventIdentity),
    ]);
  }

  function revealNodesFromDetail(nextDetail: TaskDetailResponse) {
    const ordered = orderNodes(nextDetail).filter((node) => Boolean(node.node_execution_id));
    setRevealedNodeOrder((current) => {
      const next = { ...current };
      const addNode = (nodeId: string | null | undefined) => {
        if (!nodeId || next[nodeId] !== undefined) return;
        next[nodeId] = revealSequenceRef.current++;
      };
      const firstDetailLoad = Object.keys(next).length === 0;
      if (firstDetailLoad || !stepRevealModeRef.current) {
        for (const node of ordered) addNode(node.node_id);
      } else {
        addNode(nextDetail.task.current_node_id);
        for (const node of ordered) {
          const label = statusLabel(node.status);
          if (label === "运行中" || label === "等待用户" || label === "失败") addNode(node.node_id);
        }
      }
      const changed = Object.keys(next).length !== Object.keys(current).length;
      if (changed) revealedNodeOrderRef.current = next;
      return changed ? next : current;
    });
    if (!stepRevealModeRef.current) {
      baselineEventIdsRef.current = new Set(nextDetail.events.map(taskEventIdentity));
    }
  }

  useEffect(() => {
    let active = true;
    setLoading(!detail);
    setError("");
    getTask(projectId, taskId)
      .then((nextDetail) => {
        if (!active) return;
        onRuntimeContextChange(taskRuntimeContext(nextDetail, orderNodes(nextDetail)));
        onTaskUpdated(nextDetail.task);
        setDetail(nextDetail);
        revealNodesFromDetail(nextDetail);
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
      (event) => {
        const liveEvent = normalizeLiveTaskEvent(event);
        const eventKey = taskEventIdentity(liveEvent);
        setLiveEvents((current) => mergeTaskEvents(current, [liveEvent]));
        if (stepRevealModeRef.current && !baselineEventIdsRef.current.has(eventKey) && taskEventRevealsNode(liveEvent)) {
          scheduleNodeStepReveal(nodeIdFromTaskEvent(liveEvent));
        }
        baselineEventIdsRef.current.add(eventKey);
        setRefreshKey((current) => current + 1);
      },
      (nextError) => setError(readableError(nextError, "任务事件连接失败，请刷新后重试。")),
    );
  }, [projectId, taskId]);

  const eventsByNode = useMemo(() => {
    const grouped = new Map<string, TaskEvent[]>();
    for (const event of mergeTaskEvents(detail?.events ?? [], liveEvents)) {
      const nodeId = nodeIdFromTaskEvent(event);
      if (!nodeId) continue;
      grouped.set(nodeId, [...(grouped.get(nodeId) ?? []), event]);
    }
    return grouped;
  }, [detail, liveEvents]);

  const orderedNodes = useMemo(() => orderNodes(detail), [detail]);
  const rerunCandidateNode = useMemo(
    () => orderedNodes.find((node) => node.node_id === rerunCandidateNodeId) ?? null,
    [orderedNodes, rerunCandidateNodeId],
  );

  useEffect(() => {
    if (!pendingTransitionNodeId || !detail) return;
    const pendingOrder = revealedNodeOrder[pendingTransitionNodeId];
    const hasLaterRevealedNode = orderedNodes.some((node) => (
      node.node_id !== pendingTransitionNodeId
      && revealedNodeOrder[node.node_id] !== undefined
      && (pendingOrder === undefined || (revealedNodeOrder[node.node_id] ?? -1) > pendingOrder)
    ));
    const taskDone = ["成功", "失败"].includes(statusLabel(detail.task.status));
    if (hasLaterRevealedNode || taskDone) {
      setPendingTransitionNodeId(null);
    }
  }, [
    detail,
    orderedNodes.map((node) => `${node.node_id}:${node.status}:${node.node_execution_id ?? ""}`).join("|"),
    pendingTransitionNodeId,
    revealedNodeOrder,
  ]);

  async function handleRerun(nodeId: string) {
    setRerunError("");
    setRerunRevisionNote("");
    setRerunCandidateNodeId(nodeId);
  }

  async function handleConfirmRerun() {
    if (!rerunCandidateNodeId) return;
    const nodeId = rerunCandidateNodeId;
    const affectedNodeIds = workflowDownstreamNodeIds(detail?.workflow_snapshot, nodeId);
    setRerunningNodeId(nodeId);
    setRerunError("");
    rememberCurrentEventsAsBaseline();
    stepRevealModeRef.current = true;
    liveRevealDelayRef.current = 0;
    scheduledRevealIdsRef.current = new Set();
    clearRevealedNodeSteps(affectedNodeIds);
    revealNodeStep(nodeId);
    setPendingTransitionNodeId(nodeId);
    try {
      await rerunNode(taskId, nodeId, projectId, rerunRevisionNote);
      setRerunCandidateNodeId(null);
      setRerunRevisionNote("");
      onTaskChanged();
      setRefreshKey((current) => current + 1);
    } catch (nextError) {
      setRerunError(readableError(nextError, "重新运行失败，请检查任务状态后重试。"));
    } finally {
      setRerunningNodeId("");
    }
  }

  function markInteractionRunning(nodeId: string) {
    if (!detail) return;
    rememberCurrentEventsAsBaseline();
    stepRevealModeRef.current = true;
    liveRevealDelayRef.current = 0;
    scheduledRevealIdsRef.current = new Set();
    revealNodeStep(nodeId);
    setPendingTransitionNodeId(nodeId);
    const nextDetail = {
      ...detail,
      task: { ...detail.task, status: "running", current_node_id: nodeId },
    };
    setDetail(nextDetail);
    onRuntimeContextChange(taskRuntimeContext(nextDetail, orderNodes(nextDetail)));
    onTaskUpdated(nextDetail.task);
  }

  async function handleInteraction(nodeId: string, input: Record<string, unknown>) {
    markInteractionRunning(nodeId);
    try {
      const task = await submitInteraction(taskId, { project_id: projectId, node_id: nodeId, input });
      onTaskUpdated(task);
      setDetail((current) => (current ? { ...current, task: { ...current.task, ...task } } : current));
    } finally {
      onTaskChanged();
      setRefreshKey((current) => current + 1);
    }
  }

  async function handleInteractionDraft(nodeId: string, input: Record<string, unknown>) {
    const task = await saveInteractionDraft(taskId, { project_id: projectId, node_id: nodeId, input });
    onTaskUpdated(task);
    setDetail((current) => (current ? { ...current, task: { ...current.task, ...task } } : current));
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

          <WorkflowProgressView
            eventsByNode={eventsByNode}
            nodes={orderedNodes}
            projectId={projectId}
            pendingTransitionNodeId={pendingTransitionNodeId}
            revealedNodeOrder={revealedNodeOrder}
            snapshot={detail.workflow_snapshot}
            onInteractionDraft={handleInteractionDraft}
            onInteraction={handleInteraction}
            onRerun={handleRerun}
          />
          {rerunCandidateNode ? (
            <div className="confirm-backdrop" role="presentation">
              <section className="confirm-dialog" role="dialog" aria-modal="true" aria-label="确认重新运行步骤">
                <h2>确认重新运行步骤</h2>
                <p>重新运行此步骤会使该步骤及其下游已完成结果失效，并从这里重新执行。历史记录会保留。</p>
                <strong>{nodeDisplayTitle(rerunCandidateNode, detail.workflow_snapshot)}</strong>
                <label className="rerun-revision-field">
                  <span>修改意见</span>
                  <textarea
                    disabled={Boolean(rerunningNodeId)}
                    placeholder="可填写本次重新运行的修改意见，例如不要生成某类配件、保留某个字段、修正上次结果的问题。"
                    value={rerunRevisionNote}
                    onChange={(event) => setRerunRevisionNote(event.target.value)}
                  />
                </label>
                {rerunError ? <p className="form-error">{rerunError}</p> : null}
                <div className="button-row end">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => {
                      setRerunCandidateNodeId(null);
                      setRerunRevisionNote("");
                    }}
                    disabled={Boolean(rerunningNodeId)}
                  >
                    取消
                  </button>
                  <button className="primary-button danger" type="button" onClick={() => void handleConfirmRerun()} disabled={Boolean(rerunningNodeId)}>
                    {rerunningNodeId ? "重新运行中" : "确认重新运行"}
                  </button>
                </div>
              </section>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function WorkflowProgressView({
  nodes,
  eventsByNode,
  projectId,
  pendingTransitionNodeId,
  revealedNodeOrder,
  snapshot,
  onInteractionDraft,
  onInteraction,
  onRerun,
}: {
  nodes: TaskNodeExecution[];
  eventsByNode: Map<string, TaskEvent[]>;
  projectId: string;
  pendingTransitionNodeId: string | null;
  revealedNodeOrder: Record<string, number>;
  snapshot?: WorkflowSnapshot | null;
  onInteractionDraft: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
  onInteraction: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
  onRerun: (nodeId: string) => Promise<void>;
}) {
  const stages = workflowStages(snapshot);
  const pendingTransitionStageIndex = pendingTransitionNodeId
    ? stages.findIndex((stage) => stage.nodes.includes(pendingTransitionNodeId))
    : -1;
  const stepOrdinalByNodeId = useMemo(() => {
    const ordinals = new Map<string, number>();
    let ordinal = 1;
    const nodeById = new Map(nodes.map((node) => [node.node_id, node]));
    for (const stage of stages) {
      for (const nodeId of stage.nodes) {
        const node = nodeById.get(nodeId);
        if (!node?.node_execution_id || revealedNodeOrder[node.node_id] === undefined) continue;
        ordinals.set(node.node_id, ordinal++);
      }
    }
    return ordinals;
  }, [nodes, revealedNodeOrder, stages]);
  if (!stages.length) {
    return (
      <section className="node-timeline">
        {nodes.map((node, index) => (
          <NodeExecutionCard
            events={eventsByNode.get(node.node_id) ?? []}
            index={index}
            key={node.node_execution_id ?? `${node.node_id}-${index}`}
            node={node}
            projectId={projectId}
            snapshot={snapshot}
            onInteractionDraft={onInteractionDraft}
            onInteraction={onInteraction}
            onRerun={onRerun}
          />
        ))}
        {nodes.length === 0 ? <section className="panel">任务还没有节点执行记录。</section> : null}
      </section>
    );
  }

  return (
    <section className="workflow-stage-list">
      {stages.map((stage, index) => (
        <WorkflowStageCard
          eventsByNode={eventsByNode}
          index={index}
          key={stage.id}
          nodes={stage.nodes.map((nodeId) => nodes.find((node) => node.node_id === nodeId)).filter(Boolean) as TaskNodeExecution[]}
          projectId={projectId}
          revealedNodeOrder={revealedNodeOrder}
          showPreparingNextStage={pendingTransitionStageIndex === index}
          snapshot={snapshot}
          stage={stage}
          stepOrdinalByNodeId={stepOrdinalByNodeId}
          onInteractionDraft={onInteractionDraft}
          onInteraction={onInteraction}
          onRerun={onRerun}
        />
      ))}
    </section>
  );
}

function WorkflowStageCard({
  stage,
  nodes,
  index,
  eventsByNode,
  projectId,
  revealedNodeOrder,
  showPreparingNextStage,
  snapshot,
  onInteractionDraft,
  onInteraction,
  onRerun,
  stepOrdinalByNodeId,
}: {
  stage: WorkflowUiStage;
  nodes: TaskNodeExecution[];
  index: number;
  eventsByNode: Map<string, TaskEvent[]>;
  projectId: string;
  revealedNodeOrder: Record<string, number>;
  showPreparingNextStage: boolean;
  snapshot?: WorkflowSnapshot | null;
  stepOrdinalByNodeId: Map<string, number>;
  onInteractionDraft: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
  onInteraction: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
  onRerun: (nodeId: string) => Promise<void>;
}) {
  const visibleNodes = nodes.filter((node) => Boolean(node.node_execution_id) && revealedNodeOrder[node.node_id] !== undefined);
  const [expanded, setExpanded] = useState(() => visibleNodes.some(nodeShouldDefaultExpand) || (index === 0 && visibleNodes.length > 0));
  const [expandedNodeId, setExpandedNodeId] = useState<string | null>(() => defaultExpandedStageNodeId(visibleNodes, snapshot));
  const stageStatus = stageStatusLabel(visibleNodes);

  useEffect(() => {
    if (visibleNodes.some(nodeShouldDefaultExpand) || (index === 0 && visibleNodes.length > 0)) setExpanded(true);
    const defaultNodeId = defaultExpandedStageNodeId(visibleNodes, snapshot);
    if (defaultNodeId) setExpandedNodeId((current) => current ?? defaultNodeId);
  }, [snapshot, visibleNodes.map((node) => `${node.node_id}:${node.status}`).join("|")]);

  return (
    <article className="workflow-stage-card">
      <header
        className="workflow-stage-header"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
        onKeyDown={(event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          setExpanded((current) => !current);
        }}
      >
        <div>
          <h2>{stage.name}</h2>
          {stage.description ? <p>{stage.description}</p> : null}
        </div>
        <div className="node-actions">
          <span className={`status-badge ${stageTone(visibleNodes)}`}>{stageStatus}</span>
        </div>
      </header>
      {!expanded ? (
        <>
          <StageProgressRail
            nodes={visibleNodes}
            snapshot={snapshot}
            stepOrdinalByNodeId={stepOrdinalByNodeId}
          />
          {showPreparingNextStage ? <PreparingNextStage compact /> : null}
        </>
      ) : null}
      {expanded ? (
        <div className="stage-step-list">
          {visibleNodes.length ? visibleNodes.map((node, nodeIndex) => {
            const isOpen = expandedNodeId === node.node_id;
            const nodeEvents = eventsByNode.get(node.node_id) ?? [];
            const progress = nodeProgressValue(node);
            const showSubmit = nodeUsesStageHeaderSubmit(node, snapshot);
            const showRerun = !showSubmit && nodeCanRerun(node, snapshot);
            return (
              <div className="stage-step-entry" key={node.node_execution_id ?? `${node.node_id}-${nodeIndex}`}>
                <div
                  className={`stage-step-row ${nodeIsInMotion(node) ? "in-motion" : ""}`}
                  aria-expanded={isOpen}
                  onClick={(event) => {
                    if ((event.target as HTMLElement).closest("button")) return;
                    setExpandedNodeId((current) => (current === node.node_id ? null : node.node_id));
                  }}
                >
                  <button
                    className="stage-step-toggle"
                    type="button"
                    aria-expanded={isOpen}
                    onClick={() => setExpandedNodeId((current) => (current === node.node_id ? null : node.node_id))}
                  >
                    <span className="stage-step-indicator">{`S${stepOrdinalByNodeId.get(node.node_id) ?? nodeIndex + 1}`}</span>
                    <span className="stage-step-main">
                      <strong>{nodeDisplayTitle(node, snapshot)}</strong>
                      <span className="stage-step-subline">
                        <small>{nodeActivityText(node, eventsByNode, snapshot)}</small>
                        <span>{progress}%</span>
                      </span>
                      <span className="stage-step-progress" aria-hidden="true">
                        <span style={{ width: `${progress}%` }} />
                      </span>
                    </span>
                  </button>
                  <span className="stage-step-actions">
                    <span className={`status-badge ${statusTone(node.status)}`}>{statusLabel(node.status)}</span>
                    {showSubmit ? (
                      <button className="primary-button stage-step-action" form={nodeInputFormId(node)} type="submit">
                        运行下一步
                      </button>
                    ) : null}
                    {showRerun ? (
                      <button className="secondary-button stage-step-action" type="button" onClick={() => void onRerun(node.node_id)}>
                        重新运行
                      </button>
                    ) : null}
                  </span>
                </div>
                {isOpen ? (
                  <div className="stage-node-details">
                    <NodeExecutionDetails
                      events={nodeEvents}
                      node={node}
                      projectId={projectId}
                      snapshot={snapshot}
                      onInteractionDraft={onInteractionDraft}
                      onInteraction={onInteraction}
                      onRerun={onRerun}
                    />
                  </div>
                ) : null}
              </div>
            );
          }) : <p className="muted">执行到该阶段后会生成步骤记录。</p>}
          {showPreparingNextStage ? <PreparingNextStage /> : null}
        </div>
      ) : null}
    </article>
  );
}

function PreparingNextStage({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`stage-preparing-next ${compact ? "compact" : ""}`} role="status" aria-live="polite">
      <span aria-hidden="true" />
      <p>正在准备下一阶段...</p>
    </div>
  );
}

function StageProgressRail({
  nodes,
  snapshot,
  stepOrdinalByNodeId,
}: {
  nodes: TaskNodeExecution[];
  snapshot?: WorkflowSnapshot | null;
  stepOrdinalByNodeId: Map<string, number>;
}) {
  if (!nodes.length) {
    return <p className="stage-progress-empty">执行到该阶段后会生成步骤记录。</p>;
  }
  const completedCount = nodes.filter((node) => statusLabel(node.status) === "成功").length;
  const percent = Math.round((completedCount / nodes.length) * 100);
  return (
    <div className="stage-progress-rail" aria-label={`阶段进度 ${percent}%`}>
      <span className="stage-progress-line" aria-hidden="true" />
      {nodes.map((node, index) => {
        const ordinal = stepOrdinalByNodeId.get(node.node_id) ?? index + 1;
        const tone = statusTone(node.status);
        return (
          <div className={`stage-progress-node ${tone}`} key={node.node_execution_id ?? `${node.node_id}-${index}`}>
            <strong>{`S${ordinal}`}</strong>
            <span aria-hidden="true" />
            <small>{nodeDisplayTitle(node, snapshot)}</small>
          </div>
        );
      })}
    </div>
  );
}

function NodeExecutionCard({
  node,
  index,
  events,
  projectId,
  snapshot,
  onInteractionDraft,
  onInteraction,
  onRerun,
  initialExpanded,
}: {
  node: TaskNodeExecution;
  index: number;
  events: TaskEvent[];
  projectId: string;
  snapshot?: WorkflowSnapshot | null;
  onInteractionDraft: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
  onInteraction: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
  onRerun: (nodeId: string) => Promise<void>;
  initialExpanded?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [actionError, setActionError] = useState("");
  const nodeSpec = snapshot?.nodes?.find((item) => item.id === node.node_id);
  const displayTitle = nodeDisplayTitle(node, snapshot);
  const nodeStatusLabel = statusLabel(node.status);
  const canRerun = nodeCanRerun(node, snapshot);
  const [expanded, setExpanded] = useState(() => initialExpanded ?? nodeShouldDefaultExpand(node));

  useEffect(() => {
    if (nodeShouldDefaultExpand(node)) setExpanded(true);
  }, [node.node_execution_id, node.status, initialExpanded]);

  async function withBusy(action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError("");
    try {
      await action();
    } catch (nextError) {
      setActionError(nodeActionError(nextError));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <article className="node-card">
      <div className="timeline-dot">{index + 1}</div>
      <div className="node-card-content">
        <header className="node-header">
          <div>
            <h2>{displayTitle}</h2>
          </div>
          <div className="node-actions">
            <span className={`status-badge ${statusTone(node.status)}`}>{nodeStatusLabel}</span>
            <button
              aria-expanded={expanded}
              className="secondary-button node-expand-button"
              type="button"
              onClick={() => setExpanded((current) => !current)}
            >
              {expanded ? "收起" : "展开"}
            </button>
            {canRerun ? (
              <button className="secondary-button" disabled={busy} type="button" onClick={() => withBusy(() => onRerun(node.node_id))}>
                重新运行
              </button>
            ) : null}
          </div>
        </header>
        {actionError ? <p className="form-error">{actionError}</p> : null}

        {expanded ? (
          <NodeExecutionDetails
            events={events}
            node={node}
            projectId={projectId}
            snapshot={snapshot}
            onInteractionDraft={onInteractionDraft}
            onInteraction={onInteraction}
            onRerun={onRerun}
          />
        ) : null}
      </div>
    </article>
  );
}

function NodeExecutionDetails({
  node,
  events,
  projectId,
  snapshot,
  onInteractionDraft,
  onInteraction,
  onRerun,
  showRerun = false,
}: {
  node: TaskNodeExecution;
  events: TaskEvent[];
  projectId: string;
  snapshot?: WorkflowSnapshot | null;
  onInteractionDraft: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
  onInteraction: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
  onRerun: (nodeId: string) => Promise<void>;
  showRerun?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [actionError, setActionError] = useState("");
  const nodeSpec = snapshot?.nodes?.find((item) => item.id === node.node_id);
  const displayTitle = nodeDisplayTitle(node, snapshot);
  const canRerun = nodeCanRerun(node, snapshot);
  const inputConfig = resolveNodeControlConfig(node, nodeSpec, snapshot, "input");
  const outputConfig = node.error
    ? { control_id: "ui.display.value.v1", variant: "default", mode: "readonly" }
    : resolveNodeControlConfig(node, nodeSpec, snapshot, "output");
  const interactionConfig = resolveNodeInteractionConfig(node, nodeSpec, snapshot);
  const hidesGenericSections = interactionConfig?.control_id === "ui.interaction.asset_summary_table.v1"
    || interactionConfig?.control_id === "ui.interaction.asset_image_cards.v1";
  const InteractionControl = interactionConfig ? getNodeUiControl(interactionConfig.control_id) : null;
  const waitingForInteraction = isWaitingNode(node, snapshot);
  const renderedInteractionConfig = interactionConfig && !waitingForInteraction
    ? { ...interactionConfig, mode: "readonly" }
    : interactionConfig;
  const inputCanSubmit = waitingForInteraction && inputConfig?.mode === "input";
  const inputDefaultOpen = nodeSectionDefaultOpen(snapshot, nodeSpec, "input", false);
  const outputDefaultOpen = node.error ? true : nodeSectionDefaultOpen(snapshot, nodeSpec, "output", true);
  const eventsDefaultOpen = nodeSectionDefaultOpen(snapshot, nodeSpec, "events", false);
  const inputVisible = !hidesGenericSections && nodeSectionVisible(nodeSpec, "input", true);
  const outputVisible = node.error || (!hidesGenericSections && nodeSectionVisible(nodeSpec, "output", true));
  const eventsVisible = !hidesGenericSections && nodeSectionVisible(nodeSpec, "events", true);
  const inputWrapped = nodeSectionWrapped(nodeSpec, "input", true);
  const InputControl = inputConfig ? getNodeUiControl(inputConfig.control_id) : null;

  async function withBusy(action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError("");
    try {
      await action();
    } catch (nextError) {
      setActionError(nodeActionError(nextError));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="node-detail-body">
      {showRerun && canRerun ? (
        <div className="node-detail-actions">
          <button className="secondary-button" disabled={busy} type="button" onClick={() => withBusy(() => onRerun(node.node_id))}>
            重新运行
          </button>
        </div>
      ) : null}

      {inputVisible || outputVisible ? (
        <div className="node-data-stack">
          {inputVisible && !inputWrapped && inputConfig && InputControl ? (
            <InputControl
              busy={busy}
              config={inputConfig.options?.submit_placement === "stage_header"
                ? { ...inputConfig, options: { ...inputConfig.options, form_id: nodeInputFormId(node) } }
                : inputConfig}
              imageAltPrefix={`${displayTitle} 输入图片`}
              node={node}
              nodeSpec={nodeSpec}
              projectId={projectId}
              slot="input"
              snapshot={snapshot}
              value={node.input_snapshot}
              onSubmit={inputCanSubmit ? (input) => withBusy(() => onInteraction(node.node_id, input)) : undefined}
            />
          ) : null}
          {inputVisible && inputWrapped ? (
            <NodeDataSection
              busy={busy}
              config={inputConfig}
              defaultOpen={inputDefaultOpen}
              imageAltPrefix={`${displayTitle} 输入图片`}
              node={node}
              nodeSpec={nodeSpec}
              projectId={projectId}
              slot="input"
              snapshot={snapshot}
              title="输入"
              value={node.input_snapshot}
              onSubmit={inputCanSubmit ? (input) => withBusy(() => onInteraction(node.node_id, input)) : undefined}
            />
          ) : null}
          {outputVisible ? (
            <NodeDataSection
              config={outputConfig}
              defaultOpen={outputDefaultOpen}
              imageAltPrefix={`${displayTitle} 输出图片`}
              node={node}
              nodeSpec={nodeSpec}
              projectId={projectId}
              slot="output"
              snapshot={snapshot}
              title={node.error ? "错误" : "输出"}
              value={node.error ?? node.output_snapshot}
            />
          ) : null}
        </div>
      ) : null}

      {interactionConfig && InteractionControl && (waitingForInteraction || hidesGenericSections) ? (
        <InteractionControl
          busy={busy}
          config={renderedInteractionConfig ?? interactionConfig}
          node={node}
          nodeSpec={nodeSpec}
          projectId={projectId}
          snapshot={snapshot}
          onDraft={waitingForInteraction ? (input) => onInteractionDraft(node.node_id, input) : undefined}
          onSubmit={waitingForInteraction ? (output) => withBusy(() => onInteraction(node.node_id, output)) : undefined}
        />
      ) : null}

      {actionError ? <p className="form-error">{actionError}</p> : null}

      {waitingForInteraction && !interactionConfig && !inputCanSubmit ? (
        <WaitingInteraction busy={busy} node={node} nodeSpec={nodeSpec} onSubmit={(output) => withBusy(() => onInteraction(node.node_id, output))} />
      ) : null}

      {eventsVisible ? (
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
      ) : null}
    </div>
  );
}

function NodeDataSection({
  title,
  value,
  node,
  nodeSpec,
  projectId,
  snapshot,
  config,
  slot,
  imageAltPrefix,
  defaultOpen,
  busy,
  onSubmit,
}: {
  title: string;
  value: unknown;
  node: TaskNodeExecution;
  nodeSpec?: WorkflowNodeSpec;
  projectId?: string;
  snapshot?: WorkflowSnapshot | null;
  config: ReturnType<typeof resolveNodeControlConfig>;
  slot: "input" | "output";
  imageAltPrefix: string;
  defaultOpen: boolean;
  busy?: boolean;
  onSubmit?: (input: Record<string, unknown>) => void;
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
        projectId={projectId}
        slot={slot}
        snapshot={snapshot}
        title={title}
        value={value}
        busy={busy}
        onSubmit={onSubmit}
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
          <textarea aria-label={formatFieldLabel(answerKey)} readOnly={busy} value={text} onChange={(event) => setText(event.target.value)} />
        </label>
        <button className="primary-button" disabled={busy || !text.trim()} type="button" onClick={() => onSubmit({ [answerKey]: text.trim() })}>
          {busy ? "提交中" : "提交并继续"}
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
          <textarea aria-label="图片地址" readOnly={busy} value={text} onChange={(event) => setText(event.target.value)} placeholder="每行一个公开图片地址" />
        </label>
        <button className="primary-button" disabled={busy || splitLines(text).length === 0} type="button" onClick={() => onSubmit({ [answerKey]: splitLines(text) })}>
          {busy ? "提交中" : "提交图片并继续"}
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
        <textarea aria-label="确认意见" readOnly={busy} value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <div className="button-row">
        <button className="primary-button" disabled={busy} type="button" onClick={() => onSubmit({ decision: "approved", approved: true, comment: text })}>
          {busy ? "提交中" : "同意并继续"}
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

  const selectedProject = projects.find((project) => project.project_id === selectedProjectId) ?? projects[0] ?? null;

  return (
    <main className="project-entry-page">
      <section className="project-entry-head">
        <div>
          <p className="eyebrow">项目入口</p>
          <h1>项目</h1>
          <p>选择一个项目进入对应工作台，任务、资产和工作流运行记录都会归属在项目下。</p>
        </div>
        <button className="secondary-button" type="button" onClick={onReload}>
          刷新项目
        </button>
      </section>

      <section className="project-entry-layout">
        <aside className="project-entry-create">
          <section className="project-create-panel">
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
        </aside>

        <div className="project-directory">
          <div className="project-directory-head">
            <div>
              <p className="eyebrow">项目列表</p>
              <h2>选择工作空间</h2>
            </div>
            <span>{projects.length} 个项目</span>
          </div>
          {loading ? <p className="muted">正在加载项目...</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
          <div className="project-card-grid">
            {projects.map((project) => (
              <button
                className={project.project_id === selectedProjectId ? "project-card active" : "project-card"}
                key={project.project_id}
                type="button"
                aria-label={`进入 ${project.name} 工作台`}
                onClick={() => onSelectProject(project.project_id)}
              >
                <span className="project-card-kicker">{project.project_id === "global" ? "共享项目" : "用户项目"}</span>
                <strong>{project.name}</strong>
                <span>{project.description || "项目工作空间"}</span>
                <small>创建于 {formatDate(project.created_at)}</small>
                <span className="project-card-action">进入工作台</span>
              </button>
            ))}
          </div>
        </div>

        <aside className="project-entry-side">
          <section className="project-focus-panel">
            <p className="eyebrow">当前焦点</p>
            <h2>{selectedProject?.name ?? "未选择项目"}</h2>
            <dl className="project-summary-list">
              <div>
                <dt>类型</dt>
                <dd>{selectedProject?.project_id === "global" ? "共享项目" : "用户项目"}</dd>
              </div>
              <div>
                <dt>说明</dt>
                <dd>{selectedProject?.description || "项目工作空间"}</dd>
              </div>
              <div>
                <dt>创建时间</dt>
                <dd>{formatDate(selectedProject?.created_at)}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </section>
    </main>
  );
}

type DirectoryAction = "create" | "rename" | "delete" | null;
type TagAction = "create" | "delete" | null;
type AssetLibraryScope = "combined" | "project" | "global";

interface AssetCollectionTreeNode {
  collection: AssetCollection;
  children: AssetCollectionTreeNode[];
}

function buildAssetCollectionTree(collections: AssetCollection[]): AssetCollectionTreeNode[] {
  const byParent = new Map<string, AssetCollection[]>();
  for (const collection of collections) {
    const parentId = collection.parent_id ?? "";
    byParent.set(parentId, [...(byParent.get(parentId) ?? []), collection]);
  }

  function build(parentId: string): AssetCollectionTreeNode[] {
    return (byParent.get(parentId) ?? []).map((collection) => ({
      collection,
      children: build(collection.collection_id),
    }));
  }

  return build("");
}

function AssetCollectionTreeItems({
  nodes,
  selectedCollectionId,
  onSelect,
}: {
  nodes: AssetCollectionTreeNode[];
  selectedCollectionId: string;
  onSelect: (collectionId: string) => void;
}) {
  return (
    <>
      {nodes.map((node) => (
        <div className="asset-directory-node" key={node.collection.collection_id}>
          <button
            aria-selected={selectedCollectionId === node.collection.collection_id}
            className={selectedCollectionId === node.collection.collection_id ? "directory-tree-item active" : "directory-tree-item"}
            role="treeitem"
            type="button"
            onClick={() => onSelect(node.collection.collection_id)}
          >
            <span>{node.collection.name}</span>
            {node.collection.asset_count === undefined ? null : <small>{node.collection.asset_count}</small>}
          </button>
          {node.children.length ? (
            <div className="asset-directory-children" role="group">
              <AssetCollectionTreeItems nodes={node.children} selectedCollectionId={selectedCollectionId} onSelect={onSelect} />
            </div>
          ) : null}
        </div>
      ))}
    </>
  );
}

function AssetLibraryPage({ project, onProjectRequired }: { project: ProjectRecord | null; onProjectRequired: () => void }) {
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [keyword, setKeyword] = useState("");
  const [scope, setScope] = useState<AssetLibraryScope>("combined");
  const [collections, setCollections] = useState<AssetCollection[]>([]);
  const [tags, setTags] = useState<AssetTag[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState("");
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [directoryAction, setDirectoryAction] = useState<DirectoryAction>(null);
  const [directoryName, setDirectoryName] = useState("");
  const [directorySaving, setDirectorySaving] = useState(false);
  const [assetRenameOpen, setAssetRenameOpen] = useState(false);
  const [assetRenameName, setAssetRenameName] = useState("");
  const [assetNameSaving, setAssetNameSaving] = useState(false);
  const [tagAction, setTagAction] = useState<TagAction>(null);
  const [tagName, setTagName] = useState("");
  const [tagSaving, setTagSaving] = useState(false);
  const [currentAssetTags, setCurrentAssetTags] = useState<AssetTag[]>([]);
  const [assetTagDialogOpen, setAssetTagDialogOpen] = useState(false);
  const [assetTagFilter, setAssetTagFilter] = useState("");
  const [assetTagSavingId, setAssetTagSavingId] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (scope !== "global" && !project) return;
    let active = true;
    const projectId = scope === "global" ? undefined : project?.project_id;
    setLoading(true);
    setMessage("");
    searchAssets({
      scope,
      project_id: projectId,
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
    if (scope !== "global" && !project) return;
    let active = true;
    const projectId = scope === "global" ? undefined : project?.project_id;
    Promise.all([
      listAssetCollections(scope, projectId),
      listAssetTags(scope, projectId),
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

  useEffect(() => {
    setDirectoryAction(null);
    setDirectoryName("");
    setTagAction(null);
    setTagName("");
  }, [project?.project_id, scope]);

  const selectedAsset = assets.find((asset) => asset.asset_id === selectedAssetId) ?? null;
  const selectedCollection = collections.find((collection) => collection.collection_id === selectedCollectionId) ?? null;
  const selectedEditableTag = selectedTagIds.length === 1 ? tags.find((tag) => tag.tag_id === selectedTagIds[0]) ?? null : null;
  const selectedEditableTagIsEmpty = selectedEditableTag ? (selectedEditableTag.asset_count ?? 0) === 0 : false;
  const collectionTree = useMemo(() => buildAssetCollectionTree(collections), [collections]);
  const collectionWriteScope = scope === "global" ? "global" : "project";
  const collectionProjectId = collectionWriteScope === "project" ? project?.project_id : undefined;
  const tagWriteScope = scope === "global" ? "global" : "project";
  const tagProjectId = tagWriteScope === "project" ? project?.project_id : undefined;
  const projectDisplayName = project?.name?.trim() || "项目";
  const combinedScopeLabel = `${projectDisplayName} + 全局`;
  const projectScopeLabel = `${projectDisplayName}资产`;
  const filteredAssetTagOptions = useMemo(() => {
    const keyword = assetTagFilter.trim().toLowerCase();
    const compatibleTags = selectedAsset ? tags.filter((tag) => tagMatchesAssetScope(tag, selectedAsset)) : [];
    if (!keyword) return compatibleTags;
    return compatibleTags.filter((tag) => tag.name.toLowerCase().includes(keyword));
  }, [assetTagFilter, selectedAsset, tags]);

  useEffect(() => {
    setAssetRenameOpen(false);
    setAssetRenameName("");
  }, [selectedAsset?.asset_id]);

  useEffect(() => {
    if (!selectedAsset) {
      setCurrentAssetTags([]);
      setAssetTagDialogOpen(false);
      setAssetTagFilter("");
      return;
    }
    let active = true;
    listAssetTagsForAsset(selectedAsset.asset_id)
      .then((items) => {
        if (active) setCurrentAssetTags(items);
      })
      .catch((error) => {
        if (active) setMessage(readableError(error, "资产标签暂时不可用。"));
      });
    return () => {
      active = false;
    };
  }, [reloadKey, selectedAsset]);

  async function handleUpload() {
    const cleanName = uploadName.trim();
    if (!file || !cleanName) return;
    if (scope !== "global" && !project) {
      onProjectRequired();
      return;
    }
    await uploadAsset({
      file,
      scope: scope === "global" ? "global" : "project",
      project_id: scope === "global" ? undefined : project?.project_id,
      name: cleanName,
      collection_ids: selectedCollectionId ? [selectedCollectionId] : undefined,
      publish: true,
    });
    setFile(null);
    setUploadName("");
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

  function handleStartAssetRename(asset: AssetRecord) {
    setAssetRenameName(asset.name);
    setAssetRenameOpen(true);
  }

  async function handleSaveAssetName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanName = assetRenameName.trim();
    if (!selectedAsset || !cleanName) return;
    setAssetNameSaving(true);
    setMessage("");
    try {
      const renamed = await updateAsset({
        asset_id: selectedAsset.asset_id,
        name: cleanName,
      });
      setAssets((current) => current.map((asset) => asset.asset_id === renamed.asset_id ? renamed : asset));
      setAssetRenameOpen(false);
      setAssetRenameName("");
      setMessage(`已重命名资产：${renamed.name}`);
      setReloadKey((current) => current + 1);
    } catch (error) {
      setMessage(readableError(error, "资产重命名失败，请稍后重试。"));
    } finally {
      setAssetNameSaving(false);
    }
  }

  function handleSelectCollection(collectionId: string) {
    setSelectedCollectionId(collectionId);
    setDirectoryAction(null);
    setDirectoryName("");
  }

  function handleStartDirectoryAction(action: Exclude<DirectoryAction, null>) {
    if (action !== "create" && !selectedCollection) return;
    setDirectoryAction(action);
    setDirectoryName(action === "rename" ? selectedCollection?.name ?? "" : "");
  }

  async function handleSaveDirectory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanName = directoryName.trim();
    if (!cleanName) return;
    if (collectionWriteScope === "project" && !collectionProjectId) {
      onProjectRequired();
      return;
    }
    setDirectorySaving(true);
    setMessage("");
    try {
      if (directoryAction === "create") {
        const collection = await createAssetCollection({
          scope: collectionWriteScope,
          project_id: collectionProjectId,
          parent_id: selectedCollectionId || null,
          name: cleanName,
        });
        setSelectedCollectionId(collection.collection_id);
        setMessage(`已创建目录：${collection.name}`);
      }
      if (directoryAction === "rename" && selectedCollection) {
        const collection = await updateAssetCollection({
          collection_id: selectedCollection.collection_id,
          name: cleanName,
        });
        setMessage(`已重命名目录：${collection.name}`);
      }
      setDirectoryAction(null);
      setDirectoryName("");
      setReloadKey((current) => current + 1);
    } catch (error) {
      setMessage(readableError(error, "目录保存失败，请稍后重试。"));
    } finally {
      setDirectorySaving(false);
    }
  }

  async function handleConfirmDeleteCollection() {
    if (!selectedCollection) return;
    setDirectorySaving(true);
    setMessage("");
    try {
      await deleteAssetCollection(selectedCollection.collection_id);
      setMessage(`已删除目录：${selectedCollection.name}`);
      setSelectedCollectionId("");
      setDirectoryAction(null);
      setReloadKey((current) => current + 1);
    } catch (error) {
      setMessage(readableError(error, "目录删除失败，请稍后重试。"));
    } finally {
      setDirectorySaving(false);
    }
  }

  function handleToggleTag(tagId: string, checked: boolean) {
    setSelectedTagIds((current) => checked ? [...current, tagId] : current.filter((item) => item !== tagId));
    setTagAction(null);
    setTagName("");
  }

  function handleStartTagAction(action: Exclude<TagAction, null>) {
    if (action === "delete" && !selectedEditableTagIsEmpty) return;
    setTagAction(action);
    setTagName("");
  }

  async function handleSaveTag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanName = tagName.trim();
    if (!cleanName) return;
    if (tagWriteScope === "project" && !tagProjectId) {
      onProjectRequired();
      return;
    }
    setTagSaving(true);
    setMessage("");
    try {
      if (tagAction === "create") {
        const tag = await createAssetTag({
          scope: tagWriteScope,
          project_id: tagProjectId,
          name: cleanName,
        });
        setSelectedTagIds([tag.tag_id]);
        setMessage(`已创建标签：${tag.name}`);
      }
      setTagAction(null);
      setTagName("");
      setReloadKey((current) => current + 1);
    } catch (error) {
      setMessage(readableError(error, "标签保存失败，请稍后重试。"));
    } finally {
      setTagSaving(false);
    }
  }

  async function handleConfirmDeleteTag() {
    if (!selectedEditableTag || !selectedEditableTagIsEmpty) return;
    setTagSaving(true);
    setMessage("");
    try {
      await deleteAssetTag(selectedEditableTag.tag_id);
      setMessage(`已删除标签：${selectedEditableTag.name}`);
      setSelectedTagIds((current) => current.filter((tagId) => tagId !== selectedEditableTag.tag_id));
      setTagAction(null);
      setReloadKey((current) => current + 1);
    } catch (error) {
      setMessage(readableError(error, "标签删除失败，请稍后重试。"));
    } finally {
      setTagSaving(false);
    }
  }

  async function handleToggleAssetTag(tag: AssetTag, checked: boolean) {
    if (!selectedAsset || assetTagSavingId) return;
    if (!tagMatchesAssetScope(tag, selectedAsset)) {
      setMessage("当前标签与资产范围不一致，不能贴到该资产。");
      return;
    }
    setAssetTagSavingId(tag.tag_id);
    setMessage("");
    try {
      const nextTags = checked
        ? await attachAssetTag(selectedAsset.asset_id, tag.tag_id)
        : await detachAssetTag(selectedAsset.asset_id, tag.tag_id);
      setCurrentAssetTags(nextTags);
      setReloadKey((current) => current + 1);
    } catch (error) {
      setMessage(readableError(error, "资产标签更新失败，请稍后重试。"));
    } finally {
      setAssetTagSavingId("");
    }
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
          <button className={assetScopeButtonClass(scope === "combined")} disabled={!project} type="button" onClick={() => setScope("combined")}>
            {combinedScopeLabel}
          </button>
          <button className={assetScopeButtonClass(scope === "project")} disabled={!project} type="button" onClick={() => setScope("project")}>
            {projectScopeLabel}
          </button>
          <button className={assetScopeButtonClass(scope === "global")} type="button" onClick={() => setScope("global")}>
            全局资产
          </button>
          <input aria-label="搜索资产" placeholder="搜索资产" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
        </div>
        <div className="asset-tag-management">
          <div className="asset-tag-management-head">
            <div>
              <p className="eyebrow">标签</p>
              <h2>资产标签</h2>
            </div>
            <div className="asset-tag-toolbar" role="toolbar" aria-label="资产库标签操作">
              <button className="secondary-button" type="button" onClick={() => handleStartTagAction("create")}>
                新建标签
              </button>
              <button
                className="secondary-button danger"
                disabled={!selectedEditableTag || !selectedEditableTagIsEmpty}
                title={selectedEditableTag && !selectedEditableTagIsEmpty ? "标签仍被资产使用" : undefined}
                type="button"
                onClick={() => handleStartTagAction("delete")}
              >
                删除标签
              </button>
            </div>
          </div>
          <div className="tag-filter-group" aria-label="资产标签筛选">
            {tags.length ? tags.map((tag) => {
              const checked = selectedTagIds.includes(tag.tag_id);
              return (
                <label className={checked ? "tag-filter active" : "tag-filter"} key={tag.tag_id}>
                  <input
                    aria-label={`筛选标签 ${tag.name}`}
                    checked={checked}
                    type="checkbox"
                    onChange={(event) => handleToggleTag(tag.tag_id, event.target.checked)}
                  />
                  <span>{tag.name}{tag.asset_count === undefined ? "" : ` ${tag.asset_count}`}</span>
                </label>
              );
            }) : <span className="muted">暂无标签</span>}
          </div>
          {tagAction === "create" ? (
            <form className="tag-edit-form" onSubmit={handleSaveTag}>
              <label className="compact-field">
                <span>标签名称</span>
                <input aria-label="标签名称" value={tagName} onChange={(event) => setTagName(event.target.value)} />
              </label>
              <div className="button-row">
                <button className="secondary-button" type="button" onClick={() => setTagAction(null)} disabled={tagSaving}>
                  取消
                </button>
                <button className="primary-button" type="submit" disabled={tagSaving || !tagName.trim()}>
                  创建标签
                </button>
              </div>
            </form>
          ) : null}
          {tagAction === "delete" && selectedEditableTag ? (
            <div className="tag-edit-form">
              <p>确认删除“{selectedEditableTag.name}”？</p>
              <div className="button-row">
                <button className="secondary-button" type="button" onClick={() => setTagAction(null)} disabled={tagSaving}>
                  取消
                </button>
                <button className="primary-button danger" type="button" onClick={() => void handleConfirmDeleteTag()} disabled={tagSaving}>
                  确认删除标签
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </section>
      {message ? <p className="toast-message">{message}</p> : null}
      <div className="asset-layout">
        <aside className="panel asset-directory-panel">
          <div className="section-title-row">
            <div>
              <p className="eyebrow">目录</p>
              <h2>资产目录</h2>
            </div>
          </div>
          <div className="asset-directory-actions">
            <button className="secondary-button" type="button" onClick={() => handleStartDirectoryAction("create")}>
              {selectedCollection ? "新建子目录" : "新建目录"}
            </button>
            <button className="secondary-button" disabled={!selectedCollection} type="button" onClick={() => handleStartDirectoryAction("rename")}>
              重命名目录
            </button>
            <button className="secondary-button danger" disabled={!selectedCollection} type="button" onClick={() => handleStartDirectoryAction("delete")}>
              删除目录
            </button>
          </div>
          <div className="asset-directory-tree" role="tree" aria-label="资产目录">
            <button
              aria-selected={!selectedCollectionId}
              className={!selectedCollectionId ? "directory-tree-item active" : "directory-tree-item"}
              role="treeitem"
              type="button"
              onClick={() => handleSelectCollection("")}
            >
              <span>全部目录</span>
            </button>
            {collectionTree.length ? (
              <AssetCollectionTreeItems nodes={collectionTree} selectedCollectionId={selectedCollectionId} onSelect={handleSelectCollection} />
            ) : (
              <p className="muted">暂无目录</p>
            )}
          </div>
          {directoryAction === "create" || directoryAction === "rename" ? (
            <form className="directory-edit-form" onSubmit={handleSaveDirectory}>
              <label className="compact-field">
                <span>目录名称</span>
                <input aria-label="目录名称" value={directoryName} onChange={(event) => setDirectoryName(event.target.value)} />
              </label>
              <div className="button-row">
                <button className="secondary-button" type="button" onClick={() => setDirectoryAction(null)} disabled={directorySaving}>
                  取消
                </button>
                <button className="primary-button" type="submit" disabled={directorySaving || !directoryName.trim()}>
                  {directoryAction === "create" ? "创建目录" : "保存目录"}
                </button>
              </div>
            </form>
          ) : null}
          {directoryAction === "delete" && selectedCollection ? (
            <div className="directory-edit-form">
              <p>确认删除“{selectedCollection.name}”及其子目录？目录内资产会保留在资产库中。</p>
              <div className="button-row">
                <button className="secondary-button" type="button" onClick={() => setDirectoryAction(null)} disabled={directorySaving}>
                  取消
                </button>
                <button className="primary-button danger" type="button" onClick={() => void handleConfirmDeleteCollection()} disabled={directorySaving}>
                  确认删除目录
                </button>
              </div>
            </div>
          ) : null}
        </aside>
        <section className="panel asset-list-panel">
          <div className="asset-list-header">
            <div className="asset-list-title-row">
              <h2>资产列表</h2>
            </div>
          </div>
          {loading ? <p className="muted">正在加载资产...</p> : null}
          {!loading && !assets.length ? <p className="empty-box">暂无资产，可以上传文件。</p> : null}
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
              <div className="asset-detail-actions" role="group" aria-label="资产操作">
                {selectedAsset.metadata.public_url ? (
                  <>
                    <a className="secondary-button asset-action-button" href={selectedAsset.metadata.public_url} target="_blank" rel="noreferrer">
                      预览资产
                    </a>
                    <button className="secondary-button asset-action-button" type="button" onClick={() => void handleCopyAssetUrl(selectedAsset)}>
                      复制引用
                    </button>
                  </>
                ) : null}
                <button className="primary-button asset-action-button" type="button" onClick={() => void handleDownload(selectedAsset)}>
                  下载
                </button>
                <button className="secondary-button asset-action-button" type="button" onClick={() => handleStartAssetRename(selectedAsset)}>
                  重命名资产
                </button>
                <button className="secondary-button danger asset-action-button" type="button" onClick={() => void handleDelete(selectedAsset)}>
                  软删除
                </button>
              </div>
              {assetRenameOpen ? (
                <form className="asset-inline-form" onSubmit={(event) => void handleSaveAssetName(event)}>
                  <label className="compact-field">
                    <span>资产名称</span>
                    <input
                      aria-label="资产名称"
                      value={assetRenameName}
                      onChange={(event) => setAssetRenameName(event.target.value)}
                    />
                  </label>
                  <div className="asset-inline-actions">
                    <button className="primary-button" disabled={!assetRenameName.trim() || assetNameSaving} type="submit">
                      保存资产名称
                    </button>
                    <button className="secondary-button" disabled={assetNameSaving} type="button" onClick={() => setAssetRenameOpen(false)}>
                      取消
                    </button>
                  </div>
                </form>
              ) : null}
              <div className="asset-current-tags">
                <div className="section-title-row">
                  <h4>资产标签</h4>
                  <button className="secondary-button" type="button" onClick={() => {
                    setAssetTagFilter("");
                    setAssetTagDialogOpen(true);
                  }}>
                    管理资产标签
                  </button>
                </div>
                <div className="asset-tag-chip-row" role="group" aria-label="当前资产标签">
                  {currentAssetTags.length ? currentAssetTags.map((tag) => (
                    <span className="tag-chip" key={tag.tag_id}>{tag.name}</span>
                  )) : <span className="muted">暂无标签</span>}
                </div>
              </div>
              {assetTagDialogOpen ? (
                <div className="asset-picker-modal">
                  <button className="modal-scrim" type="button" aria-label="关闭资产标签弹窗" onClick={() => setAssetTagDialogOpen(false)} />
                  <section className="asset-tag-dialog" role="dialog" aria-modal="true" aria-label="管理资产标签">
                    <div className="asset-picker-header">
                      <div>
                        <p className="eyebrow">标签</p>
                        <h2>管理资产标签</h2>
                      </div>
                      <button className="secondary-button" type="button" onClick={() => setAssetTagDialogOpen(false)}>
                        关闭
                      </button>
                    </div>
                    <label className="compact-field">
                      <span>过滤标签</span>
                      <input aria-label="过滤标签" value={assetTagFilter} onChange={(event) => setAssetTagFilter(event.target.value)} />
                    </label>
                    <div className="asset-tag-option-list">
                      {filteredAssetTagOptions.length ? filteredAssetTagOptions.map((tag) => {
                        const checked = currentAssetTags.some((item) => item.tag_id === tag.tag_id);
                        return (
                          <label className={checked ? "asset-tag-option active" : "asset-tag-option"} key={tag.tag_id}>
                            <input
                              aria-label={`${checked ? "取消资产标签" : "给资产贴标签"} ${tag.name}`}
                              checked={checked}
                              disabled={assetTagSavingId === tag.tag_id}
                              type="checkbox"
                              onChange={(event) => void handleToggleAssetTag(tag, event.target.checked)}
                            />
                            <span>{tag.name}</span>
                            {tag.asset_count === undefined ? null : <small>{tag.asset_count}</small>}
                          </label>
                        );
                      }) : <p className="muted">暂无匹配标签</p>}
                    </div>
                  </section>
                </div>
              ) : null}
            </>
          ) : (
            <p className="muted">选择资产查看详情。</p>
          )}
          <div className="asset-create-stack">
            <label className="compact-field">
              <span>上传文件</span>
              <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            </label>
            <label className="compact-field">
              <span>上传资产名称</span>
              <input
                aria-label="上传资产名称"
                placeholder="填写资产名，不必等同文件名"
                value={uploadName}
                onChange={(event) => setUploadName(event.target.value)}
              />
            </label>
            <button className="secondary-button" disabled={!file || !uploadName.trim()} type="button" onClick={() => void handleUpload()}>
              上传到资产库
            </button>
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
    inputSchema: firstUserInputSchema(item.nodes),
    contract: { workflow: item.workflow, nodes: item.nodes, edges: item.edges ?? [] },
    nodes: item.nodes.map((node) => node.id),
  };
}

function firstUserInputSchema(nodes: WorkflowNodeSpec[]): JsonSchema {
  for (const node of nodes) {
    const inputSpecs = recordValue(node.inputs);
    if (!inputSpecs) continue;
    const properties: Record<string, JsonSchema> = {};
    const required: string[] = [];
    for (const [name, specValue] of Object.entries(inputSpecs)) {
      const spec = recordValue(specValue);
      if (spec?.from_user !== true) continue;
      properties[name] = isJsonSchema(spec.schema) ? spec.schema : {};
      if (spec.required !== false) required.push(name);
    }
    if (Object.keys(properties).length) {
      return { type: "object", required, properties, additionalProperties: false };
    }
  }
  return { type: "object", properties: {}, additionalProperties: false };
}

function isJsonSchema(value: unknown): value is JsonSchema {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return record.type === undefined || typeof record.type === "string";
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function orderNodes(detail: TaskDetailResponse | null): TaskNodeExecution[] {
  if (!detail) return [];
  const byId = new Map(detail.node_executions.map((node) => [node.node_id, node]));
  const ordered = detail.workflow_snapshot?.nodes?.map((node) => byId.get(node.id) ?? virtualNodeExecution(node, detail)).filter(Boolean) as TaskNodeExecution[] | undefined;
  if (!ordered?.length) return detail.node_executions;
  const extras = detail.node_executions.filter((node) => !ordered.some((orderedNode) => orderedNode.node_id === node.node_id));
  return [...ordered, ...extras];
}

function normalizeLiveTaskEvent(event: TaskEvent): TaskEvent {
  return {
    ...event,
    event_id: event.event_id ?? `live-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    created_at: event.created_at ?? event.timestamp ?? new Date().toISOString(),
  };
}

function mergeTaskEvents(...groups: TaskEvent[][]): TaskEvent[] {
  const merged: TaskEvent[] = [];
  const seen = new Set<string>();
  for (const group of groups) {
    for (const event of group) {
      const key = taskEventKey(event, merged.length);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(event);
    }
  }
  return merged;
}

function taskEventKey(event: TaskEvent, fallbackIndex: number): string {
  if (event.event_id) return `id:${event.event_id}`;
  const nodeId = nodeIdFromTaskEvent(event);
  const createdAt = event.created_at ?? event.timestamp ?? "";
  const message = event.message ?? "";
  return `${event.event_type ?? event.type ?? "message"}:${nodeId}:${createdAt}:${message}:${fallbackIndex}`;
}

function nodeIdFromTaskEvent(event: TaskEvent): string {
  return event.node_id || (typeof event.payload?.node_id === "string" ? event.payload.node_id : "");
}

function taskEventIdentity(event: TaskEvent): string {
  return taskEventKey(event, 0);
}

function taskEventRevealsNode(event: TaskEvent): boolean {
  const type = (event.event_type ?? event.type ?? "").toLowerCase();
  return [
    "node_rerun_started",
    "node_started",
    "node_running",
    "node_waiting",
    "node_succeeded",
    "node_failed",
  ].includes(type);
}

function workflowDownstreamNodeIds(snapshot: WorkflowSnapshot | null | undefined, nodeId: string): Set<string> {
  const affected = new Set<string>([nodeId]);
  const edges = (snapshot?.edges ?? []).map(edgeRecord);
  const stack = [nodeId];
  while (stack.length) {
    const current = stack.pop() ?? "";
    for (const edge of edges) {
      if (edge.from !== current || !edge.to || edge.to === "__end__") continue;
      if (affected.has(edge.to)) continue;
      affected.add(edge.to);
      stack.push(edge.to);
    }
  }
  return affected;
}

function virtualNodeExecution(node: WorkflowNodeSpec, detail: TaskDetailResponse): TaskNodeExecution {
  return {
    node_id: node.id,
    node_ref: node.ref,
    status: virtualNodeStatus(node.id, detail),
    input_snapshot: null,
    output_snapshot: null,
    metadata: {},
  };
}

function virtualNodeStatus(nodeId: string, detail: TaskDetailResponse): string {
  const inbound = (detail.workflow_snapshot?.edges ?? []).map(edgeRecord).filter((edge) => edge.to === nodeId);
  if (!inbound.length) return "not_started";
  const executions = new Map(detail.node_executions.map((node) => [node.node_id, node]));
  const conditional = inbound.filter((edge) => edge.when);
  if (conditional.length) {
    const resolved = conditional.map((edge) => evaluateEdgeCondition(edge, executions));
    if (resolved.some((value) => value === true)) return "not_started";
    if (resolved.every((value) => value === false)) return "skipped";
    return "branch_pending";
  }
  if (inbound.every((edge) => executions.get(edge.from)?.status === "skipped")) return "skipped";
  return "not_started";
}

function workflowStages(snapshot?: WorkflowSnapshot | null): WorkflowUiStage[] {
  const stages = snapshot?.workflow?.ui?.stages;
  if (!Array.isArray(stages)) return [];
  const normalized: WorkflowUiStage[] = [];
  for (const stage of stages) {
    const record = recordValue(stage);
    if (!record) continue;
    const id = typeof record.id === "string" ? record.id : "";
    const name = typeof record.name === "string" ? record.name : "";
    const nodes = Array.isArray(record.nodes) ? record.nodes.filter((node): node is string => typeof node === "string") : [];
    if (!id || !name) continue;
    normalized.push({
      id,
      name,
      description: typeof record.description === "string" ? record.description : undefined,
      nodes,
    });
  }
  return normalized;
}

interface WorkflowEdgeView {
  from: string;
  to: string;
  when?: { path?: string; equals?: unknown };
}

function edgeRecord(edge: unknown): WorkflowEdgeView {
  const record = recordValue(edge) ?? {};
  const when = recordValue(record.when);
  return {
    from: typeof record.from === "string" ? record.from : "",
    to: typeof record.to === "string" ? record.to : "",
    when: when ? { path: typeof when.path === "string" ? when.path : undefined, equals: when.equals } : undefined,
  };
}

function evaluateEdgeCondition(edge: WorkflowEdgeView, executions: Map<string, TaskNodeExecution>): boolean | "pending" {
  const path = edge.when?.path;
  if (!path) return "pending";
  const value = readWorkflowNodePath(path, executions);
  if (value === undefined) return "pending";
  return value === edge.when?.equals;
}

function readWorkflowNodePath(path: string, executions: Map<string, TaskNodeExecution>): unknown {
  const prefix = "$nodes.";
  if (!path.startsWith(prefix)) return undefined;
  const parts = path.slice(prefix.length).split(".");
  const nodeId = parts.shift();
  const slot = parts.shift();
  if (!nodeId || slot !== "output") return undefined;
  let current: unknown = executions.get(nodeId)?.output_snapshot;
  for (const part of parts) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function stageStatusLabel(nodes: TaskNodeExecution[]): string {
  if (!nodes.length) return "待运行";
  if (nodes.some((node) => statusLabel(node.status) === "失败")) return "失败";
  if (nodes.some((node) => statusLabel(node.status) === "等待用户")) return "等待用户";
  if (nodes.some((node) => statusLabel(node.status) === "运行中")) return "运行中";
  if (nodes.every((node) => statusLabel(node.status) === "成功" || statusLabel(node.status) === "已跳过")) return "成功";
  if (nodes.every((node) => statusLabel(node.status) === "待判定" || statusLabel(node.status) === "已跳过")) return "待判定";
  return "待运行";
}

function stageTone(nodes: TaskNodeExecution[]): "neutral" | "info" | "success" | "warning" | "danger" {
  return statusTone(stageStatusLabel(nodes));
}

function nodeIsInMotion(node: TaskNodeExecution): boolean {
  return statusLabel(node.status) === "运行中";
}

function nodeProgressValue(node: TaskNodeExecution): number {
  const label = statusLabel(node.status);
  if (label === "成功" || label === "已跳过") return 100;
  if (label === "失败") return 100;
  if (label === "等待用户") return 60;
  if (label === "运行中") return 35;
  if (label === "待判定") return 10;
  return 10;
}

function nodeUsesStageHeaderSubmit(node: TaskNodeExecution, snapshot?: WorkflowSnapshot | null): boolean {
  if (!isWaitingNode(node, snapshot)) return false;
  const nodeSpec = snapshot?.nodes?.find((item) => item.id === node.node_id);
  const inputConfig = resolveNodeControlConfig(node, nodeSpec, snapshot, "input");
  return inputConfig?.mode === "input" && inputConfig.options?.submit_placement === "stage_header";
}

function nodeCanRerun(node: TaskNodeExecution, snapshot?: WorkflowSnapshot | null): boolean {
  const nodeSpec = snapshot?.nodes?.find((item) => item.id === node.node_id);
  return statusLabel(node.status) === "成功" && nodeSpec?.ui?.actions?.rerun !== false;
}

function nodeInputFormId(node: TaskNodeExecution): string {
  return `xiagent-node-input-${node.node_execution_id ?? node.node_id}`;
}

function nodeActivityText(node: TaskNodeExecution, eventsByNode: Map<string, TaskEvent[]>, snapshot?: WorkflowSnapshot | null): string {
  const label = statusLabel(node.status);
  if (label === "运行中") return `正在${nodeDisplayTitle(node, snapshot)}`;
  if (label === "等待用户") return "等待用户处理";
  if (label === "成功") return "已完成";
  if (label === "失败") {
    const errorRecord = recordValue(node.error);
    const errorText = typeof node.error === "string"
      ? node.error
      : (typeof errorRecord?.message === "string" ? errorRecord.message : undefined) ?? (typeof errorRecord?.code === "string" ? errorRecord.code : undefined);
    return errorText ? `失败：${errorText}` : "失败";
  }
  const events = eventsByNode.get(node.node_id) ?? [];
  const latestEvent = events.length ? events[events.length - 1] : undefined;
  return latestEvent ? eventText(latestEvent) : statusLabel(node.status);
}

function taskRuntimeContext(detail: TaskDetailResponse, orderedNodes: TaskNodeExecution[]): TaskRuntimeContext {
  const status = detail.task.status;
  const activeNode =
    orderedNodes.find((node) => statusLabel(node.status) === "等待用户") ??
    orderedNodes.find((node) => statusLabel(node.status) === "运行中") ??
    orderedNodes.find((node) => statusLabel(node.status) === "失败") ??
    null;
  if (activeNode) {
    return {
      status,
      currentNodeLabel: nodeDisplayTitle(activeNode, detail.workflow_snapshot),
    };
  }
  if (statusLabel(status) === "成功") {
    return { status, currentNodeLabel: "已完成" };
  }
  if (detail.task.current_node_id) {
    const node = orderedNodes.find((item) => item.node_id === detail.task.current_node_id);
    return {
      status,
      currentNodeLabel: node ? nodeDisplayTitle(node, detail.workflow_snapshot) : formatFieldLabel(detail.task.current_node_id),
    };
  }
  return { status, currentNodeLabel: "未记录" };
}

function nodeShouldDefaultExpand(node: TaskNodeExecution): boolean {
  const label = statusLabel(node.status);
  return label === "等待用户" || label === "失败" || label === "运行中" || Boolean(node.error);
}

function defaultExpandedStageNodeId(nodes: TaskNodeExecution[], snapshot?: WorkflowSnapshot | null): string | null {
  return nodes.find((node) => nodeRequiresUserAction(node, snapshot))?.node_id ?? null;
}

function nodeRequiresUserAction(node: TaskNodeExecution, snapshot?: WorkflowSnapshot | null): boolean {
  return isWaitingNode(node, snapshot);
}

function nodeSectionDefaultOpen(
  snapshot: WorkflowSnapshot | null | undefined,
  nodeSpec: WorkflowNodeSpec | undefined,
  section: "input" | "output" | "events",
  fallback: boolean,
): boolean {
  const nodeSectionDefault = nodeSectionDefaultOpenValue(nodeSpec?.ui?.sections?.[section]);
  if (nodeSectionDefault !== undefined) return nodeSectionDefault;
  const layout = snapshot?.workflow?.ui?.layout;
  if (layout?.default_expanded_sections?.includes(section)) return true;
  if (layout?.default_collapsed_sections?.includes(section)) return false;
  return fallback;
}

function nodeSectionDefaultOpenValue(config: unknown): boolean | undefined {
  if (typeof config === "boolean") return config;
  if (typeof config !== "object" || config === null) return undefined;
  const section = config as Record<string, unknown>;
  if (typeof section.default_open === "boolean") return section.default_open;
  if (typeof section.open === "boolean") return section.open;
  if (typeof section.default_expanded === "boolean") return section.default_expanded;
  if (typeof section.default_collapsed === "boolean") return !section.default_collapsed;
  if (typeof section.collapsed === "boolean") return !section.collapsed;
  return undefined;
}

function nodeSectionVisible(nodeSpec: WorkflowNodeSpec | undefined, section: "input" | "output" | "events", fallback: boolean): boolean {
  const config = recordValue(nodeSpec?.ui?.sections?.[section]);
  if (!config) return fallback;
  if (typeof config.visible === "boolean") return config.visible;
  if (typeof config.hidden === "boolean") return !config.hidden;
  return fallback;
}

function nodeSectionWrapped(nodeSpec: WorkflowNodeSpec | undefined, section: "input" | "output" | "events", fallback: boolean): boolean {
  const config = recordValue(nodeSpec?.ui?.sections?.[section]);
  if (!config) return fallback;
  if (typeof config.wrapper === "boolean") return config.wrapper;
  if (typeof config.wrapped === "boolean") return config.wrapped;
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

function tagMatchesAssetScope(tag: AssetTag, asset: AssetRecord): boolean {
  if (tag.scope !== asset.scope) return false;
  if (asset.scope !== "project") return true;
  return (tag.project_id ?? null) === (asset.project_id ?? null);
}

function assetScopeButtonClass(active: boolean): string {
  return active ? "secondary-button asset-scope-button active-control" : "secondary-button asset-scope-button";
}

function readableError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function nodeActionError(error: unknown): string {
  const message = readableError(error, "节点操作失败，请检查输入后重试。");
  const schemaDetails = error instanceof ApiError ? schemaValidationDetails(error.body) : "";
  return schemaDetails ? `${message}：${schemaDetails}` : message;
}

function schemaValidationDetails(body: unknown): string {
  if (typeof body !== "object" || body === null) return "";
  const details = (body as { error?: { details?: unknown } }).error?.details;
  if (typeof details !== "object" || details === null) return "";
  const record = details as { path?: unknown; error?: unknown };
  const path = Array.isArray(record.path) && record.path.length ? `字段 ${record.path.join(".")}` : "";
  const error = typeof record.error === "string" ? record.error : "";
  return [path, error].filter(Boolean).join("，");
}
