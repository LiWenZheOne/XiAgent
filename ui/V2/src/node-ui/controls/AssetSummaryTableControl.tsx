import { type ChangeEvent, useEffect, useMemo, useState } from "react";

import { searchAssets, uploadAsset } from "../../api/assets";
import type { AssetRecord, AssetScope } from "../../api/types";
import type { NodeUiControlProps } from "../types";

type TabKey = "character" | "asset" | "prop";

interface AssetSummaryRow {
  key: string;
  type: TabKey;
  name: string;
  matchedAsset?: AssetMatch;
  imageUrl?: string;
  fields: Record<string, string>;
}

interface AssetMatch {
  asset_id: string;
  name: string;
  imageUrl?: string;
}

type ImageState = Record<string, string>;
type UploadState = Record<string, string>;
type MatchState = Record<string, AssetMatch | null>;

const tabLabels: Record<TabKey, string> = {
  character: "角色",
  asset: "地点",
  prop: "道具",
};

export function AssetSummaryTableControl({
  busy,
  config,
  node,
  projectId,
  onSubmit,
}: NodeUiControlProps) {
  const readonly = config.mode === "readonly" || !onSubmit;
  const source = recordValue(readonly ? node.output_snapshot : node.input_snapshot);
  const sourceRows = useMemo(() => buildRows(source), [source]);
  const [rows, setRows] = useState<AssetSummaryRow[]>(() => sourceRows);
  const [activeTab, setActiveTab] = useState<TabKey>("character");
  const [images, setImages] = useState<ImageState>(() => readonlyImages(node.output_snapshot, rows));
  const [uploading, setUploading] = useState<UploadState>({});
  const [error, setError] = useState("");
  const visibleRows = rows.filter((row) => row.type === activeTab);
  const columns = tableColumns(visibleRows);
  const [matches, setMatches] = useState<MatchState>(() => initialMatches(rows));
  const [pickerRow, setPickerRow] = useState<AssetSummaryRow | null>(null);
  const [pickerKeyword, setPickerKeyword] = useState("");
  const [pickerAssets, setPickerAssets] = useState<AssetRecord[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerError, setPickerError] = useState("");

  useEffect(() => {
    setRows(sourceRows);
  }, [sourceRows]);

  useEffect(() => {
    setMatches((current) => ({ ...initialMatches(rows), ...current }));
  }, [rows]);

  useEffect(() => {
    if (!pickerRow) return;
    let active = true;
    setPickerLoading(true);
    setPickerError("");
    searchAssets({
      scope: "combined",
      project_id: projectId && projectId !== "global" ? projectId : undefined,
      keyword: pickerKeyword.trim() || undefined,
      asset_type: "text",
    })
      .then((items) => {
        if (!active) return;
        setPickerAssets(items.filter((asset) => assetMatchesRowType(asset, pickerRow.type)));
      })
      .catch((nextError) => {
        if (active) setPickerError(nextError instanceof Error ? nextError.message : "资产搜索失败。");
      })
      .finally(() => {
        if (active) setPickerLoading(false);
      });
    return () => {
      active = false;
    };
  }, [pickerKeyword, pickerRow, projectId]);

  function submit(decision: "approved" | "needs_changes") {
    if (readonly || busy) return;
    onSubmit?.({
      decision,
      approved_assets: {
        characters: rows.filter((row) => row.type === "character").map((row) => rowPayload(row, matches[row.key] ?? row.matchedAsset ?? null)),
        assets: rows.filter((row) => row.type === "asset").map((row) => rowPayload(row, matches[row.key] ?? row.matchedAsset ?? null)),
        props: rows.filter((row) => row.type === "prop").map((row) => rowPayload(row, matches[row.key] ?? row.matchedAsset ?? null)),
      },
      asset_images: rows
        .map((row) => {
          const imageUrl = (images[row.key] || row.imageUrl || "").trim();
          if (!imageUrl) return null;
          return {
            asset_type: row.type === "asset" ? "scene" : row.type,
            asset_key: row.key,
            full_name: row.name,
            image_url: imageUrl,
            source: "manual_upload",
          };
        })
        .filter(Boolean),
    });
  }

  async function uploadImageFile(row: AssetSummaryRow, file: File | undefined) {
    if (!file) return;
    setUploading((current) => ({ ...current, [row.key]: "上传中" }));
    setError("");
    try {
      const scope = uploadScope(projectId);
      const uploaded = await uploadAsset({
        file,
        scope,
        project_id: scope === "project" ? projectId : undefined,
        name: `${row.name}_图像`,
        publish: true,
      });
      const url = uploaded.metadata.public_url;
      if (!url) {
        setError("图片已上传，但没有可用于工作流的公开地址。");
        return;
      }
      setImages((current) => ({ ...current, [row.key]: url }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "图片上传失败。");
    } finally {
      setUploading((current) => {
        const next = { ...current };
        delete next[row.key];
        return next;
      });
    }
  }

  async function uploadRowImage(row: AssetSummaryRow, event: ChangeEvent<HTMLInputElement>) {
    await uploadImageFile(row, event.target.files?.[0]);
    event.target.value = "";
  }

  function addRow(type: TabKey) {
    const key = `${type}:manual:${Date.now()}`;
    setRows((current) => [
      ...current,
      {
        key,
        type,
        name: "",
        fields: defaultFieldsForType(type),
      },
    ]);
  }

  function deleteRow(row: AssetSummaryRow) {
    setRows((current) => current.filter((item) => item.key !== row.key));
    setMatches((current) => {
      const next = { ...current };
      delete next[row.key];
      return next;
    });
    setImages((current) => {
      const next = { ...current };
      delete next[row.key];
      return next;
    });
  }

  function updateRowName(row: AssetSummaryRow, name: string) {
    setRows((current) => current.map((item) => item.key === row.key ? { ...item, name } : item));
  }

  function updateRowField(row: AssetSummaryRow, field: string, value: string) {
    setRows((current) => current.map((item) => (
      item.key === row.key ? { ...item, fields: { ...item.fields, [field]: value } } : item
    )));
  }

  if (!rows.length) {
    return (
      <section className="interaction-panel asset-summary-table-control">
        <p className="eyebrow">资产列表汇总</p>
        <h3>暂无可审核资产</h3>
        {!readonly ? (
          <div className="asset-summary-actions">
            <button className="secondary-button" type="button" onClick={() => addRow(activeTab)}>
              新增{tabLabels[activeTab]}
            </button>
          </div>
        ) : null}
      </section>
    );
  }

  return (
    <section className="interaction-panel asset-summary-table-control">
      <div className="asset-summary-head">
        <div>
          <p className="eyebrow">{readonly ? "资产列表结果" : "等待确认"}</p>
          <h3>资产列表汇总</h3>
        </div>
        {!readonly ? (
          <div className="asset-summary-actions">
            <button className="secondary-button" disabled={busy} type="button" onClick={() => addRow(activeTab)}>
              新增{tabLabels[activeTab]}
            </button>
            <button className="secondary-button" disabled={busy} type="button" onClick={() => submit("needs_changes")}>
              需要调整
            </button>
            <button className="primary-button" disabled={busy} type="button" onClick={() => submit("approved")}>
              确认并继续
            </button>
          </div>
        ) : null}
      </div>

      <div className="asset-summary-tabs" role="tablist" aria-label="资产类型">
        {(["character", "asset", "prop"] as const).map((tab) => (
          <button
            className={activeTab === tab ? "active" : ""}
            key={tab}
            role="tab"
            type="button"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
          >
            {tabLabels[tab]}
            <span>{rows.filter((row) => row.type === tab).length}</span>
          </button>
        ))}
      </div>

      <div className="asset-summary-table-wrap">
        <table className="asset-summary-table">
          <colgroup>
            <col className="asset-summary-col-name" />
            <col className="asset-summary-col-match" />
            <col className="asset-summary-col-image" />
            {columns.map((column) => <col className={assetSummaryColumnClass(column)} key={column} />)}
            {!readonly ? <col className="asset-summary-col-action" /> : null}
          </colgroup>
          <thead>
            <tr>
              <th>名称</th>
              <th>匹配资产</th>
              <th>图像</th>
              {columns.map((column) => <th key={column}>{fieldLabel(column)}</th>)}
              {!readonly ? <th>操作</th> : null}
            </tr>
          </thead>
          <tbody>
            {visibleRows.length ? visibleRows.map((row) => {
              const imageUrl = images[row.key] || row.imageUrl || "";
              const match = matches[row.key] ?? row.matchedAsset ?? null;
              return (
                <tr key={row.key}>
                  <td>
                    {readonly ? <strong>{row.name}</strong> : (
                      <input
                        aria-label={`${tabLabels[row.type]}名称`}
                        className="asset-summary-cell-input"
                        placeholder={`请输入${tabLabels[row.type]}名称`}
                        value={row.name}
                        onChange={(event) => updateRowName(row, event.target.value)}
                      />
                    )}
                  </td>
                  <td className="asset-summary-match-cell">
                    <button
                      className={match ? "asset-match-button matched" : "asset-match-button missing"}
                      disabled={readonly && !match}
                      type="button"
                      onClick={() => {
                        if (readonly) return;
                        setPickerRow(row);
                        setPickerKeyword("");
                      }}
                    >
                      {match ? match.name : "未匹配到对应资产"}
                    </button>
                  </td>
                  <td className="asset-summary-image-cell">
                    {readonly ? (
                      imageUrl ? <img src={imageUrl} alt={`${row.name} 图像`} /> : <span>未上传</span>
                    ) : (
                      <label
                        className={imageUrl ? "asset-summary-image-drop has-image" : "asset-summary-image-drop"}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => {
                          event.preventDefault();
                          void uploadImageFile(row, event.dataTransfer.files?.[0]);
                        }}
                      >
                        <input
                          accept="image/*"
                          aria-label={`${row.name || tabLabels[row.type]} 选取图像`}
                          disabled={busy || Boolean(uploading[row.key])}
                          type="file"
                          onChange={(event) => void uploadRowImage(row, event)}
                        />
                        {imageUrl ? <img src={imageUrl} alt={`${row.name} 图像`} /> : <span>点击选取<br />拖拽上传</span>}
                        {uploading[row.key] ? <small>{uploading[row.key]}</small> : null}
                      </label>
                    )}
                  </td>
                  {columns.map((column) => (
                    <td className="asset-summary-field-cell" key={`${row.key}-${column}`}>
                      {readonly ? (row.fields[column] || "—") : (
                        <textarea
                          aria-label={`${row.name || tabLabels[row.type]} ${fieldLabel(column)}`}
                          className="asset-summary-cell-input"
                          rows={textareaRows(row.fields[column] || "")}
                          value={row.fields[column] || ""}
                          onChange={(event) => updateRowField(row, column, event.target.value)}
                        />
                      )}
                    </td>
                  ))}
                  {!readonly ? (
                    <td className="asset-summary-action-cell">
                      <button
                        aria-label="删除"
                        className="asset-summary-delete-button"
                        disabled={busy}
                        title="删除"
                        type="button"
                        onClick={() => deleteRow(row)}
                      >
                        ×
                      </button>
                    </td>
                  ) : null}
                </tr>
              );
            }) : (
              <tr>
                <td colSpan={columns.length + (readonly ? 3 : 4)}>暂无{tabLabels[activeTab]}。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      {pickerRow ? (
        <div className="confirm-backdrop" role="presentation">
          <section className="asset-picker-dialog" role="dialog" aria-modal="true" aria-label="选择匹配资产">
            <header>
              <div>
                <p className="eyebrow">选择{tabLabels[pickerRow.type]}资产</p>
                <h3>{pickerRow.name}</h3>
              </div>
              <button className="secondary-button" type="button" onClick={() => setPickerRow(null)}>关闭</button>
            </header>
            <label className="asset-picker-search">
              <span>搜索资产</span>
              <input autoFocus placeholder={`搜索${tabLabels[pickerRow.type]}资产`} value={pickerKeyword} onChange={(event) => setPickerKeyword(event.target.value)} />
            </label>
            {pickerError ? <p className="form-error">{pickerError}</p> : null}
            <div className="asset-picker-list">
              {pickerLoading ? <p className="muted">正在搜索...</p> : null}
              {!pickerLoading && pickerAssets.length ? pickerAssets.map((asset) => (
                <button
                  className="asset-picker-option"
                  key={asset.asset_id}
                  type="button"
                  onClick={() => {
                    setMatches((current) => ({
                      ...current,
                      [pickerRow.key]: {
                        asset_id: asset.asset_id,
                        name: asset.name,
                        imageUrl: assetImageUrl(asset),
                      },
                    }));
                    setPickerRow(null);
                  }}
                >
                  <strong>{asset.name}</strong>
                  <span>{assetSummary(asset)}</span>
                </button>
              )) : null}
              {!pickerLoading && !pickerAssets.length ? <p className="muted">没有找到对应类型的资产。</p> : null}
            </div>
            <div className="button-row end">
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setMatches((current) => ({ ...current, [pickerRow.key]: null }));
                  setPickerRow(null);
                }}
              >
                标记为未匹配
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function buildRows(source: Record<string, unknown> | null): AssetSummaryRow[] {
  if (!source) return [];
  return [
    ...buildGroupRows("character", arrayOfRecords(source.characters), {
      enriched: mapByName(arrayOfRecords(source.enriched_characters)),
      variants: mapByName(arrayOfRecords(source.variant_results)),
      accessories: mapByName(arrayOfRecords(source.accessory_results)),
      semantic: mapByName(arrayOfRecords(source.semantic_match)),
      byName: mapByName(arrayOfRecords(source.match_by_name)),
    }),
    ...buildGroupRows("asset", arrayOfRecords(source.scenes), {
      enriched: mapByName(arrayOfRecords(source.enriched_scenes)),
      byName: mapByName(arrayOfRecords(source.scene_matches)),
    }),
    ...buildGroupRows("prop", arrayOfRecords(source.props), {
      enriched: mapByName(arrayOfRecords(source.enriched_props)),
      byName: mapByName(arrayOfRecords(source.prop_matches)),
    }),
  ];
}

function buildGroupRows(
  type: TabKey,
  items: Array<Record<string, unknown>>,
  related: Record<string, Map<string, Record<string, unknown>>>,
): AssetSummaryRow[] {
  return items.map((item, index) => {
    const name = textValue(item.full_name) || textValue(item.name) || `${tabLabels[type]} ${index + 1}`;
    const fields = {
      ...flattenRecord(item),
    };
    delete fields.full_name;
    delete fields.name;
    delete fields.image_url;
    return {
      key: `${type}:${name}`,
      type,
      name,
      matchedAsset: matchedAsset(related.enriched?.get(name), related.byName?.get(name), related.semantic?.get(name)),
      imageUrl: textValue(item.image_url),
      fields,
    };
  });
}

function rowPayload(row: AssetSummaryRow, match: AssetMatch | null): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    type: row.type,
    name: row.name.trim(),
    matched: Boolean(match),
    matched_asset_id: match?.asset_id ?? null,
    matched_asset_name: match?.name ?? "",
    ...row.fields,
  };
  if (match?.imageUrl) {
    payload.matched_asset_image_url = match.imageUrl;
    payload.reference_image_url = match.imageUrl;
  }
  return payload;
}

function tableColumns(rows: AssetSummaryRow[]): string[] {
  const seen = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(defaultFieldsForType(row.type))) {
      seen.add(key);
    }
    for (const key of Object.keys(row.fields)) {
      seen.add(key);
    }
  }
  return [...seen];
}

