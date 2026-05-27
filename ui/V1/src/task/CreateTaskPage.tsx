import { useEffect, useMemo, useState } from "react";

import { getTask, listTasks } from "../api/tasks";
import type { TaskDetailResponse, TaskEvent, TaskNodeExecution, TaskRecord, WorkflowSnapshot } from "../api/types";

interface TaskListPageProps {
  currentProjectName?: string;
  projectId: string;
  selectedTaskId?: string;
  onSelectTask?: (taskId: string) => void;
  onCreateTaskClick?: () => void;
}

interface TaskDetailPageProps {
  projectId: string;
  taskId: string;
  onBackToList: () => void;
  onCreateTaskClick?: () => void;
}

interface CreateTaskPageProps {
  currentProjectName?: string;
  projectId: string;
  selectedTaskId?: string;
  onSelectTask?: (taskId: string) => void;
  onCreateTaskClick?: () => void;
}

function statusLabel(status?: string) {
  const normalized = (status ?? "").toLowerCase();
  if (["failed", "failure", "error", "cancelled", "canceled"].some((item) => normalized.includes(item))) {
    return "失败";
  }
  if (["succeeded", "success", "completed", "done"].some((item) => normalized.includes(item))) return "成功";
  if (normalized.includes("superseded")) return "历史";
  if (["queued", "pending", "waiting"].some((item) => normalized.includes(item))) return "等待";
  return "运行中";
}

function statusClass(status?: string) {
  const label = statusLabel(status);
  if (label === "失败") return "status danger";
  if (label === "运行中") return "status info";
  if (label === "等待") return "status warning";
  if (label === "历史") return "status";
  return "status success";
}

function workflowLabel(task: TaskRecord) {
  const name = task.workflow_name ?? task.workflow_id ?? "unknown_workflow";
  return task.workflow_version ? `${name}@${task.workflow_version}` : name;
}

function taskTime(task: TaskRecord) {
  return task.started_at ?? task.created_at ?? "未记录";
}

