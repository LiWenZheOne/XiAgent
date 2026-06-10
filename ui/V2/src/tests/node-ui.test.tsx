import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApprovalControl } from "../node-ui/controls/ApprovalControl";
import { AssetImageCardsControl } from "../node-ui/controls/AssetImageCardsControl";
import { AssetPickerDialog } from "../node-ui/controls/AssetPickerDialog";
import { AssetSummaryTableControl } from "../node-ui/controls/AssetSummaryTableControl";
import { AssetTaskSummaryControl } from "../node-ui/controls/AssetTaskSummaryControl";
import { ControlLibraryPage } from "../node-ui/ControlLibraryPage";
import { EpisodeContextControl } from "../node-ui/controls/EpisodeContextControl";
import { ImageChoiceThreeControl } from "../node-ui/controls/ImageChoiceThreeControl";
import { SchemaFormControl } from "../node-ui/controls/SchemaFormControl";
import { ScriptTextInputControl } from "../node-ui/controls/ScriptTextInputControl";
import { StoryboardPanelCardsControl } from "../node-ui/controls/StoryboardPanelCardsControl";
import { ValueDisplayControl } from "../node-ui/controls/ValueDisplayControl";
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

describe("ValueDisplayControl", () => {
  it("renders mixed prompt results as structured text instead of broken image output", () => {
    render(
      <ValueDisplayControl
        config={{ control_id: "ui.display.value.v1", variant: "default", mode: "readonly" }}
        imageAltPrefix="生成角色图像提示词 输出图片"
        node={{
          node_execution_id: "exec-prompt",
          node_id: "generate_prompt",
          node_ref: "ai.deepseek_structured_json.v1",
          status: "succeeded",
          output_snapshot: {
            prompt_results: [
              {
                full_name: "林冲",
                think: "只保留囚服和毡笠等稳定造型。",
                prompt: "请将图中角色的官服改成囚服，头戴旧毡笠，保持风格和其它特征不变",
                reference_image_ref: { kind: "data_uri", data: "data:image/png;base64,cmVmLWxpbmNob25n", role: "reference" },
              },
            ],
          },
        }}
        value={{
          prompt_results: [
            {
              full_name: "林冲",
              think: "只保留囚服和毡笠等稳定造型。",
              prompt: "请将图中角色的官服改成囚服，头戴旧毡笠，保持风格和其它特征不变",
              reference_image_ref: { kind: "data_uri", data: "data:image/png;base64,cmVmLWxpbmNob25n", role: "reference" },
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("提示词结果")).toBeInTheDocument();
    expect(screen.getAllByText("林冲").length).toBeGreaterThan(0);
    expect(screen.getByText(/请将图中角色的官服改成囚服/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /生成角色图像提示词 输出图片/ })).not.toBeInTheDocument();
  });

  it("still renders pure image URL fields as images", () => {
    render(
      <ValueDisplayControl
        config={{ control_id: "ui.display.value.v1", variant: "default", mode: "readonly" }}
        imageAltPrefix="准备提示词 输出图片"
        node={{
          node_execution_id: "exec-image",
          node_id: "prepare_prompt",
          node_ref: "tool.echo.v1",
          status: "succeeded",
          output_snapshot: {
            image_urls: ["https://cdn.example.com/a.png"],
          },
        }}
        value={{
          image_urls: ["https://cdn.example.com/a.png"],
        }}
      />,
    );

    expect(screen.getByRole("img", { name: "准备提示词 输出图片 1" })).toHaveAttribute("src", "https://cdn.example.com/a.png");
  });

  it("shows LLM prompt text in AI node inputs", () => {
    render(
      <ValueDisplayControl
        config={{ control_id: "ui.display.value.v1", variant: "default", mode: "readonly" }}
        node={{
          node_execution_id: "exec-llm",
          node_id: "match_variants",
          node_ref: "ai.parallel_deepseek_structured_json.v1",
          status: "succeeded",
          input_snapshot: {
            system: "仅返回合法 JSON。",
            prompt_template: "请为以下角色匹配变体。\n\n角色信息：{item}",
            items: [{ full_name: "林冲", accessories: ["毡笠"] }],
          },
        }}
        slot="input"
        value={{
          system: "仅返回合法 JSON。",
          prompt_template: "请为以下角色匹配变体。\n\n角色信息：{item}",
          items: [{ full_name: "林冲", accessories: ["毡笠"] }],
        }}
      />,
    );

    const promptPanel = screen.getByLabelText("LLM 提示词");
    expect(promptPanel).toBeInTheDocument();
    expect(within(promptPanel).getByText("Prompt Template")).toBeInTheDocument();
    expect(within(promptPanel).getByText("实际提示词 1")).toBeInTheDocument();
    expect(within(promptPanel).getAllByText(/请为以下角色匹配变体/).length).toBeGreaterThanOrEqual(2);
    expect(within(promptPanel).getByText(/"full_name":"林冲"/)).toBeInTheDocument();
  });

  it("renders fully substituted prompt templates for parallel AI node inputs", () => {
    const promptTemplate = [
      "段落：{paragraph_text}",
      "世界背景：{world_background}",
      "完整剧本：{shared_context.full_script}",
      "规则：{material_rule}",
      "场景：{scene_layout.location_summary}",
      "场景布局：{scene_layout}",
      "分格计划：{panel_plan}",
      "完整项：{item}",
    ].join("\n");
    const item = {
      paragraph_text: "林冲踏雪进入山神庙。",
      scene_layout: { location_summary: "雪夜破庙" },
      panel_plan: { panel_count: 1, panels: [{ index: 1, shot: "远景" }] },
      shared_context: {
        world_background: "水浒传雪夜情节。",
        full_script: "完整剧本内容。",
        prompt_rules: { material_rule: "不写现代材质。" },
      },
    };

    render(
      <ValueDisplayControl
        config={{ control_id: "ui.display.value.v1", variant: "default", mode: "readonly" }}
        node={{
          node_execution_id: "exec-llm-fields",
          node_id: "analyze_scene_layout",
          node_ref: "ai.parallel_deepseek_structured_json.v1",
          status: "succeeded",
          input_snapshot: { prompt_template: promptTemplate, items: [item] },
        }}
        slot="input"
        value={{ prompt_template: promptTemplate, items: [item] }}
      />,
    );

    const actualPrompt = within(screen.getByLabelText("LLM 提示词")).getByText(/段落：林冲踏雪进入山神庙/);
    expect(actualPrompt).toHaveTextContent("世界背景：水浒传雪夜情节。");
    expect(actualPrompt).toHaveTextContent("完整剧本：完整剧本内容。");
    expect(actualPrompt).toHaveTextContent("规则：不写现代材质。");
    expect(actualPrompt).toHaveTextContent("场景：雪夜破庙");
    expect(actualPrompt).toHaveTextContent('"location_summary":"雪夜破庙"');
    expect(actualPrompt).toHaveTextContent('"panel_count":1');
    expect(actualPrompt).not.toHaveTextContent("{paragraph_text}");
    expect(actualPrompt).not.toHaveTextContent("{world_background}");
    expect(actualPrompt).not.toHaveTextContent("{material_rule}");
    expect(actualPrompt).not.toHaveTextContent("{scene_layout}");
    expect(actualPrompt).not.toHaveTextContent("{panel_plan}");
  });

  it("does not show the LLM prompt panel for non-AI nodes", () => {
    render(
      <ValueDisplayControl
        config={{ control_id: "ui.display.value.v1", variant: "default", mode: "readonly" }}
        node={{
          node_execution_id: "exec-tool",
          node_id: "echo",
          node_ref: "tool.echo.v1",
          status: "succeeded",
          input_snapshot: { prompt: "只是普通工具输入" },
        }}
        slot="input"
        value={{ prompt: "只是普通工具输入" }}
      />,
    );

    expect(screen.queryByLabelText("LLM 提示词")).not.toBeInTheDocument();
    expect(screen.getByText("只是普通工具输入")).toBeInTheDocument();
  });
});

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
    control_id: "ui.interaction.asset_image_cards.v1",
    version: "1.0.0",
    name: "Asset Image Cards",
    kind: "interaction",
    tags: ["asset", "image", "cards", "upload"],
    variants: [{ name: "grouped_cards", label: "按资产类型分组的补图卡片", tags: [], modes: ["interactive", "readonly"], required_bindings: [] }],
    description: "按资产类型分组的补图卡片。",
  },
  {
    control_id: "ui.interaction.storyboard_panel_cards.v1",
    version: "1.0.0",
    name: "Storyboard Panel Cards",
    kind: "interaction",
    tags: ["storyboard", "panel", "image", "cards"],
    variants: [{ name: "panel_review", label: "分镜汇总卡片", tags: [], modes: ["interactive", "readonly"], required_bindings: [] }],
    description: "S8 分镜汇总控件。",
  },
  {
    control_id: "ui.interaction.asset_summary_table.v1",
    version: "1.0.0",
    name: "Asset Summary Table",
    kind: "interaction",
    tags: ["asset", "summary", "table", "upload"],
    variants: [{ name: "tabbed_table", label: "资产汇总列表", tags: [], modes: ["interactive", "readonly"], required_bindings: [] }],
    description: "P3 资产列表汇总控件。",
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
    control_id: "ui.input.script_text.v1",
    version: "1.0.0",
    name: "Script Text Input",
    kind: "input",
    tags: ["script", "text", "upload"],
    variants: [{ name: "default", label: "剧本文本输入", tags: [], modes: ["input", "readonly"], required_bindings: [] }],
    description: "用于剧本输入节点。",
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
    control_id: "ui.input.asset_picker.v1",
    version: "1.0.0",
    name: "Asset Picker",
    kind: "input",
    tags: ["asset", "picker"],
    variants: [{ name: "list", label: "资产列表选择", tags: [], modes: ["input", "readonly"], required_bindings: [] }],
    description: "从资产库选择资产。",
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

  it("preselects name and variant filters for an existing matched asset", async () => {
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:luzhishen"), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/assets/search")) {
        return jsonResponse({
          items: [{
            asset_id: "asset-luzhishen",
            asset_type: "file",
            name: "角色_鲁智深_僧衣_禅杖",
            scope: "project",
            mime_type: "image/png",
            size_bytes: 128,
            metadata: { public_url: "https://assets.local.invalid/assets/luzhishen.png" },
            created_at: "2026-05-27T10:00:00Z",
          }],
        });
      }
      if (url === "/api/assets/asset-luzhishen/tags") {
        return jsonResponse({ items: [] });
      }
      if (url === "/api/assets/asset-luzhishen/content" || url.startsWith("/api/assets/asset-luzhishen/content?") || url.startsWith("/api/assets/asset-luzhishen/thumbnail?")) {
        return Promise.resolve(new Response(new Blob(["fake"], { type: "image/png" }), {
          status: 200,
          headers: { "Content-Type": "image/png" },
        }));
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AssetPickerDialog
        assetLabel="角色"
        initialAssetId="asset-luzhishen"
        initialAssetName="角色_错误_默认"
        tagName="角色"
        targetName="鲁智深"
        onClose={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(await screen.findByRole("dialog", { name: "选择匹配资产" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "选择名称 鲁智深" })).toHaveClass("active"));
    expect(screen.getByRole("button", { name: "选择变体 僧衣" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "选择资产 角色_鲁智深_僧衣_禅杖" })).toBeInTheDocument();
  });

  it("preselects the target name when the matched asset name is unavailable", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/assets/search")) {
        return jsonResponse({
          items: [{
            asset_id: "asset-chaogai",
            asset_type: "file",
            name: "角色_晁盖_庄主服",
            scope: "project",
            mime_type: "image/png",
            size_bytes: 128,
            metadata: { public_url: "https://cdn.example.com/chaogai.png" },
            created_at: "2026-05-27T10:00:00Z",
          }],
        });
      }
      if (url === "/api/assets/asset-chaogai/tags") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AssetPickerDialog
        assetLabel="角色"
        tagName="角色"
        targetName="晁盖"
        onClose={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(await screen.findByRole("dialog", { name: "选择匹配资产" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "选择名称 晁盖" })).toHaveClass("active"));
  });

  it("shows the upload placeholder when an asset image preview cannot load", async () => {
    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-broken-preview",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            characters: [{ asset_type: "character", asset_name: "林冲", asset_tags: ["囚服"] }],
            prompt_results: [{ asset_type: "character", asset_name: "林冲", asset_tags: ["囚服"], prompt: "囚服" }],
            asset_images: [
              {
                asset_type: "character",
                asset_key: "林冲",
                asset_name: "林冲",
                asset_tags: ["囚服"],
                image_url: "https://cdn.example.com/missing-linchong.png",
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.error(screen.getByRole("img"));

    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());
    expect(screen.getByLabelText("林冲 选择图像")).toHaveTextContent("点击选择");
    expect(screen.getByLabelText("林冲 选择图像")).toHaveTextContent("拖拽上传");
  });

  it("does not treat reference image asset ids as linked assets", () => {
    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-internal-id-link",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            characters: [
              {
                asset_type: "character",
                asset_name: "众公差",
                asset_tags: ["公差皂衣"],
                reference_image_ref: { kind: "asset", asset_id: "asset_0382ca8350d344cc841870ea12345678", role: "reference" },
              },
            ],
            prompt_results: [
              {
                asset_type: "character",
                asset_name: "众公差",
                asset_tags: ["公差皂衣"],
                prompt: "公差皂衣",
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getAllByText("无资产关联").length).toBeGreaterThan(0);
    expect(screen.queryByText("已关联资产")).not.toBeInTheDocument();
    expect(screen.queryByText(/asset_0382ca8350d344cc841870ea/)).not.toBeInTheDocument();
  });

  it("fills the asset prompt from the selected pool image prompt", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ items: [] })));

    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-asset-pool-prompt",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            characters: [{ asset_type: "character", asset_name: "林冲", asset_tags: ["囚服"] }],
            prompt_results: [
              { asset_type: "character", asset_name: "林冲", asset_tags: ["囚服"], prompt: "第一条预生成提示词" },
              { asset_type: "character", asset_name: "林冲_2", asset_tags: ["囚服"], prompt: "第二条预生成提示词" },
            ],
            generated_images: [
              {
                asset_key: "character:林冲:囚服",
                asset_type: "character",
                asset_name: "林冲",
                asset_tags: ["囚服"],
                image_url: "https://cdn.example.com/linchong-1.png",
                prompt_index: 0,
              },
              {
                asset_key: "character:林冲:囚服",
                asset_type: "character",
                asset_name: "林冲",
                asset_tags: ["囚服"],
                image_url: "https://cdn.example.com/linchong-2.png",
                prompt_index: 1,
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("img", { name: "角色_林冲_囚服 图像池 2" }).closest("button") as HTMLButtonElement);

    await waitFor(() => expect(screen.getByLabelText("资产提示词")).toHaveValue("第二条预生成提示词"));
  });

  it("uses the current asset prompt for single-card regeneration", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/generate-image") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        expect(body.prompt_result.prompt).toBe("当前提示词框内容");
        return jsonResponse({ generation_id: "asset-generation-current-prompt", status: "queued" });
      }
      if (url === "/api/assets/generate-image/asset-generation-current-prompt") {
        return jsonResponse({
          generation_id: "asset-generation-current-prompt",
          status: "succeeded",
          result: {
            image_url: "https://cdn.example.com/linchong-current.png",
            source: "ai_generated",
          },
        });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-asset-single-regenerate",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            characters: [{ asset_type: "character", asset_name: "林冲", asset_tags: ["囚服"] }],
            prompt_results: [{ asset_type: "character", asset_name: "林冲", asset_tags: ["囚服"], prompt: "原始提示词" }],
            prompts_per_item: 3,
            images_per_prompt: 2,
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("资产提示词"), { target: { value: "当前提示词框内容" } });
    fireEvent.click(screen.getByRole("button", { name: "生成" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/assets/generate-image",
      expect.objectContaining({ method: "POST" }),
    ));
    const postCalls = fetchMock.mock.calls.filter(([url, init]) => String(url) === "/api/assets/generate-image" && init?.method === "POST");
    expect(postCalls).toHaveLength(1);
  });

  it("uses the default reference template for unlinked asset cards with stale reference refs", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/assets/search")) {
        return jsonResponse({
          items: [{
            asset_id: "asset-default-character",
            asset_type: "file",
            name: "塞雷2d角色模板",
            scope: "project",
            mime_type: "image/png",
            size_bytes: 128,
            metadata: { public_url: "https://cdn.example.com/default-character.png" },
            created_at: "2026-05-27T10:00:00Z",
          }],
        });
      }
      if (url === "/api/assets/asset-default-character/tags" || url.startsWith("/api/assets/tags")) {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{
          control_id: "ui.interaction.asset_image_cards.v1",
          variant: "grouped_cards",
          mode: "interactive",
          options: { default_reference_templates: { character: "塞雷2d角色模板" } },
        }}
        node={{
          node_execution_id: "exec-default-template-stale-ref",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            characters: [
              {
                asset_type: "character",
                asset_name: "梁山泊头领",
                asset_tags: ["头巾"],
                reference_image_ref: { kind: "asset", asset_id: "asset-stale-reference", role: "reference" },
              },
            ],
            prompt_results: [
              {
                asset_type: "character",
                asset_name: "梁山泊头领",
                asset_tags: ["头巾"],
                prompt: "头巾短打",
                reference_image_ref: { kind: "asset", asset_id: "asset-stale-reference", role: "reference" },
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    expect(await screen.findByText("塞雷2d角色模板")).toBeInTheDocument();
  });

  it("renders matched asset cards, generates images locally, and submits after confirmation", async () => {
    const onSubmit = vi.fn();
    const onDraft = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:luzhishen"), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    let includeExistingNameTag = false;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/tags" && init?.method === "POST") {
        const body = JSON.parse(String(init.body ?? "{}")) as { name: string };
        if (body.name === "林冲") {
          includeExistingNameTag = true;
          return jsonResponse({ error: { code: "asset_tag_name_conflict", message: "同一资产库中已存在同名标签。" } }, 409);
        }
        return jsonResponse({ tag_id: `tag-${body.name}`, name: body.name, scope: "project", project_id: "project-1", asset_count: 0 });
      }
      if (url.startsWith("/api/assets/tags")) {
        return jsonResponse({
          items: [
            { tag_id: "tag-character", name: "角色", scope: "project", project_id: "project-1", asset_count: 1 },
            includeExistingNameTag ? { tag_id: "tag-linchong", name: "林冲", scope: "project", project_id: "project-1", asset_count: 1 } : null,
            { tag_id: "tag-location", name: "地点", scope: "project", project_id: "project-1", asset_count: 1 },
            { tag_id: "tag-prop", name: "道具", scope: "project", project_id: "project-1", asset_count: 0 },
          ].filter(Boolean),
        });
      }
      if (url.startsWith("/api/assets/search")) {
        const called = new URL(url, "http://localhost");
        expect(["combined", "project"]).toContain(called.searchParams.get("scope"));
        expect(called.searchParams.get("project_id")).toBe("project-1");
        const tagNames = called.searchParams.get("tag_names") ?? "";
        const includeCharacters = tagNames.includes("角色");
        const includeLocations = tagNames.includes("地点");
        return jsonResponse({
          items: [
            includeCharacters ? {
              asset_id: "asset-luzhishen",
              asset_type: "file",
              name: "角色_鲁智深_僧衣",
              scope: "project",
              project_id: "project-1",
              mime_type: "image/png",
              size_bytes: 128,
              storage_uri: "assets/luzhishen.png",
              metadata: { public_url: "https://assets.local.invalid/assets/luzhishen.png" },
              created_at: "2026-05-27T10:00:00Z",
            } : null,
            includeLocations ? {
              asset_id: "asset-yazhulin",
              asset_type: "text",
              name: "野猪林",
              scope: "project",
              project_id: "project-1",
              mime_type: null,
              size_bytes: null,
              metadata: {},
              created_at: "2026-05-27T10:00:00Z",
            } : null,
          ].filter(Boolean),
        });
      }
      if (url === "/api/assets/asset-luzhishen/tags") {
        return jsonResponse({
          items: [
            { tag_id: "tag-character", name: "角色", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-luzhishen", name: "鲁智深", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-monk-robe", name: "僧衣", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-staff", name: "禅杖", scope: "project", project_id: "global", asset_count: 1 },
          ],
        });
      }
      if (url === "/api/assets/asset-luzhishen/content" || url.startsWith("/api/assets/asset-luzhishen/content?") || url.startsWith("/api/assets/asset-luzhishen/thumbnail?")) {
        return Promise.resolve(new Response(new Blob(["fake"], { type: "image/png" }), {
          status: 200,
          headers: { "Content-Type": "image/png" },
        }));
      }
      if (url === "/api/assets/generate-image") {
        return jsonResponse({
          generation_id: "image-generation-linchong",
          status: "queued",
        });
      }
      if (url === "/api/assets/generate-image/image-generation-linchong") {
        return jsonResponse({
          generation_id: "image-generation-linchong",
          status: "succeeded",
          result: {
            full_name: "林冲",
            image_url: "https://cdn.example.com/generated-linchong.png",
            source: "ai_generated",
            runninghub_task_id: "rh-1",
            generation_summary: { total_asset_count: 2 },
          },
        });
      }
      return jsonResponse({
        asset_id: "asset-upload-linchong",
        name: "林冲_图像",
        asset_type: "file",
        scope: "project",
        metadata: { public_url: "https://cdn.example.com/linchong.png" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const cardNode: TaskNodeExecution = {
      node_execution_id: "exec-card",
      node_id: "upload_images",
      node_ref: "system.human_approval.v1",
      status: "waiting",
      input_snapshot: {
        characters: [
          {
            asset_type: "character",
            asset_name: "林冲",
            asset_tags: ["默认"],
            aliases: ["林教头"],
            summary: "八十万禁军教头，武艺高强。",
            character_status: "被发配沧州途中，身着囚服，面带风霜。",
          },
          {
            asset_type: "character",
            asset_name: "鲁智深",
            asset_tags: ["僧衣", "禅杖"],
            aliases: ["花和尚"],
            summary: "梁山好汉。",
            character_status: "身穿僧衣。",
          },
        ],
        enriched_characters: [
          { asset_type: "character", asset_name: "林冲", matched: true, matched_asset_name: "林冲_默认" },
          { asset_type: "character", asset_name: "鲁智深", matched: false },
        ],
        variant_results: [
          { asset_type: "character", asset_name: "林冲", asset_tags: ["默认"] },
          { asset_type: "character", asset_name: "鲁智深", asset_tags: ["僧衣"] },
        ],
        accessory_results: [
          { asset_type: "character", asset_name: "林冲", asset_tags: [], reason: "无配件" },
          { asset_type: "character", asset_name: "鲁智深", asset_tags: ["僧衣", "禅杖"] },
        ],
        prompt_results: [
          { asset_type: "character", asset_name: "林冲", asset_tags: ["默认"], prompt: "囚服", reference_image_ref: { kind: "asset", asset_id: "asset-linchong", role: "reference" } },
          { asset_type: "character", asset_name: "鲁智深", asset_tags: ["僧衣"], prompt: "僧衣", reference_image_ref: { kind: "asset", asset_id: "asset-luzhishen", role: "reference" } },
          { asset_type: "prop", asset_name: "水火棍", prompt: "生成水火棍道具图", reference_image_ref: { kind: "asset", asset_id: "asset-prop", role: "reference" } },
        ],
        approved_assets: {
          props: [
            {
              name: "水火棍",
              matched: true,
              matched_asset_name: "水火棍旧图",
              matched_asset_ref: { kind: "asset", asset_id: "asset-prop", role: "reference" },
            },
          ],
        },
      },
    };

    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={cardNode}
        onDraft={onDraft}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByRole("tab", { name: /角色/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /道具/ })).toBeInTheDocument();
    expect(screen.getAllByText("资产名称").length).toBeGreaterThan(0);
    expect(screen.getAllByText("标签").length).toBeGreaterThan(0);
    expect(screen.queryByText("主体")).not.toBeInTheDocument();
    expect(screen.queryByText("配件")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("林冲")).toBeInTheDocument();
    expect(screen.getByDisplayValue("默认")).toBeInTheDocument();
    expect(screen.getByDisplayValue("囚服")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "关联资产" }).length).toBeGreaterThan(0);
    expect(screen.getByText("角色_林冲_默认")).toBeInTheDocument();
    expect(screen.getByDisplayValue("鲁智深")).toBeInTheDocument();
    expect(screen.queryByText("已匹配")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("僧衣")).toBeInTheDocument();
    const missingMatchButtons = screen.getAllByRole("button", { name: "关联资产" });
    await userEvent.click(missingMatchButtons[1]);
    expect(await screen.findByRole("dialog", { name: "选择匹配资产" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择名称 鲁智深" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择变体 僧衣" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择资产 角色_鲁智深_僧衣" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("img", { name: "角色_鲁智深_僧衣 图像" })).toHaveAttribute("src", "blob:luzhishen"));
    expect(screen.queryByRole("button", { name: /野猪林/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "选择资产 角色_鲁智深_僧衣" }));
    expect(screen.getAllByText("角色_鲁智深_僧衣").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("tab", { name: /道具/ }));
    expect(screen.queryByText("水火棍")).not.toBeInTheDocument();
    expect(screen.getByText("暂无道具资产。")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "查看参考图" })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("生成水火棍道具图")).not.toBeInTheDocument();

    expect(screen.queryByLabelText("林冲 图片地址")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /角色/ }));
    const firstPrompt = screen.getByDisplayValue("囚服");
    await userEvent.clear(firstPrompt);
    await userEvent.type(firstPrompt, "修改后的囚服提示词");
    const file = new File(["fake"], "linchong.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText("林冲 选择图像"), file);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/assets/files", expect.objectContaining({ method: "POST" })));
    await userEvent.click(screen.getAllByRole("button", { name: "重新生成" })[0]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/assets/generate-image",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(onSubmit).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("img", { name: "林冲 图像" })).toHaveAttribute("src", "https://cdn.example.com/generated-linchong.png"));
    expect(onDraft).toHaveBeenCalledWith(expect.objectContaining({
      decision: "generate_missing",
          asset_images: expect.arrayContaining([
            expect.objectContaining({
              asset_type: "character",
              asset_name: "林冲",
              image_url: "https://cdn.example.com/generated-linchong.png",
              source: "ai_generated",
            }),
      ]),
    }));
    const latestDraftPayload = onDraft.mock.calls[onDraft.mock.calls.length - 1]?.[0] as Record<string, unknown>;
    expect(JSON.stringify(latestDraftPayload.asset_images)).not.toContain("generation_summary");
    const clickMock = vi.fn();
    const appendMock = vi.spyOn(document.body, "appendChild");
    const removeMock = vi.fn();
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const element = document.createElementNS("http://www.w3.org/1999/xhtml", tagName) as HTMLAnchorElement;
      if (tagName === "a") {
        element.click = clickMock;
        element.remove = removeMock;
      }
      return element;
    });
    await userEvent.click(screen.getByRole("button", { name: "下载角色_林冲_默认图像" }));
    expect(clickMock).toHaveBeenCalled();
    expect(appendMock).toHaveBeenCalled();
    createElementSpy.mockRestore();
    appendMock.mockRestore();

    await userEvent.click(screen.getByRole("button", { name: "一键入库" }));
    expect(await screen.findByRole("dialog", { name: "缺少资产图像" })).toBeInTheDocument();
    expect(screen.getByText("还有资产没有图像")).toBeInTheDocument();
    expect(screen.getAllByText("角色_鲁智深_僧衣_禅杖").length).toBeGreaterThan(1);
    expect(screen.getByRole("button", { name: "跳过未补图并入库" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "返回" }));
    expect(screen.queryByRole("dialog", { name: "缺少资产图像" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "资产生成" }));
    await waitFor(() => expect(screen.getByRole("img", { name: "鲁智深 图像" })).toHaveAttribute("src", "https://cdn.example.com/generated-linchong.png"));
    const luzhishenName = screen.getByDisplayValue("鲁智深");
    await userEvent.clear(luzhishenName);
    await userEvent.type(luzhishenName, "鲁智深新图");
    expect(screen.queryByRole("button", { name: "确认并继续" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "一键入库" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      decision: "finish",
      created_asset_ids: expect.arrayContaining(["asset-upload-linchong"]),
      asset_images: expect.arrayContaining([
        expect.objectContaining({
          asset_type: "character",
          asset_name: "林冲",
          image_url: "https://cdn.example.com/generated-linchong.png",
          source: "library",
          runninghub_task_id: "rh-1",
        }),
      ]),
      prompt_results: expect.arrayContaining([
        expect.objectContaining({
          asset_type: "character",
          asset_name: "林冲",
          prompt: "修改后的囚服提示词",
        }),
      ]),
    })));
    const latestSubmitPayload = onSubmit.mock.calls[onSubmit.mock.calls.length - 1]?.[0] as Record<string, unknown>;
    expect(JSON.stringify(latestSubmitPayload.asset_images)).not.toContain("generation_summary");
    const libraryUploadForms = fetchMock.mock.calls
      .filter(([url, init]) => url === "/api/assets/files" && init?.method === "POST")
      .map(([, init]) => init?.body as FormData)
      .filter((form) => typeof form.get("metadata_json") === "string");
    expect(libraryUploadForms.length).toBeGreaterThan(0);
    expect(String(libraryUploadForms[0].get("metadata_json"))).toContain("asset_catalog_workflow");
    expect(String(libraryUploadForms[0].get("metadata_json"))).toContain("\"asset_name\":\"林冲\"");
    expect(String(libraryUploadForms[0].get("metadata_json"))).toContain("\"asset_tags\":[\"默认\"]");
    expect(String(libraryUploadForms[0].get("metadata_json"))).not.toContain("\"tags\"");
    expect(String(libraryUploadForms[0].get("tag_ids"))).toContain("tag-character");
    expect(String(libraryUploadForms[0].get("tag_ids"))).toContain("tag-linchong");
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/assets/text")).toBe(false);
  });

  it("can remove an asset image card from the current generation and submit scope", async () => {
    const onDraft = vi.fn();
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ items: [] })));

    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-remove-asset-card",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            characters: [
              { asset_type: "character", asset_name: "甲", asset_tags: ["默认"] },
              { asset_type: "character", asset_name: "乙", asset_tags: ["默认"] },
            ],
            prompt_results: [
              { asset_type: "character", asset_name: "甲", asset_tags: ["默认"], prompt: "甲提示词" },
              { asset_type: "character", asset_name: "乙", asset_tags: ["默认"], prompt: "乙提示词" },
            ],
          },
        }}
        onDraft={onDraft}
        onSubmit={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "移出角色_甲_默认本次生成" }));

    expect(screen.queryByDisplayValue("甲")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("乙")).toBeInTheDocument();
    await waitFor(() => expect(onDraft).toHaveBeenCalledWith(expect.objectContaining({
      skipped_asset_keys: ["character:甲:默认"],
      skipped_asset_count: 1,
      prompt_results: [
        expect.objectContaining({ asset_name: "乙", prompt: "乙提示词" }),
      ],
    })));
    const latestDraftPayload = onDraft.mock.calls[onDraft.mock.calls.length - 1]?.[0] as Record<string, unknown>;
    expect(JSON.stringify(latestDraftPayload.prompt_results)).not.toContain("甲提示词");
  });

  it("can continue without saving images when missing asset images are skipped at import time", async () => {
    const onSubmit = vi.fn();
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ items: [] })));

    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-skip-missing-images",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            characters: [
              { asset_type: "character", asset_name: "甲", asset_tags: ["默认"] },
              { asset_type: "character", asset_name: "乙", asset_tags: ["默认"] },
            ],
            prompt_results: [
              { asset_type: "character", asset_name: "甲", asset_tags: ["默认"], prompt: "甲提示词" },
              { asset_type: "character", asset_name: "乙", asset_tags: ["默认"], prompt: "乙提示词" },
            ],
          },
        }}
        onSubmit={onSubmit}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "一键入库" }));
    expect(await screen.findByRole("dialog", { name: "缺少资产图像" })).toBeInTheDocument();
    expect(screen.getAllByText("角色_甲_默认").length).toBeGreaterThan(1);
    expect(screen.getAllByText("角色_乙_默认").length).toBeGreaterThan(1);
    await userEvent.click(screen.getByRole("button", { name: "跳过未补图并入库" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      decision: "finish",
      asset_images: [],
      prompt_results: expect.arrayContaining([
        expect.objectContaining({ asset_name: "甲", prompt: "甲提示词" }),
        expect.objectContaining({ asset_name: "乙", prompt: "乙提示词" }),
      ]),
    })));
  });

  it("renders storyboard panel cards and submits edited panel results", async () => {
    const onSubmit = vi.fn();
    let thumbnailIndex = 0;
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => `blob:storyboard-thumb-${thumbnailIndex++}`), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/thumbnail?")) {
        return Promise.resolve(new Response(new Blob(["thumb"], { type: "image/png" })));
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                description: "林冲踏雪前行。",
                prompt: "分镜描述\n林冲踏雪前行。",
                reference_images: [
                  {
                    label: "林冲",
                    asset_type: "character",
                    asset_name: "林冲",
                    asset_tags: ["囚服"],
                    image_ref: { kind: "asset", asset_id: "asset-linchong-ref", role: "reference" },
                    source: "asset",
                  },
                ],
                generated_images: [{ image_url: "https://cdn.example.com/storyboard-0.png", source: "ai_generated", asset_id: "asset-storyboard-0" }],
                selected_image_url: "https://cdn.example.com/storyboard-0.png",
                aspect_ratio: "16:9",
                resolution: "2K",
              },
            ],
          },
        }}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByRole("heading", { name: "雪夜" })).toBeInTheDocument();
    expect(screen.getByLabelText("参考图像池")).toBeInTheDocument();
    expect(screen.getByLabelText("生成图像池")).toBeInTheDocument();
    expect(screen.getByText("已定稿")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "一键生成分镜" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新生成提示词" })).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/assets/asset-linchong-ref/thumbnail?size=256&project_id=project-1", expect.any(Object));
      expect(fetchMock).toHaveBeenCalledWith("/api/assets/asset-storyboard-0/thumbnail?size=256&project_id=project-1", expect.any(Object));
    });
    expect(screen.getByRole("img", { name: "生成图 1" })).toHaveAttribute("src", expect.stringMatching(/^(blob:storyboard-thumb-|https:\/\/cdn\.example\.com\/storyboard-0\.png)/));
    await userEvent.click(screen.getByRole("button", { name: "全屏查看生成图 1" }));
    expect(screen.getByRole("dialog", { name: "全屏查看 雪夜 分格 1 生成图 1" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(screen.getByText("资产")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("分段提示词"));
    await userEvent.type(screen.getByLabelText("分段提示词"), "新的分镜提示词");
    await userEvent.click(screen.getByRole("button", { name: "完成并继续" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      decision: "finish",
      panel_results: [
        expect.objectContaining({
          card_id: "segment-0",
          prompt: "新的分镜提示词",
          selected_image_url: "https://cdn.example.com/storyboard-0.png",
          generated_images: [
            expect.objectContaining({
              image_url: "https://cdn.example.com/storyboard-0.png",
              source: "ai_generated",
              asset_id: "asset-storyboard-0",
            }),
          ],
          reference_images: [
            expect.objectContaining({
              label: "林冲",
              asset_type: "character",
              asset_name: "林冲",
              image_ref: expect.objectContaining({ kind: "asset", asset_id: "asset-linchong-ref", role: "reference" }),
            }),
          ],
        }),
      ],
    }));
  });

  it("blocks storyboard panel submission until every card has a selected image", async () => {
    const onSubmit = vi.fn();
    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel-missing",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                description: "林冲踏雪前行。",
                prompt: "分镜描述\n林冲踏雪前行。",
                reference_images: [
                  {
                    label: "林冲",
                    asset_type: "character",
                    asset_name: "林冲",
                    image_ref: { kind: "data_uri", data: "data:image/png;base64,cmVm", role: "reference" },
                    source: "asset",
                  },
                ],
                aspect_ratio: "16:9",
                resolution: "2K",
              },
            ],
          },
        }}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByText("待生成")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "完成并继续" }));

    expect(screen.getByRole("dialog", { name: "缺少分镜图像" })).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("uses the edited panel count when regenerating storyboard prompts", async () => {
    const promptRequests: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/storyboard-panel-prompt") {
        promptRequests.push(JSON.parse(String(init?.body ?? "{}")));
        return jsonResponse({
          card: {
            card_id: "segment-0",
            segment_index: 0,
            panel_index: 0,
            segment_title: "雪夜",
            prompt: "三格新版提示词",
            reference_images: [],
            generated_images: [],
            selected_image_url: "",
            aspect_ratio: "16:9",
            resolution: "2K",
          },
          segment_description: { panel_count: "3" },
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel-prompt-count",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                description: "林冲踏雪前行。",
                prompt: "原始提示词",
                panel_count: "2",
                panel_plan: { panel_count: 2, panels: [{ description: "风雪起" }, { description: "人物行" }] },
                reference_images: [
                  {
                    label: "林冲",
                    asset_type: "character",
                    asset_name: "林冲",
                    asset_tags: ["囚服"],
                    image_ref: { kind: "asset", asset_id: "asset-linchong-ref", role: "reference" },
                    source: "asset",
                  },
                ],
                generated_images: [],
                selected_image_url: "",
                aspect_ratio: "16:9",
                resolution: "2K",
                source_item: {
                  index: 0,
                  paragraph_text: "林冲踏雪。",
                  panel_count: "auto",
                },
              },
            ],
            shared_context: { full_script: "完整剧本" },
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    const panelCountInput = screen.getByLabelText("雪夜 分格数量");
    expect(panelCountInput).toHaveValue(2);
    await userEvent.clear(panelCountInput);
    await userEvent.type(panelCountInput, "3");
    await userEvent.click(screen.getByRole("button", { name: "重新生成提示词" }));

    await waitFor(() => expect(screen.getByLabelText("分段提示词")).toHaveValue("三格新版提示词"));
    expect((promptRequests[0].item as Record<string, unknown>).panel_count).toBe("3");
    expect(promptRequests[0].card).toMatchObject({
      reference_images: [
        expect.objectContaining({
          asset_name: "林冲",
          image_ref: { kind: "asset", asset_id: "asset-linchong-ref", role: "reference" },
        }),
      ],
    });
  });

  it("marks storyboard cards that failed during prompt generation", async () => {
    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel-failed",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-1",
                segment_index: 1,
                panel_index: 0,
                segment_title: "失败段",
                description: "提示词生成失败。",
                prompt: "当前段落画面提示词生成失败，请重新生成提示词或手动编辑后再生成分镜图。",
                status: "failed",
                error: "DeepSeek response is not valid JSON",
                reference_images: [],
                aspect_ratio: "16:9",
                resolution: "2K",
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "失败段" })).toBeInTheDocument();
    expect(screen.getByText("生成失败")).toBeInTheDocument();
    expect(screen.getByText("DeepSeek response is not valid JSON")).toBeInTheDocument();
  });

  it("restores storyboard generated images from saved interaction drafts after refresh", async () => {
    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel-draft",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                description: "林冲踏雪前行。",
                prompt: "原始提示词",
                reference_images: [],
                aspect_ratio: "16:9",
                resolution: "2K",
              },
            ],
            panel_results: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                prompt: "已保存提示词",
                reference_images: [],
                selected_image_url: "https://cdn.example.com/storyboard-draft.png",
                generated_images: [{ image_url: "https://cdn.example.com/storyboard-draft.png", source: "ai_generated" }],
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText("已定稿")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "生成图 1" })).toHaveAttribute("src", "https://cdn.example.com/storyboard-draft.png");
    expect(screen.getByLabelText("分段提示词")).toHaveValue("已保存提示词");
  });

  it("fills the storyboard prompt when selecting a generated image", async () => {
    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel-select-prompt",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                description: "林冲踏雪前行。",
                prompt: "当前提示词",
                reference_images: [],
                generated_images: [
                  { image_url: "https://cdn.example.com/storyboard-old.png", source: "ai_generated", prompt: "旧图提示词" },
                  { image_url: "https://cdn.example.com/storyboard-new.png", source: "ai_generated", prompt: "新图提示词" },
                ],
                selected_image_url: "https://cdn.example.com/storyboard-old.png",
                aspect_ratio: "16:9",
                resolution: "2K",
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("img", { name: "生成图 2" }).closest("button") as HTMLButtonElement);

    expect(screen.getByLabelText("分段提示词")).toHaveValue("新图提示词");
    const selectedButtons = screen.getAllByRole("button").filter((button) => button.textContent?.includes("已选定稿"));
    expect(selectedButtons[0].querySelector("img")).toHaveAttribute("src", "https://cdn.example.com/storyboard-new.png");
  });

  it("fills the storyboard prompt from prompt index when generated image prompt is missing", async () => {
    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel-select-indexed-prompt",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                description: "林冲踏雪前行。",
                prompt: "当前提示词",
                panel_count: "2",
                prompt_variants: ["第一条隐藏提示词", "第二条隐藏提示词"],
                reference_images: [],
                generated_images: [
                  { image_url: "https://cdn.example.com/storyboard-old.png", source: "ai_generated", prompt_index: 0, panel_count: "2" },
                  { image_url: "https://cdn.example.com/storyboard-new.png", source: "ai_generated", prompt_index: 1, panel_count: "4" },
                ],
                selected_image_url: "https://cdn.example.com/storyboard-old.png",
                aspect_ratio: "16:9",
                resolution: "2K",
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("img", { name: "生成图 2" }).closest("button") as HTMLButtonElement);

    await waitFor(() => expect(screen.getByLabelText("分段提示词")).toHaveValue("第二条隐藏提示词"));
    expect(screen.getByLabelText("雪夜 分格数量")).toHaveValue(4);
  });

  it("generates storyboard images for each configured hidden prompt in batch mode", async () => {
    const promptRequests: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/storyboard-panel-image") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        promptRequests.push(body.prompt);
        return jsonResponse({ generation_id: `storyboard-generation-${promptRequests.length}`, status: "queued" });
      }
      if (url.startsWith("/api/assets/generate-image/storyboard-generation-")) {
        const generationId = url.split("/").pop() ?? "storyboard-generation-0";
        return jsonResponse({
          generation_id: generationId,
          status: "succeeded",
          result: {
            card_id: "segment-0",
            image_url: `https://cdn.example.com/${generationId}.png`,
            source: "ai_generated",
          },
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel-batch-prompts",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                description: "林冲踏雪前行。",
                prompt: "当前提示词",
                panel_count: "2",
                prompt_variants: ["第一条隐藏提示词", "第二条隐藏提示词"],
                panel_count_variants: ["2", "4"],
                reference_images: [
                  {
                    label: "林冲",
                    asset_type: "character",
                    asset_name: "林冲",
                    image_ref: { kind: "data_uri", data: "data:image/png;base64,cmVm", role: "reference" },
                    source: "asset",
                  },
                ],
                generated_images: [],
                selected_image_url: "",
                aspect_ratio: "16:9",
                resolution: "2K",
                generation_config: { prompts_per_item: 2, images_per_prompt: 2 },
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "一键生成分镜" }));

    await waitFor(() => expect(promptRequests).toHaveLength(4));
    expect(promptRequests).toEqual([
      "第一条隐藏提示词",
      "第一条隐藏提示词",
      "第二条隐藏提示词",
      "第二条隐藏提示词",
    ]);
    expect(await screen.findByText("4 张生成图")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("img", { name: "生成图 3" }).closest("button") as HTMLButtonElement);
    expect(screen.getByLabelText("分段提示词")).toHaveValue("第二条隐藏提示词");
    expect(screen.getByLabelText("雪夜 分格数量")).toHaveValue(4);
  });

  it("appends regenerated storyboard images without replacing the selected image", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/storyboard-panel-image") {
        expect(JSON.parse(String(init?.body ?? "{}"))).toMatchObject({ card_id: "segment-0", prompt: "用户修改后的提示词" });
        return jsonResponse({ generation_id: "storyboard-generation-2", status: "queued" });
      }
      if (url === "/api/assets/generate-image/storyboard-generation-2") {
        return jsonResponse({
          generation_id: "storyboard-generation-2",
          status: "succeeded",
          result: {
            card_id: "segment-0",
            image_url: "https://cdn.example.com/storyboard-new.png",
            source: "ai_generated",
          },
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StoryboardPanelCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.storyboard_panel_cards.v1", variant: "panel_review", mode: "interactive" }}
        node={{
          node_execution_id: "exec-storyboard-panel-regenerate",
          node_id: "review_storyboard_image",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            panel_cards: [
              {
                card_id: "segment-0",
                segment_index: 0,
                panel_index: 0,
                segment_title: "雪夜",
                description: "林冲踏雪前行。",
                prompt: "分镜提示词",
                reference_images: [
                  {
                    label: "林冲",
                    asset_type: "character",
                    asset_name: "林冲",
                    image_ref: { kind: "data_uri", data: "data:image/png;base64,cmVm", role: "reference" },
                    source: "asset",
                  },
                ],
                generated_images: [{ image_url: "https://cdn.example.com/storyboard-old.png", source: "ai_generated" }],
                selected_image_url: "https://cdn.example.com/storyboard-old.png",
                aspect_ratio: "16:9",
                resolution: "2K",
              },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("分段提示词"), { target: { value: "用户修改后的提示词" } });
    fireEvent.click(screen.getByRole("button", { name: "重新生成" }));

    expect(await screen.findByRole("img", { name: "生成图 2" })).toHaveAttribute("src", "https://cdn.example.com/storyboard-new.png");
    expect(screen.getByRole("img", { name: "生成图 1" })).toHaveAttribute("src", "https://cdn.example.com/storyboard-old.png");
    expect(screen.getByText("2 张生成图")).toBeInTheDocument();
    const selectedButtons = screen.getAllByRole("button").filter((button) => button.textContent?.includes("已选定稿"));
    expect(selectedButtons).toHaveLength(1);
    expect(selectedButtons[0].querySelector("img")).toHaveAttribute("src", "https://cdn.example.com/storyboard-old.png");
  });

  it("uses configured default reference assets in asset image cards when no match exists", async () => {
    const onSubmit = vi.fn();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/assets/tags")) {
        return jsonResponse({ items: [] });
      }
      if (url.startsWith("/api/assets/search")) {
        const called = new URL(url, "http://localhost");
        const names = called.searchParams.get("names") ?? "";
        if (names === "塞雷2d角色模板") {
          return jsonResponse({
            items: [{
              asset_id: "asset-default-character",
              asset_type: "file",
              name: "塞雷2d角色模板",
              scope: "project",
              mime_type: "image/png",
              size_bytes: 128,
              storage_uri: "assets/default-character.png",
              metadata: {
                public_url: "https://assets.local.invalid/default-character.png",
                appearance_description: "默认角色模板外貌。",
              },
              created_at: "2026-05-27T10:00:00Z",
            }],
          });
        }
        return jsonResponse({ items: [] });
      }
      if (url === "/api/assets/generate-image") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        expect(body.prompt_result).toMatchObject({
          reference_image_ref: {
            kind: "asset",
            asset_id: "asset-default-character",
            role: "reference",
          },
          reference_appearance_description: "默认角色模板外貌。",
        });
        return jsonResponse({ generation_id: "image-generation-default", status: "queued" });
      }
      if (url === "/api/assets/generate-image/image-generation-default") {
        return jsonResponse({
          generation_id: "image-generation-default",
          status: "succeeded",
          result: {
            full_name: "鲁智深",
            image_url: "https://cdn.example.com/generated-luzhishen.png",
            source: "ai_generated",
          },
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    const cardNode: TaskNodeExecution = {
      node_execution_id: "exec-default-reference",
      node_id: "upload_images",
      node_ref: "system.human_approval.v1",
      status: "waiting",
      input_snapshot: {
        characters: [{ full_name: "鲁智深", aliases: ["花和尚"], summary: "梁山好汉。" }],
        enriched_characters: [{ full_name: "鲁智深", matched: false }],
        variant_results: [{ full_name: "鲁智深", new_variant_name: "鲁智深_僧衣" }],
        accessory_results: [{ full_name: "鲁智深", new_accessories: [] }],
        prompt_results: [{ asset_type: "character", asset_name: "鲁智深", asset_tags: ["僧衣"], prompt: "生成僧衣角色" }],
        approved_assets: {
          characters: [{ type: "character", name: "鲁智深", matched: false, variant_name: "僧衣" }],
          assets: [],
          props: [],
        },
      },
      metadata: {},
    };

    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{
          control_id: "ui.interaction.asset_image_cards.v1",
          variant: "grouped_cards",
          mode: "interactive",
          options: {
            default_reference_templates: {
              character: "塞雷2d角色模板",
            },
          },
        }}
        node={cardNode}
        onSubmit={onSubmit}
      />,
    );

    expect(await screen.findByText("塞雷2d角色模板")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "生成" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/assets/generate-image",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("shows a custom dialog with the duplicated asset name when library save conflicts", async () => {
    const onSubmit = vi.fn();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/assets/tags")) {
        return jsonResponse({
          items: [
            { tag_id: "tag-character", name: "角色", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-linchong", name: "林冲", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-luzhishen", name: "鲁智深", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-default", name: "默认", scope: "project", project_id: "global", asset_count: 1 },
          ],
        });
      }
      if (url.startsWith("/api/assets/search")) {
        const called = new URL(url, "http://localhost");
        expect(called.searchParams.get("names")).toBeNull();
        const tagNames = called.searchParams.get("tag_names") ?? "";
        if (tagNames === "角色,林冲,默认") {
          return jsonResponse({
            items: [
              { asset_id: "asset-linchong", name: "角色_林冲_默认", asset_type: "file", scope: "project", metadata: {}, created_at: "2026-05-31T00:00:00Z" },
            ],
          });
        }
        if (tagNames === "角色,鲁智深,默认") {
          return jsonResponse({
            items: [
              { asset_id: "asset-luzhishen", name: "角色_鲁智深_默认", asset_type: "file", scope: "project", metadata: {}, created_at: "2026-05-31T00:00:00Z" },
            ],
          });
        }
        return jsonResponse({ items: [] });
      }
      if (url === "/api/assets/asset-linchong/tags") {
        return jsonResponse({
          items: [
            { tag_id: "tag-character", name: "角色", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-linchong", name: "林冲", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-default", name: "默认", scope: "project", project_id: "global", asset_count: 1 },
          ],
        });
      }
      if (url === "/api/assets/asset-luzhishen/tags") {
        return jsonResponse({
          items: [
            { tag_id: "tag-character", name: "角色", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-luzhishen", name: "鲁智深", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-default", name: "默认", scope: "project", project_id: "global", asset_count: 1 },
          ],
        });
      }
      if (url === "https://cdn.example.com/linchong-ready.png" || url === "https://cdn.example.com/luzhishen-ready.png") {
        return Promise.resolve(new Response(new Blob(["fake"], { type: "image/png" }), {
          status: 200,
          headers: { "Content-Type": "image/png" },
        }));
      }
      if ((url === "/api/assets/asset-linchong/file" || url === "/api/assets/asset-luzhishen/file") && init?.method === "PUT") {
        return jsonResponse({
          asset_id: url.includes("asset-linchong") ? "asset-linchong" : "asset-luzhishen",
          name: url.includes("asset-linchong") ? "角色_林冲_默认" : "角色_鲁智深_默认",
          asset_type: "file",
          scope: "project",
          metadata: {},
          created_at: "2026-05-31T00:00:00Z",
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-conflict",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            characters: [
              { asset_type: "character", asset_name: "林冲", asset_tags: ["默认"], matched: false },
              { asset_type: "character", asset_name: "鲁智深", asset_tags: ["默认"], matched: false },
            ],
            variant_results: [
              { asset_type: "character", asset_name: "林冲", asset_tags: ["默认"] },
              { asset_type: "character", asset_name: "鲁智深", asset_tags: ["默认"] },
            ],
            prompt_results: [
              { asset_type: "character", asset_name: "林冲", asset_tags: ["默认"], prompt: "囚服" },
              { asset_type: "character", asset_name: "鲁智深", asset_tags: ["默认"], prompt: "僧衣" },
            ],
            asset_images: [
              {
                asset_type: "character",
                asset_name: "林冲",
                asset_tags: ["默认"],
                image_url: "https://cdn.example.com/linchong-ready.png",
              },
              {
                asset_type: "character",
                asset_name: "鲁智深",
                asset_tags: ["默认"],
                image_url: "https://cdn.example.com/luzhishen-ready.png",
              },
            ],
          },
        }}
        onSubmit={onSubmit}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "一键入库" }));

    const dialog = await screen.findByRole("dialog", { name: "资产名称重复" });
    expect(within(dialog).getByText("资产名称重复")).toBeInTheDocument();
    expect(within(dialog).getByText("角色_林冲_默认")).toBeInTheDocument();
    expect(within(dialog).getByText("角色_鲁智深_默认")).toBeInTheDocument();
    expect(within(dialog).getByText(/以下资产名称已在项目资产库或本次入库列表中重复/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "覆盖" })).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "返回" }));
    expect(screen.queryByRole("dialog", { name: "资产名称重复" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "一键入库" }));
    const overwriteDialog = await screen.findByRole("dialog", { name: "资产名称重复" });
    await userEvent.click(within(overwriteDialog).getByRole("button", { name: "覆盖" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      decision: "finish",
      created_asset_ids: expect.arrayContaining(["asset-linchong", "asset-luzhishen"]),
    })));
    expect(fetchMock.mock.calls.some(([url, init]) => url === "/api/assets/asset-linchong/file" && init?.method === "PUT")).toBe(true);
    expect(fetchMock.mock.calls.some(([url, init]) => url === "/api/assets/asset-luzhishen/file" && init?.method === "PUT")).toBe(true);
    expect(screen.queryByText("同一资产库中已存在同名资产。")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/assets/files")).toBe(false);
  });

  it("uses asset-type-specific prompt prefixes and suffixes when generating asset images", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/generate-image") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        const promptResult = body.prompt_result as Record<string, unknown>;
        const assetType = String(promptResult.asset_type ?? "");
        return jsonResponse({
          generation_id: `image-generation-${assetType}`,
          status: "queued",
        });
      }
      if (url.startsWith("/api/assets/generate-image/image-generation-")) {
        return jsonResponse({
          generation_id: url.split("/").pop(),
          status: "succeeded",
          result: {
            full_name: "generated",
            image_url: "https://cdn.example.com/generated.png",
            source: "ai_generated",
          },
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{
          control_id: "ui.interaction.asset_image_cards.v1",
          variant: "grouped_cards",
          mode: "interactive",
          options: {
            prompt_text_by_type: {
              character: {
                prefix: "将图中角色改成",
                suffix: "保持角色比例、画风、线条和其它未提及特征不变",
              },
              character_default_reference: {
                prefix: "将图中角色改成",
                suffix: "保持画风和角色体型不变，改变原图中的所有角色特征，根据描述设计全新的形象。",
              },
              scene: {
                prefix: "将图中场景改成",
                suffix: "保持画风、构图视角、空间透视和其它未提及元素不变",
              },
              prop: {
                prefix: "将图中道具改成",
                suffix: "保持画风、主体轮廓、摆放角度和其它未提及特征不变",
              },
            },
          },
        }}
        node={{
          node_execution_id: "exec-card-types",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            approved_assets: {
              characters: [{ name: "鲁智深", prompt: "粗眉僧衣", reference_source: "default_template" }],
              assets: [{ name: "山神庙", prompt: "雪夜破庙" }],
              props: [{ name: "花枪", prompt: "木杆长枪" }],
            },
            prompt_results: [
              { asset_type: "character", asset_name: "鲁智深", prompt: "粗眉僧衣", reference_source: "default_template", reference_image_ref: { kind: "asset", asset_id: "asset-character", role: "reference" } },
              { asset_type: "scene", asset_name: "山神庙", prompt: "雪夜破庙", reference_image_ref: { kind: "asset", asset_id: "asset-scene", role: "reference" } },
              { asset_type: "prop", asset_name: "花枪", prompt: "木杆长枪", reference_image_ref: { kind: "asset", asset_id: "asset-prop", role: "reference" } },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "资产生成" }));

    await waitFor(() => {
      const generateCalls = fetchMock.mock.calls.filter(([url]) => String(url) === "/api/assets/generate-image");
      expect(generateCalls.length).toBe(3);
    });
    expect(screen.getByRole("status")).toHaveTextContent("资产图像生成完成");
    expect(screen.getByRole("status")).toHaveTextContent("3/3");
    const bodies = fetchMock.mock.calls
      .filter(([url]) => String(url) === "/api/assets/generate-image")
      .map(([, init]) => JSON.parse(String((init as RequestInit).body ?? "{}")) as Record<string, unknown>);
    expect(bodies).toEqual(expect.arrayContaining([
      expect.objectContaining({
        prompt_prefix: "将图中角色改成",
        prompt_suffix: "保持画风和角色体型不变，改变原图中的所有角色特征，根据描述设计全新的形象。",
        aspect_ratio: "1:1",
      }),
      expect.objectContaining({
        prompt_prefix: "将图中场景改成",
        prompt_suffix: "保持画风、构图视角、空间透视和其它未提及元素不变",
        aspect_ratio: "16:9",
      }),
      expect.objectContaining({
        prompt_prefix: "将图中道具改成",
        prompt_suffix: "保持画风、主体轮廓、摆放角度和其它未提及特征不变",
        aspect_ratio: "1:1",
      }),
    ]));
  });

  it("queues batch generation with two concurrent cards and visible per-card statuses", async () => {
    const statusResolvers = new Map<string, (response: Response) => void>();
    const response = (body: unknown) => new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/generate-image") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        const promptResult = body.prompt_result as Record<string, unknown>;
        const assetName = String(promptResult.asset_name ?? "");
        return jsonResponse({
          generation_id: `image-generation-${assetName}`,
          status: "queued",
        });
      }
      if (url.startsWith("/api/assets/generate-image/")) {
        const generationId = decodeURIComponent(url.split("/").pop() ?? "");
        return new Promise<Response>((resolve) => {
          statusResolvers.set(generationId, resolve);
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-card-queue",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            approved_assets: {
              characters: [
                { name: "林冲", prompt: "囚服毡笠" },
                { name: "鲁智深", prompt: "粗眉僧衣" },
                { name: "武松", prompt: "行者装束" },
              ],
            },
            prompt_results: [
              { asset_type: "character", asset_name: "林冲", prompt: "囚服毡笠", reference_image_ref: { kind: "asset", asset_id: "asset-lin", role: "reference" } },
              { asset_type: "character", asset_name: "鲁智深", prompt: "粗眉僧衣", reference_image_ref: { kind: "asset", asset_id: "asset-lu", role: "reference" } },
              { asset_type: "character", asset_name: "武松", prompt: "行者装束", reference_image_ref: { kind: "asset", asset_id: "asset-wu", role: "reference" } },
            ],
          },
        }}
        onSubmit={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "资产生成" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([url]) => String(url) === "/api/assets/generate-image").length).toBe(2);
    });
    expect(screen.getAllByText("生成中").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("等待中").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("status")).toHaveTextContent("0/3");

    statusResolvers.get("image-generation-林冲")?.(response({
      generation_id: "image-generation-林冲",
      status: "succeeded",
      result: { image_url: "https://cdn.example.com/generated-lin.png", source: "ai_generated" },
    }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([url]) => String(url) === "/api/assets/generate-image").length).toBe(3);
    });
    expect(await screen.findByText("成功")).toBeInTheDocument();
    expect(screen.getAllByText("生成中").length).toBeGreaterThanOrEqual(2);
    statusResolvers.get("image-generation-鲁智深")?.(response({
      generation_id: "image-generation-鲁智深",
      status: "succeeded",
      result: { image_url: "https://cdn.example.com/generated-lu.png", source: "ai_generated" },
    }));
    statusResolvers.get("image-generation-武松")?.(response({
      generation_id: "image-generation-武松",
      status: "succeeded",
      result: { image_url: "https://cdn.example.com/generated-wu.png", source: "ai_generated" },
    }));
  });

  it("keeps successful generated images when one asset image generation fails", async () => {
    const onDraft = vi.fn();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/generate-image") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        const promptResult = body.prompt_result as Record<string, unknown>;
        const assetType = String(promptResult.asset_type ?? "");
        if (assetType === "scene") throw new Error("NOT_ENOUGH_BALANCE");
        return jsonResponse({
          generation_id: `image-generation-${assetType}`,
          status: "queued",
        });
      }
      if (url.startsWith("/api/assets/generate-image/image-generation-")) {
        const assetType = url.split("-").pop() ?? "asset";
        return jsonResponse({
          generation_id: url.split("/").pop(),
          status: "succeeded",
          result: {
            full_name: assetType,
            image_url: `https://cdn.example.com/generated-${assetType}.png`,
            source: "ai_generated",
          },
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-card-partial-failure",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            approved_assets: {
              characters: [{ name: "鲁智深", prompt: "粗眉僧衣" }],
              assets: [{ name: "山神庙", prompt: "雪夜破庙" }],
              props: [{ name: "花枪", prompt: "木杆长枪" }],
            },
            prompt_results: [
              { asset_type: "character", asset_name: "鲁智深", prompt: "粗眉僧衣", reference_image_ref: { kind: "asset", asset_id: "asset-character", role: "reference" } },
              { asset_type: "scene", asset_name: "山神庙", prompt: "雪夜破庙", reference_image_ref: { kind: "asset", asset_id: "asset-scene", role: "reference" } },
              { asset_type: "prop", asset_name: "花枪", prompt: "木杆长枪", reference_image_ref: { kind: "asset", asset_id: "asset-prop", role: "reference" } },
            ],
          },
        }}
        onDraft={onDraft}
        onSubmit={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "资产生成" }));

    expect(await screen.findByRole("img", { name: "鲁智深 图像" })).toHaveAttribute("src", "https://cdn.example.com/generated-character.png");
    await userEvent.click(screen.getByRole("button", { name: "全屏查看图像" }));
    const preview = await screen.findByRole("dialog", { name: "全屏查看 角色_鲁智深_默认" });
    expect(within(preview).getByAltText("角色_鲁智深_默认")).toHaveAttribute("src", "https://cdn.example.com/generated-character.png");
    fireEvent.wheel(within(preview).getByAltText("角色_鲁智深_默认").parentElement as HTMLElement, { deltaY: -120 });
    expect(await within(preview).findByText("112%")).toBeInTheDocument();
    fireEvent.mouseDown(preview);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "全屏查看 角色_鲁智深_默认" })).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("tab", { name: /道具/ }));
    expect(await screen.findByRole("img", { name: "花枪 图像" })).toHaveAttribute("src", "https://cdn.example.com/generated-prop.png");
    await userEvent.click(screen.getByRole("tab", { name: /地点/ }));
    expect(screen.getByText("生成失败：余额不足，请充值后重试。")).toBeInTheDocument();
    expect(screen.queryByText(/NOT_ENOUGH_BALANCE/)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("资产图像生成完成");
    expect(screen.getByRole("status")).toHaveTextContent("3/3");
    expect(screen.getByText("已生成 2 张资产图像，1 张生成失败。")).toBeInTheDocument();
    expect(onDraft).toHaveBeenCalledWith(expect.objectContaining({
      decision: "generate_missing",
      asset_images: expect.arrayContaining([
        expect.objectContaining({ asset_name: "鲁智深", image_url: "https://cdn.example.com/generated-character.png" }),
        expect.objectContaining({ asset_name: "花枪", image_url: "https://cdn.example.com/generated-prop.png" }),
      ]),
    }));
  });

  it("merges concurrent single-card generation results without losing earlier images", async () => {
    const onDraft = vi.fn(() => Promise.resolve());
    const statusResolvers = new Map<string, (response: Response) => void>();
    const response = (body: unknown) => new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
    const generationIdForName = (name: string) => name.includes("鲁智深") ? "image-generation-lu" : "image-generation-lin";
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/assets/generate-image") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        const promptResult = body.prompt_result as Record<string, unknown>;
        const assetName = String(promptResult.asset_name ?? "");
        return jsonResponse({
          generation_id: generationIdForName(assetName),
          status: "queued",
        });
      }
      if (url.startsWith("/api/assets/generate-image/")) {
        const generationId = decodeURIComponent(url.split("/").pop() ?? "");
        return new Promise<Response>((resolve) => {
          statusResolvers.set(generationId, resolve);
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AssetImageCardsControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={{
          node_execution_id: "exec-card-concurrent-single",
          node_id: "upload_images",
          node_ref: "system.human_approval.v1",
          status: "waiting",
          input_snapshot: {
            approved_assets: {
              characters: [
                { name: "林冲", prompt: "囚服毡笠" },
                { name: "鲁智深", prompt: "粗眉僧衣" },
              ],
            },
            prompt_results: [
              { asset_type: "character", asset_name: "林冲", prompt: "囚服毡笠", reference_image_ref: { kind: "asset", asset_id: "asset-lin", role: "reference" } },
              { asset_type: "character", asset_name: "鲁智深", prompt: "粗眉僧衣", reference_image_ref: { kind: "asset", asset_id: "asset-lu", role: "reference" } },
            ],
          },
        }}
        onDraft={onDraft}
        onSubmit={vi.fn()}
      />,
    );

    const generateButtons = screen.getAllByRole("button", { name: "生成" });
    await userEvent.click(generateButtons[0]);
    await userEvent.click(generateButtons[1]);

    await waitFor(() => expect(statusResolvers.size).toBe(2));
    statusResolvers.get("image-generation-lu")?.(response({
      generation_id: "image-generation-lu",
      status: "succeeded",
      result: {
        image_url: "https://cdn.example.com/generated-lu.png",
        source: "ai_generated",
      },
    }));
    expect(await screen.findByRole("img", { name: "鲁智深 图像" })).toHaveAttribute("src", "https://cdn.example.com/generated-lu.png");

    statusResolvers.get("image-generation-lin")?.(response({
      generation_id: "image-generation-lin",
      status: "succeeded",
      result: {
        image_url: "https://cdn.example.com/generated-lin.png",
        source: "ai_generated",
      },
    }));

    await waitFor(() => {
      expect(screen.getByRole("img", { name: "林冲 图像" })).toHaveAttribute("src", "https://cdn.example.com/generated-lin.png");
      expect(screen.getByRole("img", { name: "鲁智深 图像" })).toHaveAttribute("src", "https://cdn.example.com/generated-lu.png");
      expect(onDraft).toHaveBeenLastCalledWith(expect.objectContaining({
        asset_images: expect.arrayContaining([
          expect.objectContaining({ asset_name: "林冲", image_url: "https://cdn.example.com/generated-lin.png" }),
          expect.objectContaining({ asset_name: "鲁智深", image_url: "https://cdn.example.com/generated-lu.png" }),
        ]),
      }));
    });
  });

  it("renders the P3 asset summary table with tabs and submitted image rows", async () => {
    const onSubmit = vi.fn();
    const onDraft = vi.fn();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/assets/tags")) {
        return jsonResponse({
          items: [
            { tag_id: "tag-character", name: "角色", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-location", name: "地点", scope: "project", project_id: "global", asset_count: 1 },
            { tag_id: "tag-prop", name: "道具", scope: "project", project_id: "global", asset_count: 0 },
          ],
        });
      }
      if (url.startsWith("/api/assets/search")) {
        const called = new URL(url, "http://localhost");
        const tagNames = called.searchParams.get("tag_names") ?? "";
        const includeCharacters = tagNames.includes("角色");
        const includeLocations = tagNames.includes("地点");
        return jsonResponse({
          items: [
            includeCharacters ? {
              asset_id: "asset-luzhishen",
              asset_type: "text",
              name: "鲁智深",
              scope: "project",
              mime_type: null,
              size_bytes: null,
              metadata: { public_url: "https://cdn.example.com/luzhishen-ref.png" },
              created_at: "2026-05-27T10:00:00Z",
            } : null,
            includeLocations ? {
              asset_id: "asset-yazhulin",
              asset_type: "text",
              name: "野猪林资产",
              scope: "project",
              mime_type: null,
              size_bytes: null,
              metadata: {},
              created_at: "2026-05-27T10:00:00Z",
            } : null,
          ].filter(Boolean),
        });
      }
      if (url === "/api/assets/draft-from-description") {
        return jsonResponse({
          assets: [
            {
              asset_type: "character",
              asset_name: "武松",
              asset_tags: ["劲装短打", "哨棒"],
              matched: false,
              matched_asset_id: null,
              matched_asset_name: "",
              aliases: "行者",
              summary: "梁山好汉",
              character_status: "途经景阳冈",
              variant_description: "劲装短打",
            },
            {
              asset_type: "scene",
              asset_name: "官兵船",
              asset_tags: ["水上", "官船"],
              matched: false,
              matched_asset_id: null,
              matched_asset_name: "",
              description: "官兵在水上押送使用的船只，甲板可站人，带低矮船舱、桅杆、缆绳和官府旗号。",
              location_type: "水上",
              time_of_day: "",
            },
            {
              asset_type: "prop",
              asset_name: "哨棒",
              asset_tags: ["武器"],
              matched: false,
              matched_asset_id: null,
              matched_asset_name: "",
              description: "武松途经景阳冈时随身携带的棍棒，长直木杆，握柄处颜色更深，杆身有磨损，便于防身挥击。",
              category: "武器",
              related_character: "武松",
            },
          ],
          confidence: 0.86,
          reasoning: "根据用户描述和原文补全多个资产字段。",
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const reviewNode: TaskNodeExecution = {
      node_execution_id: "exec-review",
      node_id: "review_assets",
      node_ref: "system.human_approval.v1",
      status: "waiting",
      input_snapshot: {
        characters: [
          { asset_type: "character", asset_name: "林冲", asset_tags: ["囚服"], aliases: ["林教头"], summary: "禁军教头", character_status: "发配途中" },
        ],
        enriched_characters: [
          { asset_type: "character", asset_name: "林冲", asset_tags: ["囚服"], matched: true, matched_asset_name: "林冲_囚服" },
        ],
        scenes: [
          { name: "野猪林", description: "密林埋伏地", time_of_day: "白天" },
        ],
        enriched_scenes: [
          { name: "野猪林", matched: false },
        ],
        props: [
          { asset_type: "prop", asset_name: "水火棍", asset_tags: ["武器"], description: "差役棍棒", category: "武器" },
        ],
        enriched_props: [
          { asset_type: "prop", asset_name: "水火棍", asset_tags: ["武器"], matched: false },
        ],
      },
    };

    render(
      <AssetSummaryTableControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_summary_table.v1", variant: "tabbed_table", mode: "interactive" }}
        node={reviewNode}
        onDraft={onDraft}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByRole("tab", { name: /角色/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /地点/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /道具/ })).toBeInTheDocument();
    expect(screen.getByDisplayValue("林冲")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "标签" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "变体描述" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /asset type/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "林冲_囚服" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /道具/ }));
    expect(screen.getByRole("textbox", { name: "水火棍 关联角色" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /asset type/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /地点/ }));
    expect(screen.getByRole("columnheader", { name: "时间/环境/氛围" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "未匹配到对应资产" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /asset type/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /角色/ }));

    await userEvent.click(screen.getByRole("button", { name: "林冲_囚服" }));
    expect(await screen.findByRole("dialog", { name: "选择匹配资产" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择名称 鲁智深" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择资产 鲁智深" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /野猪林资产/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "选择资产 鲁智深" }));

    await userEvent.click(screen.getByRole("button", { name: "补充缺失资产" }));
    expect(await screen.findByRole("dialog", { name: "补充缺失资产" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("描述需要新增的资产"), "增加一个拿哨棒的武松、官兵船和哨棒");
    await userEvent.click(screen.getByRole("button", { name: "生成资产草稿" }));
    expect(await screen.findByText("根据用户描述和原文补全多个资产字段。")).toBeInTheDocument();
    expect(screen.getByText("生成 3 个资产草稿")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "合并到资产表格" }));
    expect(screen.getByDisplayValue("武松")).toBeInTheDocument();
    await waitFor(() => expect(onDraft).toHaveBeenLastCalledWith(expect.objectContaining({
      approved_assets: expect.objectContaining({
        characters: expect.arrayContaining([expect.objectContaining({ asset_name: "武松" })]),
        assets: expect.arrayContaining([expect.objectContaining({ asset_name: "官兵船" })]),
        props: expect.arrayContaining([expect.objectContaining({ asset_name: "哨棒" })]),
      }),
      additional_asset_request: "增加一个拿哨棒的武松、官兵船和哨棒",
    })));
    const savedDraft = onDraft.mock.calls[onDraft.mock.calls.length - 1]?.[0] as Record<string, unknown>;
    cleanup();
    render(
      <AssetSummaryTableControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_summary_table.v1", variant: "tabbed_table", mode: "interactive" }}
        node={{ ...reviewNode, input_snapshot: { ...(reviewNode.input_snapshot as Record<string, unknown>), ...savedDraft } }}
        onDraft={onDraft}
        onSubmit={onSubmit}
      />,
    );
    expect(screen.getByDisplayValue("武松")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /地点/ }));
    expect(screen.getByDisplayValue("官兵船")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /道具/ }));
    expect(screen.getByDisplayValue("哨棒")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /角色/ }));

    await userEvent.click(screen.getByRole("button", { name: "补充缺失资产" }));
    await userEvent.click(await screen.findByRole("button", { name: "手动新增当前分类空行" }));
    let nameInputs = screen.getAllByLabelText("角色名称");
    await userEvent.type(nameInputs[nameInputs.length - 1], "宋江");
    const deleteButtons = screen.getAllByRole("button", { name: "删除" });
    await userEvent.click(deleteButtons[deleteButtons.length - 1]);
    expect(screen.getAllByLabelText("角色名称")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "确认并继续" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      decision: "approved",
      approved_assets: expect.objectContaining({
        characters: expect.arrayContaining([
          expect.objectContaining({
            asset_type: "character",
            asset_name: "林冲",
            asset_tags: ["囚服"],
            matched_asset_name: "鲁智深",
            matched_asset_ref: { kind: "asset", asset_id: "asset-luzhishen", role: "reference" },
            reference_image_ref: { kind: "asset", asset_id: "asset-luzhishen", role: "reference" },
          }),
          expect.objectContaining({
            asset_type: "character",
            asset_name: "武松",
            asset_tags: ["劲装短打", "哨棒"],
            matched: false,
            aliases: "行者",
            summary: "梁山好汉",
          }),
        ]),
        assets: expect.arrayContaining([
          expect.objectContaining({
            asset_type: "scene",
            asset_name: "野猪林",
            matched: false,
            matched_asset_id: null,
            matched_asset_name: "",
          }),
          expect.objectContaining({
            asset_type: "scene",
            asset_name: "官兵船",
            asset_tags: ["水上", "官船"],
            matched: false,
            description: "官兵在水上押送使用的船只，甲板可站人，带低矮船舱、桅杆、缆绳和官府旗号。",
          }),
        ]),
        props: expect.arrayContaining([
          expect.objectContaining({
            asset_type: "prop",
            asset_name: "哨棒",
            asset_tags: ["武器"],
            matched: false,
            category: "武器",
            related_character: "武松",
          }),
        ]),
      }),
      additional_asset_request: "增加一个拿哨棒的武松、官兵船和哨棒",
      asset_images: [],
    }));
  });

  it("renders the P5 asset task summary and exports image zip", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith("/api/assets/asset-linchong/thumbnail?")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          blob: async () => new Blob([new Uint8Array([9, 8, 7])], { type: "image/png" }),
        } as Response);
      }
      if (String(input) === "/api/assets/asset-linchong/content") {
        return Promise.resolve({
          ok: true,
          status: 200,
          blob: async () => ({
            type: "image/png",
            arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
          }),
        } as Response);
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const clickMock = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:asset-zip"), revokeObjectURL: vi.fn() });
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const element = document.createElementNS("http://www.w3.org/1999/xhtml", tagName) as HTMLAnchorElement;
      if (tagName === "a") element.click = clickMock;
      return element;
    });
    const summaryNode: TaskNodeExecution = {
      node_execution_id: "exec-summary",
      node_id: "finish_summary",
      node_ref: "tool.echo.v1",
      status: "succeeded",
      output_snapshot: {
        created_asset_ids: ["asset-linchong"],
        asset_catalog: {
          approved_assets: {
            characters: [{ asset_name: "林冲", asset_tags: ["囚服"] }],
            assets: [{ asset_name: "山神庙外", asset_tags: [] }],
            props: [{ asset_name: "花枪", asset_tags: [] }],
          },
          generation_summary: {
            total_asset_count: 3,
            new_asset_count: 1,
            matched_asset_count: 2,
            has_assets_to_generate: true,
          },
          asset_images: [
            {
              asset_type: "character",
              asset_name: "林冲",
              asset_tags: ["囚服", "佩刀"],
              image_url: "https://cdn.example.com/linchong.png",
              source: "library",
              asset_id: "asset-linchong",
            },
          ],
        },
      },
    };

    render(
      <AssetTaskSummaryControl
        config={{ control_id: "ui.display.asset_task_summary.v1", variant: "catalog_complete", mode: "readonly" }}
        node={summaryNode}
      />,
    );

    expect(screen.getByText("资产编目已完成")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "林冲 图像" })).toHaveAttribute("src", "blob:asset-zip");
    expect(fetchMock).toHaveBeenCalledWith("/api/assets/asset-linchong/thumbnail?size=256", expect.any(Object));
    expect(screen.getByText("已入库")).toBeInTheDocument();
    expect(screen.getByText("总资产").closest("div")).toHaveTextContent("3");
    expect(screen.getByText("新增").closest("div")).toHaveTextContent("1");
    expect(screen.getByText("已匹配").closest("div")).toHaveTextContent("2");
    expect(screen.getByText("角色").closest("div")).toHaveTextContent("1");
    expect(screen.getByText("地点").closest("div")).toHaveTextContent("1");
    expect(screen.getByText("道具").closest("div")).toHaveTextContent("1");
    await userEvent.click(screen.getByRole("button", { name: "全屏查看图像" }));
    const preview = await screen.findByRole("dialog", { name: "全屏查看 林冲" });
    expect(fetchMock).toHaveBeenCalledWith("/api/assets/asset-linchong/content", expect.any(Object));
    fireEvent.wheel(within(preview).getByAltText("林冲").parentElement as HTMLElement, { deltaY: -120 });
    expect(await within(preview).findByText("112%")).toBeInTheDocument();
    fireEvent.mouseDown(preview);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "全屏查看 林冲" })).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "导出资产为压缩包" }));
    await waitFor(() => expect(clickMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("/api/assets/asset-linchong/content", expect.any(Object));
  });

  it("renders the storyboard task summary and exports storyboard images", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input) === "https://cdn.example.com/panel-1.png") {
        return Promise.resolve({
          ok: true,
          status: 200,
          blob: async () => ({
            type: "image/png",
            arrayBuffer: async () => new Uint8Array([4, 5, 6]).buffer,
          }),
        } as Response);
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const clickMock = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:storyboard-zip"), revokeObjectURL: vi.fn() });
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const element = document.createElementNS("http://www.w3.org/1999/xhtml", tagName) as HTMLAnchorElement;
      if (tagName === "a") element.click = clickMock;
      return element;
    });
    const summaryNode: TaskNodeExecution = {
      node_execution_id: "exec-storyboard-summary",
      node_id: "storyboard_summary",
      node_ref: "tool.storyboard_task_summary.v1",
      status: "succeeded",
      output_snapshot: {
        generation_summary: {
          total_panel_count: 2,
          completed_panel_count: 1,
          missing_panel_count: 1,
        },
        asset_images: [
          {
            asset_type: "storyboard",
            asset_name: "芦苇荡遇敌_水港伏击",
            asset_tags: ["分镜", "第1段", "第1格"],
            image_url: "https://cdn.example.com/panel-1.png",
            source: "storyboard_generated",
          },
        ],
      },
    };

    render(
      <AssetTaskSummaryControl
        config={{ control_id: "ui.display.asset_task_summary.v1", variant: "storyboard_complete", mode: "readonly" }}
        node={summaryNode}
      />,
    );

    expect(screen.getByText("分镜生成已完成")).toBeInTheDocument();
    expect(screen.getByText("总分镜").closest("div")).toHaveTextContent("2");
    expect(screen.getByText("已完成").closest("div")).toHaveTextContent("1");
    expect(screen.getByText("未完成").closest("div")).toHaveTextContent("1");
    expect(screen.getByRole("img", { name: "芦苇荡遇敌_水港伏击 图像" })).toHaveAttribute("src", "https://cdn.example.com/panel-1.png");
    await userEvent.click(screen.getByRole("button", { name: "导出分镜为压缩包" }));
    await waitFor(() => expect(clickMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("https://cdn.example.com/panel-1.png");
  });

  it("renders completed P3 asset summary rows from approved_assets output", async () => {
    const reviewNode: TaskNodeExecution = {
      node_execution_id: "exec-review-done",
      node_id: "review_assets",
      node_ref: "system.human_approval.v1",
      status: "succeeded",
      output_snapshot: {
        decision: "approved",
        approved_assets: {
          characters: [
            {
              asset_type: "character",
              asset_name: "林冲",
              asset_tags: ["囚服"],
              matched: true,
              matched_asset_id: "asset-linchong",
              matched_asset_name: "林冲_囚服",
              summary: "八十万禁军教头",
              character_status: "发配途中",
              variant_description: "身着囚服，头戴旧毡笠。",
            },
          ],
          assets: [
            {
              asset_type: "scene",
              asset_name: "野猪林",
              asset_tags: [],
              matched: false,
              matched_asset_id: null,
              matched_asset_name: "",
              description: "密林埋伏地",
              location_type: "户外",
              time_of_day: "白天",
            },
          ],
          props: [
            {
              asset_type: "prop",
              asset_name: "水火棍",
              asset_tags: ["武器"],
              matched: false,
              matched_asset_id: null,
              matched_asset_name: "",
              description: "差役棍棒",
              category: "武器",
            },
          ],
        },
        asset_images: [
          {
            asset_type: "character",
            asset_name: "林冲",
            asset_tags: ["囚服"],
            image_url: "https://cdn.example.com/linchong.png",
            source: "manual_upload",
          },
        ],
      },
    };

    render(
      <AssetSummaryTableControl
        projectId="project-1"
        config={{ control_id: "ui.interaction.asset_summary_table.v1", variant: "tabbed_table", mode: "readonly" }}
        node={reviewNode}
      />,
    );

    expect(screen.getAllByText("林冲").length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: "操作" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "标签" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "变体描述" })).not.toBeInTheDocument();
    expect(screen.getByText("囚服")).toBeInTheDocument();
    expect(screen.queryByText("身着囚服，头戴旧毡笠。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "林冲_囚服" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "林冲 图像" })).toHaveAttribute("src", "https://cdn.example.com/linchong.png");
    await userEvent.click(screen.getByRole("tab", { name: /地点/ }));
    expect(screen.getByText("野猪林")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /道具/ }));
    expect(screen.getByText("水火棍")).toBeInTheDocument();
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

  it("imports txt files and submits script text input", async () => {
    const onSubmit = vi.fn();
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["script", "background"],
      properties: {
        script: { type: "string", title: "剧本内容" },
        background: { type: "string", title: "世界背景", default: "水浒传" },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-script",
      node_id: "collect_asset_input",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema },
    };

    render(
      <ScriptTextInputControl
        config={{ control_id: "ui.input.script_text.v1", variant: "default", mode: "input" }}
        node={inputNode}
        onSubmit={onSubmit}
        slot="interaction"
      />,
    );

    await userEvent.upload(screen.getByLabelText("上传 Word/TXT"), new File(["武松打虎"], "script.txt", { type: "text/plain" }));
    expect(await screen.findByText("已导入：script.txt")).toBeInTheDocument();
    expect(screen.getByLabelText("剧本内容")).toHaveValue("武松打虎");
    expect(screen.getByLabelText("世界背景")).toHaveValue("水浒传");

    await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));

    expect(onSubmit).toHaveBeenCalledWith({
      script: "武松打虎",
      background: "水浒传",
    });
  });

  it("keeps episode name above background and script fields in script input", () => {
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["script", "episode_name", "background"],
      properties: {
        script: { type: "string", title: "剧本内容" },
        episode_name: { type: "string", title: "集名称" },
        background: { type: "string", title: "世界背景", default: "水浒传" },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-script-episode",
      node_id: "collect_asset_input",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema },
    };

    render(
      <ScriptTextInputControl
        config={{ control_id: "ui.input.script_text.v1", variant: "default", mode: "input" }}
        node={inputNode}
        onSubmit={vi.fn()}
        slot="interaction"
      />,
    );

    const fields = screen.getAllByLabelText(/集名称|世界背景|剧本内容/);
    expect(fields.map((field) => field.getAttribute("aria-label"))).toEqual([
      "集名称",
      "世界背景",
      "剧本内容",
    ]);
    expect(screen.getByLabelText("集名称")).toHaveValue("");
  });

  it("prefills empty episode name from imported script file names", async () => {
    const onSubmit = vi.fn();
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["script", "episode_name", "background"],
      properties: {
        script: { type: "string", title: "剧本内容" },
        episode_name: { type: "string", title: "集名称" },
        background: { type: "string", title: "世界背景", default: "水浒传" },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-script-episode-file",
      node_id: "collect_asset_input",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema },
    };

    render(
      <ScriptTextInputControl
        config={{ control_id: "ui.input.script_text.v1", variant: "default", mode: "input" }}
        node={inputNode}
        onSubmit={onSubmit}
        slot="interaction"
      />,
    );

    await userEvent.upload(screen.getByLabelText("上传 Word/TXT"), new File(["杨志卖刀"], "第12集 杨志卖刀.txt", { type: "text/plain" }));
    expect(await screen.findByDisplayValue("第12集 杨志卖刀")).toBeInTheDocument();
    expect(await screen.findByDisplayValue("杨志卖刀")).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("集名称"));
    await userEvent.type(screen.getByLabelText("集名称"), "手动集名称");
    await userEvent.upload(screen.getByLabelText("上传 Word/TXT"), new File(["宋江题反诗"], "第13集 宋江题反诗.txt", { type: "text/plain" }));

    expect(screen.getByLabelText("集名称")).toHaveValue("手动集名称");
    expect(await screen.findByDisplayValue("宋江题反诗")).toBeInTheDocument();
  });

  it("imports script files by dropping them on the script field", async () => {
    const onSubmit = vi.fn();
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["script", "background"],
      properties: {
        script: { type: "string", title: "剧本内容" },
        background: { type: "string", title: "世界背景", default: "水浒传" },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-script-drop",
      node_id: "collect_asset_input",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema },
    };

    render(
      <ScriptTextInputControl
        config={{ control_id: "ui.input.script_text.v1", variant: "default", mode: "input" }}
        node={inputNode}
        onSubmit={onSubmit}
        slot="interaction"
      />,
    );

    const dropTarget = screen.getByLabelText("剧本内容").closest(".script-textarea-field") as HTMLElement;
    fireEvent.dragOver(dropTarget, {
      dataTransfer: { files: [new File(["鲁智深倒拔垂杨柳"], "drop-script.txt", { type: "text/plain" })] },
    });
    expect(dropTarget).toHaveClass("dragging");
    fireEvent.drop(dropTarget, {
      dataTransfer: { files: [new File(["鲁智深倒拔垂杨柳"], "drop-script.txt", { type: "text/plain" })] },
    });

    expect(await screen.findByText("已导入：drop-script.txt")).toBeInTheDocument();
    expect(screen.getByLabelText("剧本内容")).toHaveValue("鲁智深倒拔垂杨柳");
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
        image_refs: {
          type: "array",
          title: "参考图",
          items: {
            type: "object",
            required: ["kind"],
            properties: {
              kind: { type: "string" },
              asset_id: { type: "string" },
              data: { type: "string" },
              role: { type: "string" },
            },
          },
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
          image_refs: {
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
      image_refs: [{ kind: "asset", asset_id: "asset-1", project_id: "project-1", role: "reference" }],
    });
  });

  it("loads thumbnails for readonly schema form asset image refs", async () => {
    const createObjectUrl = vi.fn(() => "blob:readonly-asset-thumbnail");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const parsed = new URL(String(input), "http://localhost");
      if (parsed.pathname === "/api/assets/asset-1/thumbnail") {
        return Promise.resolve(new Response(new Blob(["png"], { type: "image/png" }), { status: 200, headers: { "Content-Type": "image/png" } }));
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const inputSchema: JsonSchema = {
      type: "object",
      properties: {
        image_refs: {
          type: "array",
          title: "Reference Images",
          items: {
            type: "object",
            properties: {
              kind: { type: "string" },
              asset_id: { type: "string" },
              role: { type: "string" },
            },
          },
        },
      },
    };
    const readonlyNode: TaskNodeExecution = {
      node_execution_id: "exec-readonly-input",
      node_id: "collect_user_input",
      node_ref: "system.user_input.v1",
      status: "succeeded",
      input_snapshot: {
        image_refs: [{ kind: "asset", asset_id: "asset-1", role: "reference" }],
      },
      output_snapshot: null,
      metadata: { input_schema: inputSchema },
    };

    render(
      <SchemaFormControl
        projectId="project-1"
        config={{
          control_id: "ui.input.schema_form.v1",
          variant: "default",
          mode: "readonly",
          options: {
            fields: {
              image_refs: {
                control_id: "ui.input.asset_image_picker.v1",
                variant: "thumbnails",
                mode: "readonly",
                selection_mode: "multiple",
              },
            },
          },
        }}
        node={readonlyNode}
        slot="input"
      />,
    );

    expect(await screen.findByRole("img")).toHaveAttribute("src", "blob:readonly-asset-thumbnail");
    expect(fetchMock).toHaveBeenCalledWith("/api/assets/asset-1/thumbnail?size=256&project_id=project-1", expect.any(Object));
  });

  it("renders prompt count fields side by side without stale help text", () => {
    const inputSchema: JsonSchema = {
      type: "object",
      properties: {
        prompts_per_item: {
          type: "integer",
          title: "每段提示词数",
          default: 1,
        },
        images_per_prompt: {
          type: "integer",
          title: "每个提示词生成图数",
          default: 1,
        },
      },
    };

    render(
      <SchemaFormControl
        projectId="project-1"
        config={{ control_id: "ui.input.schema_form.v1", variant: "default", mode: "input" }}
        node={{
          node_execution_id: "exec-prompt-count-row",
          node_id: "select_episode_metadata",
          node_ref: "system.user_input.v1",
          status: "waiting",
          input_snapshot: null,
          metadata: { input_schema: inputSchema },
        }}
        onSubmit={vi.fn()}
      />,
    );

    const promptCount = screen.getByLabelText("每段提示词数");
    const imageCount = screen.getByLabelText("每个提示词生成图数");
    expect(promptCount.closest(".schema-form-count-row")).toBe(imageCount.closest(".schema-form-count-row"));
    expect(screen.queryByText(/空间深度、物理反馈、建筑陈设/)).not.toBeInTheDocument();
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
        projectId="project-1"
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

  it("renders node user input through schema form and the reusable text asset dropdown", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const parsed = new URL(String(input), "http://localhost");
      if (parsed.pathname === "/api/projects") {
        return jsonResponse({
          items: [
            { project_id: "global", name: "全局项目", owner_user_id: "user-1" },
            { project_id: "project-1", name: "当前项目", owner_user_id: "user-1" },
          ],
        });
      }
      if (parsed.pathname === "/api/assets/tags") {
        return jsonResponse({
          items: [
            { tag_id: "tag-episode", name: "集元数据", scope: "project", project_id: "project-1", asset_count: 1 },
            { tag_id: "tag-character", name: "角色", scope: "project", project_id: "project-1", asset_count: 3 },
          ],
        });
      }
      if (parsed.pathname === "/api/assets/search") {
        return jsonResponse({
          items: [
            {
              asset_id: "asset-episode-23",
              asset_type: "text",
              name: "23、私放晁天王",
              scope: "project",
              project_id: "project-1",
              mime_type: null,
              size_bytes: 0,
              text_content: JSON.stringify({
                episode_name: "23、私放晁天王",
                episode_summary: "宋江私放晁盖，官府追查。",
                source_script: "宋江听闻官府要捉晁盖，连夜报信。",
                asset_catalog: {
                  approved_assets: {
                    characters: [{ name: "宋江" }, { name: "晁盖" }],
                    assets: [{ name: "郓城县" }],
                    props: [{ name: "书信" }],
                  },
                },
                episode_asset_id: "asset-episode-23",
              }),
              metadata: {},
              created_at: "2026-05-31T09:00:00Z",
            },
          ],
        });
      }
      if (parsed.pathname === "/api/assets/asset-episode-23/content") {
        return Promise.resolve(new Response(JSON.stringify({
          episode_name: "23、私放晁天王",
          episode_summary: "宋江私放晁盖，官府追查。",
          source_script: "宋江听闻官府要捉晁盖，连夜报信。",
          asset_catalog: {
            approved_assets: {
              characters: [{ name: "宋江" }, { name: "晁盖" }],
              assets: [{ name: "郓城县" }],
              props: [{ name: "书信" }],
            },
          },
          episode_asset_id: "asset-episode-23",
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }));
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSubmit = vi.fn();
    const inputSchema: JsonSchema = {
      type: "object",
      required: ["episode_asset_id"],
      properties: {
        episode_asset_id: { type: "string", title: "集信息资产" },
        no_material: {
          type: "boolean",
          title: "禁止材质区分",
          default: false,
        },
        enrich_description: {
          type: "boolean",
          title: "丰富画面描述",
          default: false,
        },
      },
    };
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-episode-input",
      node_id: "select_episode_metadata",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema, title: "选择集信息资产" },
    };

    const dropdownConfig: NodeUiControlConfig = {
      control_id: "ui.input.schema_form.v1",
      variant: "default",
      mode: "input",
      options: {
        fields: {
          episode_asset_id: {
            control_id: "ui.input.asset_picker.v1",
            variant: "dropdown",
            mode: "input",
            asset_type: "text",
            search_scope: "project",
            filter_tag_names: ["集元数据"],
            placeholder: "请选择集信息资产",
            preview_control_id: "ui.display.episode_context.v1",
          },
        },
      },
    };
    const assetSearchCallCount = () => fetchMock.mock.calls.filter(([calledUrl]) => {
      const called = new URL(String(calledUrl), "http://localhost");
      return called.pathname === "/api/assets/search";
    }).length;

    const { rerender } = render(
      <SchemaFormControl
        config={dropdownConfig}
        node={inputNode}
        onSubmit={onSubmit}
        projectId="global"
      />,
    );

    const picker = await screen.findByRole("combobox", { name: "集信息资产" });
    expect(picker.closest(".schema-form-primary-row")).toBeInTheDocument();
    const primaryPicker = picker.closest(".schema-form-primary-picker");
    const switchGroup = screen.getByRole("group", { name: "分镜生成选项" });
    expect(primaryPicker).toContainElement(switchGroup);
    expect(primaryPicker?.firstElementChild).toBe(switchGroup);
    const noMaterialSwitch = screen.getByLabelText("禁止材质区分");
    const enrichDescriptionSwitch = screen.getByLabelText("丰富画面描述");
    expect(noMaterialSwitch.closest(".check-field")).toHaveClass("check-field");
    await userEvent.click(noMaterialSwitch);
    await userEvent.click(enrichDescriptionSwitch);
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([calledUrl]) => {
        const called = new URL(String(calledUrl), "http://localhost");
        return called.pathname === "/api/assets/search"
          && called.searchParams.get("asset_type") === "text"
          && called.searchParams.get("scope") === "project"
          && called.searchParams.get("project_id") === "global"
          && called.searchParams.get("tag_names") === "集元数据";
      })).toBe(true);
    });
    await userEvent.clear(picker);
    await userEvent.type(picker, "私放");
    expect(screen.getByRole("option", { name: "23、私放晁天王" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "24、夺命芦苇荡" })).not.toBeInTheDocument();
    const callsAfterInitialLoad = assetSearchCallCount();
    rerender(
      <SchemaFormControl
        config={{ ...dropdownConfig, options: { ...dropdownConfig.options } }}
        node={inputNode}
        onSubmit={onSubmit}
        projectId="global"
      />,
    );
    expect(assetSearchCallCount()).toBe(callsAfterInitialLoad);
    await userEvent.click(screen.getByRole("option", { name: "23、私放晁天王" }));
    expect(await screen.findByRole("heading", { name: "23、私放晁天王" })).toBeInTheDocument();
    expect(screen.getByText(/宋江私放晁盖/)).toBeInTheDocument();
    expect(screen.getByText("晁盖")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));

    expect(onSubmit).toHaveBeenCalledWith({
      episode_asset_id: "asset-episode-23",
      no_material: true,
      enrich_description: true,
    });
  });

  it("renders loaded episode context with summary, script, and asset catalog", () => {
    const nodeExecution: TaskNodeExecution = {
      node_execution_id: "exec-episode-context",
      node_id: "load_episode_metadata",
      node_ref: "tool.episode_metadata_from_asset.v1",
      status: "succeeded",
      input_snapshot: {},
      output_snapshot: {
        episode_name: "24、夺命芦苇荡",
        episode_summary: "何涛率官兵进入芦苇荡，阮氏兄弟设伏取胜。",
        source_script: "何涛领兵来到石碣村。阮小七唱歌诱敌。",
        asset_catalog: {
          approved_assets: {
            characters: [{ name: "何涛" }, { name: "阮小七" }],
            assets: [{ name: "芦苇荡" }],
            props: [{ name: "官船" }],
          },
        },
        episode_asset_id: "asset-episode-24",
      },
      metadata: {},
    };

    render(
      <EpisodeContextControl
        config={{ control_id: "ui.display.episode_context.v1", variant: "summary_catalog", mode: "readonly" }}
        node={nodeExecution}
      />,
    );

    expect(screen.getByRole("heading", { name: "24、夺命芦苇荡" })).toBeInTheDocument();
    expect(screen.getByText(/何涛率官兵进入芦苇荡/)).toBeInTheDocument();
    expect(screen.getByText(/阮小七唱歌诱敌/)).toBeInTheDocument();
    expect(screen.getByText("何涛")).toBeInTheDocument();
    expect(screen.getByText("阮小七")).toBeInTheDocument();
    expect(screen.getByText("芦苇荡")).toBeInTheDocument();
    expect(screen.getByText("官船")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
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
        reference_images: [{ kind: "data_uri", data: "data:image/png;base64,cmVm", role: "reference" }],
        ratio: "wide",
        quality: "final",
      },
      metadata: { input_schema: inputSchema, title: "Submitted parameters" },
    };

    render(
      <SchemaFormControl
        projectId="project-1"
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
    expect(screen.getByRole("img", { name: "参考图" })).toHaveAttribute("src", "data:image/png;base64,cmVm");
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
        projectId="project-1"
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

