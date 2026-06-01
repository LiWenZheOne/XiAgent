import { type ChangeEvent, useEffect, useMemo, useState } from "react";

import {
  downloadAssetContent,
  generateStoryboardPanelImage,
  regenerateStoryboardPanelPrompt,
  searchAssets,
  uploadAsset,
} from "../../api/assets";
import type { AssetRecord } from "../../api/types";
import type { NodeUiControlProps } from "../types";
import { assetSearchScopeForProject } from "./assetPicker";

interface ImageRef {
  kind: "asset" | "data_uri";
  asset_id?: string;
  data?: string;
  role?: string;
}

interface ReferenceAsset {
  full_name: string;
  variant?: string;
  image_ref: ImageRef;
  image_url?: string;
  source?: "asset" | "upload";
}

interface ReferenceImage {
  image_ref: ImageRef;
  label: string;
  variant?: string;
  source?: "asset" | "upload";
  preview_url?: string;
}

interface PanelCard {
  card_id: string;
  segment_index: number;
  panel_index: number;
  segment_title: string;
  description: string;
  style: string;
  constraints: string;
  prompt: string;
  negative_prompt?: string;
  image_refs: ImageRef[];
  reference_images: ReferenceImage[];
  reference_assets: ReferenceAsset[];
  aspect_ratio: string;
  resolution: string;
  source_item?: Record<string, unknown>;
}

interface GeneratedImage {
  image_url: string;
  source?: string;
  runninghub_task_id?: string;
}

interface PanelDraft {
  prompt: string;
  reference_images: ReferenceImage[];
  generated_images: GeneratedImage[];
  selected_image_url: string;
  status?: string;
  error?: string;
}

interface AssetSearchDialogState {
  cardId: string;
  keyword: string;
  loading: boolean;
  error: string;
  assets: AssetRecord[];
}

type DraftMap = Record<string, PanelDraft>;

