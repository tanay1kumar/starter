# Talent Dex

Talent Dex helps recruiters find student builders through their hackathon work. It reads projects
from Ontario hackathons on Devpost, works out from each repo's git history which teammate wrote
which code, and ranks those builders against a recruiter's search ("ML intern, Toronto"). Every
number on a builder's Dex entry links back to where it came from (a GitHub repo, a Devpost page or
People Data Labs), and anything we couldn't find reads "Not listed" with where we looked. A Python
pipeline builds the data ahead of time and the web app only reads the cached files, so the demo
never calls Devpost, GitHub, People Data Labs or Gemini.

Screenshots of each screen are in `docs/screenshots/` (sample data) and `docs/screenshots/real/`
(real data), and the demo script below, step by step, in `docs/screenshots/demo/`.
[NOTES.md](NOTES.md) records every decision, what was skipped and the known data gaps;
[BUILD.md](BUILD.md) is the brief.

## Setup

### Requirements

- **Node.js 20.9 or newer** (the minimum for Next.js 16). Developed and tested on Node 26.3.
- **Python 3.11 with [uv](https://docs.astral.sh/uv/)** for the pipeline and its tests. uv fetches
  3.11 if you don't have it.
- **git.** The pipeline clones repos with it and the attribution tests build small repos with it.
- **A macOS or Linux shell.** The npm scripts set variables inline (`DATA_SOURCE=real next dev`).

### Install

```bash
npm install
npx playwright install chromium     # browser for the end-to-end tests

cd pipeline
uv venv --python 3.11               # creates pipeline/.venv
uv pip install --python .venv/bin/python -r requirements.txt
cd ..
```

### Keys

The demo needs no keys. They are only used to rebuild the data.

```bash
cp -n keys.env.example keys.env     # -n keeps a keys.env you already have. Never commit it.
```

`keys.env` holds one `NAME=value` per line. The pipeline (`pipeline/talentdex/config.py`), the app's
server code (`next.config.ts`) and `scripts/load-db.mjs` read it; a variable already set in your
shell wins.

| Key | Used for | Without it |
| --- | --- | --- |
| `GITHUB_TOKEN` | Pipeline: GitHub API calls (repos, commit authors, profiles). Public read access is enough. | GitHub's unauthenticated limit, far below what a run needs. |
| `GEMINI_API_KEY` | Pipeline: types for files the rules can't place, and each builder's "why" line and summary. App: parsing a search that isn't cached, only with `ALLOW_LIVE_GEMINI=1`. | Those files stay unclassified, the lines come from templates, and uncached searches use the keyword parser. |
| `PDL_API_KEY` | Pipeline, optional: People Data Labs lookups (school, program, graduation, city) by LinkedIn URL. | School and year come from the Devpost tagline. |
| `DATABASE_URL` | Optional: Postgres with pgvector (Tiger Data), loaded by `scripts/load-db.mjs` and then used by the topic search. | The topic search scores the same vectors from `data/embeddings.json`. |

Two app switches can go in the shell or in `keys.env`:

- `DATA_SOURCE=sample|real`: which dataset the app reads. Default `sample`.
- `ALLOW_LIVE_GEMINI=1`: lets `/api/parse` call Gemini when a search isn't cached. Leave it off for
  demos.

### Run the demo on cached data

```bash
npm run dev         # sample data: the design's sample builders (data/sample.json)
npm run dev:real    # real data: the cached pipeline run (data/builders.json)
```

Open http://localhost:3000. If port 3000 is taken, Next uses the next free port and prints the URL.
The demo script below uses `npm run dev:real`.

### Tests

```bash
# Pipeline
(cd pipeline && .venv/bin/python -m pytest tests)

# Web app. Playwright starts its own `next dev --port 3100`, so stop any other
# next dev in this folder first.
npx playwright test                                            # sample data
DATA_SOURCE=real npx playwright test                           # real data
DATA_SOURCE=real npx playwright test tests/e2e/topic.spec.ts   # one file

# Checks
npx tsc --noEmit
npx eslint lib app components scripts tests
```

- Most pytest cases run offline on small fixtures (temporary git repos, inline pages, stand-ins for
  Gemini and People Data Labs). The PlantHopper and Hack the Valley X checks read Devpost and GitHub
  once and are served from `pipeline/cache/` after that.
- Run Playwright in both data modes. Seven tests skip themselves on sample data, which has no crawl
  order, no project write-ups and fewer than one page of builders: the scan replay test in
  `search.spec.ts`, the three tests in `topic.spec.ts`, the topic "Try again" test in
  `states.spec.ts`, "Show more moves focus…" in `a11y.spec.ts`, and `demo.spec.ts`.
- `tests/e2e/demo.spec.ts` (real data only) runs the 4-minute demo script below as one test, a step
  per section, from the search to the trust line. It also checks that no request leaves the app's
  own server.
- `screens.spec.ts`, `topic.spec.ts` and `demo.spec.ts` save screenshots to `docs/screenshots/`
  (sample), `docs/screenshots/real/` and `docs/screenshots/demo/` (real; 18 PNGs, one or more per
  demo step), so a test run updates those files.

## Rebuilding the data

The repo ships with the pipeline's output in `data/`; rebuild only for fresh data. Run the steps in
this order.

### 1. Run the pipeline

Writes `data/builders.json` and `data/projects.json`. Run it from `pipeline/`; steps 2 to 4 run from
the repo root.

```bash
cd pipeline
.venv/bin/python -m talentdex.run                              # full run, resumes from the cache
.venv/bin/python -m talentdex.run --portfolio-cap 0 --no-pdl   # quick: scanned projects only, no PDL
```

| Flag | Default | Effect |
| --- | --- | --- |
| `--total N` | 214 | Projects to scan, split evenly across the hackathons with a public gallery and rounded up (5 events × 43 = 215). |
| `--portfolio-cap N` | 30 | How many of each builder's other Devpost hackathon projects to read and attribute. 0 = scanned projects only. |
| `--workers N` | 6 | Repos analysed in parallel. |
| `--no-pdl` | off | Skip People Data Labs entirely: no lookups, and cached answers aren't used either. |
| `--no-words` | off | Template lines instead of Gemini for each "why" line and summary. |
| `--no-clone` | off | Analyse only repos already cloned and cached; skip the rest without remembering the skip, so a later run without the flag fetches them. For a slow network. |
| `--out PATH` | `data/builders.json` | Where the dataset goes; `projects.json` is written next to it. |

- Every network response is cached under `pipeline/cache/`: Devpost pages and API answers, GitHub
  API answers, Gemini answers, People Data Labs answers and demo-link checks. Rate limits and server
  errors are retried with backoff and never cached. A re-run only fetches what is missing.
- Each repo is cloned once into `pipeline/work/`, read into an extract under `pipeline/cache/git/`,
  and the clone is deleted. Repos over 300 MB are skipped.
- People Data Labs lookups are capped and cached per LinkedIn URL. Only the LinkedIn URL a builder
  posted on their own Devpost profile is looked up, builders with the most wins and code go first,
  and a URL is never sent twice (a cached 404 counts as an answer). A ledger in
  `pipeline/cache/pdl/calls.jsonl` stops every run at `PDL_MAX_CALLS` lookups in total (default 90).
- The output is checked against the `lib/types.ts` shape before it is written.
  `pipeline/cache/steps/run.json` records what the last run did (portfolio cap, counts, skipped
  repos, People Data Labs matches, Gemini or template lines).
- Other settings: `GEMINI_MODEL` (default `gemini-3.8-flash`), and `TALENTDEX_CACHE` /
  `TALENTDEX_WORK` to move the cache and clone folders. The hackathon list is `TARGETS` in
  `pipeline/talentdex/crawl.py`.

### 2. Cache the demo searches

Writes `data/searches.json`. Needed only when a text in `data/demo-searches.json` is added or
changed (`examples` are the chips on screen 0, `more` are the other demo texts). Needs
`GEMINI_API_KEY`.

```bash
# Terminal 1: a dev server that may call Gemini (stop any other next dev in this folder first)
ALLOW_LIVE_GEMINI=1 npx next dev -p 3100

# Terminal 2
node scripts/cache-searches.mjs http://localhost:3100
```

Texts already in the cache are answered from it; new ones go to Gemini and are added. The script
exits 1 if any text fell back to the keyword rules. To ask Gemini again about a cached text, delete
its entry from `data/searches.json` first. `tests/e2e/api.spec.ts` fails until every demo text is
cached. Stop the server when done, so the app runs with live Gemini off again.

### 3. Embed projects and search topics

Writes `data/embeddings.json`. Run it after steps 1 and 2.

```bash
node scripts/embed.mjs
```

Embeds every project in `data/projects.json` and every cached search's topic with a local model
(transformers.js, no API calls). The first run downloads the model into `.cache/models/`.

### 4. Optional: load Postgres + pgvector (Tiger Data)

```bash
node scripts/load-db.mjs
```

Needs `DATABASE_URL`. Creates the `vector` extension if needed and loads builders, projects, chunk
vectors and builder-project links into a `talentdex` schema, replacing its tables in one
transaction. If you just added `DATABASE_URL`, restart the app. `/api/topic` responses then say
`"source": "postgres"`, and the route falls back to `data/embeddings.json` on its own if the
database can't be reached.

Tiger Data's connection string ends in `?sslmode=require`. Add `&uselibpqcompat=true` to it:
node-postgres treats `require` as full certificate verification, and Tiger's certificate chain
isn't in Node's trust store ("self-signed certificate in certificate chain"). With it, the
connection is encrypted without checking the certificate, as `psql` does with `sslmode=require`.
Inserts go in batches of a few MB, since a small Tiger service runs out of memory on one large
statement.

### Data files

| File | Written by | Read by |
| --- | --- | --- |
| `data/builders.json` | the pipeline | the app with `DATA_SOURCE=real`, `load-db.mjs` |
| `data/projects.json` | the pipeline | `embed.mjs`, `load-db.mjs`, `/api/topic` |
| `data/embeddings.json` | `embed.mjs` | `/api/topic`, `load-db.mjs` |
| `data/searches.json` | `/api/parse` with live Gemini (via `cache-searches.mjs`) | `/api/parse`, `embed.mjs` |
| `data/demo-searches.json` | by hand | screen 0's chips, `cache-searches.mjs`, the tests |
| `data/places.json` | by hand | location checks in the app and the pipeline |
| `data/sample.json` | `npm run sample` (from the design file) | the app with `DATA_SOURCE=sample` |

## How it works

### Pipeline (`pipeline/talentdex/`)

1. **Crawl.** Find each target hackathon on Devpost's hackathon API and read its submission window
   from the event's dates page. Take an even share of projects from each public gallery (winners
   first, only projects that link a GitHub repo), then read each project page (team, repo, prizes,
   demo video, tools, write-up) and each member's Devpost profile (hackathon history, tagline, and
   the GitHub and LinkedIn links they posted). The current data scans 215 projects from Hack the
   Valley X, Hack the Valley 9, Hack the 6ix 2025, DeltaHacks XI and Hack the North 2025.
