import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SchemaFormControl } from "../node-ui/controls/SchemaFormControl";
import type { JsonSchema, NodeUiControlConfig, TaskNodeExecution } from "../api/types";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("asset image picker layout", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("marks the image picker dialog so the asset grid scrolls without hiding actions", async () => {
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
      if (parsed.pathname === "/api/assets/collections" || parsed.pathname === "/api/assets/tags") {
        return jsonResponse({ items: [] });
      }
      if (parsed.pathname === "/api/assets/search") {
        return jsonResponse({
          items: Array.from({ length: 12 }, (_, index) => ({
            asset_id: `asset-${index + 1}`,
            asset_type: "file",
            name: `参考图 ${index + 1}`,
            scope: "project",
            project_id: "project-1",
            mime_type: "image/png",
            size_bytes: 1024,
            metadata: { public_url: `https://cdn.example.com/ref-${index + 1}.png` },
            created_at: "2026-06-08T09:00:00Z",
          })),
        });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    const inputSchema: JsonSchema = {
      type: "object",
      properties: {
        image_refs: {
          type: "array",
          title: "参考图",
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
    const inputNode: TaskNodeExecution = {
      node_execution_id: "exec-input",
      node_id: "collect_user_input",
      node_ref: "system.user_input.v1",
      status: "waiting",
      input_snapshot: {},
      output_snapshot: null,
      metadata: { input_schema: inputSchema, title: "启动参数" },
    };
    const config: NodeUiControlConfig = {
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

    render(<SchemaFormControl config={config} node={inputNode} onSubmit={vi.fn()} projectId="project-1" />);

    await userEvent.click(screen.getByRole("button", { name: "选择图片" }));
    const dialog = await screen.findByRole("dialog", { name: "选择资产图片" });
    const panel = dialog.querySelector(".asset-image-picker-dialog");

    expect(panel).toBeInTheDocument();
    expect(panel?.querySelector(".asset-picker-body")).toBeInTheDocument();
    expect(panel?.querySelector(".asset-picker-results")).toBeInTheDocument();
    expect(panel?.querySelector(".asset-picker-footer")).toContainElement(screen.getByRole("button", { name: "确认选择" }));
  });
});
