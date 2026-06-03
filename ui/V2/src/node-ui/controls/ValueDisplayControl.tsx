import { extractImageUrls, formatFieldLabel, humanizeValue } from "../../utils/display";
import type { NodeUiControlProps } from "../types";

export function ValueDisplayControl({ value, node, imageAltPrefix, slot }: NodeUiControlProps) {
  const displayValue = value === undefined ? node.output_snapshot : value;
  const summary = humanizeValue(displayValue);
  const promptPreview = slot === "input" && isAiNode(node.node_ref ?? node.ref) ? readPromptPreview(displayValue) : null;

  return (
    <section className="node-ui-readonly">
      {promptPreview ? <LlmPromptPreview preview={promptPreview} /> : null}
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

  const entries = summary.entries.filter(([key]) => !isTransportUrlKey(key));

  return (
    <div className="value-stack">
      {entries.length ? (
        <dl className="field-list">
          {entries.map(([key, child]) => (
            <div key={key}>
              <dt>{formatFieldLabel(key)}</dt>
              <dd>
                {isImageOnly(child) ? (
                  <ImageGallery urls={extractImageUrls(child)} altPrefix={imageAltPrefix || `${nodeId} ${formatFieldLabel(key)}图片`} />
                ) : (
                  <ValueView value={child} nodeId={nodeId} imageAltPrefix={`${nodeId} ${formatFieldLabel(key)}图片`} />
                )}
              </dd>
            </div>
          ))}
        </dl>
      ) : isImageOnly(value) ? (
        <ImageGallery urls={extractImageUrls(value)} altPrefix={imageAltPrefix || `${nodeId} 图片`} />
      ) : (
        <p className="value-text">{summary.text}</p>
      )}
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

interface PromptPreview {
  system?: string;
  prompt?: string;
  promptTemplate?: string;
  renderedPrompts: string[];
}

function LlmPromptPreview({ preview }: { preview: PromptPreview }) {
  return (
    <div className="llm-prompt-preview" aria-label="LLM 提示词">
      <div className="llm-prompt-preview-head">
        <span>LLM 提示词</span>
        <small>{preview.renderedPrompts.length ? `${preview.renderedPrompts.length} 次调用` : "单次调用"}</small>
      </div>
      {preview.system ? <PromptBlock title="System" text={preview.system} /> : null}
      {preview.prompt ? <PromptBlock title="Prompt" text={preview.prompt} /> : null}
      {preview.promptTemplate ? <PromptBlock title="Prompt Template" text={preview.promptTemplate} /> : null}
      {preview.renderedPrompts.map((prompt, index) => (
        <PromptBlock key={`${index}-${prompt.slice(0, 24)}`} title={`实际提示词 ${index + 1}`} text={prompt} />
      ))}
    </div>
  );
}

function PromptBlock({ title, text }: { title: string; text: string }) {
  return (
    <details className="llm-prompt-block" open={title !== "System"}>
      <summary>{title}</summary>
      <pre>{text}</pre>
    </details>
  );
}

function readPromptPreview(value: unknown): PromptPreview | null {
  if (!isRecord(value)) return null;
  const system = readNonEmptyString(value.system);
  const prompt = readNonEmptyString(value.prompt);
  const promptTemplate = readNonEmptyString(value.prompt_template);
  const renderedPrompts = promptTemplate ? renderPromptTemplate(promptTemplate, value.items) : [];

  if (!system && !prompt && !promptTemplate && !renderedPrompts.length) return null;
  return { system, prompt, promptTemplate, renderedPrompts };
}

function renderPromptTemplate(template: string, items: unknown): string[] {
  if (!Array.isArray(items)) return [];
  return items.slice(0, 20).map((item) => renderPromptForItem(template, item));
}

function renderPromptForItem(template: string, item: unknown): string {
  if (!isRecord(item)) return template.split("{item}").join(stableStringify(item));
  const values = templateValues(item);
  values.item = stableStringify(item);
  return template.replace(/\{([A-Za-z_][A-Za-z0-9_.]*)\}/g, (match, key: string) => {
    const value = values[key];
    return value === undefined ? match : value;
  });
}

function templateValues(value: Record<string, unknown>): Record<string, string> {
  const values: Record<string, string> = {};
  const visit = (prefix: string, current: unknown) => {
    if (isRecord(current)) {
      if (prefix) values[prefix] = templateValue(current);
      for (const [key, item] of Object.entries(current)) {
        if (!key) continue;
        const nextKey = prefix ? `${prefix}.${key}` : key;
        visit(nextKey, item);
        if (prefix === "shared_context" && !isRecord(item)) {
          values[key] ??= templateValue(item);
        }
        if (prefix.endsWith("prompt_rules")) {
          values[key] ??= templateValue(item);
        }
      }
      return;
    }
    values[prefix] = templateValue(current);
  };
  visit("", value);
  return values;
}

function templateValue(value: unknown): string {
  return typeof value === "string" ? value : stableStringify(value);
}

function stableStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function readNonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function isAiNode(ref: unknown): boolean {
  return typeof ref === "string" && ref.startsWith("ai.");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
