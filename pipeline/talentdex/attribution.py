"""Who wrote what, from a cached git extract (see gitrepo.py).

Rules (BUILD.md, "Attribution"):
- A commit counts only if its author date (original timezone) is inside the
  hackathon window [start, end].
- Excluded: build output, lockfiles, node_modules, vendored code, binaries,
  minified/generated files, non-code files, and any file that already existed
  in the repo's first commit when that commit predates the event (starter
  templates; followed through renames).
- Lines are `git log --numstat` added lines per author per file.
- Authors map to Devpost team members by GitHub login / noreply address /
  exact email first, then by name *within that team only*. Anyone else stays
  "unknown"; nobody is guessed.
- wrote N% = a member's share of all counted added lines in the repo
  (unknown authors stay in the denominator). If one author has > 90% and the
  team has 3+ members, the project gets the caveat
  "possible shared laptop or squashed commits".
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from .files import counted_reason, is_readme, looks_minified

SHARED_LAPTOP = "possible shared laptop or squashed commits"
NOREPLY = re.compile(r"^(?:\d+\+)?([A-Za-z0-9-]+)@users\.noreply\.github\.com$", re.I)
# A safety valve against generated files that slip past every name rule
# (huge notebooks with outputs, data dumped into .py): per file, per commit.
MAX_LINES_PER_FILE_COMMIT = 2000


@dataclass(frozen=True)
class Member:
    username: str  # Devpost username
    name: str  # Devpost display name
    github: str | None = None  # from the GitHub link on their own Devpost profile
    email: str | None = None  # public email on that GitHub account, if any


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s.lower())).strip()


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def identity_key(email: str, name: str) -> str:
    e = (email or "").strip().lower()
    return e if e else "name:" + norm_name(name)


def resolve_identities(commits: list[dict], logins: dict[str, str | None], team: list[Member]) -> dict[str, dict]:
    """identity key -> {member, method, names, logins}. member is None when unmapped."""
    groups: dict[str, dict] = {}
    for c in commits:
        k = identity_key(c["ae"], c["an"])
        g = groups.setdefault(k, {"names": set(), "logins": set(), "email": (c["ae"] or "").strip().lower()})
        if c["an"]:
            g["names"].add(c["an"])
        login = logins.get(c["sha"])
        if login:
            g["logins"].add(login)

    by_gh = {m.github.lower(): m for m in team if m.github}
    by_email = {m.email.lower(): m for m in team if m.email}

    out: dict[str, dict] = {}
    for k, g in groups.items():
        member: Member | None = None
        method = "unknown"
        # 1. GitHub username: the account GitHub links this commit's email to.
        hits = {by_gh[l.lower()].username: by_gh[l.lower()] for l in g["logins"] if l.lower() in by_gh}
        if len(hits) == 1:
            member, method = next(iter(hits.values())), "github-login"
        # 2. GitHub username from a noreply address.
        if member is None:
            m = NOREPLY.match(g["email"])
            if m and m.group(1).lower() in by_gh:
                member, method = by_gh[m.group(1).lower()], "github-noreply"
        # 3. Exact email (public email on the member's GitHub account).
        if member is None and g["email"] in by_email:
            member, method = by_email[g["email"]], "email"
        # 4. Name, within this team only: full name, same words in any order,
        #    or the git name is the member's Devpost/GitHub username.
        if member is None:
            cands: dict[str, Member] = {}
            for n in g["names"]:
                nn = norm_name(n)
                words = set(nn.split())
                for t in team:
                    tn = norm_name(t.name)
                    if nn and (nn == tn or (len(words) >= 2 and words == set(tn.split()))):
                        cands[t.username] = t
                    elif _compact(n) and _compact(n) in {_compact(t.username), _compact(t.github or "")}:
                        cands[t.username] = t
            if len(cands) == 1:
                member, method = next(iter(cands.values())), "name-in-team"
        out[k] = {
            "member": member.username if member else None,
            "method": method,
            "names": sorted(g["names"]),
            "logins": sorted(g["logins"]),
        }
    return out


def attribute(
    extract: dict,
    start: datetime,
    end: datetime,
    team: list[Member],
    logins: dict[str, str | None] | None = None,
) -> dict:
    """Attribute counted lines in one repo to team members."""
    logins = logins or {}
    commits = extract["commits"]
    ids = resolve_identities(commits, logins, team)

    def who(c: dict) -> str:
        k = identity_key(c["ae"], c["an"])
        m = ids[k]["member"]
        return m if m else "unknown:" + k

    # Starter template: files in the first commit, when it predates the event.
    template: set[str] = set()
    roots = sorted(extract.get("roots", []), key=lambda r: parse_date(r["ad"]))
    template_applied = False
    if roots and parse_date(roots[0]["ad"]) < start:
        template = set(roots[0]["files"])
        template_applied = True

    head = extract.get("head_files", {})

    def reason(path: str) -> str | None:
        r = counted_reason(path)
        if r:
            return r
        h = head.get(path)
        if h and looks_minified(h["lines"], h["chars"], h["max_line"]):
            return "minified"
        return None

    file_lines: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    person_commits: dict[str, int] = defaultdict(int)
    excluded: dict[str, int] = defaultdict(int)
    kept: set[str] = set()
    readme_lines: dict[str, int] = defaultdict(int)
    capped = 0
    in_window = 0
    counted_commits = 0

    # Oldest first, so template paths follow renames forward.
    for c in sorted(commits, key=lambda c: parse_date(c["ad"])):
        when = parse_date(c["ad"])
        author = who(c)
        inside = start <= when <= end
        after = when > end
        touched_code = False
        counted_here = 0
        for path, added, _deleted, renamed_from in c["files"]:
            if renamed_from and renamed_from in template:
                template.add(path)
            if is_readme(path) and added:
                readme_lines[author] += added
            if added is None:
                if inside:
                    excluded["binary"] += 1
                continue
            r = reason(path)
            if r is None and path in template:
                r = "starter-template"
            if r is not None:
                if inside:
                    excluded[r] += added
                continue
            touched_code = True
            if inside and added:
                n = added
                if n > MAX_LINES_PER_FILE_COMMIT:
                    capped += n - MAX_LINES_PER_FILE_COMMIT
                    n = MAX_LINES_PER_FILE_COMMIT
                file_lines[path][author] += n
                counted_here += n
        if inside:
            in_window += 1
            if counted_here:
                counted_commits += 1
                person_commits[author] += 1
        if after and touched_code and not author.startswith("unknown:"):
            kept.add(author)

    totals: dict[str, int] = defaultdict(int)
    for path, by in file_lines.items():
        for a, n in by.items():
            totals[a] += n
    lines_total = sum(totals.values())

    people = {}
    unknown = {}
    for a, n in totals.items():
        share = round(100 * n / lines_total) if lines_total else 0
        files = {p: by[a] for p, by in file_lines.items() if by.get(a)}
        if a.startswith("unknown:"):
            k = a[len("unknown:"):]
            unknown[k] = {"lines": n, "share": share, "names": ids[k]["names"], "commits": person_commits[a]}
        else:
            people[a] = {"lines": n, "share": share, "files": files, "commits": person_commits[a]}

    top = max(totals.items(), key=lambda kv: kv[1])[0] if totals else None
    flags = []
    if top and lines_total and totals[top] / lines_total > 0.9 and len(team) >= 3:
        flags.append(SHARED_LAPTOP)

    readme = extract.get("readme")
    readme_out = None
    if readme:
        author = max(readme_lines.items(), key=lambda kv: kv[1])[0] if readme_lines else None
        readme_out = {"path": readme["path"], "chars": readme["chars"], "author": author}

    return {
        "repo": extract["slug"],
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "commits_total": len(commits),
        "commits_in_window": in_window,
        "commits_counted": counted_commits,
        "lines_total": lines_total,
        "people": people,
        "unknown": unknown,
        "files": {p: dict(by) for p, by in file_lines.items()},
        "top_author": top,
        "flags": flags,
        "kept": sorted(kept),
        "readme": readme_out,
        "template": {"applied": template_applied, "files": len(template) if template_applied else 0},
        "excluded": dict(excluded),
        "capped_lines": capped,
        "identities": ids,
    }


def file_share(result: dict, path: str) -> dict[str, float]:
    """Share (0..1) of a file's counted lines per author."""
    by = result["files"].get(path, {})
    total = sum(by.values())
    return {a: n / total for a, n in by.items()} if total else {}
