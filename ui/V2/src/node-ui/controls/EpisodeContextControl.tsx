import type { NodeUiControlProps } from "../types";

interface CatalogCounts {
  character: number;
  scene: number;
  prop: number;
  total: number;
}

export function EpisodeContextControl({ node, value }: NodeUiControlProps) {
  const source = recordValue(value) ?? recordValue(node.output_snapshot) ?? recordValue(node.input_snapshot) ?? {};
  const catalog = episodeCatalog(source);
  const counts = countCatalog(catalog);
  const characters = arrayRecords(catalog.characters);
  const scenes = [...arrayRecords(catalog.assets), ...arrayRecords(catalog.scenes), ...arrayRecords(catalog.locations)];
  const props = arrayRecords(catalog.props);
  const script = textValue(source.source_script);

  return (
    <section className="node-ui-readonly episode-context-control">
      <header className="episode-context-header">
        <div>
          <p className="eyebrow">集信息</p>
          <h3>{textValue(source.episode_name) || "未命名集"}</h3>
          {textValue(source.episode_summary) ? <p>{textValue(source.episode_summary)}</p> : null}
        </div>
        <div className="episode-context-metrics" aria-label="资产目录统计">
          <SummaryMetric label="总资产" value={counts.total} />
          <SummaryMetric label="角色" value={counts.character} />
          <SummaryMetric label="地点" value={counts.scene} />
          <SummaryMetric label="道具" value={counts.prop} />
        </div>
      </header>

      <div className="episode-context-grid">
        <section className="episode-context-panel">
          <h4>原剧本</h4>
          <p className="episode-script-preview">{script || "暂无原剧本内容。"}</p>
        </section>

        <section className="episode-context-panel">
          <h4>完整资产目录</h4>
          <div className="episode-catalog-columns">
            <CatalogList title="角色" items={characters} />
            <CatalogList title="地点" items={scenes} />
            <CatalogList title="道具" items={props} />
          </div>
        </section>
      </div>
    </section>
  );
}

function SummaryMetric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CatalogList({ title, items }: { title: string; items: Record<string, unknown>[] }) {
  return (
    <div className="episode-catalog-list">
      <strong>{title}</strong>
      {items.length ? (
        <ul>
          {items.slice(0, 12).map((item, index) => (
            <li key={`${title}-${index}`}>{catalogItemName(item, index)}</li>
          ))}
        </ul>
      ) : (
        <span className="muted">暂无</span>
      )}
      {items.length > 12 ? <span className="muted">另有 {items.length - 12} 项</span> : null}
    </div>
  );
}

function episodeCatalog(source: Record<string, unknown>): Record<string, unknown> {
  const assetCatalog = recordValue(source.asset_catalog);
  return recordValue(assetCatalog?.approved_assets) ?? assetCatalog ?? {};
}

function countCatalog(catalog: Record<string, unknown>): CatalogCounts {
  const character = arrayRecords(catalog.characters).length;
  const scene = arrayRecords(catalog.assets).length + arrayRecords(catalog.scenes).length + arrayRecords(catalog.locations).length;
  const prop = arrayRecords(catalog.props).length;
  return { character, scene, prop, total: character + scene + prop };
}

function catalogItemName(item: Record<string, unknown>, index: number): string {
  return textValue(item.asset_name) || textValue(item.name) || `资产 ${index + 1}`;
}

function arrayRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null) : [];
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : null;
}

function textValue(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}