2. **Attribution.** Count added lines per author from `git log --numstat`, for commits authored
   inside the event window. Build output, lockfiles, vendored, generated and minified code, and
   starter-template files from before the event don't count. Commit authors are matched to Devpost
   teammates through the GitHub account on each teammate's own Devpost profile, and by name only
   within that one team; anyone left over stays "unknown". "wrote N%" is a person's share of the
   repo's counted lines, and a project where one person wrote over 90% on a team of three or more
   is flagged "possible shared laptop or squashed commits". A builder is a team member with counted
   code and a public Devpost profile; their other hackathon projects are attributed the same way,
   each with its own window and team.
3. **Classification.** Each counted file gets one of six types (ML / AI, Backend, Frontend, Design,
   Mobile, Hardware) from rules: extension, path, imports and dependencies. Gemini only sees the
   leftovers, with names, usernames, emails and URLs removed.
4. **Enrichment.** School, program, graduation and city from People Data Labs (by the LinkedIn URL on
   their own Devpost profile), else from the Devpost tagline. Repo count and last push from GitHub.
5. **Scores.** EVs, IVs, the card numbers (Hackathons, Wins, Repos) and a stable 4-digit dex number
   from a hash of the Devpost username.
6. **Words.** Gemini writes each card's "why" line (at most 15 words) and the Dex summary (at most
   20) from verified facts only; names, schools and photos are never sent. Every number in a line
   must appear in those facts, and a line that fails twice is replaced by a template.

