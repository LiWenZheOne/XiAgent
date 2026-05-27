import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssetLibraryPage } from "../assets/AssetLibraryPage";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AssetLibraryPage", () => {
  it("shows a real empty state instead of sample assets when the backend has no assets", async () => {
    vi.stubGlobal("fetch", createAssetFetchMock({ assets: [] }));

    render(<AssetLibraryPage projectName="内容生成平台" />);

    expect(await screen.findByText("真实数据：0 个资产")).toBeInTheDocument();
    expect(screen.getByText("当前项目还没有资产")).toBeInTheDocument();
    expect(screen.queryByText("产品说明片段")).not.toBeInTheDocument();
    expect(screen.queryByText("素材封面组")).not.toBeInTheDocument();
  });

  it("loads real assets, selects a real detail, searches through the API, and downloads content", async () => {
    const user = userEvent.setup();
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    const fetchMock = createAssetFetchMock({
      requests,
      assets: [imageAsset(), textAsset()],
      content: "downloaded bytes",
    });
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:asset-download"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(() => undefined),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    render(<AssetLibraryPage projectName="内容生成平台" />);

    expect(await screen.findByRole("cell", { name: "真实七牛图片.png" })).toBeInTheDocument();
    expect(screen.getByText("真实数据：2 个资产")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "标签 角色" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "分类 视觉资产" })).toBeInTheDocument();
    expect(screen.queryByText("引用 8")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "浏览 文案片段.txt" }));
    const detail = screen.getByRole("complementary", { name: "资产详情" });
    expect(within(detail).getByRole("heading", { name: "文案片段.txt" })).toBeInTheDocument();
    expect(within(detail).getByText(/text\/plain/)).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "搜索资产" }), "七牛");
    await waitFor(() => {
      const searchRequest = requests.find(
        (request) =>
          request.url.startsWith("/api/assets/search") &&
          request.url.includes("keyword=%E4%B8%83%E7%89%9B"),
      );
      expect(searchRequest?.url).toContain("project_id=backend_project_1");
      expect(new Headers(searchRequest?.init?.headers).get("Authorization")).toBe("Bearer asset-token");
    });

    await user.click(screen.getByRole("button", { name: "下载 真实七牛图片.png" }));
    await waitFor(() => {
      expect(requests.some((request) => request.url === "/api/assets/asset_real_1/content?project_id=backend_project_1")).toBe(true);
    });
    expect(await screen.findByText("已下载：真实七牛图片.png")).toBeInTheDocument();
  });
});

function createAssetFetchMock({
  assets,
  content = "",
  requests = [],
}: {
  assets: unknown[];
  content?: string;
  requests?: Array<{ url: string; init?: RequestInit }>;
}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString();
    requests.push({ url, init });

    if (url === "/api/auth/login") {
      return jsonResponse({ access_token: "asset-token", token_type: "bearer" });
    }
    if (url === "/api/projects") {
      return jsonResponse({
        items: [{ project_id: "backend_project_1", name: "内容生成平台" }],
      });
    }
    if (url.startsWith("/api/assets/search")) {
      return jsonResponse({ items: assets, total: assets.length });
    }
    if (url.startsWith("/api/assets/tags")) {
      return jsonResponse({
        items: [{ tag_id: "tag_1", name: "角色", scope: "project", asset_count: 1 }],
      });
    }
    if (url.startsWith("/api/assets/collections")) {
      return jsonResponse({
        items: [{ collection_id: "collection_1", name: "视觉资产", scope: "project", asset_count: 1 }],
      });
    }
    if (url.startsWith("/api/assets/asset_real_1/content")) {
      return new Response(content, {
        status: 200,
        headers: { "Content-Type": "image/png" },
      });
    }

    return jsonResponse({ detail: "not found" }, 404);
  });
}

function imageAsset() {
  return {
    asset_id: "asset_real_1",
    asset_type: "file",
    name: "真实七牛图片.png",
    scope: "project",
    project_id: "backend_project_1",
    mime_type: "image/png",
    size_bytes: 12,
    storage_uri: "assets/real.png",
    text_content: null,
    metadata: {
      public_url: "http://csimg.beixinggu.cn/xiagent/assets/real.png",
      tags: ["角色"],
      object_storage: {
        provider: "qiniu",
        bucket: "lwzimg01",
        key: "xiagent/assets/real.png",
      },
    },
    created_by: "user_1",
    created_at: "2026-05-27T00:00:00Z",
    updated_at: "2026-05-27T00:00:00Z",
    deleted_at: null,
  };
}

function textAsset() {
  return {
    asset_id: "asset_text_1",
    asset_type: "text",
    name: "文案片段.txt",
    scope: "project",
    project_id: "backend_project_1",
    mime_type: "text/plain",
    size_bytes: 32,
    storage_uri: null,
    text_content: "真实文案内容",
    metadata: { kind: "brief" },
    created_by: "user_1",
    created_at: "2026-05-27T01:00:00Z",
    updated_at: "2026-05-27T01:00:00Z",
    deleted_at: null,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
