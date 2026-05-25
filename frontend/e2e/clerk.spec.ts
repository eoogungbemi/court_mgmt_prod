import { test, expect } from "@playwright/test";
import { loginAs, firstCourtroomId } from "./helpers";

test.describe("Clerk docket management", () => {
  test("clerk can view their room's live docket", async ({ page }) => {
    await loginAs(page, "demo_clerk", "Clerk1234");
    const roomId = await firstCourtroomId(page);
    await page.goto(`/clerk/${roomId}`);

    // Page heading contains the courtroom name from the API
    await expect(page.getByRole("heading").first()).toBeVisible();
    // Subheading confirms docket management context
    await expect(page.getByText("Live docket management")).toBeVisible();
  });

  test("queue cards render with hearing details", async ({ page }) => {
    await loginAs(page, "demo_clerk", "Clerk1234");
    const roomId = await firstCourtroomId(page);
    await page.goto(`/clerk/${roomId}`);

    // Wait for at least one hearing card (spinner disappears when data arrives)
    const card = page.locator(".rounded-lg.bg-white.shadow-sm").first();
    await expect(card).toBeVisible({ timeout: 15_000 });

    // Check-in buttons visible on the card
    await expect(card.getByRole("button", { name: "Attorney" })).toBeVisible();
    await expect(card.getByRole("button", { name: "Juvenile" })).toBeVisible();
  });

  test("Schedule Hearing button opens the modal", async ({ page }) => {
    await loginAs(page, "demo_clerk", "Clerk1234");
    const roomId = await firstCourtroomId(page);
    await page.goto(`/clerk/${roomId}`);

    await page.getByRole("button", { name: "Schedule Hearing" }).click();
    // Modal h2: "Schedule Hearing — {room name}"
    await expect(page.getByRole("heading", { name: /Schedule Hearing/ })).toBeVisible();
  });

  test("admin can also access the clerk docket view", async ({ page }) => {
    await loginAs(page, "demo_admin", "Admin1234");
    const roomId = await firstCourtroomId(page);
    await page.goto(`/clerk/${roomId}`);
    await expect(page.getByText("Live docket management")).toBeVisible();
  });
});
