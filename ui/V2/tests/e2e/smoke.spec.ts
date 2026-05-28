import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

test("registers a user, enters the global project, and starts a task creation flow", async ({ page }) => {
  const username = `e2e_${Date.now()}`;
  const password = "secret-123";

  await page.goto("/");
  await page.getByRole("button", { name: "切换到注册" }).click();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);

  const projectsResponse = page.waitForResponse((response) =>
    response.url().includes("/api/projects") && response.request().method() === "GET",
  );
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: "任务工作台" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "登录 XiAgent" })).toHaveCount(0);

  const projectsPayload = await (await projectsResponse).json();
  expect(projectsPayload.items.some((project: { project_id?: string }) => project.project_id === "global")).toBe(true);
  await expect(page.getByLabel("当前项目")).toHaveValue("global");
  expect(await page.evaluate(() => localStorage.getItem("xiagent.v2.access_token"))).toBeTruthy();

  const currentUserResponse = page.waitForResponse((response) =>
    response.url().includes("/api/auth/me") && response.request().method() === "GET",
  );
  await page.reload();
  const currentUserResult = await currentUserResponse;
  expect(currentUserResult.status()).toBe(200);
  expect((await currentUserResult.json()).username).toBe(username);
  await expect(page.getByText(username, { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "登录 XiAgent" })).toHaveCount(0);
  await expect(page.getByLabel("当前项目")).toHaveValue("global");

  const workflowsResponse = page.waitForResponse((response) =>
    response.url().includes("/api/workflows") &&
    response.url().includes("project_id=global") &&
    response.request().method() === "GET",
  );
  await page.getByRole("button", { name: "创建任务" }).first().click();
  await expect(page.getByRole("heading", { name: "新建任务" })).toBeVisible();

  const workflowsPayload = await (await workflowsResponse).json();
  expect(workflowsPayload.items.length).toBeGreaterThan(0);
  const stableWorkflow = workflowsPayload.items.find(
    (item: { workflow?: { id?: string; name?: string } }) => item.workflow?.id === "deepseek_echo",
  );
  expect(stableWorkflow?.workflow?.name).toBeTruthy();
  await page.getByRole("button").filter({ hasText: stableWorkflow.workflow.name }).click();

  const taskResponse = page.waitForResponse((response) =>
    response.url().includes("/api/tasks") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "创建并运行" }).click();

  const taskPayload = await (await taskResponse).json();
  expect(taskPayload.project_id).toBe("global");
  await expect(page.getByLabel("任务运行详情")).toBeVisible();
  await expect(page.getByLabel("回答")).toBeVisible({ timeout: 15000 });
});

test("opens a RunningHub text-to-image task output in the original image preview", async ({ page }) => {
  const username = `viewer_${Date.now()}`;
  const password = "secret-123";

  await page.goto("/");
  await page.getByRole("button", { name: "切换到注册" }).click();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: "任务工作台" })).toBeVisible();

  seedRunningHubViewerTask(username);

  await page.getByRole("button", { name: "刷新任务" }).click();
  await page.getByRole("button", { name: /打开 Runninghub Text To Image Test/i }).click();
  await expect(page.getByLabel("任务运行详情")).toBeVisible();

  await page.getByRole("button", { name: "查看 RunningHub output" }).click();
  const dialog = page.getByRole("dialog", { name: "图片预览" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("img", { name: "RunningHub output" })).toBeVisible();
  await expect(dialog.getByRole("link", { name: "打开原图" })).toHaveAttribute("href", /^data:image\/svg/);
});

function seedRunningHubViewerTask(username: string) {
  const script = String.raw`
import datetime
import json
from pathlib import Path
import sqlite3
import sys

from xiagent.workflows.loader import load_workflow_file

username = sys.argv[1]
db = ".data/xiagent-e2e.sqlite3"
conn = sqlite3.connect(db)
conn.execute("pragma foreign_keys = on")
user = conn.execute("select user_id from users where username = ?", (username,)).fetchone()
if user is None:
    raise SystemExit(f"user not found: {username}")

now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
contract = load_workflow_file(Path("workflows/global/runninghub_text_to_image_test.workflow.yaml"))
workflow = contract["workflow"]
template_id = "template-viewer-" + username
task_id = "task-viewer-" + username
node_execution_id = "node-exec-viewer-" + username
image_url = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NDAiIGhlaWdodD0iMzYwIj4"
    "8cmVjdCB3aWR0aD0iNjQwIiBoZWlnaHQ9IjM2MCIgZmlsbD0iIzI1NjNlYiIvPjx0ZXh0IHg9IjMyMCIgeT0iMTgwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjZmZmIiBmb250LXNpemU9IjM2IiBmb250LWZhbWlseT0iQXJpYWwiPlJ1bm5pbmdIdWIgb3V0cHV0PC90ZXh0Pjwvc3ZnPg=="
)
output = {
    "image_url": image_url,
    "model": "runninghub-e2e",
    "usage": {"credits": 0},
    "results": [
        {
            "id": "generated",
            "url": image_url,
            "text": "RunningHub output",
            "output_type": "image",
        }
    ],
    "task_id": "rh-e2e",
    "status": "SUCCESS",
}
current_view = {"status": "succeeded", "current_node_id": "generate_image"}
conn.execute("delete from task_events where task_id = ?", (task_id,))
conn.execute("delete from node_executions where task_id = ?", (task_id,))
conn.execute("delete from tasks where task_id = ?", (task_id,))
conn.execute(
    """
    insert or replace into workflow_templates (
      template_id, workflow_id, version, scope, project_id, name, description,
      contract_json, status, created_at, updated_at
    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        template_id,
        workflow["id"],
        workflow["version"],
        workflow["scope"],
        workflow.get("project_id"),
        workflow["name"],
        workflow.get("description"),
        json.dumps(contract, ensure_ascii=False),
        "active",
        now,
        now,
    ),
)
conn.execute(
    """
    insert into tasks (
      task_id, workflow_template_id, workflow_id, workflow_version, user_id, project_id,
      input_json, status, current_view_json, created_at, started_at, finished_at, updated_at
    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        task_id,
        template_id,
        "runninghub_text_to_image_test",
        workflow["version"],
        user[0],
        "global",
        "{}",
        "succeeded",
        json.dumps(current_view, ensure_ascii=False),
        now,
        now,
        now,
        now,
    ),
)
conn.execute(
    """
    insert into node_executions (
      node_execution_id, task_id, node_id, node_ref, attempt, input_snapshot_json,
      output_snapshot_json, status, error_json, metadata_json, asset_refs_json,
      started_at, finished_at, created_at, updated_at
    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        node_execution_id,
        task_id,
        "generate_image",
        "ai.runninghub_text_to_image.v1",
        1,
        json.dumps({"prompt": "e2e image", "aspect_ratio": "1:1", "resolution": "1k"}),
        json.dumps(output, ensure_ascii=False),
        "succeeded",
        None,
        "{}",
        "[]",
        now,
        now,
        now,
        now,
    ),
)
conn.execute(
    "insert into task_events (event_id, task_id, event_type, payload_json, created_at) values (?, ?, ?, ?, ?)",
    ("event-viewer-" + username, task_id, "task_succeeded", "{}", now),
)
conn.commit()
conn.close()
`;
  execFileSync("python", ["-c", script, username], { cwd: "../.." });
}
