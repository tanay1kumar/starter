"""Step 8 (output): the Dataset the UI reads (lib/types.ts), as JSON.

validate() checks the exact shape before anything is written, so a pipeline
bug can't ship a half-formed data/builders.json. Postgres loading lives in
db.py (milestone 5); without DATABASE_URL the JSON file is the only output.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TYPE_KEYS = ["ml", "backend", "frontend", "design", "mobile", "hardware"]
SOURCES = {"GitHub", "Devpost", "résumé", "People Data Labs"}
FACTS = ["school", "schoolFull", "program", "grad", "year", "city", "lastActive"]
WORDS = re.compile(r"\S+")


def _fact_problems(where: str, f: object) -> list[str]:
    if not isinstance(f, dict) or set(f) != {"value", "source", "looked"}:
        return [f"{where}: not a Fact"]
    out = []
    if f["value"] is None and f["source"] is not None:
        out.append(f"{where}: source without a value")
    if f["value"] is not None and f["source"] not in SOURCES:
        out.append(f"{where}: unknown source {f['source']!r}")
    if not isinstance(f["looked"], list) or not f["looked"] or any(s not in SOURCES for s in f["looked"]):
        out.append(f"{where}: looked must name the sources checked")
    return out


def _project_problems(where: str, p: dict) -> list[str]:
    out = []
    keys = {"id", "name", "abbr", "type", "event", "desc", "prize", "prizes", "kept", "share", "url", "repo", "demo", "flags", "inScan"}
    if set(p) != keys:
        out.append(f"{where}: keys {sorted(set(p) ^ keys)}")
        return out
    if p["type"] is not None and p["type"] not in TYPE_KEYS:
        out.append(f"{where}: type {p['type']!r}")
    if p["share"] is not None and not (isinstance(p["share"], int) and 0 <= p["share"] <= 100):
        out.append(f"{where}: share {p['share']!r}")
    if p["prize"] != (p["prizes"][0] if p["prizes"] else ""):
        out.append(f"{where}: prize is not the first prize")
    return out


def builder_problems(b: dict) -> list[str]:
    w = f"builder {b.get('id')!r}"
    out: list[str] = []
    for k in ("id", "name", "dex", "why", "sum"):
        if not isinstance(b.get(k), str):
            out.append(f"{w}: {k} missing")
    if not re.fullmatch(r"\d{4}", str(b.get("dex", ""))):
        out.append(f"{w}: dex {b.get('dex')!r}")
    if not isinstance(b.get("types"), list) or not 0 < len(b["types"]) <= 2 or any(t not in TYPE_KEYS for t in b["types"]):
        out.append(f"{w}: types {b.get('types')!r}")
    for k in FACTS:
        out += _fact_problems(f"{w}.{k}", b.get(k))
    y = (b.get("year") or {}).get("value")
    if y is not None and not (isinstance(y, int) and 0 <= y <= 5):
        out.append(f"{w}: year {y!r}")
    links = b.get("links") or {}
    if set(links) != {"devpost", "github", "linkedin"} or not links.get("devpost"):
        out.append(f"{w}: links")
    for k in ("hacks", "wins", "codeProjects"):
        if not isinstance(b.get(k), int) or b[k] < 0:
            out.append(f"{w}: {k} {b.get(k)!r}")
    if b.get("repos") is not None and not isinstance(b["repos"], int):
        out.append(f"{w}: repos {b['repos']!r}")
    ev = b.get("ev") or {}
    if set(ev) != set(TYPE_KEYS) or any(not isinstance(v, int) or not 0 <= v <= 252 for v in ev.values()) or sum(ev.values()) > 510:
        out.append(f"{w}: ev {ev!r}")
    iv = b.get("iv")
    if not isinstance(iv, list) or len(iv) != 6 or any(not isinstance(v, int) or not 0 <= v <= 31 for v in iv):
        out.append(f"{w}: iv {iv!r}")
    n = b.get("n") or {}
    if set(n) != {"demo", "own", "mates", "kept", "docs"}:
        out.append(f"{w}: n {n!r}")
    tp = b.get("typeProjects") or {}
    if set(tp) != set(TYPE_KEYS) or any(v > b.get("codeProjects", 0) for v in tp.values()):
        out.append(f"{w}: typeProjects {tp!r}")
    if len(WORDS.findall(b.get("why", ""))) > 15:
        out.append(f"{w}: why is over 15 words")
    if len(WORDS.findall(b.get("sum", ""))) > 20:
        out.append(f"{w}: sum is over 20 words")
    for i, p in enumerate(b.get("projects") or []):
        out += _project_problems(f"{w}.projects[{i}]", p)
    if not b.get("projects"):
        out.append(f"{w}: no projects")
    return out


def validate(dataset: dict) -> None:
    """Raise ValueError listing every way the dataset differs from lib/types.ts."""
    problems = []
    if dataset.get("version") != 1 or dataset.get("source") not in ("sample", "real"):
        problems.append("version/source")
    scan = dataset.get("scan") or {}
    for k in ("projectsChecked", "reposChecked", "commitsCounted", "buildersFound"):
        if not isinstance(scan.get(k), int):
            problems.append(f"scan.{k}")
    # The sample keeps the design's population (214); real data must count what it ships.
    if dataset.get("source") == "real" and scan.get("buildersFound") != len(dataset.get("builders") or []):
        problems.append("scan.buildersFound != len(builders)")
    ids = [b.get("id") for b in dataset.get("builders") or []]
    if len(ids) != len(set(ids)):
        problems.append("duplicate builder ids")
    dex = [b.get("dex") for b in dataset.get("builders") or []]
    if len(dex) != len(set(dex)):
        problems.append("duplicate dex numbers")
    for b in dataset.get("builders") or []:
        problems += builder_problems(b)
    if problems:
        raise ValueError(f"{len(problems)} problem(s) in the dataset:\n  " + "\n  ".join(problems[:40]))


def write_json(dataset: dict, path: str | Path) -> Path:
    validate(dataset)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dataset, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return path
