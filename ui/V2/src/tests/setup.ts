import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { clearAccessToken } from "../api/client";

afterEach(() => {
  cleanup();
  clearAccessToken();
});

class TestEventSource {
  public onmessage: ((event: MessageEvent) => void) | null = null;
  public onerror: (() => void) | null = null;
  public readonly url: string;

  constructor(url: string) {
    this.url = url;
  }

  close() {
    return undefined;
  }
}

Object.defineProperty(window, "EventSource", {
  value: TestEventSource,
  writable: true,
});
