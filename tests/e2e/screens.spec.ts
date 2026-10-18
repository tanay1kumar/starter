import { expect, test } from "@playwright/test";

// Milestone 1: one screenshot per screen, saved to docs/screenshots/ for a
// side-by-side check against design/shots/ (the design file rendered the same way).

const SHOTS = "docs/screenshots";

test("screen 0: search", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByPlaceholder("Describe who you're hiring, or paste a job posting.")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/screen-0-search.png`, fullPage: true });
});

test("screen 1: matches grid, scanning then done", async ({ page }) => {
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: "Scouting for you…" })).toBeVisible();
  await page.waitForTimeout(2300);
  await page.screenshot({ path: `${SHOTS}/screen-1-scanning.png` });
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Scan complete! \d+ projects checked\./)).toBeVisible();
  await page.waitForTimeout(800);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: `${SHOTS}/screen-1-grid.png`, fullPage: true });
});

test("screen 2: Dex entry, EVs, IVs and the draft", async ({ page }) => {
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
  await page.locator("article h2 button").first().click();
  await expect(page.getByRole("heading", { name: /fits your search/ })).toBeVisible();
  await page.waitForTimeout(1200);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: `${SHOTS}/screen-2-profile.png`, fullPage: true });

  await page.getByRole("button", { name: "IVs · Traits" }).click();
  await expect(page.getByText(/nature$/).first()).toBeVisible();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SHOTS}/screen-2-profile-iv.png`, fullPage: true });

  await page.getByRole("button", { name: /Say hi/ }).click();
  await expect(page.getByRole("heading", { name: /^Say hi to / })).toBeVisible();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SHOTS}/screen-2-draft.png` });
});
