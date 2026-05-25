import { Page } from "@playwright/test";

export async function loginAs(
  page: Page,
  username: string,
  password: string,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  // Wait for redirect away from /login
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 10_000,
  });
}

/** Returns the ID of the first courtroom from the API. */
export async function firstCourtroomId(page: Page): Promise<number> {
  const res  = await page.request.get("/api/courtrooms");
  const data = await res.json() as Array<{ id: number }>;
  return data[0].id;
}
