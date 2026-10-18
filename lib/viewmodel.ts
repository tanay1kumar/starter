// View models for screens 1 and 2: a TypeScript port of the design file's
// renderVals() and profile(). Components only render what these return.

import type { CSSProperties } from "react";
import { criteriaChips, type FilterChip } from "./criteria";
import { AXES, ICONS, NATURES, STATUS, TRAIT_LABELS, TYPES, avatar, judge, shade, type AvatarShape } from "./design";
import { NOT_LISTED, firstName, listNames, lookedIn, relativeDay, sentence, yearLabel } from "./format";
import { rank, type Evaluation, type Ranked, type SortKey, type TopicHits } from "./scoring";
import type { Builder, CritStatus, Criteria, Dataset, TypeKey } from "./types";

// Scan replay timing, from the design: a 60 ms tick, 500 ms start delay, done at tick 76.
export const SCAN_TICKS = 76;
export const TICK_MS = 60;
export const START_DELAY_MS = 500;
/** Cards that "appear" one by one during the scan (design: 9, one every 7 ticks). */
export const ANIMATED_CARDS = 9;
/** Cards rendered before "Show more". */
export const PAGE_SIZE = 24;

export type TabKey = "all" | TypeKey;

export interface DexState {
  tick: number;
  filter: TabKey;
  sort: SortKey;
  starred: Record<string, boolean>;
  seen: Record<string, boolean>;
  removed: Record<string, boolean>;
  open: string | null;
  showDraft: boolean;
  copied: boolean;
  burst: string | null;
  tab: "ev" | "iv";
  limit: number;
}

export function initialState(starred: Record<string, boolean> = {}): DexState {
  return {
    tick: 0,
    filter: "all",
    sort: "match",
    starred,
    seen: {},
    removed: {},
    open: null,
    showDraft: false,
    copied: false,
    burst: null,
    tab: "ev",
    limit: PAGE_SIZE,
  };
}

export interface ChipVM {
  label: string;
  icon: string;
  style: CSSProperties;
}

export interface CardVM {
  id: string;
  name: string;
  dex: string;
  dexNum: string;
  score: number;
  hacks: number;
  wins: number;
  repos: number | null;
  why: string;
  type: TypeKey;
  bg: string;
  fg: string;
  meta: string;
  dash: string;
  scoreLabel: string;
  chips: ChipVM[];
  av: AvatarShape;
  revealed: boolean;
  avClass: string;
  seen: boolean;
  dexStyle: CSSProperties;
  starred: boolean;
  starLabel: string;
  starFill: string;
  starStroke: string;
  bursting: boolean;
}

export interface TabVM {
  key: TabKey;
  label: string;
  icon: string;
  count: number;
  dot: string;
  pressed: boolean;
  style: CSSProperties;
}

export interface FilterVM extends FilterChip {
  removeLabel: string;
}

export interface GridVM {
  headline: string;
  filters: FilterVM[];
  anyRemoved: boolean;
  sort: SortKey;
  scanning: boolean;
  done: boolean;
  phase: string;
  scanned: number;
  total: number;
  progress: string;
  tabs: TabVM[];
  cards: CardVM[];
  skeletons: number;
  noneVisible: boolean;
  noneFound: boolean;
  moreCount: number;
  starCount: number;
  seenCount: number;
}

export interface CritVM {
  key: string;
  label: string;
  note: string;
  src: string;
  status: string;
  bg: string;
  fg: string;
  icon: string;
}

export interface RadarDot {
  x: string;
  y: string;
  r: number;
  fill: string;
}

export interface RadarVM {
  points: string;
  dots: RadarDot[];
  /** Value per axis, e.g. v.ml = 252. */
  v: Record<TypeKey, number>;
  /** Label colour per axis (muted when zero). */
  f: Record<TypeKey, string>;
}

export interface EvRowVM {
  key: TypeKey;
  label: string;
  value: number;
  fg: string;
  bg: string;
  icon: string;
  src: string;
}

export interface IvTileVM {
  label: string;
  value: number;
  judge: string;
  judgeStyle: CSSProperties;
  evidence: string;
}

export interface NoteVM {
  label: string;
  value: string;
  missing: boolean;
  /** "Looked in ..." when missing, otherwise the source name. */
  hint: string;
}

export interface LinkVM {
  label: string;
  href: string | null;
}

