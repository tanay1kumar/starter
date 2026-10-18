"""GitHub REST API (public data only), cached."""

from __future__ import annotations

from .config import GITHUB_TOKEN
from .httpcache import Http

_headers = {"X-GitHub-Api-Version": "2022-11-28"}
if GITHUB_TOKEN:
    _headers["Authorization"] = "Bearer " + GITHUB_TOKEN

API = Http("github", headers=_headers, keep_headers=("link",))
ACCEPT = "application/vnd.github+json"


def repo_meta(slug: str) -> dict | None:
    """size (KB), default_branch, fork, archived, pushed_at; None when missing or private."""
    r = API.get(f"https://api.github.com/repos/{slug}", accept=ACCEPT)
    if not r.ok:
        return None
    d = r.json()
    return {
        "full_name": d.get("full_name", slug),
        "size_kb": d.get("size", 0),
        "default_branch": d.get("default_branch") or "main",
        "fork": bool(d.get("fork")),
        "archived": bool(d.get("archived")),
        "pushed_at": d.get("pushed_at"),
        "html_url": d.get("html_url"),
    }


def commit_logins(slug: str, branch: str, max_pages: int = 10) -> dict[str, str | None]:
    """sha -> GitHub login of the commit author (None when the email is not linked to an account)."""
    out: dict[str, str | None] = {}
    for page in range(1, max_pages + 1):
        r = API.get(
            f"https://api.github.com/repos/{slug}/commits",
            params={"sha": branch, "per_page": 100, "page": page},
            accept=ACCEPT,
        )
        if not r.ok:
            break
        items = r.json()
        if not isinstance(items, list) or not items:
            break
        for c in items:
            author = c.get("author") or {}
            out[c["sha"]] = author.get("login")
        if len(items) < 100:
            break
    return out


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