export function StoryboardPanelCardsControl({
  busy,
  config,
  node,
  onDraft,
  onSubmit,
  projectId,
}: NodeUiControlProps) {
  const readonly = config.mode === "readonly" || !onSubmit;
  const source = recordValue(readonly ? node.output_snapshot : node.input_snapshot);
  const output = recordValue(node.output_snapshot);
  const cards = useMemo(() => buildPanelCards(source, output), [source, output]);
  const [drafts, setDrafts] = useState<DraftMap>(() => initialDrafts(cards, output));
  const [generatingAll, setGeneratingAll] = useState(false);
  const [prompting, setPrompting] = useState<Record<string, boolean>>({});
  const [picker, setPicker] = useState<AssetSearchDialogState | null>(null);
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const sharedContext = recordValue(source.shared_context);

  useEffect(() => {
    setDrafts((current) => ({ ...initialDrafts(cards, output), ...current }));
  }, [cards, output]);

  useEffect(() => {
    let active = true;
    const objectUrls: string[] = [];
    const assetIds = Array.from(new Set(cards.flatMap((card) => {
      const draft = drafts[card.card_id];
      const refs = draft?.reference_images ?? card.reference_images;
      return refs.map((ref) => ref.image_ref.asset_id).filter((id): id is string => Boolean(id));
    })));
    if (!assetIds.length) {
      setPreviewUrls({});
      return () => undefined;
    }
    Promise.all(assetIds.map(async (assetId) => {
      try {
        const blob = await downloadAssetContent(assetId, projectId);
        if (!blob.type.startsWith("image/")) return null;
        const url = URL.createObjectURL(blob);
        objectUrls.push(url);
        return [assetId, url] as const;
      } catch {
        return null;
      }
    })).then((items) => {
      if (!active) return;
      setPreviewUrls(Object.fromEntries(items.filter((item): item is readonly [string, string] => Boolean(item))));
    });
    return () => {
      active = false;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [cards, drafts, projectId]);

  async function persist(nextDrafts: DraftMap) {
    if (readonly || !onDraft) return;
    await onDraft(payloadFromDrafts(cards, nextDrafts));
  }

  function updateCard(cardId: string, updater: (draft: PanelDraft) => PanelDraft) {
    setDrafts((current) => {
      const next = {
        ...current,
        [cardId]: updater(current[cardId] ?? draftFromCard(cards.find((card) => card.card_id === cardId))),
      };
      void persist(next);
      return next;
    });
  }

  async function generateCard(card: PanelCard) {
    const draft = drafts[card.card_id] ?? draftFromCard(card);
    const imageRefs = imageRefsFromReferenceImages(draft.reference_images);
    if (!imageRefs.length) {
      updateCard(card.card_id, (current) => ({ ...current, error: "请先添加至少一张参考图。" }));
      return;
    }
    updateCard(card.card_id, (current) => ({ ...current, status: "generating", error: "" }));
    try {
      const image = await generateStoryboardPanelImage({
        project_id: projectId,
        card_id: card.card_id,
        prompt: draft.prompt,
        image_refs: imageRefs.map((ref) => ({ ...ref })),
        negative_prompt: card.negative_prompt,
        aspect_ratio: card.aspect_ratio,
        resolution: card.resolution,
      });
      updateCard(card.card_id, (current) => {
        const nextImages = [...current.generated_images, image];
        return {
          ...current,
          generated_images: nextImages,
          selected_image_url: image.image_url,
          status: "ready",
          error: "",
        };
      });
    } catch (error) {
      updateCard(card.card_id, (current) => ({ ...current, status: "failed", error: readableError(error, "生成失败。") }));
    }
  }

  async function generateAll() {
    if (readonly || generatingAll) return;
    setGeneratingAll(true);
    await Promise.all(cards.map((card) => generateCard(card)));
    setGeneratingAll(false);
  }

  async function regeneratePrompt(card: PanelCard) {
    const item = card.source_item ?? {};
    if (!Object.keys(item).length) {
      updateCard(card.card_id, (current) => ({ ...current, error: "缺少当前段落上下文，无法重新生成提示词。" }));
      return;
    }
    setPrompting((current) => ({ ...current, [card.card_id]: true }));
    try {
      const result = await regenerateStoryboardPanelPrompt({
        project_id: projectId,
        card: { ...card },
        item,
        shared_context: sharedContext,
        negative_prompt: card.negative_prompt,
        aspect_ratio: card.aspect_ratio,
        resolution: card.resolution,
      });
      const nextCard = normalizeCard(result.card);
      updateCard(card.card_id, (current) => ({
        ...current,
        prompt: nextCard?.prompt || current.prompt,
        status: "prompt_ready",
        error: "",
      }));
    } catch (error) {
      updateCard(card.card_id, (current) => ({ ...current, status: "failed", error: readableError(error, "提示词重新生成失败。") }));
    } finally {
      setPrompting((current) => ({ ...current, [card.card_id]: false }));
    }
  }

  async function openPicker(cardId: string) {
    const next: AssetSearchDialogState = { cardId, keyword: "", loading: true, error: "", assets: [] };
    setPicker(next);
    await searchPickerAssets(next);
  }

  async function searchPickerAssets(state: AssetSearchDialogState) {
    setPicker((current) => current ? { ...current, loading: true, error: "" } : current);
    try {
      const assets = await searchAssets({
        ...assetSearchScopeForProject(projectId),
        keyword: state.keyword.trim() || undefined,
        mime_type: "image/",
      });
      setPicker((current) => current ? { ...current, loading: false, assets } : current);
    } catch (error) {
      setPicker((current) => current ? { ...current, loading: false, error: readableError(error, "资产搜索失败。") } : current);
    }
  }

  function addAssetReference(cardId: string, asset: AssetRecord, source: ReferenceImage["source"] = "asset") {
    const ref: ReferenceImage = {
      label: asset.name,
      image_ref: { kind: "asset", asset_id: asset.asset_id, role: "reference" },
      preview_url: asset.metadata?.public_url,
      source,
    };
    updateCard(cardId, (current) => addReference(current, ref));
    setPicker(null);
  }

  async function uploadReference(card: PanelCard, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    updateCard(card.card_id, (current) => ({ ...current, status: "uploading", error: "" }));
    try {
      const asset = await uploadAsset({
        file,
        scope: projectId && projectId !== "global" ? "project" : "global",
        project_id: projectId && projectId !== "global" ? projectId : undefined,
        name: file.name,
        publish: true,
        metadata: { source: "storyboard_panel_reference" },
      });
      addAssetReference(card.card_id, asset, "upload");
      updateCard(card.card_id, (current) => ({ ...current, status: "ready", error: "" }));
    } catch (error) {
      updateCard(card.card_id, (current) => ({ ...current, status: "failed", error: readableError(error, "上传失败。") }));
    }
  }

  function finish() {
    onSubmit?.(payloadFromDrafts(cards, drafts));
  }

  if (!cards.length) {
    return <p className="node-ui-empty">暂无可汇总的分镜卡片。</p>;
  }

  return (
    <section className="storyboard-panel-workbench" aria-label="分镜汇总">
      <header className="storyboard-panel-toolbar">
        <div>
          <p className="eyebrow">分镜汇总</p>
          <h3>{cards.length} 张分镜卡片</h3>
        </div>
        {!readonly ? (
          <div className="storyboard-panel-actions">
            <button className="secondary-button" type="button" disabled={busy || generatingAll} onClick={generateAll}>
              {generatingAll ? "生成中" : "一键生成"}
            </button>
            <button className="primary-button" type="button" disabled={busy} onClick={finish}>
              完成并继续
            </button>
          </div>
        ) : null}
      </header>

      <div className="storyboard-panel-grid">
        {cards.map((card) => {
          const draft = drafts[card.card_id] ?? draftFromCard(card);
          const selectedImage = draft.selected_image_url || draft.generated_images[draft.generated_images.length - 1]?.image_url || "";
          return (
            <article className="storyboard-panel-card" key={card.card_id}>
              <header className="storyboard-card-head">
                <div>
                  <p className="eyebrow">段落 {card.segment_index + 1} · 分格 {card.panel_index + 1}</p>
                  <h4>{card.segment_title}</h4>
                </div>
                {!readonly ? (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={busy || draft.status === "generating"}
                    onClick={() => generateCard(card)}
                  >
                    {selectedImage ? "重新生成" : "生成"}
                  </button>
                ) : null}
              </header>

              <div className="storyboard-card-workspace">
                <div className="storyboard-frame-column">
                  <section className="storyboard-generated-pool" aria-label="生成图像池">
                    <header>
                      <span>生成图像池</span>
                      <small>{draft.generated_images.length ? `${draft.generated_images.length} 张生成图` : "等待生成"}</small>
                    </header>
                    {draft.generated_images.length ? (
                      <div className="storyboard-generated-grid">
                        {draft.generated_images.map((image, index) => {
                          const active = selectedImage === image.image_url;
                          return (
                            <button
                              className={active ? "active" : ""}
                              key={`${image.image_url}-${index}`}
                              type="button"
                              disabled={readonly}
                              onClick={() => updateCard(card.card_id, (current) => ({ ...current, selected_image_url: image.image_url }))}
                            >
                              <img alt={`生成图 ${index + 1}`} src={image.image_url} />
                              <span>{active ? "已选定稿" : `生成 ${index + 1}`}</span>
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="storyboard-panel-preview">
                        <span>生成后的图像会进入这里</span>
                      </div>
                    )}
                  </section>
                </div>

                <div className="storyboard-editor-column">
                  <section className="storyboard-prompt-editor" aria-label="分段提示词编辑">
                    <header>
                      <span>分段提示词</span>
                      {!readonly ? (
                        <button
                          className="secondary-button storyboard-mini-button"
                          type="button"
                          disabled={Boolean(prompting[card.card_id])}
                          onClick={() => regeneratePrompt(card)}
                        >
                          {prompting[card.card_id] ? "提示词生成中" : "重新生成提示词"}
                        </button>
                      ) : null}
                    </header>
                    <textarea
                      aria-label="分段提示词"
                      readOnly={readonly}
                      value={draft.prompt}
                      onChange={(event) => updateCard(card.card_id, (current) => ({ ...current, prompt: event.target.value }))}
                    />
                  </section>

                  <section className="storyboard-image-pool" aria-label="参考图像池">
                    <header className="storyboard-image-pool-head">
                      <div>
                        <span>参考图像池</span>
                        <small>{draft.reference_images.length} 张参考图</small>
                      </div>
                      {!readonly ? (
                        <div>
                          <button className="secondary-button storyboard-mini-button" type="button" onClick={() => openPicker(card.card_id)}>添加资产</button>
                          <label className="secondary-button storyboard-mini-button">
                            上传图像
                            <input type="file" accept="image/*" onChange={(event) => uploadReference(card, event)} />
                          </label>
                        </div>
                      ) : null}
                    </header>
                    {draft.reference_images.length ? (
                      <div className="storyboard-image-pool-grid">
                        {draft.reference_images.map((ref, index) => {
                          const imageUrl = referenceImageUrl(ref, previewUrls);
                          const isUpload = ref.source === "upload";
                          return (
                            <div
                              className={`storyboard-pool-item ${isUpload ? "manual-source" : "asset-source"}`}
                              key={`${card.card_id}-${index}`}
                            >
                              <span className="storyboard-pool-thumb">
                                {imageUrl ? <img alt={`${ref.label} 参考图`} src={imageUrl} /> : "图"}
                              </span>
                              <span className="storyboard-pool-kind">{isUpload ? "上传" : "资产"}</span>
                              {!readonly ? (
                                <button type="button" aria-label={`删除参考图 ${ref.label}`} onClick={() => updateCard(card.card_id, (current) => removeReference(current, index))}>
                                  删除
                                </button>
                              ) : null}
                              <strong>{ref.label}</strong>
                              {ref.variant ? <small>{ref.variant}</small> : null}
                            </div>
                          );
                        })}
                      </div>
                    ) : <p className="storyboard-pool-empty">暂无参考图。</p>}
                  </section>
                </div>
              </div>
              {draft.error ? <p className="form-error">{draft.error}</p> : null}
            </article>
          );
        })}
      </div>

      {picker ? (
        <div className="confirm-backdrop" role="presentation">
          <section className="storyboard-asset-dialog" role="dialog" aria-modal="true" aria-label="添加参考资产">
            <header>
              <h3>添加参考资产</h3>
              <button className="secondary-button" type="button" onClick={() => setPicker(null)}>关闭</button>
            </header>
            <label>
              <span>搜索</span>
              <input
                autoFocus
                value={picker.keyword}
                onChange={(event) => setPicker({ ...picker, keyword: event.target.value })}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void searchPickerAssets(picker);
                }}
              />
            </label>
            <button className="secondary-button" type="button" onClick={() => searchPickerAssets(picker)}>搜索资产</button>
            {picker.error ? <p className="form-error">{picker.error}</p> : null}
            <div className="storyboard-asset-list">
              {picker.loading ? <p className="muted">正在搜索...</p> : null}
              {!picker.loading && picker.assets.map((asset) => (
                <button key={asset.asset_id} type="button" onClick={() => addAssetReference(picker.cardId, asset)}>
                  {asset.metadata?.public_url ? <img alt={`${asset.name} 图像`} src={asset.metadata.public_url} /> : <span>图</span>}
                  <strong>{asset.name}</strong>
                </button>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function buildPanelCards(source: Record<string, unknown>, output: Record<string, unknown>): PanelCard[] {
  const items = Array.isArray(source.panel_cards) ? source.panel_cards : output.panel_results;
  if (!Array.isArray(items)) return [];
  return items.map(normalizeCard).filter((card): card is PanelCard => Boolean(card));
}

function normalizeCard(value: unknown): PanelCard | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  const cardId = text(item.card_id);
  if (!cardId) return null;
  return {
    card_id: cardId,
    segment_index: numberValue(item.segment_index),
    panel_index: numberValue(item.panel_index),
    segment_title: text(item.segment_title) || `段落 ${numberValue(item.segment_index) + 1}`,
    description: text(item.description),
    style: text(item.style),
    constraints: text(item.constraints),
    prompt: text(item.prompt),
    negative_prompt: text(item.negative_prompt),
    image_refs: imageRefs(item.image_refs),
    reference_images: referenceImages(item.reference_images, item.reference_assets, item.image_refs),
    reference_assets: referenceAssets(item.reference_assets),
    aspect_ratio: text(item.aspect_ratio) || "16:9",
    resolution: text(item.resolution) || "2K",
    source_item: recordValue(item.source_item),
  };
}

function initialDrafts(cards: PanelCard[], output: Record<string, unknown>): DraftMap {
  const submitted = Array.isArray(output.panel_results) ? output.panel_results : [];
  const byCard = new Map(submitted.map((item) => [text(recordValue(item).card_id), recordValue(item)]));
  return Object.fromEntries(cards.map((card) => {
    const existing = byCard.get(card.card_id);
    return [card.card_id, existing ? draftFromSubmitted(card, existing) : draftFromCard(card)];
  }));
}

function draftFromCard(card?: PanelCard): PanelDraft {
  return {
    prompt: card?.prompt ?? "",
    reference_images: card?.reference_images ?? [],
    generated_images: [],
    selected_image_url: "",
  };
}

function draftFromSubmitted(card: PanelCard, value: Record<string, unknown>): PanelDraft {
  const generated = Array.isArray(value.generated_images)
    ? value.generated_images.map((item) => recordValue(item)).map((item) => ({ image_url: text(item.image_url), source: text(item.source), runninghub_task_id: text(item.runninghub_task_id) })).filter((item) => item.image_url)
    : [];
  const selected = text(value.selected_image_url);
  const submittedReferences = referenceImages(value.reference_images, value.reference_assets, value.image_refs);
  return {
    prompt: text(value.prompt) || card.prompt,
    reference_images: submittedReferences.length ? submittedReferences : card.reference_images,
    generated_images: generated,
    selected_image_url: selected || generated[generated.length - 1]?.image_url || "",
  };
}

function payloadFromDrafts(cards: PanelCard[], drafts: DraftMap): Record<string, unknown> {
  return {
    decision: "finish",
    panel_results: cards.map((card) => {
      const draft = drafts[card.card_id] ?? draftFromCard(card);
      const imageRefs = imageRefsFromReferenceImages(draft.reference_images);
      return {
        card_id: card.card_id,
        segment_index: card.segment_index,
        panel_index: card.panel_index,
        segment_title: card.segment_title,
        prompt: draft.prompt,
        reference_images: draft.reference_images,
        image_refs: imageRefs,
        reference_assets: legacyReferenceAssets(draft.reference_images),
        selected_image_url: draft.selected_image_url,
        generated_images: draft.generated_images,
      };
    }),
  };
}

function addReference(draft: PanelDraft, ref: ReferenceImage): PanelDraft {
  if (ref.image_ref.asset_id && draft.reference_images.some((item) => item.image_ref.asset_id === ref.image_ref.asset_id)) return draft;
  return {
    ...draft,
    reference_images: [...draft.reference_images, ref],
  };
}

function removeReference(draft: PanelDraft, index: number): PanelDraft {
  return {
    ...draft,
    reference_images: draft.reference_images.filter((_, itemIndex) => itemIndex !== index),
  };
}

function referenceImageUrl(ref: ReferenceImage, previewUrls: Record<string, string>): string {
  if (ref.preview_url) return ref.preview_url;
  if (ref.image_ref.kind === "data_uri") return ref.image_ref.data ?? "";
  return ref.image_ref.asset_id ? previewUrls[ref.image_ref.asset_id] ?? "" : "";
}

function imageRefsFromReferenceImages(referenceImages: ReferenceImage[]): ImageRef[] {
  return referenceImages.map((item) => item.image_ref).filter((item) => (item.kind === "asset" ? Boolean(item.asset_id) : Boolean(item.data)));
}

function legacyReferenceAssets(referenceImages: ReferenceImage[]): ReferenceAsset[] {
  return referenceImages.map((item) => ({
    full_name: item.label,
    variant: item.variant,
    image_ref: item.image_ref,
    image_url: item.preview_url,
    source: item.source ?? "asset",
  }));
}

function imageRefs(value: unknown): ImageRef[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const record = recordValue(item);
    const kind: ImageRef["kind"] = text(record.kind) === "data_uri" ? "data_uri" : "asset";
    return {
      kind,
      asset_id: text(record.asset_id) || undefined,
      data: text(record.data) || undefined,
      role: text(record.role) || "reference",
    };
  }).filter((item) => (item.kind === "asset" ? Boolean(item.asset_id) : Boolean(item.data)));
}

function referenceAssets(value: unknown): ReferenceAsset[] {
  if (!Array.isArray(value)) return [];
  const refs: ReferenceAsset[] = [];
  for (const rawItem of value) {
    const item = recordValue(rawItem);
    const imageRef = imageRefs([item.image_ref])[0];
    if (!imageRef) continue;
    refs.push({
      full_name: text(item.full_name) || "参考图",
      variant: text(item.variant) || undefined,
      image_ref: imageRef,
      image_url: text(item.image_url) || undefined,
      source: text(item.source) === "upload" ? "upload" : "asset",
    });
  }
  return refs;
}

function referenceImages(value: unknown, legacyAssets: unknown, legacyImageRefs: unknown): ReferenceImage[] {
  const direct = referenceImagesFromValue(value);
  if (direct.length) return direct;

  const assets = referenceAssets(legacyAssets);
  if (assets.length) {
    return assets.map((asset) => ({
      label: asset.full_name,
      variant: asset.variant,
      image_ref: asset.image_ref,
      preview_url: asset.image_url,
      source: asset.source,
    }));
  }

  return imageRefs(legacyImageRefs).map((imageRef, index) => ({
    label: `参考图 ${index + 1}`,
    image_ref: imageRef,
    source: imageRef.kind === "data_uri" ? "upload" : "asset",
  }));
}

function referenceImagesFromValue(value: unknown): ReferenceImage[] {
  if (!Array.isArray(value)) return [];
  const refs: ReferenceImage[] = [];
  for (const rawItem of value) {
    const item = recordValue(rawItem);
    const imageRef = imageRefs([item.image_ref])[0];
    if (!imageRef) continue;
    refs.push({
      label: text(item.label) || text(item.full_name) || "参考图",
      variant: text(item.variant) || undefined,
      image_ref: imageRef,
      preview_url: text(item.preview_url) || text(item.image_url) || undefined,
      source: text(item.source) === "upload" ? "upload" : "asset",
    });
  }
  return refs;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function readableError(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
