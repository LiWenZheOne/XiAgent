import { type ChangeEvent, type DragEvent, type PointerEvent, type WheelEvent, useEffect, useMemo, useRef, useState } from "react";

import { createAssetTag, generateAssetImage, listAssetTags, listAssetTagsForAsset, searchAssets, uploadAsset } from "../../api/assets";
import { ApiError } from "../../api/client";
import type { AssetRecord, AssetScope, AssetTag } from "../../api/types";
import { assetNameFromTagNames, assetTagNamesForCatalogAsset, assetTagNamesFromName, catalogAssetTypeTags } from "../../utils/assetNaming";
import type { NodeUiControlProps } from "../types";
import { AssetPickerDialog } from "./AssetPickerDialog";
import { assetSearchScopeForProject } from "./assetPicker";
import { createStoredZip, extensionFromBlobOrUrl, safeAssetImageFileName } from "./assetZip";

interface AssetImageCard {
  assetType: "character" | "scene" | "prop" | string;
  assetKey: string;
  title: string;
  variantName?: string;
  secondaryTagsText?: string;
  prompt?: string;
  referenceImageRef?: ImageRef;
  referenceSource?: string;
  referenceAppearanceDescription?: string;
  matchedAsset?: AssetMatch;
}

interface CardEditState {
  name: string;
  assetTags: string;
  prompt: string;
}