function defaultFieldsForType(type: TabKey): Record<string, string> {
  if (type === "character") {
    return { aliases: "", summary: "", character_status: "" };
  }
  if (type === "asset") {
    return { description: "", location_type: "", time_of_day: "" };
  }
  return { description: "", category: "", related_character: "" };
}

function flattenRecord(record: Record<string, unknown> | undefined): Record<string, string> {
  if (!record) return {};
  const flattened: Record<string, string> = {};
  for (const [key, value] of Object.entries(record)) {
    const text = displayValue(value);
    if (text) flattened[key] = text;
  }
  return flattened;
}

function matchedAsset(...records: Array<Record<string, unknown> | undefined>): AssetMatch | undefined {
  for (const record of records) {
    if (!record) continue;
    const assetId = textValue(record.asset_id) || textValue(record.matched_asset_id);
    const name = textValue(record.name) || textValue(record.matched_asset_name);
    if ((record.matched === true || assetId || name) && (assetId || name)) {
      return {
        asset_id: assetId ?? name ?? "",
        name: name ?? assetId ?? "",
        imageUrl: assetImageUrl(record),
      };
    }
  }
  return undefined;
}

function initialMatches(rows: AssetSummaryRow[]): MatchState {
  const matches: MatchState = {};
  for (const row of rows) {
    if (row.matchedAsset) matches[row.key] = row.matchedAsset;
  }
  return matches;
}

