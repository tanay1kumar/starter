"""GitHub REST API (public data only), cached."""

from __future__ import annotations

from collections import defaultdict

from .config import GITHUB_TOKEN
from .httpcache import Http

_headers = {"X-GitHub-Api-Version": "2022-11-28"}
if GITHUB_TOKEN:
    _headers["Authorization"] = "Bearer " + GITHUB_TOKEN

API = Http("github", headers=_headers, keep_headers=("link",))
ACCEPT = "application/vnd.github+json"
# Answers that won't change on a retry: no such repo or commit, or an empty repo.
GONE = {404, 409, 410, 422}


def _commits_page(slug: str, params: dict) -> list:
    """One page of /repos/{slug}/commits ([] when the repo or commit is gone). Raises RuntimeError on
    rate limits and outages, so a caller that caches results (code.py) retries later instead."""
    r = API.get(f"https://api.github.com/repos/{slug}/commits", params=params, accept=ACCEPT)
    if r.status in GONE:
        return []
    if not r.ok:
        raise RuntimeError(f"GitHub answered {r.status} listing commits of {slug}")
    items = r.json()
    return items if isinstance(items, list) else []


def repo_status(slug: str) -> tuple[str, dict | None]:
    """("ok", meta), ("missing", None) for 404/410 (deleted or private), or
    ("temporary", None) for rate limits, server errors and network failures."""
    try:
        r = API.get(f"https://api.github.com/repos/{slug}", accept=ACCEPT)
        if r.status in (404, 410):
            return "missing", None
        if not r.ok:
            return "temporary", None
        d = r.json()
    except (RuntimeError, ValueError):  # Http gave up after retries, or a garbled answer
        return "temporary", None
    return "ok", {
        "full_name": d.get("full_name", slug),
        "size_kb": d.get("size", 0),
        "default_branch": d.get("default_branch") or "main",
        "fork": bool(d.get("fork")),
        "archived": bool(d.get("archived")),
        "pushed_at": d.get("pushed_at"),
        "html_url": d.get("html_url"),
    }


def repo_meta(slug: str) -> dict | None:
    """size (KB), default_branch, fork, archived, pushed_at; None when missing, private
    or unavailable right now (use repo_status to tell those apart)."""
    return repo_status(slug)[1]


def commit_logins(slug: str, branch: str, commits: list[dict] | None = None, max_pages: int = 10) -> dict[str, str | None]:
    """sha -> GitHub login of the commit author (None when the email is not linked to an account).

    Pages through the newest commits first. Then, for every author email in
    `commits` (an extract's commits) that no listed commit covered, asks GitHub
    about one of that email's commits and applies the answer to all of them, so
    the oldest (hackathon) commits of a long-lived repo keep their login.
    Raises RuntimeError when GitHub is rate limiting or down.
    """
    out: dict[str, str | None] = {}
    for page in range(1, max_pages + 1):
        items = _commits_page(slug, {"sha": branch, "per_page": 100, "page": page})
        if not items:
            break
        for c in items:
            author = c.get("author") or {}
            out[c["sha"]] = author.get("login")
        if len(items) < 100:
            break
    by_email: dict[str, list[str]] = defaultdict(list)
    for c in commits or []:
        email = (c.get("ae") or "").strip().lower()
        if email:
            by_email[email].append(c["sha"])
    for shas in by_email.values():
        if any(s in out for s in shas):
            continue
        login = commit_login(slug, shas[-1])
        for s in shas:
            out[s] = login
    return out


def commit_login(slug: str, sha: str) -> str | None:
    """GitHub login of one commit's author. Uses the list endpoint starting at that
    commit (per_page=1), which carries the same author field as
    /repos/{slug}/commits/{sha} without the commit's full diff."""
    items = _commits_page(slug, {"sha": sha, "per_page": 1})
    if items and isinstance(items[0], dict) and items[0].get("sha") == sha:
        return (items[0].get("author") or {}).get("login")
    return None


def user(login: str) -> dict | None:
    r = API.get(f"https://api.github.com/users/{login}", accept=ACCEPT)
    if not r.ok:
        return None
    d = r.json()
    return {"login": d.get("login", login), "public_repos": d.get("public_repos"), "email": d.get("email"), "name": d.get("name"), "type": d.get("type")}


def latest_push(login: str) -> str | None:
    """ISO time of the most recent push to any public repo they own."""
    r = API.get(f"https://api.github.com/users/{login}/repos", params={"sort": "pushed", "per_page": 1, "type": "owner"}, accept=ACCEPT)
    if not r.ok:
        return None
    items = r.json()
    if isinstance(items, list) and items:
        return items[0].get("pushed_at")
    return None
