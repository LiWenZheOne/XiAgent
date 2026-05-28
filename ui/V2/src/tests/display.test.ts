import { describe, expect, it } from "vitest";

import {
  buildSchemaFields,
  extractImageUrls,
  formatFieldLabel,
  humanizeValue,
  nodeDisplayKind,
  statusLabel,
} from "../utils/display";

describe("display helpers", () => {
  it("turns workflow schema fields into user-facing labels without exposing schema words", () => {
    const fields = buildSchemaFields({
      type: "object",
      required: ["topic", "image_urls"],
      properties: {
        topic: { type: "string", title: "创作主题" },
        image_urls: { type: "array", items: { type: "string" } },
        draft_count: { type: "integer", default: 3 },
      },
    });

    expect(fields.map((field) => field.label)).toEqual(["创作主题", "参考图片", "草稿数量"]);
    expect(fields.find((field) => field.key === "image_urls")?.control).toBe("asset_images");
    expect(JSON.stringify(fields)).not.toContain("input_schema");
  });

  it("uses schema enum values for fixed-value controls and does not infer business options by field name", () => {
    const fields = buildSchemaFields({
      type: "object",
      required: ["resolution"],
      properties: {
        aspectRatio: {
          type: "string",
          enum: ["1:1", "16:9", "9:16", "4:3"],
        },
        resolution: {
          type: "string",
          enum: ["1k", "2k", "4k"],
        },
        prompt: {
          type: "string",
        },
      },
    });

    expect(fields.find((field) => field.key === "aspectRatio")).toMatchObject({
      label: "画面比例",
      control: "select",
      placeholder: "请选择画面比例",
    });
    expect(fields.find((field) => field.key === "resolution")).toMatchObject({
      label: "清晰度",
      required: true,
      control: "choice_group",
      placeholder: "请选择清晰度",
    });
    expect(fields.find((field) => field.key === "resolution")?.helpText).toContain("可选值：1k、2k、4k");
    expect(fields.find((field) => field.key === "prompt")?.placeholder).toBe("请输入提示词");

    const fieldsWithoutEnum = buildSchemaFields({
      type: "object",
      properties: {
        aspectRatio: { type: "string" },
        resolution: { type: "string" },
      },
    });
    expect(fieldsWithoutEnum.find((field) => field.key === "aspectRatio")?.control).toBe("text");
    expect(fieldsWithoutEnum.find((field) => field.key === "resolution")?.control).toBe("text");
  });

  it("summarizes nested outputs as readable field groups instead of raw JSON", () => {
    const summary = humanizeValue({
      selected_image: "https://cdn.example.com/final.png",
      usage: { prompt_tokens: 12, completion_tokens: 8 },
      notes: ["可用", "已发布"],
    });

    expect(summary.kind).toBe("object");
    expect(summary.text).toContain("3 个字段");
    expect(summary.text).not.toContain("{");
    expect(summary.text).not.toContain("}");
  });

  it("extracts displayable image urls from node outputs", () => {
    const urls = extractImageUrls({
      results: [
        { public_url: "https://cdn.example.com/a.png" },
        { url: "https://cdn.example.com/b.jpg" },
        { url: "https://cdn.example.com/c.svg" },
      ],
      ignored: "not-an-image",
    });

    expect(urls).toEqual(["https://cdn.example.com/a.png", "https://cdn.example.com/b.jpg", "https://cdn.example.com/c.svg"]);
  });

  it("uses Chinese status labels and readable snake case labels", () => {
    expect(statusLabel("task_waiting")).toBe("等待用户");
    expect(statusLabel("node_succeeded")).toBe("成功");
    expect(formatFieldLabel("current_node_id")).toBe("当前节点");
  });
  it("turns English workflow labels into user-facing Chinese labels", () => {
    const fields = buildSchemaFields({
      type: "object",
      properties: {
        script: { type: "string", title: "Script" },
        generate_assets: { type: "string", title: "Generate Assets" },
        template_image_url: { type: "string", title: "Template Image Url", format: "uri" },
      },
    });

    expect(fields.map((field) => field.label)).toEqual(["剧本", "生成方式", "模板图片地址"]);
    expect(fields.find((field) => field.key === "template_image_url")?.control).toBe("asset_images");
  });

  it("keeps completed human input nodes labeled as user input", () => {
    expect(
      nodeDisplayKind(
        {
          node_id: "ask_color",
          node_ref: "system.human_approval.v1",
          status: "succeeded",
        },
        {
          nodes: [
            {
              id: "ask_color",
              ref: "system.human_approval.v1",
              outputs: {
                type: "object",
                required: ["answer"],
                properties: { answer: { type: "string" } },
              },
            },
          ],
        },
      ),
    ).toBe("用户输入");
  });
});
