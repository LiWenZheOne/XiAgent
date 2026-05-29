import { type ChangeEvent, type DragEvent, useEffect, useMemo, useState } from "react";

import type { JsonSchema, WorkflowNodeSpec } from "../../api/types";
import type { NodeUiControlProps } from "../types";

type FormValue = string | number | Record<string, unknown>;

const SCRIPT_FIELD = "script";
const BACKGROUND_FIELD = "background";

export function ScriptTextInputControl({ busy, config, node, nodeSpec, slot, value, onSubmit }: NodeUiControlProps) {
  const metadataSchema = node.metadata?.input_schema;
  const fields = useMemo(() => scriptFields(node, nodeSpec, slot), [metadataSchema, nodeSpec?.inputs, nodeSpec?.outputs, slot]);
  const fieldSignature = useMemo(() => fields.map((field) => `${field.key}:${field.label}:${field.required}`).join("|"), [fields]);
  const readonly = config.mode === "readonly" || !onSubmit;
  const renderedValues = readonly ? valuesFromPayload(fields, value ?? readonlySnapshotValue(node, slot)) : undefined;
  const submitInStageHeader = config.options?.submit_placement === "stage_header";
  const formId = typeof config.options?.form_id === "string" ? config.options.form_id : scriptInputFormId(node);
  const [values, setValues] = useState<Record<string, FormValue>>(() => initialValues(fields));
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const script = String((readonly ? renderedValues?.[SCRIPT_FIELD] : values[SCRIPT_FIELD]) ?? "");
  const background = String((readonly ? renderedValues?.[BACKGROUND_FIELD] : values[BACKGROUND_FIELD]) ?? "");
  const otherFields = fields.filter((field) => field.key !== SCRIPT_FIELD && field.key !== BACKGROUND_FIELD);

  useEffect(() => {
    setValues(initialValues(fields));
    setMessage("");
    setError("");
  }, [fieldSignature]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || readonly || busy) return;
    await importScriptFile(file);
  }

  async function importScriptFile(file: File) {
    setMessage(`正在导入：${file.name}`);
    setError("");
    try {
      const text = await readScriptFile(file);
      if (!text.trim()) throw new Error("文件内容为空，请检查文件或直接粘贴文本。");
      setValues((current) => ({ ...current, [SCRIPT_FIELD]: text }));
      setMessage(`已导入：${file.name}`);
    } catch (nextError) {
      setError(readableError(nextError, "文件读取失败，请改为粘贴文本。"));
    }
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    if (readonly || busy) return;
    event.preventDefault();
    setDragging(true);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    if (readonly || busy) return;
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void importScriptFile(file);
  }

  function submit() {
    if (busy || readonly) return;
    if (!String(values[SCRIPT_FIELD] ?? "").trim()) {
      setError("请填写剧本内容。");
      return;
    }
    setError("");
    onSubmit?.(buildSubmitData(fields, values));
  }

  return (
    <form className="interaction-panel script-input-control" id={formId} onSubmit={(event) => {
      event.preventDefault();
      submit();
    }}>
      <div className="script-input-head">
        <div>
          <p className="eyebrow">{readonly ? "参数快照" : "剧本输入"}</p>
          <h3>剧本输入</h3>
        </div>
      </div>

      <div className="script-input-grid">
        <label className="form-field">
          <span>{fieldLabel(fields, BACKGROUND_FIELD, "世界背景")}</span>
          <input
            aria-label="世界背景"
            placeholder="例如：水浒传"
            readOnly={readonly || Boolean(busy)}
            value={background}
            onChange={(event) => setValues((current) => ({ ...current, [BACKGROUND_FIELD]: event.target.value }))}
          />
        </label>

        <div
          className={dragging ? "form-field script-textarea-field dragging" : "form-field script-textarea-field"}
          onDragLeave={() => setDragging(false)}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <div className="script-field-head">
            <span>{fieldLabel(fields, SCRIPT_FIELD, "剧本内容")}</span>
            {!readonly ? (
              <label className="secondary-button script-file-button">
                上传 Word/TXT
                <input accept=".txt,.text,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={busy} type="file" onChange={handleFileChange} />
              </label>
            ) : null}
          </div>
          <textarea
            aria-label="剧本内容"
            placeholder="粘贴剧本文本，或拖入 / 上传 .txt、.docx 后自动填入"
            readOnly={readonly || Boolean(busy)}
            value={script}
            onChange={(event) => setValues((current) => ({ ...current, [SCRIPT_FIELD]: event.target.value }))}
          />
          <small>{script.length} 字符</small>
        </div>

        {otherFields.map((field) => (
          <label className="form-field" key={field.key}>
            <span>{field.label}</span>
            <input
              aria-label={field.label}
              readOnly={readonly || Boolean(busy)}
              type={field.schema.type === "integer" || field.schema.type === "number" ? "number" : "text"}
              value={String((readonly ? renderedValues?.[field.key] : values[field.key]) ?? "")}
              onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
            />
          </label>
        ))}
      </div>

      {message ? <p className="form-success">{message}</p> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!readonly && !submitInStageHeader ? (
        <button className="primary-button" disabled={busy} type="submit">
          {busy ? "提交中" : "提交并继续"}
        </button>
      ) : null}
    </form>
  );
}

