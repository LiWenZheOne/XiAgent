import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { clearAccessToken } from "../api/client";

if (typeof localStorage.removeItem !== "function") {
  const values = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    },
  });
}

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