function readonlyImages(value: unknown, rows: AssetSummaryRow[]): ImageState {
  const images: ImageState = {};
  const byName = new Map(rows.map((row) => [row.name, row.key]));
  for (const item of arrayOfRecords(recordValue(value)?.asset_images)) {
    const name = textValue(item.full_name) || textValue(item.name);
    const key = textValue(item.asset_key) || (name ? byName.get(name) : undefined);
    const url = textValue(item.image_url);
    if (key && url) images[key] = url;
  }
  return images;
}

function mapByName(items: Array<Record<string, unknown>>): Map<string, Record<string, unknown>> {
  const mapped = new Map<string, Record<string, unknown>>();
  for (const item of items) {
    const name = textValue(item.full_name) || textValue(item.name);
    if (name) mapped.set(name, item);
  }
  return mapped;
}

function arrayOfRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null) : [];
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : null;
}

function textValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((item) => displayValue(item)).filter(Boolean).join("、");
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return "";
}

function textareaRows(value: string): number {
  const lineRows = value.split(/\r?\n/).reduce((total, line) => total + Math.max(1, Math.ceil(line.length / 24)), 0);
  return Math.min(8, Math.max(2, lineRows));
}

function assetMatchesRowType(asset: AssetRecord, type: TabKey): boolean {
  const expected = tabLabels[type];
  const metadata = asset.metadata as Record<string, unknown>;
  const tags = Array.isArray(metadata.tags) ? metadata.tags : [];
  const values = [
    ...tags,
    metadata.asset_type,
    metadata.asset_kind,
    metadata.category,
    metadata.type,
  ].map((value) => String(value ?? "").trim()).filter(Boolean);
  return values.some((value) => value === expected || value === type || (type === "asset" && (value === "scene" || value === "场景")));
}

