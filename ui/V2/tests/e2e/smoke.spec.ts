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