export interface ProjectVM {
  id: string;
  name: string;
  abbr: string;
  event: string;
  desc: string;
  prize: string;
  hasPrize: boolean;
  kept: boolean;
  bg: string;
  fg: string;
  share: string;
  url: string;
  repo: string | null;
  flags: string[];
}

export interface ProfileVM {
  id: string;
  name: string;
  first: string;
  dex: string;
  dexNum: string;
  fg: string;
  bg: string;
  av: AvatarShape;
  meta: string;
  chips: ChipVM[];
  sum: string;
  score: number;
  scoreLabel: string;
  dash: string;
  starred: boolean;
  shortLabel: string;
  shortStyle: CSSProperties;
  starFill: string;
  bursting: boolean;
  crits: CritVM[];
  metLabel: string;
  metStyle: CSSProperties;
  radar: RadarVM;
  radarLabel: string;
  evRows: EvRowVM[];
  hasZeros: boolean;
  zeros: string;
  evTotal: number;
  trainedLabel: string;
  trainedStyle: CSSProperties;
  ivTiles: IvTileVM[];
  ivPopulation: number;
  natureName: string;
  natureLine: string;
  notes: NoteVM[];
  links: LinkVM[];
  verify: string;
  projCount: string;
  projects: ProjectVM[];
  draftSubject: string;
  draftBody: string;
  backLabel: string;
  pos: string;
  prevLabel: string;
  nextLabel: string;
  prevAria: string;
  nextAria: string;
  noPrev: boolean;
  noNext: boolean;
  prevId: string | null;
  nextId: string | null;
}

export interface Ctx {
  data: Dataset;
  /** Criteria still in effect (chips not removed). */
  criteria: Criteria;
  /** The full search, used to draw the chips. */
  search: Criteria;
  accent: string;
  hits?: TopicHits;
  now?: Date;
}

const RING_SMALL = 2 * Math.PI * 17;
const RING_LARGE = 2 * Math.PI * 29;

function chipsFor(types: TypeKey[]): ChipVM[] {
  return types.map((k) => ({ label: TYPES[k].label, icon: TYPES[k].icon, style: { background: TYPES[k].bg, color: TYPES[k].fg } }));
}

function topType(b: Builder): TypeKey {
  if (b.types.length) return b.types[0];
  const best = AXES.slice().sort((x, y) => (b.ev[y] || 0) - (b.ev[x] || 0))[0];
  return best;
}

/** "School · Year · City", skipping parts that are not listed. */
function metaLine(parts: (string | null)[]): string {
  const have = parts.filter((p): p is string => !!p);
  return have.length ? have.join(" · ") : "School, year and city not listed";
}

function appearAt(i: number): number {
  return i < ANIMATED_CARDS ? 7 * (i + 1) : SCAN_TICKS - 6;
}

export interface Derived {
  ranked: Ranked[];
  grid: GridVM;
  /** Revealed, visible builders in grid order: what prev/next walks through. */
  order: Ranked[];
}

