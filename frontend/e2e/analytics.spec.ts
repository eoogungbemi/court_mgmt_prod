import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Analytics dashboard", () => {
  test("admin can access analytics", async ({ page }) => {
    await loginAs(page, "demo_admin", "Admin1234");
    await page.goto("/analytics");
    await expect(page).toHaveURL(/\/analytics/);
    await expect(page.getByRole("heading", { name: "Court Analytics" })).toBeVisible();
  });

  test("analytics shows total hearings stat card", async ({ page }) => {
    await loginAs(page, "demo_admin", "Admin1234");
    await page.goto("/analytics");
    await expect(page.getByText("Total Hearings Today")).toBeVisible();
  });

  test("attorney is redirected away from analytics", async ({ page }) => {
    await loginAs(page, "demo_attorney", "Attorney1234");
    await page.goto("/analytics");
    // Middleware sends unauthorized role to /queue
    await expect(page).toHaveURL(/\/queue/);
  });

  test("clerk can access analytics", async ({ page }) => {
    await loginAs(page, "demo_clerk", "Clerk1234");
    await page.goto("/analytics");
    await expect(page).toHaveURL(/\/analytics/);
  });
});
