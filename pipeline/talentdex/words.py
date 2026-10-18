"""Step 7 (words): Gemini writes each builder's "why" line and Dex summary.

    python -m talentdex.words                      # design samples: new lines next to the design's
    python -m talentdex.words ../data/builders.json --limit 20

BUILD.md "Words": Gemini (Flash) writes the card's "why" line (<= 15 words) and
the Dex entry summary (<= 20 words) from a JSON of that builder's verified
facts only: card numbers, EVs, trait counts, and signature projects with their
names, prizes and the share of code the builder wrote. Rules implemented here:

- The facts JSON never holds the person's name, Devpost username, school,
  program, city, graduation, links, photos, emails or dex number. Project text
  goes in as written on Devpost minus links, emails and @handles; a tagline
  that names the builder is left out.
- Every line is checked before it is used: word limits, every number must
  appear in the facts, no links or "@", no gendered words, no technology the
  facts don't name, no school, place, year of study or graduation. A line
  that fails gets one retry with a stricter prompt (different text, so a
  different cache key); if it fails again, a plain template written from the
  same facts is used and the result says source="template".
- Responses are cached by gemini.py (namespace "words"), so re-runs are free.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from . import gemini
from .config import DATA_DIR

NAMESPACE = "words"
WHY_MAX = 15
SUM_MAX = 20
MIN_WORDS = 3
MAX_PROJECTS = 6  # Builder.projects holds the signature projects (3 today)
MAX_TAGLINE = 200  # characters; og:description fallbacks can run long

TYPE_LABELS = {
    "ml": "ML / AI", "backend": "Backend", "frontend": "Frontend",
    "design": "Design", "mobile": "Mobile", "hardware": "Hardware",
}

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "why": {"type": "STRING", "description": "At most 15 words."},
        "sum": {"type": "STRING", "description": "At most 20 words."},
    },
    "required": ["why", "sum"],
}

SYSTEM = """You write two short lines about one hackathon builder, for tech recruiters.
The message is a JSON of that builder's verified facts. Write only from that JSON.

Return JSON with two strings:
- "why" (at most 15 words; aim for 8 to 12): shown under the builder's card. The strongest concrete reason to look at them: a prize and the project that won it, or a project and how much of its code they wrote. One clear claim, with each number tied to what it counts.
- "sum" (at most 20 words; aim for 10 to 16): the Dex entry summary. A warm sketch of what they build, drawn from the project taglines and top_types, plus at most one standout habit from the n counts (demos, owning the code, building after the event, READMEs, teammates). Don't repeat the why line or list every project.

What the JSON fields mean:
- hacks: hackathons on their Devpost profile. wins: prizes won. repos: public GitHub repos (null: no GitHub linked).
- top_types: the areas they code in most. ev: effort per area from their own counted code, 0 to 252; use it to judge focus, never quote it.
- codeProjects: projects with their own counted code. typeProjects: per area, projects where they wrote code in that area.
- n.demo: projects with a demo video or live link. n.own: projects where they wrote the most code on their team. n.mates: different teammates. n.kept: projects they kept adding code to after the event. n.docs: projects whose README they wrote.
- projects: their signature projects. tagline: the project's own pitch. prizes: prizes that project won. wrote_pct: percent of the project's counted code they wrote (null: not measured). kept: they kept adding code after the event. demo: has a demo video or live link. main_type: the area of most of their code on that project. caveats: if present, don't quote that project's wrote_pct.

Rules:
- Only state what the JSON shows. Never invent numbers, technologies, tools, languages, employers, schools, places, years or results (users, accuracy, speed, scale, what judges thought).
- Every number you write must appear in the JSON. Say a prize was won more than once only if the JSON lists it more than once.
- A habit ("usually ships a demo", "keeps building after events") needs its n count to be more than half of hacks; otherwise name the project where it happened.
- Name projects, prizes and events exactly as the JSON writes them.
- Never name a person. No gendered words (he, she, his, her, guy, girl). Prefer no pronoun; "they" is fine.
- No school, year of study, graduation or location: the JSON doesn't have them.
- Plain, warm and specific, like the examples: short sentences that start with a verb or a noun phrase. No hype ("rockstar", "passionate", "visionary"), no emojis, no exclamation marks, no URLs, no "@", no game words (EV, IV, dex).
- End each line with a period.

