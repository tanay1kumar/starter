"""Step 6 (scores): turn per-project evidence into the numbers on screen.

Exactly BUILD.md "How every number is computed":
  EV_t   = min(252, round(510 * maturity * share_t)),
           share_t = builder's counted lines in type t / all their counted lines,
           maturity = min(1, projects with counted code / 6)
  IVs    = round(31 * percentile_rank) among builders in this scan, from raw values:
           Ships demos   projects with a demo video or working live URL / hackathons
           Wins          prizes won (tie-break: prizes / hackathons)
           Ownership     projects where they wrote the most counted lines / hackathons
           Teamwork      distinct teammates across all projects
           Persistence   projects with code commits after the event ended / hackathons
           Documentation projects whose README has > 300 chars they wrote (blame) / hackathons
  Cards  = Devpost hackathon count, prizes on Devpost, public GitHub repos;
           types = top one or two EV types (second only if >= 60% of the first);
           dex = stable 4-digit id from a hash of the Devpost username.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

TYPE_KEYS = ["ml", "backend", "frontend", "design", "mobile", "hardware"]
TRAITS = ["demo", "wins", "own", "team", "persist", "docs"]


@dataclass
class ProjectView:
    """One hackathon project as seen from one builder."""

    slug: str
    name: str
    tagline: str
    url: str
    event: str
    prizes: list[str]
    repos: list[str]
    in_scan: bool
    demo: bool
    teammates: list[str]  # Devpost usernames of the other members
    analyzed: bool = False  # at least one repo was attributed
    lines: int = 0  # this builder's counted lines across the project's repos
    total_lines: int = 0  # everyone's counted lines across the project's repos
    lines_by_type: dict[str, int] = field(default_factory=dict)
    top: bool = False  # wrote the most counted lines of anyone
    kept: bool = False  # code commits after the event
    readme: bool = False  # wrote the README (> 300 chars)
    flags: list[str] = field(default_factory=list)

    @property
    def share(self) -> int | None:
        if not self.analyzed:
            return None
        return round(100 * self.lines / self.total_lines) if self.total_lines else 0

    @property
    def main_type(self) -> str | None:
        if not self.lines_by_type:
            return None
        return max(self.lines_by_type.items(), key=lambda kv: kv[1])[0]


def project_view(username: str, project: dict, results: list[dict], classes: dict[str, dict[str, str]], demo: bool, in_scan: bool) -> ProjectView:
    """Combine the attribution results of a project's repos for one builder."""
    subs = project.get("submissions", [])
    event = (project.get("window") or {}).get("hackathon") or (subs[0]["hackathon"] if subs else "")
    prizes = [p for s in subs for p in s.get("prizes", [])]
    v = ProjectView(
        slug=project["slug"], name=project.get("name") or project["slug"], tagline=project.get("tagline", ""),
        url=project.get("url", ""), event=event, prizes=prizes, repos=list(project.get("repos", [])),
        in_scan=in_scan, demo=demo,
        teammates=[m["username"] for m in project.get("members", []) if m["username"] != username],
    )
    per_identity: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    for r in results:
        if "skip" in r:
            continue
        v.analyzed = True
        v.total_lines += r["lines_total"]
        for who, d in r["people"].items():
            per_identity[who] += d["lines"]
        for k, d in r["unknown"].items():
            per_identity["unknown:" + k] += d["lines"]
        mine = r["people"].get(username)
        if mine:
            repo_classes = classes.get(r["repo"], {})
            for path, n in mine["files"].items():
                t = repo_classes.get(path)
                if t in TYPE_KEYS:  # the orchestrator classifies every path a builder touched
                    by_type[t] += n
        if username in r.get("kept", []):
            v.kept = True
        rd = r.get("readme")
        # Documentation: more than 300 characters of the current README are theirs (git blame).
        if rd and (rd.get("by") or {}).get(username, 0) > 300:
            v.readme = True
        for fl in r.get("flags", []):
            if fl not in v.flags:
                v.flags.append(fl)
    v.lines = per_identity.get(username, 0)
    v.lines_by_type = {k: n for k, n in by_type.items() if n > 0}
    if v.lines > 0:
        others = [n for who, n in per_identity.items() if who != username]
        v.top = v.lines > max(others, default=0)
    return v


