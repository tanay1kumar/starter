"""Clone a repo once, extract what attribution needs, cache it, delete the clone.

The cached extract (cache/git/<owner>__<repo>.json) holds:
  commits     every non-merge commit on the default branch: sha, author name,
              author email, author date (ISO, original offset), numstat
              [path, added, deleted, renamed_from] (added None for binaries)
  roots       root commits with their author date and file list
  head        facts about files at HEAD that are candidates for counting:
              line count, chars, longest line, and a short sample for classifying
  readme      root README path and its length in characters
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .config import CACHE_DIR, MAX_REPO_KB, WORK_DIR
from .files import counted_reason, is_readme
from .github import repo_meta

EXTRACT_VERSION = 2
GIT_DIR = CACHE_DIR / "git"
SAMPLE_LINES = 60
IMPORT_LINE = re.compile(r"^\s*(import |from |#include|require\(|const .*= require\(|using |@import|use |extern crate|library\()")


class RepoSkip(Exception):
    """The repo can't be analysed (missing, private, too big, clone failed)."""


def _key(slug: str) -> str:
    return slug.replace("/", "__")


def _git(args: list[str], cwd: Path | None = None, timeout: int = 600) -> bytes:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1", "GIT_ASKPASS": "true"}
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RepoSkip(f"git {args[0]} failed: {r.stderr.decode(errors='replace').strip()[:300]}")
    return r.stdout


def parse_numstat_log(raw: bytes) -> list[dict]:
    """Parse `git log -z --numstat --format=%x1e%H%x1f%an%x1f%ae%x1f%aI%x1f%P`."""
    commits = []
    for chunk in raw.decode("utf-8", errors="replace").split("\x1e"):
        if not chunk.strip():
            continue
        # With -z the header ends in NUL, then a newline, then NUL-terminated numstat entries.
        header, _, rest = chunk.partition("\n")
        sha, an, ae, ad, parents = (header.rstrip("\0").split("\x1f") + ["", "", "", "", ""])[:5]
        files = []
        toks = rest.split("\0")
        i = 0
        while i < len(toks):
            t = toks[i].lstrip("\n")
            i += 1
            if not t:
                continue
            m = re.match(r"^(\d+|-)\t(\d+|-)\t(.*)$", t, re.S)
            if not m:
                continue
            added = None if m.group(1) == "-" else int(m.group(1))
            deleted = None if m.group(2) == "-" else int(m.group(2))
            path = m.group(3)
            renamed_from = None
            if path == "":
                # rename: "<added>\t<deleted>\t\0<old path>\0<new path>\0"
                if i + 1 >= len(toks):
                    break
                renamed_from, path = toks[i], toks[i + 1]
                i += 2
            files.append([path, added, deleted, renamed_from])
        commits.append({"sha": sha, "an": an, "ae": ae, "ad": ad, "parents": len(parents.split()), "files": files})
    return commits


def _head_facts(root: Path, paths: list[str]) -> dict:
    head = {}
    for path in paths[:4000]:
        if counted_reason(path) is not None:
            continue
        f = root / path
        try:
            if not f.is_file() or f.is_symlink():
                continue
            data = f.read_bytes()[: 512 * 1024]
        except OSError:
            continue
        if b"\0" in data[:8000]:
            continue  # binary
        s = data.decode("utf-8", errors="replace")
        lines = s.splitlines()
        imports = [ln.strip()[:200] for ln in lines[:400] if IMPORT_LINE.match(ln)][:60]
        head[path] = {
            "lines": len(lines),
            "chars": len(s),
            "max_line": max((len(x) for x in lines), default=0),
            "sample": "\n".join(lines[:SAMPLE_LINES])[:4000],
            "imports": imports,
        }
    return head


def extract(slug: str, *, refresh: bool = False) -> dict:
    """Return the cached extract for owner/repo, cloning once if needed. Raises RepoSkip."""
    GIT_DIR.mkdir(parents=True, exist_ok=True)
    out = GIT_DIR / f"{_key(slug)}.json"
    if out.exists() and not refresh:
        d = json.loads(out.read_text())
        if d.get("version") == EXTRACT_VERSION:
            if d.get("skip"):
                raise RepoSkip(d["skip"])
            return d

    def remember_skip(reason: str) -> None:
        out.write_text(json.dumps({"version": EXTRACT_VERSION, "slug": slug, "skip": reason}))
        raise RepoSkip(reason)

    meta = repo_meta(slug)
    if meta is None:
        remember_skip("repo not found or private")
    assert meta is not None
    if meta["size_kb"] > MAX_REPO_KB:
        remember_skip(f"repo is {meta['size_kb'] // 1024} MB (over 300 MB)")

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    dest = WORK_DIR / _key(slug)
    shutil.rmtree(dest, ignore_errors=True)
    try:
        try:
            _git(["clone", "--single-branch", "--no-tags", "--quiet", f"https://github.com/{slug}.git", str(dest)], timeout=900)
        except (RepoSkip, subprocess.TimeoutExpired) as e:
            remember_skip(f"clone failed: {e}")
        d = extract_dir(dest, slug)
        d.update({"size_kb": meta["size_kb"], "fork": meta["fork"]})
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        tmp.replace(out)
        return d
    finally:
        shutil.rmtree(dest, ignore_errors=True)


def extract_dir(dest: Path, slug: str) -> dict:
    """Extract from a local clone (also used by the tests on synthetic repos)."""
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=dest).decode().strip()
    head_sha = _git(["rev-parse", "HEAD"], cwd=dest).decode().strip()
    raw = _git(["-c", "core.quotePath=false", "log", "--no-merges", "-M", "-z", "--numstat",
                "--format=%x1e%H%x1f%an%x1f%ae%x1f%aI%x1f%P"], cwd=dest, timeout=900)
    commits = parse_numstat_log(raw)
    roots = []
    for sha in _git(["rev-list", "--max-parents=0", "HEAD"], cwd=dest).decode().split():
        ad = _git(["log", "-1", "--format=%aI", sha], cwd=dest).decode().strip()
        files = [p for p in _git(["ls-tree", "-r", "--name-only", "-z", sha], cwd=dest).decode(errors="replace").split("\0") if p]
        roots.append({"sha": sha, "ad": ad, "files": files})
    paths = [p for p in _git(["-c", "core.quotePath=false", "ls-files", "-z"], cwd=dest).decode(errors="replace").split("\0") if p]
    readme = None
    for p in paths:
        if is_readme(p):
            try:
                readme = {"path": p, "chars": len((dest / p).read_text(errors="replace"))}
            except OSError:
                pass
            break
    return {
        "version": EXTRACT_VERSION,
        "slug": slug,
        "url": f"https://github.com/{slug}",
        "branch": branch,
        "head": head_sha,
        "size_kb": None,
        "fork": False,
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commits": commits,
        "roots": roots,
        "head_files": _head_facts(dest, paths),
        "readme": readme,
    }