Tone examples, about other builders (match the tone, never reuse their wording or claims):
why: "Won Best Use of ML twice."
why: "Wrote the inference API for a winning ML hack."
why: "Deep backend work on ML pipelines. No wins yet."
sum: "Turns messy real-world data into ML demos that work on the first try."
sum: "The person who makes the model actually serve real traffic."
"""

STRICT = """
This is a second try: an earlier answer broke the rules listed in the message. Be literal this time:
- "why" at most 12 words, "sum" at most 16 words.
- Copy project, prize and event names exactly from the JSON. Write numbers as digits, and only numbers that are in the JSON.
- Name no technology, tool or language unless the JSON names it.
- No pronouns at all, and nothing about school, year, graduation or location.
"""

# ---------------------------------------------------------------- facts

URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
HANDLE_RE = re.compile(r"(?<![\w@])@\w[\w.-]*")


def _scrub(text: str) -> str:
    """Project text without links, emails or @handles, whitespace tidied."""
    t = URL_RE.sub("", text or "")
    t = EMAIL_RE.sub("", t)
    t = HANDLE_RE.sub("", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return " ".join(t.split())


def _clip(text: str, limit: int = MAX_TAGLINE) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:-—") + "…"


def _has(text: str, term: str, *, ignore_case: bool = True) -> bool:
    """Whole-word (or whole-phrase) match; works for terms like 'c++' and 'next.js'."""
    pat = rf"(?<!\w){re.escape(term)}(?!\w)"
    return re.search(pat, text, re.I if ignore_case else 0) is not None


def _name_terms(b: dict) -> list[str]:
    """The builder's name words and username, used only to keep them out of the facts."""
    terms = re.findall(r"[^\W\d_]{3,}", b.get("name") or "")
    if b.get("id"):
        terms.append(str(b["id"]))
    return terms


def facts_for_words(b: dict) -> dict:
    """The verified facts Gemini may write from: no name, username, school, place, year, links or dex.

    b is a builder in the final data shape (lib/types.ts Builder). Missing numbers stay None.
    """
    names = _name_terms(b)
    projects = []
    for p in (b.get("projects") or [])[:MAX_PROJECTS]:
        tagline = _scrub(p.get("desc") or "")
        # A tagline that names the builder ("Built by Maya ...") is left out rather than edited.
        if any(_has(tagline, t, ignore_case=(t == b.get("id"))) for t in names):
            tagline = ""
        proj = {
            "name": _scrub(p.get("name") or ""),
            "tagline": _clip(tagline) or None,
            "event": _scrub(p.get("event") or "") or None,
            "prizes": [x for x in (_scrub(z) for z in p.get("prizes") or []) if x],
            "wrote_pct": p.get("share"),
            "kept": p.get("kept"),
            "demo": p.get("demo"),
            "main_type": TYPE_LABELS.get(p.get("type") or ""),
        }
        if p.get("flags"):  # e.g. "possible shared laptop or squashed commits"
            proj["caveats"] = [str(f) for f in p["flags"]]
        projects.append(proj)
    ev = b.get("ev") or {}
    tp = b.get("typeProjects") or {}
    n = b.get("n") or {}
    return {
        "hacks": b.get("hacks"),
        "wins": b.get("wins"),
        "repos": b.get("repos"),
        "top_types": [TYPE_LABELS[t] for t in b.get("types") or [] if t in TYPE_LABELS],
        "ev": {label: ev.get(t) for t, label in TYPE_LABELS.items()},
        "codeProjects": b.get("codeProjects"),
        "typeProjects": {label: tp.get(t) for t, label in TYPE_LABELS.items()},
        "n": {k: n.get(k) for k in ("demo", "own", "mates", "kept", "docs")},
        "projects": projects,
    }


