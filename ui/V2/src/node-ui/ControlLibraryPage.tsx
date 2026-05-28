import { useEffect, useMemo, useState } from "react";

import { listNodeControls } from "../api/ui";
import type { NodeUiControlConfig, TaskNodeExecution, UiControlDescriptor, WorkflowNodeSpec } from "../api/types";
import { imageChoicePreviewNode } from "./fixtures/imageChoiceThree";
import { getNodeUiControl } from "./registry";

type UiControlVariantDescriptor = UiControlDescriptor["variants"][number];
type JsonRecord = Record<string, unknown>;

const imageChoiceConfig = {
  control_id: "ui.choice.image_three.v1",
  mode: "interactive",
  bindings: {
    items_path: "$node.input.candidates",
    image_url_path: "image_url",
    value_path: "id",
  },
};

const imageViewerConfig = {
  control_id: "ui.display.image_viewer.v1",
  variant: "grid_modal",
  mode: "readonly",
  bindings: {
    items_path: "$node.output.results",
    image_url_path: "url",
    label_path: "text",
  },
};

const imageViewerPreviewNode: TaskNodeExecution = {
  node_execution_id: "preview-image-viewer",
  node_id: "preview_image_viewer",
  node_ref: "ai.runninghub_text_to_image.v1",
  status: "succeeded",
  output_snapshot: {
    results: [
      {
        id: "sample-1",
        url: "https://images.unsplash.com/photo-1541701494587-cb58502866ab?w=800&auto=format&fit=crop",
        text: "示例图片",
      },
    ],
  },
};

interface ControlPreviewFixture {
  config: NodeUiControlConfig;
  node: TaskNodeExecution;
  nodeSpec?: WorkflowNodeSpec;
  slot?: "input" | "output" | "interaction" | "detail";
  value?: unknown;
  projectId?: string;
  imageAltPrefix?: string;
}

const sampleImageUrls = [
  "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=480&q=80",
  "https://images.unsplash.com/photo-1493246507139-91e8fad9978e?auto=format&fit=crop&w=480&q=80",
  "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=480&q=80",
];

const schemaFormPreviewSchema = {
  type: "object",
  required: ["prompt", "resolution"],
  properties: {
    prompt: {
      type: "string",
      title: "提示词",
      description: "描述要生成的画面。",
    },
    resolution: {
      type: "string",
      title: "清晰度",
      enum: ["1k", "2k", "4k"],
    },
    image_urls: {
      type: "array",
      title: "参考图",
      items: { type: "string" },
    },
  },
};

const fallbackSchemaPreviewSchema = {
  type: "object",
  required: ["fallback_prompt"],
  properties: {
    fallback_prompt: {
      type: "string",
      title: "Fallback 提示词",
    },
  },
};

