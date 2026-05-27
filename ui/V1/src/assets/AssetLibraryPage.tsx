import { useEffect, useMemo, useState } from "react";

import {
  deleteAsset,
  downloadAssetContent,
  listAssetCollections,
  listAssetTags,
  readAssetTextContent,
  searchAssets,
} from "../api/assets";
import { ensureAccessToken } from "../api/auth";
import { ApiError } from "../api/client";
import { listProjects } from "../api/projects";
import type { AssetCollection, AssetRecord, AssetScope, AssetTag } from "../api/types";
import { AssetTextDialog } from "./AssetTextDialog";
import { AssetUploadDialog } from "./AssetUploadDialog";

interface AssetLibraryPageProps {
  projectId?: string;
  projectName?: string;
}

type AssetTypeFilter = "all" | "file" | "text" | "image";

interface AssetFilters {
  scope: AssetScope;
  keyword: string;
  assetType: AssetTypeFilter;
  collectionId?: string;
  tagIds: string[];
}

async function resolveBackendProjectId(projectId?: string, projectName?: string): Promise<string | undefined> {
  const projects = await listProjects();
  const byId = projects.find((project) => project.project_id === projectId);
  if (byId) return byId.project_id;

  const cleanName = projectName?.trim();
  if (!cleanName) return projectId;

  return projects.find((project) => project.name === cleanName)?.project_id;
}

function assetKind(asset: AssetRecord): string {
  if (asset.asset_type === "text") return "文字";
  if ((asset.mime_type ?? "").startsWith("image/")) return "图片";
  if ((asset.mime_type ?? "").startsWith("video/")) return "视频";
  if ((asset.mime_type ?? "").includes("json")) return "JSON";
  return asset.asset_type === "file" ? "文件" : asset.asset_type || "未知";
}

function assetStatus(asset: AssetRecord): { label: string; className: string } {
  if (asset.deleted_at) return { label: "已删除", className: "status danger" };
  if (asset.metadata.public_url) return { label: "已发布", className: "status success" };
  return { label: "未发布", className: "status warning" };
}

function assetTags(asset: AssetRecord): string[] {
  return Array.isArray(asset.metadata.tags) ? asset.metadata.tags.filter(Boolean) : [];
}

function assetProjectId(asset: AssetRecord, fallbackProjectId?: string): string | undefined {
  return asset.scope === "project" ? asset.project_id ?? fallbackProjectId : undefined;
}

function formatBytes(size: number | null): string {
  if (size === null || Number.isNaN(size)) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}

function buildDownloadName(asset: AssetRecord): string {
  if (asset.name.includes(".")) return asset.name;
  if (asset.asset_type === "text") return `${asset.name}.txt`;
  return asset.name;
}

