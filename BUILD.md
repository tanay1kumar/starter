# Build brief: Talent Dex

You are building **Talent Dex** end to end in this repo, from this one brief. Work through the
milestones at the bottom **in order**. Each one must run before you start the next. Commit after
each milestone. Don't stop to ask questions unless you're blocked by a missing key; make a
reasonable choice, write it down in `NOTES.md`, and keep going.

## Hard rules
- Hackathon rule: all code is written now (Hack the Valley 11 coding window started Fri Oct 16, 8 PM ET).
- Secrets are in `keys.env` at the repo root. Load it with dotenv (`path: "keys.env"`). Never print,
  log or commit key values. Add `keys.env` and `.env*` to `.gitignore` first thing.
- The demo never calls Devpost, GitHub, People Data Labs or Gemini live. The pipeline runs ahead of
  time and caches everything; the UI reads cached data.
- Never invent a number. If data is missing, show "Not listed" and say where you looked.
- Never match a person across sites by name. Only follow GitHub/LinkedIn links the person posted on
  their own Devpost profile.
- It's called **Talent Dex**. Don't use the words Pokémon or Pokédex, sprites, Poké Ball imagery or
  any game assets. Game-style ideas (dex numbers, types, EVs, IVs, natures) are fine as we define them.

## What it is
Recruiters at hackathon sponsor companies use Talent Dex to find student builders. A recruiter
describes who they're hiring; Talent Dex scans students' hackathon projects on Devpost and their
GitHub code, works out what each person actually built, and shows a ranked grid of "dex cards".
Clicking a card opens a "Dex entry" with evidence for every claim. Hackers are found, not users.

## Design source of truth
`design/talent-dex-v3.html` is the approved design for the matches grid and the Dex entry. Match it
closely: layout, copy, colours, fonts, motion, states.

How to read it: the file is ~350 KB, mostly embedded fonts. The real content is inside
`<script type="__bundler/template">`, a JSON-encoded string. Parse that string to get the screen
markup (a `<x-dc>` template with `{{holes}}`, `<sc-for>`, `<sc-if>`) and a
`<script type="text/x-dc">` block with `class Component extends DCLogic`. That class contains the
sample candidates, the type colours, the scoring helpers and all interaction logic. Port the markup
to React components and the logic to TypeScript. Keep the copy exactly unless this brief changes it.

Design tokens visible in the file (confirm against it):
- Fonts: Fredoka (display), Nunito (body), Geist Mono (numbers). Load from Google Fonts.
- Ink `#2A1715`, muted `#6E5A55`, paper `#FFF6EE`, accent red `#E8382B` (darker shade for the
  chunky offset shadows), shortlist yellow `#FFCB3D` with shadow `#C98F0E`.
- Six types, each with a background/foreground pair and an icon path in `types()`:
  ML / AI, Backend, Frontend, Design, Mobile, Hardware.
- Motion: card-to-profile FLIP morph (~560 ms), prev/next slide (~380 ms), radar pop-in, shortlist
  burst. Respect `prefers-reduced-motion` exactly as the file does.

## Screens and behaviour

### 0. Search (not in the design file; build it in the same style)
- One big input: "Describe who you're hiring, or paste a job posting." Plus 3 example chips.
- Gemini turns the text into criteria: 1–2 skill types (from the six), a school year, a location,
  and "hackathon winner" yes/no. These become the removable filter chips on screen 1.
- Button: "Start scan". Goes to screen 1.

### 1. Matches grid ("Starter matches")
- Header: Seen count, Shortlist count, "New scan".
- Headline "Scouting for you…" while scanning, then "N builders found!".
- Scan progress: `{scanned} / {total}` projects with three phases in this order: "Reading Devpost
  projects", "Checking GitHub commits", "Comparing builders to your search". Then "Scan complete!
  N projects checked." The scan replays the cached pipeline run as an animation; cards appear one by
  one as they're "found".
- Removable filter chips + "Restore filters". Removing a chip re-ranks immediately.
- Sort: Best match, Most wins, Most hackathons.
- Type tabs with counts ("All" + each type that has builders). Empty state: "No builders of this
  type yet. Try another tab!"
- Each card: dex number, match score ring, name, "School · Year · City", type chips,
  Hackathons / Wins / Repos, one-line "why" (≤ 15 words).