function scriptInputFormId(node: NodeUiControlProps["node"]): string {
  return `xiagent-node-input-${node.node_execution_id ?? node.node_id}`;
}

async function readScriptFile(file: File): Promise<string> {
  const lowerName = file.name.toLowerCase();
  if (lowerName.endsWith(".txt") || file.type === "text/plain") return readBlobText(file);
  if (lowerName.endsWith(".docx")) return readDocxText(file);
  throw new Error("仅支持 .txt 和 .docx 文件。");
}

function readBlobText(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("文件读取失败。"));
    reader.readAsText(file);
  });
}

function readBlobArrayBuffer(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === "function") return file.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) resolve(reader.result);
      else reject(new Error("文件读取失败。"));
    };
    reader.onerror = () => reject(reader.error ?? new Error("文件读取失败。"));
    reader.readAsArrayBuffer(file);
  });
}

async function readDocxText(file: File): Promise<string> {
  if (typeof DecompressionStream === "undefined") {
    throw new Error("当前浏览器暂不支持直接解析 Word，请另存为 txt 或粘贴文本。");
  }
  const buffer = await readBlobArrayBuffer(file);
  const entry = await findZipEntry(buffer, "word/document.xml");
  if (!entry) throw new Error("未在 Word 文件中找到正文。");
  const xml = new TextDecoder("utf-8").decode(entry);
  return xml
    .replace(/<w:tab\/>/g, "\t")
    .replace(/<\/w:p>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function findZipEntry(buffer: ArrayBuffer, wantedName: string): Promise<Uint8Array | null> {
  const view = new DataView(buffer);
  let offset = 0;
  while (offset + 30 <= buffer.byteLength) {
    if (view.getUint32(offset, true) !== 0x04034b50) break;
    const compression = view.getUint16(offset + 8, true);
    const compressedSize = view.getUint32(offset + 18, true);
    const fileNameLength = view.getUint16(offset + 26, true);
    const extraLength = view.getUint16(offset + 28, true);
    const nameStart = offset + 30;
    const dataStart = nameStart + fileNameLength + extraLength;
    const name = new TextDecoder("utf-8").decode(new Uint8Array(buffer, nameStart, fileNameLength));
    if (dataStart + compressedSize > buffer.byteLength) break;
    const compressed = new Uint8Array(buffer, dataStart, compressedSize);
    if (name === wantedName) {
      if (compression === 0) return compressed;
      if (compression === 8) return inflateRaw(compressed);
      throw new Error("暂不支持该 Word 压缩格式。");
    }
    offset = dataStart + compressedSize;
  }
  return null;
}

async function inflateRaw(bytes: Uint8Array): Promise<Uint8Array> {
  const input = new Uint8Array(bytes.byteLength);
  input.set(bytes);
  const stream = new Blob([input.buffer]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  const chunks: Uint8Array[] = [];
  const reader = stream.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  const size = chunks.reduce((total, chunk) => total + chunk.byteLength, 0);
  const output = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output;
}

interface ScriptField {
  key: string;
  label: string;
  required: boolean;
  schema: JsonSchema;
}

function scriptFields(node: NodeUiControlProps["node"], nodeSpec: WorkflowNodeSpec | undefined, slot: NodeUiControlProps["slot"]): ScriptField[] {
  const schema = resolveInputSchema(node, nodeSpec, slot);
  const properties = recordValue(schema?.properties) as Record<string, JsonSchema> | undefined;
  const required = Array.isArray(schema?.required) ? schema.required : [];
  if (!properties) return [];
  return Object.entries(properties).map(([key, property]) => ({
    key,
    label: property.title || fallbackLabel(key),
    required: required.includes(key),
    schema: property,
  }));
}

function resolveInputSchema(node: NodeUiControlProps["node"], nodeSpec: WorkflowNodeSpec | undefined, slot: NodeUiControlProps["slot"]): JsonSchema | undefined {
  const metadataSchema = node.metadata?.input_schema;
  if (isJsonSchema(metadataSchema)) return metadataSchema;
  if (slot === "input" || slot === "interaction") {
    const userInputSchema = schemaFromUserInputSpecs(nodeSpec?.inputs);
    if (userInputSchema) return userInputSchema;
  }
  if (slot !== "input" && isJsonSchema(nodeSpec?.outputs)) return nodeSpec.outputs;
  return undefined;
}

function schemaFromUserInputSpecs(inputs: WorkflowNodeSpec["inputs"] | undefined): JsonSchema | undefined {
  const inputSpecs = recordValue(inputs);
  if (!inputSpecs) return undefined;
  const properties: Record<string, JsonSchema> = {};
  const required: string[] = [];
  for (const [name, specValue] of Object.entries(inputSpecs)) {
    const spec = recordValue(specValue);
    if (spec?.from_user !== true) continue;
    const schema = isJsonSchema(spec.schema) ? spec.schema : {};
    properties[name] = schema;
    if (spec.required !== false) required.push(name);
  }
  if (Object.keys(properties).length === 0) return undefined;
  return { type: "object", required, properties };
}

function initialValues(fields: ScriptField[]): Record<string, FormValue> {
  const values: Record<string, FormValue> = {};
  for (const field of fields) {
    if (field.schema.type === "object") values[field.key] = {};
    else if (field.schema.type === "integer" || field.schema.type === "number") values[field.key] = typeof field.schema.default === "number" ? field.schema.default : "";
    else values[field.key] = field.schema.default === undefined ? "" : String(field.schema.default);
  }
  return values;
}

function valuesFromPayload(fields: ScriptField[], payload: unknown): Record<string, FormValue> {
  const source = recordValue(payload);
  const values = initialValues(fields);
  if (!source) return values;
  for (const field of fields) {
    const value = source[field.key];
    if (value === undefined || value === null) continue;
    values[field.key] = field.schema.type === "object" ? recordValue(value) ?? {} : String(value);
  }
  return values;
}

function buildSubmitData(fields: ScriptField[], values: Record<string, FormValue>): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.key];
    if (field.schema.type === "object") {
      data[field.key] = recordValue(value) ?? {};
    } else if (field.schema.type === "integer" || field.schema.type === "number") {
      data[field.key] = value === "" || value === undefined ? null : Number(value);
    } else {
      data[field.key] = String(value ?? "");
    }
  }
  return data;
}

function readonlySnapshotValue(node: NodeUiControlProps["node"], slot: NodeUiControlProps["slot"]): unknown {
  if (slot === "input") return node.input_snapshot;
  return node.output_snapshot ?? node.input_snapshot;
}

function fieldLabel(fields: ScriptField[], key: string, fallback: string): string {
  const field = fields.find((item) => item.key === key);
  if (!field) return fallback;
  return `${field.label}${field.required ? " *" : ""}`;
}

function fallbackLabel(key: string): string {
  const labels: Record<string, string> = {
    script: "剧本内容",
    background: "世界背景",
  };
  return labels[key] ?? key;
}

function isJsonSchema(value: unknown): value is JsonSchema {
  return typeof value === "object" && value !== null;
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function readableError(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
