import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApprovalControl } from "../node-ui/controls/ApprovalControl";
import { ControlLibraryPage } from "../node-ui/ControlLibraryPage";
import { ImageChoiceThreeControl } from "../node-ui/controls/ImageChoiceThreeControl";
import { SchemaFormControl } from "../node-ui/controls/SchemaFormControl";
import { getNodeUiControl, resolveNodeControlConfig, resolveNodeInteractionConfig } from "../node-ui/registry";
import type { JsonSchema, NodeUiControlConfig, TaskNodeExecution, UiControlDescriptor, WorkflowNodeSpec } from "../api/types";

const config: NodeUiControlConfig = {
  control_id: "ui.choice.image_three.v1",
  variant: "hover_focus",
  mode: "interactive",
  bindings: {
    items_path: "$node.input.candidates",
    image_url_path: "image_url",
    value_path: "id",
  },
};

const node: TaskNodeExecution = {
  node_execution_id: "exec-1",
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
};

const controlDescriptors: UiControlDescriptor[] = [
  {
    control_id: "ui.display.value.v1",
    version: "1.0.0",
    name: "Value Display",
    kind: "output",
    tags: ["value", "fallback", "readonly"],
    variants: [{ name: "default", label: "默认值展示", tags: [], modes: ["readonly"], required_bindings: [] }],
    description: "通用值展示 fallback 控件。",
  },
  {
    control_id: "ui.display.image_candidates.v1",
    version: "1.0.0",
    name: "Image Candidates",
    kind: "output",
    tags: ["image", "list", "candidates", "readonly"],
    variants: [{ name: "grid", label: "网格", tags: [], modes: ["readonly"], required_bindings: [] }],
    description: "图片候选列表展示控件。",
  },
  {
    control_id: "ui.display.image_viewer.v1",
    version: "1.0.0",
    name: "Image Viewer",
    kind: "output",
    tags: ["image", "viewer", "modal", "readonly"],
    variants: [{ name: "grid_modal", label: "缩略图网格原图查看", tags: [], modes: ["readonly"], required_bindings: [] }],
    description: "只读图片输出查看控件。",
  },
  {
    control_id: "ui.choice.image_three.v1",
    version: "1.0.0",
    name: "Image Three Choice",
    kind: "interaction",
    tags: ["image", "choice", "select_one", "candidates_3", "interactive"],
    variants: [
      { name: "equal_grid", label: "三图等宽", tags: [], modes: ["interactive", "readonly"], required_bindings: [] },
      { name: "hero_list", label: "首图大列表", tags: [], modes: ["interactive", "readonly"], required_bindings: [] },
      { name: "hover_focus", label: "悬停放大", tags: [], modes: ["interactive", "readonly"], required_bindings: [] },
    ],
    description: "图片候选三选一控件。",
  },
  {
    control_id: "ui.interaction.approval.v1",
    version: "1.0.0",
    name: "Approval",
    kind: "interaction",
    tags: ["approval", "human", "interactive"],
    variants: [{ name: "default", label: "默认审批", tags: [], modes: ["interactive", "readonly"], required_bindings: [] }],
    description: "人工审批交互控件。",
  },
  {
    control_id: "ui.input.schema_form.v1",
    version: "1.0.0",
    name: "Schema Input Form",
    kind: "input",
    tags: ["schema", "input", "form", "interactive"],
    variants: [{ name: "default", label: "通用 schema 输入表单", tags: [], modes: ["input", "readonly"], required_bindings: [] }],
    description: "在输入节点中按 schema 收集用户提交的结构化参数。",
  },
  {
    control_id: "ui.input.asset_image_picker.v1",
    version: "1.0.0",
    name: "Asset Image Picker",
    kind: "input",
    tags: ["asset", "image", "picker", "upload"],
    variants: [{ name: "thumbnails", label: "缩略图资产图片选择", tags: [], modes: ["input", "readonly"], required_bindings: [] }],
    description: "从资产库选择或上传图片。",
  },
  {
    control_id: "ui.fallback.schema_form.v1",
    version: "1.0.0",
    name: "Schema Form",
    kind: "input",
    tags: ["schema", "form", "fallback"],
    variants: [{ name: "default", label: "默认表单", tags: [], modes: ["input"], required_bindings: [] }],
    description: "基于 JSON Schema 的输入表单 fallback 控件。",
  },
];

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("node-ui controls", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders image three choice candidates and submits selected payload", async () => {
    const onSubmit = vi.fn();
    render(<ImageChoiceThreeControl config={config} node={node} onSubmit={onSubmit} />);

    expect(screen.getByRole("img", { name: "第一张" })).toHaveAttribute("src", "https://cdn.example.com/a.png");
    expect(screen.getByRole("img", { name: "第二张" })).toHaveAttribute("src", "https://cdn.example.com/b.png");
    expect(screen.getByRole("img", { name: "第三张" })).toHaveAttribute("src", "https://cdn.example.com/c.png");

    await userEvent.click(screen.getByRole("button", { name: "选择 第二张" }));

    expect(onSubmit).toHaveBeenCalledWith({
      selected_id: "b",
      selected_index: 1,
      selected_item: { id: "b", label: "第二张", image_url: "https://cdn.example.com/b.png" },
      selected_image_url: "https://cdn.example.com/b.png",
    });
  });

  it("shows an in-node preview for every manifest control in the control library", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input) === "/api/ui/node-controls") return jsonResponse({ items: controlDescriptors });
      return jsonResponse({ items: [] });
    }));

    render(<ControlLibraryPage />);

    expect(await screen.findByRole("heading", { name: "控件库" })).toBeInTheDocument();
    expect(await screen.findAllByRole("heading", { name: "节点效果预览" })).toHaveLength(controlDescriptors.length);
    expect(screen.getByText("镜头数量")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "候选输出 A" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "示例图片" })).toBeInTheDocument();
    expect(screen.getAllByLabelText("图片三选一")).toHaveLength(3);
    expect(screen.getByRole("textbox", { name: "确认意见" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "提示词" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "提交并继续" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("img", { name: "参考图" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("textbox", { name: "Fallback 提示词" })).toBeInTheDocument();
  });

  it("uses default user choice control when workflow has no explicit ui config", () => {
    const resolved = resolveNodeInteractionConfig(node);
    const Control = getNodeUiControl(resolved?.control_id ?? "");

    expect(resolved?.control_id).toBe("ui.choice.image_three.v1");
    render(<Control config={resolved!} node={node} preview />);

    expect(screen.getByLabelText("图片三选一")).toBeInTheDocument();
  });

  it("opens readonly image viewer thumbnails in an original image dialog", async () => {
    const Control = getNodeUiControl("ui.display.image_viewer.v1");
    const outputNode: TaskNodeExecution = {
      node_execution_id: "exec-viewer",
      node_id: "generate_image",
      node_ref: "ai.runninghub_text_to_image.v1",
      status: "succeeded",
      output_snapshot: {
        results: [
          {
            id: "rh-1",
            url: "https://cdn.example.com/generated.png",
            text: "Generated image",
            output_type: "image",
          },
        ],
      },
    };

    render(
      <Control
        config={{
          control_id: "ui.display.image_viewer.v1",
          variant: "grid_modal",
          mode: "readonly",
          bindings: {
            items_path: "$node.output.results",
            image_url_path: "url",
            label_path: "text",
          },
        }}
        node={outputNode}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "查看 Generated image" }));

    const dialog = screen.getByRole("dialog", { name: "图片预览" });
    expect(within(dialog).getByRole("img", { name: "Generated image" })).toHaveAttribute("src", "https://cdn.example.com/generated.png");
    expect(within(dialog).getByRole("link", { name: "打开原图" })).toHaveAttribute("href", "https://cdn.example.com/generated.png");
  });

  it("reuses a completed interaction control as the readonly output renderer", () => {
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["prompt"],
      properties: {
        prompt: { type: "string", title: "Prompt" },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-input",
      node_id: "collect_user_input",
      node_ref: "system.user_input.v1",
      status: "succeeded",
      input_snapshot: {},
      output_snapshot: { prompt: "neon city" },
    };
    const nodeSpec: WorkflowNodeSpec = {
      id: "collect_user_input",
      ref: "system.user_input.v1",
      outputs: inputSchema,
      ui: {
        controls: {
          interaction: {
            control_id: "ui.input.schema_form.v1",
            variant: "default",
            mode: "input",
          },
        },
      },
    };

    const resolved = resolveNodeControlConfig(inputNode, nodeSpec, { workflow: { input_schema: inputSchema } }, "output");

    expect(resolved).toMatchObject({
      control_id: "ui.input.schema_form.v1",
      variant: "default",
      mode: "readonly",
    });
  });

  it("keeps unknown controls on the fallback path", async () => {
    const Control = getNodeUiControl("ui.unknown.v1");

    render(<Control config={{ control_id: "ui.unknown.v1" }} node={node} />);

    await waitFor(() => {
      expect(screen.getByText(/尚未在 V2 注册/)).toBeInTheDocument();
    });
  });

  it("renders node user input through schema form and the reusable asset image picker", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/assets/collections")) {
        return jsonResponse({ items: [{ collection_id: "collection-1", name: "角色素材", asset_count: 1 }] });
      }
      if (url.startsWith("/api/assets/tags")) {
        return jsonResponse({ items: [{ tag_id: "tag-1", name: "角色", scope: "project", asset_count: 1 }] });
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
              metadata: { public_url: "https://cdn.example.com/ref.png" },
              created_at: "2026-05-28T09:00:00Z",
            },
          ],
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSubmit = vi.fn();
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["prompt"],
      properties: {
        prompt: { type: "string", title: "提示词" },
        image_urls: { type: "array", title: "参考图", items: { type: "string" } },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-input",
      node_id: "collect_user_input",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema, title: "启动参数" },
    };
    const nodeSpec: WorkflowNodeSpec = {
      id: "collect_user_input",
      ref: "system.user_input.v1",
      outputs: inputSchema,
    };
    const schemaConfig: NodeUiControlConfig = {
      control_id: "ui.input.schema_form.v1",
      variant: "default",
      mode: "input",
      options: {
        fields: {
          image_urls: {
            control_id: "ui.input.asset_image_picker.v1",
            variant: "thumbnails",
            mode: "input",
            selection_mode: "multiple",
            upload_scope: "project",
          },
        },
      },
    };

    render(
      <SchemaFormControl
        config={schemaConfig}
        node={inputNode}
        nodeSpec={nodeSpec}
        onSubmit={onSubmit}
        projectId="project-1"
        snapshot={{ workflow: { input_schema: inputSchema } }}
      />,
    );

    await userEvent.type(screen.getByLabelText("提示词"), "蓝色机器人");
    await userEvent.click(screen.getByRole("button", { name: "选择图片" }));
    expect(await screen.findByRole("dialog", { name: "选择资产图片" })).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/assets/search?scope=combined&project_id=project-1"))).toBe(true);
    });

    const assetImage = await screen.findByRole("img", { name: "参考图" });
    await userEvent.click(assetImage.closest("button") as HTMLButtonElement);
    await userEvent.click(screen.getByRole("button", { name: "确认选择" }));
    await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));

    expect(onSubmit).toHaveBeenCalledWith({
      prompt: "蓝色机器人",
      image_urls: ["https://cdn.example.com/ref.png"],
    });
  });

  it("filters task asset picker assets by selected project directories and tags", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const parsed = new URL(url, "http://localhost");
      if (parsed.pathname === "/api/projects") {
        return jsonResponse({
          items: [
            { project_id: "global", name: "全局项目", owner_user_id: "user-1" },
            { project_id: "project-1", name: "当前项目", owner_user_id: "user-1" },
            { project_id: "project-2", name: "素材项目", owner_user_id: "user-1" },
          ],
        });
      }
      if (parsed.pathname === "/api/assets/collections") {
        const projectId = parsed.searchParams.get("project_id");
        return jsonResponse({
          items: projectId === "project-2"
            ? [{ collection_id: "collection-project", name: "项目目录", asset_count: 1 }]
            : [{ collection_id: "collection-current", name: "当前目录", asset_count: 1 }],
        });
      }
      if (parsed.pathname === "/api/assets/tags") {
        const projectId = parsed.searchParams.get("project_id");
        return jsonResponse({
          items: projectId === "project-2"
            ? [{ tag_id: "tag-project", name: "项目标签", scope: "project", project_id: "project-2", asset_count: 1 }]
            : [{ tag_id: "tag-current", name: "当前标签", scope: "project", project_id: "project-1", asset_count: 1 }],
        });
      }
      if (parsed.pathname === "/api/assets/search") {
        const projectId = parsed.searchParams.get("project_id");
        return jsonResponse({
          items: [
            {
              asset_id: projectId === "project-2" ? "asset-project" : "asset-current",
              asset_type: "file",
              name: projectId === "project-2" ? "项目参考图" : "当前参考图",
              scope: "project",
              project_id: projectId,
              mime_type: "image/png",
              size_bytes: 1024,
              metadata: { public_url: projectId === "project-2" ? "https://cdn.example.com/project.png" : "https://cdn.example.com/current.png" },
              created_at: "2026-05-28T09:00:00Z",
            },
          ],
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const inputSchema: JsonSchema = {
      type: "object",
      properties: {
        image_urls: { type: "array", title: "参考图", items: { type: "string" } },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-input",
      node_id: "collect_user_input",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema, title: "启动参数" },
    };

    render(
      <SchemaFormControl
        config={{
          control_id: "ui.input.schema_form.v1",
          variant: "default",
          mode: "input",
          options: {
            fields: {
              image_urls: {
                control_id: "ui.input.asset_image_picker.v1",
                variant: "thumbnails",
                mode: "input",
                selection_mode: "multiple",
                upload_scope: "project",
              },
            },
          },
        }}
        node={inputNode}
        onSubmit={vi.fn()}
        projectId="project-1"
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "选择图片" }));
    expect(await screen.findByRole("dialog", { name: "选择资产图片" })).toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: "选择资产项目：当前项目" }));
    const projectDialog = screen.getByRole("dialog", { name: "选择资产项目" });
    expect(within(projectDialog).getByRole("radio", { name: "全局项目" })).toBeInTheDocument();
    await userEvent.click(within(projectDialog).getByRole("radio", { name: "素材项目" }));
    await userEvent.click(within(projectDialog).getByRole("button", { name: "确认项目" }));

    expect(await screen.findByRole("button", { name: "项目目录" })).toBeInTheDocument();
    await userEvent.click(await screen.findByLabelText("筛选标签 项目标签"));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([calledUrl]) => {
        const called = new URL(String(calledUrl), "http://localhost");
        return called.pathname === "/api/assets/search"
          && called.searchParams.get("project_id") === "project-2"
          && called.searchParams.get("tag_ids") === "tag-project";
      })).toBe(true);
    });
  });

  it("renders submitted schema form values with the same controls in readonly mode", () => {
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["caption"],
      properties: {
        caption: { type: "string", title: "Caption" },
        reference_images: { type: "array", title: "Reference Images", items: { type: "string" } },
        ratio: { type: "string", title: "Ratio", enum: ["square", "wide", "tall", "poster"] },
        quality: { type: "string", title: "Quality", enum: ["draft", "final"] },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-input",
      node_id: "collect_user_input",
      node_ref: "system.user_input.v1",
      status: "succeeded",
      input_snapshot: {},
      output_snapshot: {
        caption: "neon city",
        reference_images: ["https://cdn.example.com/ref.png"],
        ratio: "wide",
        quality: "final",
      },
      metadata: { input_schema: inputSchema, title: "Submitted parameters" },
    };

    render(
      <SchemaFormControl
        config={{
          control_id: "ui.input.schema_form.v1",
          variant: "default",
          mode: "readonly",
          options: {
            fields: {
              reference_images: {
                control_id: "ui.input.asset_image_picker.v1",
                variant: "thumbnails",
                mode: "readonly",
              },
            },
          },
        }}
        node={inputNode}
        value={inputNode.output_snapshot}
      />,
    );

    expect(screen.getByLabelText("Caption")).toHaveValue("neon city");
    expect(screen.getByLabelText("Caption")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Ratio")).toHaveValue("wide");
    expect(screen.getByLabelText("Ratio")).toBeDisabled();
    expect(screen.getByRole("radio", { name: "final" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "final" })).toBeDisabled();
    expect(screen.getByRole("img", { name: "Reference Images" })).toHaveAttribute("src", "https://cdn.example.com/ref.png");
    expect(screen.queryByRole("button", { name: "选择图片" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交并继续" })).not.toBeInTheDocument();
  });

  it("renders completed image choices with the selected card readonly", () => {
    const readonlyNode: TaskNodeExecution = {
      ...node,
      status: "succeeded",
      output_snapshot: {
        selected_id: "b",
        selected_index: 1,
        selected_image_url: "https://cdn.example.com/b.png",
      },
    };

    render(<ImageChoiceThreeControl config={{ ...config, mode: "readonly" }} node={readonlyNode} />);

    const selected = screen.getByRole("button", { name: /第二张/ });
    expect(selected).toHaveClass("active");
    expect(selected).toBeDisabled();
  });

  it("renders submitted approvals readonly", () => {
    render(
      <ApprovalControl
        config={{ control_id: "ui.interaction.approval.v1", variant: "default", mode: "readonly" }}
        node={{
          node_execution_id: "exec-approval",
          node_id: "approve",
          node_ref: "system.user_approval.v1",
          status: "succeeded",
          output_snapshot: { approved: true, decision: "approved", comment: "looks good" },
        }}
      />,
    );

    expect(screen.getByLabelText("确认意见")).toHaveValue("looks good");
    expect(screen.getByLabelText("确认意见")).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "同意并继续" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "拒绝" })).toBeDisabled();
  });

  it("renders enum fields as a short option group or a long dropdown with field guidance", async () => {
    const onSubmit = vi.fn();
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["resolution"],
      properties: {
        aspectRatio: {
          type: "string",
          enum: ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"],
        },
        resolution: {
          type: "string",
          enum: ["1k", "2k", "4k"],
        },
        prompt: {
          type: "string",
        },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-input",
      node_id: "collect_user_input",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema, title: "图片参数" },
    };

    render(
      <SchemaFormControl
        config={{ control_id: "ui.input.schema_form.v1", variant: "default", mode: "input" }}
        node={inputNode}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByLabelText("画面比例")).toHaveDisplayValue("请选择画面比例");
    expect(screen.getByTitle(/可选值：1:1、16:9/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "清晰度 *" })).toHaveAttribute("title", expect.stringContaining("可选值：1k、2k、4k"));
    await userEvent.click(screen.getByRole("radio", { name: "2k" }));
    await userEvent.type(screen.getByLabelText("提示词"), "一张海报");
    await userEvent.selectOptions(screen.getByLabelText("画面比例"), "16:9");
    await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));

    expect(onSubmit).toHaveBeenCalledWith({
      aspectRatio: "16:9",
      resolution: "2k",
      prompt: "一张海报",
    });
  });
});
