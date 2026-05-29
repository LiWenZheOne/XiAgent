import { type ChangeEvent, useMemo, useState } from "react";

import { uploadAsset } from "../../api/assets";
import type { AssetScope } from "../../api/types";
import type { NodeUiControlProps } from "../types";

interface AssetImageCard {
  assetType: "character" | "scene" | "prop" | string;
  assetKey: string;
  title: string;
  fields: Array<{ label: string; value: string }>;
  prompt?: string;
  referenceImageUrl?: string;
}

type ImageState = Record<string, string>;
type UploadState = Record<string, string>;

const groupLabels: Record<string, string> = {
  character: "角色",
  scene: "地点",
  prop: "道具",
};

export function AssetImageCardsControl({
  busy,
  config,
  node,
  projectId,
  onSubmit,
}: NodeUiControlProps) {
  const readonly = config.mode === "readonly" || !onSubmit;
  const source = recordValue(readonly ? node.output_snapshot : node.input_snapshot);
  const cards = useMemo(() => buildAssetCards(source), [source]);
  const [images, setImages] = useState<ImageState>(() => readonlyImages(node.output_snapshot));
  const [uploading, setUploading] = useState<UploadState>({});
  const [error, setError] = useState("");

  function submit(decision: "finish" | "generate_missing") {
    if (readonly || busy) return;
    onSubmit?.({
      decision,
      asset_images: cards
        .map((card) => {
          const imageUrl = images[card.assetKey]?.trim();
          if (!imageUrl) return null;
          return {
            asset_type: card.assetType,
            asset_key: card.assetKey,
            full_name: card.title,
            image_url: imageUrl,
            source: "manual_upload",
          };
        })
        .filter(Boolean),
    });
  }

  async function uploadCardImage(card: AssetImageCard, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
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
      setImages((current) => ({ ...current, [card.assetKey]: url }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "图片上传失败。");
    } finally {
      event.target.value = "";
      setUploading((current) => {
        const next = { ...current };
        delete next[card.assetKey];
        return next;
      });
    }
  }

  if (!cards.length) {
    return (
      <section className="interaction-panel asset-image-cards-control">
        <div>
          <p className="eyebrow">资产补图</p>
          <h3>暂无可补图资产</h3>
        </div>
      </section>
    );
  }

  return (
    <section className="interaction-panel asset-image-cards-control">
      <div className="asset-image-cards-head">
        <div>
          <p className="eyebrow">{readonly ? "资产图像结果" : "等待资产图像"}</p>
          <h3>{readonly ? "已提交的资产图像" : "按资产卡片上传图像或生成缺图"}</h3>
        </div>
        {!readonly ? (
          <div className="asset-image-cards-actions">
            <button className="secondary-button" disabled={busy} type="button" onClick={() => submit("finish")}>
              完成上传
            </button>
            <button className="primary-button" disabled={busy} type="button" onClick={() => submit("generate_missing")}>
              一键生成未上传图像
            </button>
          </div>
        ) : null}
      </div>

      {(["character", "scene", "prop"] as const).map((group) => (
        <AssetCardGroup
          busy={Boolean(busy)}
          cards={cards.filter((card) => card.assetType === group)}
          group={group}
          images={images}
          key={group}
          readonly={readonly}
          uploading={uploading}
          onUpload={uploadCardImage}
        />
      ))}
      <AssetCardGroup
        busy={Boolean(busy)}
        cards={cards.filter((card) => !["character", "scene", "prop"].includes(card.assetType))}
        group="other"
        images={images}
        readonly={readonly}
        uploading={uploading}
        onUpload={uploadCardImage}
      />
      {error ? <p className="form-error">{error}</p> : null}
    </section>
  );
}

