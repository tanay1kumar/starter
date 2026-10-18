// Criteria checks and the match score, exactly as defined in BUILD.md:
//   score = 100 * (0.6 * criteria + 0.4 * skill_fit)
//   criteria  = average over criteria rows (Matches 1, Close 0.5, otherwise 0)
//   skill_fit = mean over searched types of EV_t / 252
// Ranking is plain math; no model is ever asked to rank.

import { TYPES } from "./design";
import { lookedIn, ordinal, plural } from "./format";
import { CLOSE_KM, distanceKm, findCity } from "./places";
import type { Builder, CritStatus, Criteria, TypeKey } from "./types";

export interface CritRow {
  key: string;
  label: string;
  status: CritStatus;
  note: string;
  src: string;
}

/**
 * Topic search (lib/topic.ts): builder id -> their most similar project, its cosine
 * similarity, and z: how many standard deviations that stands above all projects
 * for the same topic.
 */
export type TopicHits = Record<string, { similarity: number; z: number; project: string }>;

/**
 * A topic match needs both: to stand out from the other projects (z), and to be
 * similar in absolute terms, so a topic no one built matches no one.
 * Calibrated on the real projects; see NOTES.md (milestone 5).
 */
export const TOPIC_MET = { z: 2.5, similarity: 0.36 };
export const TOPIC_CLOSE = { z: 2.0, similarity: 0.32 };

const VALUE: Record<CritStatus, number> = { met: 1, close: 0.5, miss: 0, unknown: 0 };

function typeRow(b: Builder, t: TypeKey): CritRow {
  const label = TYPES[t].label;
  const k = b.typeProjects[t] || 0;
  const n = b.codeProjects;
  let status: CritStatus = "miss";
  if (k > 0 && k * 2 >= n) status = "met";
  else if (k > 0) status = "close";
  const note =
    k > 0
      ? `${k} of ${n} ${n === 1 ? "project has" : "projects have"} ${label} code`
      : `No ${label} code in ${n} ${plural(n, "project")}`;
  return { key: "type:" + t, label, status, note, src: "GitHub" };
}

function yearRow(b: Builder, want: number): CritRow {
  const label = want === 0 ? "New grad" : "Year " + want;
  const v = b.year.value;
  if (v === null) {
    return { key: "year", label, status: "unknown", note: "Not listed. " + lookedIn(b.year), src: b.year.looked.join(" · ") };
  }
  let status: CritStatus = "miss";
  if (v === want) status = "met";
  else if (Math.abs(v - want) === 1) status = "close";
  const src = b.year.source || "Devpost";
  let note: string;
  if (v === 0) {
    const g = b.grad.value ? b.grad.value.replace(/^\w+\s+/, "") : null;
    note = g ? "Graduated in " + g : "Graduated";
  } else if (src === "People Data Labs" && b.grad.value) {
    note = `Graduating ${b.grad.value}, so ${ordinal(v)} year`;
  } else if (status === "met" && b.program.value) {
    note = `Lists ${ordinal(v)}-year ${b.program.value}`;
  } else {
    note = `Lists ${ordinal(v)} year`;
  }
  if (status === "close" && v !== 0 && want !== 0) note += v > want ? ", one year ahead" : ", one year behind";
  return { key: "year", label, status, note, src };
}

function locationRow(b: Builder, want: string): CritRow {
  const v = b.city.value;
  if (!v) {
    return { key: "loc", label: want, status: "unknown", note: "Not listed. " + lookedIn(b.city), src: b.city.looked.join(" · ") };
  }
  const src = b.city.source || "Devpost";
  const target = findCity(want);
  const here = findCity(v);
  const school = b.school.value;
  if ((target && here && target.name === here.name) || v.trim().toLowerCase() === want.trim().toLowerCase()) {
    const note = school ? `Studies at ${school}, ${here ? here.name : v}` : `Based in ${here ? here.name : v}`;
    return { key: "loc", label: want, status: "met", note, src };
  }
  if (target && here) {
    const km = distanceKm(target, here);
    const rounded = km < 20 ? Math.round(km) : Math.round(km / 5) * 5;
    if (km <= CLOSE_KM) return { key: "loc", label: want, status: "close", note: `${here.name}, about ${rounded} km from ${target.name}`, src };
    return { key: "loc", label: want, status: "miss", note: `${here.name}, about ${rounded} km from ${target.name}`, src };
  }
  return { key: "loc", label: want, status: "miss", note: `Based in ${v}`, src };
}