The output step writes `data/builders.json` for the app and `data/projects.json` for the topic
search.

### Match score

Ranking is plain arithmetic in `lib/scoring.ts`; no model ranks anyone.

```
score     = 100 × (0.6 × criteria + 0.4 × skill_fit)
criteria  = average over the search's rows: Matches 1, Close 0.5, Does not match or Not listed 0
skill_fit = mean over the searched types of min(1, EV_type / 252)
```

| Row | Matches | Close |
| --- | --- | --- |
| Skill type | at least half of their projects with code have code of that type | any do |
| Year | same year of study (People Data Labs, else the Devpost tagline) | one year off |
| Location | same city | within 150 km (`data/places.json`) |
| Hackathon winner | at least one prize on Devpost | — |
| Topic | a project at z ≥ 2.5 and similarity ≥ 0.36 that they wrote at least 25% of | a project at z ≥ 2.0 and similarity ≥ 0.32, or a Matches-level one they wrote less of |

Ties go to more wins, then more hackathons. A row we can't check (no year or city found) is "Not
listed": it scores 0 and names where we looked.

### EVs and IVs

- **EVs (effort, 0–252 per type, 510 in total).** `EV_t = min(252, round(510 × maturity × share_t))`,
  where `share_t` is the builder's counted lines of type t over all their counted lines and
  `maturity = min(1, projects with counted code ÷ 6)`. "Fully trained" means 510. Each EV row names
  the projects its points came from.