function stringifySnapshot(value: unknown) {
  if (value === null || value === undefined || value === "") return "{}";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function eventNodeId(event: TaskEvent) {
  const payloadNodeId = event.payload?.node_id;
  if (typeof event.node_id === "string") return event.node_id;
  return typeof payloadNodeId === "string" ? payloadNodeId : "";
}

function eventLabel(event: TaskEvent) {
  const type = event.event_type ?? event.type ?? "event";
  const nodeId = eventNodeId(event);
  const node = nodeId ? ` · ${nodeId}` : "";
  const message = event.message ? ` · ${event.message}` : "";
  return `${type}${node}${message}`;
}

function nodeRef(node: TaskNodeExecution, workflowSnapshot?: WorkflowSnapshot | null) {
  if (node.node_ref) return node.node_ref;
  if (node.ref) return node.ref;
  const snapshotNode = workflowSnapshot?.nodes?.find((item) => item.id === node.node_id);
  return snapshotNode?.ref ?? snapshotNode?.name ?? "runtime";
}

export function TaskNodeBlock({
  node,
  index,
  events,
  workflowSnapshot,
}: {
  node: TaskNodeExecution;
  index: number;
  events: TaskEvent[];
  workflowSnapshot?: WorkflowSnapshot | null;
}) {
  return (
    <article className="panel node-execution-card">
      <div className="node-card-header">
        <div>
          <p className="eyebrow">节点 {index + 1}</p>
          <h2>{node.node_id}</h2>
          <p>{nodeRef(node, workflowSnapshot)}</p>
        </div>
        <span className={statusClass(node.status)}>{statusLabel(node.status)}</span>
      </div>
      <div className="node-snapshot-grid">
        <section>
          <h3>输入快照</h3>
          <pre>{stringifySnapshot(node.input_snapshot)}</pre>
        </section>
        <section>
          <h3>输出快照</h3>
          <pre>{stringifySnapshot(node.output_snapshot ?? node.error)}</pre>
        </section>
      </div>
      <section>
        <h3>节点事件</h3>
        {events.length ? (
          <ul className="event-list">
            {events.map((event, eventIndex) => (
              <li key={event.event_id ?? `${node.node_id}-${eventIndex}`}>{eventLabel(event)}</li>
            ))}
          </ul>
        ) : (
          <p className="empty-state muted">该节点暂无事件。</p>
        )}
      </section>
    </article>
  );
}

export function TaskListPage({
  currentProjectName = "当前项目",
  projectId,
  selectedTaskId,
  onSelectTask,
  onCreateTaskClick,
}: TaskListPageProps) {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    listTasks(projectId)
      .then((items) => {
        if (!active) return;
        setTasks(items);
      })
      .catch(() => {
        if (active) setError("任务接口不可用，请重试。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, reloadKey]);

  return (
    <main className="page task-page">
      <section className="page-header">
        <div>
          <p className="eyebrow">{currentProjectName} / task runtime</p>
          <h1>任务中心</h1>
          <p>任务列表来自后端任务运行记录；选择任务后读取节点输入、输出和事件快照。</p>
          {!loading && !error ? <p className="current-project-text">真实数据：{tasks.length} 个任务</p> : null}
        </div>
        <div className="header-actions">
          <button className="primary-button" type="button" onClick={onCreateTaskClick}>
            创建任务
          </button>
          <button className="secondary-button" type="button" onClick={() => setReloadKey((current) => current + 1)}>
            重试加载任务
          </button>
        </div>
      </section>

      {loading ? <section className="panel empty-panel">正在加载任务...</section> : null}
      {error ? (
        <section className="panel empty-panel">
          <h2>{error}</h2>
          <button className="secondary-button" type="button" onClick={() => setReloadKey((current) => current + 1)}>
            重试加载任务
          </button>
        </section>
      ) : null}
      {!loading && !error && tasks.length === 0 ? (
        <section className="panel empty-panel">
          <h2>暂无任务</h2>
          <p>从工作流页选择后端契约并创建任务后，这里会显示真实运行记录。</p>
        </section>
      ) : null}
      {!loading && !error && tasks.length > 0 ? (
        <section className="task-center-layout">
          <aside className="task-list-panel">
            <div className="chip-row">
              <span className="chip active">全部</span>
              <span className="chip">运行中</span>
              <span className="chip danger">失败</span>
            </div>
            <div className="task-list">
              {tasks.map((task) => (
                <button
                  aria-label={task.task_id}
                  className={task.task_id === selectedTaskId ? "task-item active" : "task-item"}
                  key={task.task_id}
                  type="button"
                  onClick={() => onSelectTask?.(task.task_id)}
                >
                  <div>
                    <strong>{task.task_id}</strong>
                    <span className={statusClass(task.status)}>{statusLabel(task.status)}</span>
                  </div>
                  <p>
                    {workflowLabel(task)} · {taskTime(task)}
                    {task.current_node_id ? ` · 当前节点: ${task.current_node_id}` : ""}
                  </p>
                </button>
              ))}
            </div>
          </aside>
          <section className="panel empty-panel">
            <h2>选择任务查看详情</h2>
            <p>任务详情会从 `/api/tasks/&lt;task_id&gt;` 读取，不使用前端静态快照。</p>
          </section>
        </section>
      ) : null}
    </main>
  );
}

export function TaskDetailPage({ projectId, taskId, onBackToList, onCreateTaskClick }: TaskDetailPageProps) {
  const [detail, setDetail] = useState<TaskDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setDetail(null);
    getTask(projectId, taskId)
      .then((nextDetail) => {
        if (active) setDetail(nextDetail);
      })
      .catch(() => {
        if (active) setError("任务详情接口不可用，请重试。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, taskId, reloadKey]);

  const eventsByNode = useMemo(() => {
    const grouped = new Map<string, TaskEvent[]>();
    for (const event of detail?.events ?? []) {
      const nodeId = eventNodeId(event);
      if (!nodeId) continue;
      grouped.set(nodeId, [...(grouped.get(nodeId) ?? []), event]);
    }
    return grouped;
  }, [detail]);

  return (
    <main className="page task-page">
      <section className="page-header">
        <div>
          <p className="eyebrow">task runtime / {taskId}</p>
          <h1>任务中心</h1>
          <p>任务详情按后端返回的工作流快照、节点执行和事件展示。</p>
        </div>
        <div className="header-actions">
          <button className="secondary-button" type="button" onClick={onBackToList}>
            返回任务列表
          </button>
          <button className="primary-button" type="button" onClick={onCreateTaskClick}>
            创建任务
          </button>
        </div>
      </section>

      {loading ? <section className="panel empty-panel">正在加载任务详情...</section> : null}
      {error ? (
        <section className="panel empty-panel">
          <h2>{error}</h2>
          <button className="secondary-button" type="button" onClick={() => setReloadKey((current) => current + 1)}>
            重试加载任务详情
          </button>
        </section>
      ) : null}
      {detail ? (
        <section className="task-detail-stack">
          <section className="panel task-summary">
            <div>
              <p className="eyebrow">任务详情</p>
              <h2>任务详情 / {detail.task.task_id}</h2>
              <p>
                <span>{workflowLabel(detail.task)}</span> · {taskTime(detail.task)}
              </p>
              {detail.task.error ? <p className="form-error">{detail.task.error}</p> : null}
            </div>
            <span className={statusClass(detail.task.status)}>{statusLabel(detail.task.status)}</span>
          </section>

          <section className="node-stack" aria-label="节点执行链">
            {detail.node_executions.map((node, index) => (
              <TaskNodeBlock
                events={eventsByNode.get(node.node_id) ?? []}
                index={index}
                key={node.node_execution_id ?? `${node.node_id}-${index}`}
                node={node}
                workflowSnapshot={detail.workflow_snapshot}
              />
            ))}
            {detail.node_executions.length === 0 ? (
              <section className="panel empty-panel">
                <h2>暂无节点执行记录</h2>
              </section>
            ) : null}
          </section>

          <section className="panel">
            <h2>任务事件</h2>
            {detail.events.length ? (
              <ul className="event-list">
                {detail.events.map((event, index) => (
                  <li key={event.event_id ?? index}>{eventLabel(event)}</li>
                ))}
              </ul>
            ) : (
              <p className="empty-state muted">暂无任务事件。</p>
            )}
          </section>
        </section>
      ) : null}
    </main>
  );
}

export function CreateTaskPage({
  currentProjectName = "当前项目",
  projectId,
  selectedTaskId,
  onSelectTask,
  onCreateTaskClick,
}: CreateTaskPageProps) {
  const [localSelectedTaskId, setLocalSelectedTaskId] = useState("");
  const activeTaskId = selectedTaskId ?? localSelectedTaskId;

  function handleSelectTask(taskId: string) {
    setLocalSelectedTaskId(taskId);
    onSelectTask?.(taskId);
  }

  if (activeTaskId) {
    return (
      <TaskDetailPage
        projectId={projectId}
        taskId={activeTaskId}
        onBackToList={() => handleSelectTask("")}
        onCreateTaskClick={onCreateTaskClick}
      />
    );
  }

  return (
    <TaskListPage
      currentProjectName={currentProjectName}
      projectId={projectId}
      onCreateTaskClick={onCreateTaskClick}
      onSelectTask={handleSelectTask}
    />
  );
}
