"""Who wrote what, from a cached git extract (format v3, see gitrepo.py).

Rules (BUILD.md, "Attribution"):
- A commit counts only if its author time is inside the hackathon window
  [start, end], compared as instants (git's %at), so odd offsets can't break it.
- Excluded: build output, lockfiles, node_modules, vendored code, binaries,
  minified/generated files and non-code files (files.counted_reason), and
  starter-template files: every file of every root commit authored before the
  event, followed through renames. A template path that is deleted stops being
  template. An edit also counts as template when the version it changes descends
  from a template file, so a rename or delete on a parallel branch can't free it.
  A new file identical to a template file (a copy) has only that commit's lines
  excluded: later edits to it are the team's.
- Lines are `git log --numstat` added lines per author per file (notebooks:
  code-cell sources only). A change that recreates a file version already seen
  at that path (merge replays, reverts, cherry-picks) credits nothing; those
  lines are reported as replayed_lines.
- Authors map to Devpost team members by GitHub login / noreply address / exact
  email first (for every commit with that email), then by name *within that team
  only*, separately for each name used with an email, so people who share an
  email are told apart. When the names on one email match exactly one member, a
  shorter form of that member's name on it ("Ann" next to "Ann Lee") is theirs
  too. Anyone else stays "unknown"; nobody is guessed.
- wrote N% = a member's share of all counted added lines in the repo
  (unknown authors stay in the denominator). If one author has > 90% and the
  team has 3+ members, the project gets the caveat
  "possible shared laptop or squashed commits".
- Kept building: a member's commit after kept_after (default: the end of the
  event's last day) that adds lines to counted code; the template rule does
  not apply there.
- README author: the member with the most surviving README characters by
  git blame at HEAD, ignoring lines from template roots.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from .files import counted_reason, looks_minified

SHARED_LAPTOP = "possible shared laptop or squashed commits"
NOREPLY = re.compile(r"^(?:\d+\+)?([A-Za-z0-9-]+)@users\.noreply\.github\.com$", re.I)
# A safety valve against generated files that slip past every name rule
# (huge notebooks with outputs, data dumped into .py): per file, per commit.
MAX_LINES_PER_FILE_COMMIT = 2000
# Letters that NFKD does not split into a base letter plus an accent.
_TRANSLIT = str.maketrans({"ł": "l", "đ": "d", "ø": "o", "ı": "i", "ß": "ss", "æ": "ae", "œ": "oe", "þ": "th"})
# Tutorial defaults: never evidence that two emails belong to the same person.
PLACEHOLDER_NAMES = {"your name", "full name", "first last", "firstname lastname", "user name", "john doe", "jane doe"}


@dataclass(frozen=True)
class Member:
    username: str  # Devpost username
    name: str  # Devpost display name
    github: str | None = None  # from the GitHub link on their own Devpost profile
    email: str | None = None  # public email on that GitHub account, if any
    gh_name: str | None = None  # name on that GitHub profile, if any


def norm_name(s: str) -> str:
    """Casefolded words without accents; letters of any script survive."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", s.casefold().translate(_TRANSLIT)))


def _compact(s: str) -> str:
    return "".join(norm_name(s).split())


def parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _name_key(name: str) -> str:
    return norm_name(name) or (name or "").strip()


def identity_key(email: str, name: str) -> str:
    """The email group of a commit: its lowercased email, or "name:<name>" without one."""
    e = (email or "").strip().lower()
    return e if e else "name:" + _name_key(name)


def commit_identity(ids: dict[str, dict], email: str, name: str) -> str:
    """Key in resolve_identities() output for a commit's (email, name)."""
    k = identity_key(email, name)
    return k if k in ids else f"{k}|{_name_key(name)}"


def _whole_email(g: dict, by_gh: dict[str, Member], by_email: dict[str, Member]) -> tuple[Member | None, str]:
    # 1. GitHub username: the account GitHub links this commit's email to.
    hits = {by_gh[l.lower()] for l in g["logins"] if l.lower() in by_gh}
    if len(hits) == 1:
        return next(iter(hits)), "github-login"
    # 2. GitHub username from a noreply address.
    m = NOREPLY.match(g["email"])
    if m and m.group(1).lower() in by_gh:
        return by_gh[m.group(1).lower()], "github-noreply"
    # 3. Exact email (public email on the member's GitHub account).
    if g["email"] and g["email"] in by_email:
        return by_email[g["email"]], "email"
    return None, "unknown"


