import { type ChangeEvent, type DragEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  downloadAssetThumbnail,
  generateStoryboardPanelImage,
  regenerateStoryboardPanelPrompt,
  searchAssets,
  uploadAsset,
} from "../../api/assets";
import {
  generateTaskStoryboardPanelImage,
  regenerateTaskStoryboardPanelPrompt,
} from "../../api/tasks";
import type { AssetRecord } from "../../api/types";
import type { NodeUiControlProps } from "../types";
import { AssetImageFullscreenViewer, type AssetImagePreview } from "./AssetImageCardsControl";
import { assetSearchScopeForProject } from "./assetPicker";

interface ImageRef {
  kind: "asset" | "data_uri";
  asset_id?: string;
  data?: string;
  role?: string;
}

interface ReferenceImage {
  image_ref: ImageRef;
  label: string;
  asset_type?: string;
  asset_name?: string;
  asset_tags?: string[];
  reference_index?: number;
  source?: "asset" | "upload";
  preview_url?: string;
}

interface PanelCard {
  card_id: string;
  segment_index: number;
  panel_index: number;
  segment_title: string;
  description: string;
  prompt: string;
  negative_prompt?: string;
  reference_images: ReferenceImage[];
  generated_images: GeneratedImage[];
  selected_image_url: string;
  aspect_ratio: string;
  resolution: string;
  source_item?: Record<string, unknown>;
  status?: GenerationStatus;
  error?: string;
}

interface GeneratedImage {
  image_url: string;
  source?: string;
  runninghub_task_id?: string;
  asset_id?: string;
}

interface PanelDraft {
  prompt: string;
  panel_count: string;
  reference_images: ReferenceImage[];
  generated_images: GeneratedImage[];
  selected_image_url: string;
  status?: GenerationStatus;
  error?: string;
}

type GenerationStatus = "waiting" | "generating" | "ready" | "failed" | "prompt_ready" | "uploading" | "";

interface GenerationJob {
  card: PanelCard;
}

interface GenerationProgress {
  total: number;
  completed: number;
  running: boolean;
}

interface AssetSearchDialogState {
  cardId: string;
  keyword: string;
  loading: boolean;
  error: string;
  assets: AssetRecord[];
}

type DraftMap = Record<string, PanelDraft>;

const GENERATION_CONCURRENCY = 2;

