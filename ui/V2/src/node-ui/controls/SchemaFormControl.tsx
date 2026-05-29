import { type ChangeEvent, useEffect, useMemo, useState } from "react";

import { listAssetCollections, listAssetTags, searchAssets, uploadAsset } from "../../api/assets";
import { listProjects } from "../../api/projects";
import type { AssetCollection, AssetRecord, AssetScope, AssetTag, JsonSchema, NodeUiControlConfig, ProjectRecord, WorkflowNodeSpec } from "../../api/types";
import { buildSchemaFields, type SchemaField } from "../../utils/display";
import type { NodeUiControlProps } from "../types";

type FormValue = string | boolean | string[];

export function SchemaFormControl({ busy, config, node, nodeSpec, projectId, snapshot, slot, value, onSubmit }: NodeUiControlProps) {
  const inputSchema = resolveInputSchema(node, nodeSpec, slot);
  const fields = useMemo(() => buildSchemaFields(inputSchema), [inputSchema]);
  const [values, setValues] = useState<Record<string, FormValue>>(() => initialValues(fields));
  const [error, setError] = useState("");
  const readonly = config.mode === "readonly" || !onSubmit;
  const controlsReadonly = readonly || Boolean(busy);
  const renderedValues = readonly ? valuesFromPayload(fields, value ?? readonlySnapshotValue(node, slot)) : values;
  const fieldConfigs = fieldControlConfigs(config);
  const nodeConfig = recordValue(nodeSpec?.config);
  const title = readText(node.metadata?.title) || readText(nodeConfig?.title) || "填写运行输入";
  const description = readText(node.metadata?.description) || readText(nodeConfig?.description);

  useEffect(() => {
    setValues(initialValues(fields));
    setError("");
  }, [fields]);

  function submit() {
    if (busy) return;
    const validation = validateFields(fields, values);
    if (validation) {
      setError(validation);
      return;
    }
    setError("");
    onSubmit?.(buildInputData(fields, values));
  }

  return (
    <section className="interaction-panel schema-form-control">
      <div>
        <p className="eyebrow">{readonly ? "参数快照" : "等待输入"}</p>
        <h3>{title}</h3>
        {description ? <p className="muted">{description}</p> : null}
      </div>

      <div className="schema-form-grid">
        {fields.map((field) => {
          const fieldConfig = fieldConfigs[field.key];
          if (fieldConfig?.control_id === "ui.input.asset_image_picker.v1" || field.control === "asset_images") {
            return (
              <AssetImagePickerField
                config={fieldConfig}
                field={field}
                key={field.key}
                projectId={projectId}
                readonly={controlsReadonly}
                value={renderedValues[field.key]}
                onChange={(value) => setValues((current) => ({ ...current, [field.key]: value }))}
              />
            );
          }
          return (
            <SchemaValueField
              field={field}
              key={field.key}
              readonly={controlsReadonly}
              value={renderedValues[field.key]}
              onChange={(value) => setValues((current) => ({ ...current, [field.key]: value }))}
            />
          );
        })}
      </div>

      {error ? <p className="form-error">{error}</p> : null}
      {!readonly ? (
        <button className="primary-button" disabled={busy || fields.length === 0} type="button" onClick={submit}>
          {busy ? "提交中" : "提交并继续"}
        </button>
      ) : null}
    </section>
  );
}