def _name_hits(name: str, cands: dict[str, list[tuple[str, str]]], shared_firsts: set[str]) -> set[str]:
    """Members whose names match a git author name.

    Multi-word git names: same words (any order) as a name, or the same letters
    as a name or username. One-word git names: only a username/login or a
    one-word display name, and never a first name two teammates share.
    """
    nn = norm_name(name)
    if not nn:
        return set()
    one_word = len(name.split()) == 1  # counted on the original name
    if one_word and nn in shared_firsts:
        return set()
    words = set(nn.split())
    hits = set()
    for user, cs in cands.items():
        for cand, kind in cs:
            cn = norm_name(cand)
            if not cn:
                continue
            if kind == "id":
                ok = _compact(name) == _compact(cand)
            elif one_word:
                ok = kind == "name" and len(cand.split()) == 1 and nn == cn
            else:
                ok = nn == cn or (len(words) >= 2 and words == set(cn.split())) or _compact(name) == _compact(cand)
            if ok:
                hits.add(user)
                break
    return hits


def resolve_identities(commits: list[dict], logins: dict[str, str | None], team: list[Member]) -> dict[str, dict]:
    """identity key -> {member, method, names, logins}. member is None when unmapped.

    Keys are emails (or "name:<name>"). An email tied to a member by GitHub
    (login or noreply) or by the member's public email maps as a whole. Otherwise
    each name used with it is matched on its own, keyed "<email>|<name>" when the
    email carries more than one name (look keys up with commit_identity()).
    """
    groups: dict[str, dict] = {}
    for c in commits:
        k = identity_key(c.get("ae", ""), c.get("an", ""))
        g = groups.setdefault(k, {"email": (c.get("ae") or "").strip().lower(), "names": defaultdict(set), "logins": set()})
        g["names"][_name_key(c.get("an", ""))].add(c.get("an") or "")
        login = logins.get(c.get("sha", ""))
        if login:
            g["logins"].add(login)

    by_gh = {m.github.lower(): m for m in team if m.github}
    by_email = {m.email.strip().lower(): m for m in team if m.email}

    out: dict[str, dict] = {}
    proven: dict[str, set[str]] = defaultdict(set)  # git names proven for a member by steps 1-3
    pending = []
    for k, g in groups.items():
        member, method = _whole_email(g, by_gh, by_email)
        names = sorted(n for ns in g["names"].values() for n in ns if n)
        if member is None:
            pending.append((k, g))
            continue
        out[k] = {"member": member.username, "method": method, "names": names, "logins": sorted(g["logins"])}
        proven[member.username].update(names)

    # 4. Name, within this team only.
    cands: dict[str, list[tuple[str, str]]] = {}
    firsts: dict[str, set[str]] = defaultdict(set)
    for t in team:
        cs = [(t.username, "id")] + ([(t.github, "id")] if t.github else [])
        cs += [(n, "name") for n in (t.name, t.gh_name) if n]
        cs += [(n, "proven") for n in sorted(proven[t.username]) if norm_name(n) not in PLACEHOLDER_NAMES]
        cands[t.username] = cs
        for n in (t.name, t.gh_name):
            w = norm_name(n or "").split()
            if w:
                firsts[w[0]].add(t.username)
    shared_firsts = {w for w, users in firsts.items() if len(users) >= 2}

    by_user = {t.username: t for t in team}
    for k, g in pending:
        hits = {nk: set().union(*(_name_hits(n, cands, shared_firsts) for n in raw)) for nk, raw in g["names"].items()}
        found = {next(iter(h)) for h in hits.values() if len(h) == 1}
        if len(found) == 1:
            # The same person's shorter name on this email ("Ann" next to "Ann Lee"), never a
            # different name ("Dan Mentor") nor a first name two teammates share.
            m = by_user[next(iter(found))]
            words = {w for nk, h in hits.items() if h == {m.username} for w in norm_name(nk).split()}
            words |= {w for n in (m.name, m.gh_name) for w in norm_name(n or "").split()}
            for nk, h in hits.items():
                ws = norm_name(nk).split()
                if not h and ws and set(ws) <= words and not (len(ws) == 1 and ws[0] in shared_firsts):
                    hits[nk] = {m.username}
        split = len(g["names"]) > 1
        for nk, raw in g["names"].items():
            member = next(iter(hits[nk])) if len(hits[nk]) == 1 else None
            out[f"{k}|{nk}" if split else k] = {
                "member": member,
                "method": "name-in-team" if member else "unknown",
                "names": sorted(n for n in raw if n),
                "logins": sorted(g["logins"]),
            }
    return out


