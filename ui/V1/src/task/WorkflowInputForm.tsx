import { FormEvent, useMemo, useState } from "react";

import type { AssetRecord, JsonSchema } from "../api/types";
import { AssetPicker } from "../assets/AssetPicker";

interface WorkflowInputFormProps {
  schema: JsonSchema;
  assets: AssetRecord[];
  onSubmit(input: Record<string, unknown>): void;
}

function schemaProperties(schema: JsonSchema): Record<string, JsonSchema> {
  return schema.properties ?? {};
}

export function WorkflowInputForm({ schema, assets, onSubmit }: WorkflowInputFormProps) {
  const properties = useMemo(() => schemaProperties(schema), [schema]);
  const [textValues, setTextValues] = useState<Record<string, string>>({});
  const [imageUrls, setImageUrls] = useState<string[]>([]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input: Record<string, unknown> = {};
    for (const [key, property] of Object.entries(properties)) {
      if (key === "image_urls" && property.type === "array") {
        input[key] = imageUrls;
      } else {
        input[key] = textValues[key] ?? "";
      }
    }
    onSubmit(input);
  }

  return (
    <form className="workflow-input-form" onSubmit={handleSubmit}>
      {Object.entries(properties).map(([key, property]) => {
        if (key === "image_urls" && property.type === "array") {
          return (
            <section className="workflow-field" key={key}>
              <div>
                <label>{key}</label>
                <p>从资产库选择一张已有公网 URL 的图片。</p>
              </div>
              <AssetPicker assets={assets} selectedUrls={imageUrls} onChange={setImageUrls} />
            </section>
          );
        }

        return (
          <label className="workflow-field" key={key}>
            <span>{key}</span>
            <input
              aria-label={key}
              value={textValues[key] ?? ""}
              onChange={(event) =>
                setTextValues((current) => ({ ...current, [key]: event.target.value }))
              }
            />
          </label>
        );
      })}
      <div className="form-actions">
        <button className="primary-button" type="submit">
          创建并运行
        </button>
      </div>
    </form>
  );
}