export function StoryboardPanelCardsControl({
  busy,
  config,
  node,
  onDraft,
  onSubmit,
  projectId,
  taskId,
}: NodeUiControlProps) {
  const readonly = config.mode === "readonly" || !onSubmit;
  const source = recordValue(readonly ? node.output_snapshot : node.input_snapshot);
  const output = recordValue(node.output_snapshot);
  const cards = useMemo(() => buildPanelCards(source, output), [source, output]);
  const [drafts, setDrafts] = useState<DraftMap>(() => initialDrafts(cards, source, output));
  const draftsRef = useRef(drafts);
  const draftPersistQueueRef = useRef<Promise<void>>(Promise.resolve());
  const generationQueueRef = useRef<GenerationJob[]>([]);
  const activeGenerationCountRef = useRef(0);
  const generationSummaryRef = useRef({ succeeded: 0, failed: 0 });
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const [prompting, setPrompting] = useState<Record<string, boolean>>({});
  const [uploading, setUploading] = useState<Record<string, string>>({});
  const [draggingCardId, setDraggingCardId] = useState("");
  const [missingImageDialogOpen, setMissingImageDialogOpen] = useState(false);
  const [previewImage, setPreviewImage] = useState<AssetImagePreview | null>(null);
  const [error, setError] = useState("");
  const [picker, setPicker] = useState<AssetSearchDialogState | null>(null);
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const sharedContext = recordValue(source.shared_context);
  const generatingCount = Object.values(drafts).filter((draft) => draft.status === "waiting" || draft.status === "generating").length;
  const generationProgressPercent = generationProgress?.total
    ? Math.round((generationProgress.completed / generationProgress.total) * 100)
    : 0;

  useEffect(() => {
    setDrafts((current) => ({ ...initialDrafts(cards, source, output), ...current }));
  }, [cards, source, output]);

  useEffect(() => {
    draftsRef.current = drafts;
  }, [drafts]);

  useEffect(() => {
    let active = true;
    const objectUrls: string[] = [];
    const assetIds = Array.from(new Set(cards.flatMap((card) => {
      const draft = drafts[card.card_id];
      const refs = draft?.reference_images ?? card.reference_images;
      const generated = draft?.generated_images ?? card.generated_images;
      return [
        ...refs.map((ref) => ref.image_ref.asset_id),
        ...generated.map((image) => image.asset_id),
      ].filter((id): id is string => Boolean(id));
    })));
    if (!assetIds.length) {
      setPreviewUrls({});
      return () => undefined;
    }
    Promise.all(assetIds.map(async (assetId) => {
      try {
        const blob = await downloadAssetThumbnail(assetId, projectId, 256);
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
    const persistDraft = () => onDraft(payloadFromDrafts(cards, nextDrafts));
    const nextPersist = draftPersistQueueRef.current.then(persistDraft, persistDraft);
    draftPersistQueueRef.current = nextPersist.catch(() => undefined);
    await nextPersist;
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

  function enqueueGeneration(cardsToQueue: PanelCard[]) {
    if (readonly || busy) return;
    const queuedCards = cardsToQueue.filter((card) => {
      const status = draftsRef.current[card.card_id]?.status;
      return status !== "waiting" && status !== "generating";
    });
    if (!queuedCards.length) {
      setError("当前没有需要生成的分镜卡片。");
      return;
    }
    setError("");
    const startingNewRun = activeGenerationCountRef.current === 0 && generationQueueRef.current.length === 0;
    if (startingNewRun) {
      generationSummaryRef.current = { succeeded: 0, failed: 0 };
    }
    generationQueueRef.current = [
      ...generationQueueRef.current,
      ...queuedCards.map((card) => ({ card })),
    ];
    setGenerationProgress((current) => ({
      total: (current?.running ? current.total : 0) + queuedCards.length,
      completed: current?.running ? current.completed : 0,
      running: true,
    }));
    setDrafts((current) => {
      const next = { ...current };
      for (const card of queuedCards) {
        next[card.card_id] = { ...(next[card.card_id] ?? draftFromCard(card)), status: "waiting", error: "" };
      }
      draftsRef.current = next;
      void persist(next);
      return next;
    });
    processGenerationQueue();
  }

  function processGenerationQueue() {
    while (activeGenerationCountRef.current < GENERATION_CONCURRENCY && generationQueueRef.current.length) {
      const job = generationQueueRef.current.shift();
      if (!job) return;
      activeGenerationCountRef.current += 1;
      void runGenerationJob(job).finally(() => {
        activeGenerationCountRef.current = Math.max(0, activeGenerationCountRef.current - 1);
        setGenerationProgress((current) => {
          if (!current) return current;
          const completed = Math.min(current.completed + 1, current.total);
          const running = activeGenerationCountRef.current > 0 || generationQueueRef.current.length > 0;
          return { ...current, completed, running };
        });
        if (activeGenerationCountRef.current === 0 && generationQueueRef.current.length === 0) {
          const summary = generationSummaryRef.current;
          setError(summary.failed ? `已生成 ${summary.succeeded} 张分镜图，${summary.failed} 张生成失败。` : `已生成 ${summary.succeeded} 张分镜图。`);
        }
        processGenerationQueue();
      });
    }
  }

  async function runGenerationJob({ card }: GenerationJob) {
    const draft = draftsRef.current[card.card_id] ?? draftFromCard(card);
    const imageRefs = imageRefsFromReferenceImages(draft.reference_images);
    if (!imageRefs.length) {
      updateCard(card.card_id, (current) => ({ ...current, status: "failed", error: "请先添加至少一张参考图。" }));
      generationSummaryRef.current.failed += 1;
      return;
    }
    updateCard(card.card_id, (current) => ({ ...current, status: "generating", error: "" }));
    try {
      const generationInput = {
        project_id: projectId || "global",
        node_id: node.node_id,
        card_id: card.card_id,
        prompt: draft.prompt,
        image_refs: imageRefs.map((ref) => ({ ...ref })),
        negative_prompt: card.negative_prompt,
        aspect_ratio: card.aspect_ratio,
        resolution: card.resolution,
      };
      const image = taskId
        ? await generateTaskStoryboardPanelImage(taskId, generationInput)
        : await generateStoryboardPanelImage({
            project_id: projectId,
            card_id: generationInput.card_id,
            prompt: generationInput.prompt,
            image_refs: generationInput.image_refs,
            negative_prompt: generationInput.negative_prompt,
            aspect_ratio: generationInput.aspect_ratio,
            resolution: generationInput.resolution,
          });
      updateCard(card.card_id, (current) => {
        const nextImages = [...current.generated_images, image];
        return {
          ...current,
          generated_images: nextImages,
          selected_image_url: current.selected_image_url || image.image_url,
          status: "ready",
          error: "",
        };
      });
      generationSummaryRef.current.succeeded += 1;
    } catch (error) {
      updateCard(card.card_id, (current) => ({ ...current, status: "failed", error: readableError(error, "生成失败。") }));
      generationSummaryRef.current.failed += 1;
    }
  }

  function generateCard(card: PanelCard) {
    enqueueGeneration([card]);
  }

  function generateMissing() {
    const missingCards = cards.filter((card) => !selectedImageUrl(draftsRef.current[card.card_id] ?? draftFromCard(card)));
    if (!missingCards.length) {
      setError("所有分镜卡片都已有选定图像。");
      return;
    }
    enqueueGeneration(missingCards);
  }

  async function regeneratePrompt(card: PanelCard) {
    const draft = draftsRef.current[card.card_id] ?? draftFromCard(card);
    const panelCount = normalizedPanelCount(draft.panel_count);
    if (!panelCount) {
      updateCard(card.card_id, (current) => ({ ...current, error: "请先填写有效的分格数量。" }));
      return;
    }
    const sourceItem = card.source_item ?? {};
    if (!Object.keys(sourceItem).length) {
      updateCard(card.card_id, (current) => ({ ...current, error: "缺少当前段落上下文，无法重新生成提示词。" }));
      return;
    }
    const item = { ...sourceItem, panel_count: panelCount };
    setPrompting((current) => ({ ...current, [card.card_id]: true }));
    try {
      const promptInput = {
        project_id: projectId || "global",
        node_id: node.node_id,
        card: { ...card, ...draft },
        item,
        shared_context: sharedContext,
        negative_prompt: card.negative_prompt,
        aspect_ratio: card.aspect_ratio,
        resolution: card.resolution,
      };
      const result = taskId
        ? await regenerateTaskStoryboardPanelPrompt(taskId, promptInput)
        : await regenerateStoryboardPanelPrompt({
            project_id: projectId,
            card: promptInput.card,
            item: promptInput.item,
            shared_context: promptInput.shared_context,
            negative_prompt: promptInput.negative_prompt,
            aspect_ratio: promptInput.aspect_ratio,
            resolution: promptInput.resolution,
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
      asset_name: asset.name,
      image_ref: { kind: "asset", asset_id: asset.asset_id, role: "reference" },
      preview_url: asset.metadata?.public_url,
      source,
    };
    updateCard(cardId, (current) => addReference(current, ref));
    setPicker(null);
  }

  async function uploadReferenceFile(card: PanelCard, file: File) {
    if (!file) return;
    setUploading((current) => ({ ...current, [card.card_id]: "上传中" }));
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
    } finally {
      setUploading((current) => {
        const next = { ...current };
        delete next[card.card_id];
        return next;
      });
    }
  }

  async function uploadReference(card: PanelCard, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await uploadReferenceFile(card, file);
  }

  function dropReference(card: PanelCard, event: DragEvent<HTMLElement>) {
    if (readonly || busy) return;
    event.preventDefault();
    setDraggingCardId("");
    const file = Array.from(event.dataTransfer.files).find((item) => item.type.startsWith("image/"));
    if (file) void uploadReferenceFile(card, file);
  }

  function finish() {
    if (cards.some((card) => !selectedImageUrl(drafts[card.card_id] ?? draftFromCard(card)))) {
      setMissingImageDialogOpen(true);
      return;
    }
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
            <button className="secondary-button" type="button" disabled={busy || Boolean(generatingCount)} onClick={generateMissing}>
              {generatingCount ? `生成队列 ${generationProgress?.completed ?? 0}/${generationProgress?.total ?? generatingCount}` : "一键生成分镜"}
            </button>
            <button className="primary-button" type="button" disabled={busy} onClick={finish}>
              完成并继续
            </button>
          </div>
        ) : null}
      </header>

      {generationProgress ? (
        <div className={generationProgress.running ? "asset-generation-progress running" : "asset-generation-progress"} role="status" aria-live="polite">
          <div>
            <strong>{generationProgress.running ? `正在生成分镜图像（并发 ${GENERATION_CONCURRENCY}）` : "分镜图像生成完成"}</strong>
            <span>{generationProgress.completed}/{generationProgress.total}</span>
          </div>
          <div className="asset-generation-progress-bar" aria-hidden="true">
            <span style={{ width: `${generationProgressPercent}%` }} />
          </div>
        </div>
      ) : null}

      <div className="storyboard-panel-grid">
        {cards.map((card) => {
          const draft = drafts[card.card_id] ?? draftFromCard(card);
          const selectedImage = draft.selected_image_url || draft.generated_images[draft.generated_images.length - 1]?.image_url || "";
          return (
            <article
              className={draggingCardId === card.card_id ? "storyboard-panel-card dragging" : "storyboard-panel-card"}
              key={card.card_id}
              onDragEnter={(event) => {
                if (readonly || busy) return;
                event.preventDefault();
                setDraggingCardId(card.card_id);
              }}
              onDragOver={(event) => {
                if (readonly || busy) return;
                event.preventDefault();
              }}
              onDragLeave={(event) => {
                if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
                setDraggingCardId("");
              }}
              onDrop={(event) => dropReference(card, event)}
            >
              <header className="storyboard-card-head">
                <div>
                  <p className="eyebrow">段落 {card.segment_index + 1} · 分格 {card.panel_index + 1}</p>
                  <h4>{card.segment_title}</h4>
                </div>
                <span className={`storyboard-card-status ${draftStatusClass(draft)}`}>{draftStatusLabel(draft)}</span>
                {!readonly ? (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={busy || draft.status === "generating"}
                    onClick={() => generateCard(card)}
                  >
                    {draft.status === "waiting" ? "等待中" : draft.status === "generating" ? "生成中" : selectedImage ? "重新生成" : "生成"}
                  </button>
                ) : null}
              </header>

              <div className="storyboard-card-workspace">
                <div className="storyboard-frame-column">
                  <section className="storyboard-generated-pool" aria-label="生成图像池">
                    <header>
                      <span>生成图像池</span>
                      <small>{draft.status === "waiting" ? "等待中" : draft.status === "generating" ? "生成中" : draft.generated_images.length ? `${draft.generated_images.length} 张生成图` : "等待生成"}</small>
                    </header>
                    {draft.generated_images.length ? (
                      <div className="storyboard-generated-grid">
                        {draft.generated_images.map((image, index) => {
                          const active = selectedImage === image.image_url;
                          const thumbnailUrl = generatedImageThumbnailUrl(image, previewUrls);
                          return (
                            <div
                              className={active ? "storyboard-generated-item active" : "storyboard-generated-item"}
                              key={`${image.image_url}-${index}`}
                            >
                              <button
                                className="storyboard-generated-select"
                                type="button"
                                disabled={readonly}
                                onClick={() => updateCard(card.card_id, (current) => ({ ...current, selected_image_url: image.image_url }))}
                              >
                                <img alt={`生成图 ${index + 1}`} loading="lazy" src={thumbnailUrl} />
                                <span className={active ? "storyboard-generated-badge active" : "storyboard-generated-badge"}>
                                  {active ? "已选定稿" : "备选"}
                                </span>
                              </button>
                              <button
                                aria-label={`全屏查看生成图 ${index + 1}`}
                                className="asset-zoom-button"
                                title="全屏查看"
                                type="button"
                                onClick={() => setPreviewImage({ name: `${card.segment_title} 分格 ${card.panel_index + 1} 生成图 ${index + 1}`, url: image.image_url })}
                              >
                                ⛶
                              </button>
                            </div>
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
                        <div className="storyboard-prompt-actions">
                          <label className="storyboard-panel-count-field">
                            <span>分格数</span>
                            <input
                              aria-label={`${card.segment_title} 分格数量`}
                              inputMode="numeric"
                              min={1}
                              step={1}
                              type="number"
                              value={draft.panel_count}
                              onChange={(event) => updateCard(card.card_id, (current) => ({ ...current, panel_count: event.target.value }))}
                            />
                          </label>
                          <button
                            className="secondary-button storyboard-mini-button"
                            type="button"
                            disabled={Boolean(prompting[card.card_id])}
                            onClick={() => regeneratePrompt(card)}
                          >
                            {prompting[card.card_id] ? "提示词生成中" : "重新生成提示词"}
                          </button>
                        </div>
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
                            {uploading[card.card_id] ? "上传中" : "上传图像"}
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
                                {imageUrl ? <img alt={`${ref.label} 参考图`} loading="lazy" src={imageUrl} /> : "图"}
                              </span>
                              <span className="storyboard-pool-kind">{isUpload ? "上传" : "资产"}</span>
                              {!readonly ? (
                                <button className="storyboard-pool-remove" type="button" aria-label={`删除参考图 ${ref.label}`} onClick={() => updateCard(card.card_id, (current) => removeReference(current, index))}>
                                  ×
                                </button>
                              ) : null}
                              <small>参考图{ref.reference_index || index + 1}</small>
                              <strong>{ref.label}</strong>
                              {ref.asset_tags?.length ? <small>{ref.asset_tags.join("、")}</small> : null}
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
      {error ? <p className="form-error">{error}</p> : null}

      {missingImageDialogOpen ? (
        <div className="confirm-backdrop" role="presentation">
          <section className="confirm-dialog storyboard-missing-image-dialog" role="dialog" aria-modal="true" aria-label="缺少分镜图像">
            <div>
              <p className="eyebrow">无法完成</p>
              <h2>还有分镜没有选定图像</h2>
            </div>
            <p>请先为所有分镜生成或选择定稿图像，再完成工作流。</p>
            <div className="button-row end">
              <button className="secondary-button" type="button" onClick={() => setMissingImageDialogOpen(false)}>
                知道了
              </button>
              <button
                className="primary-button"
                disabled={busy}
                type="button"
                onClick={() => {
                  setMissingImageDialogOpen(false);
                  generateMissing();
                }}
              >
                一键生成分镜
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {previewImage ? <AssetImageFullscreenViewer image={previewImage} onClose={() => setPreviewImage(null)} /> : null}

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
    prompt: text(item.prompt),
    negative_prompt: text(item.negative_prompt),
    reference_images: referenceImages(item.reference_images),
    generated_images: generatedImages(item.generated_images),
    selected_image_url: text(item.selected_image_url),
    aspect_ratio: text(item.aspect_ratio) || "16:9",
    resolution: text(item.resolution) || "2K",
    source_item: recordValue(item.source_item),
    status: generationStatus(item.status),
    error: text(item.error),
  };
}

function initialDrafts(cards: PanelCard[], source: Record<string, unknown>, output: Record<string, unknown>): DraftMap {
  const submitted = Array.isArray(output.panel_results)
    ? output.panel_results
    : Array.isArray(source.panel_results)
      ? source.panel_results
      : [];
  const byCard = new Map(submitted.map((item) => [text(recordValue(item).card_id), recordValue(item)]));
  return Object.fromEntries(cards.map((card) => {
    const existing = byCard.get(card.card_id);
    return [card.card_id, existing ? draftFromSubmitted(card, existing) : draftFromCard(card)];
  }));
}

function draftFromCard(card?: PanelCard): PanelDraft {
  return {
    prompt: card?.prompt ?? "",
    panel_count: panelCountFromCard(card),
    reference_images: card?.reference_images ?? [],
    generated_images: card?.generated_images ?? [],
    selected_image_url: card?.selected_image_url || card?.generated_images[card.generated_images.length - 1]?.image_url || "",
    status: card?.status,
    error: card?.error ?? "",
  };
}

function draftFromSubmitted(card: PanelCard, value: Record<string, unknown>): PanelDraft {
  const generated = generatedImages(value.generated_images);
  const selected = text(value.selected_image_url);
  const submittedReferences = referenceImages(value.reference_images);
  return {
    prompt: text(value.prompt) || card.prompt,
    panel_count: text(value.panel_count) || panelCountFromCard(card),
    reference_images: submittedReferences.length ? submittedReferences : card.reference_images,
    generated_images: generated,
    selected_image_url: selected || generated[generated.length - 1]?.image_url || "",
    status: generationStatus(value.status) || card.status,
    error: text(value.error) || card.error || "",
  };
}

function selectedImageUrl(draft: PanelDraft): string {
  return draft.selected_image_url || draft.generated_images[draft.generated_images.length - 1]?.image_url || "";
}

function panelCountFromCard(card?: PanelCard): string {
  const sourceCount = card?.source_item ? text(card.source_item.panel_count) : "";
  return normalizedPanelCount(sourceCount) || "1";
}

function normalizedPanelCount(value: string): string {
  const parsed = Number.parseInt(value.trim(), 10);
  if (!Number.isFinite(parsed) || parsed < 1) return "";
  return String(parsed);
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
        panel_count: normalizedPanelCount(draft.panel_count) || panelCountFromCard(card),
        reference_images: draft.reference_images,
        selected_image_url: selectedImageUrl(draft),
        generated_images: draft.generated_images,
      };
    }),
  };
}

function draftStatusLabel(draft: PanelDraft): string {
  if (draft.status === "waiting") return "等待生成";
  if (draft.status === "generating") return "生成中";
  if (draft.status === "failed") return "生成失败";
  if (draft.status === "uploading") return "上传中";
  if (selectedImageUrl(draft)) return "已定稿";
  return "待生成";
}

function draftStatusClass(draft: PanelDraft): string {
  if (draft.status === "waiting") return "waiting";
  if (draft.status === "generating" || draft.status === "uploading") return "running";
  if (draft.status === "failed") return "failed";
  if (selectedImageUrl(draft)) return "ready";
  return "missing";
}

function generationStatus(value: unknown): GenerationStatus {
  const status = text(value);
  return ["waiting", "generating", "ready", "failed", "prompt_ready", "uploading"].includes(status)
    ? status as GenerationStatus
    : "";
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
  if (ref.image_ref.asset_id && previewUrls[ref.image_ref.asset_id]) return previewUrls[ref.image_ref.asset_id];
  if (ref.preview_url) return ref.preview_url;
  if (ref.image_ref.kind === "data_uri") return ref.image_ref.data ?? "";
  return "";
}

function generatedImages(value: unknown): GeneratedImage[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => recordValue(item))
    .map((item) => ({
      image_url: text(item.image_url),
      source: text(item.source),
      runninghub_task_id: text(item.runninghub_task_id),
      asset_id: text(item.asset_id),
    }))
    .filter((item) => item.image_url);
}

function generatedImageThumbnailUrl(image: GeneratedImage, previewUrls: Record<string, string>): string {
  return image.asset_id ? previewUrls[image.asset_id] || image.image_url : image.image_url;
}

function imageRefsFromReferenceImages(referenceImages: ReferenceImage[]): ImageRef[] {
  return referenceImages.map((item) => item.image_ref).filter((item) => (item.kind === "asset" ? Boolean(item.asset_id) : Boolean(item.data)));
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

function referenceImages(value: unknown): ReferenceImage[] {
  return referenceImagesFromValue(value);
}

function referenceImagesFromValue(value: unknown): ReferenceImage[] {
  if (!Array.isArray(value)) return [];
  const refs: ReferenceImage[] = [];
  for (const rawItem of value) {
    const item = recordValue(rawItem);
    const imageRef = imageRefs([item.image_ref])[0];
    if (!imageRef) continue;
    refs.push({
      label: text(item.label) || text(item.asset_name) || "参考图",
      asset_type: text(item.asset_type) || undefined,
      asset_name: text(item.asset_name) || text(item.label) || undefined,
      asset_tags: stringList(item.asset_tags),
      reference_index: numberValue(item.reference_index) || refs.length + 1,
      image_ref: imageRef,
      preview_url: text(item.preview_url) || undefined,
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

function stringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const items = value.map((item) => text(item)).filter(Boolean);
  return items.length ? items : undefined;
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function readableError(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