export function deriveGrid(s: DexState, ctx: Ctx): Derived {
  const { data, criteria, search, accent } = ctx;
  const accentDark = shade(accent, 0.24);
  const ranked = rank(data.builders, criteria, ctx.hits);
  const total = Math.max(1, data.scan.projectsChecked);
  const tick = s.tick;

  const pos: Record<string, number> = {};
  ranked.forEach((r, i) => (pos[r.b.id] = i));
  const shownList = ranked.filter((_, i) => tick >= appearAt(i));
  const isRevealed = (r: Ranked) => tick >= appearAt(pos[r.b.id]) + 6;
  const done = tick >= SCAN_TICKS;

  const counts: Partial<Record<TypeKey, number>> = {};
  shownList.forEach((r) => r.b.types.forEach((k) => (counts[k] = (counts[k] || 0) + 1)));
  const tabKeys: TabKey[] = ["all", ...AXES.filter((k) => counts[k])];
  const tabs: TabVM[] = tabKeys.map((k) => {
    const on = k === s.filter;
    return {
      key: k,
      label: k === "all" ? "All" : TYPES[k].label,
      icon: k === "all" ? ICONS.all : TYPES[k].icon,
      count: k === "all" ? shownList.length : counts[k] || 0,
      dot: on ? "#FFFFFF" : k === "all" ? accent : TYPES[k].fg,
      pressed: on,
      style: on
        ? { background: accent, color: "#FFFFFF", boxShadow: "0 4px 0 " + accentDark }
        : { background: "#FFFFFF", color: "#2A1715", boxShadow: "0 4px 0 rgba(42,23,21,.1)" },
    };
  });

  const visible = s.filter === "all" ? shownList.slice() : shownList.filter((r) => r.b.types.includes(s.filter as TypeKey));
  if (s.sort === "wins") visible.sort((a, b) => b.b.wins - a.b.wins || b.e.score - a.e.score);
  if (s.sort === "hacks") visible.sort((a, b) => b.b.hacks - a.b.hacks || b.e.score - a.e.score);

  const cards: CardVM[] = visible.slice(0, s.limit).map(({ b, e }) => {
    const k = topType(b);
    const t = TYPES[k];
    const on = !!s.starred[b.id];
    const rev = isRevealed({ b, e });
    const wasSeen = !!s.seen[b.id];
    return {
      id: b.id,
      name: b.name,
      dex: "#" + b.dex,
      dexNum: b.dex,
      score: e.score,
      hacks: b.hacks,
      wins: b.wins,
      repos: b.repos,
      why: b.why,
      type: k,
      bg: t.bg,
      fg: t.fg,
      meta: metaLine([b.school.value, yearLabel(b.year.value), b.city.value]),
      dash: ((e.score / 100) * RING_SMALL).toFixed(1) + " " + RING_SMALL.toFixed(1),
      scoreLabel: "Match score " + e.score + " percent",
      chips: chipsFor(b.types.length ? b.types : [k]),
      av: avatar(b.id),
      revealed: rev,
      avClass: rev ? "" : "silhouette",
      seen: wasSeen,
      dexStyle: wasSeen ? { background: t.fg, color: "#FFFFFF" } : { background: "#FFFFFF", color: t.fg },
      starred: on,
      starLabel: on ? "Remove " + b.name + " from shortlist" : "Add " + b.name + " to shortlist",
      starFill: on ? "#FFCB3D" : "none",
      starStroke: on ? "#C98F0E" : "#6E5A55",
      bursting: s.burst === b.id,
    };
  });

  const remaining = ranked.length - shownList.length;
  const skeletons = done || s.filter !== "all" ? 0 : Math.min(3, remaining);

  const filters: FilterVM[] = criteriaChips(search)
    .filter((f) => !s.removed[f.id])
    .map((f) => ({ ...f, removeLabel: "Remove filter " + f.label }));

  let phase = "Reading Devpost projects";
  if (tick >= 24) phase = "Checking GitHub commits";
  if (tick >= 48) phase = "Comparing builders to your search";
  const scanned = Math.min(total, Math.round((tick * 3 * total) / 214));

  const n = ranked.length;
  const headline = !done ? "Scouting for you…" : n === 0 ? "No builders found" : n + (n === 1 ? " builder found!" : " builders found!");

  return {
    ranked,
    order: visible.filter(isRevealed),
    grid: {
      headline,
      filters,
      anyRemoved: Object.keys(s.removed).length > 0,
      sort: s.sort,
      scanning: !done,
      done,
      phase,
      scanned,
      total: data.scan.projectsChecked,
      progress: (done ? 100 : Math.round((scanned / total) * 100)) + "%",
      tabs,
      cards,
      skeletons,
      noneVisible: cards.length === 0 && skeletons === 0 && shownList.length > 0,
      noneFound: done && n === 0,
      moreCount: Math.max(0, visible.length - s.limit),
      starCount: Object.keys(s.starred).filter((k) => s.starred[k]).length,
      seenCount: Object.keys(s.seen).length,
    },
  };
}

const STATUS_VM = (status: CritStatus) => STATUS[status];