def facts_text(facts: dict) -> str:
    return json.dumps(facts, ensure_ascii=False)


# ---------------------------------------------------------------- checks

NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
NUM_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "twice": 2, "thrice": 3, "dozen": 12,
}
# "one", "once" and ordinals are left out: "one-click", "on the first try" are not counts.

# Named technologies: a line may only name one the facts name (taglines, prizes, project names).
TECH = (
    "python", "javascript", "typescript", "java", "kotlin", "swiftui", "rust", "golang", "c++", "c#", "ruby",
    "php", "dart", "scala", "solidity", "matlab", "verilog", "sql",
    "react", "next.js", "nextjs", "vue", "svelte", "angular", "node.js", "nodejs", "flask", "fastapi", "django",
    "tailwind", "three.js", "flutter", "expo", "unity", "unreal", "electron",
    "pytorch", "tensorflow", "keras", "sklearn", "scikit-learn", "opencv", "yolo", "hugging face", "huggingface",
    "langchain", "llm", "llms", "gpt", "chatgpt", "openai", "gemini", "claude", "anthropic", "cohere", "llama",
    "whisper", "elevenlabs", "rag", "cnn", "bert", "mediapipe",
    "aws", "gcp", "azure", "firebase", "supabase", "mongodb", "postgres", "postgresql", "mysql", "redis",
    "docker", "kubernetes", "snowflake", "vercel",
    "api", "apis", "graphql", "websocket", "websockets", "ios", "android", "arduino", "esp32", "stm32",
    "raspberry pi", "fpga", "figma", "blockchain", "web3", "ethereum", "solana",
)

GENDERED_RE = re.compile(r"\b(?:he|she|him|her|his|hers|himself|herself|guy|gal|girl|boy|woman|man|lady|gentleman)\b", re.I)
LINK_RE = re.compile(r"(?i)https?:|://|\bwww\.|\b[\w-]+\.(?:com|org|net|io|dev|app|ai|co|ca|me|xyz|gg|tech|so|sh|ly)\b")
GAME_RE = re.compile(r"\b(?:EVs?|IVs?)\b|\bdex\b", re.I)
YEAR_RE = re.compile(
    r"(?i)\b(?:\d+(?:st|nd|rd|th)|first|second|third|fourth|fifth|final|senior|junior)[- ]year\b"
    r"|\b(?:freshman|sophomore)\b|\bgraduat\w*|\bgrad\b|\bclass of\b")
PLACE_RE = re.compile(r"(?i)\b(?:based (?:in|out of)|located in|lives in|living in|hours? (?:away|from)|minutes from)\b")


def _load_places() -> tuple[str, ...]:
    """City and school names from data/places.json (shared with the UI)."""
    try:
        d = json.loads((DATA_DIR / "places.json").read_text())
    except (OSError, ValueError):
        return ()
    terms = {c["name"] for c in d.get("cities", [])}
    for s in d.get("schools", []):
        terms.update(x for x in (s.get("short"), s.get("full")) if x)
    return tuple(sorted(terms))


PLACES = _load_places()


def count_words(text: str) -> int:
    """Words as a reader counts them: "ML / AI" is two, "real-world" is one."""
    return sum(1 for t in (text or "").split() if re.search(r"\w", t))


def _numbers(text: str) -> set[str]:
    out = set()
    for m in NUM_RE.findall(text):
        s = m.replace(",", "")
        try:
            f = float(s)
        except ValueError:
            continue
        out.add(str(int(f)) if f.is_integer() else str(f))
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in NUM_WORDS:
            out.add(str(NUM_WORDS[w]))
    return out


def private_terms(b: dict) -> list[str]:
    """The builder's own school, program and city: checked in output, never sent to Gemini."""
    out = []
    for k in ("school", "schoolFull", "program", "city"):
        v = (b.get(k) or {}).get("value") if isinstance(b.get(k), dict) else None
        if isinstance(v, str) and len(v) >= 2:
            out.append(v)
    return out


def _novel(rx: re.Pattern, text: str, ft: str) -> list[str]:
    """Matches of rx in a line that the facts text doesn't itself contain."""
    return [m.group(0) for m in rx.finditer(text) if not _has(ft, m.group(0))]