function SchemaValueField({
  field,
  value,
  readonly,
  onChange,
}: {
  field: SchemaField;
  value: FormValue | undefined;
  readonly: boolean;
  onChange: (value: FormValue) => void;
}) {
  const label = fieldLabelText(field);

  if (field.control === "select") {
    return (
      <label className="form-field" title={field.helpText}>
        <span>{label}</span>
        <select disabled={readonly} value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} aria-label={field.label}>
          <option value="">{field.placeholder || "请选择"}</option>
          {field.enumValues?.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        {field.description ? <small>{field.description}</small> : null}
      </label>
    );
  }

  if (field.control === "choice_group") {
    return (
      <fieldset className="choice-field" title={field.helpText}>
        <legend>{label}</legend>
        <div className="choice-options">
          {field.enumValues?.map((item) => (
            <label className={String(value ?? "") === item ? "choice-option active" : "choice-option"} key={item}>
              <input
                checked={String(value ?? "") === item}
                disabled={readonly}
                name={field.key}
                type="radio"
                value={item}
                onChange={() => onChange(item)}
              />
              <span>{item}</span>
            </label>
          ))}
        </div>
        {field.description ? <small>{field.description}</small> : null}
      </fieldset>
    );
  }

  if (field.control === "checkbox") {
    return (
      <label className="check-field" title={field.helpText}>
        <input checked={Boolean(value)} disabled={readonly} type="checkbox" onChange={(event) => onChange(event.target.checked)} />
        <span>{label}</span>
      </label>
    );
  }

  return (
    <label className="form-field" title={field.helpText}>
      <span>{label}</span>
      {field.control === "textarea" ? (
        <textarea
          aria-label={field.label}
          placeholder={field.placeholder}
          readOnly={readonly}
          value={String(value ?? "")}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          aria-label={field.label}
          placeholder={field.placeholder}
          readOnly={readonly}
          type={field.control === "number" ? "number" : "text"}
          value={String(value ?? "")}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {field.description ? <small>{field.description}</small> : null}
    </label>
  );
}

function fieldLabelText(field: SchemaField): string {
  return `${field.label}${field.required ? " *" : ""}`;
}

function AssetImagePickerField({
  config,
  field,
  projectId,
  readonly,
  value,
  onChange,
}: {
  config?: NodeUiControlConfig;
  field: SchemaField;
  projectId?: string;
  readonly: boolean;
  value: FormValue | undefined;
  onChange: (value: FormValue) => void;
}) {
  const option = controlOptionReader(config);
  const multiple = option("selection_mode") === "multiple" || field.type === "array";
  const selected = Array.isArray(value) ? value : value ? [String(value)] : [];
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");

  function updateSelected(urls: string[]) {
    onChange(multiple ? urls : urls[0] ?? "");
  }

  return (
    <fieldset className="asset-choice-field asset-picker-field" title={field.helpText}>
      <legend>{field.label}{field.required ? " *" : ""}</legend>
      {field.description ? <p>{field.description}</p> : null}
      <div className={expanded ? "selected-thumbnails expanded" : "selected-thumbnails"}>
        {selected.length ? selected.map((url) => (
          <button className="selected-thumbnail" key={url} type="button" onClick={() => setPreviewUrl(url)}>
            <img src={url} alt={field.label} />
          </button>
        )) : <span className="muted">尚未选择图片</span>}
      </div>
      <div className="button-row">
        {!readonly ? <button className="secondary-button" type="button" onClick={() => setOpen(true)}>选择图片</button> : null}
        {selected.length > 1 ? (
          <button className="ghost-button" type="button" onClick={() => setExpanded((current) => !current)}>
            {expanded ? "收起" : "展开全部"}
          </button>
        ) : null}
      </div>
      {open ? (
        <AssetImagePickerDialog
          multiple={multiple}
          projectId={projectId}
          selected={selected}
          uploadScope={String(option("upload_scope") ?? "project")}
          onClose={() => setOpen(false)}
          onSelect={(urls) => updateSelected(urls)}
        />
      ) : null}
      {previewUrl ? (
        <div className="asset-picker-modal" role="dialog" aria-label="图片预览">
          <button className="modal-scrim" type="button" onClick={() => setPreviewUrl("")} aria-label="关闭预览" />
          <div className="asset-preview-dialog">
            <img src={previewUrl} alt="图片预览" />
            <button className="secondary-button" type="button" onClick={() => setPreviewUrl("")}>关闭</button>
          </div>
        </div>
      ) : null}
    </fieldset>
  );
}

function AssetImagePickerDialog({
  multiple,
  projectId,
  selected,
  uploadScope,
  onClose,
  onSelect,
}: {
  multiple: boolean;
  projectId?: string;
  selected: string[];
  uploadScope: string;
  onClose: () => void;
  onSelect: (urls: string[]) => void;
}) {
  const [tab, setTab] = useState<"library" | "upload">("library");
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [collections, setCollections] = useState<AssetCollection[]>([]);
  const [tags, setTags] = useState<AssetTag[]>([]);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState(initialAssetLibraryProjectId(projectId));
  const [draftProjectId, setDraftProjectId] = useState(initialAssetLibraryProjectId(projectId));
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  const [projectLoading, setProjectLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [collectionId, setCollectionId] = useState("");
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [draft, setDraft] = useState<string[]>(selected);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const projectOptions = useMemo(() => assetProjectOptions(projects), [projects]);
  const selectedProject = projectOptions.find((item) => item.project_id === selectedProjectId);
  const selectedProjectName = selectedProject?.name?.trim() || (selectedProjectId === "global" ? "全局项目" : "项目资产");
  const libraryScope = assetLibraryScope(selectedProjectId);
  const libraryProjectId = libraryScope === "combined" ? selectedProjectId : undefined;
  const uploadAssetScope = assetScope(selectedProjectId, uploadScope);

  useEffect(() => {
    const nextProjectId = initialAssetLibraryProjectId(projectId);
    setSelectedProjectId(nextProjectId);
    setDraftProjectId(nextProjectId);
    setCollectionId("");
    setTagIds([]);
  }, [projectId]);

  useEffect(() => {
    let active = true;
    setProjectLoading(true);
    listProjects()
      .then((items) => {
        if (!active) return;
        const options = assetProjectOptions(items);
        setProjects(items);
        setSelectedProjectId((current) => options.some((project) => project.project_id === current) ? current : options[0]?.project_id ?? "global");
        setDraftProjectId((current) => options.some((project) => project.project_id === current) ? current : options[0]?.project_id ?? "global");
      })
      .catch((error) => {
        if (active) setMessage(readableError(error, "项目列表暂不可用。"));
      })
      .finally(() => {
        if (active) setProjectLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.all([
      listAssetCollections(libraryScope, libraryProjectId),
      listAssetTags(libraryScope, libraryProjectId),
    ]).then(([nextCollections, nextTags]) => {
      if (!active) return;
      setCollections(nextCollections);
      setTags(nextTags);
      setCollectionId((current) => nextCollections.some((collection) => collection.collection_id === current) ? current : "");
      setTagIds((current) => current.filter((tagId) => nextTags.some((tag) => tag.tag_id === tagId)));
    }).catch((error) => {
      if (active) setMessage(readableError(error, "资产目录或标签暂不可用。"));
    });
    return () => {
      active = false;
    };
  }, [libraryProjectId, libraryScope]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    searchAssets({
      scope: libraryScope,
      project_id: libraryProjectId,
      keyword: keyword.trim() || undefined,
      collection_id: collectionId || undefined,
      tag_ids: tagIds,
      mime_type: "image/*",
    }).then((items) => {
      if (active) setAssets(items.filter((asset) => asset.metadata.public_url));
    }).catch((error) => {
      if (active) setMessage(readableError(error, "资产搜索暂不可用。"));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [collectionId, keyword, libraryProjectId, libraryScope, reloadKey, tagIds]);

  function toggleUrl(url: string) {
    if (!multiple) {
      setDraft([url]);
      return;
    }
    setDraft((current) => current.includes(url) ? current.filter((item) => item !== url) : [...current, url]);
  }

  function openProjectDialog() {
    setDraftProjectId(selectedProjectId);
    setProjectDialogOpen(true);
  }

  function confirmProjectSelection() {
    setSelectedProjectId(draftProjectId);
    setCollectionId("");
    setTagIds([]);
    setProjectDialogOpen(false);
  }

  async function uploadSelectedFile() {
    if (!file) return;
    const uploaded = await uploadAsset({
      file,
      scope: uploadAssetScope,
      project_id: uploadAssetScope === "project" ? selectedProjectId : undefined,
      publish: true,
      collection_ids: collectionId ? [collectionId] : undefined,
      tag_ids: tagIds,
    });
    const url = uploaded.metadata.public_url;
    if (url) setDraft((current) => multiple ? [...current, url] : [url]);
    setFile(null);
    setTab("library");
    setReloadKey((current) => current + 1);
  }

  return (
    <div className="asset-picker-modal" role="dialog" aria-label="选择资产图片">
      <button className="modal-scrim" type="button" onClick={onClose} aria-label="关闭资产选择" />
      <section className="asset-picker-dialog">
        <header className="asset-picker-header">
          <h3>选择资产图片</h3>
          <button className="ghost-button" type="button" onClick={onClose}>关闭</button>
        </header>
        <div className="segmented-control">
          <button className={tab === "library" ? "active" : ""} type="button" onClick={() => setTab("library")}>资产库</button>
          <button className={tab === "upload" ? "active" : ""} type="button" onClick={() => setTab("upload")}>本地上传</button>
        </div>

        {tab === "library" ? (
          <>
            <div className="asset-picker-project-row">
              <div className="asset-picker-project-summary">
                <span className="eyebrow">资产项目</span>
                <button className="asset-project-select-button" type="button" aria-label={`选择资产项目：${selectedProjectName}`} onClick={openProjectDialog}>
                  <strong>{selectedProjectName}</strong>
                  <span>{projectLoading ? "加载中" : "切换"}</span>
                </button>
              </div>
            </div>
            {projectDialogOpen ? (
              <div className="asset-project-dialog-backdrop">
                <section className="asset-project-dialog" role="dialog" aria-label="选择资产项目">
                  <header className="asset-picker-header">
                    <h4>选择资产项目</h4>
                    <button className="ghost-button" type="button" onClick={() => setProjectDialogOpen(false)}>关闭</button>
                  </header>
                  <div className="asset-project-options" role="radiogroup" aria-label="资产项目">
                    {projectOptions.map((project) => (
                      <label className={draftProjectId === project.project_id ? "asset-project-option active" : "asset-project-option"} key={project.project_id}>
                        <input
                          aria-label={project.name}
                          checked={draftProjectId === project.project_id}
                          name="asset-library-project"
                          type="radio"
                          value={project.project_id}
                          onChange={() => setDraftProjectId(project.project_id)}
                        />
                        <span>{project.name}</span>
                      </label>
                    ))}
                  </div>
                  <footer className="asset-picker-footer">
                    <button className="secondary-button" type="button" onClick={() => setProjectDialogOpen(false)}>取消</button>
                    <button className="primary-button" type="button" onClick={confirmProjectSelection}>确认项目</button>
                  </footer>
                </section>
              </div>
            ) : null}
            <div className="asset-picker-body">
              <aside className="asset-picker-tree">
                <button className={collectionId === "" ? "active" : ""} type="button" onClick={() => setCollectionId("")}>全部目录</button>
                {collections.map((collection) => (
                  <button className={collectionId === collection.collection_id ? "active" : ""} key={collection.collection_id} type="button" onClick={() => setCollectionId(collection.collection_id)}>
                    {collection.name}
                  </button>
                ))}
              </aside>
              <section className="asset-picker-results">
                <input aria-label="搜索资产" placeholder="搜索资产" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
                <div className="asset-picker-tag-section">
                  <span className="eyebrow">标签过滤</span>
                  <div className="tag-filter-group">
                    {tags.length ? tags.map((tag) => {
                      const checked = tagIds.includes(tag.tag_id);
                      return (
                        <label className={checked ? "tag-filter active" : "tag-filter"} key={tag.tag_id}>
                          <input aria-label={`筛选标签 ${tag.name}`} checked={checked} type="checkbox" onChange={(event) => setTagIds((current) => event.target.checked ? [...current, tag.tag_id] : current.filter((item) => item !== tag.tag_id))} />
                          <span>{tag.name}</span>
                        </label>
                      );
                    }) : <span className="muted">暂无标签</span>}
                  </div>
                </div>
                {message ? <p className="form-error">{message}</p> : null}
                {loading ? <p className="muted">正在加载资产...</p> : null}
                <div className="asset-check-grid">
                  {assets.map((asset) => {
                    const url = asset.metadata.public_url ?? "";
                    const checked = draft.includes(url);
                    return (
                      <button className={checked ? "asset-check-card active" : "asset-check-card"} key={asset.asset_id} type="button" onClick={() => toggleUrl(url)}>
                        <img src={url} alt={asset.name} />
                        <span>{asset.name}</span>
                      </button>
                    );
                  })}
                </div>
              </section>
            </div>
          </>
        ) : (
          <div className="asset-upload-panel">
            <label className="compact-field">
              <span>本地图片</span>
              <input accept="image/*" type="file" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} />
            </label>
            <button className="secondary-button" disabled={!file} type="button" onClick={() => void uploadSelectedFile()}>上传并选择</button>
          </div>
        )}

        <footer className="asset-picker-footer">
          <span>{draft.length} 张已选择</span>
          <button className="primary-button" type="button" onClick={() => { onSelect(draft); onClose(); }}>确认选择</button>
        </footer>
      </section>
    </div>
  );
}

function resolveInputSchema(node: NodeUiControlProps["node"], nodeSpec: NodeUiControlProps["nodeSpec"], slot: NodeUiControlProps["slot"]): JsonSchema | undefined {
  const metadataSchema = node.metadata?.input_schema;
  if (isJsonSchema(metadataSchema)) return metadataSchema;
  if (slot === "input") {
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
  return {
    type: "object",
    required,
    properties,
  };
}

function fieldControlConfigs(config: NodeUiControlConfig): Record<string, NodeUiControlConfig> {
  const fields = config.options?.fields;
  return typeof fields === "object" && fields !== null ? fields as Record<string, NodeUiControlConfig> : {};
}

function initialValues(fields: SchemaField[]): Record<string, FormValue> {
  const values: Record<string, FormValue> = {};
  for (const field of fields) {
    if (field.control === "checkbox") values[field.key] = Boolean(field.defaultValue);
    else if (field.control === "asset_images" || field.type === "array") values[field.key] = [];
    else values[field.key] = field.defaultValue === undefined ? "" : String(field.defaultValue);
  }
  return values;
}

function validateFields(fields: SchemaField[], values: Record<string, FormValue>): string {
  for (const field of fields) {
    const value = values[field.key];
    const emptyArray = Array.isArray(value) && value.length === 0;
    if (field.required && (value === undefined || value === "" || emptyArray)) return `请填写${field.label}。`;
  }
  return "";
}

function buildInputData(fields: SchemaField[], values: Record<string, FormValue>): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.key];
    if (field.type === "integer" || field.type === "number") data[field.key] = value === "" || value === undefined ? null : Number(value);
    else if (field.type === "boolean") data[field.key] = Boolean(value);
    else if (field.type === "array") data[field.key] = Array.isArray(value) ? value : splitLines(String(value ?? ""));
    else data[field.key] = Array.isArray(value) ? value[0] ?? "" : value ?? "";
  }
  return data;
}

function valuesFromPayload(fields: SchemaField[], payload: unknown): Record<string, FormValue> {
  const source = recordValue(payload);
  const values = initialValues(fields);
  if (!source) return values;

  for (const field of fields) {
    const value = source[field.key];
    if (value === undefined || value === null) continue;
    values[field.key] = formValueFromPayload(field, value);
  }
  return values;
}

function formValueFromPayload(field: SchemaField, value: unknown): FormValue {
  if (field.control === "checkbox" || field.type === "boolean") return Boolean(value);
  if (field.control === "asset_images" || field.type === "array") {
    if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
    return value === "" ? [] : [String(value)];
  }
  return String(value);
}

function readonlySnapshotValue(node: NodeUiControlProps["node"], slot: NodeUiControlProps["slot"]): unknown {
  if (slot === "input") return node.input_snapshot;
  return node.output_snapshot ?? node.input_snapshot;
}

function splitLines(value: string): string[] {
  return value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
}

function assetScope(projectId: string | undefined, uploadScope: string): Exclude<AssetScope, "combined"> {
  if (uploadScope === "global" || !projectId || projectId === "global") return "global";
  return "project";
}

function assetLibraryScope(projectId: string | undefined): AssetScope {
  return !projectId || projectId === "global" ? "global" : "combined";
}

function initialAssetLibraryProjectId(projectId: string | undefined): string {
  return projectId || "global";
}

function assetProjectOptions(projects: ProjectRecord[]): ProjectRecord[] {
  if (projects.some((project) => project.project_id === "global")) return projects;
  return [{ project_id: "global", name: "全局项目", owner_user_id: "system" }, ...projects];
}

function controlOptionReader(config?: NodeUiControlConfig): (key: string) => unknown {
  const topLevel = recordValue(config);
  return (key: string) => config?.options?.[key] ?? topLevel?.[key];
}

function isJsonSchema(value: unknown): value is JsonSchema {
  return typeof value === "object" && value !== null;
}

function readText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : undefined;
}

function readableError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
