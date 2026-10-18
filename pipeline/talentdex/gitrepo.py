"""Clone a repo once, extract what attribution needs, cache it, delete the clone.

The cached extract (cache/git/<owner>__<repo>.json, format v3) holds:
  commits     every non-merge commit reachable from HEAD, parents before children
              (otherwise oldest author date first): sha, author name/email, author
              date as git prints it (%aI) and as unix time (%at, used for every
              comparison), and per file
              [path, added, deleted, old_path, status, blob, old_blob, note].
              added/deleted are None for binaries. Notebooks are counted on their
              code-cell sources (a version that doesn't parse adds nothing), and a
              binary file that became text on its text lines; note says which.
  roots       every root commit: dates, paths and blob ids
  head_files  facts about the counted files at HEAD (size, long lines, a sample
              and import lines for classifying)
  layout      files.repo_layout() of HEAD (project roots, vendored and generated dirs)
  manifests   dependency manifests at HEAD (package.json, requirements.txt, ...)
  readme      the root README at HEAD and its git blame per author

Only permanent skips (missing or private repo, over 300 MB) are cached. Rate
limits, network errors and failed clones raise RepoSkip(retryable=True).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from . import github
from .config import CACHE_DIR, MAX_REPO_KB, WORK_DIR
from .files import code_like, counted_reason, exclusion_reason, is_readme, repo_layout

EXTRACT_VERSION = 3
GIT_DIR = CACHE_DIR / "git"
# Set by run.py --no-clone: only repos already in the extract cache are analysed.
NO_CLONE = False
SAMPLE_LINES = 60
HEAD_FILES_CAP = 4000
LONG_LINE = 500
MAX_FACT_BYTES = 4 * 1024 * 1024
MANIFEST_CAP = 60
MANIFEST_CHARS = 20000
IMPORT_LINE = re.compile(r"^\s*(import |from |#include|require\(|const .*= require\(|using |@import|use |extern crate|library\()")
NUMSTAT = re.compile(r"^(\d+|-)\t(\d+|-)\t(.*)$", re.S)
LOG_FORMAT = "%x1e%H%x1f%an%x1f%ae%x1f%aI%x1f%at%x1f%P"
MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "Pipfile", "setup.py", "environment.yml", "go.mod", "Cargo.toml",
    "pubspec.yaml", "platformio.ini", "build.gradle", "build.gradle.kts", "settings.gradle", "Podfile",
    "Package.swift", "Gemfile", "composer.json", "CMakeLists.txt", "app.json", "app.config.js", "app.config.ts",
    "pom.xml", "library.properties", "library.json", "idf_component.yml",
}
# The user's own git config must not change what we parse (log.showSignature,
# colours, log encodings, rename settings), and nothing may prompt.
GIT_ENV = {
    "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1", "GIT_ASKPASS": "true",
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
}


class RepoSkip(Exception):
    """The repo can't be analysed. retryable: a temporary failure (rate limit,
    network, clone error) that was not cached and may work on a later run."""

    def __init__(self, reason: str, retryable: bool = False) -> None:
        super().__init__(reason)
        self.retryable = retryable


def _key(slug: str) -> str:
    return slug.replace("/", "__")


def _env() -> dict[str, str]:
    # Drop inherited GIT_* variables too (GIT_DIR from a hook would point git elsewhere).
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return {**env, **GIT_ENV}


def _git(args: list[str], cwd: Path | None = None, timeout: int = 600) -> bytes:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, env=_env(), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RepoSkip(f"git {args[0]} timed out after {timeout}s", retryable=True) from None
    if r.returncode != 0:
        raise RepoSkip(f"git {args[0]} failed: {r.stderr.decode(errors='replace').strip()[:300]}", retryable=True)
    return r.stdout


def _oid(s: str) -> str | None:
    return None if not s or set(s) == {"0"} else s


def _int(s: str) -> int:
    try:
        return int(s)
    except ValueError:
        return 0


def parse_log(raw: bytes) -> list[dict]:
    """Parse `git log -z --raw --numstat --no-abbrev --format=LOG_FORMAT`.

    Tokens are NUL-separated: a header per commit, then its raw entries
    (":modes oids status", then one path, or two for renames and copies), then its
    numstat entries ("added<TAB>deleted<TAB>path", or an empty path followed by
    the old and new paths). Paths are consumed by count, so any byte in a path is safe.
    """
    toks = raw.decode("utf-8", errors="replace").split("\0")
    commits: list[dict] = []
    c: dict | None = None
    i = 0
    while i < len(toks):
        t = toks[i].lstrip("\n")
        i += 1
        if t.startswith("\x1e"):
            f = t[1:].split("\x1f")
            if len(f) < 6:
                c = None
                continue
            c = {"sha": f[0], "an": "\x1f".join(f[1:-4]), "ae": f[-4], "ad": f[-3], "at": _int(f[-2]),
                 "parents": len(f[-1].split()), "raw": [], "num": []}
            commits.append(c)
        elif c is None or not t:
            continue
        elif t.startswith(":"):
            meta = t[1:].split()
            if len(meta) < 5:
                continue
            status = meta[4][0]
            if status in "RC":
                if i + 1 >= len(toks):
                    break
                old, path = toks[i], toks[i + 1]
                i += 2
            else:
                if i >= len(toks):
                    break
                old, path = None, toks[i]
                i += 1
            c["raw"].append((path, old, status, _oid(meta[3]), _oid(meta[2])))
        else:
            m = NUMSTAT.match(t)
            if not m:
                continue
            path, old = m.group(3), None
            if path == "":
                if i + 1 >= len(toks):
                    break
                old, path = toks[i], toks[i + 1]
                i += 2
            added = None if m.group(1) == "-" else int(m.group(1))
            deleted = None if m.group(2) == "-" else int(m.group(2))
            c["num"].append((path, old, added, deleted))
    for c in commits:
        c["files"] = _join(c.pop("raw"), c.pop("num"))
    return commits


def _join(raw: list[tuple], num: list[tuple]) -> list[list]:
    """Pair raw entries (status, blobs) with numstat entries (line counts)."""
    if len(raw) == len(num) and all(r[0] == n[0] for r, n in zip(raw, num)):
        pairs = list(zip(raw, num))
    else:  # both come from the same diff queue, so this is only a safety net
        by_path = {n[0]: n for n in num}
        pairs = [(r, by_path.get(r[0])) for r in raw]
    files = []
    for (path, old, status, blob, old_blob), n in pairs:
        added, deleted = (n[2], n[3]) if n else (0, 0)
        files.append([path, added, deleted, old, status, blob, old_blob, None])
    return files


def _list(x) -> list:
    return x if isinstance(x, list) else []


def notebook_source(data: bytes) -> list[str] | None:
    """Code-cell source lines of a Jupyter notebook (nbformat 3 or 4); None if it isn't one."""
    try:
        nb = json.loads(data.decode("utf-8-sig"))  # some editors save a BOM
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(nb, dict) or ("cells" not in nb and "worksheets" not in nb):
        return None
    cells = nb.get("cells")
    if not isinstance(cells, list):
        cells = [c for ws in _list(nb.get("worksheets")) if isinstance(ws, dict) for c in _list(ws.get("cells"))]
    out: list[str] = []
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        src = cell.get("source", cell.get("input", ""))  # nbformat 3 code cells use "input"
        if isinstance(src, list):
            src = "".join(s for s in src if isinstance(s, str))
        if isinstance(src, str):
            out.extend(_lines(src))
    return out


