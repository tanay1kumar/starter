import { expect, test, type Page } from "@playwright/test";

// One screenshot per screen, saved to docs/screenshots/ for a side-by-side check
// against design/shots/ (the design file rendered the same way). With
// DATA_SOURCE=real the same run renders data/builders.json into docs/screenshots/real/.

const SHOTS = process.env.DATA_SOURCE === "real" ? "docs/screenshots/real" : "docs/screenshots";

// Stable pixels: finite animations (the FLIP morph, card pop-ins, the radar) are
// fast-forwarded to their end and endless ones (bob, shimmer, sweep) are held at
// their start, so a re-run saves the same picture. The mouse is parked so no
// hover state shows.
async function shot(page: Page, name: string, fullPage: boolean) {
  await page.mouse.move(0, 0);
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage, animations: "disabled" });
}

test("screen 0: search", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByPlaceholder("Describe who you're hiring, or paste a job posting.")).toBeVisible();
  // The "Scanning N projects" line arrives with /api/scan; wait so every run shows it.
  await expect(page.getByText(/^Scanning \d+ projects/)).toBeVisible();
  await shot(page, "screen-0-search", true);
});

test("screen 1: matches grid, scanning then done", async ({ page }) => {
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: "Scouting for you…" })).toBeVisible();
  // Mid-scan on purpose: the replay's timing decides which cards are out yet.
  await page.waitForTimeout(2300);
  await shot(page, "screen-1-scanning", false);
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Scan complete! \d+ projects checked\./)).toBeVisible();
  await shot(page, "screen-1-grid", true);
});

test("screen 2: Dex entry, EVs, IVs and the draft", async ({ page }) => {
  await page.goto("/matches");
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 20_000 });
  await page.locator("article h2 button").first().click();
  await expect(page.getByRole("heading", { name: /fits your search/ })).toBeVisible();
  await shot(page, "screen-2-profile", true);

  await page.getByRole("button", { name: "IVs · Traits" }).click();
  await expect(page.getByText(/nature$/).first()).toBeVisible();
  await shot(page, "screen-2-profile-iv", true);

  await page.getByRole("button", { name: /Say hi/ }).click();
  await expect(page.getByRole("heading", { name: /^Say hi to / })).toBeVisible();
  // Opening the draft moves focus into it, which can scroll the page; shoot from the top as before.
  await page.evaluate(() => window.scrollTo(0, 0));
  await shot(page, "screen-2-draft", false);
});
