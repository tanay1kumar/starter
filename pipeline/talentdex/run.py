"""Run the whole pipeline and write data/builders.json.

    cd pipeline && .venv/bin/python -m talentdex.run              # full run (resumes from cache)
    .venv/bin/python -m talentdex.run --portfolio-cap 0           # scanned projects only (fast)
    .venv/bin/python -m talentdex.run --no-words                  # template lines instead of Gemini

Steps (BUILD.md "Data pipeline"): 1 hackathons, 2 projects, 3 people,
4 code (clone, attribute, classify), 5 enrichment, 6 scores, 7 words,
8 output. Every network answer is cached, so a re-run is free.

Who becomes a builder: a member of a scanned project with a public Devpost
profile (where their GitHub/LinkedIn links come from) and counted, classified
code in a scanned repo. Their other Devpost hackathon projects (the
portfolio) are then read too, so per-hackathon numbers cover their history.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from . import code as code_step
from . import crawl, devpost, github, gitrepo
from .attribution import Member
from .config import CACHE_DIR, DATA_DIR
from .gitrepo import RepoSkip, extract
from .output import write_json, write_projects
from .scores import (
    TYPE_KEYS, ProjectView, card_types, dex_numbers, evs, iv_raw, percentile_ivs, project_view, signature, trait_counts,
)

STEPS_DIR = CACHE_DIR / "steps"
T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def abbr(name: str) -> str:
    words = [w for w in "".join(c if c.isalnum() else " " for c in name).split() if w]
    if not words:
        return "?"
    second = words[1][0] if len(words) > 1 else (words[0][1] if len(words[0]) > 1 else "")
    return words[0][0].upper() + second.lower()


def save_step(name: str, data) -> None:
    STEPS_DIR.mkdir(parents=True, exist_ok=True)
    (STEPS_DIR / f"{name}.json").write_text(json.dumps(data, indent=1, default=str))


def pmap(fn, items: list, workers: int) -> list:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


# ---------------------------------------------------------------- steps 1-3

def step_targets(total: int) -> tuple[list[dict], dict[str, dict]]:
    """The target hackathons and {project slug: hackathon} for the scan."""
    hackathons = crawl.resolve_targets()
    public = []
    for h in hackathons:
        if h.get("gallery_public") and h.get("window"):
            public.append(h)
            log(f"hackathon {h['title']!r}: window {h['window']['start']} -> {h['window']['end']} ({h['window']['source']})")
        else:
            log(f"hackathon {h.get('name')!r}: skipped ({h.get('note') or 'gallery not public yet'})")
    quota = crawl.quota_for(total, len(public))
    targets: dict[str, dict] = {}
    for h in public:
        stats: dict = {}
        slugs = crawl.select_targets(h, quota, skip=targets.keys(), stats=stats)
        log(f"  {h['title']}: {len(slugs)} projects with a GitHub repo (quota {quota})")
        for s in slugs:
            targets.setdefault(s, h)
    return hackathons, targets


def step_projects(targets: dict[str, dict]) -> dict[str, dict]:
    projects = {}
    for slug, h in targets.items():
        p = devpost.fetch_project(slug)
        if not p:
            continue
        p["window"] = {**h["window"], "hackathon": h["title"], "url": h["url"]}
        p["in_scan"] = True
        projects[slug] = p
    return projects


def step_portfolios(builders: set[str], projects: dict[str, dict], profiles: dict[str, dict | None],
                    cap: int) -> dict[str, list[str]]:
    """Each builder's hackathon projects: scanned ones plus their Devpost portfolio (capped)."""
    mine: dict[str, list[str]] = defaultdict(list)
    for slug, p in projects.items():
        for m in p["members"]:
            if m["username"] in builders:
                mine[m["username"]].append(slug)
    if cap <= 0:
        return mine
    wanted = {u: crawl.portfolio_slugs(profiles[u], cap=cap) for u in sorted(builders)}
    new = sorted({s for ss in wanted.values() for s in ss} - set(projects))
    log(f"portfolio: {len(new)} more project pages for {len(builders)} builders")
    extra = crawl.hackathon_projects(new)
    no_window = 0
    for slug, p in extra.items():
        win = None
        for sub in p["submissions"]:
            w = crawl.submission_window(sub)
            if w:
                win = {**w, "hackathon": sub["hackathon"] or w.get("hackathon"), "url": sub["url"] or w.get("url")}
                break
        if win is None:
            no_window += 1
        p["window"] = win
        p["in_scan"] = False
        projects[slug] = p
    log(f"portfolio: {len(extra)} hackathon projects ({no_window} without a submission window)")
    for u, ss in wanted.items():
        for slug in ss:
            p = projects.get(slug)
            if p and slug not in mine[u] and any(m["username"] == u for m in p["members"]):
                mine[u].append(slug)
    return mine


