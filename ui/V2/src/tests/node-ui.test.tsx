import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApprovalControl } from "../node-ui/controls/ApprovalControl";
import { AssetImageCardsControl } from "../node-ui/controls/AssetImageCardsControl";
import { AssetSummaryTableControl } from "../node-ui/controls/AssetSummaryTableControl";
import { AssetTaskSummaryControl } from "../node-ui/controls/AssetTaskSummaryControl";
import { ControlLibraryPage } from "../node-ui/ControlLibraryPage";
import { ImageChoiceThreeControl } from "../node-ui/controls/ImageChoiceThreeControl";
import { SchemaFormControl } from "../node-ui/controls/SchemaFormControl";
import { ScriptTextInputControl } from "../node-ui/controls/ScriptTextInputControl";
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

  it("renders matched asset cards, generates images locally, and submits after confirmation", async () => {
    const onSubmit = vi.fn();
    const onDraft = vi.fn();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/assets/search")) {
        return jsonResponse({
          items: [
            {
              asset_id: "asset-luzhishen",
              asset_type: "text",
              name: "鲁智深_僧衣",
              scope: "global",
              mime_type: null,
              size_bytes: null,
              metadata: { tags: ["角色"], public_url: "https://cdn.example.com/luzhishen-linked.png" },
              created_at: "2026-05-27T10:00:00Z",
            },
            {
              asset_id: "asset-yazhulin",
              asset_type: "text",
              name: "野猪林",
              scope: "global",
              mime_type: null,
              size_bytes: null,
              metadata: { tags: ["地点"] },
              created_at: "2026-05-27T10:00:00Z",
            },
          ],
        });
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
          },
        });
      }
      return jsonResponse({
        asset_id: "asset-upload-linchong",
        name: "林冲_图像",
        asset_type: "file",
        scope: "global",
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
            full_name: "林冲",
            aliases: ["林教头"],
            summary: "八十万禁军教头，武艺高强。",
            character_status: "被发配沧州途中，身着囚服，面带风霜。",
          },
          {
            full_name: "鲁智深",
            aliases: ["花和尚"],
            summary: "梁山好汉。",
            character_status: "身穿僧衣。",
          },
        ],
        enriched_characters: [
          { full_name: "林冲", matched: true, matched_asset_name: "林冲_默认" },
          { full_name: "鲁智深", matched: false },
        ],
        variant_results: [
          { full_name: "林冲", matched_variant: "默认" },
          { full_name: "鲁智深", new_variant_name: "鲁智深_僧衣" },
        ],
        accessory_results: [
          { full_name: "林冲", reason: "无配件" },
          { full_name: "鲁智深", new_accessories: ["禅杖"] },
        ],
        prompt_results: [
          { full_name: "林冲_默认", prompt: "囚服", reference_image_ref: { kind: "asset", asset_id: "asset-linchong", role: "reference" } },
          { full_name: "鲁智深_僧衣", prompt: "僧衣", reference_image_ref: { kind: "asset", asset_id: "asset-luzhishen", role: "reference" } },
          { full_name: "水火棍", prompt: "生成水火棍道具图", reference_image_ref: { kind: "asset", asset_id: "asset-prop", role: "reference" } },
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
        config={{ control_id: "ui.interaction.asset_image_cards.v1", variant: "grouped_cards", mode: "interactive" }}
        node={cardNode}
        onDraft={onDraft}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByRole("tab", { name: /角色/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /道具/ })).toBeInTheDocument();
    expect(screen.getAllByText("林冲").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("默认")).toBeInTheDocument();
    expect(screen.getByDisplayValue("囚服")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "关联资产" }).length).toBeGreaterThan(0);
    expect(screen.getByText("林冲_默认")).toBeInTheDocument();
    expect(screen.getByDisplayValue("鲁智深")).toBeInTheDocument();
    expect(screen.queryByText("已匹配")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("僧衣")).toBeInTheDocument();
    const missingMatchButtons = screen.getAllByRole("button", { name: "关联资产" });
    await userEvent.click(missingMatchButtons[1]);
    expect(await screen.findByRole("dialog", { name: "选择匹配资产" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /鲁智深_僧衣/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /野猪林/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /鲁智深_僧衣/ }));
    expect(screen.getAllByText("鲁智深_僧衣").length).toBeGreaterThan(0);

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
          asset_key: "林冲",
          image_url: "https://cdn.example.com/generated-linchong.png",
          source: "ai_generated",
        }),
      ]),
    }));
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
    await userEvent.click(screen.getByRole("button", { name: "下载林冲图像" }));
    expect(clickMock).toHaveBeenCalled();
    expect(appendMock).toHaveBeenCalled();
    createElementSpy.mockRestore();
    appendMock.mockRestore();

    await userEvent.click(screen.getByRole("button", { name: "一键入库" }));
    expect(await screen.findByRole("dialog", { name: "缺少资产图像" })).toBeInTheDocument();
    expect(screen.getByText("还有资产没有图像")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "知道了" }));
    expect(screen.queryByRole("dialog", { name: "缺少资产图像" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "资产生成" }));
    await waitFor(() => expect(screen.getByRole("img", { name: "鲁智深 图像" })).toHaveAttribute("src", "https://cdn.example.com/generated-linchong.png"));
    expect(screen.queryByRole("button", { name: "确认并继续" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "一键入库" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      decision: "finish",
      created_asset_ids: expect.arrayContaining(["asset-upload-linchong"]),
      asset_images: expect.arrayContaining([
        expect.objectContaining({
          asset_type: "character",
          asset_key: "林冲",
          full_name: "林冲",
          image_url: "https://cdn.example.com/generated-linchong.png",
          source: "library",
          runninghub_task_id: "rh-1",
        }),
      ]),
      prompt_results: expect.arrayContaining([
        expect.objectContaining({
          asset_key: "林冲",
          full_name: "林冲",
          prompt: "修改后的囚服提示词",
        }),
      ]),
    })));
  });

  it("renders the P3 asset summary table with tabs and submitted image rows", async () => {
    const onSubmit = vi.fn();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/assets/search")) {
        return jsonResponse({
          items: [
            {
              asset_id: "asset-luzhishen",
              asset_type: "text",
              name: "鲁智深",
              scope: "global",
              mime_type: null,
              size_bytes: null,
              metadata: { tags: ["角色"], public_url: "https://cdn.example.com/luzhishen-ref.png" },
              created_at: "2026-05-27T10:00:00Z",
            },
            {
              asset_id: "asset-yazhulin",
              asset_type: "text",
              name: "野猪林资产",
              scope: "global",
              mime_type: null,
              size_bytes: null,
              metadata: { tags: ["地点"] },
              created_at: "2026-05-27T10:00:00Z",
            },
          ],
        });
      }
      if (url === "/api/assets/draft-from-description") {
        return jsonResponse({
          assets: [
            {
              type: "character",
              name: "武松",
              matched: false,
              matched_asset_id: null,
              matched_asset_name: "",
              aliases: "行者",
              summary: "梁山好汉",
              character_status: "途经景阳冈",
              variant_name: "默认",
              variant_description: "劲装短打",
              accessories: "哨棒",
            },
            {
              type: "location",
              name: "官兵船",
              matched: false,
              matched_asset_id: null,
              matched_asset_name: "",
              description: "官兵在水上使用的船只，可作为水面地点资产。",
              location_type: "水上",
              time_of_day: "",
            },
            {
              type: "prop",
              name: "哨棒",
              matched: false,
              matched_asset_id: null,
              matched_asset_name: "",
              description: "武松随身携带的棍棒。",
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
          { full_name: "林冲", aliases: ["林教头"], summary: "禁军教头", character_status: "发配途中" },
        ],
        enriched_characters: [
          { full_name: "林冲", matched: true, matched_asset_name: "林冲_默认" },
        ],
        scenes: [
          { name: "野猪林", description: "密林埋伏地", time_of_day: "白天" },
        ],
        enriched_scenes: [
          { name: "野猪林", matched: false },
        ],
        props: [
          { full_name: "水火棍", description: "差役棍棒", category: "武器" },
        ],
        enriched_props: [
          { full_name: "水火棍", matched: false },
        ],
      },
    };

    render(
      <AssetSummaryTableControl
        config={{ control_id: "ui.interaction.asset_summary_table.v1", variant: "tabbed_table", mode: "interactive" }}
        node={reviewNode}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByRole("tab", { name: /角色/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /地点/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /道具/ })).toBeInTheDocument();
    expect(screen.getByDisplayValue("林冲")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "变体名" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "变体描述" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "林冲_默认" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /道具/ }));
    expect(screen.getByRole("textbox", { name: "水火棍 关联角色" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /地点/ }));
    expect(screen.getByRole("button", { name: "未匹配到对应资产" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /角色/ }));

    await userEvent.click(screen.getByRole("button", { name: "林冲_默认" }));
    expect(await screen.findByRole("dialog", { name: "选择匹配资产" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /鲁智深/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /野猪林资产/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /鲁智深/ }));

    await userEvent.click(screen.getByRole("button", { name: "资产分析" }));
    expect(await screen.findByRole("dialog", { name: "资产分析" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("描述需要新增的资产"), "增加一个拿哨棒的武松、官兵船和哨棒");
    await userEvent.click(screen.getByRole("button", { name: "分析资产" }));
    expect(await screen.findByText("根据用户描述和原文补全多个资产字段。")).toBeInTheDocument();
    expect(screen.getByText("分析出 3 个资产")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "保留修改意见" }));
    expect(screen.queryByDisplayValue("武松")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /地点/ }));
    expect(screen.queryByDisplayValue("官兵船")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /道具/ }));
    expect(screen.queryByDisplayValue("哨棒")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /角色/ }));

    await userEvent.click(screen.getByRole("button", { name: "资产分析" }));
    await userEvent.click(await screen.findByRole("button", { name: "手动新增当前分类空行" }));
    let nameInputs = screen.getAllByLabelText("角色名称");
    await userEvent.type(nameInputs[nameInputs.length - 1], "宋江");
    const deleteButtons = screen.getAllByRole("button", { name: "删除" });
    await userEvent.click(deleteButtons[deleteButtons.length - 1]);
    expect(screen.getAllByLabelText("角色名称")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "确认并继续" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      decision: "approved",
      approved_assets: expect.objectContaining({
        characters: [
          expect.objectContaining({
            name: "林冲",
            matched_asset_name: "鲁智深",
            matched_asset_ref: { kind: "asset", asset_id: "asset-luzhishen", role: "reference" },
            reference_image_ref: { kind: "asset", asset_id: "asset-luzhishen", role: "reference" },
          }),
        ],
        assets: [
          expect.objectContaining({
            name: "野猪林",
            matched: false,
            matched_asset_id: null,
            matched_asset_name: "",
          }),
        ],
      }),
      additional_asset_request: "增加一个拿哨棒的武松、官兵船和哨棒",
      asset_images: [],
    }));
  });

  it("renders the P5 asset task summary and exports image zip", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input) === "https://cdn.example.com/linchong.png") {
        return Promise.resolve({
          ok: true,
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
        echo: {
          created_asset_ids: ["asset-linchong"],
          asset_images: [
            {
              asset_type: "character",
              asset_key: "林冲",
              full_name: "林冲_囚服_佩刀",
              image_url: "https://cdn.example.com/linchong.png",
              source: "library",
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
    expect(screen.getByText("林冲_囚服_佩刀")).toBeInTheDocument();
    expect(screen.getByText("已入库")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "导出为压缩包" }));
    await waitFor(() => expect(clickMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("https://cdn.example.com/linchong.png");
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
              type: "character",
              name: "林冲",
              matched: true,
              matched_asset_id: "asset-linchong",
              matched_asset_name: "林冲_默认",
              summary: "八十万禁军教头",
              character_status: "发配途中",
              variant_name: "囚服",
              variant_description: "身着囚服，头戴旧毡笠。",
            },
          ],
          assets: [
            {
              type: "asset",
              name: "野猪林",
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
              type: "prop",
              name: "水火棍",
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
            asset_key: "character:林冲",
            full_name: "林冲",
            image_url: "https://cdn.example.com/linchong.png",
            source: "manual_upload",
          },
        ],
      },
    };

    render(
      <AssetSummaryTableControl
        config={{ control_id: "ui.interaction.asset_summary_table.v1", variant: "tabbed_table", mode: "readonly" }}
        node={reviewNode}
      />,
    );

    expect(screen.getAllByText("林冲").length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: "操作" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "变体名" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "变体描述" })).toBeInTheDocument();
    expect(screen.getByText("囚服")).toBeInTheDocument();
    expect(screen.getByText("身着囚服，头戴旧毡笠。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "林冲_默认" })).toBeInTheDocument();
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
      image_refs: [{ kind: "asset", asset_id: "asset-1", role: "reference" }],
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
        reference_images: [{ kind: "data_uri", data: "data:image/png;base64,cmVm", role: "reference" }],
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
