import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Login page", () => {
  test("shows error on invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username").fill("nobody");
    await page.getByLabel("Password").fill("wrongpass");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.locator("p.text-red-700")).toBeVisible();
    expect(page.url()).toContain("/login");
  });

  test("admin login redirects to /admin", async ({ page }) => {
    await loginAs(page, "demo_admin", "Admin1234");
    await expect(page).toHaveURL(/\/admin/);
  });

  test("clerk login redirects away from /login", async ({ page }) => {
    // Clerk home is /clerk which has no index page, but the redirect itself
    // proves login succeeded and the middleware accepted the role.
    await page.goto("/login");
    await page.getByLabel("Username").fill("demo_clerk");
    await page.getByLabel("Password").fill("Clerk1234");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
      timeout: 10_000,
    });
    expect(page.url()).not.toContain("/login");
  });

  test("unauthenticated visit to /admin redirects to /login", async ({ page }) => {
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("attorney is redirected to /queue when visiting /admin", async ({ page }) => {
    await loginAs(page, "demo_attorney", "Attorney1234");
    await page.goto("/admin");
    // middleware sends unauthorized role to /queue
    await expect(page).toHaveURL(/\/queue/);
  });
});
