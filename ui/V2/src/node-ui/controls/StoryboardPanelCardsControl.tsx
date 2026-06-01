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
  image_refs: ImageRef[];
  reference_assets: ReferenceAsset[];
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
      const refs = draft?.reference_assets ?? card.reference_assets;
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
    const next = {
      ...drafts,
      [cardId]: updater(drafts[cardId] ?? draftFromCard(cards.find((card) => card.card_id === cardId))),
    };
    setDrafts(next);
    void persist(next);
  }

  async function generateCard(card: PanelCard) {
    const draft = drafts[card.card_id] ?? draftFromCard(card);
    if (!draft.image_refs.length) {
      updateCard(card.card_id, (current) => ({ ...current, error: "请先添加至少一张参考图。" }));
      return;
    }
    updateCard(card.card_id, (current) => ({ ...current, status: "generating", error: "" }));
    try {
      const image = await generateStoryboardPanelImage({
        project_id: projectId,
        card_id: card.card_id,
        prompt: draft.prompt,
        image_refs: draft.image_refs.map((ref) => ({ ...ref })),
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

  function addAssetReference(cardId: string, asset: AssetRecord) {
    const ref: ReferenceAsset = {
      full_name: asset.name,
      image_ref: { kind: "asset", asset_id: asset.asset_id, role: "reference" },
      image_url: asset.metadata?.public_url,
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
      addAssetReference(card.card_id, asset);
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
              <header>
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

              <div className="storyboard-panel-preview">
                {selectedImage ? <img alt={`${card.segment_title} 分镜图`} src={selectedImage} /> : <span>等待生成</span>}
              </div>

              <label className="storyboard-panel-prompt">
                <span>分段提示词</span>
                <textarea
                  readOnly={readonly}
                  value={draft.prompt}
                  onChange={(event) => updateCard(card.card_id, (current) => ({ ...current, prompt: event.target.value }))}
                />
              </label>

              <div className="storyboard-reference-list" aria-label="参考资产">
                <div className="storyboard-reference-head">
                  <span>参考资产</span>
                  {!readonly ? (
                    <div>
                      <button className="text-button" type="button" onClick={() => openPicker(card.card_id)}>添加资产</button>
                      <label className="text-button">
                        上传参考图
                        <input type="file" accept="image/*" onChange={(event) => uploadReference(card, event)} />
                      </label>
                    </div>
                  ) : null}
                </div>
                {draft.reference_assets.length ? draft.reference_assets.map((ref, index) => (
                  <div className="storyboard-reference-chip" key={`${card.card_id}-${index}`}>
                    <span className="storyboard-reference-thumb">
                      {referenceImageUrl(ref, previewUrls) ? <img alt={`${ref.full_name} 参考图`} src={referenceImageUrl(ref, previewUrls)} /> : "图"}
                    </span>
                    <span>
                      <strong>{ref.full_name}</strong>
                      {ref.variant ? <small>{ref.variant}</small> : null}
                    </span>
                    {!readonly ? (
                      <button type="button" aria-label={`删除参考资产 ${ref.full_name}`} onClick={() => updateCard(card.card_id, (current) => removeReference(current, index))}>
                        删除
                      </button>
                    ) : null}
                  </div>
                )) : <p className="muted">暂无参考图。</p>}
              </div>

              {draft.generated_images.length > 1 ? (
                <div className="storyboard-generated-strip" aria-label="生成历史">
                  {draft.generated_images.map((image, index) => (
                    <button
                      className={draft.selected_image_url === image.image_url ? "active" : ""}
                      key={`${image.image_url}-${index}`}
                      type="button"
                      disabled={readonly}
                      onClick={() => updateCard(card.card_id, (current) => ({ ...current, selected_image_url: image.image_url }))}
                    >
                      <img alt={`生成图 ${index + 1}`} src={image.image_url} />
                    </button>
                  ))}
                </div>
              ) : null}

              {!readonly ? (
                <button
                  className="text-button"
                  type="button"
                  disabled={Boolean(prompting[card.card_id])}
                  onClick={() => regeneratePrompt(card)}
                >
                  {prompting[card.card_id] ? "提示词生成中" : "重新生成提示词"}
                </button>
              ) : null}
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
    image_refs: card?.image_refs ?? [],
    reference_assets: card?.reference_assets ?? [],
    generated_images: [],
    selected_image_url: "",
  };
}

function draftFromSubmitted(card: PanelCard, value: Record<string, unknown>): PanelDraft {
  const generated = Array.isArray(value.generated_images)
    ? value.generated_images.map((item) => recordValue(item)).map((item) => ({ image_url: text(item.image_url), source: text(item.source), runninghub_task_id: text(item.runninghub_task_id) })).filter((item) => item.image_url)
    : [];
  const selected = text(value.selected_image_url);
  return {
    prompt: text(value.prompt) || card.prompt,
    image_refs: imageRefs(value.image_refs).length ? imageRefs(value.image_refs) : card.image_refs,
    reference_assets: referenceAssets(value.reference_assets).length ? referenceAssets(value.reference_assets) : card.reference_assets,
    generated_images: generated,
    selected_image_url: selected || generated[generated.length - 1]?.image_url || "",
  };
}

function payloadFromDrafts(cards: PanelCard[], drafts: DraftMap): Record<string, unknown> {
  return {
    decision: "finish",
    panel_results: cards.map((card) => {
      const draft = drafts[card.card_id] ?? draftFromCard(card);
      return {
        card_id: card.card_id,
        segment_index: card.segment_index,
        panel_index: card.panel_index,
        segment_title: card.segment_title,
        prompt: draft.prompt,
        image_refs: draft.image_refs,
        reference_assets: draft.reference_assets,
        selected_image_url: draft.selected_image_url,
        generated_images: draft.generated_images,
      };
    }),
  };
}

function addReference(draft: PanelDraft, ref: ReferenceAsset): PanelDraft {
  if (ref.image_ref.asset_id && draft.image_refs.some((item) => item.asset_id === ref.image_ref.asset_id)) return draft;
  return {
    ...draft,
    image_refs: [...draft.image_refs, ref.image_ref],
    reference_assets: [...draft.reference_assets, ref],
  };
}

function removeReference(draft: PanelDraft, index: number): PanelDraft {
  return {
    ...draft,
    image_refs: draft.image_refs.filter((_, itemIndex) => itemIndex !== index),
    reference_assets: draft.reference_assets.filter((_, itemIndex) => itemIndex !== index),
  };
}

function referenceImageUrl(ref: ReferenceAsset, previewUrls: Record<string, string>): string {
  if (ref.image_url) return ref.image_url;
  if (ref.image_ref.kind === "data_uri") return ref.image_ref.data ?? "";
  return ref.image_ref.asset_id ? previewUrls[ref.image_ref.asset_id] ?? "" : "";
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
