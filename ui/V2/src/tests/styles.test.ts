/// <reference types="vite/client" />

import { describe, expect, it } from "vitest";

import css from "../styles/app.css?raw";

function selectorRule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
  const match = css.match(new RegExp(`${escaped}\\s*\\{(?<body>[^}]*)\\}`, "s"));
  return match?.groups?.body ?? "";
}

describe("V2 CSS safeguards", () => {
  it("keeps asset thumbnails inside cards when asset names are long", () => {
    expect(selectorRule(".asset-card")).toContain("min-width: 0");
    expect(selectorRule(".asset-card")).toContain("overflow: hidden");
    expect(selectorRule(".asset-card img")).toContain("display: block");
    expect(selectorRule(".asset-card img")).toContain("max-width: 100%");
    expect(selectorRule(".asset-card strong, .asset-card small")).toContain("overflow-wrap: anywhere");
  });

  it("keeps long asset detail names from creating horizontal page overflow", () => {
    expect(selectorRule(".asset-layout")).toContain("min-width: 0");
    expect(selectorRule(".asset-list-panel, .asset-detail-panel")).toContain("min-width: 0");
    expect(selectorRule(".asset-detail-panel h3")).toContain("overflow-wrap: anywhere");
  });
});
