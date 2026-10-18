// Port the design file's sample candidates to data/sample.json in the final data shape.
// Run: node scripts/port-sample.mjs   (after python3 scripts/extract_design.py)
//
// Values come straight from candidates() in design/extracted/component.js.
// The design's free-text criteria notes are replaced by the counts they describe
// (codeProjects / typeProjects) because the app computes every note from data.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const js = fs.readFileSync(path.join(root, "design/extracted/component.js"), "utf8");
const body = js.match(/candidates\(\)\s*\{\s*return\s*(\[[\s\S]*?\]);\s*\}\s*\n\s*avatar\(/);
if (!body) throw new Error("could not find candidates() in component.js");
const candidates = new Function("return " + body[1])();

const GENERATED = "2026-10-17T12:00:00-04:00";
const now = new Date(GENERATED);
const AXES = ["ml", "backend", "frontend", "design", "mobile", "hardware"];
const LOOKED = ["résumé", "People Data Labs", "Devpost"];

const fact = (value, source) => ({ value, source: value === null ? null : source, looked: LOOKED });

function daysAgo(s) {
  const m = { today: 0, yesterday: 1 }[s];
  if (m !== undefined) return m;
  const d = s.match(/^(\d+) days? ago$/);
  if (d) return +d[1];
  const w = s.match(/^(\d+) weeks? ago$/);
  if (w) return 7 * +w[1];
  throw new Error("unknown active string " + s);
}

function isoDaysAgo(n) {
  const d = new Date(now.getTime() - n * 24 * 3600 * 1000);
  return d.toISOString();
}

/** "Crop Doctor, Gesture Keys, 3 more" -> ["Crop Doctor", "Gesture Keys", +3 unnamed] */
function fromList(src) {
  if (!src) return [];
  const parts = src.split(", ");
  const out = [];
  for (const p of parts) {
    const more = p.match(/^(\d+) more$/);
    if (more) for (let i = 1; i <= +more[1]; i++) out.push("Earlier project " + i);
    else out.push(p);
  }
  return out;
}

function countFromSrc(src) {
  if (!src) return 0;
  const earlier = src.match(/^(\d+) earlier projects?$/);
  if (earlier) return +earlier[1];
  return fromList(src).length;
}

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const abbrOf = (p) => p.abbr;

const builders = candidates.map((c) => {
  const year = c.year === "New grad" ? 0 : +c.year.replace("Year ", "");
  const evFrom = {};
  const typeProjects = {};
  for (const k of AXES) {
    const src = c.src[k];
    if (src) evFrom[k] = /^\d+ earlier projects?$/.test(src) ? [src] : fromList(src);
    typeProjects[k] = countFromSrc(src);
  }
  // A "met" ML note in the design states how many projects have ML code ("6 of 7 ...").
  if (c.mlc[0] === "met") {
    const m = c.mlc[1].match(/^(\d+) of (\d+)/);
    const all = c.mlc[1].match(/^All (\d+)/);
    if (m) typeProjects.ml = +m[1];
    else if (all) typeProjects.ml = +all[1];
  }
  return {
    id: c.id,
    name: c.name,
    dex: c.dex,
    types: c.types,
    school: fact(c.school, "Devpost"),
    schoolFull: fact(c.schoolFull, "Devpost"),
    program: fact(c.program, "Devpost"),
    grad: fact(c.grad, "Devpost"),
    year: fact(year, "Devpost"),
    city: fact(c.city, "Devpost"),
    lastActive: { value: isoDaysAgo(daysAgo(c.active)), source: "GitHub", looked: ["GitHub"] },
    links: { devpost: "https://devpost.com", github: "https://github.com", linkedin: "https://www.linkedin.com" },
    hacks: c.hacks,
    wins: c.wins,
    repos: c.repos,
    why: c.why,
    sum: c.sum,
    ev: Object.fromEntries(AXES.map((k) => [k, c.ev[k] || 0])),
    evFrom,
    iv: c.iv,
    n: c.n,
    codeProjects: c.hacks,
    typeProjects,
    projects: c.projects.map((p) => ({
      id: slug(p.name),
      name: p.name,
      abbr: abbrOf(p),
      type: p.type,
      event: p.event,
      desc: p.desc,
      prize: p.prize,
      prizes: p.prize ? [p.prize] : [],
      kept: p.kept,
      share: p.share,
      url: "https://devpost.com",
      repo: null,
      demo: true,
      flags: [],
      inScan: true,
    })),
  };
});

const dataset = {
  version: 1,
  source: "sample",
  generatedAt: GENERATED,
  scan: {
    hackathons: [],
    projectsChecked: 214,
    reposChecked: 0,
    commitsCounted: 0,
    buildersFound: 214,
  },
  builders,
  demo: { shortlist: ["arjun", "sofia"] },
};

fs.writeFileSync(path.join(root, "data/sample.json"), JSON.stringify(dataset, null, 2) + "\n");
console.log("wrote data/sample.json with", builders.length, "builders");
