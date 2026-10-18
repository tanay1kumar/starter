// Screen 0: the recruiter's text -> search criteria.
//
// 1. A cached Gemini answer from data/searches.json (the demo's searches are cached ahead of time).
// 2. A live Gemini call, only when ALLOW_LIVE_GEMINI=1 and GEMINI_API_KEY is set; the answer is
//    added to the cache file when it is writable.
// 3. The keyword rules parser (offline), when neither is available or Gemini fails.

import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { geminiParse, GEMINI_MODEL } from "./parse-gemini";
import { parseRules } from "./parse-rules";
import type { Criteria } from "./types";

export type ParseSource = "gemini" | "rules";

export interface ParseResult {
  criteria: Criteria;
  /** Which parser produced the criteria. */
  source: ParseSource;
  /** True when a Gemini answer came from the cache rather than a live call. */
  cached: boolean;
}

interface CacheEntry {
  text: string;
  criteria: Omit<Criteria, "text">;
  model: string;
  at: string;
}

interface CacheFile {
  version: 1;
  entries: Record<string, CacheEntry>;
}

const CACHE_PATH = path.join(process.cwd(), "data", "searches.json");

/** Same text, same key: case and spacing don't matter. */
export function normalizeSearch(text: string): string {
  return text.replace(/\s+/g, " ").trim().toLowerCase();
}

export function searchKey(text: string): string {
  return createHash("sha1").update(normalizeSearch(text)).digest("hex");
}

async function readCache(): Promise<CacheFile> {
  try {
    const d = JSON.parse(await readFile(CACHE_PATH, "utf8"));
    if (d && d.version === 1 && d.entries && typeof d.entries === "object") return d as CacheFile;
  } catch {
    // no cache yet, or unreadable: treat as empty
  }
  return { version: 1, entries: {} };
}

async function remember(text: string, criteria: Criteria): Promise<void> {
  const cache = await readCache();
  const rest: Omit<Criteria, "text"> = {
    types: criteria.types,
    year: criteria.year,
    location: criteria.location,
    winner: criteria.winner,
    topic: criteria.topic,
    topicQuery: criteria.topicQuery,
  };
  cache.entries[searchKey(text)] = { text: text.trim(), criteria: rest, model: GEMINI_MODEL, at: new Date().toISOString() };
  const sorted = Object.fromEntries(Object.entries(cache.entries).sort(([a], [b]) => a.localeCompare(b)));
  try {
    await writeFile(CACHE_PATH, JSON.stringify({ version: 1, entries: sorted }, null, 1) + "\n");
  } catch {
    // read-only deploys keep serving the answer without caching it
  }
}

export function liveGeminiAllowed(): boolean {
  return process.env.ALLOW_LIVE_GEMINI === "1" && !!process.env.GEMINI_API_KEY;
}

export async function parseSearch(text: string): Promise<ParseResult> {
  const t = text.trim();
  if (t) {
    const hit = (await readCache()).entries[searchKey(t)];
    if (hit) return { criteria: { ...hit.criteria, text: t }, source: "gemini", cached: true };
    if (liveGeminiAllowed()) {
      try {
        const criteria = await geminiParse(t, process.env.GEMINI_API_KEY!);
        await remember(t, criteria);
        return { criteria, source: "gemini", cached: false };
      } catch {
        // fall through to the rules parser
      }
    }
  }
  return { criteria: parseRules(t), source: "rules", cached: false };
}
