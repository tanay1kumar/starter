import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

// Milestone 5: the topic search. "Built a RAG pipeline" is matched against every
// builder's project write-ups (Postgres + pgvector with DATABASE_URL, else the
// same vectors in data/embeddings.json). Needs DATA_SOURCE=real.

const SHOTS = "docs/screenshots/real";
const searches = JSON.parse(readFileSync("data/searches.json", "utf8")) as {
  entries: Record<string, { text: string; criteria: { topic: string | null; topicQuery: string | null } }>;
};
const rag = Object.values(searches.entries).find((e) => e.text === "Built a RAG pipeline")!;

test.beforeEach(async ({ request }) => {
  const { source } = await (await request.get("/api/scan")).json();
  test.skip(source !== "real", "topic search runs on the real data");
});

test("the RAG topic finds builders whose projects do retrieval", async ({ request }) => {
  const r = await request.post("/api/topic", { data: { query: rag.criteria.topicQuery } });
  expect(r.ok()).toBeTruthy();
  const body = await r.json();
  expect(["postgres", "json"]).toContain(body.source);
  expect(body.cachedQuery).toBe(true);
  const ranked = Object.entries(body.hits as Record<string, { z: number; similarity: number; project: string }>).sort(
    (a, b) => b[1].z - a[1].z,
  );
  expect(ranked.length).toBeGreaterThan(0);
  // A clear winner stands well above the rest of the projects.
  expect(ranked[0][1].z).toBeGreaterThan(2.5);
});

test("bad topic requests get a 400", async ({ request }) => {
  expect((await request.post("/api/topic", { data: { query: "" } })).status()).toBe(400);
  expect((await request.post("/api/topic", { data: { query: "x".repeat(501) } })).status()).toBe(400);
});

test("a RAG search ranks topic matches first and explains them", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("textbox").fill("Built a RAG pipeline");
  await page.getByRole("button", { name: /Start scan/ }).click();
  await page.waitForURL(/\/matches\?/);
  await expect(page.getByRole("heading", { name: /builders? found!/ })).toBeVisible({ timeout: 25_000 });
  await page.waitForTimeout(800);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: `${SHOTS}/screen-1-topic.png`, fullPage: false });
  await page.locator("article h2 button").first().click();
  const why = page.getByRole("heading", { name: /fits your search/ });
  await expect(why).toBeVisible();
  await expect(page.getByText(/^Built .+ \(wrote \d+%\)$/)).toBeVisible();
  await page.waitForTimeout(1000);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: `${SHOTS}/screen-2-topic.png`, fullPage: false });
});
