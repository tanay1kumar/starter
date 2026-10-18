// Caches Gemini's parse of every demo search (data/demo-searches.json) in
// data/searches.json, so the demo never calls Gemini live.
//
// Start a dev server that may call Gemini, then run this against it:
//   ALLOW_LIVE_GEMINI=1 npx next dev -p 3100
//   node scripts/cache-searches.mjs http://localhost:3100
//
// Texts already in the cache are answered from it (no Gemini call). Exits 1 if
// any text fell back to the keyword rules (Gemini off or failing).

import { readFile } from "node:fs/promises";

const base = (process.argv[2] || "http://localhost:3100").replace(/\/$/, "");
const demo = JSON.parse(await readFile(new URL("../data/demo-searches.json", import.meta.url), "utf8"));
const texts = [...demo.examples.map((e) => e.text), ...demo.more];

let failed = 0;
for (const text of texts) {
  const res = await fetch(base + "/api/parse", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const body = await res.json().catch(() => null);
  const label = text.split("\n")[0].slice(0, 60);
  if (!res.ok || !body?.criteria) {
    failed++;
    console.log(`FAIL  ${label}  (${res.status} ${body?.error || ""})`);
    continue;
  }
  if (body.source !== "gemini") failed++;
  const c = body.criteria;
  const parts = [
    c.types.join("+") || "-",
    c.year === null ? "any year" : c.year === 0 ? "new grad" : "year " + c.year,
    c.location || "anywhere",
    c.winner ? "winner" : "",
    c.topic ? `topic "${c.topic}"` : "",
  ].filter(Boolean);
  console.log(`${body.source}${body.cached ? " (cached)" : ""}  ${label}  ->  ${parts.join(", ")}`);
}
process.exit(failed ? 1 : 0);
