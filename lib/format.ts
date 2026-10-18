// Small text helpers used by the view models.

import type { Fact } from "./types";

export const NOT_LISTED = "Not listed";

export function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] || name;
}

export function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

/** Card/profile label for a year of study: 1..5 -> "Year 3", 0 -> "New grad". */
export function yearLabel(year: number | null): string | null {
  if (year === null || year === undefined) return null;
  return year === 0 ? "New grad" : "Year " + year;
}

/** "A, B, C" when three or fewer, else "A, B, 3 more" (design: src strings). */
export function listNames(names: string[] | undefined): string | null {
  if (!names || names.length === 0) return null;
  if (names.length <= 3) return names.join(", ");
  return names.slice(0, 2).join(", ") + ", " + (names.length - 2) + " more";
}

/** "today", "yesterday", "5 days ago", "1 week ago", "3 months ago". */
export function relativeDay(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  if (isNaN(then.getTime())) return iso;
  const day = 24 * 60 * 60 * 1000;
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(then)) / day);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return days + " days ago";
  if (days < 30) {
    const w = Math.floor(days / 7);
    return w === 1 ? "1 week ago" : w + " weeks ago";
  }
  if (days < 365) {
    const m = Math.floor(days / 30);
    return m === 1 ? "1 month ago" : m + " months ago";
  }
  const y = Math.floor(days / 365);
  return y === 1 ? "1 year ago" : y + " years ago";
}

/** "Looked in résumé, People Data Labs and Devpost." */
export function lookedIn(f: Fact<unknown>): string {
  const l = f.looked.length ? f.looked : ["Devpost"];
  const list = l.length === 1 ? l[0] : l.slice(0, -1).join(", ") + " and " + l[l.length - 1];
  return "Looked in " + list + ".";
}

/** Two-letter project tile text: "Pantry Pal" -> "Pp", "Sightline" -> "Si". */
export function abbr(name: string): string {
  const words = name.replace(/[^\p{L}\p{N}\s]/gu, " ").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const a = words[0][0].toUpperCase();
  const b = words.length > 1 ? words[1][0] : words[0][1] || "";
  return a + b.toLowerCase();
}

/** Make sure a sentence ends with punctuation before we append more text. */
export function sentence(s: string): string {
  const t = s.trim();
  if (!t) return t;
  return /[.!?…]$/.test(t) ? t : t + ".";
}

export function plural(n: number, one: string, many: string = one + "s"): string {
  return n === 1 ? one : many;
}
