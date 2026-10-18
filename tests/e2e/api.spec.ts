import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

// Milestone 4: search parsing. The demo's searches are answered from the cached
// Gemini parses in data/searches.json; anything else falls back to the keyword
// rules, because the test server never has ALLOW_LIVE_GEMINI=1.

const demo = JSON.parse(readFileSync("data/demo-searches.json", "utf8")) as {
  examples: { label: string; text: string; type: string }[];
  more: string[];
};
const cache = JSON.parse(readFileSync("data/searches.json", "utf8")) as {
  entries: Record<string, { text: string; criteria: Record<string, unknown> }>;
};

const parse = (request: import("@playwright/test").APIRequestContext, text: string) =>
  request.post("/api/parse", { data: { text } });

test("every demo search is a cached Gemini parse", async ({ request }) => {
  const texts = [...demo.examples.map((e) => e.text), ...demo.more];
  for (const text of texts) {
    const r = await parse(request, text);
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(body.source, text).toBe("gemini");
    expect(body.cached, text).toBe(true);
    expect(body.criteria.text).toBe(text.trim());
    const entry = Object.values(cache.entries).find((e) => e.text === text.trim());
    expect(entry, text).toBeTruthy();
    expect({ ...body.criteria, text: undefined }).toEqual({ ...entry!.criteria, text: undefined });
  }
});

test("each example chip asks for its own type", async ({ request }) => {
  for (const ex of demo.examples) {
    const body = await (await parse(request, ex.text)).json();
    expect(body.criteria.types[0], ex.label).toBe(ex.type);
  }
});

test("case and spacing don't miss the cache", async ({ request }) => {
  const body = await (await parse(request, "  built   a RAG pipeline ")).json();
  expect(body.source).toBe("gemini");
  expect(body.criteria.topic).toBeTruthy();
  expect(body.criteria.topicQuery).toMatch(/retrieval/i);
});

test("an uncached search falls back to the rules parser offline", async ({ request }) => {
  const body = await (await parse(request, "Frontend developer in Ottawa, second year, React")).json();
  expect(body.source).toBe("rules");
  expect(body.cached).toBe(false);
  expect(body.criteria).toMatchObject({ types: ["frontend"], year: 2, location: "Ottawa", winner: false, topic: null });
});

test("bad requests get a plain-language 400", async ({ request }) => {
  const notJson = await request.post("/api/parse", { data: "hello", headers: { "content-type": "text/plain" } });
  expect(notJson.status()).toBe(400);
  const noText = await request.post("/api/parse", { data: { query: "ML" } });
  expect(noText.status()).toBe(400);
  const tooLong = await parse(request, "x".repeat(8001));
  expect(tooLong.status()).toBe(400);
  expect((await tooLong.json()).error).toMatch(/8,000 characters/);
});

test("the scan summary carries real totals", async ({ request }) => {
  const r = await request.get("/api/scan");
  expect(r.ok()).toBeTruthy();
  const { source, scan } = await r.json();
  expect(scan.projectsChecked).toBeGreaterThan(0);
  if (source === "real") {
    expect(scan.hackathons.length).toBeGreaterThan(0);
    expect(scan.buildersFound).toBeGreaterThan(0);
    expect(scan.order.length).toBe(scan.projectsChecked);
  }
});