function winnerRow(b: Builder): CritRow {
  // Design copy: winc = wins ? [met, "N prize(s) in H hackathons"] : [miss, "No prizes yet"]
  if (b.wins >= 1) {
    return { key: "win", label: "Hackathon winner", status: "met", note: `${b.wins} prize${b.wins > 1 ? "s" : ""} in ${b.hacks} hackathons`, src: "Devpost" };
  }
  return { key: "win", label: "Hackathon winner", status: "miss", note: "No prizes yet", src: "Devpost" };
}

function topicRow(b: Builder, topic: string, hits: TopicHits | undefined): CritRow {
  if (!hits) {
    // The topic search didn't run (no embeddings, or it failed): say so rather than guess.
    return { key: "topic", label: topic, status: "unknown", note: "Couldn't check projects for this topic", src: "Devpost" };
  }
  const h = hits[b.id];
  let status: CritStatus = "miss";
  if (h && h.z >= TOPIC_MET.z && h.similarity >= TOPIC_MET.similarity) status = "met";
  else if (h && h.z >= TOPIC_CLOSE.z && h.similarity >= TOPIC_CLOSE.similarity) status = "close";
  const note =
    status === "met" ? `Built ${h!.project}, a close match` : status === "close" ? `${h!.project} is related` : "No project like this yet";
  return { key: "topic", label: topic, status, note, src: "Devpost" };
}

export interface Evaluation {
  rows: CritRow[];
  met: number;
  score: number;
  /** Has code in at least one searched type (or no type was searched). */
  found: boolean;
}

export function evaluate(b: Builder, c: Criteria, hits?: TopicHits): Evaluation {
  const rows: CritRow[] = [];
  for (const t of c.types) rows.push(typeRow(b, t));
  if (c.year !== null) rows.push(yearRow(b, c.year));
  if (c.location) rows.push(locationRow(b, c.location));
  if (c.winner) rows.push(winnerRow(b));
  if (c.topic) rows.push(topicRow(b, c.topic, hits));

  const criteria = rows.length ? rows.reduce((a, r) => a + VALUE[r.status], 0) / rows.length : 0;
  const fit = c.types.length ? c.types.reduce((a, t) => a + Math.min(1, (b.ev[t] || 0) / 252), 0) / c.types.length : null;

  let score: number;
  if (fit === null) score = 100 * criteria;
  else if (rows.length === 0) score = 100 * fit;
  else score = 100 * (0.6 * criteria + 0.4 * fit);

  // A builder is "found" when they have code in a searched type, or a project
  // like the searched topic. With neither searched, everyone in the dex counts.
  let found = true;
  if (c.types.length || c.topic) {
    const typeHit = c.types.some((t) => (b.typeProjects[t] || 0) > 0);
    const topicHit = !!c.topic && rows.some((r) => r.key === "topic" && (r.status === "met" || r.status === "close"));
    found = typeHit || topicHit;
  }
  return {
    rows,
    met: rows.filter((r) => r.status === "met").length,
    score: Math.round(score),
    found,
  };
}

/** Top one or two EV types; the second only if it is at least 60% of the first. */
export function cardTypes(ev: Record<TypeKey, number>): TypeKey[] {
  const sorted = (Object.keys(ev) as TypeKey[]).filter((k) => ev[k] > 0).sort((a, b) => ev[b] - ev[a]);
  if (sorted.length === 0) return [];
  if (sorted.length > 1 && ev[sorted[1]] >= 0.6 * ev[sorted[0]]) return [sorted[0], sorted[1]];
  return [sorted[0]];
}

export type SortKey = "match" | "wins" | "hacks";

export interface Ranked {
  b: Builder;
  e: Evaluation;
}

/** Best-match order: score, then wins, hackathons, name. */
export function rank(builders: Builder[], c: Criteria, hits?: TopicHits): Ranked[] {
  return builders
    .map((b) => ({ b, e: evaluate(b, c, hits) }))
    .filter((r) => r.e.found)
    .sort((x, y) => y.e.score - x.e.score || y.b.wins - x.b.wins || y.b.hacks - x.b.hacks || x.b.name.localeCompare(y.b.name));
}