interface AssetMatch {
  asset_id?: string;
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
type ImageMetaState = Record<string, Record<string, string>>;
type UploadState = Record<string, string>;
type MatchState = Record<string, AssetMatch | null>;
type CardEditsState = Record<string, CardEditState>;
type GenerationStatus = "waiting" | "generating" | "success" | "failed";
type GenerationStatusState = Record<string, GenerationStatus>;
type GenerationErrorState = Record<string, string>;
type TabKey = "character" | "scene" | "prop" | "other";

interface AssetNameConflictDialog {
  assetNames: string[];
  scopeLabel: string;
}

interface AssetImagePreview {
  name: string;
  url: string;
}

interface GenerationProgress {
  total: number;
  completed: number;
  running: boolean;
}

interface GenerationJob {
  card: AssetImageCard;
}

interface AssetIdentity {
  assetType: TabKey;
  assetName: string;
  assetTags: string[];
}

interface AssetUploadPlan {
  card: AssetImageCard;
  edit: CardEditState;
  group: TabKey;
  fullName: string;
  identity: AssetIdentity;
  imageUrl: string;
}

type DefaultReferenceTemplates = Partial<Record<TabKey, string>>;

const groupLabels: Record<string, string> = {
  character: "角色",
  scene: "地点",
  prop: "道具",
  other: "其他",
};
const GENERATION_CONCURRENCY = 2;

export function AssetImageCardsControl({
  busy,
  config,
  node,
  projectId,
  onDraft,
  onSubmit,
}: NodeUiControlProps) {
  const readonly = config.mode === "readonly" || !onSubmit;
  const source = recordValue(readonly ? node.output_snapshot : node.input_snapshot);
  const cards = useMemo(() => buildAssetCards(source), [source]);
  const [images, setImages] = useState<ImageState>(() => readonlyImages(readonly ? node.output_snapshot : node.input_snapshot));
  const [imageMeta, setImageMeta] = useState<ImageMetaState>({});
  const imagesRef = useRef(images);
  const imageMetaRef = useRef(imageMeta);
  const draftPersistQueueRef = useRef<Promise<void>>(Promise.resolve());
  const [matches, setMatches] = useState<MatchState>(() => initialMatches(cards));
  const [edits, setEdits] = useState<CardEditsState>(() => initialCardEdits(cards));
  const matchesRef = useRef(matches);
  const editsRef = useRef(edits);
  const [uploading, setUploading] = useState<UploadState>({});
  const [generationStatuses, setGenerationStatuses] = useState<GenerationStatusState>({});
  const [generationErrors, setGenerationErrors] = useState<GenerationErrorState>({});
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const generationStatusesRef = useRef(generationStatuses);
  const generationQueueRef = useRef<GenerationJob[]>([]);
  const activeGenerationCountRef = useRef(0);
  const generationSummaryRef = useRef({ succeeded: 0, failed: 0 });
  const [brokenImageUrls, setBrokenImageUrls] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState<TabKey>("character");
  const [draggingKey, setDraggingKey] = useState("");
  const [error, setError] = useState("");
  const [pickerCard, setPickerCard] = useState<AssetImageCard | null>(null);
  const [libraryTags, setLibraryTags] = useState<AssetTag[]>([]);
  const [libraryBusy, setLibraryBusy] = useState(false);
  const [missingImageDialogOpen, setMissingImageDialogOpen] = useState(false);
  const [assetNameConflictDialog, setAssetNameConflictDialog] = useState<AssetNameConflictDialog | null>(null);
  const [previewImage, setPreviewImage] = useState<AssetImagePreview | null>(null);
  const tabs = useMemo(() => buildTabs(cards), [cards]);
  const selectedTab = tabs.some((tab) => tab.key === activeTab) ? activeTab : tabs[0]?.key ?? "character";
  const generatingCount = Object.values(generationStatuses).filter((status) => status === "waiting" || status === "generating").length;
  const generationProgressPercent = generationProgress?.total
    ? Math.round((generationProgress.completed / generationProgress.total) * 100)
    : 0;
  const defaultReferenceTemplates = useMemo(
    () => defaultReferenceTemplatesFromOptions(config.options),
    [config.options],
  );

  useEffect(() => {
    setMatches((current) => ({ ...initialMatches(cards), ...current }));
    setEdits((current) => ({ ...initialCardEdits(cards), ...current }));
  }, [cards]);

  useEffect(() => {
    imagesRef.current = images;
  }, [images]);

  useEffect(() => {
    imageMetaRef.current = imageMeta;
  }, [imageMeta]);

  useEffect(() => {
    matchesRef.current = matches;
  }, [matches]);

  useEffect(() => {
    editsRef.current = edits;
  }, [edits]);

  useEffect(() => {
    generationStatusesRef.current = generationStatuses;
  }, [generationStatuses]);

  useEffect(() => {
    if (readonly || !cards.length || !Object.keys(defaultReferenceTemplates).length) return;
    let active = true;
    void loadDefaultReferenceMatches(cards, defaultReferenceTemplates, projectId)
      .then((defaultMatches) => {
        if (!active || !Object.keys(defaultMatches).length) return;
        setMatches((current) => {
          const next = { ...current };
          let changed = false;
          for (const card of cards) {
            if (Object.prototype.hasOwnProperty.call(next, card.assetKey) || card.matchedAsset || card.referenceImageRef) continue;
            const defaultMatch = defaultMatches[card.assetKey];
            if (!defaultMatch) continue;
            next[card.assetKey] = defaultMatch;
            changed = true;
          }
          return changed ? next : current;
        });
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [cards, defaultReferenceTemplates, projectId, readonly]);

  useEffect(() => {
    let active = true;
    listAssetTags("combined", projectId && projectId !== "global" ? projectId : undefined)
      .then((items) => {
        if (active) setLibraryTags(items);
      })
      .catch(() => {
        if (active) setLibraryTags([]);
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  async function persistDraft(
    nextImages: ImageState,
    nextImageMeta: ImageMetaState,
    nextMatches: MatchState = matches,
    nextEdits: CardEditsState = edits,
  ) {
    if (readonly || !onDraft) return;
    const payload = interactionPayload("generate_missing", "", nextImages, nextImageMeta, nextMatches, nextEdits);
    const persist = () => onDraft(payload);
    const nextPersist = draftPersistQueueRef.current.then(persist, persist);
    draftPersistQueueRef.current = nextPersist.catch(() => undefined);
    await nextPersist;
  }

  function interactionPayload(
    decision: "finish" | "generate_missing",
    targetAssetName: string,
    imageState: ImageState,
    imageMetaState: ImageMetaState,
    matchState: MatchState,
    editState: CardEditsState,
  ): Record<string, unknown> {
    const payload: Record<string, unknown> = {
      decision,
      asset_images: cards
        .map((card) => {
          const match = activeMatchForCard(matchState, card);
          const edit = editState[card.assetKey] ?? cardEditFromCard(card);
          const imageUrl = (imageState[card.assetKey] || "").trim();
          if (!imageUrl) return null;
          const payload: Record<string, unknown> = {
            asset_type: card.assetType,
            asset_name: edit.name.trim() || card.title,
            image_url: imageUrl,
            source: imageMetaState[card.assetKey]?.source || "manual_upload",
          };
          const tags = assetTagsForEdit(edit);
          if (tags.length) payload.asset_tags = tags;
          Object.assign(payload, assetImagePayloadMeta(imageMetaState[card.assetKey]));
          if (match?.asset_id) payload.asset_id = match.asset_id;
          return payload;
        })
        .filter(Boolean),
    prompt_results: editedPromptResults(cards, editState, matchState),
    };
    if (targetAssetName) payload.target_asset_name = targetAssetName;
    return payload;
  }

  function finishPayload(createdAssetIds: string[] = []): Record<string, unknown> {
    const payload = interactionPayload("finish", "", images, imageMeta, matches, edits);
    payload.created_asset_ids = createdAssetIds;
    const assetImages = Array.isArray(payload.asset_images) ? payload.asset_images : [];
    assetImages.forEach((item, index) => {
      if (item && typeof item === "object" && createdAssetIds[index]) {
        (item as Record<string, unknown>).asset_id = createdAssetIds[index];
        (item as Record<string, unknown>).source = "library";
      }
    });
    return payload;
  }

  async function saveCardsToLibrary() {
    if (readonly || busy || libraryBusy) return;
    const readyCards = cards.filter((card) => Boolean(images[card.assetKey]));
    if (readyCards.length !== cards.length) {
      setMissingImageDialogOpen(true);
      return;
    }
    setLibraryBusy(true);
    setError("");
    setAssetNameConflictDialog(null);
    try {
      const uploadPlans = readyCards.map((card): AssetUploadPlan => {
        const edit = edits[card.assetKey] ?? cardEditFromCard(card);
        const group = tabKeyForAssetType(card.assetType);
        const fullName = cardDisplayName(edit, group);
        const imageUrl = images[card.assetKey];
        return { card, edit, group, fullName, identity: assetIdentityForEdit(edit, group), imageUrl };
      });
      const conflict = await findAssetNameConflicts(uploadPlans, projectId);
      if (conflict) {
        setAssetNameConflictDialog(conflict);
        return;
      }
      const createdAssets = await Promise.all(uploadPlans.map(async ({ card, edit, group, fullName, imageUrl }) => {
        const imageFile = await fileFromImageUrl(imageUrl, fullName);
        const tagIds = await ensureAssetTagIds({
          projectId,
          tags: assetLibraryTags(card, edit, group),
          currentTags: libraryTags,
          onTagsChanged: setLibraryTags,
        });
        try {
          return await uploadAsset({
            file: imageFile,
            scope: uploadScope(projectId),
            project_id: projectId && projectId !== "global" ? projectId : undefined,
            name: fullName,
            publish: true,
            metadata: {
              type: card.assetType,
              asset_type: card.assetType,
              asset_name: edit.name.trim() || card.title,
              asset_tags: assetTagsForEdit(edit),
              prompt: edit.prompt.trim(),
              appearance_description: card.referenceAppearanceDescription || "",
              source: "asset_catalog_workflow",
            },
            tag_ids: tagIds,
          });
        } catch (error) {
          throw enrichAssetNameConflict(error, fullName);
        }
      }));
      onSubmit?.(finishPayload(createdAssets.map((asset) => asset.asset_id).filter(Boolean)));
    } catch (nextError) {
      const conflict = assetNameConflictFromError(nextError);
      if (conflict) {
        setAssetNameConflictDialog(conflict);
        setError("");
      } else {
        setError(nextError instanceof Error ? nextError.message : "资产入库失败。");
      }
    } finally {
      setLibraryBusy(false);
    }
  }

  async function exportCardsZip() {
    const readyCards = cards.filter((card) => Boolean(images[card.assetKey]));
    if (!readyCards.length) {
      setError("暂无可导出的图像。");
      return;
    }
    setError("");
    try {
      const files = await Promise.all(readyCards.map(async (card) => {
        const edit = edits[card.assetKey] ?? cardEditFromCard(card);
        const response = await fetch(images[card.assetKey]);
        if (!response.ok) throw new Error(`${card.title} 图像下载失败。`);
        const blob = await response.blob();
        const bytes = new Uint8Array(await blob.arrayBuffer());
        const ext = extensionFromBlobOrUrl(blob, images[card.assetKey]);
        return {
          name: `${safeAssetImageFileName(cardDisplayName(edit, tabKeyForAssetType(card.assetType)))}${ext}`,
          bytes,
        };
      }));
      const zipBytes = createStoredZip(files);
      const zipBlob = new Blob([Uint8Array.from(zipBytes).buffer], { type: "application/zip" });
      const url = URL.createObjectURL(zipBlob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "资产图像.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "导出压缩包失败。");
    }
  }

  async function generateCards(target?: AssetImageCard) {
    if (readonly || busy) return;
    const targetCards = target ? [target] : cards.filter((card) => !imagesRef.current[card.assetKey]);
    const queuedCards = targetCards.filter((card) => {
      const status = generationStatusesRef.current[card.assetKey];
      return status !== "waiting" && status !== "generating";
    });
    if (!queuedCards.length) {
      setError("当前没有需要生成的缺图资产。");
      return;
    }
    setError("");
    setGenerationErrors((current) => {
      const next = { ...current };
      for (const card of queuedCards) delete next[card.assetKey];
      return next;
    });
    const startingNewRun = activeGenerationCountRef.current === 0 && generationQueueRef.current.length === 0;
    if (startingNewRun) {
      generationSummaryRef.current = { succeeded: 0, failed: 0 };
    }
    generationQueueRef.current = [
      ...generationQueueRef.current,
      ...queuedCards.map((card) => ({ card })),
    ];
    setGenerationStatuses((current) => {
      const next = { ...current };
      for (const card of queuedCards) next[card.assetKey] = "waiting";
      generationStatusesRef.current = next;
      return next;
    });
    setGenerationProgress((current) => ({
      total: (current?.running ? current.total : 0) + queuedCards.length,
      completed: current?.running ? current.completed : 0,
      running: true,
    }));
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
          if (summary.failed) {
            setError(`已生成 ${summary.succeeded} 张资产图像，${summary.failed} 张生成失败。`);
          } else {
            setError(`已生成 ${summary.succeeded} 张资产图像。`);
          }
        }
        processGenerationQueue();
      });
    }
  }

  async function runGenerationJob({ card }: GenerationJob) {
    setGenerationStatuses((current) => {
      const next = { ...current, [card.assetKey]: "generating" as GenerationStatus };
      generationStatusesRef.current = next;
      return next;
    });
    try {
      const edit = editsRef.current[card.assetKey] ?? cardEditFromCard(card);
      const activeMatch = activeMatchForCard(matchesRef.current, card);
      const promptResult = editedPromptResult(card, edit, activeMatch);
      const promptText = assetPromptText(card, config.options, activeMatch);
      const generated = await generateAssetImage({
        project_id: projectId,
        prompt_result: promptResult,
        prompt_prefix: promptText.prefix,
        prompt_suffix: promptText.suffix,
        aspect_ratio: tabKeyForAssetType(card.assetType) === "scene" ? "16:9" : "1:1",
        resolution: "2k",
      });
      const nextImages = { ...imagesRef.current, [card.assetKey]: generated.image_url };
      const nextImageMeta = {
        ...imageMetaRef.current,
        [card.assetKey]: {
          source: generated.source || "ai_generated",
          ...(generated.asset_id ? { asset_id: generated.asset_id } : {}),
          ...(generated.runninghub_task_id ? { runninghub_task_id: generated.runninghub_task_id } : {}),
          ...(generated.variant ? { variant: generated.variant } : {}),
        },
      };
      imagesRef.current = nextImages;
      imageMetaRef.current = nextImageMeta;
      setImages(nextImages);
      setImageMeta(nextImageMeta);
      setGenerationErrors((current) => {
        const next = { ...current };
        delete next[card.assetKey];
        return next;
      });
      setBrokenImageUrls((current) => {
        const next = { ...current };
        delete next[card.assetKey];
        return next;
      });
      setGenerationStatuses((current) => {
        const next = { ...current, [card.assetKey]: "success" as GenerationStatus };
        generationStatusesRef.current = next;
        return next;
      });
      generationSummaryRef.current = {
        ...generationSummaryRef.current,
        succeeded: generationSummaryRef.current.succeeded + 1,
      };
      await persistDraft(nextImages, nextImageMeta, matchesRef.current, editsRef.current);
    } catch (generationError) {
      setGenerationErrors((current) => ({
        ...current,
        [card.assetKey]: readableGenerationError(generationError),
      }));
      setGenerationStatuses((current) => {
        const next = { ...current, [card.assetKey]: "failed" as GenerationStatus };
        generationStatusesRef.current = next;
        return next;
      });
      generationSummaryRef.current = {
        ...generationSummaryRef.current,
        failed: generationSummaryRef.current.failed + 1,
      };
    }
  }

  async function uploadFileForCard(card: AssetImageCard, file: File | undefined) {
    if (!file) return;
    setUploading((current) => ({ ...current, [card.assetKey]: "上传中" }));
    setError("");
    try {
      const scope = uploadScope(projectId);
      const uploaded = await uploadAsset({
        file,
        scope,
        project_id: scope === "project" ? projectId : undefined,
        name: `${card.title}_图像`,
        publish: true,
      });
      const url = uploaded.metadata.public_url;
      if (!url) {
        setError("图片已上传，但没有可用于工作流的公开地址。");
        return;
      }
      const nextImages = { ...images, [card.assetKey]: url };
      const nextImageMeta = { ...imageMeta, [card.assetKey]: { source: "manual_upload", asset_id: uploaded.asset_id } };
      setImages(nextImages);
      setImageMeta(nextImageMeta);
      setBrokenImageUrls((current) => {
        const next = { ...current };
        delete next[card.assetKey];
        return next;
      });
      await persistDraft(nextImages, nextImageMeta);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "图片上传失败。");
    } finally {
      setUploading((current) => {
        const next = { ...current };
        delete next[card.assetKey];
        return next;
      });
    }
  }

  async function uploadCardImage(card: AssetImageCard, event: ChangeEvent<HTMLInputElement>) {
    await uploadFileForCard(card, event.target.files?.[0]);
    event.target.value = "";
  }

  async function dropCardImage(card: AssetImageCard, event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDraggingKey("");
    if (readonly || busy || uploading[card.assetKey]) return;
    await uploadFileForCard(card, event.dataTransfer.files?.[0]);
  }

  function openAssetPicker(card: AssetImageCard) {
    if (readonly) return;
    setPickerCard(card);
  }

  function selectMatchedAsset(card: AssetImageCard, asset: AssetRecord) {
    const imageUrl = assetImageUrl(asset);
    const nextMatches = {
      ...matches,
      [card.assetKey]: {
        asset_id: asset.asset_id,
        name: asset.name,
        imageRef: imageRefFromAsset(asset),
        imageUrl,
        appearanceDescription: assetAppearanceDescription(asset),
      },
    };
    setMatches(nextMatches);
    void persistDraft(images, imageMeta, nextMatches);
    setPickerCard(null);
  }

  if (!cards.length) {
    return (
      <section className="interaction-panel asset-image-cards-control">
        <div>
          <p className="eyebrow">{readonly ? "任务概况" : "资产补图"}</p>
          <h3>{readonly ? "暂无最终资产图像" : "暂无可补图资产"}</h3>
        </div>
      </section>
    );
  }

  return (
    <section className="interaction-panel asset-image-cards-control">
      <div className="asset-image-cards-head">
        <div>
          <p className="eyebrow">{readonly ? "任务概况" : "等待资产图像"}</p>
          <h3>{readonly ? "最终资产图像汇总" : "按资产卡片上传图像或生成缺图"}</h3>
        </div>
        {!readonly ? (
          <div className="asset-image-cards-actions">
            <button className="secondary-button" disabled={busy} type="button" onClick={() => void generateCards()}>
              {generatingCount ? `生成队列 ${generationProgress?.completed ?? 0}/${generationProgress?.total ?? generatingCount}` : "资产生成"}
            </button>
            <button className="primary-button" disabled={busy || libraryBusy} type="button" onClick={saveCardsToLibrary}>
              一键入库
            </button>
          </div>
        ) : (
          <div className="asset-image-cards-actions">
            <button className="secondary-button" type="button" onClick={exportCardsZip}>
              导出为压缩包
            </button>
          </div>
        )}
      </div>

      {generationProgress ? (
        <div className={generationProgress.running ? "asset-generation-progress running" : "asset-generation-progress"} role="status" aria-live="polite">
          <div>
            <strong>{generationProgress.running ? `正在生成资产图像（并发 ${GENERATION_CONCURRENCY}）` : "资产图像生成完成"}</strong>
            <span>{generationProgress.completed}/{generationProgress.total}</span>
          </div>
          <div className="asset-generation-progress-bar" aria-hidden="true">
            <span style={{ width: `${generationProgressPercent}%` }} />
          </div>
        </div>
      ) : null}

      <div className="asset-image-tabs" role="tablist" aria-label="资产类型">
        {tabs.map((tab) => (
          <button
            aria-selected={selectedTab === tab.key}
            className={selectedTab === tab.key ? "active" : ""}
            key={tab.key}
            role="tab"
            type="button"
            onClick={() => setActiveTab(tab.key)}
          >
            {groupLabels[tab.key]} <span>{tab.count}</span>
          </button>
        ))}
      </div>

      <AssetCardGroup
        busy={Boolean(busy)}
        cards={cards.filter((card) => tabKeyForAssetType(card.assetType) === selectedTab)}
        draggingKey={draggingKey}
        group={selectedTab}
        images={images}
        brokenImageUrls={brokenImageUrls}
        matches={matches}
        edits={edits}
        readonly={readonly}
        uploading={uploading}
        generationStatuses={generationStatuses}
        generationErrors={generationErrors}
        onPreview={(image) => setPreviewImage(image)}
        onDragState={setDraggingKey}
        onDrop={dropCardImage}
        onEdit={(card, patch) => {
          setEdits((current) => ({ ...current, [card.assetKey]: { ...(current[card.assetKey] ?? cardEditFromCard(card)), ...patch } }));
        }}
        onGenerate={(card) => void generateCards(card)}
        onBrokenImage={(card, url) => {
          setBrokenImageUrls((current) => ({ ...current, [card.assetKey]: url }));
        }}
        onOpenAssetPicker={openAssetPicker}
        onUpload={uploadCardImage}
      />
      {error ? <p className="form-error">{error}</p> : null}
      {previewImage ? (
        <AssetImageFullscreenViewer image={previewImage} onClose={() => setPreviewImage(null)} />
      ) : null}
      {missingImageDialogOpen ? (
        <div className="confirm-backdrop" role="presentation">
          <section className="confirm-dialog asset-missing-image-dialog" role="dialog" aria-modal="true" aria-label="缺少资产图像">
            <div>
              <p className="eyebrow">无法一键入库</p>
              <h2>还有资产没有图像</h2>
            </div>
            <p>请先为所有资产上传图像，或点击资产生成补齐缺失图像后再一键入库。</p>
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
                  void generateCards();
                }}
              >
                生成缺失图像
              </button>
            </div>
          </section>
        </div>
      ) : null}
      {assetNameConflictDialog ? (
        <div className="confirm-backdrop" role="presentation">
          <section className="confirm-dialog asset-name-conflict-dialog" role="dialog" aria-modal="true" aria-label="资产名称重复">
            <div>
              <p className="eyebrow">无法一键入库</p>
              <h2>资产名称重复</h2>
            </div>
            <p>以下资产名称已在{assetNameConflictDialog.scopeLabel}或本次入库列表中重复：</p>
            <ul className="asset-conflict-name-list">
              {assetNameConflictDialog.assetNames.map((assetName) => (
                <li key={assetName}>{assetName}</li>
              ))}
            </ul>
            <p>请修改这张卡片的资产名称或标签后再入库，或先处理资产库中的同名资产。</p>
            <div className="button-row end">
              <button className="primary-button" type="button" onClick={() => setAssetNameConflictDialog(null)}>
                知道了
              </button>
            </div>
          </section>
        </div>
      ) : null}
      {pickerCard ? (
        <AssetPickerDialog
          assetLabel={groupLabels[tabKeyForAssetType(pickerCard.assetType)] ?? "资产"}
          initialAssetId={activeMatchForCard(matches, pickerCard)?.asset_id}
          initialAssetName={activeMatchForCard(matches, pickerCard)?.name}
          projectId={projectId}
          tagName={tagNameForAssetType(pickerCard.assetType)}
          targetName={pickerCard.title}
          onClear={() => {
            setMatches((current) => ({ ...current, [pickerCard.assetKey]: null }));
            setPickerCard(null);
          }}
          onClose={() => setPickerCard(null)}
          onSelect={(asset) => selectMatchedAsset(pickerCard, asset)}
        />
      ) : null}
    </section>
  );
}

function AssetCardGroup({
  group,
  cards,
  images,
  brokenImageUrls,
  matches,
  edits,
  readonly,
  busy,
  uploading,
  generationStatuses,
  generationErrors,
  onPreview,
  draggingKey,
  onUpload,
  onDrop,
  onEdit,
  onGenerate,
  onBrokenImage,
  onOpenAssetPicker,
  onDragState,
}: {
  group: TabKey;
  cards: AssetImageCard[];
  images: ImageState;
  brokenImageUrls: Record<string, string>;
  matches: MatchState;
  edits: CardEditsState;
  readonly: boolean;
  busy: boolean;
  uploading: UploadState;
  generationStatuses: GenerationStatusState;
  generationErrors: GenerationErrorState;
  onPreview: (image: AssetImagePreview) => void;
  draggingKey: string;
  onUpload: (card: AssetImageCard, event: ChangeEvent<HTMLInputElement>) => void;
  onDrop: (card: AssetImageCard, event: DragEvent<HTMLElement>) => void;
  onEdit: (card: AssetImageCard, patch: Partial<CardEditState>) => void;
  onGenerate: (card: AssetImageCard) => void;
  onBrokenImage: (card: AssetImageCard, url: string) => void;
  onOpenAssetPicker: (card: AssetImageCard) => void;
  onDragState: (assetKey: string) => void;
}) {
  if (!cards.length) {
    return (
      <section className="asset-card-group">
        <header>
          <h4>{groupLabels[group] ?? "其他"}</h4>
          <span>0 个资产</span>
        </header>
        <p className="muted">暂无{groupLabels[group] ?? "其他"}资产。</p>
      </section>
    );
  }

  return (
    <section className="asset-card-group">
      <div className={`asset-image-card-grid ${group === "scene" ? "scene-grid" : "square-grid"}`}>
        {cards.map((card) => {
          const match = activeMatchForCard(matches, card);
          const edit = edits[card.assetKey] ?? cardEditFromCard(card);
          const finalImageUrl = images[card.assetKey] ?? "";
          const generationStatus = generationStatuses[card.assetKey] ?? "";
          const generationError = generationErrors[card.assetKey] ?? "";
          const imageUrl = finalImageUrl || match?.imageUrl || "";
          const previewImageUrl = brokenImageUrls[card.assetKey] === imageUrl ? "" : imageUrl;
          const displayName = cardDisplayName(edit, group);
          const matchDisplayName = assetDisplayName(match);
          const inputId = `asset-image-upload-${card.assetType}-${card.assetKey}`.replace(/[^\w-]/g, "_");
          const cardClass = [
            "asset-image-card",
            group === "scene" ? "scene-card" : "square-card",
            previewImageUrl ? "ready" : "missing",
            draggingKey === card.assetKey ? "dragging" : "",
          ].filter(Boolean).join(" ");
          return (
            <article
              className={cardClass}
              key={card.assetKey}
              onDragEnter={(event) => {
                if (readonly || busy) return;
                event.preventDefault();
                onDragState(card.assetKey);
              }}
              onDragOver={(event) => {
                if (readonly || busy) return;
                event.preventDefault();
              }}
              onDragLeave={(event) => {
                if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
                onDragState("");
              }}
              onDrop={(event) => onDrop(card, event)}
            >
              <header className="asset-image-card-title">
                <div>
                  <strong>{displayName}</strong>
                  <small>{match ? `关联：${matchDisplayName}` : "无资产关联"}</small>
                </div>
                {!readonly ? (
                  <button className="secondary-button" disabled={busy || generationStatus === "waiting" || generationStatus === "generating"} type="button" onClick={() => onGenerate(card)}>
                    {generationStatus === "waiting" ? "等待中" : generationStatus === "generating" ? "生成中" : finalImageUrl ? "重新生成" : "生成"}
                  </button>
                ) : <span>{previewImageUrl ? "已上传" : "未上传"}</span>}
              </header>
              <label className="asset-image-preview" htmlFor={inputId} aria-label={`${card.title} 选择图像`}>
                {previewImageUrl ? (
                  <img
                    src={previewImageUrl}
                    alt={`${card.title} 图像`}
                    onError={() => {
                      onBrokenImage(card, previewImageUrl);
                    }}
                  />
                ) : <span>点击选择<br />拖拽上传</span>}
                {previewImageUrl ? (
                  <button
                    aria-label="全屏查看图像"
                    className="asset-zoom-button"
                    title="全屏查看"
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      onPreview({ name: displayName, url: previewImageUrl });
                    }}
                  >
                    ⛶
                  </button>
                ) : null}
                {previewImageUrl ? (
                  <button
                    aria-label={`下载${displayName}图像`}
                    className="asset-image-download-button"
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      downloadImage(previewImageUrl, displayName);
                    }}
                  >
                    下载
                  </button>
                ) : null}
                {!readonly ? (
                  <input accept="image/*" disabled={busy || Boolean(uploading[card.assetKey])} id={inputId} type="file" onChange={(event) => onUpload(card, event)} />
                ) : null}
              </label>
              <div className="asset-image-card-body">
                <div className="asset-image-link-row">
                  <div>
                    <span>关联资产</span>
                    <strong>{match ? matchDisplayName : "无资产关联"}</strong>
                  </div>
                  <button
                    className={match ? "asset-match-button matched" : "asset-match-button missing"}
                    disabled={readonly && !match}
                    type="button"
                    onClick={() => onOpenAssetPicker(card)}
                  >
                    关联资产
                  </button>
                </div>
                <div className="asset-image-edit-grid">
                  <label>
                    <span>资产名称</span>
                    <input disabled={readonly || busy} value={edit.name} onChange={(event) => onEdit(card, { name: event.target.value })} />
                  </label>
                  <label>
                    <span>标签</span>
                    <input
                      aria-label={`${card.title} 标签`}
                      disabled={readonly || busy}
                      placeholder={group === "character" ? "如：囚服、毡笠" : "可留空，多个标签用顿号分隔"}
                      value={edit.assetTags}
                      onChange={(event) => onEdit(card, { assetTags: event.target.value })}
                    />
                  </label>
                </div>
                <div className="asset-image-prompt">
                  <span>提示词</span>
                  {readonly ? (
                    <p>{edit.prompt || "暂无提示词"}</p>
                  ) : (
                    <textarea aria-label="资产提示词" disabled={busy} value={edit.prompt} onChange={(event) => onEdit(card, { prompt: event.target.value })} />
                  )}
                </div>
                {!readonly ? (
                  <div className="asset-image-card-actions">
                    {uploading[card.assetKey] ? <span>{uploading[card.assetKey]}</span> : null}
                    {generationStatus ? <span className={`asset-image-card-status ${generationStatus}`}>{generationStatusLabel(generationStatus)}</span> : null}
                    {generationError ? <span className="asset-image-card-error">{generationError}</span> : null}
                  </div>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function downloadImage(url: string, name: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = safeAssetImageFileName(name) || "资产图像";
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function generationStatusLabel(status: GenerationStatus): string {
  if (status === "waiting") return "等待中";
  if (status === "generating") return "生成中";
  if (status === "success") return "成功";
  return "失败";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function AssetImageFullscreenViewer({ image, onClose }: { image: AssetImagePreview; onClose: () => void }) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef({ pointerId: -1, startX: 0, startY: 0, originX: 0, originY: 0 });

  useEffect(() => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
  }, [image.url]);

  useEffect(() => {
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function handleWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    setScale((current) => clamp(current * (event.deltaY < 0 ? 1.12 : 0.88), 0.2, 8));
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: offset.x,
      originY: offset.y,
    };
    setDragging(true);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragging || dragRef.current.pointerId !== event.pointerId) return;
    setOffset({
      x: dragRef.current.originX + event.clientX - dragRef.current.startX,
      y: dragRef.current.originY + event.clientY - dragRef.current.startY,
    });
  }

  function handlePointerEnd(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current.pointerId === event.pointerId) {
      setDragging(false);
      dragRef.current.pointerId = -1;
    }
  }

  return (
    <div aria-label={`全屏查看 ${image.name}`} aria-modal="true" className="asset-fullscreen-viewer" role="dialog" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div className="asset-fullscreen-toolbar" onMouseDown={(event) => event.stopPropagation()}>
        <strong>{image.name}</strong>
        <span>{Math.round(scale * 100)}%</span>
        <button className="secondary-button" type="button" onClick={() => {
          setScale(1);
          setOffset({ x: 0, y: 0 });
        }}>
          100%
        </button>
        <button className="secondary-button" type="button" onClick={onClose}>
          关闭
        </button>
      </div>
      <div
        className={dragging ? "asset-fullscreen-stage dragging" : "asset-fullscreen-stage"}
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose();
          event.stopPropagation();
        }}
        onPointerCancel={handlePointerEnd}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onWheel={handleWheel}
      >
        <img
          alt={image.name}
          draggable={false}
          src={image.url}
          style={{ transform: `translate3d(${offset.x}px, ${offset.y}px, 0) scale(${scale})` }}
        />
      </div>
    </div>
  );
}

function buildAssetCards(source: Record<string, unknown> | null): AssetImageCard[] {
  if (!source) return [];
  const completedImages = arrayOfRecords(source.asset_images);
  if (completedImages.length && !recordValue(source.approved_assets) && !arrayOfRecords(source.characters).length) {
    return completedImages.map((item, index) => {
      const title = textValue(item.asset_name) || textValue(item.name) || `资产 ${index + 1}`;
      return {
        assetType: textValue(item.asset_type) || "other",
        assetKey: `${textValue(item.asset_type) || "asset"}:${title}:${stringList(item.asset_tags).join("|")}`,
        title,
        prompt: textValue(item.prompt),
      };
    });
  }
  const approvedAssets = recordValue(source.approved_assets);
  const characters = arrayOfRecords(approvedAssets?.characters ?? source.characters).filter(shouldShowInImageStep);
  const enriched = mapByName(arrayOfRecords(source.enriched_characters));
  const variants = mapByName(arrayOfRecords(source.variant_results));
  const accessories = mapByName(arrayOfRecords(source.accessory_results));
  const promptItems = arrayOfRecords(source.prompt_results);
  const cards = characters.map((character) => {
    const name = textValue(character.asset_name) || textValue(character.name) || "未命名角色";
    const enrichedItem = enriched.get(name);
    const variant = variants.get(name);
    const accessory = accessories.get(name);
    const prompt = findPromptForAsset(promptItems, name);
    return {
      assetType: "character",
      assetKey: `character:${name}:${stringList(character.asset_tags).join("|")}`,
      title: name,
      matchedAsset: matchedAsset(character, enrichedItem),
      variantName: stringList(variant?.asset_tags)[0] || stringList(character.asset_tags)[0] || "",
      secondaryTagsText: stringList(accessory?.asset_tags).slice(1).join("、") || stringList(character.asset_tags).slice(1).join("、"),
      prompt: textValue(prompt?.prompt),
      referenceImageRef: imageRefFromValue(prompt?.reference_image_ref),
      referenceSource: textValue(prompt?.reference_source) || textValue(character.reference_source),
      referenceAppearanceDescription: textValue(prompt?.reference_appearance_description) || textValue(character.reference_appearance_description) || textValue(character.matched_asset_appearance_description),
    };
  });

  return [
    ...cards,
    ...genericCards(approvedAssets?.assets ?? source.scenes, "scene", promptItems),
    ...genericCards(approvedAssets?.props ?? source.props ?? source.items, "prop", promptItems),
  ];
}

function genericCards(value: unknown, assetType: string, prompts: Array<Record<string, unknown>>): AssetImageCard[] {
  return arrayOfRecords(value).filter(shouldShowInImageStep).map((item, index) => {
    const title = textValue(item.asset_name) || textValue(item.name) || `${groupLabels[assetType] ?? "资产"} ${index + 1}`;
    const prompt = findPromptForAsset(prompts, title);
    return {
      assetType,
      assetKey: `${assetType}:${title}:${stringList(item.asset_tags).join("|")}`,
      title,
      matchedAsset: matchedAsset(item),
      variantName: stringList(item.asset_tags)[0] || "",
      secondaryTagsText: stringList(item.asset_tags).slice(1).join("、"),
      prompt: textValue(prompt?.prompt) || textValue(item.prompt),
      referenceImageRef: imageRefFromValue(prompt?.reference_image_ref) || imageRefFromValue(item.reference_image_ref) || imageRefFromRecord(item),
      referenceSource: textValue(prompt?.reference_source) || textValue(item.reference_source),
      referenceAppearanceDescription: textValue(prompt?.reference_appearance_description) || textValue(item.reference_appearance_description) || textValue(item.matched_asset_appearance_description),
    };
  });
}

function shouldShowInImageStep(item: Record<string, unknown>): boolean {
  const matched = item.matched === true;
  const matchedAssetId = textValue(item.matched_asset_id);
  const matchedAssetName = textValue(item.matched_asset_name);
  return !(matched && (matchedAssetId || matchedAssetName));
}

function findPromptForAsset(prompts: Array<Record<string, unknown>>, name: string): Record<string, unknown> | undefined {
  const normalizedName = name.trim();
  return prompts.find((prompt) => promptKey(prompt) === normalizedName)
    ?? prompts.find((prompt) => promptKey(prompt).startsWith(`${normalizedName}_`))
    ?? prompts.find((prompt) => promptKey(prompt).includes(normalizedName));
}

function promptKey(prompt: Record<string, unknown>): string {
  return textValue(prompt.asset_name) || textValue(prompt.name) || "";
}

function buildTabs(cards: AssetImageCard[]): Array<{ key: TabKey; count: number }> {
  return (["character", "scene", "prop", "other"] as const)
    .map((key) => ({ key, count: cards.filter((card) => tabKeyForAssetType(card.assetType) === key).length }))
    .filter((tab) => tab.count > 0 || tab.key !== "other");
}

function tabKeyForAssetType(assetType: string): TabKey {
  if (assetType === "character" || assetType === "scene" || assetType === "prop") return assetType;
  return "other";
}

function assetPromptText(
  card: AssetImageCard,
  options: Record<string, unknown> | undefined,
  match?: AssetMatch | null,
): { prefix: string; suffix: string } {
  const promptTextByType = recordValue(options?.prompt_text_by_type);
  const group = tabKeyForAssetType(card.assetType);
  const usesDefaultReference = !match?.imageRef && card.referenceSource === "default_template";
  const promptKey = group === "character" && usesDefaultReference ? "character_default_reference" : group;
  const promptText = recordValue(promptTextByType?.[promptKey]) || recordValue(promptTextByType?.[group]);
  return {
    prefix: textValue(promptText?.prefix) || "",
    suffix: textValue(promptText?.suffix) || "",
  };
}

function readonlyImages(value: unknown): ImageState {
  const images: ImageState = {};
  for (const item of arrayOfRecords(recordValue(value)?.asset_images)) {
    const name = textValue(item.asset_name) || textValue(item.name);
    const key = name ? `${textValue(item.asset_type) || "asset"}:${name}:${stringList(item.asset_tags).join("|")}` : "";
    const url = textValue(item.image_url);
    if (key && url) images[key] = url;
  }
  return images;
}

function assetLibraryTags(card: AssetImageCard, edit: CardEditState, group: TabKey): string[] {
  const name = edit.name.trim() || card.title;
  const tags = assetTagsForEdit(edit);
  const [variantName = "", ...extraTags] = tags;
  return assetTagNamesForCatalogAsset({
    group: group === "character" || group === "scene" || group === "prop" ? group : "asset",
    name,
    variantName: group === "character" ? variantName || "默认" : variantName,
    accessories: extraTags.join("、"),
  });
}

async function ensureAssetTagIds(options: {
  projectId?: string;
  tags: string[];
  currentTags: AssetTag[];
  onTagsChanged: (tags: AssetTag[]) => void;
}): Promise<string[]> {
  const scope = uploadScope(options.projectId);
  const project_id = options.projectId && options.projectId !== "global" ? options.projectId : undefined;
  let knownTags = options.currentTags;
  const tagIds: string[] = [];
  for (const tagName of options.tags) {
    const cleanName = tagName.trim();
    if (!cleanName) continue;
    let tag = knownTags.find((item) => item.name === cleanName && item.scope === scope && (item.project_id || undefined) === project_id);
    if (!tag) {
      try {
        tag = await createAssetTag({ scope, project_id, name: cleanName });
        knownTags = [...knownTags, tag];
      } catch (error) {
        const refreshedTags = await listAssetTags(scope, project_id);
        const existingTag = refreshedTags.find((item) => item.name === cleanName && item.scope === scope && (item.project_id || undefined) === project_id);
        if (!existingTag) throw error;
        tag = existingTag;
        knownTags = refreshedTags;
      }
      options.onTagsChanged(knownTags);
    }
    tagIds.push(tag.tag_id);
  }
  return tagIds;
}

function tagNameForAssetType(assetType: string): string {
  const group = tabKeyForAssetType(assetType);
  if (group === "character") return catalogAssetTypeTags.character;
  if (group === "scene") return catalogAssetTypeTags.scene;
  if (group === "prop") return catalogAssetTypeTags.prop;
  return "";
}

async function fileFromImageUrl(imageUrl: string, fullName: string): Promise<File> {
  const response = await fetch(imageUrl);
  if (!response.ok) throw new Error(`${fullName} 图像下载失败，无法入库。`);
  const blob = await response.blob();
  const ext = extensionFromBlobOrUrl(blob, imageUrl);
  return new File([blob], `${safeAssetImageFileName(fullName)}${ext}`, {
    type: blob.type || "image/png",
  });
}

function initialMatches(cards: AssetImageCard[]): MatchState {
  const matches: MatchState = {};
  for (const card of cards) {
    if (card.matchedAsset) matches[card.assetKey] = card.matchedAsset;
  }
  return matches;
}

async function loadDefaultReferenceMatches(
  cards: AssetImageCard[],
  templates: DefaultReferenceTemplates,
  projectId?: string,
): Promise<MatchState> {
  const templatesByGroup = new Map<TabKey, string>();
  for (const card of cards) {
    if (card.matchedAsset || card.referenceImageRef) continue;
    const group = tabKeyForAssetType(card.assetType);
    const templateName = templates[group];
    if (templateName) templatesByGroup.set(group, templateName);
  }
  if (!templatesByGroup.size) return {};

  const assetsByGroup = new Map<TabKey, AssetRecord>();
  await Promise.all(Array.from(templatesByGroup.entries()).map(async ([group, templateName]) => {
    const searchScope = assetSearchScopeForProject(projectId);
    const items = await searchAssets({
      ...searchScope,
      names: [templateName],
      mime_type: "image/*",
      limit: 10,
    });
    const asset = items.find((item) => item.name === templateName) ?? items[0];
    if (asset) assetsByGroup.set(group, asset);
  }));

  const matches: MatchState = {};
  for (const card of cards) {
    if (card.matchedAsset || card.referenceImageRef) continue;
    const asset = assetsByGroup.get(tabKeyForAssetType(card.assetType));
    if (!asset) continue;
    matches[card.assetKey] = {
      asset_id: asset.asset_id,
      name: asset.name,
      imageRef: imageRefFromAsset(asset),
      imageUrl: assetImageUrl(asset),
      appearanceDescription: assetAppearanceDescription(asset),
    };
  }
  return matches;
}

function defaultReferenceTemplatesFromOptions(options: Record<string, unknown> | undefined): DefaultReferenceTemplates {
  const raw = recordValue(options?.default_reference_templates);
  if (!raw) return {};
  return {
    character: textValue(raw.character) || textValue(raw.characters),
    scene: textValue(raw.scene) || textValue(raw.scenes) || textValue(raw.asset) || textValue(raw.assets),
    prop: textValue(raw.prop) || textValue(raw.props),
  };
}

function initialCardEdits(cards: AssetImageCard[]): CardEditsState {
  return Object.fromEntries(cards.map((card) => [card.assetKey, cardEditFromCard(card)]));
}

function cardEditFromCard(card: AssetImageCard): CardEditState {
  return {
    name: card.title,
    assetTags: assetTagsTextFromCard(card),
    prompt: card.prompt || "",
  };
}

function cardDisplayName(edit: CardEditState, group: TabKey): string {
  const name = edit.name.trim();
  const tags = assetTagsForEdit(edit);
  const [variantName = "", ...extraTags] = tags;
  return assetNameFromTagNames(assetTagNamesForCatalogAsset({
    group: group === "character" || group === "scene" || group === "prop" ? group : "asset",
    name,
    variantName: group === "character" ? variantName || "默认" : variantName,
    accessories: extraTags.join("、"),
  })) || "未命名资产";
}

function assetIdentityForEdit(edit: CardEditState, group: TabKey): AssetIdentity {
  return {
    assetType: group,
    assetName: edit.name.trim(),
    assetTags: assetTagsForEdit(edit),
  };
}

function normalizedVariantName(name: string, variantName: string): string {
  const cleanVariant = variantName.trim();
  if (name && cleanVariant.startsWith(`${name}_`)) {
    return cleanVariant.slice(name.length + 1).trim();
  }
  return cleanVariant;
}

function editedPromptResults(cards: AssetImageCard[], edits: CardEditsState, matches: MatchState): Array<Record<string, unknown>> {
  return cards.map((card) => editedPromptResult(
    card,
    edits[card.assetKey] ?? cardEditFromCard(card),
    activeMatchForCard(matches, card),
  ));
}

function activeMatchForCard(matchState: MatchState, card: AssetImageCard): AssetMatch | null {
  if (Object.prototype.hasOwnProperty.call(matchState, card.assetKey)) {
    return matchState[card.assetKey] ?? null;
  }
  return card.matchedAsset ?? null;
}

async function findAssetNameConflicts(plans: AssetUploadPlan[], projectId?: string): Promise<AssetNameConflictDialog | null> {
  const scope = uploadScope(projectId);
  const project_id = projectId && projectId !== "global" ? projectId : undefined;
  const duplicatedNames = identitiesDuplicatedInBatch(plans);
  const existingNames = await existingAssetIdentityNames(plans, scope, project_id);
  const assetNames = Array.from(new Set([...duplicatedNames, ...existingNames])).sort((left, right) => left.localeCompare(right, "zh-Hans-CN"));
  if (!assetNames.length) return null;
  return {
    assetNames,
    scopeLabel: assetScopeLabel(scope),
  };
}

function identitiesDuplicatedInBatch(plans: AssetUploadPlan[]): string[] {
  const counts = new Map<string, number>();
  const labels = new Map<string, string>();
  for (const plan of plans) {
    const key = assetIdentityKey(plan.identity);
    if (!key) continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
    labels.set(key, plan.fullName);
  }
  return Array.from(counts.entries())
    .filter(([, count]) => count > 1)
    .map(([key]) => labels.get(key) ?? key);
}

async function existingAssetIdentityNames(plans: AssetUploadPlan[], scope: AssetScope, project_id?: string): Promise<string[]> {
  const uniquePlans = uniquePlansByIdentity(plans);
  const matchedNames: string[] = [];
  await Promise.all(uniquePlans.map(async (plan) => {
    const tagNames = assetLibraryTags(plan.card, plan.edit, plan.group);
    if (!tagNames.length) return;
    const candidates = await searchAssets({
      ...assetSearchScopeForProject(project_id),
      scope,
      tag_names: tagNames,
      limit: 50,
    });
    for (const candidate of candidates) {
      if (await assetRecordMatchesIdentity(candidate, plan.identity)) {
        matchedNames.push(candidate.name || plan.fullName);
      }
    }
  }));
  return matchedNames;
}

function uniquePlansByIdentity(plans: AssetUploadPlan[]): AssetUploadPlan[] {
  const seen = new Set<string>();
  const result: AssetUploadPlan[] = [];
  for (const plan of plans) {
    const key = assetIdentityKey(plan.identity);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(plan);
  }
  return result;
}

async function assetRecordMatchesIdentity(asset: AssetRecord, target: AssetIdentity): Promise<boolean> {
  const tags = await listAssetTagsForAsset(asset.asset_id);
  const identity = assetIdentityFromAssetRecord(asset, tags.map((tag) => tag.name));
  if (!identity) return false;
  if (identity.assetType !== target.assetType) return false;
  if (identity.assetName !== target.assetName) return false;
  if (!target.assetTags.length || !identity.assetTags.length) return true;
  if (identity.assetTags.some((tag) => normalizeIdentityText(tag) === normalizeIdentityText("默认"))) return true;
  return identity.assetTags.some((candidate) => target.assetTags.some((targetTag) => normalizeIdentityText(candidate) === normalizeIdentityText(targetTag)));
}

function assetIdentityFromAssetRecord(asset: AssetRecord, tagNames: string[]): AssetIdentity | null {
  const metadata = asset.metadata ?? {};
  const metadataType = typeof metadata.asset_type === "string" ? metadata.asset_type.trim() : "";
  const metadataName = typeof metadata.asset_name === "string" ? metadata.asset_name.trim() : "";
  const metadataTags = Array.isArray(metadata.asset_tags)
    ? metadata.asset_tags.filter((tag): tag is string => typeof tag === "string")
    : [];
  const metadataTab = tabKeyFromIdentityType(metadataType);
  if (metadataTab !== "other" && metadataName) {
    return {
      assetType: metadataTab,
      assetName: metadataName,
      assetTags: tagAtoms(metadataTags),
    };
  }

  const nameIdentity = assetIdentityFromTagNames(assetTagNamesFromName(asset.name));
  if (nameIdentity) return nameIdentity;
  return assetIdentityFromTagNames(tagNames);
}

function assetIdentityFromTagNames(tagNames: string[]): AssetIdentity | null {
  const index = tagNames.findIndex((tag) => tabKeyFromTypeTag(tag) !== "other");
  if (index < 0 || tagNames.length <= index + 1) return null;
  const assetType = tabKeyFromTypeTag(tagNames[index]);
  const assetName = tagNames[index + 1]?.trim() ?? "";
  if (!assetName) return null;
  return {
    assetType,
    assetName,
    assetTags: tagAtoms(tagNames.slice(index + 2)),
  };
}

function assetIdentityKey(identity: AssetIdentity): string {
  const name = normalizeIdentityText(identity.assetName);
  if (!name) return "";
  const tags = identity.assetTags.map(normalizeIdentityText).filter(Boolean).sort();
  return `${identity.assetType}:${name}:${tags.join("|")}`;
}

function tabKeyFromTypeTag(tag: string): TabKey {
  if (tag === catalogAssetTypeTags.character) return "character";
  if (tag === catalogAssetTypeTags.scene) return "scene";
  if (tag === catalogAssetTypeTags.prop) return "prop";
  return "other";
}

function tabKeyFromIdentityType(value: string): TabKey {
  if (value === "character" || value === catalogAssetTypeTags.character) return "character";
  if (value === "scene" || value === catalogAssetTypeTags.scene) return "scene";
  if (value === "prop" || value === catalogAssetTypeTags.prop) return "prop";
  return "other";
}

function tagAtoms(values: string[]): string[] {
  const tags: string[] = [];
  for (const value of values) {
    for (const part of value.replace("，", "、").replace(",", "、").replace("/", "、").replace("／", "、").split("、")) {
      const tag = part.trim();
      if (tag && !tags.includes(tag)) tags.push(tag);
    }
  }
  return tags;
}

function normalizeIdentityText(value: string): string {
  return value.trim().toLowerCase();
}

function enrichAssetNameConflict(error: unknown, fallbackName: string): unknown {
  const conflict = assetNameConflictFromError(error);
  if (!conflict && error instanceof ApiError && apiErrorCode(error) === "asset_name_conflict") {
    const details = apiErrorDetails(error);
    return new ApiError(error.message, error.status, {
      error: {
        code: "asset_name_conflict",
        message: error.message,
        details: { ...details, name: fallbackName },
      },
    });
  }
  if (conflict?.assetNames.length) return error;
  return error;
}

function assetNameConflictFromError(error: unknown): AssetNameConflictDialog | null {
  if (!(error instanceof ApiError) || apiErrorCode(error) !== "asset_name_conflict") return null;
  const details = apiErrorDetails(error);
  const assetName = textValue(details.name) || "未命名资产";
  return {
    assetNames: [assetName],
    scopeLabel: assetScopeLabel(textValue(details.scope) || ""),
  };
}

function apiErrorCode(error: ApiError): string {
  return textValue(recordValue(recordValue(error.body)?.error)?.code) || "";
}

function apiErrorDetails(error: ApiError): Record<string, unknown> {
  return recordValue(recordValue(recordValue(error.body)?.error)?.details) ?? {};
}

function assetScopeLabel(scope: string): string {
  if (scope === "global") return "全局资产库";
  if (scope === "project") return "项目资产库";
  return "当前资产库";
}

function readableGenerationError(error: unknown): string {
  const message = error instanceof Error ? error.message : "";
  if (message.includes("NOT_ENOUGH_BALANCE")) return "生成失败：余额不足，请充值后重试。";
  return message ? `生成失败：${message}` : "生成失败，请重试";
}

function editedPromptResult(card: AssetImageCard, edit: CardEditState, match: AssetMatch | null): Record<string, unknown> {
  const prompt: Record<string, unknown> = {
    asset_type: card.assetType,
    asset_name: edit.name.trim() || card.title,
    asset_tags: assetTagsForEdit(edit),
    prompt: edit.prompt.trim(),
  };
  const referenceImageRef = match?.imageRef || card.referenceImageRef;
  if (referenceImageRef) prompt.reference_image_ref = referenceImageRef;
  if (!match?.imageRef && card.referenceSource) prompt.reference_source = card.referenceSource;
  const appearanceDescription = match?.appearanceDescription || card.referenceAppearanceDescription || "";
  if (appearanceDescription) prompt.reference_appearance_description = appearanceDescription;
  return prompt;
}

function assetTagsForEdit(edit: CardEditState): string[] {
  return edit.assetTags
    .split(/[、,，]/)
    .map((item) => item.trim())
    .map((item) => normalizedVariantName(edit.name.trim(), item))
    .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index);
}

function assetTagsTextFromCard(card: AssetImageCard): string {
  const tags = [card.variantName, card.secondaryTagsText]
    .flatMap((value) => String(value ?? "").split(/[、,，]/))
    .map((item) => item.trim())
    .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index);
  return tags.join("、");
}