- **IVs (traits, 0–31).** Six raw values per builder: Ships demos (projects with a demo video or a
  working live link), Wins (prizes), Ownership (projects where they wrote the most code), Teamwork
  (distinct teammates), Persistence (projects with code pushed after the event) and Documentation
  (projects with a README they wrote), most of them per hackathon. Each becomes
  `round(31 × share of the other builders in the scan with a lower value)`, so IVs are relative to
  everyone in the scan. The strongest trait names the builder's nature.

### Topic search

A search about a kind of project ("Built a RAG pipeline") gets a topic chip next to its skill
types. Gemini also writes the topic out as one sentence with acronyms spelled out, because small
embedding models miss "RAG" on its own. `scripts/embed.mjs` splits every project into a summary
chunk and one chunk per section of its Devpost write-up (leaving out inspiration and future-plans
sections) and embeds them locally with Snowflake arctic-embed-m v1.5. `/api/topic` scores each
project by its best chunk and measures how far that stands above all projects for the same topic
(z); the thresholds are in the table above. It runs in Postgres + pgvector when `DATABASE_URL` is
set, otherwise over the same vectors in `data/embeddings.json`.

### Code map

| Path | What |
| --- | --- |
| `app/page.tsx`, `components/search/` | Screen 0: the search |
| `app/matches/page.tsx`, `components/dex/` | Screens 1 and 2: the matches grid and the Dex entry |
| `lib/viewmodel.ts` | View models for screens 1 and 2, scan replay timing |
| `lib/scoring.ts`, `lib/criteria.ts` | Criteria rows, match score, filter chips |
| `lib/parse.ts`, `lib/parse-gemini.ts`, `lib/parse-rules.ts` | Search parsing: cache, live Gemini, keyword rules |
| `lib/topic.ts` | Topic search |
| `app/api/` | `builders`, `scan`, `parse` and `topic` routes |
| `pipeline/talentdex/` | The data pipeline; `run.py` runs every step |
| `scripts/` | The data scripts above, plus `port-sample.mjs` and `shoot.mjs` for the design comparison |
| `design/talent-dex-v3.html` | The approved design |

