import { afterEach, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "../api/client";
import { streamTaskEvents } from "../api/tasks";

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
