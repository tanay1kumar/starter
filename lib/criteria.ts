// Search criteria: defaults, URL encoding, and the removable filter chips on screen 1.

import type { CSSProperties } from "react";
import { ICONS, TYPES } from "./design";
import { yearLabel } from "./format";
import { TYPE_KEYS, type Criteria, type TypeKey } from "./types";

/** The search shown in the design file. */
export const DEFAULT_CRITERIA: Criteria = {
  types: ["ml"],
  year: 3,
  location: "Toronto",
  winner: true,
  topic: null,
  topicQuery: null,
  text: "",
};

export function encodeCriteria(c: Criteria): string {
  const p = new URLSearchParams();
  if (c.types.length) p.set("types", c.types.join(","));
  if (c.year !== null) p.set("year", String(c.year));
  if (c.location) p.set("loc", c.location);
  if (c.winner) p.set("win", "1");
  if (c.topic) p.set("topic", c.topic);
  if (c.topic && c.topicQuery && c.topicQuery !== c.topic) p.set("tq", c.topicQuery);
  if (c.text) p.set("q", c.text);
  return p.toString();
}

/** Missing params mean "no search given": fall back to the design's search. */
export function decodeCriteria(p: URLSearchParams | null): Criteria {
  if (!p || ![...p.keys()].some((k) => ["types", "year", "loc", "win", "topic", "tq", "q"].includes(k))) {
    return { ...DEFAULT_CRITERIA };
  }
  const types = (p.get("types") || "")
    .split(",")
    .map((s) => s.trim())
    .filter((s): s is TypeKey => (TYPE_KEYS as string[]).includes(s))
    .slice(0, 2);
  const y = p.get("year");
  const year = y !== null && /^\d+$/.test(y) && +y >= 0 && +y <= 6 ? +y : null;
  const topic = p.get("topic") || null;
  return {
    types,
    year,
    location: p.get("loc") || null,
    winner: p.get("win") === "1",
    topic,
    topicQuery: topic ? p.get("tq") || topic : null,
    text: p.get("q") || "",
  };
}

export interface FilterChip {
  id: string;
  label: string;
  icon: string;
  style: CSSProperties;
}

const PLAIN: CSSProperties = { background: "#FFFFFF", color: "#2A1715" };

/** Chips in the design's order: type(s), year, location, winner, then topic. */
export function criteriaChips(c: Criteria): FilterChip[] {
  const chips: FilterChip[] = c.types.map((t) => ({
    id: "type:" + t,
    label: TYPES[t].label,
    icon: TYPES[t].icon,
    style: { background: TYPES[t].bg, color: TYPES[t].fg },
  }));
  if (c.year !== null) chips.push({ id: "year", label: yearLabel(c.year)!, icon: ICONS.year, style: PLAIN });
  if (c.location) chips.push({ id: "loc", label: c.location, icon: ICONS.loc, style: PLAIN });
  if (c.winner) chips.push({ id: "win", label: "Hackathon winner", icon: ICONS.win, style: PLAIN });
  if (c.topic) chips.push({ id: "topic", label: c.topic, icon: ICONS.topic, style: PLAIN });
  return chips;
}

/** The criteria still in effect after the recruiter removes chips. */
export function activeCriteria(c: Criteria, removed: Record<string, boolean>): Criteria {
  return {
    ...c,
    types: c.types.filter((t) => !removed["type:" + t]),
    year: removed.year ? null : c.year,
    location: removed.loc ? null : c.location,
    winner: removed.win ? false : c.winner,
    topic: removed.topic ? null : c.topic,
    topicQuery: removed.topic ? null : c.topicQuery,
  };
}