### 2. Dex entry (profile)
- Opens with the FLIP morph from its card. Back ("All N builders"), prev/next with names, "k of N".
- Summary line (≤ 20 words), score, type chips, Shortlist toggle with burst.
- "Say hi to {first}": email draft, subject + body built from their top project, with bracketed
  placeholders ([ROLE], [COMPANY], [TEAM OR PRODUCT]) and a Copy button. Same template as the file.
- "Why {first} fits your search": "k of 4 match", one row per criterion with Matches / Close /
  Does not match, a note, and the source (GitHub / Devpost / résumé / People Data Labs).
- Trait board, two tabs:
  - **EVs · Effort**: hexagon radar over the six types plus rows "{type} {value} — From {projects}",
    "No points yet in …", "{total} / 510 EVs", "Fully trained" / "Still training".
  - **IVs · Traits**: six tiles 0–31 with a judge label and one evidence line each, plus
    "{Nature} nature — Strongest at …, lightest on …".
- Field notes: School, Program, Graduating, Last active, GitHub / Devpost / LinkedIn links, and the
  verify line ("GitHub and LinkedIn are linked from {first}'s own Devpost profile, so this is the
  right person."). If a link isn't on their Devpost profile, show "Not linked on Devpost" instead.
- Signature projects: tile, prize, name, one-line description, event, "Kept building" badge,
  "{first} wrote {N}%".

## How every number is computed
Nothing on screen is hand-made in the real build. Use exactly these definitions.

**Attribution (who wrote what).** Clone each project repo (`git clone --single-branch`; skip repos
over 300 MB). For each commit:
- Count it only if its author date is between the hackathon's start and end (from the Devpost
  hackathon API). Author dates in `git log` keep their original timezone; use them.
- Exclude build output (`.next/ dist/ build/ out/ __pycache__/ *.pyc`), lockfiles
  (`package-lock.json yarn.lock pnpm-lock.yaml poetry.lock Cargo.lock`), `node_modules/`, vendored
  code, binaries, minified files, and any file that already existed in the repo's first commit if
  that commit predates the event (starter templates).
- Use `git log --numstat` added lines per author per file. Map git author names/emails to Devpost
  team members (exact email or GitHub username match first; then name match *within that team only*).
  Unmapped authors are kept as "unknown", never guessed.
- `wrote N%` = that person's share of counted added lines in the repo. If one author has > 90% and
  the team has 3+ members, add a caveat flag "possible shared laptop or squashed commits".

**Areas.** Classify each counted file into one of the six types by rules first, Gemini only for leftovers:
- ML / AI: notebooks, files importing torch/tensorflow/sklearn/transformers/openai/anthropic/gemini,
  `model`/`train`/`inference` paths.
- Backend: server/api/routes/db/migrations, Express/FastAPI/Flask/Django/Go/Rust server code, SQL.
- Frontend: React/Vue/Svelte components, pages, CSS/Tailwind, web client code.
- Design: Figma exports, SVG/asset folders, design tokens, style-only files.
- Mobile: React Native/Expo, Swift/SwiftUI, Kotlin/Android, Flutter.
- Hardware: `.ino`, C/C++ firmware, ESP32/STM32/Arduino/Raspberry Pi, PCB/CAD files.

**EVs (effort, 0–252 per type, 0–510 total).** For each builder: `share_t` = their counted lines in
type t ÷ all their counted lines. `maturity` = min(1, projects with counted code ÷ 6).
`EV_t = min(252, round(510 × maturity × share_t))`. "From" = the projects that contributed most to
that type. "Fully trained" when the total reaches 510.

**IVs (traits, 0–31, relative to everyone in the scan).** Compute a raw value per builder, then
`IV = round(31 × percentile_rank)` among builders in the current scan:
- Ships demos: projects with a demo video or a working live URL ÷ hackathons.
- Wins: prizes won (tie-break: prizes ÷ hackathons).
- Ownership: projects where they wrote the most counted lines ÷ hackathons.
- Teamwork: distinct teammates across all projects.
- Persistence: projects with *code* commits (not README-only) after the event ended ÷ hackathons.
- Documentation: projects with a README they wrote (> 300 characters) ÷ hackathons.
Judge labels and nature names: use `judge()` and the `natures` list from the design file.
Evidence lines: use the same sentence templates as the file.

**Card numbers.** Hackathons = Devpost hackathon count. Wins = prizes on Devpost. Repos = public
GitHub repo count. Last active = latest public GitHub push. Dex number = stable 4-digit id from a
hash of the Devpost username.

**Types on the card.** The builder's top one or two EV types (second only if ≥ 60% of the first).

