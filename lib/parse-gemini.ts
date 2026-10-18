// Screen 0, Gemini parser: the recruiter's text -> search criteria, as JSON
// constrained by a response schema. Only the recruiter's own text is sent (no
// candidate data). The demo never calls this live: lib/parse.ts serves cached
// answers from data/searches.json and only calls Gemini when ALLOW_LIVE_GEMINI=1.

import { findCity } from "./places";
import { TYPE_KEYS, type Criteria, type TypeKey } from "./types";

export const GEMINI_MODEL = "gemini-3.8-flash";
const ENDPOINT = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`;
const TIMEOUT_MS = 20_000;

export const SYSTEM = `You turn a recruiter's hiring text into search filters for a database of student hackathon builders.
Return JSON only, matching the schema.
- types: at most two of these skill types, the ones the role needs most, in order of importance:
  ml (ML / AI: models, LLMs, data science, computer vision), backend (servers, APIs, databases, infrastructure),
  frontend (web interfaces), design (UI/UX and visual design), mobile (iOS, Android, React Native, Flutter),
  hardware (embedded, firmware, robotics, electronics, PCBs). Empty when the text names no skill.
- year: the year of study asked for, 1 to 5; 0 for new grads or recent graduates; null when not stated.
  "Intern" or "co-op" alone does not state a year.
- location: the city the role is in, as a plain city name; null for remote or when no city is given.
- winner: true only when the text asks for hackathon winners or award winners.
- topic: only when the text asks for experience building a specific kind of project or product
  ("built a RAG pipeline", "computer vision on drones", "a budgeting app"), a short label of at most
  five words. Skills, languages, tools and parts alone (embedded C, sensors, PyTorch, APIs) are
  covered by types and are never a topic. Otherwise null.
- topicQuery: when topic is set, one plain sentence describing such a project for a semantic search,
  spelling out acronyms (RAG -> retrieval-augmented generation that answers questions from documents
  retrieved from a vector database); otherwise null.`;

const SCHEMA = {
  type: "OBJECT",
  properties: {
    types: { type: "ARRAY", items: { type: "STRING", enum: TYPE_KEYS } },
    year: { type: "INTEGER", nullable: true },
    location: { type: "STRING", nullable: true },
    winner: { type: "BOOLEAN" },
    topic: { type: "STRING", nullable: true },
    topicQuery: { type: "STRING", nullable: true },
  },
  required: ["types", "year", "location", "winner", "topic", "topicQuery"],
  propertyOrdering: ["types", "year", "location", "winner", "topic", "topicQuery"],
};

interface Raw {
  types?: unknown;
  year?: unknown;
  location?: unknown;
  winner?: unknown;
  topic?: unknown;
  topicQuery?: unknown;
}

function str(v: unknown, max: number): string | null {
  if (typeof v !== "string") return null;
  const s = v.replace(/\s+/g, " ").trim();
  return s ? s.slice(0, max) : null;
}

/** Keep only answers the UI can use; anything else becomes "not stated". */
export function toCriteria(raw: Raw, text: string): Criteria {
  const types: TypeKey[] = [];
  for (const t of Array.isArray(raw.types) ? raw.types : []) {
    if ((TYPE_KEYS as unknown[]).includes(t) && !types.includes(t as TypeKey)) types.push(t as TypeKey);
  }
  const y = raw.year;
  const year = typeof y === "number" && Number.isInteger(y) && y >= 0 && y <= 5 ? y : null;
  const place = str(raw.location, 60);
  const city = place ? findCity(place) : null;
  const topic = str(raw.topic, 60);
  return {
    types: types.slice(0, 2),
    year,
    location: city ? city.name : place,
    winner: raw.winner === true,
    topic,
    topicQuery: topic ? str(raw.topicQuery, 300) || topic : null,
    text: text.trim(),
  };
}

/** One live Gemini call. Throws on any failure; callers fall back to the rules parser. */
export async function geminiParse(text: string, apiKey: string): Promise<Criteria> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      // The key goes in a header, never in the URL, so it can't end up in logs.
      headers: { "content-type": "application/json", "x-goog-api-key": apiKey },
      body: JSON.stringify({
        systemInstruction: { parts: [{ text: SYSTEM }] },
        contents: [{ role: "user", parts: [{ text }] }],
        generationConfig: { temperature: 0, responseMimeType: "application/json", responseSchema: SCHEMA },
      }),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`Gemini answered ${res.status}`);
    const body = await res.json();
    const out = body?.candidates?.[0]?.content?.parts?.map((p: { text?: string }) => p.text || "").join("");
    if (!out) throw new Error("Gemini returned no text");
    return toCriteria(JSON.parse(out), text);
  } finally {
    clearTimeout(timer);
  }
}
