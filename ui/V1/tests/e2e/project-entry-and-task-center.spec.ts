import { expect, test } from "@playwright/test";

test("project overview is the entry point before asset and task pages", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "项目总览" })).toBeVisible();
  await expect(page.getByText(/当前项目：/)).toBeVisible();

  await page.getByRole("button", { name: "资产" }).click();
  await expect(page.getByRole("heading", { name: "资产库" })).toBeVisible();
  await expect(page.getByRole("button", { name: "上传文件" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "资产筛选" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "资产详情" })).toBeVisible();

  await page.getByRole("button", { name: "任务" }).click();
  await expect(page.getByRole("heading", { name: "任务中心" })).toBeVisible();
  await expect(page.getByText("task_20260527_018")).toHaveCount(0);

  await page.getByRole("button", { name: "工作流" }).click();
  await expect(page.getByRole("heading", { name: "从工作流创建任务" })).toBeVisible();
  await expect(page.getByText("task_ui_")).toHaveCount(0);
});
