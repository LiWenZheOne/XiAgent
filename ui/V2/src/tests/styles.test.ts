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

  it("uses masonry columns for variable-height node image previews", () => {
    expect(selectorRule(".image-gallery")).toContain("column-width");
    expect(selectorRule(".image-gallery")).toContain("column-gap");
    expect(css).toMatch(/\.image-gallery img\s*\{[^}]*break-inside:\s*avoid/s);
    expect(selectorRule(".image-viewer-thumb")).toContain("break-inside: avoid");
    expect(selectorRule(".asset-image-card-grid")).toContain("column-width");
    expect(selectorRule(".asset-image-card")).toContain("break-inside: avoid");
  });

  it("uses masonry columns for variable-height control library cards", () => {
    expect(selectorRule(".control-grid")).toContain("column-width");
    expect(selectorRule(".control-grid")).toContain("column-gap");
    expect(selectorRule(".control-card")).toContain("break-inside: avoid");
    expect(selectorRule(".control-card")).toContain("margin: 0 0 14px");
  });

  it("keeps asset image picker actions reachable while the asset grid scrolls", () => {
    expect(selectorRule(".asset-image-picker-dialog")).toContain("grid-template-rows");
    expect(selectorRule(".asset-image-picker-dialog .asset-picker-body")).toContain("min-height: 0");
    expect(selectorRule(".asset-image-picker-dialog .asset-picker-results")).toContain("overflow: auto");
    expect(selectorRule(".asset-image-picker-dialog .asset-check-grid")).toContain("align-content: start");
    expect(selectorRule(".asset-image-picker-dialog > .asset-picker-footer")).toContain("position: sticky");
    expect(selectorRule(".asset-image-picker-dialog > .asset-picker-footer")).toContain("bottom: 0");
  });
});
