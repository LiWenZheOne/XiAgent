import { extractImageUrls, formatFieldLabel, humanizeValue } from "../../utils/display";
import type { NodeUiControlProps } from "../types";

export function ValueDisplayControl({ value, node, imageAltPrefix }: NodeUiControlProps) {
  const displayValue = value === undefined ? node.output_snapshot : value;
  const summary = humanizeValue(displayValue);

  return (
    <section className="node-ui-readonly">
      <ValueView value={displayValue} nodeId={node.node_id} imageAltPrefix={imageAltPrefix || `${node.node_id} 图片`} />
      {summary.kind === "empty" ? <p className="muted">暂无内容</p> : null}
    </section>
  );
}

function ValueView({ value, nodeId, imageAltPrefix }: { value: unknown; nodeId: string; imageAltPrefix: string }) {
  const summary = humanizeValue(value);
  if (summary.kind === "empty") return null;
  if (summary.kind === "text" || summary.kind === "number" || summary.kind === "boolean") {
    return <p className="value-text">{summary.text}</p>;
  }

  const images = extractImageUrls(value);
  const entries = summary.entries.filter(([key, child]) => !isTransportUrlKey(key) && !isImageOnly(child));

  return (
    <div className="value-stack">
      {images.length ? <ImageGallery urls={images} altPrefix={imageAltPrefix || `${nodeId} 图片`} /> : null}
      {entries.length ? (
        <dl className="field-list">
          {entries.map(([key, child]) => (
            <div key={key}>
              <dt>{formatFieldLabel(key)}</dt>
              <dd>
                {extractImageUrls(child).length ? (
                  <ImageGallery urls={extractImageUrls(child)} altPrefix={`${nodeId} ${formatFieldLabel(key)}图片`} />
                ) : (
                  <ValueView value={child} nodeId={nodeId} imageAltPrefix={`${nodeId} ${formatFieldLabel(key)}图片`} />
                )}
              </dd>
            </div>
          ))}
        </dl>
      ) : !images.length ? (
        <p className="value-text">{summary.text}</p>
      ) : null}
    </div>
  );
}

function ImageGallery({ urls, altPrefix }: { urls: string[]; altPrefix: string }) {
  return (
    <div className="image-gallery">
      {urls.map((url, index) => (
        <img alt={`${altPrefix} ${index + 1}`} key={url} src={url} />
      ))}
    </div>
  );
}

function isTransportUrlKey(key: string): boolean {
  return ["public_url", "url", "thumbnail_url", "storage_uri"].includes(key);
}

function isImageOnly(value: unknown): boolean {
  if (!extractImageUrls(value).length) return false;
  const summary = humanizeValue(value);
  if (!summary.entries.length) return true;
  return summary.entries.every(([key, child]) => isTransportUrlKey(key) || isImageOnly(child));
}