# ---------------------------------------------------------------- step 4

def team_of(p: dict, profiles: dict[str, dict | None], gh_users: dict[str, dict | None]) -> list[Member]:
    """Devpost team members with the GitHub account linked on their own profile."""
    team = []
    for m in p["members"]:
        prof = profiles.get(m["username"])
        gh = prof.get("github") if prof else None
        u = gh_users.get(gh.lower()) if gh else None
        team.append(Member(username=m["username"], name=(prof or {}).get("name") or m["name"], github=gh,
                           email=(u or {}).get("email"), gh_name=(u or {}).get("name")))
    return team


def step_code(projects: dict[str, dict], profiles: dict[str, dict | None], gh_users: dict[str, dict | None],
              workers: int, max_repos: int = 3) -> dict[tuple[str, str], dict]:
    jobs = []
    for slug, p in projects.items():
        if not p.get("window"):
            continue
        team = team_of(p, profiles, gh_users)
        for repo in p["repos"][:max_repos]:
            jobs.append((slug, repo, p["window"], team))
    log(f"code: {len(jobs)} repo jobs across {len(projects)} projects")
    last = [0.0]

    def progress(done: int, total: int, what: str) -> None:
        if done == total or time.time() - last[0] > 30:
            last[0] = time.time()
            log(f"  code {done}/{total}: {what}")

    results = code_step.analyze_many(jobs, workers=workers, progress=progress)
    retry = [j for j in jobs if results[(j[0], j[1])].get("retryable")]
    if retry:
        log(f"  retrying {len(retry)} repos that failed for temporary reasons, in 60 s")
        time.sleep(60)
        results.update(code_step.analyze_many(retry, workers=max(1, workers // 2), progress=progress))
    return results


def step_classify(results: dict[tuple[str, str], dict], builders: set[str], projects: dict[str, dict],
                  workers: int) -> dict[str, dict[str, str]]:
    """Types for every file a builder wrote (rules first, Gemini for leftovers)."""
    from . import classify

    paths_by_repo: dict[str, set[str]] = defaultdict(set)
    private_by_repo: dict[str, set[str]] = defaultdict(set)
    for (slug, repo), r in results.items():
        if "skip" in r:
            continue
        for u, d in r["people"].items():
            if u in builders:
                paths_by_repo[repo].update(d["files"])
        for m in projects[slug]["members"]:
            private_by_repo[repo].update(x for x in (m["username"], m.get("name")) if x)
        for ident in r.get("identities", {}).values():
            private_by_repo[repo].update(ident.get("names", []))
            private_by_repo[repo].update(ident.get("logins", []))
    repos = sorted(paths_by_repo)
    asked = sum(len(v) for v in paths_by_repo.values())
    log(f"classify: {asked} files in {len(repos)} repos")

    def one(repo: str) -> dict[str, str]:
        try:
            ex = extract(repo)
        except RepoSkip:
            return {}
        return classify.classify_repo(ex, sorted(paths_by_repo[repo]), private=sorted(private_by_repo[repo]))

    out = dict(zip(repos, pmap(one, repos, workers)))
    log(f"  classified {sum(len(v) for v in out.values())} of {asked} files")
    return out


def step_demos(slugs: list[str], projects: dict[str, dict]) -> dict[str, bool]:
    """A demo video on Devpost, or a "Try it out" link that loads a real page."""
    crawl.prefetch_live([projects[s] for s in slugs if not projects[s].get("video")], workers=8)
    return {s: bool(crawl.project_demo(projects[s])["demo"]) for s in slugs}


# ---------------------------------------------------------------- steps 5-8

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--total", type=int, default=214, help="target number of scanned projects (default 214)")
    ap.add_argument("--portfolio-cap", type=int, default=30, help="Devpost projects per builder to read (0 = scanned only)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-words", action="store_true", help="template lines instead of Gemini words")
    ap.add_argument("--no-pdl", action="store_true", help="don't spend People Data Labs lookups")
    ap.add_argument("--no-clone", action="store_true", help="analyse only repos already cloned and cached; skip the rest")
    ap.add_argument("--out", default=str(DATA_DIR / "builders.json"))
    args = ap.parse_args(argv)
    gitrepo.NO_CLONE = args.no_clone

    from . import enrich

    today = date.today()
    log("step 1: hackathons")
    hackathons, targets = step_targets(args.total)

    log("step 2: projects")
    projects = step_projects(targets)
    log(f"  {len(projects)} scanned projects")

    log("step 3: people")
    members = sorted({m["username"] for p in projects.values() for m in p["members"]})
    people = crawl.load_people(members)
    profiles: dict[str, dict | None] = {u: r.get("profile") for u, r in people.items()}
    log(f"  {len(members)} team members, {sum(1 for v in profiles.values() if v)} public profiles")
    logins = sorted({prof["github"] for prof in profiles.values() if prof and prof.get("github")})
    gh_users = dict(zip([x.lower() for x in logins], pmap(github.user, logins, 4)))

    log("step 4: code (scanned projects)")
    results = step_code(projects, profiles, gh_users, args.workers)
    ok = {k: r for k, r in results.items() if "skip" not in r}
    builders = {u for r in ok.values() for u, d in r["people"].items() if d["lines"] > 0 and profiles.get(u)}
    log(f"  {len(ok)} repos analysed, {len(results) - len(ok)} skipped; {len(builders)} members with counted code")
    scan_ok = len(ok)
    scan_commits = sum(r["commits_counted"] for r in ok.values())

    log("step 4: code (builders' other hackathon projects)")
    mine = step_portfolios(builders, projects, profiles, args.portfolio_cap)
    portfolio = {s: p for s, p in projects.items() if not p.get("in_scan")}
    if portfolio:
        mates = sorted({m["username"] for p in portfolio.values() for m in p["members"]} - set(profiles))
        log(f"  {len(mates)} more teammates' Devpost profiles")
        profiles.update(zip(mates, pmap(devpost.fetch_profile, mates, 3)))
        results.update(step_code(portfolio, profiles, gh_users, args.workers))
        ok = {k: r for k, r in results.items() if "skip" not in r}
    by_project: dict[str, list[dict]] = defaultdict(list)
    for (slug, _repo), r in results.items():
        by_project[slug].append(r)
    skips: dict[str, int] = defaultdict(int)
    for r in results.values():
        if "skip" in r:
            skips[r["skip"].split(":")[0][:60]] += 1
    log(f"  {len(ok)} repos analysed in total; skipped: {dict(skips)}")

    classes = step_classify(results, builders, projects, args.workers)

    log("step 4: demos")
    slugs = sorted({s for u in builders for s in mine.get(u, [])})
    demo_of = step_demos(slugs, projects)

    views: dict[str, list[ProjectView]] = {}
    for u in sorted(builders):
        vs = [project_view(u, projects[s], by_project.get(s, []), classes, demo_of.get(s, False), projects[s].get("in_scan", False))
              for s in mine.get(u, []) if s in projects]
        # A builder needs classified code in at least one scanned project.
        if any(v.in_scan and v.lines_by_type for v in vs):
            views[u] = vs
    log(f"  {len(views)} builders with verified, attributed, classified code")

    log("step 5: enrichment")
    prof = {u: profiles[u] for u in views}
    wins_of = {u: sum(len(v.prizes) for v in vs) for u, vs in views.items()}
    lines_of = {u: sum(v.lines for v in vs) for u, vs in views.items()}
    pdl_data: dict[str, dict | None] = {u: None for u in views}
    if not args.no_pdl:
        order = sorted((u for u in views if prof[u].get("linkedin")), key=lambda u: (-wins_of[u], -lines_of[u], u))
        for u in order:
            pdl_data[u] = enrich.pdl_enrich(prof[u]["linkedin"])
            if pdl_data[u] is None and enrich.budget_left() <= 0:
                break
    note_of: dict[str, str] = {}
    for p in projects.values():
        for m in p["members"]:
            if m.get("note") and m["username"] not in note_of and p.get("in_scan"):
                note_of[m["username"]] = m["note"]
    facts = {u: enrich.person_facts(prof[u], pdl_data[u], member_note=note_of.get(u, ""), today=today) for u in views}
    ghf = dict(zip(views, pmap(lambda u: enrich.github_facts(prof[u].get("github")), list(views), 4)))
    log(f"  PDL matched {sum(1 for v in pdl_data.values() if v)} builders; {enrich.budget_left()} lookups left in the budget")

    log("step 6: scores")
    dex = dex_numbers(list(views))
    raw = {}
    core: dict[str, dict] = {}
    for u, vs in views.items():
        p = prof[u]
        # Devpost's own count; never fewer than the distinct hackathons we found projects for.
        hacks = max(int((p.get("counts") or {}).get("hackathons") or 0), len({v.event for v in vs if v.event}))
        wins = wins_of[u]
        ev, ev_from, code_projects = evs(vs)
        n = trait_counts(vs)
        raw[u] = iv_raw(n, wins, hacks)
        core[u] = {
            "id": u,
            "name": p.get("name") or u,
            "dex": dex[u],
            "types": card_types(ev),
            **facts[u],
            "lastActive": ghf[u]["lastActive"],
            "links": {
                "devpost": f"https://devpost.com/{u}",
                "github": f"https://github.com/{p['github']}" if p.get("github") else None,
                "linkedin": p.get("linkedin"),
            },
            "hacks": hacks,
            "wins": wins,
            "repos": ghf[u]["repos"],
            "why": "",
            "sum": "",
            "ev": ev,
            "evFrom": ev_from,
            "iv": [],
            "n": n,
            "codeProjects": code_projects,
            "typeProjects": {t: sum(1 for v in vs if v.lines_by_type.get(t)) for t in TYPE_KEYS},
            "projects": [
                {
                    "id": v.slug, "name": v.name, "abbr": abbr(v.name), "type": v.main_type, "event": v.event,
                    "desc": v.tagline, "prize": v.prizes[0] if v.prizes else "", "prizes": v.prizes, "kept": v.kept,
                    "share": v.share, "url": v.url, "repo": f"https://github.com/{v.repos[0]}" if v.repos else None,
                    "demo": v.demo, "flags": v.flags, "inScan": v.in_scan,
                }
                for v in signature(vs)
            ],
        }
    ivs = percentile_ivs(raw)
    for u in core:
        core[u]["iv"] = ivs[u]

    log("step 7: words")
    from . import words

    if args.no_words:
        lines = {u: words.template_words(core[u]) for u in core}
    else:
        lines = words.write_words(list(core.values()))
    for u, b in core.items():
        w = lines.get(u) or words.template_words(b)
        b["why"], b["sum"] = w["why"], w["sum"]

    log("step 8: output")
    scanned = {s: p for s, p in projects.items() if p.get("in_scan")}
    per_event: dict[str, int] = defaultdict(int)
    for p in scanned.values():
        per_event[p["window"]["url"]] += 1
    found_in: dict[str, list[str]] = defaultdict(list)
    for u in sorted(core):
        for s in mine.get(u, []):
            if s in scanned:
                found_in[s].append(u)
    dataset = {
        "version": 1,
        "source": "real",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scan": {
            "hackathons": [
                {"name": h["title"], "url": h["url"], "start": h["window"]["start"], "end": h["window"]["end"],
                 "projects": per_event.get(h["url"], 0)}
                for h in hackathons if h.get("gallery_public") and h.get("window")
            ],
            "projectsChecked": len(scanned),
            "reposChecked": scan_ok,
            "commitsCounted": scan_commits,
            "buildersFound": len(core),
            # Scan order for the replay: each scanned project and the builders it surfaced.
            "order": [{"id": s, "builders": found_in.get(s, [])} for s in targets if s in scanned],
        },
        "builders": sorted(core.values(), key=lambda b: b["id"]),
    }
    save_step("dataset", dataset)  # kept even when validation below fails, for debugging
    write_json(dataset, args.out)
    # Every project with a builder's counted code, for the topic search (embeddings, Postgres).
    by_slug: dict[str, list[dict]] = defaultdict(list)
    view_of: dict[str, ProjectView] = {}
    for u in sorted(core):
        for v in views[u]:
            if v.lines > 0:
                by_slug[v.slug].append({"id": u, "share": v.share})
                view_of.setdefault(v.slug, v)
    write_projects({
        "version": 1,
        "generatedAt": dataset["generatedAt"],
        "projects": [
            {"id": s, "name": view_of[s].name, "event": view_of[s].event, "tagline": view_of[s].tagline,
             "builtWith": projects[s].get("built_with") or [], "story": projects[s].get("story") or "",
             "url": view_of[s].url, "builders": by_slug[s]}
            for s in sorted(by_slug)
        ],
    }, Path(args.out).with_name("projects.json"))
    save_step("run", {
        "at": dataset["generatedAt"], "seconds": round(time.time() - T0), "portfolio_cap": args.portfolio_cap,
        "members": len(members), "builders_with_code": len(builders), "builders": len(core),
        "scanned_projects": len(scanned), "scanned_repos": sum(1 for (s, _r) in results if s in scanned),
        "scanned_repos_ok": scan_ok, "projects_total": len(projects), "repos_total": len(results), "repos_ok": len(ok),
        "skips": dict(skips), "pdl_matched": sum(1 for v in pdl_data.values() if v),
        "words": {k: sum(1 for w in lines.values() if w.get("source") == k) for k in ("gemini", "template")},
    })
    log(f"wrote {args.out}: {len(core)} builders from {len(scanned)} scanned projects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
