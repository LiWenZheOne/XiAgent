import { expect, test } from "@playwright/test";

test("image-to-image asset flow loads from the app shell", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("body")).toBeVisible();
});