function assetDisplayName(match: AssetMatch | null | undefined): string {
  const name = match?.name.trim() ?? "";
  if (name && !isInternalAssetId(name)) return name;
  return "已关联资产";
}

function isInternalAssetId(value: string): boolean {
  return /^asset[_-][a-zA-Z0-9_-]{8,}$/.test(value.trim());
}

function matchedAsset(...records: Array<Record<string, unknown> | undefined>): AssetMatch | undefined {
  for (const record of records) {
    if (!record) continue;
    const hasExplicitMatchFields = "matched" in record || "matched_asset_id" in record || "matched_asset_name" in record;
    const matchedAssetId = textValue(record.matched_asset_id);
    const matchedAssetName = textValue(record.matched_asset_name);
    const assetId = matchedAssetId || (!hasExplicitMatchFields ? textValue(record.asset_id) : undefined);
    const name = matchedAssetName || (!hasExplicitMatchFields ? textValue(record.name) : undefined);
    if ((record.matched === true || assetId || name) && (assetId || name)) {
      return {
        asset_id: assetId,
        name: name ?? assetId ?? "",
        imageRef: imageRefFromRecord(record),
        imageUrl: assetImageUrl(record),
        appearanceDescription: assetAppearanceDescription(record),
      };
    }
  }
  return undefined;
}

