import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest, ApiError } from "../api/client";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("maps backend method errors to a user-facing message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "Method Not Allowed" }), {
            status: 405,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );

    await expect(apiRequest("/api/tasks")).rejects.toMatchObject({
      name: ApiError.name,
      status: 405,
      message: "当前服务暂时不支持这个操作，请刷新后重试。",
    });
  });
});
