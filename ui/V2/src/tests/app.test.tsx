import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import type { AssetRecord } from "../api/types";

const workflowContract = {
  workflow: {
    id: "storyboard_generation",
    version: "1.0.0",
    name: "故事板生成",
    description: "根据主题生成候选图片并等待用户选择。",
    ui: {
      stages: [
        {
          id: "p1_input",
          name: "P1 用户输入",
          description: "收集创作主题和参考图。",
          nodes: ["collect_user_input"],
        },
        {
          id: "p2_generate",
          name: "P2 生成与选择",
          description: "准备提示词并等待用户选择图片。",
          nodes: ["prepare_prompt", "choose_image"],
        },
      ],
    },
    input_schema: {
      type: "object",
      required: ["topic"],
      properties: {
        topic: { type: "string", title: "创作主题" },
        image_urls: { type: "array", title: "参考图片", items: { type: "string" } },
      },
    },
  },
  nodes: [
    {
      id: "collect_user_input",
      ref: "system.user_input.v1",
      inputs: {
        topic: {
          from_user: true,
          schema: { type: "string", title: "创作主题" },
        },
        image_urls: {
          from_user: true,
          required: false,
          schema: { type: "array", title: "参考图片", items: { type: "string" } },
        },
      },
      outputs: {
        type: "object",
        required: ["topic"],
        properties: {
          topic: { type: "string", title: "创作主题" },
          image_urls: { type: "array", title: "参考图", items: { type: "string" } },
        },
      },
      ui: {
        controls: {
          interaction: {
            control_id: "ui.input.schema_form.v1",
            variant: "default",
            mode: "input",
          },
        },
      },
    },
    { id: "prepare_prompt", ref: "tools.storyboard_prompt.v1" },
    {
      id: "choose_image",
      ref: "system.user_choice.v1",
      outputs: {
        type: "object",
        required: ["selected_id", "selected_item"],
        properties: {
          selected_id: { type: "string" },
          selected_item: { type: "object" },
          selected_image_url: { type: "string" },
        },
      },
      ui: {
        controls: {
          interaction: {
            control_id: "ui.choice.image_three.v1",
            variant: "hover_focus",
            mode: "interactive",
            bindings: {
              items_path: "$node.input.candidates",
              image_url_path: "image_url",
              value_path: "id",
            },
          },
        },
      },
    },
  ],
  edges: [],
};

