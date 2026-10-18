// Screen 0, rules parser: turns a recruiter's text into search criteria with
// keyword rules. Deterministic and offline (no network, no model). lib/parse.ts
// uses it when there is no cached Gemini answer and live Gemini is off or fails.
// It never sets a topic: project-experience searches need the Gemini parse.

import places from "@/data/places.json";
import type { Criteria, TypeKey } from "./types";

/** Keyword patterns per type, as regex sources. Each is matched case-insensitively as a whole word. */
const TYPE_WORDS: Record<TypeKey, string[]> = {
  ml: [
    "ml",
    "machine[\\s-]+learning",
    "ai",
    "gen[\\s-]?ai",
    "artificial[\\s-]+intelligence",
    "llms?",
    "deep[\\s-]+learning",
    "computer[\\s-]+vision",
    "nlp",
    "data[\\s-]+scien\\w*",
    "pytorch",
    "tensorflow",
    "scikit[\\s-]?learn",
    "sklearn",
    "hugging[\\s-]?face",
    "rag",
    "langchain",
  ],
  backend: [
    "back[\\s-]?ends?",
    "apis?",
    "server(?:s|less|[\\s-]side)?",
    "databases?",
    "devops",
    "infra(?:structure)?",
    "distributed[\\s-]+systems?",
    "(?:my|postgre|no)?sql(?:ite)?",
    "postgres",
    "graphql",
    "node(?:\\.?js)?",
    "express\\.?js",
    "django",
    "flask",
    "fastapi",
  ],
  frontend: [
    "front[\\s-]?ends?",
    "react(?:\\.?js)?",
    "web[\\s-]?dev(?:eloper|elopers|elopment)?",
    // Longer than mobile's "app developer", so "web app developer" stays frontend.
    "web[\\s-]+app(?:lication)?[\\s-]+dev(?:eloper|elopers|elopment)?",
    "javascript",
    "typescript",
    "vue(?:\\.?js)?",
    "svelte(?:kit)?",
    "angular",
    "next\\.?js",
    "html5?",
    "css3?",
    "tailwind(?:[\\s-]?css)?",
    "ui[\\s-]+(?:engineer|developer)s?",
  ],
  design: [
    // "designer", "designed" and "designing" count; "designated" does not.
    "design(?:s|ers?|ed|ing)?",
    "ux",
    "ui\\s*/\\s*ux",
    "figma",
    "product[\\s-]+design(?:ers?)?",
  ],
  mobile: [
    "mobile",
    "ios",
    "android",
    "swift(?:ui)?",
    "kotlin",
    "react[\\s-]+native",
    "flutter",
    "app[\\s-]+dev(?:eloper|elopers|elopment)?",
  ],
  hardware: [
    "hardware",
    "embedded",
    "firmware",
    "arduinos?",
    "esp[\\s-]?32",
    "raspberry[\\s-]+pis?",
    "robot(?:s|ics?)?",
    "iot",
    "pcbs?",
    "fpgas?",
    "sensors?",
    "microcontrollers?",
    "stm32",
    "electronics",
    "circuits?",
    "verilog",
    "vhdl",
  ],
};

/** Whole-word, case-insensitive. Lookarounds instead of \b so sources may start or end with punctuation. */
function word(src: string, flags = "gi"): RegExp {
  return new RegExp("(?<![\\w])(?:" + src + ")(?![\\w])", flags);
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

interface Hit {
  start: number;
  end: number;
}

const TYPE_RES: { type: TypeKey; re: RegExp }[] = (Object.keys(TYPE_WORDS) as TypeKey[]).flatMap((type) =>
  TYPE_WORDS[type].map((src) => ({ type, re: word(src) })),
);

/**
 * Up to two types, ordered by first mention. Overlapping keywords resolve to the
 * longest one, so "React Native" is Mobile only, not Frontend too.
 */
function findTypes(text: string): TypeKey[] {
  const hits: (Hit & { type: TypeKey })[] = [];
  for (const { type, re } of TYPE_RES) {
    for (const m of text.matchAll(re)) {
      const start = m.index ?? 0;
      hits.push({ type, start, end: start + m[0].length });
    }
  }
  hits.sort((a, b) => a.start - b.start || b.end - a.end);
  const types: TypeKey[] = [];
  let end = -1;
  for (const h of hits) {
    if (h.start < end) continue;
    end = h.end;
    if (!types.includes(h.type)) types.push(h.type);
    if (types.length === 2) break;
  }
  return types;
}

const ORDINALS: Record<string, number> = {
  "1st": 1,
  first: 1,
  "2nd": 2,
  second: 2,
  "3rd": 3,
  third: 3,
  "4th": 4,
  fourth: 4,
  final: 4,
  "5th": 5,
  fifth: 5,
};
const ORD = Object.keys(ORDINALS).join("|");

/** Year patterns. The earliest mention in the text wins. */
const YEAR_RULES: { re: RegExp; year: (m: RegExpExecArray) => number | null }[] = [
  // "3rd year", "third-year", "3rd or 4th year" (the first one listed wins), "final year"
  {
    re: word("(" + ORD + ")(?:\\s*-?\\s*(?:or|and|to|/|-|,)\\s*(?:" + ORD + "))*[\\s-]*(?:years?|yrs?)", "i"),
    year: (m) => ORDINALS[m[1].toLowerCase()] ?? null,
  },
  // "year 3", "Year-2"
  { re: word("year[\\s-]*([1-5])", "i"), year: (m) => Number(m[1]) },
  // "new grad", "recent graduates"
  { re: word("(?:new|recent|fresh)[\\s-]+grad(?:uate)?s?", "i"), year: () => 0 },
  // "any year", "all years": the recruiter does not mind
  { re: word("(?:any|all)[\\s-]+years?", "i"), year: () => null },
];

function findYear(text: string): number | null {
  let best: { index: number; year: number | null } | null = null;
  for (const rule of YEAR_RULES) {
    const m = rule.re.exec(text);
    if (m && (!best || m.index < best.index)) best = { index: m.index, year: rule.year(m) };
  }
  return best ? best.year : null;
}

/** Every city name and alias from data/places.json, as whole-word patterns. */
const CITY_RES: { city: string; re: RegExp }[] = places.cities.flatMap((c) =>
  [c.name, ...c.aliases].map((term) => ({
    city: c.name,
    re: word(escapeRe(term.trim()).replace(/\s+/g, "\\s+")),
  })),
);

/** The first city mentioned (the longest name wins at the same spot), or null. */
function findLocation(text: string): string | null {
  let best: (Hit & { city: string }) | null = null;
  for (const { city, re } of CITY_RES) {
    for (const m of text.matchAll(re)) {
      const start = m.index ?? 0;
      // "Hack the 6ix" is a hackathon, not a place to hire in.
      if (/hack\s+$/i.test(text.slice(Math.max(0, start - 8), start))) continue;
      const end = start + m[0].length;
      if (!best || start < best.start || (start === best.start && end > best.end)) best = { city, start, end };
      break;
    }
  }
  return best ? best.city : null;
}

const WINNER_RE = word(
  "winners?|won(?!['’]t)|winning|prizes?|awards?|awarded|placed|hackathon[\\s-]+wins?|(?:1st|2nd|3rd|first|second|third)[\\s-]+place",
  "i",
);

/** Turn free text ("ML intern, 3rd year, Toronto, has won a hackathon") into search criteria. */
export function parseRules(text: string): Criteria {
  const t = text.trim();
  return {
    types: findTypes(t),
    year: findYear(t),
    location: findLocation(t),
    winner: WINNER_RE.test(t),
    topic: null,
    topicQuery: null,
    text: t,
  };
}
