import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("App", () => {
  it("keeps the project overview as the entry page and opens feature pages through navigation", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", createAppFetchMock());
    render(<App />);

    expect(screen.getByRole("heading", { name: "项目总览" })).toBeInTheDocument();
    expect(await screen.findByRole("cell", { name: "后端真实项目" })).toBeInTheDocument();
    expect(screen.queryByRole("cell", { name: "资产治理验证" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "资产" }));
    expect(screen.getByRole("heading", { name: "资产库" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "资产筛选" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "任务" }));
    expect(screen.getByRole("heading", { name: "任务中心" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "task_backend_1" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "工作流" }));
    expect(screen.getByRole("heading", { name: "从工作流创建任务" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "选择 runninghub_image_to_image_test" })).toBeInTheDocument();
  });

  it("creates and selects a project from the project overview", async () => {
    const user = userEvent.setup();
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", createAppFetchMock(requests));
    render(<App />);

    expect(await screen.findByRole("cell", { name: "后端真实项目" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建项目" }));
    await user.type(screen.getByLabelText("项目名称"), "客户简报项目");
    await user.click(screen.getByRole("button", { name: "创建项目" }));

    expect(screen.getByRole("cell", { name: "客户简报项目" })).toBeInTheDocument();
    expect(screen.getByText("当前项目：客户简报项目")).toBeInTheDocument();

    await waitFor(() => {
      const createProjectRequest = requests.find(
        (request) => request.url === "/api/projects" && request.init?.method === "POST",
      );
      expect(createProjectRequest).toBeTruthy();
      expect(JSON.stringify(createProjectRequest?.init?.body)).toContain("客户简报项目");
    });

    await user.click(screen.getByRole("button", { name: "选择 后端真实项目" }));
    expect(screen.getByText("当前项目：后端真实项目")).toBeInTheDocument();
  });

  it("opens the correct page from project row actions", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", createAppFetchMock());
    render(<App />);

    expect(await screen.findByRole("cell", { name: "后端真实项目" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "资产" }));
    expect(screen.getByRole("heading", { name: "资产库" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "项目" }));
    await user.click(screen.getByRole("button", { name: "工作流" }));
    expect(screen.getByRole("heading", { name: "从工作流创建任务" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "项目" }));
    await user.click(screen.getByRole("button", { name: "打开 后端真实项目 任务" }));
    expect(screen.getByRole("heading", { name: "任务中心" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "task_backend_1" })).toBeInTheDocument();
  });

  it("loads a task detail from the backend when a real task is selected", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", createAppFetchMock());
    render(<App />);

    await user.click(screen.getByRole("button", { name: "任务" }));
    await user.click(await screen.findByRole("button", { name: "task_backend_1" }));

    expect(await screen.findByRole("heading", { name: "任务详情 / task_backend_1" })).toBeInTheDocument();
    expect(screen.getByText("runninghub_image_to_image_test@1.0.0")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "transform_image" })).toBeInTheDocument();
    expect(screen.getByText("输入快照")).toBeInTheDocument();
    expect(screen.getByText("输出快照")).toBeInTheDocument();
  });

  it("creates a task from /api/workflows and navigates by the backend task_id", async () => {
    const user = userEvent.setup();
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", createAppFetchMock(requests));
    render(<App />);

    await user.click(screen.getByRole("button", { name: "工作流" }));
    await user.click(await screen.findByRole("button", { name: "选择 runninghub_image_to_image_test" }));
    await user.type(screen.getByLabelText("prompt"), "生成新品发布简报");
    await user.type(screen.getByLabelText("image_urls"), "https://cdn.example.test/brief.png");
    await user.click(screen.getByRole("button", { name: "创建并运行任务" }));

    expect(await screen.findByRole("heading", { name: "任务详情 / task_backend_created" })).toBeInTheDocument();
    expect(screen.queryByText(/task_ui_/)).not.toBeInTheDocument();

    await waitFor(() => {
      const createRequest = requests.find((request) => request.url === "/api/tasks" && request.init?.method === "POST");
      expect(createRequest).toBeTruthy();
      expect(JSON.stringify(createRequest?.init?.body)).not.toContain("task_ui_");
    });
    expect(screen.getByRole("heading", { name: "transform_image" })).toBeInTheDocument();
  });

  it("shows an error and retry action when /api/workflows is unavailable", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", createAppFetchMock([], { workflowsUnavailable: true }));
    render(<App />);

    await user.click(screen.getByRole("button", { name: "工作流" }));

    expect(await screen.findByText("工作流接口不可用，请重试。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试加载工作流" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "选择 asset_catalog" })).not.toBeInTheDocument();
  });
});

function createAppFetchMock(
  requests: Array<{ url: string; init?: RequestInit }> = [],
  options: { workflowsUnavailable?: boolean } = {},
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString();
    requests.push({ url, init });

    if (url === "/api/auth/login") return jsonResponse({ access_token: "asset-token", token_type: "bearer" });
    if (url === "/api/projects") {
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        return jsonResponse({
          project_id: "backend_project_created",
          owner_user_id: "user_1",
          name: body.name,
          description: null,
          created_at: "2026-05-27T03:00:00Z",
        });
      }
      return jsonResponse({
        items: [
          {
            project_id: "backend_project_1",
            owner_user_id: "user_1",
            name: "后端真实项目",
            description: null,
            created_at: "2026-05-27T02:00:00Z",
          },
        ],
      });
    }
    if (url.startsWith("/api/assets/search")) return jsonResponse({ items: [], total: 0 });
    if (url.startsWith("/api/assets/tags")) return jsonResponse({ items: [] });
    if (url.startsWith("/api/assets/collections")) return jsonResponse({ items: [] });

    if (url.startsWith("/api/tasks?project_id=")) {
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
    if (url.startsWith("/api/tasks/task_backend_1?")) return jsonResponse(taskDetail("task_backend_1"));
    if (url.startsWith("/api/tasks/task_backend_created?")) return jsonResponse(taskDetail("task_backend_created"));

    if (url === "/api/workflows") {
      if (options.workflowsUnavailable) return jsonResponse({ detail: "service unavailable" }, 503);
      return jsonResponse({
        items: [
          {
            workflow: {
              id: "runninghub_image_to_image_test",
              version: "1.0.0",
              name: "RunningHub 图生图调用测试",
              scope: "global",
              input_schema: {
                type: "object",
                required: ["prompt", "image_urls"],
                properties: {
                  prompt: { type: "string" },
                  image_urls: { type: "array", items: { type: "string" } },
                },
              },
            },
            nodes: [
              {
                id: "transform_image",
                ref: "ai.runninghub_image_to_image.v1",
                inputs: {
                  prompt: { from: "$workflow.input.prompt" },
                  image_urls: { from: "$workflow.input.image_urls" },
                },
                outputs: { type: "object" },
              },
            ],
            edges: [{ from: "START", to: "transform_image" }, { from: "transform_image", to: "END" }],
          },
        ],
      });
    }
    if (url === "/api/tasks" && init?.method === "POST") {
      return jsonResponse({
        task_id: "task_backend_created",
        project_id: "backend_project_1",
        workflow_id: "runninghub_image_to_image_test",
        workflow_version: "1.0.0",
        status: "queued",
        created_at: "2026-05-27T02:05:00Z",
      });
    }

    return jsonResponse({ detail: "not found" }, 404);
  });
}

function taskDetail(taskId: string) {
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
