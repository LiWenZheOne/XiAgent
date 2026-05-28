import { useMemo, useState } from "react";

import { readBindingValue } from "../resolve";
import type { NodeUiControlProps } from "../types";

interface ImageViewerItem {
  id: string;
  label: string;
  imageUrl: string;
  index: number;
}

export function ImageViewerControl({ config, node }: NodeUiControlProps) {
  const items = useMemo(() => readImageViewerItems(config, node), [config, node]);
  const [activeItem, setActiveItem] = useState<ImageViewerItem | null>(null);

  if (!items.length) {
    return (
      <section className="node-ui-readonly">
        <p className="muted">暂无图片输出</p>
      </section>
    );
  }

  return (
    <section className="node-ui-readonly image-viewer-control" aria-label="图片输出">
      <div className="image-gallery image-viewer-grid">
        {items.map((item) => (
          <button
            aria-label={`查看 ${item.label}`}
            className="image-viewer-thumb"
            key={`${item.id}-${item.index}`}
            type="button"
            onClick={() => setActiveItem(item)}
          >
            <img alt={item.label} src={item.imageUrl} />
            <span>{item.label}</span>
          </button>
        ))}
      </div>
      {activeItem ? (
        <div className="asset-picker-modal" role="dialog" aria-modal="true" aria-label="图片预览">
          <button className="modal-scrim" type="button" onClick={() => setActiveItem(null)} aria-label="关闭预览" />
          <div className="asset-preview-dialog image-viewer-dialog">
            <img src={activeItem.imageUrl} alt={activeItem.label} />
            <div className="button-row image-viewer-actions">
              <a className="secondary-button" href={activeItem.imageUrl} target="_blank" rel="noreferrer">
                打开原图
              </a>
              <button className="secondary-button" type="button" onClick={() => setActiveItem(null)}>
                关闭
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function readImageViewerItems(config: NodeUiControlProps["config"], node: NodeUiControlProps["node"]): ImageViewerItem[] {
  const bindings = config.bindings ?? {};
  const source = readBindingValue(bindings.items_path ?? "$node.output.results", node);
  const items = Array.isArray(source) ? source : [];
  const imageField = bindings.image_url_path ?? "image_url";
  const labelField = bindings.label_path ?? "label";
  return items
    .map((item, index) => normalizeImageViewerItem(item, index, imageField, labelField))
    .filter((item): item is ImageViewerItem => item !== null);
}

function normalizeImageViewerItem(item: unknown, index: number, imageField: string, labelField: string): ImageViewerItem | null {
  if (typeof item !== "object" || item === null) return null;
  const record = item as Record<string, unknown>;
  const imageUrl =
    readStringField(record, imageField) ??
    readStringField(record, "image_url") ??
    readStringField(record, "public_url") ??
    readStringField(record, "url");
  if (!imageUrl) return null;
  const id = readStringField(record, "id") ?? imageUrl;
  const label =
    readStringField(record, labelField) ??
    readStringField(record, "label") ??
    readStringField(record, "name") ??
    `图片 ${index + 1}`;
  return { id, label, imageUrl, index };
}

function readStringField(value: Record<string, unknown>, path: string): string | null {
  const next = readObjectPath(value, path);
  return typeof next === "string" && next ? next : null;
}

function readObjectPath(value: unknown, path: string): unknown {
  if (!path) return value;
  let current = value;
  for (const part of path.split(".")) {
    if (current === null || typeof current !== "object" || Array.isArray(current)) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}