def _lines(text: str) -> list[str]:
    ls = text.split("\n")
    if ls and ls[-1] == "":
        ls.pop()
    return ls


def _line_diff(old: list[str], new: list[str]) -> tuple[int, int]:
    """(added, deleted) lines between two versions, from difflib opcodes."""
    sm = difflib.SequenceMatcher(None, old, new, autojunk=len(old) + len(new) > 20000)
    added = deleted = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            added += j2 - j1
        if tag in ("replace", "delete"):
            deleted += i2 - i1
    return added, deleted


class _Blobs:
    """Blob contents by id, through one `git cat-file --batch` process."""

    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd
        self.proc: subprocess.Popen | None = None
        self.notebooks: dict[str, list[str] | None] = {}

    def read(self, oid: str | None) -> bytes | None:
        if not oid:
            return None
        if self.proc is None:
            self.proc = subprocess.Popen(["git", "cat-file", "--batch"], cwd=self.cwd, env=_env(),
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(oid.encode() + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if len(header) < 3:  # "<oid> missing"
            return None
        data = self.proc.stdout.read(int(header[2]))
        self.proc.stdout.read(1)
        return data if header[1] == b"blob" else None

    def text(self, oid: str | None) -> str | None:
        """The blob as text, or None when it is missing or binary (NUL in the first 8000 bytes, or not UTF-8)."""
        data = self.read(oid)
        if data is None or b"\0" in data[:8000]:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def notebook(self, oid: str) -> list[str] | None:
        if oid not in self.notebooks:
            data = self.read(oid)
            self.notebooks[oid] = notebook_source(data) if data is not None else None
        return self.notebooks[oid]

    def close(self) -> None:
        if self.proc:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.kill()
            self.proc.wait()


def _recount(commits: list[dict], blobs: _Blobs, counts: Callable[[str], bool]) -> None:
    """Notebooks: lines from code-cell sources. A version that doesn't parse (conflict markers,
    truncated JSON) adds nothing, and the next one is compared with the last version that did.
    Binary that became text: its text lines."""
    parsed: dict[str, list[str]] = {}  # notebook path -> code lines of its last version that parsed
    for c in commits:
        for f in c["files"]:
            path, added, _deleted, old_path, _status, blob, old_blob, _note = f
            if path.lower().endswith(".ipynb"):
                new = blobs.notebook(blob) if blob else []
                old = blobs.notebook(old_blob) if old_blob else []
                if old is None:
                    old = parsed.get(old_path or path, [])
                if new is None:
                    f[1], f[2], f[7] = 0, 0, "notebook-unparsed"
                else:
                    f[1], f[2] = _line_diff(old, new)
                    f[7] = "notebook-source"
                    parsed[path] = new
            elif added is None and blob and counts(path):
                new_text = blobs.text(blob)
                if new_text is not None:
                    old_text = blobs.text(old_blob)
                    f[1], f[2] = _line_diff(_lines(old_text) if old_text is not None else [], _lines(new_text))
                    f[7] = "binary-to-text"


def _ls_tree(cwd: Path, rev: str) -> list[tuple[str, str, str, str]]:
    """(mode, type, oid, path) for every file in a commit's tree."""
    out = []
    for e in _git(["ls-tree", "-r", "-z", rev], cwd=cwd).decode("utf-8", errors="replace").split("\0"):
        meta, tab, path = e.partition("\t")
        parts = meta.split()
        if tab and len(parts) == 3:
            out.append((parts[0], parts[1], parts[2], path))
    return out


def file_facts(data: bytes, path: str) -> dict | None:
    """Facts about a file's content for exclusion and classification; None for binaries.
    Notebooks are measured on their code-cell sources only."""
    notebook = path.lower().endswith(".ipynb")
    src = notebook_source(data) if notebook else None
    if src is not None:
        lines, text = src, "\n".join(src)
    else:
        if b"\0" in data[:8000]:
            return None
        text = data[:MAX_FACT_BYTES].decode("utf-8", errors="replace")
        lines = text.splitlines()
    long = [x for x in lines if len(x) > LONG_LINE]
    code = [x for x in long if code_like(x)]
    return {
        "lines": len(lines),
        "chars": len(text),
        "max_line": max((len(x) for x in lines), default=0),
        "long_lines": len(long),
        "long_code": len(code),  # long lines that read like code, not prose, base64 or URLs
        "long_code_chars": sum(map(len, code)),
        "sample": "\n".join(lines[:SAMPLE_LINES])[:4000],
        "imports": [ln.strip()[:200] for ln in lines[:400] if IMPORT_LINE.match(ln)][:60],
        "notebook": notebook,
    }


def is_manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (name in MANIFEST_NAMES or name.endswith(".csproj")
            or (name.startswith("requirements") and name.endswith(".txt")))


def parse_blame(raw: bytes) -> list[dict]:
    """`git blame --line-porcelain` -> [{sha, an, ae, at, lines, chars}] per (commit, name, email)."""
    agg: dict[tuple, dict] = {}
    sha, an, ae, at = "", "", "", 0
    for line in raw.split(b"\n"):
        if line.startswith(b"\t"):
            a = agg.setdefault((sha, an, ae), {"sha": sha, "an": an, "ae": ae, "at": at, "lines": 0, "chars": 0})
            a["lines"] += 1
            a["chars"] += len(line[1:].decode("utf-8", errors="replace")) + 1
            continue
        key, _, val = line.decode("utf-8", errors="replace").partition(" ")
        if key == "author":
            an = val
        elif key == "author-mail":
            ae = val[1:-1] if val.startswith("<") and val.endswith(">") else val
        elif key == "author-time":
            at = _int(val)
        elif re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", key):
            sha = key
    return sorted(agg.values(), key=lambda a: (-a["chars"], a["sha"]))


def extract_dir(dest: Path, slug: str) -> dict:
    """Extract from a local clone (also used by the tests on synthetic repos)."""
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=dest).decode().strip()
    head_sha = _git(["rev-parse", "HEAD"], cwd=dest).decode().strip()
    blobs = _Blobs(dest)
    try:
        tree = [e for e in _ls_tree(dest, "HEAD") if e[1] == "blob"]
        oid_of = {path: oid for _mode, _typ, oid, path in tree}

        def read(path: str) -> str | None:
            data = blobs.read(oid_of.get(path))
            return None if data is None else data.decode("utf-8", errors="replace")

        layout = repo_layout(list(oid_of), read)
        raw = _git(["log", "--no-merges", "--author-date-order", "--reverse", "-M", "-z", "--raw", "--numstat",
                    "--no-abbrev", "--no-show-signature", "--no-color", "--no-ext-diff", "--no-textconv",
                    f"--format={LOG_FORMAT}", "HEAD"], cwd=dest, timeout=900)
        commits = parse_log(raw)
        _recount(commits, blobs, lambda p: counted_reason(p, layout) is None)

        by_sha = {c["sha"]: c for c in commits}
        roots = []
        for sha in _git(["rev-list", "--max-parents=0", "HEAD"], cwd=dest).decode().split():
            c = by_sha.get(sha) or {}
            entries = _ls_tree(dest, sha)
            roots.append({"sha": sha, "ad": c.get("ad", ""), "at": c.get("at", 0), "files": [e[3] for e in entries],
                          "blobs": {p: oid for _m, typ, oid, p in entries if typ == "blob"}})

        regular = [(oid, path) for mode, _typ, oid, path in tree if mode.startswith("100")]
        head_files = {}
        # Filter before the cap: a committed node_modules must not push real files out.
        for oid, path in [(o, p) for o, p in regular if counted_reason(p, layout) is None][:HEAD_FILES_CAP]:
            data = blobs.read(oid)
            facts = file_facts(data, path) if data is not None else None
            if facts:
                head_files[path] = facts

        manifests = {}
        found = [(o, p) for o, p in regular if is_manifest(p)
                 and exclusion_reason(p, layout) not in ("node_modules", "vendored", "build-output")]
        for oid, path in sorted(found, key=lambda op: (op[1].count("/"), op[1]))[:MANIFEST_CAP]:
            data = blobs.read(oid)
            if data is not None:
                manifests[path] = data.decode("utf-8", errors="replace")[:MANIFEST_CHARS]

        readme = None
        for oid, path in regular:
            if is_readme(path):
                data = blobs.read(oid) or b""
                try:
                    blame = parse_blame(_git(["blame", "--line-porcelain", "HEAD", "--", path], cwd=dest, timeout=300))
                except RepoSkip:
                    blame = []
                for b in blame:  # blame applies .mailmap and %an does not: use the commit's own identity
                    if b["sha"] in by_sha:
                        b.update(an=by_sha[b["sha"]]["an"], ae=by_sha[b["sha"]]["ae"], at=by_sha[b["sha"]]["at"])
                readme = {"path": path, "chars": len(data.decode("utf-8", errors="replace")), "blame": blame}
                break
    finally:
        blobs.close()
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
        "head_files": head_files,
        "layout": layout,
        "manifests": manifests,
        "readme": readme,
    }


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(slug: str) -> threading.Lock:
    """One extraction per repo at a time (two projects can share a repo)."""
    with _locks_guard:
        return _locks.setdefault(slug.lower(), threading.Lock())


