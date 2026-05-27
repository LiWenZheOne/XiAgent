import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ImageChoiceThreeControl } from "../node-ui/controls/ImageChoiceThreeControl";
import { getNodeUiControl, resolveNodeInteractionConfig } from "../node-ui/registry";
import type { NodeUiControlConfig, TaskNodeExecution } from "../api/types";

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

describe("node-ui controls", () => {
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

  it("uses default user choice control when workflow has no explicit ui config", () => {
    const resolved = resolveNodeInteractionConfig(node);
    const Control = getNodeUiControl(resolved?.control_id ?? "");

    expect(resolved?.control_id).toBe("ui.choice.image_three.v1");
    render(<Control config={resolved!} node={node} preview />);

    expect(screen.getByLabelText("图片三选一")).toBeInTheDocument();
  });

  it("keeps unknown controls on the fallback path", async () => {
    const Control = getNodeUiControl("ui.unknown.v1");

    render(<Control config={{ control_id: "ui.unknown.v1" }} node={node} />);

    await waitFor(() => {
      expect(screen.getByText(/尚未在 V2 注册/)).toBeInTheDocument();
    });
  });
});
