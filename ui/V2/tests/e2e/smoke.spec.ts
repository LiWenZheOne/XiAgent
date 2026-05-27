import { expect, test } from "@playwright/test";

test("opens the XiAgent V2 login screen", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "登录 XiAgent" })).toBeVisible();
  await expect(page.getByLabel("用户名")).toBeVisible();
  await expect(page.getByLabel("密码")).toBeVisible();
});
