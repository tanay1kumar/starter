// Embeds every project in data/projects.json, and every cached search's topic
// (data/searches.json), into data/embeddings.json for the topic search.
//
//   node scripts/embed.mjs
//
// Runs locally with transformers.js (no API calls). The model is downloaded once
// from Hugging Face into .cache/models/ (gitignored).
//
// A project is several chunks: a summary (name, tagline, tools) and one chunk per
// section of its Devpost write-up. Sections about inspiration or future plans are
// left out, so "built X" matches what the team built, not what it hoped to. A
// project's similarity to a topic is its best chunk's. Vectors are unit length,
// so a dot product is the cosine similarity; chunk vectors are stored as int8
// (x 127, base64) to keep the file small. /api/topic reads the model settings
// from this file, so the queries it embeds always match the documents.

import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { env, pipeline } from "@huggingface/transformers";

const MODEL = "Snowflake/snowflake-arctic-embed-m-v1.5";
const DTYPE = "q8";
const POOLING = "cls";
const QUERY_PREFIX = "Represent this sentence for searching relevant passages: ";
const MAX_CHARS = 1500; // the model reads 512 tokens; the rest would be cut anyway
const BATCH = 16;
const SCALE = 127;
// Headings of sections that describe intent rather than what was built.
const SKIP = /inspiration|what'?s next|next steps?|future|roadmap|road map|motivation|the problem|why we|vision/i;

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
env.cacheDir = path.join(root, ".cache", "models");

const read = async (f) => JSON.parse(await readFile(path.join(root, "data", f), "utf8"));
const normalize = (s) => s.replace(/\s+/g, " ").trim().toLowerCase();
const queryKey = (q) => createHash("sha1").update(normalize(q)).digest("hex");

function unit(v) {
  const n = Math.hypot(...v) || 1;
  return v.map((x) => x / n);
}

function toInt8(v) {
  return Buffer.from(Int8Array.from(v, (x) => Math.max(-127, Math.min(127, Math.round(x * SCALE)))).buffer).toString("base64");
}

/** [kind, text] chunks for one project. */
function chunks(p) {
  const out = [["summary", `${p.name}. ${p.tagline}${p.builtWith.length ? "\nBuilt with " + p.builtWith.join(", ") + "." : ""}`]];
  for (const block of p.story.split("\n\n")) {
    const [first, ...rest] = block.split("\n");
    const heading = rest.length ? first : "";
    const body = rest.length ? rest.join(" ") : first;
    if (!body.trim() || SKIP.test(heading)) continue;
    out.push([heading || "about", `${p.name}: ${heading}\n${body}`.slice(0, MAX_CHARS)]);
  }
  return out;
}

const { projects } = await read("projects.json");
let searches = { entries: {} };
try {
  searches = await read("searches.json");
} catch {
  // no cached searches yet: projects only
}

const extract = await pipeline("feature-extraction", MODEL, { dtype: DTYPE });
async function embed(texts) {
  const out = [];
  for (let i = 0; i < texts.length; i += BATCH) {
    const t = await extract(texts.slice(i, i + BATCH), { pooling: POOLING, normalize: true });
    out.push(...t.tolist());
    if (texts.length > 500 && (i / BATCH) % 50 === 0) process.stdout.write(`  ${i}/${texts.length}\r`);
  }
  return out;
}

const t0 = Date.now();
const all = projects.flatMap((p) => chunks(p).map(([kind, text]) => ({ project: p.id, kind, text })));
const vectors = await embed(all.map((c) => c.text));
const topics = [
  ...new Set(
    Object.values(searches.entries)
      .map((e) => e.criteria.topicQuery)
      .filter(Boolean),
  ),
];
const qv = await embed(topics.map((q) => QUERY_PREFIX + q));

const doc = {
  version: 2,
  model: MODEL,
  dtype: DTYPE,
  pooling: POOLING,
  dims: vectors[0]?.length || 768,
  scale: SCALE,
  queryPrefix: QUERY_PREFIX,
  generatedAt: new Date().toISOString(),
  chunks: all.map((c, i) => ({ project: c.project, kind: c.kind, v: toInt8(unit(vectors[i])) })),
  queries: Object.fromEntries(topics.map((q, i) => [queryKey(q), { text: q, vector: unit(qv[i]).map((x) => Math.round(x * 1e5) / 1e5) }])),
};
await writeFile(path.join(root, "data", "embeddings.json"), JSON.stringify(doc) + "\n");
console.log(
  `embedded ${projects.length} projects as ${all.length} chunks and ${topics.length} topics in ${((Date.now() - t0) / 1000).toFixed(1)}s`,
);