const uiControlsResponse = {
  items: [
    {
      control_id: "ui.choice.image_three.v1",
      version: "1.0.0",
      name: "Image Three Choice",
      kind: "interaction",
      tags: ["image", "choice", "select_one", "candidates_3"],
      variants: [
        {
          name: "equal_grid",
          label: "三图等宽",
          tags: [],
          modes: ["interactive"],
          required_bindings: [
            {
              name: "items_path",
              binding_kind: "schema_path",
              accepted_sources: ["node.input", "node.output"],
              schema_constraints: { type: "array", minItems: 1 },
            },
          ],
          submit_schema: {
            type: "object",
            required: ["selected_id", "selected_item"],
            properties: {
              selected_id: { type: "string" },
              selected_item: { type: "object" },
            },
          },
        },
        { name: "hero_list", label: "首图大列表", tags: [], modes: ["interactive"], required_bindings: [] },
        { name: "hover_focus", label: "悬停放大", tags: [], modes: ["interactive"], required_bindings: [] },
      ],
      description: "图片候选三选一控件",
    },
  ],
};

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockFetch() {
  const createdTasks: Array<{
    task_id: string;
    project_id: string;
    workflow_id?: string;
    workflow_name?: string;
    workflow_version?: string;
    status: string;
    current_node_id?: string | null;
    created_at: string;
  }> = [];
  const deletedTaskIds = new Set<string>();
  const uploadedAssetForms: FormData[] = [];
  let assetCollections = [
    { collection_id: "collection-scenes", name: "分镜素材", parent_id: null, asset_count: 2 },
    { collection_id: "collection-characters", name: "角色素材", parent_id: "collection-scenes", asset_count: 1 },
  ];
  let assetRecords: AssetRecord[] = [
    {
      asset_id: "asset-1",
      asset_type: "file",
      name: "参考图",
      scope: "project",
      project_id: "global",
      mime_type: "image/png",
      size_bytes: 1024,
      metadata: { public_url: "https://cdn.example.com/ref.png", variant_description: "动态显示的变体描述" },
      created_at: "2026-05-27T08:01:00Z",
    },
    {
      asset_id: "asset-global",
      asset_type: "file",
      name: "全局参考.png",
      scope: "global",
      project_id: null,
      mime_type: "image/png",
      size_bytes: 2048,
      metadata: { public_url: "https://cdn.example.com/global.png" },
      created_at: "2026-05-27T08:02:00Z",
    },
  ];
  let assetTags: Array<{ tag_id: string; name: string; scope: string; project_id: string | null; asset_count: number }> = [
    { tag_id: "tag-character", name: "角色", scope: "project", project_id: "global", asset_count: 1 },
    { tag_id: "tag-location", name: "地点", scope: "project", project_id: "global", asset_count: 0 },
    { tag_id: "tag-prop", name: "道具", scope: "project", project_id: "global", asset_count: 0 },
    { tag_id: "tag-episode-metadata", name: "集元数据", scope: "project", project_id: "global", asset_count: 0 },
    { tag_id: "tag-empty", name: "空标签", scope: "project", project_id: "global", asset_count: 0 },
    { tag_id: "tag-global", name: "全局通用", scope: "global", project_id: null, asset_count: 0 },
  ];
  let nextCreatedTagNumber = 2;
  const assetTagLinks = new Set(["asset-1:tag-character"]);
  const assetTagItems = () => assetTags.map((tag) => ({
    ...tag,
    asset_count: [...assetTagLinks].some((item) => item.endsWith(`:${tag.tag_id}`)) ? 1 : 0,
  }));

  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";

    if (url === "/api/auth/login" && method === "POST") {
      return jsonResponse({ user: { user_id: "user-1", username: "alice" }, access_token: "token", token_type: "bearer" });
    }
    if (url === "/api/projects" && method === "GET") {
      return jsonResponse({
        items: [
          { project_id: "global", name: "全局项目", owner_user_id: "system", description: "所有用户可访问的默认项目", created_at: "2026-05-27T00:00:00Z" },
          { project_id: "project-1", name: "演示项目", owner_user_id: "user-1", created_at: "2026-05-27T08:00:00Z" },
          { project_id: "project-2", name: "客户项目", owner_user_id: "user-1", created_at: "2026-05-27T09:00:00Z" },
        ],
      });
    }
    if (url === "/api/tasks?project_id=global") {
      return jsonResponse({
        items: [
          {
            task_id: "task-1",
            project_id: "global",
            workflow_id: "storyboard_generation",
            workflow_name: workflowContract.workflow.name,
            workflow_version: "1.0.0",
            status: "waiting",
            current_node_id: "choose_image",
            created_at: "2026-05-27T08:10:00Z",
          },
          {
            task_id: "task-storyboard-23",
            project_id: "global",
            workflow_id: "asset_storyboard_generation",
            workflow_name: "Asset Storyboard Generation",
            workflow_version: "1.1.0",
            status: "waiting",
            current_node_id: "select_episode_metadata",
            current_view: { summary: { episode_name: "23、私放晁天王" } },
            created_at: "2026-05-27T08:09:30Z",
          },
          {
            task_id: "task-episode-23",
            project_id: "global",
            workflow_id: "asset_catalog",
            workflow_name: "资产提取",
            workflow_version: "1.0.0",
            status: "waiting",
            current_node_id: "collect_asset_catalog_input",
            current_view: { summary: { episode_name: "23、私放晁天王" } },
            created_at: "2026-05-27T08:09:00Z",
          },
          ...createdTasks.filter((task) => task.project_id === "global"),
        ].filter((task) => !deletedTaskIds.has(task.task_id)),
      });
    }
    if (url === "/api/tasks?project_id=project-1") {
      return jsonResponse({
        items: [
          {
            task_id: "task-1",
            project_id: "project-1",
            workflow_id: "storyboard_generation",
            workflow_name: "故事板生成",
            workflow_version: "1.0.0",
            status: "waiting",
            current_node_id: "choose_image",
            created_at: "2026-05-27T08:10:00Z",
          },
          ...createdTasks.filter((task) => task.project_id === "project-1"),
        ].filter((task) => !deletedTaskIds.has(task.task_id)),
      });
    }
    if (url === "/api/tasks?project_id=project-2") {
      return jsonResponse({
        items: [{
          task_id: "task-project-2",
          project_id: "project-2",
          workflow_id: "runninghub_text_to_image_test",
          workflow_name: "RunningHub 文生图调用测试",
          workflow_version: "1.0.0",
          status: "created",
          current_node_id: null,
          created_at: "2026-05-27T09:10:00Z",
        }],
      });
    }
    if (url === "/api/workflows?project_id=global" || url === "/api/workflows?project_id=project-1" || url === "/api/workflows?project_id=project-2" || url === "/api/workflows") {
      return jsonResponse({
        items: [
          workflowContract,
          {
            workflow: {
              id: "runninghub_text_to_image_test",
              version: "1.0.0",
              name: "RunningHub Text To Image Test",
              description: "Developer-only workflow test",
              input_schema: { type: "object", properties: { prompt: { type: "string" } } },
            },
            nodes: [{
              id: "run",
              ref: "ai.runninghub_text_to_image.v1",
              inputs: {
                prompt: {
                  from_user: true,
                  schema: { type: "string", title: "提示词" },
                },
              },
            }],
            edges: [],
          },
        ],
      });
    }
    if (url === "/api/ui/node-controls") {
      return jsonResponse(uiControlsResponse);
    }
    if (url.startsWith("/api/assets/search")) {
      return jsonResponse({ items: assetRecords });
    }
    if (url.startsWith("/api/assets/") && url.includes("/thumbnail")) {
      return Promise.resolve(new Response(new Uint8Array([137, 80, 78, 71]), {
        status: 200,
        headers: { "Content-Type": "image/png", "X-Asset-Thumbnail-Cache": "miss" },
      }));
    }
    if (url.startsWith("/api/assets/") && url.includes("/content")) {
      return Promise.resolve(new Response(new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]), {
        status: 200,
        headers: { "Content-Type": "image/png" },
      }));
    }
    if (url === "/api/assets/files" && method === "POST") {
      uploadedAssetForms.push(init?.body as FormData);
      const form = init?.body as FormData;
      return jsonResponse({
        asset_id: `asset-upload-${uploadedAssetForms.length}`,
        asset_type: "file",
        name: String(form.get("name") ?? "uploaded.png"),
        scope: "project",
        project_id: "global",
        mime_type: "image/png",
        size_bytes: 16,
        metadata: { public_url: "https://cdn.example.com/uploaded.png" },
        created_at: "2026-05-27T08:03:00Z",
      });
    }
    if (url === "/api/assets/files/intelligent" && method === "POST") {
      uploadedAssetForms.push(init?.body as FormData);
      const form = init?.body as FormData;
      const scope = form.get("scope") === "global" ? "global" : "project";
      const asset = {
        asset_id: `asset-smart-${uploadedAssetForms.length}`,
        asset_type: "file",
        name: String(form.get("name") ?? "智能资产"),
        scope,
        project_id: String(form.get("project_id") ?? "global"),
        mime_type: "image/png",
        size_bytes: 16,
        metadata: {
          public_url: "https://cdn.example.com/smart.png",
          type: form.get("asset_type"),
          summary: "根据原作补全的生平背景。",
          relationships: "相关人物关系。",
        },
        created_at: "2026-05-27T08:04:00Z",
      } satisfies AssetRecord;
      assetRecords = [asset, ...assetRecords];
      return jsonResponse({ asset, confidence: 0.9, reasoning: "根据资产名和世界背景补全。" });
    }
    if (url.startsWith("/api/assets/asset-") && method === "PATCH") {
      const assetId = decodeURIComponent(url.split("/").pop() ?? "");
      const body = JSON.parse(String(init?.body ?? "{}")) as { name: string; metadata?: Record<string, unknown> };
      assetRecords = assetRecords.map((asset) =>
        asset.asset_id === assetId ? { ...asset, name: body.name, metadata: (body.metadata ?? asset.metadata) as AssetRecord["metadata"] } : asset,
      );
      return jsonResponse(assetRecords.find((asset) => asset.asset_id === assetId));
    }
    if (url === "/api/assets/collections" && method === "POST") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { name: string; parent_id?: string | null };
      const collection = {
        collection_id: `collection-${assetCollections.length + 1}`,
        name: body.name,
        parent_id: body.parent_id ?? null,
        asset_count: 0,
      };
      assetCollections = [...assetCollections, collection];
      return jsonResponse(collection);
    }
    if (url.startsWith("/api/assets/collections/") && method === "PATCH") {
      const collectionId = decodeURIComponent(url.split("/").pop() ?? "");
      const body = JSON.parse(String(init?.body ?? "{}")) as { name: string };
      assetCollections = assetCollections.map((collection) =>
        collection.collection_id === collectionId ? { ...collection, name: body.name } : collection,
      );
      return jsonResponse(assetCollections.find((collection) => collection.collection_id === collectionId));
    }
    if (url.startsWith("/api/assets/collections/") && method === "DELETE") {
      const collectionId = decodeURIComponent(url.split("/").pop() ?? "");
      const deletedIds = new Set<string>([collectionId]);
      let changed = true;
      while (changed) {
        changed = false;
        for (const collection of assetCollections) {
          if (collection.parent_id && deletedIds.has(collection.parent_id) && !deletedIds.has(collection.collection_id)) {
            deletedIds.add(collection.collection_id);
            changed = true;
          }
        }
      }
      assetCollections = assetCollections.filter((collection) => !deletedIds.has(collection.collection_id));
      return jsonResponse({ deleted: true });
    }
    if (
      url === "/api/assets/collections?scope=combined&project_id=global" ||
      url === "/api/assets/collections?scope=project&project_id=global" ||
      url === "/api/assets/collections?scope=combined&project_id=project-1" ||
      url === "/api/assets/collections?scope=project&project_id=project-1"
    ) return jsonResponse({ items: assetCollections });
    if (url === "/api/assets/asset-1/tags" && method === "GET") {
      return jsonResponse({ items: assetTagItems().filter((tag) => assetTagLinks.has(`asset-1:${tag.tag_id}`)) });
    }
    if (url === "/api/assets/asset-global/tags" && method === "GET") {
      return jsonResponse({ items: assetTagItems().filter((tag) => assetTagLinks.has(`asset-global:${tag.tag_id}`)) });
    }
    if (url.startsWith("/api/assets/asset-1/tags/") && method === "POST") {
      const tagId = decodeURIComponent(url.split("/").pop() ?? "");
      assetTagLinks.add(`asset-1:${tagId}`);
      return jsonResponse({ items: assetTagItems().filter((tag) => assetTagLinks.has(`asset-1:${tag.tag_id}`)) });
    }
    if (url.startsWith("/api/assets/asset-1/tags/") && method === "DELETE") {
      const tagId = decodeURIComponent(url.split("/").pop() ?? "");
      assetTagLinks.delete(`asset-1:${tagId}`);
      return jsonResponse({ items: assetTagItems().filter((tag) => assetTagLinks.has(`asset-1:${tag.tag_id}`)) });
    }
    if (url === "/api/assets/tags" && method === "POST") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { name: string; scope: string; project_id?: string | null };
      const tag = {
        tag_id: `tag-${nextCreatedTagNumber++}`,
        name: body.name,
        scope: body.scope,
        project_id: body.project_id ?? null,
        asset_count: 0,
      };
      assetTags = [...assetTags, tag];
      return jsonResponse(tag);
    }
    if (url.startsWith("/api/assets/tags/") && method === "PATCH") {
      const tagId = decodeURIComponent(url.split("/").pop() ?? "");
      const body = JSON.parse(String(init?.body ?? "{}")) as { name: string };
      assetTags = assetTags.map((tag) => tag.tag_id === tagId ? { ...tag, name: body.name } : tag);
      return jsonResponse(assetTags.find((tag) => tag.tag_id === tagId));
    }
    if (url.startsWith("/api/assets/tags/") && method === "DELETE") {
      const tagId = decodeURIComponent(url.split("/").pop() ?? "");
      if (assetTagItems().find((tag) => tag.tag_id === tagId)?.asset_count) {
        return jsonResponse({ error: { code: "asset_tag_not_empty", message: "标签仍被资产使用" } }, 400);
      }
      assetTags = assetTags.filter((tag) => tag.tag_id !== tagId);
      return jsonResponse({ deleted: true });
    }
    if (url.startsWith("/api/assets/") && method === "DELETE") {
      const assetId = decodeURIComponent(url.split("/").pop() ?? "");
      assetRecords = assetRecords.filter((asset) => asset.asset_id !== assetId);
      return jsonResponse({ deleted: true, asset_id: assetId });
    }
    if (
      url === "/api/assets/tags?scope=combined&project_id=global" ||
      url === "/api/assets/tags?scope=project&project_id=global" ||
      url === "/api/assets/tags?scope=combined&project_id=project-1" ||
      url === "/api/assets/tags?scope=project&project_id=project-1" ||
      url === "/api/assets/tags?scope=combined&project_id=project-2" ||
      url === "/api/assets/tags?scope=project&project_id=project-2"
    ) return jsonResponse({ items: assetTagItems() });
    if (url === "/api/tasks/task-episode-23?project_id=global") {
      return jsonResponse({
        task: {
          task_id: "task-episode-23",
          project_id: "global",
          workflow_id: "asset_catalog",
          workflow_name: "资产提取",
          workflow_version: "1.0.0",
          status: "waiting",
          current_node_id: "collect_asset_catalog_input",
          current_view: { summary: { episode_name: "23、私放晁天王" } },
          created_at: "2026-05-27T08:09:00Z",
        },
        workflow_snapshot: {
          workflow: { id: "asset_catalog", version: "1.0.0", name: "资产提取" },
          nodes: [{ id: "collect_asset_catalog_input", ref: "system.user_input.v1", name: "剧本输入" }],
          edges: [],
        },
        node_executions: [
          {
            node_execution_id: "exec-episode-input",
            node_id: "collect_asset_catalog_input",
            node_ref: "system.user_input.v1",
            status: "waiting",
            input_snapshot: {},
            output_snapshot: { episode_name: "23、私放晁天王" },
            attempt: 1,
          },
        ],
        node_attempts: {},
        events: [],
      });
    }
    if (url === "/api/tasks/task-storyboard-23?project_id=global") {
      return jsonResponse({
        task: {
          task_id: "task-storyboard-23",
          project_id: "global",
          workflow_id: "asset_storyboard_generation",
          workflow_name: "Asset Storyboard Generation",
          workflow_version: "1.1.0",
          status: "waiting",
          current_node_id: "select_episode_metadata",
          current_view: { summary: { episode_name: "23、私放晁天王" } },
          created_at: "2026-05-27T08:09:30Z",
        },
        workflow_snapshot: {
          workflow: { id: "asset_storyboard_generation", version: "1.1.0", name: "分镜生成" },
          nodes: [{ id: "select_episode_metadata", ref: "system.user_input.v1", name: "选择集" }],
          edges: [],
        },
        node_executions: [
          {
            node_execution_id: "exec-storyboard-episode",
            node_id: "select_episode_metadata",
            node_ref: "system.user_input.v1",
            status: "waiting",
            input_snapshot: {},
            output_snapshot: { episode_name: "23、私放晁天王" },
            attempt: 1,
          },
        ],
        node_attempts: {},
        events: [],
      });
    }
    if (url === "/api/tasks/task-1?project_id=global" || url === "/api/tasks/task-2?project_id=global" || url === "/api/tasks/task-1?project_id=project-1" || url === "/api/tasks/task-2?project_id=project-1") {
      const createdTask = createdTasks.find((task) => task.task_id === "task-2");
      const projectId = url.includes("project_id=global") ? "global" : "project-1";
      return jsonResponse({
        task: createdTask ?? {
          task_id: "task-1",
          project_id: projectId,
          workflow_id: "storyboard_generation",
          workflow_name: "故事板生成",
          workflow_version: "1.0.0",
          status: "waiting",
          current_node_id: "choose_image",
          created_at: "2026-05-27T08:10:00Z",
        },
        workflow_snapshot: workflowContract,
        node_executions: [
          {
            node_execution_id: "exec-1",
            node_id: "prepare_prompt",
            node_ref: "tools.storyboard_prompt.v1",
            status: "succeeded",
            input_snapshot: { topic: "雨夜城市" },
            output_snapshot: { prompt: "雨夜城市电影感", results: [{ public_url: "https://cdn.example.com/a.png" }] },
            attempt: 1,
          },
          {
            node_execution_id: "exec-2",
            node_id: "choose_image",
            node_ref: "system.user_choice.v1",
            status: "waiting",
            input_snapshot: {
              question: "选择一张图",
              candidates: [
                { id: "a", label: "第一张", image_url: "https://cdn.example.com/a.png" },
                { id: "b", label: "第二张", image_url: "https://cdn.example.com/b.png" },
                { id: "c", label: "第三张", image_url: "https://cdn.example.com/c.png" },
              ],
            },
            output_snapshot: null,
            metadata: {
              question: "选择一张图",
              candidates: [
                { id: "a", label: "第一张", image_url: "https://cdn.example.com/a.png" },
                { id: "b", label: "第二张", image_url: "https://cdn.example.com/b.png" },
                { id: "c", label: "第三张", image_url: "https://cdn.example.com/c.png" },
              ],
            },
            attempt: 1,
          },
        ],
        node_attempts: {},
        events: [{ event_id: "event-1", event_type: "node_waiting", node_id: "choose_image", message: "等待选择" }],
      });
    }
    if (url === "/api/tasks" && method === "POST") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { project_id?: string; contract?: { workflow?: { name?: string; version?: string } } };
      const task = {
        task_id: body.project_id === "project-2" ? "task-project-2-created" : "task-2",
        project_id: body.project_id ?? "global",
        workflow_name: body.contract?.workflow?.name ?? "故事板生成",
        workflow_version: String(body.contract?.workflow?.version ?? "1.0.0"),
        status: "created",
        current_node_id: null,
        created_at: "2026-05-27T08:20:00Z",
      };
      createdTasks.push(task);
      return jsonResponse({
        task_id: task.task_id,
        project_id: task.project_id,
        status: task.status,
        workflow_name: task.workflow_name,
        workflow_version: task.workflow_version,
      });
    }
    if (url === "/api/tasks/task-1?project_id=global" && method === "DELETE") {
      deletedTaskIds.add("task-1");
      return jsonResponse({ deleted: true, task_id: "task-1" });
    }
    if (url === "/api/tasks/task-1/interactions" && method === "POST") {
      return jsonResponse({ task_id: "task-1", project_id: "global", status: "running" });
    }
    if (url === "/api/tasks/task-1/nodes/prepare_prompt/rerun" && method === "POST") {
      return jsonResponse({ task_id: "task-1", project_id: "global", status: "running" });
    }
    return jsonResponse({ items: [] });
  });
}

