"""Attribute one Devpost project's repo(s) to its team.

    python -m talentdex.analyze plant-hopper            # summary
    python -m talentdex.analyze plant-hopper --file UniversalControl.ino
"""

from __future__ import annotations

import argparse
import json
import sys

from . import devpost, github
from .attribution import Member, attribute, file_share
from .gitrepo import RepoSkip, extract


def team_for(project: dict) -> list[Member]:
    """Devpost team members with the GitHub account linked on their own profile."""
    team = []
    for m in project["members"]:
        prof = devpost.fetch_profile(m["username"])
        gh = prof["github"] if prof else None
        u = github.user(gh) if gh else None
        team.append(Member(username=m["username"], name=(prof or {}).get("name") or m["name"], github=gh,
                           email=(u or {}).get("email"), gh_name=(u or {}).get("name")))
    return team


def window_for(project: dict, hackathon_name: str | None = None) -> dict:
    """Submission window of the project's hackathon (the named one, else the first).
    Raises ValueError when the project was not submitted to the named hackathon."""
    subs = project["submissions"]
    if hackathon_name:
        want = devpost.norm_title(hackathon_name)
        subs = [s for s in subs if devpost.norm_title(s["hackathon"]) == want]
        if not subs:
            sent = ", ".join(s["hackathon"] for s in project["submissions"]) or "none"
            raise ValueError(f"{project['slug']} has no submission to {hackathon_name!r} (submitted to: {sent})")
    for s in subs:
        try:
            return {**devpost.hackathon_window({"url": s["url"], "title": s["hackathon"]}), "hackathon": s["hackathon"], "url": s["url"]}
        except (ValueError, KeyError):
            h = devpost.find_hackathon(s["hackathon"])
            if h:
                return {**devpost.hackathon_window(h), "hackathon": h["title"], "url": h["url"]}
    raise ValueError(f"no hackathon window for {project['slug']}")


def analyze_repo(slug: str, win: dict, team: list[Member]) -> dict:
    ex = extract(slug)
    try:
        logins = github.commit_logins(slug, ex["branch"], ex["commits"])
    except RuntimeError as e:  # rate limit or outage
        raise RepoSkip(f"GitHub login lookup failed: {e}", retryable=True) from None
    start, end = devpost.window_bounds(win)
    return attribute(ex, start, end, team, logins)


def analyze_project(slug_or_url: str, hackathon_name: str | None = None) -> dict:
    project = devpost.fetch_project(slug_or_url)
    if project is None:
        raise SystemExit(f"Devpost project not found: {slug_or_url}")
    win = window_for(project, hackathon_name)
    team = team_for(project)
    repos = {}
    for slug in project["repos"]:
        try:
            repos[slug] = analyze_repo(slug, win, team)
        except RepoSkip as e:
            repos[slug] = {"skip": str(e), "retryable": e.retryable}
    return {"project": project, "window": win, "team": [m.__dict__ for m in team], "repos": repos}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", help="Devpost software slug or URL")
    ap.add_argument("--hackathon", help="which submission's window to use (default: the first)")
    ap.add_argument("--file", help="also print who wrote this file (path suffix match)")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = ap.parse_args(argv)

    out = analyze_project(args.project, args.hackathon)
    if args.json:
        json.dump(out, sys.stdout, indent=2, default=str)
        return 0
    p, win = out["project"], out["window"]
    print(f"{p['name']}  ({p['url']})")
    print(f"window: {win['start']} -> {win['end']}  [{win['source']}, {win['hackathon']}]")
    for m in out["team"]:
        print(f"  member {m['username']:<16} github={m['github'] or '-'}")
    for slug, r in out["repos"].items():
        if "skip" in r:
            print(f"repo {slug}: skipped ({r['skip']})")
            continue
        print(f"repo {slug}: {r['commits_in_window']} of {r['commits_total']} commits in window, {r['lines_total']} counted lines")
        for who, d in sorted(r["people"].items(), key=lambda kv: -kv[1]["lines"]):
            print(f"  {who:<16} wrote {d['share']:>3}%  ({d['lines']} lines, {d['commits']} commits)")
        for k, d in r["unknown"].items():
            print(f"  unknown {k:<30} {d['share']:>3}%  ({d['lines']} lines; names {d['names']})")
        print(f"  identities: " + "; ".join(f"{k} -> {v['member'] or 'unknown'} ({v['method']})" for k, v in r["identities"].items()))
        print(f"  flags: {r['flags'] or 'none'}  kept building: {r['kept'] or 'nobody'}  readme: {r['readme']}")
        print(f"  excluded lines: {r['excluded']}  template: {r['template']}  replayed: {r['replayed_lines']}  capped: {r['capped_lines']}")
        if args.file:
            paths = [f for f in r["files"] if f.endswith(args.file)]
            for f in paths:
                sh = file_share(r, f)
                print(f"  file {f}: " + ", ".join(f"{a} {v:.0%}" for a, v in sorted(sh.items(), key=lambda kv: -kv[1])) + f"  ({sum(r['files'][f].values())} lines)")
            if not paths:
                print(f"  file {args.file}: no counted lines in the window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
