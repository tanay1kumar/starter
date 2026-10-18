"""Step 4 (code): clone, attribute and classify every project repo, in parallel.

One job = (Devpost project, GitHub repo, hackathon window, team[, kept_after]).
Results are cached under cache/steps/attr/ keyed by the repo's HEAD, the window,
kept_after and the team, so a re-run is free. Clones are deleted right after
extraction.
"""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from typing import Callable

from . import github
from .attribution import Member, attribute
from .config import CACHE_DIR
from .devpost import parse_iso, window_bounds
from .gitrepo import RepoSkip, extract

ATTR_DIR = CACHE_DIR / "steps" / "attr"
ATTR_VERSION = 6


def _job_key(project: str, repo: str, window: dict, team: list[Member], head: str, kept_after: str | None) -> str:
    raw = json.dumps([ATTR_VERSION, project, repo, head, window["start"], window["end"], kept_after,
                      [asdict(m) for m in team]], sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()


def analyze_job(project: str, repo: str, window: dict, team: list[Member], kept_after: datetime | str | None = None) -> dict:
    """Attribute one repo for one project. Returns the attribution dict or
    {"skip": reason, "repo": repo, "retryable": bool}. kept_after (datetime or ISO
    string) defaults to the end of the event's last day (see attribution.attribute)."""
    try:
        ex = extract(repo)
    except RepoSkip as e:
        return {"skip": str(e), "repo": repo, "retryable": e.retryable}
    ka = parse_iso(kept_after) if isinstance(kept_after, str) else kept_after
    key = _job_key(project, repo, window, team, ex["head"], ka.isoformat() if ka else None)
    path = ATTR_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    try:
        logins = github.commit_logins(repo, ex["branch"], ex["commits"])
    except RuntimeError as e:  # rate limit or outage: nothing is cached, so a later run retries
        return {"skip": f"GitHub login lookup failed: {e}"[:300], "repo": repo, "retryable": True}
    start, end = window_bounds(window)
    result = attribute(ex, start, end, team, logins, kept_after=ka)
    result["project"] = project
    result["head"] = ex["head"]
    ATTR_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result))
    tmp.replace(path)
    return result


def analyze_many(
    jobs: list[tuple[str, str, dict, list[Member]]],
    *,
    workers: int = 6,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[tuple[str, str], dict]:
    """Run analyze_job for (project, repo, window, team[, kept_after]) jobs; never raises for one bad repo."""
    out: dict[tuple[str, str], dict] = {}
    lock = threading.Lock()
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(analyze_job, *j): j for j in jobs}
        for f in as_completed(futs):
            project, repo = futs[f][0], futs[f][1]
            try:
                r = f.result()
            except Exception as e:  # keep going; record why
                # Http gives up with RuntimeError (rate limits, network); worth another try.
                r = {"skip": f"error: {type(e).__name__}: {e}"[:300], "repo": repo,
                     "retryable": isinstance(e, (RuntimeError, OSError))}
            with lock:
                out[(project, repo)] = r
                done += 1
                if progress:
                    progress(done, len(jobs), repo if "skip" not in r else f"{repo} (skipped: {r['skip'][:60]})")
    return out