async function login() {
  await userEvent.type(screen.getByLabelText("用户名"), "alice");
  await userEvent.type(screen.getByLabelText("密码"), "secret-123");
  await userEvent.click(screen.getByRole("button", { name: "登录" }));
  await screen.findByRole("heading", { name: "项目" });
  await userEvent.click(await screen.findByRole("button", { name: "进入 全局项目 工作台" }));
  await screen.findByRole("button", { name: "创建任务" });
}

describe("XiAgent V2 app", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", mockFetch());
  });

  it("requires a real user login and opens the project entry page", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "登录 XiAgent" })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("用户名"), "alice");
    await userEvent.type(screen.getByLabelText("密码"), "secret-123");
    await userEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("heading", { name: "项目" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "进入 全局项目 工作台" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "进入 演示项目 工作台" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "创建任务" })).not.toBeInTheDocument();
  });

  it("opens the shared global project workbench from the project entry page", async () => {
    render(<App />);
    await login();

    expect(screen.getByRole("heading", { name: "全局项目" })).toBeInTheDocument();
    expect(screen.getByText("所有用户可访问的默认项目")).toBeInTheDocument();
    const storyboardTask = screen.getByRole("button", { name: "打开 分镜生成" });
    expect(storyboardTask).toHaveTextContent("第23集 私放晁天王");
    await userEvent.click(storyboardTask);
    await screen.findByLabelText("任务运行详情");
    expect(screen.getByRole("button", { name: "打开 分镜生成" })).toHaveTextContent("第23集 私放晁天王");
    const assetTask = screen.getByRole("button", { name: "打开 资产提取" });
    expect(assetTask).toHaveTextContent("第23集 私放晁天王");
    await userEvent.click(assetTask);
    await screen.findByLabelText("任务运行详情");
    expect(screen.getByRole("button", { name: "打开 资产提取" })).toHaveTextContent("第23集 私放晁天王");
    expect(screen.queryByLabelText("当前项目")).not.toBeInTheDocument();
  });

  it("creates tasks from launch information and leaves user input to the first node", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await screen.findByRole("heading", { name: "新建任务" });

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/workflows?project_id=global")).toBe(true);
    });
    expect(screen.getByText(/RunningHub Text To Image Test/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "启动信息" })).toBeInTheDocument();
    expect(screen.getByText(/创作主题/)).toBeInTheDocument();
    expect(screen.getByText(/这些参数将在任务详情的第一个输入节点中填写/)).toBeInTheDocument();
    expect(screen.queryByLabelText("创作主题")).not.toBeInTheDocument();
    expect(screen.queryByText(/input_schema/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\"type\"/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "创建并运行" }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([url, init]) => url === "/api/tasks" && init?.method === "POST");
      expect(post).toBeTruthy();
      const body = JSON.parse(String(post?.[1]?.body));
      expect(body).toMatchObject({ project_id: "global" });
      expect(body).not.toHaveProperty("input_data");
    });
    const detail = await screen.findByLabelText("任务运行详情");
    expect(detail).toBeInTheDocument();
    expect(await within(detail).findByRole("heading", { name: "故事板生成", level: 1 })).toBeInTheDocument();
    const context = document.querySelector(".context-panel") as HTMLElement;
    expect(within(context).getByText("选择图片")).toBeInTheDocument();
    expect(within(context).queryByText("未记录")).not.toBeInTheDocument();
  });

  it("switches task and workflow creation data to the selected project", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    expect(await screen.findByRole("button", { name: "打开 故事板生成" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "返回项目" }));
    await userEvent.click(await screen.findByRole("button", { name: "进入 客户项目 工作台" }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "打开 故事板生成" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "打开 RunningHub 文生图调用测试" })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await screen.findByRole("heading", { name: "新建任务" });
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/workflows?project_id=project-2")).toBe(true);
    });

    await userEvent.click(screen.getByRole("button", { name: /RunningHub Text To Image Test/ }));
    expect(screen.getByText(/提示词/)).toBeInTheDocument();
    expect(screen.queryByLabelText("提示词")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "创建并运行" }));

    await waitFor(() => {
      const post = [...fetchMock.mock.calls].reverse().find(([url, init]) => url === "/api/tasks" && init?.method === "POST");
      expect(post).toBeTruthy();
      const body = JSON.parse(String(post?.[1]?.body));
      expect(body).toMatchObject({ project_id: "project-2" });
      expect(body).not.toHaveProperty("input_data");
    });
  });

  it("asks for confirmation before deleting a task from the list", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(await screen.findByRole("button", { name: /task-1/ }));

    const dialog = await screen.findByRole("dialog", { name: "确认删除任务" });
    expect(within(dialog).getByText(/删除后/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url, init]) => url === "/api/tasks/task-1?project_id=global" && init?.method === "DELETE"),
      ).toBe(true);
      expect(screen.queryByRole("button", { name: "删除任务 task-1" })).not.toBeInTheDocument();
    });
  });

  it("sends rerun revision note text when confirming a node rerun", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(await screen.findByRole("button", { name: "打开 故事板生成" }));
    const detail = await screen.findByLabelText("任务运行详情");
    const prepareStep = within(detail).getAllByText("准备提示词").find((item) => item.closest(".stage-step-row"));
    const prepareRow = prepareStep?.closest(".stage-step-row") as HTMLElement;
    expect(prepareRow).toBeTruthy();

    await userEvent.click(within(prepareRow).getByRole("button", { name: "重新运行" }));
    const dialog = await screen.findByRole("dialog", { name: "确认重新运行步骤" });
    await userEvent.type(within(dialog).getByLabelText("修改意见"), "保留原有水墨风格，只修正角色服装。");
    await userEvent.click(within(dialog).getByRole("button", { name: "确认重新运行" }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([url, init]) => url === "/api/tasks/task-1/nodes/prepare_prompt/rerun" && init?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        project_id: "global",
        rerun_revision_note: "保留原有水墨风格，只修正角色服装。",
      });
    });
  });

  it("shows node input and output as user-facing cards and supports waiting interaction", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(await screen.findByRole("button", { name: "打开 故事板生成" }));

    const detail = await screen.findByLabelText("任务运行详情");
    expect(within(detail).getByText("P1 用户输入")).toBeInTheDocument();
    expect(within(detail).getByText("P2 生成与选择")).toBeInTheDocument();
    expect(within(detail).getAllByText("待运行").length).toBeGreaterThan(0);
    expect(within(detail).getAllByText("准备提示词").length).toBeGreaterThan(0);
    expect(within(detail).queryByLabelText("节点进度：成功")).not.toBeInTheDocument();
    expect(within(detail).queryByText("雨夜城市电影感")).not.toBeInTheDocument();
    const prepareStep = within(detail).getAllByText("准备提示词").find((item) => item.closest(".stage-step-row"));
    expect(prepareStep).toBeTruthy();
    expect(prepareStep!.closest(".stage-step-row")?.textContent).toContain("S1");
    expect(prepareStep!.closest(".stage-step-row")?.querySelector(".stage-step-progress")).toBeTruthy();
    await userEvent.click(prepareStep!.closest(".stage-step-row") as HTMLElement);
    expect(prepareStep!.closest(".stage-step-entry")?.querySelector(".node-detail-body")).toBeTruthy();
    expect(within(detail).getByText("雨夜城市电影感")).toBeInTheDocument();
    expect(within(detail).getByRole("img", { name: "准备提示词 输出图片 1" })).toHaveAttribute("src", "https://cdn.example.com/a.png");
    expect(within(detail).getAllByText("输入")[0].closest("details")).not.toHaveAttribute("open");
    expect(within(detail).getAllByText("输出")[0].closest("details")).toHaveAttribute("open");
    for (const eventSummary of within(detail).getAllByText("节点事件")) {
      expect(eventSummary.closest("details")).not.toHaveAttribute("open");
    }
    expect(screen.queryByText(/output_snapshot/)).not.toBeInTheDocument();
    expect(screen.queryByText(/public_url/)).not.toBeInTheDocument();

    const chooseStep = within(detail).getAllByText("选择图片").find((item) => item.closest(".stage-step-row"));
    expect(chooseStep).toBeTruthy();
    await userEvent.click(chooseStep!.closest(".stage-step-row") as HTMLElement);
    await userEvent.click(screen.getByRole("button", { name: "选择 第二张" }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([url, init]) => url === "/api/tasks/task-1/interactions" && init?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        project_id: "global",
        node_id: "choose_image",
        input: {
          selected_id: "b",
          selected_index: 1,
          selected_image_url: "https://cdn.example.com/b.png",
        },
      });
    });
  });

  it("expands the matching step when clicking a collapsed stage progress dot", async () => {
    render(<App />);
    await login();

    await userEvent.click(await screen.findByRole("button", { name: "打开 故事板生成" }));

    const detail = await screen.findByLabelText("任务运行详情");
    await userEvent.click(within(detail).getByRole("button", { name: /P2 生成与选择/ }));

    expect(within(detail).queryByText("雨夜城市电影感")).not.toBeInTheDocument();
    await userEvent.click(within(detail).getByRole("button", { name: /展开 S2 选择图片/ }));

    expect(within(detail).getByRole("button", { name: "选择 第一张" })).toBeInTheDocument();
    const chooseStep = within(detail).getAllByText("选择图片").find((item) => item.closest(".stage-step-row"));
    expect(chooseStep?.closest(".stage-step-entry")?.querySelector(".node-detail-body")).toBeTruthy();
  });

  it("keeps the task workbench scene mounted when switching to the asset library and back", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const { container } = render(<App />);
    await login();

    await userEvent.click(await screen.findByRole("button", { name: "打开 故事板生成" }));

    const detail = await screen.findByLabelText("任务运行详情");
    const prepareStep = within(detail).getAllByText("准备提示词").find((item) => item.closest(".stage-step-row"));
    expect(prepareStep).toBeTruthy();
    await userEvent.click(prepareStep!.closest(".stage-step-row") as HTMLElement);
    expect(within(detail).getByText("雨夜城市电影感")).toBeInTheDocument();

    const workspaceMain = container.querySelector(".workspace-main") as HTMLElement;
    expect(workspaceMain).toBeTruthy();
    workspaceMain.scrollTop = 480;
    fireEvent.scroll(workspaceMain);

    const detailFetchCountBefore = fetchMock.mock.calls.filter(([url, init]) =>
      url === "/api/tasks/task-1?project_id=global" && (init?.method ?? "GET") === "GET",
    ).length;
    expect(detailFetchCountBefore).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    expect(await screen.findByRole("toolbar", { name: "资产库标签操作" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "任务工作台" }));

    const detailAfterReturn = screen.getByLabelText("任务运行详情");
    expect(detailAfterReturn).toBe(detail);
    expect(screen.queryByText("选择任务或创建新任务")).not.toBeInTheDocument();
    expect(screen.queryByText("正在加载任务详情...")).not.toBeInTheDocument();
    expect(within(detailAfterReturn).getByText("雨夜城市电影感")).toBeInTheDocument();
    const prepareStepAfterReturn = within(detailAfterReturn).getAllByText("准备提示词").find((item) => item.closest(".stage-step-row"));
    expect(prepareStepAfterReturn?.closest(".stage-step-entry")?.querySelector(".node-detail-body")).toBeTruthy();

    const workspaceMainAfterReturn = container.querySelector(".workspace-main") as HTMLElement;
    expect(workspaceMainAfterReturn).toBe(workspaceMain);
    expect(workspaceMainAfterReturn.scrollTop).toBe(480);
    expect(fetchMock.mock.calls.filter(([url, init]) =>
      url === "/api/tasks/task-1?project_id=global" && (init?.method ?? "GET") === "GET",
    )).toHaveLength(detailFetchCountBefore);
  });

  it("renders unwrapped output controls directly in the node detail", async () => {
    const baseFetch = mockFetch();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/tasks/task-1?project_id=global" && method === "GET") {
        return jsonResponse({
          task: {
            task_id: "task-1",
            project_id: "global",
            workflow_id: "asset_catalog",
            workflow_name: "资产提取",
            workflow_version: "1.0.0",
            status: "succeeded",
            current_node_id: "finish_summary",
            created_at: "2026-05-27T08:10:00Z",
          },
          workflow_snapshot: {
            workflow: {
              id: "asset_catalog",
              version: "1.0.0",
              name: "资产提取",
              ui: {
                stages: [{ id: "p5_final", name: "P5 任务完成", nodes: ["finish_summary"] }],
              },
            },
            nodes: [{
              id: "finish_summary",
              ref: "tool.episode_metadata_finalize.v1",
              name: "任务完成",
              ui: {
                controls: {
                  output: { control_id: "ui.display.asset_task_summary.v1", variant: "catalog_complete", mode: "readonly" },
                },
              },
            }],
            edges: [],
          },
          node_executions: [{
            node_execution_id: "exec-summary",
            node_id: "finish_summary",
            node_ref: "tool.episode_metadata_finalize.v1",
            status: "succeeded",
            output_snapshot: {
              asset_images: [{
                asset_type: "character",
                asset_key: "林冲",
                full_name: "林冲_囚服",
                image_url: "https://cdn.example.com/linchong.png",
                source: "library",
              }],
            },
            attempt: 1,
          }],
          node_attempts: {},
          events: [],
        });
      }
      return baseFetch(input, init);
    }));
    render(<App />);
    await login();

    await userEvent.click(await screen.findByRole("button", { name: "打开 故事板生成" }));
    const detail = await screen.findByLabelText("任务运行详情");
    const finishStep = within(detail).getAllByText("任务完成").find((item) => item.closest(".stage-step-row"));
    expect(finishStep).toBeTruthy();
    await userEvent.click(finishStep!.closest(".stage-step-row") as HTMLElement);

    expect(within(detail).getByText("资产编目已完成")).toBeInTheDocument();
    expect(within(detail).getByRole("button", { name: "导出资产为压缩包" })).toBeEnabled();
    expect(within(detail).queryByText("输出")).not.toBeInTheDocument();
  });

  it("shows backend validation errors when waiting interaction submit fails", async () => {
    const baseFetch = mockFetch();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/tasks/task-1/interactions" && init?.method === "POST") {
        return jsonResponse({
          error: {
            code: "json_value_validation_failed",
            message: "数据不满足 JSON Schema",
            details: { path: ["aspect_ratio"], error: "'' is too short" },
          },
        }, 400);
      }
      return baseFetch(input, init);
    }));

    render(<App />);
    await login();
    await userEvent.click(await screen.findByRole("button", { name: "打开 故事板生成" }));
    expect(screen.getByRole("button", { name: /S2 选择图片/ })).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByRole("button", { name: "选择 第二张" }));

    expect(await screen.findByText(/数据不满足 JSON Schema/)).toBeInTheDocument();
    expect(screen.getByText(/字段 aspect_ratio/)).toBeInTheDocument();
  });

  it("locks schema input controls while a node input submission is in flight", async () => {
    let resolveInteraction: (response: Response) => void = () => {};
    const pendingInteraction = new Promise<Response>((resolve) => {
      resolveInteraction = resolve;
    });
    const baseFetch = mockFetch();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/tasks?project_id=global" && method === "GET") {
        return jsonResponse({
          items: [{
            task_id: "schema-task",
            project_id: "global",
            workflow_id: "runninghub_text_to_image_test",
            workflow_name: "RunningHub Text To Image Test",
            workflow_version: "1.0.0",
            status: "waiting",
            current_node_id: "generate_image",
            created_at: "2026-05-27T10:00:00Z",
          }],
        });
      }
      if (url === "/api/tasks/schema-task?project_id=global" && method === "GET") {
        return jsonResponse({
          task: {
            task_id: "schema-task",
            project_id: "global",
            workflow_id: "runninghub_text_to_image_test",
            workflow_name: "RunningHub Text To Image Test",
            workflow_version: "1.0.0",
            status: "waiting",
            current_node_id: "generate_image",
            created_at: "2026-05-27T10:00:00Z",
          },
          workflow_snapshot: {
            workflow: { id: "runninghub_text_to_image_test", version: "1.0.0", name: "RunningHub Text To Image Test" },
            nodes: [{
              id: "generate_image",
              ref: "ai.runninghub_text_to_image.v1",
              name: "生成图片",
              inputs: {
                prompt: {
                  from_user: true,
                  schema: { type: "string", minLength: 1, title: "提示词" },
                },
              },
              ui: {
                sections: {
                  input: { default_open: true },
                  output: { default_open: false },
                },
                controls: {
                  input: { control_id: "ui.input.schema_form.v1", variant: "default", mode: "input" },
                },
              },
            }],
            edges: [],
          },
          node_executions: [{
            node_execution_id: "schema-exec",
            node_id: "generate_image",
            node_ref: "ai.runninghub_text_to_image.v1",
            status: "waiting",
            input_snapshot: {},
            output_snapshot: {},
            metadata: {
              input_schema: {
                type: "object",
                required: ["prompt"],
                properties: { prompt: { type: "string", minLength: 1, title: "提示词" } },
                additionalProperties: false,
              },
            },
            attempt: 1,
          }],
          node_attempts: {},
          events: [{ event_id: "schema-event", event_type: "human_input_requested", node_id: "generate_image" }],
        });
      }
      if (url === "/api/tasks/schema-task/interactions" && method === "POST") {
        return pendingInteraction;
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await login();
    await userEvent.click(await screen.findByRole("button", { name: "打开 RunningHub Text To Image Test" }));
    const detail = await screen.findByLabelText("任务运行详情");
    expect(within(detail).getByText("输入").closest("details")).toHaveAttribute("open");
    expect(within(detail).getByText("输出").closest("details")).not.toHaveAttribute("open");
    const prompt = within(detail).getByLabelText("提示词");
    await userEvent.type(prompt, "真实浏览器输入");
    const submitButton = within(detail).getByRole("button", { name: "提交并继续" });
    fireEvent.click(submitButton);
    fireEvent.click(submitButton);

    expect(prompt).toHaveAttribute("readonly");
    expect(within(screen.getByRole("button", { name: "打开 RunningHub Text To Image Test" })).getByText("运行中")).toBeInTheDocument();
    expect(within(detail).getAllByText("运行中").length).toBeGreaterThanOrEqual(1);
    expect(within(detail).getAllByText("等待用户").length).toBeGreaterThan(0);
    expect(fetchMock.mock.calls.filter(([url, init]) =>
      url === "/api/tasks/schema-task/interactions" && init?.method === "POST",
    )).toHaveLength(1);

    void jsonResponse({ task_id: "schema-task", project_id: "global", status: "running" }).then(resolveInteraction);
  });

  it("syncs the selected task row from task event stream refreshes", async () => {
    let taskStatus = "waiting";
    let nodeStatus = "waiting";
    let streamController = null as unknown as ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        streamController = controller;
      },
    });
    const baseFetch = mockFetch();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/tasks?project_id=global" && method === "GET") {
        return jsonResponse({
          items: [{
            task_id: "schema-task",
            project_id: "global",
            workflow_id: "runninghub_text_to_image_test",
            workflow_name: "RunningHub Text To Image Test",
            workflow_version: "1.0.0",
            status: "waiting",
            current_node_id: "generate_image",
            created_at: "2026-05-27T10:00:00Z",
          }],
        });
      }
      if (url === "/api/tasks/schema-task?project_id=global" && method === "GET") {
        return jsonResponse({
          task: {
            task_id: "schema-task",
            project_id: "global",
            workflow_id: "runninghub_text_to_image_test",
            workflow_name: "RunningHub Text To Image Test",
            workflow_version: "1.0.0",
            status: taskStatus,
            current_node_id: "generate_image",
            created_at: "2026-05-27T10:00:00Z",
          },
          workflow_snapshot: {
            workflow: { id: "runninghub_text_to_image_test", version: "1.0.0", name: "RunningHub Text To Image Test" },
            nodes: [{ id: "generate_image", ref: "ai.runninghub_text_to_image.v1", name: "生成图片" }],
            edges: [],
          },
          node_executions: [{
            node_execution_id: "schema-exec",
            node_id: "generate_image",
            node_ref: "ai.runninghub_text_to_image.v1",
            status: nodeStatus,
            input_snapshot: {},
            output_snapshot: {},
            attempt: 1,
          }],
          node_attempts: {},
          events: [],
        });
      }
      if (url === "/api/tasks/schema-task/stream?project_id=global" && method === "GET") {
        return Promise.resolve(new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }));
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await login();
    await userEvent.click(await screen.findByRole("button", { name: "打开 RunningHub Text To Image Test" }));

    expect(within(screen.getByRole("button", { name: "打开 RunningHub Text To Image Test" })).getByText("等待用户")).toBeInTheDocument();
    taskStatus = "succeeded";
    nodeStatus = "succeeded";
    streamController.enqueue(new TextEncoder().encode('event: task_succeeded\ndata: {"node_id":"generate_image"}\n\n'));

    await waitFor(() => {
      expect(within(screen.getByRole("button", { name: "打开 RunningHub Text To Image Test" })).getByText("成功")).toBeInTheDocument();
    });
    expect(within(screen.getByLabelText("任务运行详情")).getAllByText("成功").length).toBeGreaterThanOrEqual(2);
    streamController.close();
  });

  it("refreshes task detail after a failed interaction response", async () => {
    const baseFetch = mockFetch();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/tasks/task-1/interactions" && init?.method === "POST") {
        return jsonResponse({
          error: {
            code: "runninghub_text_to_image_request_failed",
            message: "RunningHub image request failed",
            details: {},
          },
        }, 500);
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await login();
    await userEvent.click(await screen.findByRole("button", { name: "打开 故事板生成" }));

    let detailReadCount = 0;
    await waitFor(() => {
      const detailReads = fetchMock.mock.calls.filter(([url, init]) =>
        url === "/api/tasks/task-1?project_id=global" && (init?.method ?? "GET") === "GET",
      );
      expect(detailReads.length).toBeGreaterThan(0);
      detailReadCount = detailReads.length;
    });

    expect(screen.getByRole("button", { name: /S2 选择图片/ })).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByRole("button", { name: "选择 第二张" }));

    expect(await screen.findByText(/RunningHub image request failed/)).toBeInTheDocument();
    await waitFor(() => {
      const detailReads = fetchMock.mock.calls.filter(([url, init]) =>
        url === "/api/tasks/task-1?project_id=global" && (init?.method ?? "GET") === "GET",
      );
      expect(detailReads.length).toBeGreaterThan(detailReadCount);
    });
  });

  it("keeps asset filtering in search and tags without exposing directories", async () => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:asset-thumbnail") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));

    expect(screen.queryByRole("tree", { name: "资产目录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "资产目录" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "集元数据" })).toBeInTheDocument();
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith("/api/assets/asset-1/thumbnail?")
          && String(url).includes("project_id=global")
          && String(url).includes("size=256"),
        ),
      ).toBe(true);
    });
    await userEvent.click(screen.getByRole("button", { name: "角色" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith("/api/assets/search?")
          && String(url).includes("scope=combined")
          && String(url).includes("project_id=global")
          && String(url).includes("tag_ids=tag-character")
          && String(url).includes("limit=72")
          && String(url).includes("offset=0"),
        ),
      ).toBe(true);
    });
  });

  it("opens asset images in a fullscreen zoom viewer", async () => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:asset-fullscreen") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    const card = await screen.findByRole("button", { name: "参考图" });
    await userEvent.click(within(card).getByRole("button", { name: "全屏查看图像" }));

    const viewer = await screen.findByRole("dialog", { name: "全屏查看 参考图" });
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith("/api/assets/asset-1/content?")
          && String(url).includes("project_id=global"),
        ),
      ).toBe(true);
    });
    expect(within(viewer).getAllByText("100%").length).toBeGreaterThan(0);

    fireEvent.wheel(within(viewer).getByAltText("参考图").parentElement as HTMLElement, { deltaY: -120 });
    expect(await within(viewer).findByText("112%")).toBeInTheDocument();

    fireEvent.mouseDown(viewer);
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "全屏查看 参考图" })).not.toBeInTheDocument();
    });
  });

  it("keeps the selected asset library scene when switching to the task workbench and back", async () => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:asset-thumbnail") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const { container } = render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    await userEvent.click(await screen.findByRole("button", { name: /全局参考\.png/ }));
    expect(await screen.findByRole("heading", { name: "全局参考.png" })).toBeInTheDocument();
    const detailPanel = container.querySelector(".asset-detail-panel") as HTMLElement;
    expect(detailPanel).toBeTruthy();

    const searchFetchCountBefore = fetchMock.mock.calls.filter(([url, init]) =>
      String(url).startsWith("/api/assets/search?") && (init?.method ?? "GET") === "GET",
    ).length;
    expect(searchFetchCountBefore).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: "任务工作台" }));
    expect(await screen.findByRole("button", { name: "创建任务" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));

    expect(screen.getByRole("heading", { name: "全局参考.png" })).toBeInTheDocument();
    expect(container.querySelector(".asset-detail-panel")).toBe(detailPanel);
    expect(fetchMock.mock.calls.filter(([url, init]) =>
      String(url).startsWith("/api/assets/search?") && (init?.method ?? "GET") === "GET",
    )).toHaveLength(searchFetchCountBefore);
  });

  it("batch selects and soft deletes assets from the asset library", async () => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:asset-thumbnail") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    expect(await screen.findByRole("button", { name: "参考图" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /全局参考\.png/ })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "批量选择" }));
    await userEvent.click(screen.getByLabelText("选择资产 参考图"));
    await userEvent.click(screen.getByLabelText("选择资产 全局参考.png"));
    await userEvent.click(screen.getByRole("button", { name: "批量软删除 2" }));

    const dialog = await screen.findByRole("dialog", { name: "批量软删除资产" });
    expect(within(dialog).getByText("参考图")).toBeInTheDocument();
    expect(within(dialog).getByText("全局参考.png")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "确认软删除" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url, init]) => url === "/api/assets/asset-1" && init?.method === "DELETE"),
      ).toBe(true);
      expect(
        fetchMock.mock.calls.some(([url, init]) => url === "/api/assets/asset-global" && init?.method === "DELETE"),
      ).toBe(true);
      expect(screen.getByText("已软删除 2 个资产。")).toBeInTheDocument();
    });
  });

  it("uses the project name in asset scope controls and supports project-only filtering", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));

    const combinedButton = await screen.findByRole("button", { name: "全局项目 + 全局" });
    const projectButton = screen.getByRole("button", { name: "全局项目资产" });
    const globalButton = screen.getByRole("button", { name: "全局资产" });
    expect(screen.queryByRole("button", { name: "当前项目 + 全局" })).not.toBeInTheDocument();
    expect(combinedButton).toHaveClass("asset-scope-button", "active-control");
    expect(projectButton).toHaveClass("asset-scope-button");
    expect(projectButton).not.toHaveClass("active-control");

    await userEvent.click(projectButton);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith("/api/assets/search?")
          && String(url).includes("scope=project")
          && String(url).includes("project_id=global")
          && String(url).includes("limit=72")
          && String(url).includes("offset=0"),
        ),
      ).toBe(true);
      expect(projectButton).toHaveClass("active-control");
      expect(combinedButton).not.toHaveClass("active-control");
      expect(globalButton).not.toHaveClass("active-control");
    });
  });

  it("uses a project dropdown and quick asset type filters", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    expect(screen.queryByRole("tree", { name: "资产目录" })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("资产项目"), "project-2");

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith("/api/assets/search?")
          && String(url).includes("scope=combined")
          && String(url).includes("project_id=project-2")
          && String(url).includes("limit=72")
          && String(url).includes("offset=0"),
        ),
      ).toBe(true);
    });

    await userEvent.click(screen.getByRole("button", { name: "角色" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).startsWith("/api/assets/search?")
          && String(url).includes("scope=combined")
          && String(url).includes("project_id=project-2")
          && String(url).includes("tag_ids=tag-character")
          && String(url).includes("limit=72")
          && String(url).includes("offset=0"),
        ),
      ).toBe(true);
    });
  });

  it("uploads files without requiring an asset directory", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    await userEvent.upload(screen.getByLabelText("上传文件"), new File(["fake image"], "uploaded.png", { type: "image/png" }));
    await userEvent.type(screen.getByLabelText("上传资产名称"), "资产库资产");
    await userEvent.click(screen.getByRole("button", { name: "上传到资产库" }));

    await waitFor(() => {
      const uploadCall = fetchMock.mock.calls.find(([url, init]) => url === "/api/assets/files" && init?.method === "POST");
      expect(uploadCall).toBeTruthy();
      const form = uploadCall?.[1]?.body as FormData;
      expect(form.get("collection_ids")).toBeNull();
      expect(form.get("name")).toBe("资产库资产");
    });
  });

  it("uploads files with LLM metadata completion from the asset library", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    await userEvent.upload(screen.getByLabelText("上传文件"), new File(["fake image"], "linchong.png", { type: "image/png" }));
    await userEvent.type(screen.getByLabelText("上传资产名称"), "林冲");
    await userEvent.clear(screen.getByLabelText("世界背景"));
    await userEvent.type(screen.getByLabelText("世界背景"), "水浒传");
    await userEvent.selectOptions(screen.getByLabelText("智能上传资产类型"), "character");
    await userEvent.click(screen.getByRole("button", { name: "智能上传并补全" }));

    await waitFor(() => {
      const uploadCall = fetchMock.mock.calls.find(([url, init]) => url === "/api/assets/files/intelligent" && init?.method === "POST");
      expect(uploadCall).toBeTruthy();
      const form = uploadCall?.[1]?.body as FormData;
      expect(form.get("name")).toBe("林冲");
      expect(form.get("world_background")).toBe("水浒传");
      expect(form.get("asset_type")).toBe("character");
    });
    expect(await screen.findByText("已智能上传并补全：林冲")).toBeInTheDocument();
  });

  it("uploads files with a user-defined asset name", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    await userEvent.upload(screen.getByLabelText("上传文件"), new File(["fake image"], "source-file.png", { type: "image/png" }));
    await userEvent.type(screen.getByLabelText("上传资产名称"), "主角立绘");
    await userEvent.click(screen.getByRole("button", { name: "上传到资产库" }));

    await waitFor(() => {
      const uploadCall = fetchMock.mock.calls.find(([url, init]) => url === "/api/assets/files" && init?.method === "POST");
      expect(uploadCall).toBeTruthy();
      const form = uploadCall?.[1]?.body as FormData;
      expect(form.get("name")).toBe("主角立绘");
    });
  });

  it("renames an existing asset from the asset detail panel", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    expect(await screen.findByRole("heading", { name: "参考图" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "重命名资产" }));
    const nameInput = screen.getByLabelText("资产名称");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "角色_林冲_默认");
    await userEvent.click(screen.getByRole("button", { name: "保存资产名称" }));

    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(([url, init]) => url === "/api/assets/asset-1" && init?.method === "PATCH");
      expect(patchCall).toBeTruthy();
      expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({ name: "角色_林冲_默认" });
      expect(screen.getByRole("heading", { name: "角色_林冲_默认" })).toBeInTheDocument();
      expect(
        fetchMock.mock.calls.some(([url, init]) =>
          url === "/api/assets/tags" && init?.method === "POST" && JSON.parse(String(init?.body)).name === "林冲",
        ),
      ).toBe(true);
      expect(
        fetchMock.mock.calls.some(([url, init]) =>
          url === "/api/assets/tags" && init?.method === "POST" && JSON.parse(String(init?.body)).name === "默认",
        ),
      ).toBe(true);
      expect(
        fetchMock.mock.calls.some(([url, init]) =>
          String(url).startsWith("/api/assets/asset-1/tags/") && init?.method === "POST",
        ),
      ).toBe(true);
    });
  });

  it("renders and saves asset metadata fields dynamically", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    expect(await screen.findByRole("heading", { name: "参考图" })).toBeInTheDocument();
    expect(screen.getByLabelText("metadata public_url")).toHaveValue("https://cdn.example.com/ref.png");
    const variantDescription = screen.getByLabelText("metadata variant_description");
    expect(variantDescription).toHaveValue("动态显示的变体描述");

    await userEvent.clear(variantDescription);
    await userEvent.type(variantDescription, "保存后的描述");
    await userEvent.click(screen.getByRole("button", { name: "保存字段" }));

    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(([url, init]) => url === "/api/assets/asset-1" && init?.method === "PATCH");
      expect(patchCall).toBeTruthy();
      expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
        metadata: expect.objectContaining({ variant_description: "保存后的描述" }),
      });
    });
  });

  it("does not expose manual text asset creation in the asset detail panel", async () => {
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));

    await screen.findByRole("group", { name: "资产操作" });
    expect(screen.getByLabelText("上传文件")).toBeInTheDocument();
    expect(screen.queryByText("文字资产名")).not.toBeInTheDocument();
    expect(screen.queryByText("文字内容")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "创建文字资产" })).not.toBeInTheDocument();
  });

  it("manages library tag filters and asset detail tag assignment", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    const tagToolbar = await screen.findByRole("toolbar", { name: "资产库标签操作" });
    const detailActions = await screen.findByRole("group", { name: "资产操作" });
    expect(within(detailActions).getByRole("link", { name: "预览资产" })).toHaveClass("asset-action-button");
    expect(within(detailActions).getByRole("button", { name: "复制引用" })).toHaveClass("asset-action-button");
    expect(within(detailActions).getByRole("button", { name: "下载" })).toHaveClass("asset-action-button");
    expect(within(detailActions).getByRole("button", { name: "软删除" })).toHaveClass("asset-action-button");
    expect(within(tagToolbar).queryByRole("button", { name: "重命名标签" })).not.toBeInTheDocument();
    expect(await screen.findByRole("group", { name: "当前资产标签" })).toHaveTextContent("角色");

    await userEvent.click(screen.getByLabelText("筛选标签 角色"));
    expect(within(tagToolbar).getByRole("button", { name: "删除标签" })).toBeDisabled();
    await userEvent.click(screen.getByLabelText("筛选标签 角色"));
    await userEvent.click(screen.getByLabelText("筛选标签 空标签"));
    expect(within(tagToolbar).getByRole("button", { name: "删除标签" })).toBeEnabled();
    await userEvent.click(within(tagToolbar).getByRole("button", { name: "删除标签" }));
    await userEvent.click(screen.getByRole("button", { name: "确认删除标签" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url, init]) =>
          url === "/api/assets/tags/tag-empty" && init?.method === "DELETE",
        ),
      ).toBe(true);
      expect(screen.queryByLabelText("筛选标签 空标签")).not.toBeInTheDocument();
    });

    await userEvent.click(within(tagToolbar).getByRole("button", { name: "新建标签" }));
    await userEvent.type(screen.getByLabelText("标签名称"), "场景参考");
    await userEvent.click(screen.getByRole("button", { name: "创建标签" }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([url, init]) => url === "/api/assets/tags" && init?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        scope: "project",
        project_id: "global",
        name: "场景参考",
      });
    });

    expect(await screen.findByLabelText("筛选标签 场景参考")).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "管理资产标签" }));
    const dialog = await screen.findByRole("dialog", { name: "管理资产标签" });
    await userEvent.type(within(dialog).getByLabelText("过滤标签"), "场景");
    await userEvent.click(within(dialog).getByLabelText("给资产贴标签 场景参考"));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url, init]) =>
          url === "/api/assets/asset-1/tags/tag-2" && init?.method === "POST",
        ),
      ).toBe(true);
    });

    await userEvent.clear(within(dialog).getByLabelText("过滤标签"));
    await userEvent.type(within(dialog).getByLabelText("过滤标签"), "角色");
    await userEvent.click(within(dialog).getByLabelText("取消资产标签 角色"));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url, init]) =>
          url === "/api/assets/asset-1/tags/tag-character" && init?.method === "DELETE",
        ),
      ).toBe(true);
      expect(within(dialog).queryByLabelText("取消资产标签 角色")).not.toBeInTheDocument();
    });
  });

  it("only offers scope-compatible tags when assigning a global asset", async () => {
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "资产库" }));
    await userEvent.click(await screen.findByRole("button", { name: /全局参考\.png/ }));
    await userEvent.click(screen.getByRole("button", { name: "管理资产标签" }));

    const dialog = await screen.findByRole("dialog", { name: "管理资产标签" });
    expect(within(dialog).getByLabelText("给资产贴标签 全局通用")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("给资产贴标签 角色")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("给资产贴标签 空标签")).not.toBeInTheDocument();
  });

  it("opens the control library tab and lists registered node controls", async () => {
    render(<App />);
    await login();

    await userEvent.click(screen.getByRole("button", { name: "控件库" }));

    expect(await screen.findByRole("heading", { name: "控件库" })).toBeInTheDocument();
    expect(screen.getByText("ui.choice.image_three.v1")).toBeInTheDocument();
    expect(screen.getByText("悬停放大")).toBeInTheDocument();
    expect(screen.getByText("items_path")).toBeInTheDocument();
    expect(screen.getByText(/node\.input/)).toBeInTheDocument();
    expect(screen.getByText(/minItems: 1/)).toBeInTheDocument();
    expect(screen.getByText("selected_id")).toBeInTheDocument();
    expect(screen.getByText("selected_item")).toBeInTheDocument();
  });
});
