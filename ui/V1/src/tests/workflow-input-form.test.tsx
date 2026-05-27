import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WorkflowInputForm } from "../task/WorkflowInputForm";

describe("WorkflowInputForm", () => {
  it("writes selected asset public URL into image_urls", async () => {
    const onSubmit = vi.fn();
    render(
      <WorkflowInputForm
        schema={{
          type: "object",
          required: ["prompt", "image_urls"],
          properties: {
            prompt: { type: "string" },
            image_urls: { type: "array", items: { type: "string" } },
          },
        }}
        assets={[
          {
            asset_id: "asset_1",
            asset_type: "file",
            name: "hero.png",
            scope: "project",
            mime_type: "image/png",
            size_bytes: 12,
            metadata: { public_url: "https://cdn.example.test/hero.png" },
            created_at: "2026-05-26T00:00:00Z",
          },
        ]}
        onSubmit={onSubmit}
      />,
    );

    await userEvent.type(screen.getByLabelText("prompt"), "改成电影海报风格");
    await userEvent.click(screen.getByRole("button", { name: /选择 hero\.png/ }));
    await userEvent.click(screen.getByRole("button", { name: "创建并运行" }));

    expect(onSubmit).toHaveBeenCalledWith({
      prompt: "改成电影海报风格",
      image_urls: ["https://cdn.example.test/hero.png"],
    });
  });
});
