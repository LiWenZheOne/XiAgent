import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "../api/client";
import { App } from "../app/App";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("session recovery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("returns to login when a stored token is no longer authorized", async () => {
    setAccessToken("stale-token");
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ detail: "Access token is missing or invalid" }, 401)));

    render(<App />);

    await waitFor(() => {
      expect(localStorage.getItem("xiagent.v2.access_token")).toBeNull();
    });
    expect(screen.getByRole("heading", { name: "登录 XiAgent" })).toBeInTheDocument();
    expect(screen.queryByText(/Access token is missing or invalid/)).not.toBeInTheDocument();
  });
});