function assetSummary(asset: AssetRecord): string {
  const tags = Array.isArray(asset.metadata?.tags) ? asset.metadata.tags.filter((item) => typeof item === "string") : [];
  const parts = [asset.scope === "project" ? "项目资产" : "全局资产", ...tags.slice(0, 2)];
  return parts.join(" · ");
}

function assetImageUrl(asset: unknown): string | undefined {
  const record = recordValue(asset);
  if (!record) return undefined;
  const direct = textValue(record.image_url) || textValue(record.public_url) || textValue(record.storage_uri);
  if (direct) return direct;
  const metadata = recordValue(record.metadata);
  const metadataUrl = textValue(metadata?.image_url) || textValue(metadata?.public_url) || textValue(metadata?.storage_uri);
  if (metadataUrl) return metadataUrl;
  const objectStorage = recordValue(metadata?.object_storage);
  return textValue(objectStorage?.public_url);
}

function fieldLabel(key: string): string {
  const labels: Record<string, string> = {
    aliases: "别名",
    accessories: "配件",
    asset_id: "资产ID",
    category: "类别",
    character_status: "角色状态",
    description: "描述",
    full_name: "名称",
    matched: "是否匹配",
    matched_asset_id: "匹配资产ID",
    matched_asset_name: "匹配资产",
    name: "名称",
    new_accessories: "新增配件",
    reason: "原因",
    related_character: "关联角色",
    time_of_day: "时间特征",
    location_type: "地点类型",
    summary: "摘要",
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

function assetSummaryColumnClass(key: string): string {
  const twoCharacterColumns = new Set(["location_type", "time_of_day", "category", "related_character"]);
  const fourCharacterColumns = new Set(["aliases", "accessories", "new_accessories"]);
  if (twoCharacterColumns.has(key)) return "asset-summary-col-field-two-char";
  if (fourCharacterColumns.has(key)) return "asset-summary-col-field-four-char";
  return "asset-summary-col-field";
}

function uploadScope(projectId: string | undefined): Exclude<AssetScope, "combined"> {
  return projectId && projectId !== "global" ? "project" : "global";
}
