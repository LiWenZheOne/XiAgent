import { afterEach, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "../api/client";
import {
  deleteTask,
  draftTaskAssetFromDescription,
  generateTaskAssetImage,
  generateTaskStoryboardPanelImage,
  regenerateTaskStoryboardPanelPrompt,
  streamTaskEvents,
} from "../api/tasks";

describe("task event stream", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setAccessToken(null);
  });

  it("streams task events with the current access token", async () => {
    setAccessToken("task-token");
    const eventBody = new TextEncoder().encode('event: node_succeeded\ndata: {"node_id":"n1"}\n\n');
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(eventBody);
        controller.close();
      },
    });
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit): Promise<Response> =>
      Promise.resolve(
        new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const onEvent = vi.fn();
    const stop = streamTaskEvents("project-1", "task-1", onEvent);

    await vi.waitFor(() => {
      expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ event_type: "node_succeeded" }));
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/task-1/stream?project_id=project-1",
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = init?.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer task-token");

    stop();
  });
});

describe("task deletion api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setAccessToken(null);
  });

  it("deletes a task with the current project and access token", async () => {
    setAccessToken("task-token");
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit): Promise<Response> =>
      Promise.resolve(
        new Response(JSON.stringify({ deleted: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await deleteTask("project-1", "task-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/task-1?project_id=project-1",
      expect.objectContaining({
        method: "DELETE",
        headers: expect.any(Headers),
      }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = init?.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer task-token");
  });
});

describe("task ai interaction api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setAccessToken(null);
  });

  it("routes workflow AI actions through task interaction endpoints", async () => {
    setAccessToken("task-token");
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      if (url.endsWith("/asset-draft")) {
        return jsonResponse({ assets: [], confidence: 0.8, reasoning: "ok" });
      }
      if (url.endsWith("/generate-asset-image") || url.endsWith("/storyboard-panel-image")) {
        return jsonResponse({ image_url: "https://cdn.example.com/generated.png", source: "ai_generated" });
      }
      if (url.endsWith("/storyboard-panel-prompt")) {
        return jsonResponse({ card: { card_id: "segment-0" }, segment_description: { panel_count: 1 } });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    await draftTaskAssetFromDescription("task-1", {
      project_id: "project-1",
      node_id: "review_assets",
      description: "补一个角色",
      current_assets: { characters: [] },
    });
    await generateTaskAssetImage("task-1", {
      project_id: "project-1",
      node_id: "upload_images",
      prompt_result: { asset_name: "林冲", prompt: "囚服" },
    });
    await generateTaskStoryboardPanelImage("task-1", {
      project_id: "project-1",
      node_id: "review_storyboard_image",
      card_id: "segment-0",
      prompt: "分镜提示词",
      image_refs: [{ kind: "data_uri", data: "data:image/png;base64,cmVm" }],
    });
    await regenerateTaskStoryboardPanelPrompt("task-1", {
      project_id: "project-1",
      node_id: "review_storyboard_image",
      card: { card_id: "segment-0" },
      item: { index: 0, panel_count: "1" },
    });

    const calls = fetchMock.mock.calls.map(([url, init]) => ({
      url: String(url),
      init: init as RequestInit,
      body: JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>,
    }));
    expect(calls.map((call) => call.url)).toEqual([
      "/api/tasks/task-1/interactions/asset-draft",
      "/api/tasks/task-1/interactions/generate-asset-image",
      "/api/tasks/task-1/interactions/storyboard-panel-image",
      "/api/tasks/task-1/interactions/storyboard-panel-prompt",
    ]);
    for (const call of calls) {
      expect(call.init.method).toBe("POST");
      expect((call.init.headers as Headers).get("Authorization")).toBe("Bearer task-token");
      expect(call.body.project_id).toBe("project-1");
      expect(call.body.node_id).toBeDefined();
    }
  });
});

function jsonResponse(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