## 4-minute demo script

Uses the real data. Builder names change when the data is refreshed, so the script says what to
point at rather than who.

**Before you start**

- Run `npm run dev:real` and click through once (a search, the grid, an entry): dev mode compiles
  each page on its first visit.
- Then open http://localhost:3000 in a fresh private window at desktop size, so Seen and Shortlist
  start at 0.
- Leave `ALLOW_LIVE_GEMINI` unset. Both searches below are cached.

### 0:00–0:30 · The search

**Do:** On screen 0, point at the line under the search card: "Scanning 215 projects from 5
hackathons". Click the "ML intern, Toronto" chip, then "Start scan".

> "Hackathon sponsors see hundreds of student projects and can't tell who on a team built what.
> Talent Dex reads Ontario hackathon projects on Devpost and the GitHub code behind them: here, 215
> projects from five hackathons. I describe who I'm hiring in my own words, or paste a job posting."

### 0:30–1:00 · The scan replay

**Do:** Point at the four filter chips (ML / AI, Year 3, Toronto, Hackathon winner), then at the
progress panel as it moves through "Reading Devpost projects", "Checking GitHub commits" and
"Comparing builders to your search". Point at a card that is still a grey silhouette while the cards
around it fill in. The round arrow next to "Sort by" replays the scan (about five seconds).

> "My sentence became four filters; Gemini read it ahead of time. This is a replay of the real
> pipeline run, counting up to 215. Each card fills in when the counter reaches the project where we
> found that builder, so a strong match found late stays a silhouette until then. Nothing is
> fetched live."

### 1:00–1:30 · The grid

**Do:** Point at "N builders found!" and "Scan complete! 215 projects checked." Remove the "Year 3"
chip (the order changes at once), then click "Restore filters". Click a type tab, then "All". Set
"Sort by" to "Most wins", then back to "Best match". Click the star on a card: Shortlist in the
header goes to 1. (That header pill is also a toggle that shows only the shortlisted builders.)

> "Each card shows hackathons, wins and repos, and one line on why they fit. Drop a filter and the
> ranking updates right away: it's plain arithmetic, never a model. Tabs split builders by type, and
> I can sort by wins or hackathons. I'll shortlist this one. Seen counts the entries I've opened."

### 1:30–2:00 · A Dex entry: why they fit, and EVs

**Do:** Click the top card; it grows into the Dex entry. Point at the match score, "k of 4 match",
and the small source under each row of "Why <first name> fits your search". On the trait board
("EVs · Effort"), point at a row's "From <project>" line and the "N / 510 EVs" total.

> "This is a Dex entry. Each row of 'why they fit' names its source: GitHub for code, Devpost for
> prizes and profiles, People Data Labs for education when we have it. EVs are effort points from
> the code they actually wrote, split by area, and each row names the projects behind it."

### 2:00–2:30 · IVs, field notes, signature projects

**Do:** Click "IVs · Traits" and point at "How <first name> ranks against the N builders in this
scan" and one tile's evidence line. In Field notes, point at a "Not listed" value and the "Looked in
…" line under it (press → to step to the next builder if this one has every field). In Signature
projects, point at "<first name> wrote N%" and the prize.

> "IVs compare them with everyone in this scan, from 0 to 31, and each tile says why. When we can't
> find something, the entry says 'Not listed' and where we looked; we never fill a gap with a guess.
> And each project shows how much of its counted code this person wrote."

### 2:30–3:00 · Say hi

**Do:** Click "Say hi". Point at the subject line and at [ROLE], [COMPANY] and [TEAM OR PRODUCT].
Click "Copy email" (it reads "Copied!"). Press → to show the next builder, then Esc to go back to
the grid.

> "Say hi drafts an email from their top project, with the parts only I know left in brackets. One
> click copies it. The arrow keys walk the ranked list, and Escape goes back to the grid."

### 3:00–3:30 · A topic search

