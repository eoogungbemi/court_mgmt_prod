import { test, expect } from "@playwright/test";

test.describe("Public queue page", () => {
  test("loads without authentication", async ({ page }) => {
    await page.goto("/queue");
    await expect(page.getByRole("heading", { name: "Live Courtroom Queue" })).toBeVisible();
  });

  test("shows courtroom panels after data loads", async ({ page }) => {
    await page.goto("/queue");

    // Wait for spinner to disappear — data loaded
    await expect(page.getByTestId("spinner")).not.toBeVisible({ timeout: 15_000 }).catch(() => {
      // spinner may not render if data loads instantly; that's fine
    });

    // With demo seed there should be at least one courtroom card
    await expect(page.locator(".rounded-lg.bg-white").first()).toBeVisible({ timeout: 15_000 });
  });

  test("table headers are present once a room has hearings", async ({ page }) => {
    await page.goto("/queue");

    // Wait for at least one table to appear
    const table = page.locator("table").first();
    await expect(table).toBeVisible({ timeout: 15_000 });

    await expect(table.getByRole("columnheader", { name: "Time" })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "Status" })).toBeVisible();
  });
});