def problems(text: str, facts: dict, max_words: int, *, private: Iterable[str] = ()) -> list[str]:
    """Why a line can't be shown (empty when it is fine). Messages never contain private values."""
    t = text or ""
    ft = facts_text(facts)
    out = []
    n = count_words(t)
    if n < MIN_WORDS:
        out.append(f"has {n} words; write at least {MIN_WORDS}")
    elif n > max_words:
        out.append(f"has {n} words; the limit is {max_words}")
    for num in sorted(_numbers(t) - _numbers(ft), key=lambda s: float(s)):
        out.append(f"the number {num} is not in the facts")
    if "@" in t or _novel(LINK_RE, t, ft):
        out.append('contains a link or "@"')
    tech = sorted(x for x in TECH if _has(t, x) and not _has(ft, x))
    if tech:
        out.append("names a technology the facts do not mention: " + ", ".join(tech))
    gendered = sorted({w.lower() for w in _novel(GENDERED_RE, t, ft)})
    if gendered:
        out.append("uses a gendered word: " + ", ".join(gendered))
    if _novel(GAME_RE, t, ft):
        out.append("uses internal score words (EV, IV, dex)")
    if _novel(YEAR_RE, t, ft):
        out.append("mentions year of study or graduation")
    if _novel(PLACE_RE, t, ft) or any(_has(t, p, ignore_case=False) and not _has(ft, p, ignore_case=False)
                                 for p in (*PLACES, *private)):
        out.append("mentions a school, program or place that is not in the facts")
    return out


def clean(text) -> str:
    """One tidy line: single spaces, no wrapping quotes, ends with a full stop."""
    t = " ".join(str(text or "").split())
    if len(t) >= 2 and t[0] in "\"'“‘`" and t[-1] in "\"'”’`":
        t = t[1:-1].strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t


# ---------------------------------------------------------------- template

def _plain_prize(prize: str) -> str:
    """'[MLH] Best Use of Gemini API' -> 'MLH Best Use of Gemini API'."""
    return " ".join(re.sub(r"\[([^\]]*)\]", r"\1", prize).split())


def _pct(v) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def _first_ok(candidates: list[str], facts: dict, limit: int, private: Iterable[str]) -> str:
    for c in candidates:
        if not problems(c, facts, limit, private=private):
            return c
    return candidates[-1]


def _template_lines(facts: dict, private: Iterable[str] = ()) -> dict:
    """Plain lines written straight from the facts; every candidate is checked like Gemini's."""
    projects = facts.get("projects") or []
    top = facts.get("top_types") or []
    whys: list[str] = []
    won = next((p for p in projects if p.get("prizes") and p.get("name")), None)
    if won:
        prize = _plain_prize(won["prizes"][0])
        if won.get("event"):
            whys.append(f"Won {prize} at {won['event']}.")
        whys += [f"Won {prize} with {won['name']}.", f"Won {prize}."]
    measured = [p for p in projects if isinstance(p.get("wrote_pct"), (int, float)) and p["wrote_pct"] >= 25
                and not p.get("caveats") and p.get("name")]
    if measured:
        best = max(measured, key=lambda p: p["wrote_pct"])
        if best.get("event"):
            whys.append(f"Wrote {_pct(best['wrote_pct'])}% of {best['name']} at {best['event']}.")
        whys.append(f"Wrote {_pct(best['wrote_pct'])}% of {best['name']}.")
    code = facts.get("codeProjects")
    if top and code:
        k = (facts.get("typeProjects") or {}).get(top[0])
        if k:
            whys.append(f"{top[0]} code on {k} of {code} hackathon projects.")
    hacks = facts.get("hacks")
    if hacks:
        whys.append(f"{hacks} hackathon{'s' if hacks != 1 else ''} on Devpost.")
    whys.append("Hackathon builder on Devpost.")

    sums: list[str] = []
    label = " and ".join(top[:2])
    if label and code:
        sums.append(f"{label} builder across {code} hackathon project{'s' if code != 1 else ''}.")
    if label:
        sums.append(f"{label} builder.")
    if hacks:
        sums.append(f"Hackathon builder with {hacks} hackathon{'s' if hacks != 1 else ''} on Devpost.")
    sums.append("Hackathon builder on Devpost.")
    return {"why": _first_ok(whys, facts, WHY_MAX, private), "sum": _first_ok(sums, facts, SUM_MAX, private)}