export function AssetLibraryPage({ projectId, projectName }: AssetLibraryPageProps) {
  const [backendProjectId, setBackendProjectId] = useState<string | undefined>(projectId);
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [collections, setCollections] = useState<AssetCollection[]>([]);
  const [tags, setTags] = useState<AssetTag[]>([]);
  const [filters, setFilters] = useState<AssetFilters>({
    scope: projectId || projectName ? "combined" : "global",
    keyword: "",
    assetType: "all",
    tagIds: [],
  });
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [statusText, setStatusText] = useState("正在读取真实资产数据");
  const [loading, setLoading] = useState(true);
  const [downloadMessage, setDownloadMessage] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [textDialogOpen, setTextDialogOpen] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);

  useEffect(() => {
    let active = true;
    async function loadProject() {
      try {
        await ensureAccessToken();
        const resolvedProjectId = await resolveBackendProjectId(projectId, projectName);
        if (!active) return;
        setBackendProjectId(resolvedProjectId);
        if (!resolvedProjectId && filters.scope !== "global") {
          setFilters((current) => ({ ...current, scope: "global" }));
        }
      } catch (error) {
        if (!active) return;
        setStatusText(error instanceof ApiError && error.status === 401 ? "资产接口需要登录" : "项目接口不可用");
      }
    }
    void loadProject();
    return () => {
      active = false;
    };
  }, [filters.scope, projectId, projectName]);

  useEffect(() => {
    let active = true;
    async function loadAssets() {
      setLoading(true);
      setDownloadMessage("");
      try {
        await ensureAccessToken();
        const projectScoped = filters.scope !== "global";
        const searchFilters = {
          scope: filters.scope,
          project_id: projectScoped ? backendProjectId : undefined,
          keyword: filters.keyword.trim() || undefined,
          asset_type: filters.assetType === "file" || filters.assetType === "text" ? filters.assetType : undefined,
          mime_type: filters.assetType === "image" ? "image/*" : undefined,
          collection_id: filters.collectionId,
          tag_ids: filters.tagIds,
        };
        const [assetItems, collectionItems, tagItems] = await Promise.all([
          searchAssets(searchFilters),
          listAssetCollections(filters.scope, projectScoped ? backendProjectId : undefined),
          listAssetTags(filters.scope, projectScoped ? backendProjectId : undefined),
        ]);
        if (!active) return;
        setAssets(assetItems);
        setCollections(collectionItems);
        setTags(tagItems);
        setSelectedAssetId((current) => {
          if (assetItems.some((asset) => asset.asset_id === current)) return current;
          return assetItems[0]?.asset_id ?? null;
        });
        setStatusText(`真实数据：${assetItems.length} 个资产`);
      } catch (error) {
        if (!active) return;
        setAssets([]);
        setCollections([]);
        setTags([]);
        setSelectedAssetId(null);
        if (error instanceof ApiError && error.status === 401) {
          setStatusText("资产接口需要登录");
        } else {
          setStatusText("资产接口不可用");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    const needsProject = filters.scope !== "global";
    if (needsProject && !backendProjectId) {
      setAssets([]);
      setCollections([]);
      setTags([]);
      setSelectedAssetId(null);
      setLoading(false);
      setStatusText("当前前端项目尚未绑定后端项目");
      return;
    }

    void loadAssets();
    return () => {
      active = false;
    };
  }, [backendProjectId, filters, refreshVersion]);

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.asset_id === selectedAssetId) ?? null,
    [assets, selectedAssetId],
  );

  useEffect(() => {
    let active = true;
    setPreviewText("");
    async function loadTextPreview(asset: AssetRecord) {
      if (asset.asset_type !== "text") return;
      if (asset.text_content) {
        setPreviewText(asset.text_content);
        return;
      }
      try {
        const text = await readAssetTextContent(asset.asset_id, assetProjectId(asset, backendProjectId));
        if (active) setPreviewText(text);
      } catch {
        if (active) setPreviewText("文字内容读取失败");
      }
    }
    if (selectedAsset) void loadTextPreview(selectedAsset);
    return () => {
      active = false;
    };
  }, [backendProjectId, selectedAsset]);

  const typeCounts = useMemo(
    () => ({
      all: assets.length,
      file: assets.filter((asset) => asset.asset_type === "file").length,
      text: assets.filter((asset) => asset.asset_type === "text").length,
      image: assets.filter((asset) => (asset.mime_type ?? "").startsWith("image/")).length,
    }),
    [assets],
  );

  async function handleDownload(asset: AssetRecord) {
    setDownloadMessage("");
    const blob = await downloadAssetContent(asset.asset_id, assetProjectId(asset, backendProjectId));
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = buildDownloadName(asset);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
    setDownloadMessage(`已下载：${asset.name}`);
  }

  async function handleDelete(asset: AssetRecord) {
    await deleteAsset(asset.asset_id);
    setRefreshVersion((current) => current + 1);
  }

  const emptyText = filters.keyword || filters.assetType !== "all" || filters.collectionId || filters.tagIds.length > 0
    ? "当前筛选条件下没有资产"
    : filters.scope === "global"
      ? "全局资产库还没有资产"
      : "当前项目还没有资产";

  return (
    <main className="page asset-governance-page">
      <section className="page-header">
        <div>
          <p className="eyebrow">asset_service / 真实资产数据</p>
          <h1>资产库</h1>
          <p>浏览、搜索、上传、创建文字资产，并通过 AssetService 下载原始内容。</p>
          <p className="current-project-text">{statusText}</p>
          {downloadMessage ? <p className="current-project-text">{downloadMessage}</p> : null}
        </div>
        <div className="header-actions">
          <button
            className={filters.scope === "combined" ? "secondary-button active-control" : "secondary-button"}
            disabled={!backendProjectId}
            type="button"
            onClick={() => setFilters((current) => ({ ...current, scope: "combined" }))}
          >
            当前项目 + 全局
          </button>
          <button
            className={filters.scope === "global" ? "secondary-button active-control" : "secondary-button"}
            type="button"
            onClick={() => setFilters((current) => ({ ...current, scope: "global", collectionId: undefined, tagIds: [] }))}
          >
            全局资产
          </button>
          <button className="primary-button" type="button" onClick={() => setUploadOpen(true)}>
            上传文件
          </button>
          <button className="secondary-button" type="button" onClick={() => setTextDialogOpen(true)}>
            新建文字资产
          </button>
        </div>
      </section>

      <div className="asset-layout">
        <nav className="filter-panel" aria-label="资产筛选">
          <h2>资产筛选</h2>
          <section className="filter-group">
            <h3>资产类型</h3>
            {[
              ["all", "全部资产", typeCounts.all],
              ["file", "文件资产", typeCounts.file],
              ["text", "文字资产", typeCounts.text],
              ["image", "图片", typeCounts.image],
            ].map(([type, label, count]) => (
              <button
                className={filters.assetType === type ? "filter-button active" : "filter-button"}
                key={type}
                type="button"
                onClick={() => setFilters((current) => ({ ...current, assetType: type as AssetTypeFilter }))}
              >
                <span>{label}</span>
                <span>{count}</span>
              </button>
            ))}
          </section>
          <section className="filter-group">
            <h3>分类目录</h3>
            <button
              className={!filters.collectionId ? "filter-button active" : "filter-button"}
              type="button"
              onClick={() => setFilters((current) => ({ ...current, collectionId: undefined }))}
            >
              <span>全部目录</span>
              <span>{collections.length}</span>
            </button>
            {collections.length === 0 ? <p className="empty-state muted">暂无分类目录</p> : null}
            {collections.map((collection) => (
              <button
                aria-label={`分类 ${collection.name}`}
                className={filters.collectionId === collection.collection_id ? "filter-button active" : "filter-button"}
                key={collection.collection_id}
                type="button"
                onClick={() => setFilters((current) => ({ ...current, collectionId: collection.collection_id }))}
              >
                <span>{collection.name}</span>
              </button>
            ))}
          </section>
          <section className="filter-group">
            <h3>标签</h3>
            <button
              className={filters.tagIds.length === 0 ? "filter-button active" : "filter-button"}
              type="button"
              onClick={() => setFilters((current) => ({ ...current, tagIds: [] }))}
            >
              <span>全部标签</span>
              <span>{tags.length}</span>
            </button>
            {tags.length === 0 ? <p className="empty-state muted">暂无标签</p> : null}
            {tags.map((tag) => {
              const selected = filters.tagIds.includes(tag.tag_id);
              return (
                <button
                  aria-label={`标签 ${tag.name}`}
                  className={selected ? "filter-button active" : "filter-button"}
                  key={tag.tag_id}
                  type="button"
                  onClick={() =>
                    setFilters((current) => ({
                      ...current,
                      tagIds: selected
                        ? current.tagIds.filter((tagId) => tagId !== tag.tag_id)
                        : [...current.tagIds, tag.tag_id],
                    }))
                  }
                >
                  <span>{tag.name}</span>
                </button>
              );
            })}
          </section>
        </nav>

        <section className="panel asset-table-panel">
          <div className="asset-tools">
            <label className="table-search">
              <span className="sr-only">搜索资产</span>
              <input
                aria-label="搜索资产"
                placeholder="搜索资产名、文字内容或元数据"
                type="search"
                value={filters.keyword}
                onChange={(event) => setFilters((current) => ({ ...current, keyword: event.target.value }))}
              />
            </label>
            <div className="chip-row">
              <span className="chip active">列表视图</span>
              <span className="chip">后端项目：{backendProjectId ?? "未绑定"}</span>
              <span className="chip">已载入 {assets.length} 项</span>
            </div>
          </div>

          {loading ? <p className="empty-state neutral">正在加载资产...</p> : null}
          {!loading && assets.length === 0 ? (
            <div className="empty-panel asset-empty-panel">
              <h2>{emptyText}</h2>
              <p>可以上传文件、创建文字资产，或切换全局/当前项目范围后重新查询。</p>
            </div>
          ) : null}

          {assets.length > 0 ? (
            <table className="data-table" aria-label="资产列表">
              <thead>
                <tr>
                  <th>资产名</th>
                  <th>类型</th>
                  <th>范围</th>
                  <th>大小</th>
                  <th>标签</th>
                  <th>更新时间</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => {
                  const status = assetStatus(asset);
                  return (
                    <tr className={asset.asset_id === selectedAssetId ? "selected-row" : ""} key={asset.asset_id}>
                      <td>{asset.name}</td>
                      <td>{assetKind(asset)}</td>
                      <td>{asset.scope === "global" ? "全局资产" : "当前项目"}</td>
                      <td>{formatBytes(asset.size_bytes)}</td>
                      <td>{assetTags(asset).join(" / ") || "未标记"}</td>
                      <td>{formatDate(asset.updated_at ?? asset.created_at)}</td>
                      <td><span className={status.className}>{status.label}</span></td>
                      <td>
                        <div className="asset-row-actions">
                          <button className="text-button" type="button" onClick={() => setSelectedAssetId(asset.asset_id)}>
                            浏览 {asset.name}
                          </button>
                          <button className="text-button" type="button" onClick={() => void handleDownload(asset)}>
                            下载 {asset.name}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : null}
        </section>

        <aside className="detail-panel" aria-label="资产详情">
          <h2>资产详情</h2>
          {selectedAsset ? (
            <>
              <AssetPreview asset={selectedAsset} previewText={previewText} />
              <h3>{selectedAsset.name}</h3>
              <p>
                {assetKind(selectedAsset)} · {selectedAsset.mime_type ?? "未知 MIME"} · {formatBytes(selectedAsset.size_bytes)}
              </p>
              <dl className="asset-meta-list">
                <div>
                  <dt>资产 ID</dt>
                  <dd>{selectedAsset.asset_id}</dd>
                </div>
                <div>
                  <dt>作用域</dt>
                  <dd>{selectedAsset.scope === "global" ? "全局资产" : selectedAsset.project_id ?? "当前项目"}</dd>
                </div>
                <div>
                  <dt>存储 URI</dt>
                  <dd>{selectedAsset.storage_uri ?? "文字资产无文件 URI"}</dd>
                </div>
                <div>
                  <dt>公开 URL</dt>
                  <dd>
                    {selectedAsset.metadata.public_url ? (
                      <a href={selectedAsset.metadata.public_url} target="_blank" rel="noreferrer">
                        打开 public_url
                      </a>
                    ) : (
                      "未发布"
                    )}
                  </dd>
                </div>
                <div>
                  <dt>对象存储</dt>
                  <dd>
                    {selectedAsset.metadata.object_storage
                      ? `${selectedAsset.metadata.object_storage.provider} / ${selectedAsset.metadata.object_storage.bucket ?? "-"}`
                      : "无"}
                  </dd>
                </div>
                <div>
                  <dt>创建 / 更新</dt>
                  <dd>{formatDate(selectedAsset.created_at)} / {formatDate(selectedAsset.updated_at)}</dd>
                </div>
              </dl>
              <div className="detail-actions">
                <button className="primary-button" type="button" onClick={() => void handleDownload(selectedAsset)}>
                  下载
                </button>
                <button className="secondary-button" type="button" onClick={() => void handleDelete(selectedAsset)}>
                  软删除
                </button>
              </div>
            </>
          ) : (
            <p className="empty-state neutral">选择一个资产后查看真实详情。</p>
          )}
        </aside>
      </div>

      <AssetUploadDialog
        open={uploadOpen}
        projectId={backendProjectId}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => setRefreshVersion((current) => current + 1)}
      />
      <AssetTextDialog
        open={textDialogOpen}
        projectId={backendProjectId}
        onClose={() => setTextDialogOpen(false)}
        onCreated={() => setRefreshVersion((current) => current + 1)}
      />
    </main>
  );
}

function AssetPreview({ asset, previewText }: { asset: AssetRecord; previewText: string }) {
  const publicUrl = asset.metadata.public_url;
  if ((asset.mime_type ?? "").startsWith("image/") && publicUrl) {
    return (
      <div className="asset-preview image-preview">
        <img src={publicUrl} alt={asset.name} />
      </div>
    );
  }
  if (asset.asset_type === "text") {
    return <pre className="asset-preview text-preview">{previewText || asset.text_content || "暂无文字预览"}</pre>;
  }
  return (
    <div className="asset-preview">
      <span>{asset.mime_type ?? asset.asset_type}</span>
    </div>
  );
}
