import { expect, test } from "@playwright/test";

// Milestone 4: screen 0 to screen 1 through the cached Gemini parse, and the scan
// replay. Runs on either dataset; the replay test needs DATA_SOURCE=real.

test("an example chip searches with Gemini's cached criteria", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "ML intern, Toronto" }).click();
  await expect(page.getByRole("textbox")).toHaveValue(/3rd-year student in Toronto/);
  await page.getByRole("button", { name: /Start scan/ }).click();
  await page.waitForURL(/\/matches\?/);
  const url = new URL(page.url());
  expect(url.searchParams.get("types")).toBe("ml");
  expect(url.searchParams.get("year")).toBe("3");
  expect(url.searchParams.get("loc")).toBe("Toronto");
  expect(url.searchParams.get("win")).toBe("1");
  for (const chip of ["ML / AI", "Year 3", "Toronto", "Hackathon winner"]) {
    await expect(page.getByRole("button", { name: "Remove filter " + chip })).toBeVisible();
  }
});

test("a project-experience search carries its topic to screen 1", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("textbox").fill("Built a RAG pipeline");
  await page.getByRole("button", { name: /Start scan/ }).click();
  await page.waitForURL(/\/matches\?/);
  const url = new URL(page.url());
  expect(url.searchParams.get("topic")).toBe("RAG pipeline");
  expect(url.searchParams.get("tq")).toMatch(/retrieval-augmented generation/i);
  await expect(page.getByRole("button", { name: "Remove filter RAG pipeline" })).toBeVisible();
});

test("the scan replay counts the real projects and reveals cards as it goes", async ({ page, request }) => {
  const { source, scan } = await (await request.get("/api/scan")).json();
  test.skip(source !== "real", "the sample has no crawl order");
  await page.goto("/matches");
  await expect(page.getByText(new RegExp(`\\d+ / ${scan.projectsChecked}$`))).toBeVisible();
  // Mid-scan, some cards are still silhouettes waiting for their project to come up.
  await page.waitForTimeout(1800);
  expect(await page.locator(".silhouette").count()).toBeGreaterThan(0);
  await expect(page.getByText(`Scan complete! ${scan.projectsChecked} projects checked.`)).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".silhouette")).toHaveCount(0);
});
