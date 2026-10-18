// Screen 0: the recruiter's text -> search criteria. Today this is the keyword
// rules parser only. Milestone 4 adds a cached Gemini parser here, with the
// rules as the fallback; callers (app/api/parse) do not change.

import { parseRules } from "./parse-rules";
import type { Criteria } from "./types";

export interface ParseResult {
  criteria: Criteria;
  /** Which parser produced the criteria. */
  source: "rules";
}

export async function parseSearch(text: string): Promise<ParseResult> {
  return { criteria: parseRules(text), source: "rules" };
}