function mapByName(items: Array<Record<string, unknown>>): Map<string, Record<string, unknown>> {
  const mapped = new Map<string, Record<string, unknown>>();
  for (const item of items) {
    const name = textValue(item.asset_name) || textValue(item.name);
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

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => textValue(item)).filter((item): item is string => Boolean(item)) : [];
}

function joinValue(value: unknown): string | undefined {
  if (Array.isArray(value)) {
    const items = value.map((item) => displayValue(item)).filter(Boolean);
    return items.length ? items.join("、") : undefined;
  }
  return textValue(value);
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((item) => displayValue(item)).filter(Boolean).join("、");
  return "";
}

function imageRefFromAsset(asset: AssetRecord): ImageRef {
  return { kind: "asset", asset_id: asset.asset_id, role: "reference" };
}

function imageRefFromRecord(record: Record<string, unknown>): ImageRef | undefined {
  const explicit = imageRefFromValue(record.reference_image_ref) || imageRefFromValue(record.matched_asset_ref);
  if (explicit) return explicit;
  const matchedAssetId = textValue(record.matched_asset_id);
  if (matchedAssetId) return { kind: "asset", asset_id: matchedAssetId, role: "reference" };
  const assetId = textValue(record.asset_id);
  if (assetId) return { kind: "asset", asset_id: assetId, role: "reference" };
  return undefined;
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

function assetImagePayloadMeta(meta: Record<string, string> | undefined): Record<string, string> {
  if (!meta) return {};
  return Object.fromEntries(
    ["source", "asset_id", "runninghub_task_id", "variant"]
      .map((key) => [key, meta[key]])
      .filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1].trim().length > 0),
  );
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
  const direct = textValue(record.matched_asset_appearance_description)
    || textValue(record.reference_appearance_description)
    || textValue(record.default_variant_appearance_description)
    || textValue(record.appearance_description)
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

function uploadScope(projectId: string | undefined): Exclude<AssetScope, "combined"> {
  return projectId && projectId !== "global" ? "project" : "global";
}