**Do:** Click "New scan", replace the text with "Built a RAG pipeline" and click "Start scan". Point
at the chips: ML / AI, Backend and the "RAG pipeline" topic. When the scan finishes, open the first
card and point at the "RAG pipeline" row: "Built <project> (wrote N%)". A builder who wrote less
than a quarter of that project gets Close instead: "Wrote N% of <project>".

> "Recruiters also ask for a kind of project. 'Built a RAG pipeline' becomes two skill types plus a
> topic. We embedded every project write-up ahead of time and compare the topic with all of them. A
> project counts when it stands well above the rest and this person wrote at least a quarter of
> it; the row names it and their share."

### 3:30–4:00 · Close on trust

**Do:** On the same entry, scroll to Field notes and point at the green line under the links ("…
linked from <first name>'s own Devpost profile, so this is the right person.").

> "Last, trust. We never match people across sites by name. We only follow the GitHub and LinkedIn
> links people posted on their own Devpost profile, and commit authors we can't place stay unknown.
> Every number on this page links back to where it came from. That's Talent Dex."

## Troubleshooting

### Port already in use

`npm run dev` moves to the next free port when 3000 is taken and says so ("Port 3000 is in use by
process …, using available port 3001 instead"); open the URL it prints. An explicit port, such as
Playwright's `--port 3100`, fails instead. See what holds it with
`lsof -nP -iTCP:3100 -sTCP:LISTEN` and stop it if it's yours, or run the tests on another port:
`E2E_PORT=3200 npx playwright test`.

### "Another next dev server is already running"

Only one `next dev` can run in this folder at a time. Next keeps a lock in `.next/dev/lock` and
prints the running server's URL and PID: use that server, or stop it (`kill <pid>`) and start again.
`pgrep -fl next-server` lists running servers. This includes Playwright, whose web server is a
`next dev --port 3100`: stop `npm run dev` first, or start your own server on port 3100 so
Playwright reuses it. A reused server keeps the `DATA_SOURCE` it was started with, whatever the
test command says.

### "No data/builders.json yet"

Real-data mode can't find the pipeline output. `/api/builders` and `/api/scan` answer 404, screen 1
shows "Something went wrong" with "No data/builders.json yet. Run the pipeline or set
DATA_SOURCE=sample.", and screen 0 leaves out the "Scanning …" line. Run the pipeline, restore the
committed copy with `git restore data/builders.json`, or use `npm run dev` for the sample.

If the file is there but isn't valid JSON or a Talent Dex dataset, screen 1 shows "Couldn't read the
builders data." and the server log (the terminal running `next dev`) says why, for example
"/api/builders: data/builders.json is not a Talent Dex dataset (version 1)". `/api/scan` logs the
same reason.

### Topic search answers 409 with sample data

The sample builders have no project write-ups, so `/api/topic` answers 409 ("Topic search needs the
real data (DATA_SOURCE=real)."). The topic row then reads "Couldn't check projects for this topic"
and the rest of the search still ranks; "Try again" in the scan panel asks once more. A topic check
that takes over 15 seconds is given up the same way. Use `npm run dev:real`. A 404 from `/api/topic`
means `data/embeddings.json` is missing: run `node scripts/embed.mjs`.

### Embedding model in `.cache/models/`

`node scripts/embed.mjs` downloads `Snowflake/snowflake-arctic-embed-m-v1.5` (q8 ONNX, about 100 MB)
from Hugging Face on its first run and loads it from `.cache/models/` (gitignored) after that,
offline. If a download was cut off and loading fails, delete `.cache/models/` and run it again. The
app loads the model only for a topic that wasn't embedded ahead of time, and only a live Gemini
parse can produce one; every cached search's topic is already in `data/embeddings.json`, so the
demo never loads it. After caching a new search with a topic, run `node scripts/embed.mjs` again.

### A search shows the wrong chips

Only texts in `data/searches.json` get Gemini's cached answer (case and spacing don't matter).
Anything else is parsed by the keyword rules, and `/api/parse` answers with `"source": "rules"`.
Cache new texts with `scripts/cache-searches.mjs` (step 2 of rebuilding the data).

### Playwright can't find a browser

Run `npx playwright install chromium`.
