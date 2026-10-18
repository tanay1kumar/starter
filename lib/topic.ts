// Topic search (milestone 5): which builders have a project like the searched one.
// Server only.
//
// Every project is a few chunks (summary + write-up sections, see scripts/embed.mjs).
// A project's similarity to the topic is its best chunk's cosine similarity; z says
// how far that stands above the other projects for the same topic, which keeps the
// thresholds in lib/scoring.ts meaningful for broad and narrow topics alike. With
// DATABASE_URL the scoring runs in Postgres + pgvector, else over the same vectors
// in data/embeddings.json. The query vector comes from the file when the topic was
// embedded ahead of time (every cached search's topic is), else from the same local model.

import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { topicStatus, type TopicHits } from "./scoring";

export interface EmbeddingsFile {
  version: 2;
  model: string;
  dtype: string;
  pooling: "cls" | "mean";
  dims: number;
  /** Chunk vectors are int8: value / scale. */
  scale: number;
  queryPrefix: string;
  chunks: { project: string; kind: string; v: string }[];
  queries: Record<string, { text: string; vector: number[] }>;
}

interface ProjectsFile {
  version: 1;
  projects: { id: string; name: string; builders: { id: string; share: number | null }[] }[];
}

export interface TopicResult {
  hits: TopicHits;
  /** Where the projects were scored. */
  source: "postgres" | "json";
  /** True when the query vector was embedded ahead of time. */
  cachedQuery: boolean;
}

const DATA = path.join(process.cwd(), "data");

async function readData<T>(file: string): Promise<T> {
  return JSON.parse(await readFile(path.join(DATA, file), "utf8")) as T;
}

interface Decoded {
  emb: EmbeddingsFile;
  vectors: Int8Array[];
  /** Each int8 vector's length: rounding leaves it slightly off unit length. */
  norms: Float64Array;
}

/** The embeddings file, parsed and decoded once per version on disk (it is several MB). */
let loaded: ({ mtime: number } & Decoded) | null = null;

async function embeddings(): Promise<Decoded> {
  const file = path.join(DATA, "embeddings.json");
  const mtime = (await stat(file)).mtimeMs;
  if (loaded?.mtime !== mtime) {
    const emb = JSON.parse(await readFile(file, "utf8")) as EmbeddingsFile;
    const vectors = emb.chunks.map((c) => new Int8Array(Buffer.from(c.v, "base64")));
    loaded = { mtime, emb, vectors, norms: Float64Array.from(vectors, (v) => Math.hypot(...v) || 1) };
  }
  return loaded;
}

export function queryKey(q: string): string {
  return createHash("sha1").update(q.replace(/\s+/g, " ").trim().toLowerCase()).digest("hex");
}

type Extractor = (texts: string[], opts: { pooling: string; normalize: boolean }) => Promise<{ tolist(): number[][] }>;
let extractor: Promise<Extractor> | null = null;

async function embedLive(q: string, emb: EmbeddingsFile): Promise<number[]> {
  if (!extractor) {
    extractor = (async () => {
      const { env, pipeline } = await import("@huggingface/transformers");
      env.cacheDir = path.join(process.cwd(), ".cache", "models");
      const make = pipeline as unknown as (task: string, model: string, opts: { dtype: string }) => Promise<Extractor>;
      return make("feature-extraction", emb.model, { dtype: emb.dtype });
    })();
    extractor.catch(() => (extractor = null));
  }
  const out = await (await extractor)([emb.queryPrefix + q], { pooling: emb.pooling, normalize: true });
  return out.tolist()[0];
}

const LEVEL = { met: 2, close: 1, miss: 0 };

/**
 * Each builder's best project, with its z-score among all projects' best
 * similarities: the one that gives them the strongest topic status (a project
 * they wrote little of counts less, see topicStatus), then the most similar.
 */
function hitsFrom(best: Map<string, number>, projects: ProjectsFile): TopicHits {
  const sims = [...best.values()];
  const mean = sims.reduce((a, b) => a + b, 0) / (sims.length || 1);
  const sd = Math.sqrt(sims.reduce((a, b) => a + (b - mean) ** 2, 0) / (sims.length || 1)) || 1;
  const hits: TopicHits = {};
  for (const p of projects.projects) {
    const s = best.get(p.id);
    if (s === undefined) continue;
    for (const b of p.builders) {
      const hit = { similarity: s, z: (s - mean) / sd, project: p.name, share: b.share };
      const h = hits[b.id];
      const d = h ? LEVEL[topicStatus(hit)] - LEVEL[topicStatus(h)] : 1;
      if (d > 0 || (d === 0 && s > h!.similarity)) hits[b.id] = hit;
    }
  }
  return hits;
}

/** Cosine similarity of every chunk, exactly as Postgres computes it from the renormalized vectors. */
function jsonBest(qv: number[], { emb, vectors, norms }: Decoded): Map<string, number> {
  const best = new Map<string, number>();
  emb.chunks.forEach((c, i) => {
    const v = vectors[i];
    let s = 0;
    for (let k = 0; k < v.length; k++) s += v[k] * qv[k];
    s /= norms[i];
    if (s > (best.get(c.project) ?? -Infinity)) best.set(c.project, s);
  });
  return best;
}

type Pool = import("pg").Pool;
let pool: Pool | null = null;

async function pgBest(qv: number[]): Promise<Map<string, number>> {
  if (!pool) {
    const { Pool } = await import("pg");
    pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 3, connectionTimeoutMillis: 5000 });
    pool.on("error", () => {}); // a dropped idle connection must not crash the server
  }
  // Exact scoring over every chunk (a few thousand rows): the z-score needs every project.
  const { rows } = await pool.query<{ project_id: string; similarity: number }>(
    `SELECT project_id, max(1 - (embedding <=> $1::vector)) AS similarity
     FROM talentdex.chunks
     GROUP BY project_id`,
    ["[" + qv.join(",") + "]"],
  );
  return new Map(rows.map((r) => [r.project_id, Number(r.similarity)]));
}

export async function topicHits(query: string): Promise<TopicResult> {
  const [decoded, projects] = await Promise.all([embeddings(), readData<ProjectsFile>("projects.json")]);
  const { emb } = decoded;
  const pre = emb.queries[queryKey(query)];
  const qv = pre ? pre.vector : await embedLive(query, emb);
  if (process.env.DATABASE_URL) {
    try {
      return { hits: hitsFrom(await pgBest(qv), projects), source: "postgres", cachedQuery: !!pre };
    } catch {
      // Database unreachable (venue wifi): the same vectors are in the JSON file.
    }
  }
  return { hits: hitsFrom(jsonBest(qv, decoded), projects), source: "json", cachedQuery: !!pre };
}
