// Data contract shared by the UI (data/sample.json, data/builders.json) and the
// Python pipeline (pipeline/talentdex/output.py writes exactly this shape).

export type TypeKey = "ml" | "backend" | "frontend" | "design" | "mobile" | "hardware";

export const TYPE_KEYS: TypeKey[] = ["ml", "backend", "frontend", "design", "mobile", "hardware"];

/** Where a fact came from. These strings are shown on screen as-is. */
export type SourceName = "GitHub" | "Devpost" | "résumé" | "People Data Labs";

/**
 * A fact we either found (value + source) or did not (value null).
 * `looked` always lists where we looked, so a missing fact can say
 * "Not listed" and name the places we checked.
 */
export interface Fact<T> {
  value: T | null;
  source: SourceName | null;
  looked: SourceName[];
}

export interface Project {
  /** Devpost software slug. */
  id: string;
  name: string;
  /** Two-letter tile text, e.g. "Pp" for Pantry Pal. */
  abbr: string;
  /** The type this builder wrote most of on this project; null when no code was counted. */
  type: TypeKey | null;
  /** Hackathon name, e.g. "Hack the Valley X". */
  event: string;
  /** Devpost tagline, verbatim. */
  desc: string;
  /** First prize name, "" when none. */
  prize: string;
  prizes: string[];
  /** This builder pushed code commits (not README-only) after the event ended. */
  kept: boolean;
  /** Percent of the repo's counted added lines this builder wrote; null when no repo was analysed. */
  share: number | null;
  /** Devpost project page. */
  url: string;
  /** GitHub repo URL, when the project links one. */
  repo: string | null;
  /** Has a demo video or a working live URL. */
  demo: boolean;
  /** Attribution caveats, e.g. "possible shared laptop or squashed commits". */
  flags: string[];
  /** True when the project belongs to one of the scanned hackathons. */
  inScan: boolean;
}

export type IvTuple = [number, number, number, number, number, number];

export interface Builder {
  /** Devpost username. */
  id: string;
  name: string;
  /** Stable 4-digit id from a hash of the Devpost username. */
  dex: string;
  /** Top one or two EV types (second only if >= 60% of the first). */
  types: TypeKey[];

  // Field notes
  /** Short school name for cards, e.g. "UofT". */
  school: Fact<string>;
  schoolFull: Fact<string>;
  program: Fact<string>;
  /** e.g. "April 2028". */
  grad: Fact<string>;
  /** Year of study: 1..5, or 0 for graduated / new grad. */
  year: Fact<number>;
  city: Fact<string>;
  /** ISO date of the latest public GitHub push. */
  lastActive: Fact<string>;
  links: { devpost: string; github: string | null; linkedin: string | null };

  // Card numbers
  /** Devpost hackathon count. */
  hacks: number;
  /** Prizes on Devpost. */
  wins: number;
  /** Public GitHub repo count; null when no GitHub is linked on Devpost. */
  repos: number | null;

  // Words (Gemini, from verified facts only)
  /** <= 15 words. */
  why: string;
  /** <= 20 words. */
  sum: string;

  // Effort and traits
  ev: Record<TypeKey, number>;
  /** Projects that contributed most to each type, most first. */
  evFrom: Partial<Record<TypeKey, string[]>>;
  /** 0..31 in trait order: Ships demos, Wins, Ownership, Teamwork, Persistence, Documentation. */
  iv: IvTuple;
  /** Raw counts behind the IV evidence lines. */
  n: { demo: number; own: number; mates: number; kept: number; docs: number };
  /** Projects where this builder has counted code. */
  codeProjects: number;
  /** For each type, projects where this builder has counted code in that type. */
  typeProjects: Record<TypeKey, number>;
  /** Signature projects first. */
  projects: Project[];
}

export interface ScanHackathon {
  name: string;
  url: string;
  /** ISO datetimes of the submission window used for attribution. */
  start: string;
  end: string;
  /** Projects from this hackathon in the scan. */
  projects: number;
}

export interface ScanSummary {
  hackathons: ScanHackathon[];
  /** Total projects the scan checked; drives "{scanned} / {total}". */
  projectsChecked: number;
  reposChecked: number;
  commitsCounted: number;
  /** Builders in this dataset (people with verified, attributed code). */
  buildersFound: number;
  /**
   * Scanned projects in the order the cached run checked them, with the builders
   * each one surfaced (first find wins). The scan replay reveals a card when its
   * project comes up. Absent in the sample.
   */
  order?: { id: string; builders: string[] }[];
}

export interface Dataset {
  version: 1;
  source: "sample" | "real";
  generatedAt: string;
  scan: ScanSummary;
  builders: Builder[];
  /** Sample-only UI state from the design file (pre-shortlisted builders). */
  demo?: { shortlist: string[] };
}

/** What the recruiter is looking for. Built by screen 0, shown as chips on screen 1. */
export interface Criteria {
  /** 0-2 skill types. */
  types: TypeKey[];
  /** Year of study 1..5, 0 = new grad, null = any. */
  year: number | null;
  /** City name, null = anywhere. */
  location: string | null;
  /** Hackathon winner wanted. */
  winner: boolean;
  /** Short label for a project-experience search ("RAG pipeline"), shown as a chip; null = none. */
  topic: string | null;
  /** The topic spelled out as one sentence for the semantic search (acronyms expanded); null = none. */
  topicQuery: string | null;
  /** The recruiter's original text. */
  text: string;
}

export type CritStatus = "met" | "close" | "miss" | "unknown";