def _remember_skip(out: Path, slug: str, reason: str) -> None:
    out.write_text(json.dumps({"version": EXTRACT_VERSION, "slug": slug, "skip": reason}))
    raise RepoSkip(reason)


def extract(slug: str, *, refresh: bool = False) -> dict:
    """Return the cached extract for owner/repo, cloning once if needed. Raises RepoSkip."""
    GIT_DIR.mkdir(parents=True, exist_ok=True)
    out = GIT_DIR / f"{_key(slug)}.json"
    with _lock(slug):
        if out.exists() and not refresh:
            try:
                d = json.loads(out.read_text())
            except ValueError:
                d = {}
            if d.get("version") == EXTRACT_VERSION:
                if d.get("skip"):
                    raise RepoSkip(d["skip"])
                return d
        if NO_CLONE:
            # Not remembered, so a later run without --no-clone still fetches it.
            raise RepoSkip("not cloned yet (run used --no-clone)")

        status, meta = github.repo_status(slug)
        if status == "missing":
            _remember_skip(out, slug, "repo not found or private")
        if status != "ok" or meta is None:
            raise RepoSkip("GitHub repo lookup failed (rate limit, server or network error)", retryable=True)
        if meta["size_kb"] > MAX_REPO_KB:
            _remember_skip(out, slug, f"repo is {meta['size_kb'] // 1024} MB (over 300 MB)")

        WORK_DIR.mkdir(parents=True, exist_ok=True)
        dest = WORK_DIR / _key(slug)
        shutil.rmtree(dest, ignore_errors=True)
        try:
            try:
                # No checkout: everything is read from git objects.
                _git(["clone", "--single-branch", "--no-tags", "--no-checkout", "--quiet",
                      f"https://github.com/{slug}.git", str(dest)], timeout=900)
            except RepoSkip as e:
                raise RepoSkip(f"clone failed: {e}", retryable=True) from None
            d = extract_dir(dest, slug)
            d.update({"size_kb": meta["size_kb"], "fork": meta["fork"]})
            tmp = out.with_suffix(".tmp")
            tmp.write_text(json.dumps(d))
            tmp.replace(out)
            return d
        finally:
            shutil.rmtree(dest, ignore_errors=True)
