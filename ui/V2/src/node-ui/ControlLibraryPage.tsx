import { useEffect, useMemo, useState } from "react";

import { listNodeControls } from "../api/ui";
import type { UiControlDescriptor } from "../api/types";
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
      {control.control_id === "ui.choice.image_three.v1" ? <ImageChoicePreview /> : null}
    </article>
  );
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

function ImageChoicePreview() {
  const Control = getNodeUiControl("ui.choice.image_three.v1");
  const node = imageChoicePreviewNode();
  return (
    <div className="control-preview-stack">
      {(["equal_grid", "hero_list", "hover_focus"] as const).map((variant) => (
        <Control
          config={{ ...imageChoiceConfig, variant }}
          key={variant}
          node={node}
          preview
        />
      ))}
    </div>
  );
}
