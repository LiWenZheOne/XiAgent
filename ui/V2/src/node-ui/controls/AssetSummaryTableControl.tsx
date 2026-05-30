import { type ChangeEvent, useEffect, useMemo, useState } from "react";

import { draftAssetFromDescription, searchAssets, uploadAsset } from "../../api/assets";
import type { AssetRecord, AssetScope } from "../../api/types";
import type { NodeUiControlProps } from "../types";

type TabKey = "character" | "asset" | "prop";

interface AssetSummaryRow {
  key: string;
  type: TabKey;
  name: string;
  matchedAsset?: AssetMatch;
  imageUrl?: string;
  referenceImageRef?: ImageRef;
  referenceAppearanceDescription?: string;
  fields: Record<string, string>;
}

interface AssetMatch {
  asset_id: string;
  name: string;
  imageRef?: ImageRef;
  imageUrl?: string;
  appearanceDescription?: string;
}

interface ImageRef {
  kind: "asset" | "data_uri";
  asset_id?: string;
  data?: string;
  role?: string;
}

type ImageState = Record<string, string>;
type UploadState = Record<string, string>;
type MatchState = Record<string, AssetMatch | null>;
type DraftState = {
  assets: Array<Record<string, unknown>>;
  confidence: number;
  reasoning: string;
} | null;

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
  const source = useMemo(
    () => normalizeAssetSummarySource(readonly ? node.output_snapshot : node.input_snapshot),
    [node.input_snapshot, node.output_snapshot, readonly],
  );
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
  const [draftOpen, setDraftOpen] = useState(false);
  const [draftDescription, setDraftDescription] = useState("");
  const [additionalAssetRequest, setAdditionalAssetRequest] = useState("");
  const [draftResult, setDraftResult] = useState<DraftState>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState("");

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
    const approvedAssets = currentApprovedAssets(rows, matches);
    onSubmit?.({
      decision,
      approved_assets: approvedAssets,
      additional_asset_request: additionalAssetRequest.trim(),
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

  function openDraftDialog() {
    setDraftDescription(additionalAssetRequest);
    setDraftResult(null);
    setDraftError("");
    setDraftOpen(true);
  }

  async function generateDraftAsset() {
    const description = draftDescription.trim();
    if (!description) {
      setDraftError("请先描述需要新增的资产特征。");
      return;
    }
    setDraftLoading(true);
    setDraftError("");
    setDraftResult(null);
    try {
      const result = await draftAssetFromDescription({
        project_id: projectId,
        asset_type: "auto",
        description,
        script: textValue(source?.script) ?? "",
        background: textValue(source?.background) ?? "",
        current_assets: currentApprovedAssets(rows, matches),
      });
      setDraftResult({
        assets: normalizeDraftAssets(result),
        confidence: result.confidence,
        reasoning: result.reasoning,
      });
      setAdditionalAssetRequest(description);
    } catch (nextError) {
      setDraftError(nextError instanceof Error ? nextError.message : "AI 新增资产失败。");
    } finally {
      setDraftLoading(false);
    }
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

  return (
    <section className="interaction-panel asset-summary-table-control">
      <div className="asset-summary-head">
        <div>
          <p className="eyebrow">{readonly ? "资产列表结果" : "等待确认"}</p>
          <h3>资产列表汇总</h3>
        </div>
        {!readonly ? (
          <div className="asset-summary-actions">
            <button className="secondary-button" disabled={busy} type="button" onClick={openDraftDialog}>
              资产分析
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
            <col className="asset-summary-col-action" />
          </colgroup>
          <thead>
            <tr>
              <th>名称</th>
              <th>匹配资产</th>
              <th>图像</th>
              {columns.map((column) => <th key={column}>{fieldLabel(column)}</th>)}
              <th>操作</th>
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
                  <td className="asset-summary-action-cell">
                    {readonly ? <span className="asset-summary-readonly-action">—</span> : (
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
                    )}
                  </td>
                </tr>
              );
            }) : (
              <tr>
                <td colSpan={columns.length + 4}>暂无{tabLabels[activeTab]}。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      {draftOpen ? (
        <div className="confirm-backdrop" role="presentation">
          <section className="asset-draft-dialog" role="dialog" aria-modal="true" aria-label="资产分析">
            <header>
              <div>
                <p className="eyebrow">资产分析</p>
                <h3>根据描述分析并补全资产字段</h3>
              </div>
              <button className="secondary-button" disabled={draftLoading} type="button" onClick={() => setDraftOpen(false)}>关闭</button>
            </header>
            <label className="asset-draft-description">
              <span>描述需要新增的资产</span>
              <textarea
                disabled={draftLoading}
                placeholder="例如：官兵的船、船上的官兵、船上兵器。可以一次描述多个资产，系统会自动判断角色、地点或道具。"
                rows={4}
                value={draftDescription}
                onChange={(event) => {
                  setDraftDescription(event.target.value);
                  setAdditionalAssetRequest(event.target.value);
                  setDraftResult(null);
                }}
              />
            </label>
            <div className="button-row">
              <button className="primary-button" disabled={draftLoading || !draftDescription.trim()} type="button" onClick={() => void generateDraftAsset()}>
                {draftLoading ? "正在分析..." : "分析资产"}
              </button>
              <button
                className="secondary-button"
                disabled={draftLoading}
                type="button"
                onClick={() => {
                  addRow(activeTab);
                  setDraftOpen(false);
                }}
              >
                手动新增当前分类空行
              </button>
            </div>
            {draftError ? <p className="form-error">{draftError}</p> : null}
            {draftResult ? (
              <div className="asset-draft-preview">
                <div>
                  <p className="eyebrow">生成结果</p>
                  <h4>分析出 {draftResult.assets.length} 个资产</h4>
                  <p>{draftResult.reasoning}</p>
                  <small>可信度 {Math.round(draftResult.confidence * 100)}%</small>
                </div>
                {draftResult.assets.map((asset, assetIndex) => (
                  <div className="asset-draft-preview-item" key={`${textValue(asset.name) ?? "asset"}-${assetIndex}`}>
                    <h5>
                      <span>{tabLabels[rowTypeFromDraft(asset)]}</span>
                      {textValue(asset.name) ?? `资产 ${assetIndex + 1}`}
                    </h5>
                    <dl>
                      {Object.entries(asset).map(([key, value]) => (
                        <div key={key}>
                          <dt>{fieldLabel(key)}</dt>
                          <dd>{displayValue(value) || "—"}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
                <div className="button-row end">
                  <button className="secondary-button" disabled={busy} type="button" onClick={() => setDraftOpen(false)}>
                    保留修改意见
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
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
                        imageRef: { kind: "asset", asset_id: asset.asset_id, role: "reference" },
                        imageUrl: assetImageUrl(asset),
                        appearanceDescription: assetAppearanceDescription(asset),
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
    ...buildGroupRows("asset", arrayOfRecords(source.scenes).length ? arrayOfRecords(source.scenes) : arrayOfRecords(source.assets), {
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
    const variantRecord = related.variants?.get(name);
    const fields = {
      ...flattenRecord(item),
    };
    delete fields.full_name;
    delete fields.name;
    delete fields.image_url;
    delete fields.type;
    delete fields.matched;
    delete fields.matched_asset_id;
    delete fields.matched_asset_name;
    delete fields.matched_asset_ref;
    delete fields.reference_image_ref;
    delete fields.matched_asset_appearance_description;
    delete fields.reference_appearance_description;
    return {
      key: `${type}:${name}`,
      type,
      name,
      matchedAsset: matchedAsset(item, related.enriched?.get(name), related.byName?.get(name), related.semantic?.get(name), related.variants?.get(name)),
      imageUrl: assetImageUrl(item) || assetImageUrl(variantRecord) || textValue(item.image_url),
      referenceImageRef: imageRefFromRecord(variantRecord) || imageRefFromRecord(item),
      referenceAppearanceDescription: assetAppearanceDescription(variantRecord),
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
  if (match?.imageRef) {
    payload.matched_asset_ref = match.imageRef;
    payload.reference_image_ref = match.imageRef;
  } else if (row.referenceImageRef) {
    payload.reference_image_ref = row.referenceImageRef;
  }
  if (match?.appearanceDescription) {
    payload.matched_asset_appearance_description = match.appearanceDescription;
    payload.reference_appearance_description = match.appearanceDescription;
  } else if (row.referenceAppearanceDescription) {
    payload.reference_appearance_description = row.referenceAppearanceDescription;
  }
  return payload;
}

function currentApprovedAssets(rows: AssetSummaryRow[], matches: MatchState): Record<string, unknown> {
  return {
    characters: rows.filter((row) => row.type === "character").map((row) => rowPayload(row, matches[row.key] ?? row.matchedAsset ?? null)),
    assets: rows.filter((row) => row.type === "asset").map((row) => rowPayload(row, matches[row.key] ?? row.matchedAsset ?? null)),
    props: rows.filter((row) => row.type === "prop").map((row) => rowPayload(row, matches[row.key] ?? row.matchedAsset ?? null)),
  };
}

function normalizeAssetSummarySource(value: unknown): Record<string, unknown> | null {
  const source = recordValue(value);
  if (!source) return null;
  const approvedAssets = recordValue(source.approved_assets);
  if (!approvedAssets) return source;
  return {
    ...approvedAssets,
    asset_images: source.asset_images,
  };
}

function rowFromDraft(asset: Record<string, unknown>): AssetSummaryRow {
  const type = rowTypeFromDraft(asset);
  const name = textValue(asset.name) || `${tabLabels[type]} ${Date.now()}`;
  const fields = {
    ...defaultFieldsForType(type),
    ...flattenRecord(asset),
  };
  delete fields.type;
  delete fields.full_name;
  delete fields.name;
  delete fields.image_url;
  delete fields.matched;
  delete fields.matched_asset_id;
  delete fields.matched_asset_name;
  return {
    key: `${type}:ai:${Date.now()}:${name}`,
    type,
    name,
    fields,
  };
}

function normalizeDraftAssets(result: { assets?: Array<Record<string, unknown>>; asset?: Record<string, unknown> }): Array<Record<string, unknown>> {
  if (Array.isArray(result.assets)) {
    return result.assets.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null);
  }
  return result.asset && typeof result.asset === "object" ? [result.asset] : [];
}

function rowTypeFromDraft(asset: Record<string, unknown>): TabKey {
  const type = String(asset.type ?? "").trim().toLowerCase();
  if (type === "character" || type === "role" || type === "角色") return "character";
  if (type === "location" || type === "asset" || type === "scene" || type === "地点" || type === "场景") return "asset";
  return "prop";
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
    return { aliases: "", summary: "", character_status: "", variant_name: "", variant_description: "" };
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
    const matchedAssetId = textValue(record.matched_asset_id);
    const matchedAssetName = textValue(record.matched_asset_name);
    const matchedVariantId = textValue(record.matched_variant_id);
    const matchedVariantName = textValue(record.matched_variant);
    const hasExplicitMatchFields = Object.prototype.hasOwnProperty.call(record, "matched")
      || Object.prototype.hasOwnProperty.call(record, "matched_asset_id")
      || Object.prototype.hasOwnProperty.call(record, "matched_asset_name")
      || Object.prototype.hasOwnProperty.call(record, "matched_variant_id")
      || Object.prototype.hasOwnProperty.call(record, "matched_variant");
    const fallbackAssetId = !hasExplicitMatchFields ? textValue(record.asset_id) : undefined;
    const assetId = matchedAssetId || matchedVariantId || fallbackAssetId;
    const name = matchedAssetName || matchedVariantName || (fallbackAssetId ? textValue(record.name) : undefined);
    if ((record.matched === true || assetId || name) && (assetId || name)) {
      return {
        asset_id: assetId ?? name ?? "",
        name: name ?? assetId ?? "",
        imageRef: imageRefFromRecord(record),
        imageUrl: assetImageUrl(record),
        appearanceDescription: assetAppearanceDescription(record),
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

function imageRefFromRecord(record: Record<string, unknown> | undefined): ImageRef | undefined {
  if (!record) return undefined;
  const explicit = imageRefFromValue(record.reference_image_ref) || imageRefFromValue(record.matched_asset_ref);
  if (explicit) return explicit;
  const assetId = textValue(record.asset_id) || textValue(record.matched_asset_id) || textValue(record.matched_variant_id);
  return assetId ? { kind: "asset", asset_id: assetId, role: "reference" } : undefined;
}

function imageRefFromValue(value: unknown): ImageRef | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  if (record.kind === "asset") {
    const assetId = textValue(record.asset_id);
    return assetId ? { kind: "asset", asset_id: assetId, role: textValue(record.role) || "reference" } : undefined;
  }
  if (record.kind === "data_uri") {
    const data = textValue(record.data);
    return data?.startsWith("data:image/") ? { kind: "data_uri", data, role: textValue(record.role) || "reference" } : undefined;
  }
  return undefined;
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
  const direct = textValue(record.image_url)
    || textValue(record.public_url)
    || textValue(record.storage_uri)
    || textValue(record.default_variant_storage_uri);
  if (direct) return direct;
  const metadata = recordValue(record.metadata);
  const metadataUrl = textValue(metadata?.image_url) || textValue(metadata?.public_url) || textValue(metadata?.storage_uri);
  if (metadataUrl) return metadataUrl;
  const objectStorage = recordValue(metadata?.object_storage);
  return textValue(objectStorage?.public_url);
}

function assetAppearanceDescription(asset: unknown): string | undefined {
  const record = recordValue(asset);
  if (!record) return undefined;
  const direct = textValue(record.appearance_description)
    || textValue(record.matched_asset_appearance_description)
    || textValue(record.reference_appearance_description)
    || textValue(record.default_variant_appearance_description)
    || textValue(record.visual_description)
    || textValue(record.variant_description)
    || textValue(record.description)
    || textValue(record.prompt)
    || textValue(record.text_content);
  if (direct) return direct;
  const metadata = recordValue(record.metadata);
  return textValue(metadata?.appearance_description)
    || textValue(metadata?.visual_description)
    || textValue(metadata?.variant_description)
    || textValue(metadata?.description)
    || textValue(metadata?.prompt);
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
    variant_description: "变体描述",
    variant_name: "变体名",
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