def evs(projects: list[ProjectView]) -> tuple[dict[str, int], dict[str, list[str]], int]:
    """EV per type, the projects behind each type (most lines first), and projects with code."""
    lines: dict[str, int] = defaultdict(int)
    for p in projects:
        for t, n in p.lines_by_type.items():
            lines[t] += n
    total = sum(lines.values())
    code_projects = sum(1 for p in projects if p.lines > 0)
    maturity = min(1.0, code_projects / 6)
    ev = {t: (min(252, round(510 * maturity * lines[t] / total)) if total else 0) for t in TYPE_KEYS}
    # Per-type rounding can overshoot the 510 total by a point or two; trim the largest.
    over = sum(ev.values()) - 510
    if over > 0:
        biggest = max(TYPE_KEYS, key=lambda t: ev[t])
        ev[biggest] -= over
    ev_from = {}
    for t in TYPE_KEYS:
        ranked = sorted((p for p in projects if p.lines_by_type.get(t)), key=lambda p: -p.lines_by_type[t])
        if ranked:
            ev_from[t] = [p.name for p in ranked]
    return ev, ev_from, code_projects


def card_types(ev: dict[str, int]) -> list[str]:
    ranked = sorted((t for t in TYPE_KEYS if ev.get(t, 0) > 0), key=lambda t: -ev[t])
    if not ranked:
        return []
    if len(ranked) > 1 and ev[ranked[1]] >= 0.6 * ev[ranked[0]]:
        return ranked[:2]
    return ranked[:1]


def trait_counts(projects: list[ProjectView]) -> dict[str, int]:
    mates: set[str] = set()
    for p in projects:
        mates.update(p.teammates)
    return {
        "demo": sum(1 for p in projects if p.demo),
        "own": sum(1 for p in projects if p.top),
        "mates": len(mates),
        "kept": sum(1 for p in projects if p.kept),
        "docs": sum(1 for p in projects if p.readme),
    }


def iv_raw(n: dict[str, int], wins: int, hacks: int) -> dict[str, tuple]:
    h = max(1, hacks)
    return {
        "demo": (n["demo"] / h,),
        "wins": (wins, wins / h),
        "own": (n["own"] / h,),
        "team": (n["mates"],),
        "persist": (n["kept"] / h,),
        "docs": (n["docs"] / h,),
    }


def percentile_ivs(raw: dict[str, dict[str, tuple]]) -> dict[str, list[int]]:
    """IV = round(31 * share of other builders with a strictly lower raw value)."""
    ids = list(raw)
    n = len(ids)
    out: dict[str, list[int]] = {i: [] for i in ids}
    for trait in TRAITS:
        vals = sorted(raw[i][trait] for i in ids)
        for i in ids:
            v = raw[i][trait]
            lower = _count_lower(vals, v)
            out[i].append(round(31 * lower / (n - 1)) if n > 1 else 31)
    return out


def _count_lower(sorted_vals: list[tuple], v: tuple) -> int:
    lo, hi = 0, len(sorted_vals)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_vals[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return lo


def dex_numbers(usernames: list[str]) -> dict[str, str]:
    """Stable 4-digit ids from sha1(username); collisions step to the next free number."""
    taken: set[int] = set()
    out = {}
    for u in sorted(usernames, key=lambda s: s.lower()):
        n = int(hashlib.sha1(u.lower().encode()).hexdigest(), 16) % 10000
        while n in taken or n == 0:
            n = (n + 1) % 10000
        taken.add(n)
        out[u] = f"{n:04d}"
    return out


def signature(projects: list[ProjectView], k: int = 3) -> list[ProjectView]:
    """Projects with their code first, prize winners next, then by lines written."""
    return sorted(projects, key=lambda p: (p.lines > 0, bool(p.prizes), p.lines, p.in_scan), reverse=True)[:k]