def attribute(
    extract: dict,
    start: datetime,
    end: datetime,
    team: list[Member],
    logins: dict[str, str | None] | None = None,
    kept_after: datetime | None = None,
) -> dict:
    """Attribute counted lines in one repo to team members.

    kept_after: commits after it count as "kept building"; default the end of the
    calendar day of `end`, in end's own offset.
    """
    logins = logins or {}
    commits = extract["commits"]
    readme = extract.get("readme")
    blame = (readme or {}).get("blame") or []
    ids = resolve_identities(commits + blame, logins, team)

    def who(email: str, name: str) -> str:
        k = commit_identity(ids, email, name)
        m = ids[k]["member"]
        return m if m else "unknown:" + k

    if kept_after is None:
        kept_after = end.replace(hour=23, minute=59, second=59, microsecond=0)
    start_ts, end_ts, kept_ts = start.timestamp(), end.timestamp(), kept_after.timestamp()

    layout = extract.get("layout")
    head = extract.get("head_files", {})
    reasons: dict[str, str | None] = {}

    def reason(path: str) -> str | None:
        if path not in reasons:
            r = counted_reason(path, layout)
            if r is None:
                h = head.get(path)
                if h and looks_minified(h, path):
                    r = "minified"
            reasons[path] = r
        return reasons[path]

    # Starter template: every root commit authored before the event.
    tmpl_roots = [r for r in extract.get("roots", []) if r["at"] < start_ts]
    template: set[str] = set()  # template paths, followed through renames and deletes
    versions: set[tuple[str, str]] = set()  # (path, blob) of template files and of every edit to them
    template_blobs: set[str] = set()
    for r in tmpl_roots:
        template.update(r["files"])
        versions.update(r.get("blobs", {}).items())
        template_blobs.update(r.get("blobs", {}).values())
    template_files = len(template)

    file_lines: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    person_commits: dict[str, int] = defaultdict(int)
    excluded: dict[str, int] = defaultdict(int)
    kept: set[str] = set()
    seen: set[tuple[str, str]] = set()  # (path, blob) versions so far, any author, any time
    capped = replayed = in_window = counted_commits = 0

    # Extract order: parents before children, so renames and replays are seen in order.
    for c in commits:
        at = c["at"]
        inside = start_ts <= at <= end_ts
        after = at > kept_ts
        author = who(c["ae"], c["an"])
        counted_here = 0
        for path, added, _deleted, old_path, status, blob, old_blob, _note in c["files"]:
            tmpl = False
            if tmpl_roots:
                src = old_path if status in ("R", "C") and old_path else path
                # Commits come in author-date order across branches, so the path set alone can miss
                # an edit made on one branch to a file another branch renamed; its version can't.
                tmpl = status != "D" and (src in template or (src, old_blob) in versions)
                if status == "D":
                    template.discard(path)
                elif status == "R":
                    template.discard(src)
                if tmpl and status in ("R", "C"):
                    template.add(path)
                if tmpl and blob:
                    versions.add((path, blob))
                elif status == "A" and blob in template_blobs:
                    tmpl = True  # a copy of a template file: these lines only, not later edits
            is_replay = blob is not None and (path, blob) in seen
            if blob is not None:
                seen.add((path, blob))
            if added is None:
                if inside:
                    excluded["binary"] += 1
                continue
            r = reason(path)
            if after and r is None and added and not is_replay and not author.startswith("unknown:"):
                kept.add(author)
            if not inside:
                continue
            if r is None and tmpl:
                r = "starter-template"
            if r is not None:
                excluded[r] += added
                continue
            if is_replay:
                replayed += added
                continue
            n = added
            if n > MAX_LINES_PER_FILE_COMMIT:
                capped += n - MAX_LINES_PER_FILE_COMMIT
                n = MAX_LINES_PER_FILE_COMMIT
            if n:
                file_lines[path][author] += n
                counted_here += n
        if inside:
            in_window += 1
            if counted_here:
                counted_commits += 1
                person_commits[author] += 1

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

    readme_out = None
    if readme:
        tmpl_shas = {r["sha"] for r in tmpl_roots}
        by_who: dict[str, int] = defaultdict(int)
        for b in blame:
            if b["sha"] not in tmpl_shas:
                by_who[who(b["ae"], b["an"])] += b["chars"]
        members = sorted(u for u in by_who if not u.startswith("unknown:"))
        author = max(members, key=lambda u: by_who[u]) if members else None
        readme_out = {"path": readme["path"], "chars": readme["chars"], "author": author, "by": dict(by_who)}

    return {
        "repo": extract["slug"],
        "window": {"start": start.isoformat(), "end": end.isoformat(), "kept_after": kept_after.isoformat()},
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
        "template": {"applied": bool(tmpl_roots), "files": template_files, "roots": len(tmpl_roots)},
        "excluded": dict(excluded),
        "replayed_lines": replayed,
        "capped_lines": capped,
        "identities": ids,
    }


def file_share(result: dict, path: str) -> dict[str, float]:
    """Share (0..1) of a file's counted lines per author."""
    by = result["files"].get(path, {})
    total = sum(by.values())
    return {a: n / total for a, n in by.items()} if total else {}