const controlPreviewFixtures: Record<string, ControlPreviewFixture[]> = {
  "ui.display.value.v1": [
    {
      config: { control_id: "ui.display.value.v1", variant: "default", mode: "readonly" },
      node: {
        node_execution_id: "preview-value-display",
        node_id: "preview_value_display",
        node_ref: "tools.storyboard_summary.v1",
        status: "succeeded",
        output_snapshot: {
          "镜头数量": 3,
          "创作主题": "雨夜城市电影感",
          "说明": "节点输出会整理为字段和值，而不是展示原始 JSON。",
        },
      },
    },
  ],
  "ui.display.image_candidates.v1": [
    {
      config: {
        control_id: "ui.display.image_candidates.v1",
        variant: "grid",
        mode: "readonly",
        bindings: {
          items_path: "$node.output.candidates",
          image_url_path: "image_url",
          value_path: "id",
        },
      },
      node: {
        node_execution_id: "preview-image-candidates",
        node_id: "preview_image_candidates",
        node_ref: "ai.runninghub_text_to_image.v1",
        status: "succeeded",
        output_snapshot: {
          candidates: sampleImageUrls.map((imageUrl, index) => ({
            id: `candidate-output-${index + 1}`,
            label: `候选输出 ${String.fromCharCode(65 + index)}`,
            image_url: imageUrl,
          })),
        },
      },
    },
  ],
  "ui.display.image_viewer.v1": [
    {
      config: imageViewerConfig,
      node: imageViewerPreviewNode,
    },
  ],
  "ui.choice.image_three.v1": (["equal_grid", "hero_list", "hover_focus"] as const).map((variant) => ({
    config: { ...imageChoiceConfig, variant },
    node: imageChoicePreviewNode(),
  })),
  "ui.interaction.approval.v1": [
    {
      config: { control_id: "ui.interaction.approval.v1", variant: "default", mode: "interactive" },
      node: {
        node_execution_id: "preview-approval",
        node_id: "preview_approval",
        node_ref: "system.user_approval.v1",
        status: "waiting",
        metadata: { title: "确认生成结果" },
        input_snapshot: {
          question: "确认当前结果是否可以继续进入下一步。",
        },
      },
    },
  ],
  "ui.input.schema_form.v1": [
    {
      config: {
        control_id: "ui.input.schema_form.v1",
        variant: "default",
        mode: "input",
        options: {
          fields: {
            image_urls: {
              control_id: "ui.input.asset_image_picker.v1",
              variant: "thumbnails",
              mode: "input",
              selection_mode: "multiple",
            },
          },
        },
      },
      node: {
        node_execution_id: "preview-schema-form",
        node_id: "preview_schema_form",
        node_ref: "system.user_input.v1",
        status: "waiting",
        metadata: {
          title: "填写图片生成参数",
          input_schema: schemaFormPreviewSchema,
        },
      },
      nodeSpec: {
        id: "preview_schema_form",
        ref: "system.user_input.v1",
        outputs: schemaFormPreviewSchema,
      },
      projectId: "global",
      slot: "interaction",
      value: {
        prompt: "",
        resolution: "",
        image_urls: [],
      },
    },
  ],
  "ui.input.asset_image_picker.v1": [
    {
      config: {
        control_id: "ui.input.schema_form.v1",
        variant: "default",
        mode: "readonly",
        options: {
          fields: {
            image_urls: {
              control_id: "ui.input.asset_image_picker.v1",
              variant: "thumbnails",
              mode: "readonly",
              selection_mode: "multiple",
            },
          },
        },
      },
      node: {
        node_execution_id: "preview-asset-image-picker",
        node_id: "preview_asset_image_picker",
        node_ref: "system.user_input.v1",
        status: "succeeded",
        metadata: {
          title: "资产图片字段",
          input_schema: {
            type: "object",
            properties: {
              image_urls: {
                type: "array",
                title: "参考图",
                items: { type: "string" },
              },
            },
          },
        },
        output_snapshot: {
          image_urls: [sampleImageUrls[0], sampleImageUrls[1]],
        },
      },
      value: {
        image_urls: [sampleImageUrls[0], sampleImageUrls[1]],
      },
    },
  ],
  "ui.fallback.schema_form.v1": [
    {
      config: { control_id: "ui.fallback.schema_form.v1", variant: "default", mode: "input" },
      node: {
        node_execution_id: "preview-fallback-schema",
        node_id: "preview_fallback_schema",
        node_ref: "system.user_input.v1",
        status: "waiting",
        metadata: {
          title: "Fallback 表单",
          input_schema: fallbackSchemaPreviewSchema,
        },
      },
      nodeSpec: {
        id: "preview_fallback_schema",
        ref: "system.user_input.v1",
        outputs: fallbackSchemaPreviewSchema,
      },
      slot: "interaction",
    },
  ],
};

