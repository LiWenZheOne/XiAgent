import { type FormEvent, useEffect, useMemo, useState } from "react";

import { AssetLibraryPage } from "../assets/AssetLibraryPage";
import { ensureAccessToken } from "../api/auth";
import { createProject as createProjectRecord, listProjects, type ProjectRecord } from "../api/projects";
import { CreateTaskPage } from "../task/CreateTaskPage";
import { WorkflowRunPage, type ProjectContext } from "../workflows/WorkflowRunPage";

type Route = "projects" | "tasks" | "assets" | "workflows" | "settings";

interface ProjectRow extends ProjectContext {
  owner: string;
  taskStatus: string;
  assets: string;
  workflows: string;
  lastRun: string;
  actionRoute: Route;
}

const navItems: Array<{ route: Route; label: string }> = [
  { route: "projects", label: "项目" },
  { route: "tasks", label: "任务" },
  { route: "assets", label: "资产" },
  { route: "workflows", label: "工作流" },
  { route: "settings", label: "设置" },
];

function routeActionLabel(route: Route) {
  if (route === "assets") return "资产库";
  if (route === "tasks") return "任务";
  if (route === "workflows") return "工作流";
  if (route === "settings") return "设置";
  return "项目";
}

function TopBar({
  currentProjectName,
  route,
  onNavigate,
}: {
  currentProjectName: string;
  route: Route;
  onNavigate: (route: Route) => void;
}) {
  return (
    <header className="topbar">
      <div className="brand-group">
        <div className="brand-mark" aria-hidden="true">
          X
        </div>
        <strong className="brand-name">XiAgent</strong>
        <nav className="topnav" aria-label="主导航">
          {navItems.map((item) => (
            <button
              className={route === item.route ? "nav-button active" : "nav-button"}
              key={item.route}
              type="button"
              onClick={() => onNavigate(item.route)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="topbar-actions">
        <span className="current-project-pill">项目：{currentProjectName}</span>
        <label className="global-search">
          <span className="sr-only">全局搜索</span>
          <input placeholder="搜索项目、任务、资产" type="search" />
        </label>
        <button className="secondary-button" type="button">
          通知
        </button>
        <div className="user-avatar" aria-label="当前用户">
          北
        </div>
      </div>
    </header>
  );
}

function ProjectOverviewPage({
  projects,
  selectedProject,
  onCreateProject,
  onSelectProject,
  onNavigate,
  loading,
  error: projectError,
  onReload,
}: {
  projects: ProjectRow[];
  selectedProject?: ProjectRow;
  onCreateProject: (name: string) => Promise<void>;
  onSelectProject: (projectId: string) => void;
  onNavigate: (route: Route) => void;
  loading: boolean;
  error: string;
  onReload: () => void;
}) {
  const [isCreating, setIsCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [formError, setFormError] = useState("");

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = projectName.trim();
    if (!trimmedName) {
      setFormError("请输入项目名称");
      return;
    }
    setSaving(true);
    try {
      await onCreateProject(trimmedName);
      setProjectName("");
      setFormError("");
      setIsCreating(false);
    } catch {
      setFormError("项目创建接口不可用，请重试");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="page project-page">
      <section className="page-header">
        <div>
          <p className="eyebrow">beixing01 / XiAgent 工作区</p>
          <h1>项目总览</h1>
          <p>先选择真实项目，再进入任务、资产和工作流运行界面。</p>
          <p className="current-project-text">当前项目：{selectedProject?.name ?? "未选择项目"}</p>
          {loading ? <p className="current-project-text">正在读取后端项目...</p> : null}
          {projectError ? <p className="form-error">{projectError}</p> : null}
        </div>
        <div className="header-actions">
          <button className="secondary-button" disabled={!selectedProject} type="button" onClick={() => onNavigate("tasks")}>
            查看运行记录
          </button>
          <button className="secondary-button" disabled={!selectedProject} type="button" onClick={() => onNavigate("workflows")}>
            从工作流创建任务
          </button>
          <button className="secondary-button" type="button" onClick={onReload}>
            刷新项目
          </button>
          <button className="primary-button" type="button" onClick={() => setIsCreating(true)}>
            新建项目
          </button>
        </div>
      </section>

      <section className="metric-grid" aria-label="项目状态概览">
        {[
          ["项目数", String(projects.length), "当前用户可访问"],
          ["当前项目", selectedProject ? "已选择" : "未选择", "任务创建需要项目上下文"],
          ["任务数据", "后端", "进入任务中心读取"],
          ["资产数据", "后端", "进入资产库读取"],
          ["工作流契约", "后端", "进入工作流页读取"],
        ].map(([label, value, note]) => (
          <article className="metric-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{note}</small>
          </article>
        ))}
      </section>

      <div className="dashboard-grid">
        <section className="panel project-list-panel">
          <div className="section-header">
            <div>
              <h2>项目列表</h2>
              <p>选择项目后，任务、资产和工作流运行都会使用同一个项目上下文。</p>
            </div>
            <button className="secondary-button" type="button">
              当前登录用户
            </button>
          </div>
          {projects.length === 0 && !loading ? (
            <div className="empty-panel asset-empty-panel">
              <h2>暂无项目</h2>
              <p>创建项目后，任务、资产和工作流都会挂到该项目上下文。</p>
            </div>
          ) : null}
          {projects.length > 0 ? (
            <table className="data-table" aria-label="项目列表">
              <thead>
                <tr>
                  <th>项目名</th>
                  <th>负责人</th>
                  <th>任务状态</th>
                  <th>资产</th>
                  <th>工作流</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((project) => (
                  <tr className={project.id === selectedProject?.id ? "selected-row" : ""} key={project.id}>
                    <td>{project.name}</td>
                    <td>{project.owner}</td>
                    <td>{project.taskStatus}</td>
                    <td>{project.assets}</td>
                    <td>{project.workflows}</td>
                    <td>{project.lastRun}</td>
                    <td>
                      <div className="project-actions">
                        <button
                          aria-label={`选择 ${project.name}`}
                          className="text-button"
                          type="button"
                          onClick={() => onSelectProject(project.id)}
                        >
                          选择
                        </button>
                        <button
                          aria-label={`打开 ${project.name} ${routeActionLabel(project.actionRoute)}`}
                          className="text-button"
                          type="button"
                          onClick={() => {
                            onSelectProject(project.id);
                            onNavigate(project.actionRoute);
                          }}
                        >
                          打开
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </section>

        <aside className="side-stack">
          <section className="panel">
            <h2>最近活动</h2>
            <ul className="event-list">
              <li>任务运行记录请进入任务中心查看真实数据</li>
              <li>资产变更请进入资产库查看真实数据</li>
              <li>工作流契约请进入工作流页从后端加载</li>
            </ul>
          </section>
          <section className="panel">
            <h2>失败 / 待处理任务</h2>
            <ul className="event-list">
              <li>后端返回任务后将在任务中心展示节点状态</li>
              <li>节点错误详情来自任务详情接口</li>
              <li>人工交互状态由后端任务事件决定</li>
            </ul>
          </section>
          <section className="panel">
            <h2>常用工作流</h2>
            <div className="chip-row">
              <span className="chip">从后端工作流加载</span>
              <span className="chip">项目上下文</span>
              <span className="chip">真实任务记录</span>
            </div>
          </section>
        </aside>
      </div>

      {isCreating ? (
        <div className="dialog-backdrop">
          <form className="upload-dialog project-dialog" onSubmit={handleCreateProject}>
            <div className="dialog-header">
              <div>
                <p className="eyebrow">project_service</p>
                <h2>新建项目</h2>
              </div>
              <button className="icon-button" type="button" onClick={() => setIsCreating(false)}>
                ×
              </button>
            </div>
            <label className="workflow-field">
              <span>项目名称</span>
              <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
            </label>
            {formError ? <p className="form-error">{formError}</p> : null}
            <div className="dialog-actions">
              <button className="secondary-button" type="button" onClick={() => setIsCreating(false)}>
                取消
              </button>
              <button className="primary-button" disabled={saving} type="submit">
                {saving ? "创建中" : "创建项目"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </main>
  );
}

export function App() {
  const [route, setRoute] = useState<Route>("projects");
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [projectLoading, setProjectLoading] = useState(true);
  const [projectError, setProjectError] = useState("");
  const [projectReloadKey, setProjectReloadKey] = useState(0);
  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId),
    [projects, selectedProjectId],
  );

  useEffect(() => {
    let active = true;
    setProjectLoading(true);
    setProjectError("");
    ensureAccessToken()
      .then(() => listProjects())
      .then((records) => {
        if (!active) return;
        const nextProjects = records.map(projectRecordToRow);
        setProjects(nextProjects);
        setSelectedProjectId((current) => {
          if (current && nextProjects.some((project) => project.id === current)) return current;
          return nextProjects[0]?.id ?? "";
        });
      })
      .catch(() => {
        if (active) setProjectError("项目接口不可用，请检查后端服务。");
      })
      .finally(() => {
        if (active) setProjectLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectReloadKey]);

  async function handleCreateProject(name: string) {
    await ensureAccessToken();
    const project = projectRecordToRow(await createProjectRecord(name));
    setProjects((current) => [project, ...current]);
    setSelectedProjectId(project.id);
    setSelectedTaskId("");
  }

  function handleSelectProject(projectId: string) {
    setSelectedProjectId(projectId);
    setSelectedTaskId("");
  }

  function handleNavigateToTask(taskId: string) {
    setSelectedTaskId(taskId);
    setRoute("tasks");
  }

  return (
    <div className="app-shell">
      <TopBar currentProjectName={selectedProject?.name ?? "未选择项目"} route={route} onNavigate={setRoute} />
      {route === "projects" ? (
        <ProjectOverviewPage
          projects={projects}
          selectedProject={selectedProject}
          onCreateProject={handleCreateProject}
          onSelectProject={handleSelectProject}
          onNavigate={setRoute}
          loading={projectLoading}
          error={projectError}
          onReload={() => setProjectReloadKey((current) => current + 1)}
        />
      ) : null}
      {route !== "projects" && !selectedProject ? (
        <main className="page">
          <section className="panel empty-panel">
            <h1>请先选择项目</h1>
            <p>任务、资产和工作流运行都需要明确的项目上下文。</p>
            <button className="primary-button" type="button" onClick={() => setRoute("projects")}>
              返回项目总览
            </button>
          </section>
        </main>
      ) : null}
      {route === "assets" && selectedProject ? (
        <AssetLibraryPage projectId={selectedProject.id} projectName={selectedProject.name} />
      ) : null}
      {route === "tasks" && selectedProject ? (
        <CreateTaskPage
          currentProjectName={selectedProject.name}
          projectId={selectedProject.id}
          selectedTaskId={selectedTaskId}
          onSelectTask={setSelectedTaskId}
          onCreateTaskClick={() => setRoute("workflows")}
        />
      ) : null}
      {route === "workflows" && selectedProject ? (
        <WorkflowRunPage
          currentProject={selectedProject}
          onNavigateToTask={handleNavigateToTask}
        />
      ) : null}
      {route === "settings" ? (
        <main className="page">
          <section className="panel empty-panel">
            <h1>设置</h1>
            <p>项目成员、权限和运行环境配置将在这里管理。</p>
          </section>
        </main>
      ) : null}
    </div>
  );
}

function projectRecordToRow(project: ProjectRecord): ProjectRow {
  return {
    id: project.project_id,
    name: project.name,
    owner: project.owner_user_id,
    taskStatus: "进入任务中心查看",
    assets: "进入资产库查看",
    workflows: "进入工作流页查看",
    lastRun: formatDate(project.created_at),
    actionRoute: "tasks",
  };
}

function formatDate(value?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}
