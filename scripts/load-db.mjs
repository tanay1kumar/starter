// Loads the cached pipeline output into Postgres + pgvector (Tiger Data) for the
// topic search: builders, their projects, each project's embedded chunks, and who
// built what.
//
//   node scripts/load-db.mjs            (DATABASE_URL from keys.env or the shell)
//
// Reads data/builders.json, data/projects.json and data/embeddings.json. Every
// load replaces the talentdex schema's tables in one transaction. /api/topic
// scores every chunk exactly (the z-score needs all projects), which takes a few
// milliseconds at this size, so there is no approximate (HNSW) index. Without
// DATABASE_URL the app searches the same vectors in data/embeddings.json instead.

import { readFile } from "node:fs/promises";
import path from "node:path";
import { config } from "dotenv";
import pg from "pg";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
config({ path: path.join(root, "keys.env"), quiet: true });

const url = process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL is not set (keys.env or the shell), so there is nothing to load into.");
  process.exit(1);
}

const read = async (f) => JSON.parse(await readFile(path.join(root, "data", f), "utf8"));
const [dataset, { projects }, emb] = await Promise.all([read("builders.json"), read("projects.json"), read("embeddings.json")]);

const builders = dataset.builders.map((b) => ({ id: b.id, name: b.name, data: b }));
const ids = new Set(builders.map((b) => b.id));
const rows = projects.map((p) => ({
  id: p.id,
  name: p.name,
  event: p.event,
  tagline: p.tagline,
  built_with: p.builtWith,
  story: p.story,
  url: p.url,
}));
const known = new Set(rows.map((p) => p.id));
/** int8 (base64) -> unit-length floats, as pgvector text. */
function vector(b64) {
  const v = Array.from(new Int8Array(Buffer.from(b64, "base64")), (x) => x / emb.scale);
  const n = Math.hypot(...v) || 1;
  return "[" + v.map((x) => (x / n).toFixed(5)).join(",") + "]";
}
const chunks = emb.chunks.filter((c) => known.has(c.project)).map((c) => ({ project_id: c.project, kind: c.kind, embedding: vector(c.v) }));
const links = projects.flatMap((p) =>
  p.builders.filter((b) => ids.has(b.id)).map((b) => ({ builder_id: b.id, project_id: p.id, share: b.share })),
);

const client = new pg.Client({ connectionString: url });
await client.connect();
try {
  await client.query("CREATE EXTENSION IF NOT EXISTS vector");
  await client.query("BEGIN");
  await client.query("CREATE SCHEMA IF NOT EXISTS talentdex");
  await client.query("DROP TABLE IF EXISTS talentdex.chunks, talentdex.builder_projects, talentdex.projects, talentdex.builders");
  await client.query(`CREATE TABLE talentdex.builders (
    id text PRIMARY KEY,
    name text NOT NULL,
    data jsonb NOT NULL
  )`);
  await client.query(`CREATE TABLE talentdex.projects (
    id text PRIMARY KEY,
    name text NOT NULL,
    event text NOT NULL,
    tagline text NOT NULL,
    built_with text[] NOT NULL,
    story text NOT NULL,
    url text NOT NULL
  )`);
  await client.query(`CREATE TABLE talentdex.chunks (
    id serial PRIMARY KEY,
    project_id text NOT NULL REFERENCES talentdex.projects (id) ON DELETE CASCADE,
    kind text NOT NULL,
    embedding vector(${Number(emb.dims)}) NOT NULL
  )`);
  await client.query(`CREATE TABLE talentdex.builder_projects (
    builder_id text NOT NULL REFERENCES talentdex.builders (id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES talentdex.projects (id) ON DELETE CASCADE,
    share smallint,
    PRIMARY KEY (builder_id, project_id)
  )`);
  await client.query(
    `INSERT INTO talentdex.builders (id, name, data)
     SELECT r.id, r.name, r.data FROM jsonb_to_recordset($1::jsonb) AS r(id text, name text, data jsonb)`,
    [JSON.stringify(builders)],
  );
  await client.query(
    `INSERT INTO talentdex.projects (id, name, event, tagline, built_with, story, url)
     SELECT r.id, r.name, r.event, r.tagline, ARRAY(SELECT jsonb_array_elements_text(r.built_with)), r.story, r.url
     FROM jsonb_to_recordset($1::jsonb)
       AS r(id text, name text, event text, tagline text, built_with jsonb, story text, url text)`,
    [JSON.stringify(rows)],
  );
  await client.query(
    `INSERT INTO talentdex.chunks (project_id, kind, embedding)
     SELECT r.project_id, r.kind, r.embedding::vector
     FROM jsonb_to_recordset($1::jsonb) AS r(project_id text, kind text, embedding text)`,
    [JSON.stringify(chunks)],
  );
  await client.query(
    `INSERT INTO talentdex.builder_projects (builder_id, project_id, share)
     SELECT r.builder_id, r.project_id, r.share
     FROM jsonb_to_recordset($1::jsonb) AS r(builder_id text, project_id text, share smallint)`,
    [JSON.stringify(links)],
  );
  await client.query("CREATE INDEX ON talentdex.chunks (project_id)");
  await client.query("CREATE INDEX ON talentdex.builder_projects (project_id)");
  await client.query("COMMIT");
  await client.query("ANALYZE talentdex.builders, talentdex.projects, talentdex.chunks, talentdex.builder_projects");
  console.log(
    `loaded ${builders.length} builders, ${rows.length} projects, ${chunks.length} chunks (${emb.dims}-d), ${links.length} builder-project links`,
  );
} catch (e) {
  await client.query("ROLLBACK").catch(() => {});
  console.error("load failed:", e.message);
  process.exitCode = 1;
} finally {
  await client.end();
}