def template_words(b: dict) -> dict:
    """Template lines for one builder, no Gemini (run.py --no-words)."""
    return {**_template_lines(facts_for_words(b), private_terms(b)), "source": "template"}


# ---------------------------------------------------------------- Gemini

def _prompt(payload: str, issues: list[str] | None = None) -> str:
    p = f"Facts JSON:\n{payload}\n"
    if issues:
        p += "\nAn earlier answer was rejected because:\n" + "".join(f"- {i}\n" for i in issues)
        p += "Write new lines that follow every rule.\n"
    return p


def words_for(b: dict) -> dict:
    """{"why", "sum", "source"} for one builder: Gemini, one stricter retry, then the template."""
    facts = facts_for_words(b)
    private = private_terms(b)
    payload = facts_text(facts)
    got: dict[str, str | None] = {"why": None, "sum": None}
    issues: list[str] = []
    for attempt in range(2):
        try:
            resp = gemini.generate_json(
                _prompt(payload, issues if attempt else None), SCHEMA, namespace=NAMESPACE,
                system=SYSTEM if attempt == 0 else SYSTEM + STRICT, temperature=0.6 if attempt == 0 else 0.3,
            )
        except (gemini.GeminiError, OSError) as e:
            print(f"[words] {b.get('id')}: Gemini unavailable ({type(e).__name__}: {str(e)[:120]}); using the template", flush=True)
            break
        resp = resp if isinstance(resp, dict) else {}
        issues = []
        for field, limit in (("why", WHY_MAX), ("sum", SUM_MAX)):
            if got[field]:
                continue
            line = clean(resp.get(field))
            bad = problems(line, facts, limit, private=private)
            if bad:
                issues += [f"{field}: {x}" for x in bad]
            else:
                got[field] = line
        if all(got.values()):
            break
    if all(got.values()):
        return {"why": got["why"], "sum": got["sum"], "source": "gemini"}
    # Only the line(s) that failed twice come from the template.
    tpl = _template_lines(facts, private)
    return {"why": got["why"] or tpl["why"], "sum": got["sum"] or tpl["sum"], "source": "template"}


def write_words(builders: list[dict], *, workers: int = 4) -> dict[str, dict]:
    """{builder id: {"why", "sum", "source"}}; source is "template" when any line fell back."""
    before = dict(gemini.stats)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(words_for, builders))
    out = {b["id"]: r for b, r in zip(builders, results)}
    tpl = sum(1 for r in results if r["source"] == "template")
    print(f"[words] {len(results)} builders: {len(results) - tpl} gemini, {tpl} with a template line "
          f"({gemini.stats['calls'] - before['calls']} Gemini calls, {gemini.stats['cached'] - before['cached']} cached)",
          flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", nargs="?", default=str(DATA_DIR / "sample.json"), help="a Dataset JSON (default: the design samples)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N builders")
    ap.add_argument("--json", action="store_true", help="print the results as JSON")
    args = ap.parse_args(argv)

    builders = json.loads(open(args.dataset).read())["builders"]
    if args.limit:
        builders = builders[: args.limit]
    lines = write_words(builders)
    if args.json:
        json.dump(lines, sys.stdout, indent=2, ensure_ascii=False)
        return 0
    for b in builders:
        w = lines[b["id"]]
        print(f"\n{b['id']}  [{w['source']}]")
        print(f"  why  now: {w['why']}  ({count_words(w['why'])} words)")
        print(f"       was: {b.get('why', '')}")
        print(f"  sum  now: {w['sum']}  ({count_words(w['sum'])} words)")
        print(f"       was: {b.get('sum', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