function AssetCardGroup({
  group,
  cards,
  images,
  readonly,
  busy,
  uploading,
  onUpload,
}: {
  group: string;
  cards: AssetImageCard[];
  images: ImageState;
  readonly: boolean;
  busy: boolean;
  uploading: UploadState;
  onUpload: (card: AssetImageCard, event: ChangeEvent<HTMLInputElement>) => void;
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
      <header>
        <h4>{groupLabels[group] ?? "其他"}</h4>
        <span>{cards.length} 个资产</span>
      </header>
      <div className="asset-image-card-grid">
        {cards.map((card) => {
          const imageUrl = images[card.assetKey] ?? "";
          return (
            <article className={imageUrl ? "asset-image-card ready" : "asset-image-card missing"} key={card.assetKey}>
              <div className="asset-image-preview">
                {imageUrl ? <img src={imageUrl} alt={`${card.title} 图像`} /> : <span>未上传</span>}
              </div>
              <div className="asset-image-card-body">
                <div className="asset-image-card-title">
                  <strong>{card.title}</strong>
                  <span>{imageUrl ? "已上传" : "未上传"}</span>
                </div>
                <dl className="asset-image-fields">
                  {card.fields.map((field) => (
                    <div key={`${card.assetKey}-${field.label}`}>
                      <dt>{field.label}</dt>
                      <dd>{field.value}</dd>
                    </div>
                  ))}
                </dl>
                {card.prompt ? (
                  <div className="asset-image-prompt">
                    <span>生成提示词</span>
                    <p>{card.prompt}</p>
                  </div>
                ) : null}
                {card.referenceImageUrl ? (
                  <a className="asset-reference-link" href={card.referenceImageUrl} target="_blank" rel="noreferrer">
                    查看参考图
                  </a>
                ) : null}
                {!readonly ? (
                  <div className="asset-image-upload-row">
                    <label className="secondary-button asset-upload-button">
                      <input accept="image/*" disabled={busy || Boolean(uploading[card.assetKey])} type="file" onChange={(event) => onUpload(card, event)} />
                      {uploading[card.assetKey] ?? "上传图像"}
                    </label>
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

function buildAssetCards(source: Record<string, unknown> | null): AssetImageCard[] {
  if (!source) return [];
  const approvedAssets = recordValue(source.approved_assets);
  const characters = arrayOfRecords(approvedAssets?.characters ?? source.characters);
  const enriched = mapByName(arrayOfRecords(source.enriched_characters));
  const variants = mapByName(arrayOfRecords(source.variant_results));
  const accessories = mapByName(arrayOfRecords(source.accessory_results));
  const prompts = mapByName(arrayOfRecords(source.prompt_results));
  const cards = characters.map((character) => {
    const name = textValue(character.full_name) || textValue(character.name) || "未命名角色";
    const enrichedItem = enriched.get(name);
    const variant = variants.get(name);
    const accessory = accessories.get(name);
    const prompt = prompts.get(name);
    return {
      assetType: "character",
      assetKey: name,
      title: name,
      fields: compactFields([
        ["别名", joinValue(character.aliases)],
        ["摘要", textValue(character.summary)],
        ["当前状态", textValue(character.character_status)],
        ["匹配状态", matchedLabel(enrichedItem)],
        ["匹配资产", textValue(enrichedItem?.matched_asset_name) || textValue(enrichedItem?.matched_asset_id)],
        ["变体", textValue(variant?.matched_variant) || textValue(variant?.new_variant_name)],
        ["配件", joinValue(accessory?.new_accessories) || joinValue(character.accessories)],
        ["配件检查", textValue(accessory?.reason)],
      ]),
      prompt: textValue(prompt?.prompt),
      referenceImageUrl: textValue(prompt?.reference_image_url),
    };
  });

  return [
    ...cards,
    ...genericCards(approvedAssets?.assets ?? source.scenes, "scene", prompts),
    ...genericCards(approvedAssets?.props ?? source.props ?? source.items, "prop", prompts),
  ];
}

function genericCards(value: unknown, assetType: string, prompts: Map<string, Record<string, unknown>>): AssetImageCard[] {
  return arrayOfRecords(value).map((item, index) => {
    const title = textValue(item.name) || textValue(item.full_name) || `${groupLabels[assetType] ?? "资产"} ${index + 1}`;
    const prompt = prompts.get(title);
    return {
      assetType,
      assetKey: title,
      title,
      fields: Object.entries(item)
        .filter(([key]) => !["prompt", "reference_image_url"].includes(key))
        .map(([key, itemValue]) => ({ label: fieldLabel(key), value: displayValue(itemValue) }))
        .filter((field) => field.value),
      prompt: textValue(prompt?.prompt) || textValue(item.prompt),
      referenceImageUrl: textValue(prompt?.reference_image_url) || textValue(item.reference_image_url) || textValue(item.matched_asset_image_url),
    };
  });
}

function readonlyImages(value: unknown): ImageState {
  const images: ImageState = {};
  for (const item of arrayOfRecords(recordValue(value)?.asset_images)) {
    const key = textValue(item.asset_key) || textValue(item.full_name) || textValue(item.name);
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

function compactFields(items: Array<[string, string | undefined]>): Array<{ label: string; value: string }> {
  return items
    .filter(([, value]) => Boolean(value))
    .map(([label, value]) => ({ label, value: value ?? "" }));
}

function matchedLabel(item: Record<string, unknown> | undefined): string {
  if (!item) return "未匹配";
  return item.matched === true ? "已匹配" : "新资产";
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

function fieldLabel(key: string): string {
  const labels: Record<string, string> = {
    full_name: "名称",
    name: "名称",
    summary: "摘要",
    status: "状态",
    description: "描述",
  };
  return labels[key] ?? key;
}

function uploadScope(projectId: string | undefined): Exclude<AssetScope, "combined"> {
  return projectId && projectId !== "global" ? "project" : "global";
}
