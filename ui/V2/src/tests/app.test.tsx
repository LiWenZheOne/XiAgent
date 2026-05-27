import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";

const workflowContract = {
  workflow: {
    id: "storyboard_generation",
    version: "1.0.0",
    name: "故事板生成",
    description: "根据主题生成候选图片并等待用户选择。",
    input_schema: {
      type: "object",
      required: ["topic"],
      properties: {
        topic: { type: "string", title: "创作主题" },
        image_urls: { type: "array", title: "参考图片", items: { type: "string" } },
      },
    },
  },
  nodes: [
    { id: "prepare_prompt", ref: "tools.storyboard_prompt.v1" },
    {
      id: "choose_image",
      ref: "system.user_choice.v1",
      outputs: {
        type: "object",
        required: ["selected_id", "selected_item"],
        properties: {
          selected_id: { type: "string" },
          selected_item: { type: "object" },
          selected_image_url: { type: "string" },
        },
      },
      ui: {
        controls: {
          interaction: {
            control_id: "ui.choice.image_three.v1",
            variant: "hover_focus",
            mode: "interactive",
            bindings: {
              items_path: "$node.input.candidates",
              image_url_path: "image_url",
              value_path: "id",
            },
          },
        },
      },
    },
  ],
  edges: [],
};

const uiControlsResponse = {
  items: [
    {
      control_id: "ui.choice.image_three.v1",
      version: "1.0.0",
      name: "Image Three Choice",
      kind: "interaction",
      tags: ["image", "choice", "select_one", "candidates_3"],
      variants: [
        { name: "equal_grid", label: "三图等宽", tags: [], modes: ["interactive"], required_bindings: [] },
        { name: "hero_list", label: "首图大列表", tags: [], modes: ["interactive"], required_bindings: [] },
        { name: "hover_focus", label: "悬停放大", tags: [], modes: ["interactive"], required_bindings: [] },
      ],
      description: "图片候选三选一控件",
    },
  ],
};

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockFetch() {
  const createdTasks: Array<{
    task_id: string;
    project_id: string;
    workflow_id?: string;
    workflow_name?: string;
    workflow_version?: string;
    status: string;
    current_node_id?: string | null;
    created_at: string;
  }> = [];

  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";

    if (url === "/api/auth/login" && method === "POST") {
      return jsonResponse({ user: { user_id: "user-1", username: "alice" }, access_token: "token", token_type: "bearer" });
    }
    if (url === "/api/projects" && method === "GET") {
      return jsonResponse({
        items: [
          { project_id: "global", name: "全局项目", owner_user_id: "system", description: "所有用户可访问的默认项目", created_at: "2026-05-27T00:00:00Z" },
          { project_id: "project-1", name: "演示项目", owner_user_id: "user-1", created_at: "2026-05-27T08:00:00Z" },
          { project_id: "project-2", name: "客户项目", owner_user_id: "user-1", created_at: "2026-05-27T09:00:00Z" },
        ],
      });
    }
    if (url === "/api/tasks?project_id=global") {
      return jsonResponse({
        items: [
          {
            task_id: "task-1",
            project_id: "global",
            workflow_id: "storyboard_generation",
            workflow_name: workflowContract.workflow.name,
            workflow_version: "1.0.0",
            status: "waiting",
            current_node_id: "choose_image",
            created_at: "2026-05-27T08:10:00Z",
          },
          ...createdTasks.filter((task) => task.project_id === "global"),
        ],
      });
    }
    if (url === "/api/tasks?project_id=project-1") {
      return jsonResponse({
        items: [
          {
            task_id: "task-1",
            project_id: "project-1",
            workflow_id: "storyboard_generation",
            workflow_name: "故事板生成",
            workflow_version: "1.0.0",
            status: "waiting",
            current_node_id: "choose_image",
            created_at: "2026-05-27T08:10:00Z",
          },
          ...createdTasks.filter((task) => task.project_id === "project-1"),
        ],
      });
    }
    if (url === "/api/tasks?project_id=project-2") {
      return jsonResponse({
        items: [{
          task_id: "task-project-2",
          project_id: "project-2",
          workflow_id: "runninghub_text_to_image_test",
          workflow_name: "RunningHub 文生图调用测试",
          workflow_version: "1.0.0",
          status: "created",
          current_node_id: null,
          created_at: "2026-05-27T09:10:00Z",
        }],
      });
    }
    if (url === "/api/workflows?project_id=global" || url === "/api/workflows?project_id=project-1" || url === "/api/workflows?project_id=project-2" || url === "/api/workflows") {
      return jsonResponse({
        items: [
          workflowContract,
          {
            workflow: {
              id: "runninghub_text_to_image_test",
              version: "1.0.0",
              name: "RunningHub Text To Image Test",
              description: "Developer-only workflow test",
              input_schema: { type: "object", properties: { prompt: { type: "string" } } },
            },
            nodes: [{ id: "run", ref: "ai.runninghub_text_to_image.v1" }],
            edges: [],
          },
        ],
      });
    }
    if (url === "/api/ui/node-controls") {
      return jsonResponse(uiControlsResponse);
    }
    if (url.startsWith("/api/assets/search")) {
      return jsonResponse({
        items: [
          {
            asset_id: "asset-1",
            asset_type: "file",
            name: "参考图",
            scope: "project",
            project_id: "project-1",
            mime_type: "image/png",
            size_bytes: 1024,
            metadata: { public_url: "https://cdn.example.com/ref.png", tags: ["角色"] },
            created_at: "2026-05-27T08:01:00Z",
          },
        ],
      });
    }
    if (url === "/api/assets/collections?scope=combined&project_id=global" || url === "/api/assets/collections?scope=combined&project_id=project-1") return jsonResponse({ items: [] });
    if (url === "/api/assets/tags?scope=combined&project_id=global" || url === "/api/assets/tags?scope=combined&project_id=project-1") return jsonResponse({ items: [] });
    if (url === "/api/tasks/task-1?project_id=global" || url === "/api/tasks/task-2?project_id=global" || url === "/api/tasks/task-1?project_id=project-1" || url === "/api/tasks/task-2?project_id=project-1") {
      const createdTask = createdTasks.find((task) => task.task_id === "task-2");
      const projectId = url.includes("project_id=global") ? "global" : "project-1";
      return jsonResponse({
        task: createdTask ?? {
          task_id: "task-1",
          project_id: projectId,
          workflow_id: "storyboard_generation",
          workflow_name: "故事板生成",
          workflow_version: "1.0.0",
          status: "waiting",
          current_node_id: "choose_image",
          created_at: "2026-05-27T08:10:00Z",
        },
        workflow_snapshot: workflowContract,
        node_executions: [
          {
            node_execution_id: "exec-1",
            node_id: "prepare_prompt",
            node_ref: "tools.storyboard_prompt.v1",
            status: "succeeded",
            input_snapshot: { topic: "雨夜城市" },
            output_snapshot: { prompt: "雨夜城市电影感", results: [{ public_url: "https://cdn.example.com/a.png" }] },
            attempt: 1,
          },
          {
            node_execution_id: "exec-2",
            node_id: "choose_image",
            node_ref: "system.user_choice.v1",
            status: "waiting",
            input_snapshot: {
              question: "选择一张图",
              candidates: [
                { id: "a", label: "第一张", image_url: "https://cdn.example.com/a.png" },
                { id: "b", label: "第二张", image_url: "https://cdn.example.com/b.png" },
                { id: "c", label: "第三张", image_url: "https://cdn.example.com/c.png" },
              ],
            },
            output_snapshot: null,
            metadata: {
              question: "选择一张图",
              candidates: [
                { id: "a", label: "第一张", image_url: "https://cdn.example.com/a.png" },
                { id: "b", label: "第二张", image_url: "https://cdn.example.com/b.png" },
                { id: "c", label: "第三张", image_url: "https://cdn.example.com/c.png" },
              ],
            },
            attempt: 1,
          },
        ],
        node_attempts: {},
        events: [{ event_id: "event-1", event_type: "node_waiting", node_id: "choose_image", message: "等待选择" }],
      });
    }
    if (url === "/api/tasks" && method === "POST") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { project_id?: string; contract?: { workflow?: { name?: string; version?: string } } };
      const task = {
        task_id: body.project_id === "project-2" ? "task-project-2-created" : "task-2",
        project_id: body.project_id ?? "global",
        workflow_name: body.contract?.workflow?.name ?? "故事板生成",
        workflow_version: String(body.contract?.workflow?.version ?? "1.0.0"),
        status: "created",
        current_node_id: null,
        created_at: "2026-05-27T08:20:00Z",
      };
      createdTasks.push(task);
      return jsonResponse({
        task_id: task.task_id,
        project_id: task.project_id,
        status: task.status,
        workflow_name: task.workflow_name,
        workflow_version: task.workflow_version,
      });
    }
    if (url === "/api/tasks/task-1/interactions" && method === "POST") {
      return jsonResponse({ task_id: "task-1", project_id: "global", status: "running" });
    }
    return jsonResponse({ items: [] });
  });
}