**Search criteria (screen 2 "Why X fits").**
- Skill type: Matches if ≥ half their projects have counted code in that type; Close if any do.
- Year: from résumé, else People Data Labs education end date, else Devpost tagline. Close if ±1 year.
- Location: Matches if same city; Close if within 150 km of the searched city (small lookup table of
  Ontario cities is fine); otherwise Does not match.
- Hackathon winner: Matches if Wins ≥ 1.

**Match score (0–100).** `100 × (0.6 × criteria + 0.4 × skill_fit)`, where criteria = average of
the four (Matches 1, Close 0.5, no 0) and skill_fit = mean over searched types of `EV_t / 252`.
Ranking is plain math; never ask the LLM to rank.

**Words.** Gemini writes the "why" line and the summary from a JSON of that builder's verified facts
only (numbers above + project names/prizes). Never pass names, schools or photos into scoring or
classification prompts. Cache every response.

## Data pipeline (`/pipeline`, Python 3.11)
1. Hackathons: `https://devpost.com/api/hackathons?search=<name>` (JSON). Target: Hack the Valley X
   and 9, Hack the 6ix 2025, UofTHacks 12, DeltaHacks 11, Hack the North 2025, and HTV 11 if its gallery
   is public. Aim for ~200 projects, like the design's "214".
2. Projects: gallery pages + `https://devpost.com/software/search?query=` (JSON); scrape each project
   page for team members, GitHub link, prizes, demo video, built-with, story text.
3. People: scrape `devpost.com/<user>` and `/<user>/challenges` for hackathon history, tagline and the
   GitHub/LinkedIn links they posted.
4. Code: clone, attribute, classify (rules above).
5. Enrichment: People Data Labs person enrich by LinkedIn URL (school, program, grad year, location).
   If `PDL_API_KEY` is missing or fails, skip it and fall back to the Devpost tagline. Cache raw JSON
   per LinkedIn URL and never call twice for the same URL.
6. Scores: EVs, IVs, card numbers.
7. Words: Gemini (Flash model), concurrency 4, retry with backoff on 429.
8. Output: write everything to Postgres (`DATABASE_URL`, Tiger Data) and export `data/builders.json`
   for the UI. If `DATABASE_URL` is missing, write JSON only.
Make every step resumable and cached in `pipeline/cache/` so re-runs are free.

## Stack
- Web: Next.js (App Router) + TypeScript + Tailwind. API routes read `data/builders.json` (or Postgres).
- Pipeline: Python 3.11 (requests, beautifulsoup4, python-dotenv, google-genai, psycopg).
- Tests: a few pytest cases for attribution; Playwright for one end-to-end click-through.

## Environment (`keys.env`)
Expected names (check the file for the actual names; never print values):
`GITHUB_TOKEN`, `GEMINI_API_KEY`, `DATABASE_URL`, `PDL_API_KEY` (optional).
Commit a `keys.env.example` with the names only.

## Milestones (do them in order)
1. **UI on sample data.** Port the design file's sample candidates to `data/sample.json` in the
   final data shape. Build screens 1 and 2 to match the design, with all interactions (filters,
   sort, tabs, shortlist, seen, FLIP morph, prev/next, draft + copy, EV/IV tabs). Then screen 0.
   Done when `npm run dev` works and a Playwright screenshot of each screen looks like the design.
2. **Attribution on one known repo.** Run it on `https://github.com/jello-2/PlantHopper`
   (Hack the Valley X, 1st place). An earlier manual check found GitHub user `pekachoo` authored
   all commits touching `UniversalControl.ino` (21 of 21, all-time). Confirm with plain `git log`,
   then write a test that the pipeline gives that file 100% to `pekachoo` (within the hackathon
   window it may be fewer commits; if so, record why in NOTES.md). Done when the test passes.
3. **Full pipeline → `data/builders.json`.** Run steps 1–7 on the target hackathons. Add a
   `DATA_SOURCE=sample|real` switch; the UI renders real data with no code changes.
4. **Search + scan replay.** Screen 0 parsing with Gemini; the scan animation on screen 1 replays the
   cached run, with real totals.
5. **Postgres + semantic search (Tiger Data).** Load the data; add pgvector embeddings of project
   descriptions so free-text searches like "built a RAG pipeline" also match.
6. **Polish.** Keyboard and focus states, reduced motion, empty and error states, loading states,
   one Playwright run through the whole demo, and a README with setup and a 4-minute demo script.

Write `NOTES.md` as you go: decisions, anything skipped, known data gaps.