export function ControlLibraryPage() {
  const [controls, setControls] = useState<UiControlDescriptor[]>([]);
  const [selectedKind, setSelectedKind] = useState("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    listNodeControls()
      .then((items) => {
        if (active) setControls(items);
      })
      .catch(() => {
        if (active) setError("控件库接口不可用，请检查后端服务。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const kinds = useMemo(() => ["all", ...Array.from(new Set(controls.map((control) => control.kind)))], [controls]);
  const visibleControls = selectedKind === "all" ? controls : controls.filter((control) => control.kind === selectedKind);

  return (
    <main className="control-library-page">
      <section className="panel control-library-header">
        <div>
          <p className="eyebrow">Node UI Controls</p>
          <h1>控件库</h1>
          <p>查看后端已注册的节点 UI 控件、变体、标签和绑定要求。</p>
        </div>
        <div className="segmented-control compact" role="tablist" aria-label="控件类型">
          {kinds.map((kind) => (
            <button className={selectedKind === kind ? "active" : ""} key={kind} type="button" onClick={() => setSelectedKind(kind)}>
              {kind === "all" ? "全部" : kind}
            </button>
          ))}
        </div>
      </section>

      {loading ? <section className="panel">正在加载控件库...</section> : null}
      {error ? <section className="panel form-error">{error}</section> : null}

      <section className="control-grid">
        {visibleControls.map((control) => (
          <ControlCard control={control} key={control.control_id} />
        ))}
      </section>
    </main>
  );
}

function ControlCard({ control }: { control: UiControlDescriptor }) {
  return (
    <article className="panel control-card">
      <header className="control-card-header">
        <div>
          <p className="eyebrow">{control.kind}</p>
          <h2>{control.name}</h2>
        </div>
        <code>{control.control_id}</code>
      </header>
      {control.description ? <p>{control.description}</p> : null}
      <div className="tag-row">
        {control.tags.map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
      </div>
      <div className="variant-list">
        {control.variants.map((variant) => (
          <section key={variant.name}>
            <h3>{variant.label}</h3>
            <p>
              <code>{variant.name}</code> · {variant.modes.join(" / ")}
            </p>
            <ControlVariantRequirements variant={variant} />
          </section>
        ))}
      </div>
      <ControlPreview controlId={control.control_id} />
    </article>
  );
}

function ControlPreview({ controlId }: { controlId: string }) {
  const fixtures = controlPreviewFixtures[controlId];
  if (!fixtures?.length) {
    return (
      <section className="control-preview-section">
        <h3>节点效果预览</h3>
        <p className="muted">该控件暂无 V2 预览 fixture。</p>
      </section>
    );
  }
  return (
    <section className="control-preview-section">
      <h3>节点效果预览</h3>
      <div className="control-preview-stack">
        {fixtures.map((fixture, index) => {
          const Control = getNodeUiControl(fixture.config.control_id);
          return (
            <Control
              config={fixture.config}
              imageAltPrefix={fixture.imageAltPrefix}
              key={`${fixture.config.control_id}-${fixture.config.variant ?? "default"}-${index}`}
              node={fixture.node}
              nodeSpec={fixture.nodeSpec}
              onSubmit={fixture.config.mode === "readonly" ? undefined : noopPreviewSubmit}
              preview
              projectId={fixture.projectId}
              slot={fixture.slot}
              value={fixture.value}
            />
          );
        })}
      </div>
    </section>
  );
}

function noopPreviewSubmit() {
  return undefined;
}

function ControlVariantRequirements({ variant }: { variant: UiControlVariantDescriptor }) {
  const bindings = variant.required_bindings.map(normalizeBindingRequirement).filter((binding) => binding.name);
  const payloadFields = getSubmitSchemaFields(variant.submit_schema);

  if (bindings.length === 0 && payloadFields.length === 0) return null;

  return (
    <div className="control-requirements">
      {bindings.length > 0 ? (
        <div>
          <h4>绑定要求</h4>
          <ul>
            {bindings.map((binding) => (
              <li key={binding.name}>
                <code>{binding.name}</code>
                <span>{binding.required ? "必填" : "可选"}</span>
                {binding.bindingKind ? <span>{binding.bindingKind}</span> : null}
                {binding.sources.length > 0 ? <span>来源 {binding.sources.join(" / ")}</span> : null}
                {binding.constraints.map((constraint) => (
                  <span key={constraint}>{constraint}</span>
                ))}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {payloadFields.length > 0 ? (
        <div>
          <h4>Payload 要求</h4>
          <ul>
            {payloadFields.map((field) => (
              <li key={field.name}>
                <code>{field.name}</code>
                <span>{field.required ? "必填" : "可选"}</span>
                {field.type ? <span>{field.type}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function normalizeBindingRequirement(requirement: unknown) {
  const record = asRecord(requirement);
  const constraints = asRecord(record.schema_constraints);
  return {
    name: typeof record.name === "string" ? record.name : "",
    required: typeof record.required === "boolean" ? record.required : true,
    bindingKind: typeof record.binding_kind === "string" ? record.binding_kind : "",
    sources: toStringList(record.accepted_sources),
    constraints: Object.entries(constraints).map(([key, value]) => `${key}: ${formatConstraintValue(value)}`),
  };
}

function getSubmitSchemaFields(schema: Record<string, unknown> | undefined) {
  const schemaRecord = asRecord(schema);
  const required = new Set(toStringList(schemaRecord.required));
  const properties = asRecord(schemaRecord.properties);
  return Object.entries(properties).map(([name, property]) => ({
    name,
    required: required.has(name),
    type: typeof asRecord(property).type === "string" ? String(asRecord(property).type) : "",
  }));
}

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function toStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function formatConstraintValue(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(formatConstraintValue).join(" / ");
  return "object";
}
