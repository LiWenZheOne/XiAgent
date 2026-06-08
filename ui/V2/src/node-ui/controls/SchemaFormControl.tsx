import { type ChangeEvent, type ReactNode, useEffect, useMemo, useState } from "react";

import { downloadAssetContent, downloadAssetThumbnail, listAssetCollections, listAssetTags, searchAssets, uploadAsset } from "../../api/assets";
import { listProjects } from "../../api/projects";
import type { AssetCollection, AssetRecord, AssetScope, AssetTag, JsonSchema, NodeUiControlConfig, ProjectRecord, WorkflowNodeSpec } from "../../api/types";
import { buildSchemaFields, type SchemaField } from "../../utils/display";
import type { NodeUiControlProps } from "../types";
import { assetSearchScopeForProject } from "./assetPicker";
import { EpisodeContextControl } from "./EpisodeContextControl";

interface ImageRef {
  kind: "asset" | "data_uri";
  asset_id?: string;
  data?: string;
  role?: string;
}

interface ImageRefPreview {
  label: string;
  url?: string;
}

type FormValue = string | boolean | string[] | ImageRef | ImageRef[];

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
  const hasDropdownAssetPicker = fields.some((field) => fieldConfigs[field.key]?.control_id === "ui.input.asset_picker.v1" && fieldConfigs[field.key]?.variant === "dropdown");
  const dropdownAssetField = hasDropdownAssetPicker
    ? fields.find((field) => fieldConfigs[field.key]?.control_id === "ui.input.asset_picker.v1" && fieldConfigs[field.key]?.variant === "dropdown")
    : undefined;
  const compactSwitchFields = hasDropdownAssetPicker ? fields.filter((field) => field.control === "checkbox").slice(0, 2) : [];
  const usesCompactPrimaryRow = Boolean(dropdownAssetField && compactSwitchFields.length);
  const compactFieldKeys = new Set(usesCompactPrimaryRow ? [
    dropdownAssetField?.key,
    ...compactSwitchFields.map((field) => field.key),
  ].filter((key): key is string => Boolean(key)) : []);
  const promptCountField = fields.find((field) => field.key === "prompts_per_item");
  const imageCountField = fields.find((field) => field.key === "images_per_prompt");
  const usesPromptCountRow = Boolean(promptCountField && imageCountField);

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

  function renderField(field: SchemaField): ReactNode {
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
    if (fieldConfig?.control_id === "ui.input.asset_picker.v1") {
      return (
        <AssetPickerField
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
  }

  return (
    <section className={hasDropdownAssetPicker ? "interaction-panel schema-form-control asset-dropdown-form" : "interaction-panel schema-form-control"}>
      <div>
        <p className="eyebrow">{readonly ? "参数快照" : "等待输入"}</p>
        <h3>{title}</h3>
        {description ? <p className="muted">{description}</p> : null}
      </div>

      <div className="schema-form-grid">
        {usesCompactPrimaryRow && dropdownAssetField ? (
          <div className="schema-form-primary-row">
            <div className="schema-form-primary-picker">
              <div className="schema-form-switch-group" role="group" aria-label="分镜生成选项">
                {compactSwitchFields.map((field) => renderField(field))}
              </div>
              {renderField(dropdownAssetField)}
            </div>
          </div>
        ) : null}
        {fields.map((field) => {
          if (compactFieldKeys.has(field.key)) return null;
          if (usesPromptCountRow && field.key === "prompts_per_item" && promptCountField && imageCountField) {
            return (
              <div className="schema-form-count-row" key="prompt-image-count-row">
                {renderField(promptCountField)}
                {renderField(imageCountField)}
              </div>
            );
          }
          if (usesPromptCountRow && field.key === "images_per_prompt") return null;
          return renderField(field);
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
        <span className="switch-track" aria-hidden="true">
          <span />
        </span>
        <span className="switch-label">{label}</span>
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
  const selected = normalizeImageRefs(value);
  const [previews, setPreviews] = useState<Record<string, ImageRefPreview>>({});
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const selectedAssetIdsKey = selected.filter((ref) => ref.kind === "asset" && ref.asset_id).map((ref) => ref.asset_id).join("|");

  useEffect(() => {
    let active = true;
    const objectUrls: string[] = [];
    const missingAssetRefs = selected.filter((ref) => {
      if (ref.kind !== "asset" || !ref.asset_id) return false;
      const preview = previews[imageRefKey(ref)] ?? intrinsicImageRefPreview(ref);
      return !preview?.url;
    });
    if (!missingAssetRefs.length) return () => undefined;

    Promise.all(missingAssetRefs.map(async (ref) => {
      const key = imageRefKey(ref);
      try {
        const blob = await downloadAssetThumbnail(ref.asset_id as string, projectId, 256);
        if (!blob.type.startsWith("image/")) return null;
        const url = URL.createObjectURL(blob);
        objectUrls.push(url);
        return [key, { label: imageRefLabel(ref), url }] as const;
      } catch {
        return null;
      }
    })).then((items) => {
      if (!active) return;
      const loadedEntries = items.filter((item): item is readonly [string, { label: string; url: string }] => Boolean(item));
      const loadedPreviews: Record<string, ImageRefPreview> = Object.fromEntries(loadedEntries);
      if (Object.keys(loadedPreviews).length) {
        setPreviews((current) => ({ ...current, ...loadedPreviews }));
      }
    });

    return () => {
      active = false;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [projectId, selectedAssetIdsKey]);

  function updateSelected(refs: ImageRef[], nextPreviews: Record<string, ImageRefPreview>) {
    setPreviews((current) => ({ ...current, ...nextPreviews }));
    onChange(multiple ? refs : refs[0] ?? { kind: "asset", asset_id: "" });
  }

  return (
    <fieldset className="asset-choice-field asset-picker-field" title={field.helpText}>
      <legend>{field.label}{field.required ? " *" : ""}</legend>
      {field.description ? <p>{field.description}</p> : null}
      <div className={expanded ? "selected-thumbnails expanded" : "selected-thumbnails"}>
        {selected.length ? selected.map((ref) => {
          const key = imageRefKey(ref);
          const preview = previews[key] ?? intrinsicImageRefPreview(ref);
          return (
          <button className="selected-thumbnail" key={key} type="button" onClick={() => preview?.url ? setPreviewUrl(preview.url) : undefined}>
            {preview?.url ? <img src={preview.url} alt={preview.label || field.label} /> : <span>{preview?.label || imageRefLabel(ref)}</span>}
          </button>
          );
        }) : <span className="muted">尚未选择图片</span>}
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
          onSelect={(refs, nextPreviews) => updateSelected(refs, nextPreviews)}
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
  selected: ImageRef[];
  uploadScope: string;
  onClose: () => void;
  onSelect: (refs: ImageRef[], previews: Record<string, ImageRefPreview>) => void;
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
  const [draft, setDraft] = useState<ImageRef[]>(selected);
  const [draftPreviews, setDraftPreviews] = useState<Record<string, ImageRefPreview>>({});
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

  function toggleAsset(asset: AssetRecord) {
    const ref = imageRefFromAsset(asset);
    const key = imageRefKey(ref);
    setDraftPreviews((current) => ({ ...current, [key]: imageRefPreviewFromAsset(asset) }));
    if (!multiple) {
      setDraft([ref]);
      return;
    }
    setDraft((current) => current.some((item) => imageRefKey(item) === key) ? current.filter((item) => imageRefKey(item) !== key) : [...current, ref]);
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
    const ref: ImageRef = { kind: "asset", asset_id: uploaded.asset_id, role: "reference" };
    const key = imageRefKey(ref);
    setDraftPreviews((current) => ({ ...current, [key]: { label: uploaded.name, url: uploaded.metadata.public_url } }));
    setDraft((current) => multiple ? [...current.filter((item) => imageRefKey(item) !== key), ref] : [ref]);
    setFile(null);
    setTab("library");
    setReloadKey((current) => current + 1);
  }

  return (
    <div className="asset-picker-modal" role="dialog" aria-label="选择资产图片">
      <button className="modal-scrim" type="button" onClick={onClose} aria-label="关闭资产选择" />
      <section className="asset-picker-dialog asset-image-picker-dialog">
        <header className="asset-picker-header">
          <h3>选择资产图片</h3>
          <button className="ghost-button" type="button" onClick={onClose}>关闭</button>
        </header>
        <div className="segmented-control">
          <button className={tab === "library" ? "active" : ""} type="button" onClick={() => setTab("library")}>资产库</button>
          <button className={tab === "upload" ? "active" : ""} type="button" onClick={() => setTab("upload")}>本地上传</button>
        </div>

        {tab === "library" ? (
          <div className="asset-image-picker-library-panel">
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
                    const ref = imageRefFromAsset(asset);
                    const checked = draft.some((item) => imageRefKey(item) === imageRefKey(ref));
                    return (
                      <button className={checked ? "asset-check-card active" : "asset-check-card"} key={asset.asset_id} type="button" onClick={() => toggleAsset(asset)}>
                        <img src={url} alt={asset.name} />
                        <span>{asset.name}</span>
                      </button>
                    );
                  })}
                </div>
              </section>
            </div>
          </div>
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
          <button className="primary-button" type="button" onClick={() => { onSelect(draft, draftPreviews); onClose(); }}>确认选择</button>
        </footer>
      </section>
    </div>
  );
}

function AssetPickerField({
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
  if (config?.variant === "dropdown") {
    return (
      <AssetPickerDropdownField
        assetType={stringOption(option("asset_type"))}
        field={field}
        filterTagNames={stringArrayOption(option("filter_tag_names"))}
        placeholder={readText(option("placeholder")) || "请选择资产"}
        previewControlId={readText(option("preview_control_id"))}
        projectId={projectId}
        readonly={readonly}
        value={value}
        onChange={onChange}
      />
    );
  }
  return (
    <AssetPickerListField
      config={config}
      field={field}
      projectId={projectId}
      readonly={readonly}
      value={value}
      onChange={onChange}
    />
  );
}

function AssetPickerListField({
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
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<AssetRefPreview | undefined>(undefined);
  const selectedAssetId = typeof value === "string" ? value : "";

  return (
    <fieldset className="asset-choice-field asset-picker-field" title={field.helpText}>
      <legend>{field.label}{field.required ? " *" : ""}</legend>
      {field.description ? <p>{field.description}</p> : null}
      <div className="selected-thumbnails">
        {selectedAssetId ? (
          <span>
            {preview?.label ?? selectedAssetId}
            {preview?.subtitle ? <small>{preview.subtitle}</small> : null}
          </span>
        ) : <span className="muted">尚未选择资产</span>}
      </div>
      {!readonly ? (
        <button className="secondary-button" type="button" onClick={() => setOpen(true)}>
          {readText(option("button_label")) || "选择资产"}
        </button>
      ) : null}
      {open ? (
        <AssetPickerDialog
          assetType={stringOption(option("asset_type"))}
          filterTagNames={stringArrayOption(option("filter_tag_names"))}
          projectId={projectId}
          selectedAssetId={selectedAssetId}
          title={readText(option("dialog_title")) || "选择资产"}
          onClose={() => setOpen(false)}
          onSelect={(asset) => {
            setPreview(assetRefPreviewFromAsset(asset));
            onChange(asset.asset_id);
          }}
        />
      ) : null}
    </fieldset>
  );
}

function AssetPickerDropdownField({
  assetType,
  field,
  filterTagNames,
  placeholder,
  previewControlId,
  projectId,
  readonly,
  value,
  onChange,
}: {
  assetType?: string;
  field: SchemaField;
  filterTagNames: string[];
  placeholder: string;
  previewControlId?: string;
  projectId?: string;
  readonly: boolean;
  value: FormValue | undefined;
  onChange: (value: FormValue) => void;
}) {
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [previewMessage, setPreviewMessage] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const selectedAssetId = typeof value === "string" ? value : "";
  const searchScope = assetSearchScopeForProject(projectId);
  const configuredTagNamesKey = stringArrayKey(filterTagNames);
  const configuredTagNames = useMemo(() => stringArrayFromKey(configuredTagNamesKey), [configuredTagNamesKey]);
  const selectedAsset = assets.find((asset) => asset.asset_id === selectedAssetId);
  const filteredAssets = useMemo(() => {
    const keyword = query.trim().toLocaleLowerCase();
    if (!keyword || selectedAsset?.name === query) return assets;
    return assets.filter((asset) => asset.name.toLocaleLowerCase().includes(keyword));
  }, [assets, query, selectedAsset?.name]);
  const listboxId = `${field.key}-asset-options`;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setMessage("");
    searchAssets({
      ...searchScope,
      asset_type: assetType,
      tag_names: configuredTagNames.length ? configuredTagNames : undefined,
      limit: 200,
    }).then((items) => {
      if (active) setAssets(items);
    }).catch((error) => {
      if (active) setMessage(readableError(error, "资产列表暂不可用。"));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [assetType, configuredTagNames, searchScope.project_id, searchScope.scope]);

  useEffect(() => {
    if (selectedAsset) setQuery(selectedAsset.name);
    else if (!selectedAssetId) setQuery("");
  }, [selectedAsset, selectedAssetId]);

  useEffect(() => {
    let active = true;
    setPreview(null);
    setPreviewMessage("");
    if (previewControlId !== "ui.display.episode_context.v1" || !selectedAssetId) return () => {
      active = false;
    };
    if (!selectedAsset) return () => {
      active = false;
    };
    const loadPreview = async () => {
      try {
        const text = selectedAsset.text_content && selectedAsset.text_content.trim()
          ? selectedAsset.text_content
          : await assetContentText(selectedAsset, projectId);
        const parsed = JSON.parse(text) as unknown;
        if (!active) return;
        if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
          setPreview(parsed as Record<string, unknown>);
        } else {
          setPreviewMessage("集信息资产内容不是可预览的 JSON。");
        }
      } catch {
        if (active) setPreviewMessage("暂时无法预览该集信息。");
      }
    };
    void loadPreview();
    return () => {
      active = false;
    };
  }, [previewControlId, projectId, selectedAsset, selectedAssetId]);

  function selectAsset(asset: AssetRecord) {
    setQuery(asset.name);
    setOpen(false);
    onChange(asset.asset_id);
  }

  return (
    <fieldset className="form-field asset-picker-dropdown-field" title={field.helpText}>
      <legend>{field.label}{field.required ? " *" : ""}</legend>
      <div className="asset-picker-combobox">
        <input
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-expanded={open}
          aria-label={field.label}
          autoComplete="off"
          disabled={readonly || loading}
          placeholder={loading ? "正在加载集信息资产..." : placeholder}
          role="combobox"
          value={query}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            if (selectedAssetId) onChange("");
          }}
          onFocus={() => setOpen(true)}
        />
        {open && !readonly ? (
          <div className="asset-picker-combobox-list" id={listboxId} role="listbox">
            {filteredAssets.length ? filteredAssets.map((asset) => (
              <button
                aria-selected={asset.asset_id === selectedAssetId}
                className={asset.asset_id === selectedAssetId ? "active" : ""}
                key={asset.asset_id}
                role="option"
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => selectAsset(asset)}
              >
                {asset.name}
              </button>
            )) : (
              <span className="asset-picker-combobox-empty">没有匹配的集信息资产。</span>
            )}
          </div>
        ) : null}
      </div>
      {message ? <small className="form-error">{message}</small> : null}
      {!message && !loading && assets.length === 0 ? <small>没有找到符合条件的资产。</small> : null}
      {!message && !loading && assets.length > 0 ? <small>已加载 {assets.length} 个可用集信息资产</small> : null}
      {preview ? (
        <div className="asset-picker-episode-preview">
          <EpisodeContextControl
            config={{ control_id: "ui.display.episode_context.v1", variant: "summary_catalog", mode: "readonly" }}
            node={{
              node_id: `${field.key}_preview`,
              status: "succeeded",
              output_snapshot: preview,
              metadata: {},
            }}
            slot="output"
            value={preview}
          />
        </div>
      ) : null}
      {previewMessage ? <small>{previewMessage}</small> : null}
    </fieldset>
  );
}

function contentProjectId(asset: AssetRecord, fallbackProjectId?: string): string | undefined {
  return asset.scope === "project" ? asset.project_id ?? fallbackProjectId : undefined;
}

async function assetContentText(asset: AssetRecord, projectId?: string): Promise<string> {
  const blob = await downloadAssetContent(asset.asset_id, contentProjectId(asset, projectId));
  return blob.text();
}

interface AssetRefPreview {
  label: string;
  subtitle?: string;
}

function AssetPickerDialog({
  assetType,
  filterTagNames,
  projectId,
  selectedAssetId,
  title,
  onClose,
  onSelect,
}: {
  assetType?: string;
  filterTagNames: string[];
  projectId?: string;
  selectedAssetId: string;
  title: string;
  onClose: () => void;
  onSelect: (asset: AssetRecord) => void;
}) {
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [tags, setTags] = useState<AssetTag[]>([]);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState(initialAssetLibraryProjectId(projectId));
  const [draftProjectId, setDraftProjectId] = useState(initialAssetLibraryProjectId(projectId));
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const projectOptions = useMemo(() => assetProjectOptions(projects), [projects]);
  const selectedProject = projectOptions.find((item) => item.project_id === selectedProjectId);
  const selectedProjectName = selectedProject?.name?.trim() || (selectedProjectId === "global" ? "全局项目" : "项目资产");
  const libraryScope = assetLibraryScope(selectedProjectId);
  const libraryProjectId = libraryScope === "combined" ? selectedProjectId : undefined;
  const configuredTagNamesKey = stringArrayKey(filterTagNames);
  const configuredTagNames = useMemo(() => stringArrayFromKey(configuredTagNamesKey), [configuredTagNamesKey]);
  const tagIdsKey = stringArrayKey(tagIds);

  useEffect(() => {
    const nextProjectId = initialAssetLibraryProjectId(projectId);
    setSelectedProjectId(nextProjectId);
    setDraftProjectId(nextProjectId);
    setTagIds([]);
  }, [projectId]);

  useEffect(() => {
    let active = true;
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
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    listAssetTags(libraryScope, libraryProjectId)
      .then((nextTags) => {
        if (!active) return;
        setTags(nextTags);
        setTagIds((current) => {
          const compatibleCurrent = current.filter((tagId) => nextTags.some((tag) => tag.tag_id === tagId));
          return compatibleCurrent;
        });
      })
      .catch((error) => {
        if (active) setMessage(readableError(error, "资产标签暂不可用。"));
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
      tag_ids: tagIds,
      tag_names: configuredTagNames.length ? configuredTagNames : undefined,
      asset_type: assetType,
    }).then((items) => {
      if (active) setAssets(items);
    }).catch((error) => {
      if (active) setMessage(readableError(error, "资产搜索暂不可用。"));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [assetType, configuredTagNames, keyword, libraryProjectId, libraryScope, tagIdsKey]);

  function openProjectDialog() {
    setDraftProjectId(selectedProjectId);
    setProjectDialogOpen(true);
  }

  function confirmProjectSelection() {
    setSelectedProjectId(draftProjectId);
    setTagIds([]);
    setProjectDialogOpen(false);
  }

  return (
    <div className="asset-picker-modal" role="dialog" aria-label={title}>
      <button className="modal-scrim" type="button" onClick={onClose} aria-label="关闭资产选择" />
      <section className="asset-picker-dialog">
        <header className="asset-picker-header">
          <h3>{title}</h3>
          <button className="ghost-button" type="button" onClick={onClose}>关闭</button>
        </header>
        <div className="asset-picker-project-row">
          <div className="asset-picker-project-summary">
            <span className="eyebrow">资产项目</span>
            <button className="asset-project-select-button" type="button" aria-label={`选择资产项目：${selectedProjectName}`} onClick={openProjectDialog}>
              <strong>{selectedProjectName}</strong>
              <span>切换</span>
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
                      name="asset-picker-project"
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
        <label className="asset-picker-search">
          <span>搜索资产</span>
          <input aria-label="搜索资产" placeholder="输入集名称或资产名" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
        </label>
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
        <div className="asset-picker-list">
          {assets.map((asset) => (
            <button className={asset.asset_id === selectedAssetId ? "asset-picker-option active" : "asset-picker-option"} key={asset.asset_id} type="button" onClick={() => { onSelect(asset); onClose(); }}>
              <strong>{asset.name}</strong>
              <span>{assetPickerSubtitle(asset)}</span>
            </button>
          ))}
          {!loading && assets.length === 0 ? <p className="muted">没有找到符合条件的资产。</p> : null}
        </div>
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
    const emptyImageRef = field.control === "asset_images" && !normalizeImageRefs(value).length;
    if (field.required && (value === undefined || value === "" || emptyArray || emptyImageRef)) return `请填写${field.label}。`;
  }
  return "";
}

function buildInputData(fields: SchemaField[], values: Record<string, FormValue>): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.key];
    if (field.control === "asset_images") {
      const refs = normalizeImageRefs(value);
      data[field.key] = field.type === "array" ? refs : refs[0] ?? null;
    }
    else if (field.type === "integer" || field.type === "number") data[field.key] = value === "" || value === undefined ? null : Number(value);
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
  if (field.control === "asset_images") {
    const refs = normalizeImageRefs(value);
    return field.type === "array" ? refs : refs[0] ?? { kind: "asset", asset_id: "" };
  }
  if (field.type === "array") {
    if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
    return value === "" ? [] : [String(value)];
  }
  return String(value);
}

function normalizeImageRefs(value: unknown): ImageRef[] {
  if (Array.isArray(value)) return value.filter(isImageRef);
  return isImageRef(value) ? [value] : [];
}

function isImageRef(value: unknown): value is ImageRef {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  if (record.kind === "asset") return typeof record.asset_id === "string" && record.asset_id.trim().length > 0;
  if (record.kind === "data_uri") return typeof record.data === "string" && record.data.startsWith("data:image/");
  return false;
}

function imageRefFromAsset(asset: AssetRecord): ImageRef {
  return { kind: "asset", asset_id: asset.asset_id, role: "reference" };
}

function imageRefPreviewFromAsset(asset: AssetRecord): ImageRefPreview {
  return { label: asset.name, url: asset.metadata.public_url };
}

function assetRefPreviewFromAsset(asset: AssetRecord): AssetRefPreview {
  return { label: asset.name, subtitle: assetPickerSubtitle(asset) };
}

function assetPickerSubtitle(asset: AssetRecord): string {
  const type = asset.asset_type === "text" ? "文字资产" : asset.asset_type;
  return type;
}

function imageRefKey(ref: ImageRef): string {
  if (ref.kind === "asset") return `asset:${ref.asset_id ?? ""}`;
  return `data_uri:${ref.data?.slice(0, 64) ?? ""}`;
}

function imageRefLabel(ref: ImageRef): string {
  if (ref.kind === "asset") return `资产 ${ref.asset_id ?? ""}`.trim();
  return "内嵌图片";
}

function intrinsicImageRefPreview(ref: ImageRef): ImageRefPreview | undefined {
  if (ref.kind === "data_uri" && ref.data) return { label: "参考图", url: ref.data };
  return undefined;
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
  return assetSearchScopeForProject(projectId).scope;
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

function stringOption(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function stringArrayOption(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

const STRING_ARRAY_KEY_SEPARATOR = "\u001f";

function stringArrayKey(values: string[]): string {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean))).join(STRING_ARRAY_KEY_SEPARATOR);
}

function stringArrayFromKey(key: string): string[] {
  return key ? key.split(STRING_ARRAY_KEY_SEPARATOR) : [];
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
