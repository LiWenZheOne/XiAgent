import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateTaskPage, TaskDetailPage, TaskListPage } from "../task/CreateTaskPage";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Task pages", () => {
  it("loads the task list from /api/tasks for the selected project", async () => {
    const requests: string[] = [];
    vi.stubGlobal("fetch", createTaskFetchMock(requests));

    render(<TaskListPage currentProjectName="内容生成平台" projectId="backend_project_1" />);

    expect(screen.getByRole("heading", { name: "任务中心" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "task_backend_1" })).toBeInTheDocument();
    expect(screen.getByText("真实数据：1 个任务")).toBeInTheDocument();
    expect(screen.queryByText("task_20260527_018")).not.toBeInTheDocument();
    expect(requests).toContain("/api/tasks?project_id=backend_project_1");
  });

  it("loads task detail snapshots and events from /api/tasks/<task_id>", async () => {
    const requests: string[] = [];
    vi.stubGlobal("fetch", createTaskFetchMock(requests));

    render(<TaskDetailPage projectId="backend_project_1" taskId="task_backend_1" onBackToList={() => undefined} />);

    expect(await screen.findByRole("heading", { name: "任务详情 / task_backend_1" })).toBeInTheDocument();
    expect(screen.getByText("runninghub_image_to_image_test@1.0.0")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "transform_image" })).toBeInTheDocument();
    expect(screen.getByText("输入快照")).toBeInTheDocument();
    expect(screen.getByText("输出快照")).toBeInTheDocument();
    expect(screen.getAllByText(/node_finished/).length).toBeGreaterThan(0);
    expect(requests).toContain("/api/tasks/task_backend_1?project_id=backend_project_1");
  });

  it("keeps CreateTaskPage export compatible while using real task APIs", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", createTaskFetchMock([]));

    render(<CreateTaskPage currentProjectName="内容生成平台" projectId="backend_project_1" />);

    await user.click(await screen.findByRole("button", { name: "task_backend_1" }));

    expect(await screen.findByRole("heading", { name: "任务详情 / task_backend_1" })).toBeInTheDocument();
  });
});

function createTaskFetchMock(requests: string[]) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = input.toString();
    requests.push(url);

    if (url === "/api/tasks?project_id=backend_project_1") {
      return jsonResponse({
        items: [
          {
            task_id: "task_backend_1",
            project_id: "backend_project_1",
            workflow_id: "runninghub_image_to_image_test",
            workflow_version: "1.0.0",
            status: "succeeded",
            created_at: "2026-05-27T02:00:00Z",
            updated_at: "2026-05-27T02:01:00Z",
          },
        ],
      });
    }

    if (url === "/api/tasks/task_backend_1?project_id=backend_project_1") {
      return jsonResponse(taskDetail("task_backend_1"));
    }

    return jsonResponse({ detail: "not found" }, 404);
  });
}

export function taskDetail(taskId: string) {
  return {
    task: {
      task_id: taskId,
      project_id: "backend_project_1",
      workflow_id: "runninghub_image_to_image_test",
      workflow_version: "1.0.0",
      status: "succeeded",
      created_at: "2026-05-27T02:00:00Z",
      updated_at: "2026-05-27T02:01:00Z",
    },
    workflow_snapshot: {
      workflow: {
        id: "runninghub_image_to_image_test",
        version: "1.0.0",
        name: "RunningHub 图生图调用测试",
      },
      nodes: [{ id: "transform_image", ref: "ai.runninghub_image_to_image.v1" }],
      edges: [],
    },
    node_executions: [
      {
        node_id: "transform_image",
        node_ref: "ai.runninghub_image_to_image.v1",
        node_execution_id: "exec_1",
        attempt: 1,
        status: "succeeded",
        input_snapshot: { prompt: "真实输入", image_urls: ["https://cdn.example.test/brief.png"] },
        output_snapshot: { image_url: "https://cdn.example.test/result.png", status: "completed" },
        started_at: "2026-05-27T02:00:02Z",
        finished_at: "2026-05-27T02:00:58Z",
      },
    ],
    node_attempts: {
      transform_image: [
        {
          node_id: "transform_image",
          node_ref: "ai.runninghub_image_to_image.v1",
          node_execution_id: "exec_1",
          attempt: 1,
          status: "succeeded",
        },
      ],
    },
    events: [
      {
        event_id: "evt_1",
        event_type: "node_started",
        payload: { node_id: "transform_image" },
        created_at: "2026-05-27T02:00:02Z",
      },
      {
        event_id: "evt_2",
        event_type: "node_finished",
        payload: { node_id: "transform_image" },
        created_at: "2026-05-27T02:00:58Z",
      },
    ],
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