async function login() {
  await userEvent.type(screen.getByLabelText("用户名"), "alice");
  await userEvent.type(screen.getByLabelText("密码"), "secret-123");
  await userEvent.click(screen.getByRole("button", { name: "登录" }));
  await screen.findByRole("button", { name: "创建任务" });
}

describe("XiAgent V2 app", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", mockFetch());
  });

  it("requires a real user login and opens the project workspace", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "登录 XiAgent" })).toBeInTheDocument();

    await login();

    expect(screen.getByRole("heading", { name: "任务工作台" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建任务" })).toBeInTheDocument();
  });

  it("uses the shared global project as the default project", async () => {
    render(<App />);
    await login();

    expect(screen.getByRole("combobox")).toHaveValue("global");
  });

  it("creates tasks through a readable workflow form without showing JSON schema", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await screen.findByRole("heading", { name: "新建任务" });

    expect(screen.getByLabelText("创作主题")).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/workflows?project_id=global")).toBe(true);
    });
    expect(screen.getByText(/RunningHub Text To Image Test/)).toBeInTheDocument();
    expect(screen.queryByText(/input_schema/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\"type\"/)).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("创作主题"), "雨夜城市");
    await userEvent.click(screen.getByRole("checkbox", { name: "选择资产 参考图" }));
    await userEvent.click(screen.getByRole("button", { name: "创建并运行" }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([url, init]) => url === "/api/tasks" && init?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        project_id: "global",
        input_data: {
          topic: "雨夜城市",
          image_urls: ["https://cdn.example.com/ref.png"],
        },
      });
    });
    const detail = await screen.findByLabelText("任务运行详情");
    expect(detail).toBeInTheDocument();
    expect(await within(detail).findByRole("heading", { name: "故事板生成", level: 1 })).toBeInTheDocument();
  });

  it("switches task and workflow creation data to the selected project", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    expect(await screen.findByRole("button", { name: "打开 故事板生成" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("当前项目"), "project-2");

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "打开 故事板生成" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "打开 RunningHub 文生图调用测试" })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await screen.findByRole("heading", { name: "新建任务" });
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/workflows?project_id=project-2")).toBe(true);
    });

    await userEvent.click(screen.getByRole("button", { name: /RunningHub Text To Image Test/ }));
    await userEvent.type(screen.getByLabelText("提示词"), "蓝色机器人");
    await userEvent.click(screen.getByRole("button", { name: "创建并运行" }));

    await waitFor(() => {
      const post = [...fetchMock.mock.calls].reverse().find(([url, init]) => url === "/api/tasks" && init?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        project_id: "project-2",
        input_data: { prompt: "蓝色机器人" },
      });
    });
  });

  it("shows node input and output as user-facing cards and supports waiting interaction", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(await screen.findByRole("button", { name: "打开 故事板生成" }));

    const detail = await screen.findByLabelText("任务运行详情");
    expect(within(detail).getByText("准备提示词")).toBeInTheDocument();
    expect(within(detail).getByText("雨夜城市电影感")).toBeInTheDocument();
    expect(within(detail).getByRole("img", { name: "准备提示词 输出图片 1" })).toHaveAttribute("src", "https://cdn.example.com/a.png");
    expect(screen.queryByText(/output_snapshot/)).not.toBeInTheDocument();
    expect(screen.queryByText(/public_url/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "选择 第二张" }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([url, init]) => url === "/api/tasks/task-1/interactions" && init?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        project_id: "global",
        node_id: "choose_image",
        output: {
          selected_id: "b",
          selected_index: 1,
          selected_image_url: "https://cdn.example.com/b.png",
        },
      });
    });
  });

  it("opens the control library tab and lists registered node controls", async () => {
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "控件库" }));

    expect(await screen.findByRole("heading", { name: "控件库" })).toBeInTheDocument();
    expect(screen.getByText("ui.choice.image_three.v1")).toBeInTheDocument();
    expect(screen.getByText("悬停放大")).toBeInTheDocument();
  });
});