export function deriveProfile(s: DexState, ctx: Ctx, id: string, e: Evaluation, order: Ranked[]): ProfileVM | null {
  const c = ctx.data.builders.find((x) => x.id === id);
  if (!c) return null;
  const accent = ctx.accent;
  const now = ctx.now || new Date();
  const k0 = topType(c);
  const t = TYPES[k0];
  const first = firstName(c.name);

  // EV hexagon (design: centre 170,150, radius 105).
  const dirs = [[0, -1], [0.866, -0.5], [0.866, 0.5], [0, 1], [-0.866, 0.5], [-0.866, -0.5]];
  const pts: string[] = [];
  const dots: RadarDot[] = [];
  const v = {} as Record<TypeKey, number>;
  const f = {} as Record<TypeKey, string>;
  AXES.forEach((k, i) => {
    const val = c.ev[k] || 0;
    const frac = Math.min(1, val / 252);
    const x = 170 + dirs[i][0] * 105 * frac;
    const y = 150 + dirs[i][1] * 105 * frac;
    pts.push(x.toFixed(1) + "," + y.toFixed(1));
    dots.push({ x: x.toFixed(1), y: y.toFixed(1), r: val > 0 ? 5.5 : 0, fill: TYPES[k].fg });
    v[k] = val;
    f[k] = val > 0 ? TYPES[k].fg : "#6E5A55";
  });
  const total = AXES.reduce((a, k) => a + (c.ev[k] || 0), 0);
  const nonzero = AXES.filter((k) => c.ev[k] > 0).sort((a, b) => c.ev[b] - c.ev[a]);
  const zeros = AXES.filter((k) => !c.ev[k]).map((k) => TYPES[k].label);
  const evRows: EvRowVM[] = nonzero.map((k) => ({
    key: k,
    label: TYPES[k].label,
    value: c.ev[k],
    fg: TYPES[k].fg,
    bg: TYPES[k].bg,
    icon: TYPES[k].icon,
    src: listNames(c.evFrom[k]) || "earlier projects",
  }));

  // IV tiles with the design's evidence sentences.
  const ev = [
    c.n.demo + " of " + c.hacks + " projects have a working demo",
    c.wins ? c.wins + " prize" + (c.wins > 1 ? "s" : "") + " in " + c.hacks + " hackathons" : "No prizes yet in " + c.hacks + " hackathons",
    "Owns the repo on " + c.n.own + " of " + c.hacks + " projects",
    "Built with " + c.n.mates + " different teammates",
    "Kept building " + c.n.kept + " of " + c.hacks + " after the event",
    "READMEs on " + c.n.docs + " of " + c.hacks + " projects",
  ];
  const ivTiles: IvTileVM[] = c.iv.map((val, i) => {
    const j = judge(val, accent);
    return { label: TRAIT_LABELS[i], value: val, judge: j[0], judgeStyle: j[1], evidence: ev[i] };
  });
  let hi = 0;
  let lo = 0;
  c.iv.forEach((val, i) => {
    if (val > c.iv[hi]) hi = i;
    if (val < c.iv[lo]) lo = i;
  });

  const crits: CritVM[] = e.rows.map((r) => ({ key: r.key, label: r.label, note: r.note, src: r.src, ...STATUS_VM(r.status) }));
  const rows = e.rows.length;

  const projects = c.projects;
  const top = projects[0];
  const topTypeLabel = TYPES[nonzero[0] || k0].label;
  const idx = order.findIndex((x) => x.b.id === c.id);
  const prev = idx > 0 ? order[idx - 1].b : null;
  const next = idx >= 0 && idx < order.length - 1 ? order[idx + 1].b : null;
  const on = !!s.starred[c.id];

  const note = (label: string, fact: { value: string | null; source: string | null; looked: Builder["school"]["looked"] }): NoteVM => ({
    label,
    value: fact.value || NOT_LISTED,
    missing: !fact.value,
    hint: fact.value ? fact.source || "" : lookedIn({ value: null, source: null, looked: fact.looked }),
  });
  const notes: NoteVM[] = [
    note("School", c.schoolFull),
    note("Program", c.program),
    note("Graduating", c.grad),
    note("Last active", { ...c.lastActive, value: c.lastActive.value ? relativeDay(c.lastActive.value, now) : null }),
  ];

  const gh = !!c.links.github;
  const li = !!c.links.linkedin;
  const verify =
    gh && li
      ? "GitHub and LinkedIn are linked from " + first + "'s own Devpost profile, so this is the right person."
      : gh
        ? "GitHub is linked from " + first + "'s own Devpost profile, so this is the right person."
        : li
          ? "LinkedIn is linked from " + first + "'s own Devpost profile, so this is the right person."
          : "Code was matched to " + first + " through their Devpost team, not by name across sites.";

  return {
    id: c.id,
    name: c.name,
    first,
    dex: "#" + c.dex,
    dexNum: c.dex,
    fg: t.fg,
    bg: t.bg,
    av: avatar(c.id),
    meta: metaLine([c.schoolFull.value, yearLabel(c.year.value), c.city.value]),
    chips: chipsFor(c.types.length ? c.types : [k0]),
    sum: c.sum,
    score: e.score,
    scoreLabel: "Match score " + e.score + " percent",
    dash: ((e.score / 100) * RING_LARGE).toFixed(1) + " " + RING_LARGE.toFixed(1),
    starred: on,
    shortLabel: on ? "Shortlisted!" : "Shortlist",
    shortStyle: on ? { background: "#FFCB3D", boxShadow: "0 5px 0 #C98F0E" } : { background: "#FFF6EE", boxShadow: "0 5px 0 rgba(42,23,21,.14)" },
    starFill: on ? "#FFFFFF" : "none",
    bursting: s.burst === c.id,
    crits,
    metLabel: rows ? e.met + " of " + rows + " match" : "No filters on",
    metStyle: rows && e.met === rows ? { background: "#DDF5EA", color: "#1A6B4A" } : { background: "#FFF3C4", color: "#7A5D00" },
    radar: { points: pts.join(" "), dots, v, f },
    radarLabel: "EV hexagon for " + c.name + ": " + (nonzero.length ? nonzero.map((k) => TYPES[k].label + " " + c.ev[k]).join(", ") : "no points yet") + ".",
    evRows,
    hasZeros: zeros.length > 0,
    zeros: "No points yet in " + zeros.join(" or ") + ".",
    evTotal: total,
    trainedLabel: total >= 510 ? "Fully trained" : "Still training",
    trainedStyle: total >= 510 ? { background: accent, color: "#FFFFFF" } : { background: "#FFF3C4", color: "#7A5D00" },
    ivTiles,
    ivPopulation: ctx.data.scan.buildersFound,
    natureName: NATURES[hi],
    natureLine: "Strongest at " + TRAIT_LABELS[hi].toLowerCase() + ", lightest on " + TRAIT_LABELS[lo].toLowerCase() + ".",
    notes,
    links: [
      { label: "GitHub", href: c.links.github },
      { label: "Devpost", href: c.links.devpost },
      { label: "LinkedIn", href: c.links.linkedin },
    ],
    verify,
    projCount: projects.length + " of " + c.hacks,
    projects: projects.map((pr) => {
      const pt = TYPES[pr.type || k0];
      return {
        id: pr.id,
        name: pr.name,
        abbr: pr.abbr,
        event: pr.event,
        desc: pr.desc,
        prize: pr.prize,
        hasPrize: !!pr.prize,
        kept: pr.kept,
        bg: pt.bg,
        fg: pt.fg,
        share: pr.share !== null ? first + " wrote " + pr.share + "%" : "No code counted",
        url: pr.url,
        repo: pr.repo,
        flags: pr.flags,
      };
    }),
    draftSubject: top ? "Your " + top.name + " build at " + top.event : "Your hackathon builds",
    draftBody: top
      ? "Hi " + first + ",\n\nI came across " + top.name + " on Devpost. " + sentence(top.desc) + " That's an impressive build for one weekend.\n\nI'm hiring for [ROLE] at [COMPANY], working on [TEAM OR PRODUCT]. Your " + topTypeLabel + " work stood out, and I think you'd be a great fit.\n\nWould you be open to a 20-minute chat next week?\n\n[YOUR NAME]"
      : "Hi " + first + ",\n\nI'm hiring for [ROLE] at [COMPANY], working on [TEAM OR PRODUCT]. Your " + topTypeLabel + " work stood out, and I think you'd be a great fit.\n\nWould you be open to a 20-minute chat next week?\n\n[YOUR NAME]",
    backLabel: "All " + order.length + " builders",
    pos: idx >= 0 ? idx + 1 + " of " + order.length : "",
    prevLabel: prev ? "#" + prev.dex + " " + firstName(prev.name) : "Start",
    nextLabel: next ? "#" + next.dex + " " + firstName(next.name) : "End",
    prevAria: prev ? "Previous: #" + prev.dex + " " + prev.name : "No previous builder",
    nextAria: next ? "Next: #" + next.dex + " " + next.name : "No next builder",
    noPrev: !prev,
    noNext: !next,
    prevId: prev ? prev.id : null,
    nextId: next ? next.id : null,
  };
}
