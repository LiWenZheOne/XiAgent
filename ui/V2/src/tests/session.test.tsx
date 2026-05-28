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

  it("recovers the current username from the authenticated API session", async () => {
    setAccessToken("valid-token");
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/me") {
        return jsonResponse({ user_id: "user-1", username: "alice" });
      }
      if (url === "/api/projects") {
        return jsonResponse({
          items: [
            { project_id: "global", name: "全局项目", owner_user_id: "system" },
          ],
        });
      }
      if (url === "/api/tasks?project_id=global") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/auth/me", expect.anything());
    });
    expect(await screen.findByText("alice")).toBeInTheDocument();
    expect(screen.queryByText("已登录用户")).not.toBeInTheDocument();
  });
});
