"""Field notes per builder: school, program, graduating, year of study, city, last active.

Rules (BUILD.md "Search criteria" and "Data pipeline" step 5):
- Every fact has the UI's Fact shape {"value", "source", "looked"} (lib/types.ts). A missing
  value is None, and `looked` names only the places we actually checked. Résumés are not public
  on Devpost, so "résumé" is never claimed as looked.
- Year of study: résumé (not available) -> People Data Labs education end date -> Devpost
  tagline (profile bio, else the member note on project pages). School and program come from
  the most recent post-secondary PDL education entry, else the tagline. City: PDL location ->
  the city on the Devpost profile -> the school's city (with the school's source).
- People Data Labs is asked only about the LinkedIn URL the person posted on their own Devpost
  profile, and a PDL record is used only when it carries that same LinkedIn URL. Nobody is
  matched across sites by name.
- PDL costs one credit per call. The raw answer (status + JSON body) is cached per normalised
  LinkedIn URL under cache/pdl/; a URL is never sent twice (a cached 404 is an answer); a hard
  budget (env PDL_MAX_CALLS, default 90) counts every call ever made from this cache, using a
  ledger written before each call. No key, no budget or an error -> None, and the Devpost
  tagline is used instead.
- The PDL key travels only in a request header; it is never printed, logged or written.
- Tagline parsing is conservative: when unsure it returns None. High-school students get no
  school or year. Nothing here goes into a model prompt.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import threading
import time
from bisect import bisect_right
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Iterator
from urllib.parse import unquote, urlencode

from . import config, github
from .config import CACHE_DIR, DATA_DIR
from .httpcache import Http, Resp

PDL = "People Data Labs"
DEVPOST = "Devpost"
GITHUB = "GitHub"

# Academic years end in April/May; a graduation with no month is taken as May.
DEFAULT_GRAD_MONTH = 5

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
_MONTH_NUM = {m.lower(): i + 1 for i, m in enumerate(MONTHS)} | {m[:3].lower(): i + 1 for i, m in enumerate(MONTHS)} | {"sept": 9}


def fact(value: Any, source: str | None, looked: list[str]) -> dict:
    """A Fact: the source is kept only when there is a value."""
    return {"value": value, "source": source if value is not None else None, "looked": list(looked)}


# ------------------------------------------------------------------ places

@lru_cache(maxsize=1)
def _places() -> dict:
    return json.loads((DATA_DIR / "places.json").read_text())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("‘", "'")).strip().lower()


# places.json is Ontario plus a few big Canadian cities outside it.
_CITY_PROVINCE = {"Montreal": "QC", "Vancouver": "BC", "Calgary": "AB", "Edmonton": "AB"}
PROVINCES = {
    "ontario": "ON", "on": "ON", "ont": "ON", "quebec": "QC", "québec": "QC", "qc": "QC",
    "british columbia": "BC", "bc": "BC", "alberta": "AB", "ab": "AB", "manitoba": "MB", "mb": "MB",
    "saskatchewan": "SK", "sk": "SK", "nova scotia": "NS", "ns": "NS", "new brunswick": "NB", "nb": "NB",
    "newfoundland and labrador": "NL", "newfoundland": "NL", "nl": "NL", "prince edward island": "PE",
    "pei": "PE", "pe": "PE", "yukon": "YT", "northwest territories": "NT", "nunavut": "NU",
}
CANADA = {"canada", "ca", "can"}  # Devpost writes "Toronto, ON, CA"
COUNTRIES = CANADA | {"united states", "united states of america", "usa", "us", "u.s.", "u.s.a.", "america"}

_SMALL_WORDS = {"of", "and", "the", "at", "for", "in", "on", "de", "du", "des", "la", "le", "et"}


def _titlecase(s: str) -> str:
    """'university of british columbia' -> 'University of British Columbia'; keeps 'BC', "Queen's"."""
    parts = re.split(r"(\s+|-|/)", s.strip())
    out = []
    for i, w in enumerate(parts):
        if not w or w.isspace() or w in "-/":
            out.append(w)
        elif w.isupper() and len(w) > 1:
            out.append(w)  # an acronym the person typed
        elif i > 0 and w.lower() in _SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return "".join(out)


def known_city(name: str, region: str | None = None, country: str | None = None) -> str | None:
    """The places.json city for a place name ('north york' -> 'Toronto'), or None.

    When a region or country is given it must agree, so 'London, England' and
    'Waterloo, Iowa' are not mistaken for the Ontario cities. places.json leaves
    bare 'london' and 'cambridge' out of the aliases on purpose; those names need
    the province ('London, Ontario').
    """
    if not name or not name.strip():
        return None
    n = _norm(name)
    for c in _places()["cities"]:
        province = c.get("region") or _CITY_PROVINCE.get(c["name"], "ON")
        confirmed = bool(region) and PROVINCES.get(_norm(region)) == province
        if n in c["aliases"] or (n == _norm(c["name"]) and confirmed):
            if country and _norm(country) not in CANADA:
                return None
            if region and not confirmed:
                return None
            return c["name"]
    return None


def _city_label(city: str, region: str | None = None, country: str | None = None) -> str:
    """A city that is not in places.json, with its province or region: 'Coquitlam, BC'."""
    label = _titlecase(city)
    if region:
        r = _norm(region)
        return f"{label}, {PROVINCES[r]}" if r in PROVINCES else f"{label}, {_titlecase(region)}"
    if country and _norm(country) not in CANADA:
        return f"{label}, {_titlecase(country)}"
    return label


def city_from_location(location: str | None) -> str | None:
    """The city named by a Devpost profile location, or None.

    Devpost locations read 'City, Region, Country'. A known city comes back as
    its places.json name ('Toronto, Ontario, Canada' -> 'Toronto'); another city
    keeps its province ('Coquitlam, British Columbia, Canada' -> 'Coquitlam, BC').
    'Ontario, Canada' and 'Canada' name no city.
    """
    if not location or not location.strip():
        return None
    whole = known_city(location)
    if whole:
        return whole
    parts = [p.strip() for p in location.split(",") if p.strip()]
    head = parts[0]
    if _norm(head) in PROVINCES or _norm(head) in COUNTRIES:
        return None
    if len(parts) == 1:
        return None  # a lone unknown word could be anything
    second = _norm(parts[1])
    if len(parts) >= 3 or second in PROVINCES:
        country = parts[2] if len(parts) >= 3 else None
        return known_city(head, parts[1], country) or _city_label(head, parts[1], country)
    if second in COUNTRIES:  # 'Toronto, Canada': only a known city is trusted
        return known_city(head, None, parts[1])
    return None


@dataclass(frozen=True)
class _School:
    short: str
    full: str
    city: str | None
    alias: str
    weak: bool


# Single-word aliases that are also common words, names or places. They count
# only in a school context ('cs @ waterloo', 'Western CS', 'Waterloo '27').
WEAK_ALIASES = {
    "waterloo", "uw", "western", "york", "queens", "queen's", "guelph", "carleton", "brock", "trent",
    "sheridan", "humber", "seneca", "centennial", "mohawk", "algonquin", "conestoga", "fanshawe",
    "concordia", "laurentian", "lakehead", "gbc", "utm", "uofo", "macu",
}
# Words that, right after a weak alias, mean a different place: 'York Region', 'UW Madison'.
_NOT_SCHOOL_NEXT = {
    "region", "regional", "county", "district", "park", "street", "st", "ave", "avenue", "road", "rd",
    "station", "college", "city", "washington", "michigan", "governors", "sydney", "australia",
    "kentucky", "carolina", "illinois", "oregon", "colorado", "new", "ny", "nyc", "madison",
    "seattle", "milwaukee", "bothell", "tacoma", "iowa",
}


@lru_cache(maxsize=1)
def _school_aliases() -> list[tuple[re.Pattern, _School]]:
    out = []
    for s in _places()["schools"]:
        for a in sorted({_norm(x) for x in s["aliases"]}, key=len, reverse=True):
            pat = re.escape(a).replace(r"\ ", r"\s+").replace("'", "['’]")
            out.append((re.compile(r"(?<![\w-])" + pat + r"(?![\w])", re.I),
                        _School(s["short"], s["full"], s.get("city"), a, a in WEAK_ALIASES)))
    out.sort(key=lambda t: len(t[1].alias), reverse=True)
    return out


def school_from_name(name: str) -> dict | None:
    """A structured school name (as PDL gives it) -> {short, full, city} from places.json.

    'university of waterloo' and 'the university of western ontario' match exactly;
    'york university - lassonde school of engineering' and "queen's university at
    kingston" match by their leading words. 'new york university' does not become
    York, and 'university of toronto schools' (a high school) does not become UofT.
    """
    n = re.sub(r"^the\s+", "", _norm(name))
    for _, s in _school_aliases():
        if n == s.alias:
            return {"short": s.short, "full": s.full, "city": s.city}
    for _, s in _school_aliases():
        if " " in s.alias and re.match(re.escape(s.alias) + r"\s*(?:[-–—,:(]|at\s|in\s|faculty\s|school\s+of\s|department\s)", n):
            return {"short": s.short, "full": s.full, "city": s.city}
    return None


# ------------------------------------------------------------------ taglines

_ENG = r"\s*eng(?:ineering|g|\.)?"  # 'eng', 'engg', 'eng.', 'engineering'; never 'engineer' (a job)

# (pattern, readable name, weak). Weak tokens are also ordinary words, so they
# count only right next to a school, year or 'student'.
PROGRAMS: list[tuple[str, str, bool]] = [
    (r"computer\s+science|comp\.?\s*sci(?:ence)?|compsci|cs|bcs", "Computer Science", False),
    (r"software" + _ENG + r"|softeng", "Software Engineering", False),
    (r"se", "Software Engineering", True),
    (r"electrical\s+(?:and|&)\s+computer" + _ENG + r"|ece", "Electrical and Computer Engineering", False),
    (r"computer" + _ENG + r"|comp\.?" + _ENG + r"|compe", "Computer Engineering", False),
    (r"ce", "Computer Engineering", True),
    (r"electrical" + _ENG + r"|elec\.?" + _ENG, "Electrical Engineering", False),
    (r"ee", "Electrical Engineering", True),
    (r"mechatronics?(?:" + _ENG + r")?|mte", "Mechatronics Engineering", False),
    (r"tron", "Mechatronics Engineering", True),  # Waterloo slang: 'tron @ uwaterloo'
    (r"mechanical" + _ENG + r"|mech\.?" + _ENG, "Mechanical Engineering", False),
    (r"mech", "Mechanical Engineering", True),
    (r"systems\s+design(?:" + _ENG + r")?|syde", "Systems Design Engineering", False),
    (r"biomedical" + _ENG + r"|biomed\.?" + _ENG + r"|bme", "Biomedical Engineering", False),
    (r"eng(?:ineering)?\.?\s*sci(?:ence)?|engsci", "Engineering Science", False),
    (r"chemical" + _ENG + r"|chem\.?" + _ENG, "Chemical Engineering", False),
    (r"civil" + _ENG, "Civil Engineering", False),
    (r"engineering", "Engineering", False),
    (r"engg?", "Engineering", True),
    (r"mathematics", "Mathematics", False),
    (r"maths?", "Mathematics", True),
    (r"statistics", "Statistics", False),
    (r"stats", "Statistics", True),
    (r"data\s+science", "Data Science", False),
    (r"ds", "Data Science", True),
    (r"computing\s+(?:and|&)\s+financial\s+management|cfm", "Computing and Financial Management", False),
    (r"business\s+administration|bba", "Business", False),
    (r"business", "Business", True),
    (r"commerce|b\.?comm?", "Commerce", True),
    (r"cognitive\s+science|cog\.?\s*sci|cogsci", "Cognitive Science", False),
    (r"design", "Design", True),
    (r"physics", "Physics", True),
    (r"economics|econ", "Economics", True),
]
_PROGRAM_RES = [(re.compile(r"(?<![\w-])(?:" + p + r")(?![\w])", re.I), name, weak) for p, name, weak in PROGRAMS]

_ORDINALS = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3, "4th": 4, "fourth": 4,
             "5th": 5, "fifth": 5, "final": 4}
_YEAR_ORD = re.compile(r"(?<![\w-])(" + "|".join(_ORDINALS) + r")[\s-]*(?:year|yr)s?(?![\w])", re.I)
_YEAR_NUM = re.compile(r"(?<![\w-])(?:year|yr)[\s-]*([1-5])(?![\w])", re.I)
_YEAR_US = re.compile(r"(?<![\w-])(freshman|sophomore)(?![\w])", re.I)  # not junior/senior: 'senior engineer'
_YEAR_WORDS = {**_ORDINALS, "freshman": 1, "sophomore": 2}
_TERM = re.compile(r"(?<![\w-])([1-5])[ab](?![\w])", re.I)  # Waterloo terms: 1A .. 4B
_UTERM = re.compile(r"(?<![\w-])u([1-5])(?![\w])", re.I)  # McGill-style U1 .. U3
_NEW_GRAD = re.compile(r"(?<![\w-])(?:new|recent|fresh)[\s-]+grad(?:uate)?s?(?![\w])"
                       r"|(?<![\w-])graduated(?![\w])(?!\s+(?:from\s+)?(?:high|secondary)\b)", re.I)
_ALUM = re.compile(r"(?<![\w-])alum(?:ni|na|nus|nae)?(?![\w])", re.I)
_POSTGRAD = re.compile(r"(?<![\w-])(?:ph\.?\s?d|doctoral|master'?s|msc|m\.sc|meng|m\.eng|masc|mmath|mcs|mba"
                       r"|postdoc|grad(?:uate)?\s+student)(?![\w])", re.I)

_MONTH_RE = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
_GRAD_CUE = re.compile(
    r"(?<![\w-])(?:class\s+of|c/o|grad(?:uat(?:ing|ion|ed)|\.)?|exp(?:ected|\.)?(?:\s+grad(?:uation|\.)?)?)"
    r"\s*[:\-]?\s*(?:in\s+)?(?:(" + _MONTH_RE + r")\.?,?\s+)?(['’]\d{2}|20[0-3]\d)(?![\w])", re.I)
_RANGE = re.compile(r"(?<![\w-])(20[0-3]\d)\s*[-–—]\s*(20[0-3]\d|present|now|current)(?![\w])", re.I)
_APOS_YEAR = re.compile(r"(?<![\d'’])['’](\d{2})(?![\w])")
_YEAR4 = re.compile(r"(?<![\w-])(20[1-3]\d)(?![\w])")
_HACK_WORDS = re.compile(r"hack\w*|htn|mlh|winner|won|finalist|conference|summit", re.I)

_CUE = re.compile(r"(?<![\w-])(?:students?|major(?:ing|ed)?|studying|studies|degree|undergrad(?:uate)?"
                  r"|bachelor'?s?|honou?rs|hons|co-?op|grad(?:uate)?|b\.?sc|b\.?a\.?sc|b\.?eng|b\.?math)(?![\w])", re.I)

_HS = re.compile(r"(?<![\w-])(?:grade|gr\.?)\s*(?:9|10|11|12)(?![\w])"
                 r"|(?<![\w-])high[\s-]?school(?:er)?s?(?![\w])|(?<![\w-])secondary\s+school(?![\w])", re.I)
_HS_NAMED = re.compile(r"(?<![\w-])[A-Z][\w.']*\s+(?:Secondary|Collegiate)(?![\w-])")  # 'Earl Haig Secondary'
# 'started coding in high school', 'mentor for high schoolers': about the past or about others.
_HS_NOT_ME = {"since", "from", "during", "after", "in", "back", "mentor", "mentoring", "mentored", "teach", "teaching",
              "taught", "teacher", "volunteer", "volunteering", "coach", "coaching", "former", "ex", "alum", "alumni",
              "graduated", "finished", "for", "helping", "help", "to", "with", "of", "about", "at"}
_HS_ME_IN = re.compile(r"(?:i'?m|i\s+am|currently|still|now)\s+in\s+$", re.I)

_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)?")
_ABBREV = {"st", "eng", "sci", "comp", "elec", "mech", "chem", "dept", "univ", "hons", "exp", "grad", "gr", "jr", "sr", "dr", "u"}


@dataclass(eq=False)
class _Hit:
    start: int
    end: int
    kind: str  # school | program | year | grad | cue
    m: re.Match
    value: Any = None  # the school or program name it stands for
    weak: bool = False


def _words_between(text: str, a: _Hit, b: _Hit) -> int:
    if a.start > b.start:
        a, b = b, a
    if b.start <= a.end:
        return 0
    return len(_WORD.findall(text[a.end:b.start]))


def _breaks(text: str, keep: list[_Hit]) -> list[int]:
    """Clause boundaries: | • · ; newlines, spaced dashes, and sentence ends (not 'St.', 'Comp. Sci.')."""
    inside = lambda i: any(h.start <= i < h.end for h in keep)  # noqa: E731 - never split a date range
    out = [m.start() for m in re.finditer(r"[|•·;\n\r]|\s[-–—]\s", text) if not inside(m.start())]
    for m in re.finditer(r"[.!?](?=\s+[A-Z]|\s*$)", text):
        prev = re.search(r"([^\W_]+)$", text[:m.start()])
        if prev and (prev.group(1).lower() in _ABBREV or len(prev.group(1)) == 1):
            continue
        out.append(m.start())
    return sorted(out)


def _find(regex: re.Pattern, text: str, kind: str, **kw: Any) -> list[_Hit]:
    return [_Hit(m.start(), m.end(), kind, m, **kw) for m in regex.finditer(text)]


def _non_overlapping(hits: list[_Hit]) -> list[_Hit]:
    """Longest match wins at each place ('software engineering' over 'engineering')."""
    out: list[_Hit] = []
    for h in sorted(hits, key=lambda h: (h.start, -(h.end - h.start))):
        if not out or h.start >= out[-1].end:
            out.append(h)
    return out


def _is_hs(text: str) -> bool:
    for m in _HS.finditer(text):
        before = text[:m.start()]
        prev = [w.lower() for w in _WORD.findall(before)[-2:]]
        if m.group(0).lower().startswith(("grade", "gr")):
            return True
        if _HS_ME_IN.search(before):
            return True
        if any(w in _HS_NOT_ME for w in prev):
            continue
        if re.match(r"\s+(?:students|teachers?|outreach)\b", text[m.end():], re.I):
            continue
        return True
    return bool(_HS_NAMED.search(text))


def parse_tagline(text: str) -> dict:
    """Read school, program, year of study and graduation year from a Devpost tagline.

    Returns {"school": None | {"short", "full", "city"}, "program": str | None,
    "year": int | None (1..5, 0 = new grad / graduated), "grad_year": int | None,
    "grad_month": int | None, "hs": bool (high-school student), "postgrad": bool
    (master's / PhD: no year of study is implied)}. Conservative: anything ambiguous
    is None. Examples: 'cs @ waterloo', '3rd year CS at UofT', 'UofT CS 2027',
    "Computer Engineering @ McMaster '27", 'BBA/CS @ Laurier'.
    """
    out = {"school": None, "program": None, "year": None, "grad_year": None, "grad_month": None, "hs": False, "postgrad": False}
    t = (text or "").replace("’", "'").replace("‘", "'").strip()
    if not t:
        return out
    if _is_hs(t):
        out["hs"] = True
        return out
    out["postgrad"] = bool(_POSTGRAD.search(t))

    # Candidates ----------------------------------------------------------
    schools = []
    for rx, s in _school_aliases():
        schools += _find(rx, t, "school", value=s, weak=s.weak)
    schools = _non_overlapping(schools)
    programs = []
    for rx, name, weak in _PROGRAM_RES:
        programs += _find(rx, t, "program", value=name, weak=weak)
    programs = _non_overlapping([p for p in programs if not any(s.start < p.end and p.start < s.end for s in schools)])
    ranges = _find(_RANGE, t, "grad", weak=True)
    cues = [h for h in _find(_CUE, t, "cue") if not any(p.start <= h.start < p.end for p in programs)]
    grad_cues = _find(_GRAD_CUE, t, "grad")
    taken = ranges + grad_cues
    apos = [h for h in _find(_APOS_YEAR, t, "grad", weak=True) if not any(x.start <= h.start < x.end for x in taken)]
    year4 = [h for h in _find(_YEAR4, t, "grad", weak=True) if not any(x.start <= h.start < x.end for x in taken + schools)]
    ord_years = _find(_YEAR_ORD, t, "year") + _find(_YEAR_NUM, t, "year") + _find(_YEAR_US, t, "year")
    terms = _find(_TERM, t, "year", weak=True) + _find(_UTERM, t, "year", weak=True)
    breaks = _breaks(t, ranges)

    def clause(i: int) -> int:
        return bisect_right(breaks, i)

    def near(h: _Hit, others: list[_Hit], window: int | None = None) -> bool:
        """Same clause and few words apart (one word when either side is a weak token)."""
        for o in others:
            if o is h or clause(o.start) != clause(h.start):
                continue
            w = window if window is not None else (1 if (h.weak or o.weak) else 3)
            if _words_between(t, h, o) <= w:
                return True
        return False

    def alone(h: _Hit) -> bool:
        """The hit is a bio segment of its own: 'U of T | Class of '27 | Computer Science'."""
        k = clause(h.start)
        lo = breaks[k - 1] + 1 if k > 0 else 0
        hi = breaks[k] if k < len(breaks) else len(t)
        return not _WORD.findall(_CUE.sub(" ", t[lo:h.start] + " " + t[h.end:hi]))

    # Schools -------------------------------------------------------------
    picked = None
    for s in schools:
        before = t[:s.start]
        if re.search(r"(?:\bex-?|\bprev(?:iously)?\.?|\bformer(?:ly)?)\s*$", before, re.I):
            continue
        if re.match(r"\s+schools?\b", t[s.end:], re.I):
            continue  # 'University of Toronto Schools' is a high school
        if s.weak:
            nxt = re.match(r"(?:\s+|[-–])([A-Za-z]+)", t[s.end:])
            if nxt and nxt.group(1).lower() in _NOT_SCHOOL_NEXT:
                continue
            if re.match(r"[-–]\w", t[s.end:]) or re.search(r"\bnew\s+$", before, re.I):
                continue  # 'UW-Madison', 'New York'
            context = (re.search(r"(?:@|(?<![\w])(?:at|attending|attends))\s*$", before, re.I)
                       or re.search(r"\b(?:graduat\w*|grad|alum\w*)\b[^|•·;\n]*\bfrom\s*$", before, re.I)
                       or near(s, programs + terms + apos + year4 + grad_cues, 0)
                       or re.match(r"\s+(?:students?|alum\w*|grad(?:uate)?s?|undergrad\w*|co-?op)\b", t[s.end:], re.I))
            if not context:
                continue
        picked = s
        break
    if picked:
        sv: _School = picked.value
        out["school"] = {"short": sv.short, "full": sv.full, "city": sv.city}
    anchors_school = [picked] if picked else []

    # Years and grad years that can anchor a program.
    strong_years = [y for y in ord_years if near(y, anchors_school + programs + cues)]
    good_terms = [y for y in terms if near(y, anchors_school + programs, 1)]
    hack_words = _find(_HACK_WORDS, t, "cue")  # 'HTN 2025 winner'

    def grad_ok(g: _Hit) -> bool:
        if g in grad_cues:
            return True
        bare = g in apos or g in year4
        return (near(g, anchors_school + programs + good_terms, 0 if bare else 1)
                and not (bare and near(g, hack_words, 0))
                and not (bare and re.search(r"\b(?:since|from|in|started|starting|est\.?|circa|until)\s*$", t[:g.start], re.I)))

    good_grads = [g for g in grad_cues + ranges + apos + year4 if grad_ok(g)]
    anchors = anchors_school + strong_years + good_terms + good_grads + cues

    # Programs: next to the school, a year or a 'student'-type word; never a minor.
    def minor(p: _Hit) -> bool:
        return bool(re.match(r"\s+minor\b", t[p.end:], re.I) or re.search(r"\bminor(?:ing)?\s+in\s+$", t[:p.start], re.I))

    chosen = [p for p in programs if not minor(p) and near(p, anchors)]
    if not chosen and (picked or good_grads or strong_years):
        chosen = [p for p in programs if not p.weak and not minor(p) and alone(p)]
    if chosen:
        first = chosen[0]
        if first.value == "Engineering":  # 'UofT Engineering, ECE': the specific program wins
            first = next((p for p in chosen if p.value != "Engineering" and "Engineering" in p.value), first)
        names = [first.value]
        # 'BBA/CS', 'CS + Stats', 'Math and CS': a double major written as one.
        joined = re.compile(r"\s*(?:/|\+|&|and)\s*", re.I)
        prev = next((p for p in reversed(programs) if p.end <= first.start), None)
        nxt = next((p for p in programs if p.start >= first.end), None)
        if prev and prev.value != first.value and not minor(prev) and joined.fullmatch(t[prev.end:first.start]):
            names.insert(0, prev.value)
        elif nxt and nxt.value != first.value and not minor(nxt) and joined.fullmatch(t[first.end:nxt.start]):
            names.append(nxt.value)
        if len(names) == 2 and "Engineering" in names:
            names.remove("Engineering")
        out["program"] = " and ".join(names)

    # A year standing alone in its own bio segment ('cs @ uoft · 2nd year') counts
    # when the bio names a school or program elsewhere.
    if picked or chosen:
        strong_years += [y for y in ord_years if y not in strong_years and alone(y)]

    # Graduation year -------------------------------------------------------
    for g in sorted(good_grads, key=lambda h: h.start):
        m = g.m
        if g in ranges:
            end = m.group(2)
            if not end.isdigit() or int(end) <= int(m.group(1)):
                continue
            out["grad_year"] = int(end)
        elif g in grad_cues:
            y = m.group(2).lstrip("'’")
            out["grad_year"] = int(y) if len(y) == 4 else 2000 + int(y)
            if m.group(1):
                out["grad_month"] = _MONTH_NUM.get(m.group(1).lower().rstrip("."))
        else:
            y = m.group(1)
            out["grad_year"] = int(y) if len(y) == 4 else 2000 + int(y)
        if not 2010 <= out["grad_year"] <= 2035:
            out["grad_year"] = out["grad_month"] = None
            continue
        break

    # Year of study -------------------------------------------------------
    year_hits = [(h.start, _YEAR_WORDS.get(h.m.group(1).lower()) or int(h.m.group(1))) for h in strong_years]  # '3rd' or '3'
    year_hits += [(h.start, int(h.m.group(1))) for h in good_terms]
    year_hits += [(h.start, 0) for h in _find(_NEW_GRAD, t, "year")]
    year_hits += [(h.start, 0) for h in _find(_ALUM, t, "year") if near(h, anchors_school, 1)]
    if year_hits and not out["postgrad"]:
        out["year"] = sorted(year_hits)[0][1]
    return out


# ------------------------------------------------------------------ years

def year_from_grad(grad_year: int, grad_month: int | None, today: date) -> int:
    """Year of study implied by a graduation date: 1..5, or 0 once it has passed.

    Academic years end in April/May, so from September on the running academic
    year ends next calendar year. years_left = grad_year - that year, and
    year = clamp(4 - years_left, 1, 5). This assumes a 4-year degree: a student
    in a 5-year co-op program reads one year low until their final year. A
    graduation with no month is taken as May; one later in the calendar year
    than today (a December finish) is the final year, 4.
    """
    month = grad_month or DEFAULT_GRAD_MONTH
    if (grad_year, month) < (today.year, today.month):
        return 0
    ay_end = today.year + 1 if today.month >= 9 else today.year
    years_left = max(0, grad_year - ay_end)
    return max(1, min(5, 4 - years_left))


def grad_label(year: int, month: int | None) -> str:
    """'April 2028', or '2028' when the month is not known."""
    return f"{MONTHS[month - 1]} {year}" if month and 1 <= month <= 12 else str(year)


# ------------------------------------------------------------------ PDL records

def _pdl_date(s: Any) -> tuple[int, int | None] | None:
    """PDL dates are 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD'."""
    m = re.match(r"^(\d{4})(?:-(\d{2}))?", s) if isinstance(s, str) else None
    if not m:
        return None
    month = int(m.group(2)) if m.group(2) else None
    return int(m.group(1)), (month if month and 1 <= month <= 12 else None)


def _program_name(s: str) -> str | None:
    """A PDL major ('computer science') as a readable name via the program table."""
    for rx, name, _weak in _PROGRAM_RES:
        if rx.fullmatch(s.strip()):
            return name
    return None


_POSTGRAD_DEGREE = re.compile(r"\b(?:master|mba|doctor|ph\.?\s?d|m\.?sc|m\.?eng|m\.?a\.?sc|postgrad)", re.I)


def _short_stay(start: tuple[int, int | None], end: tuple[int, int | None]) -> bool:
    """Under six months (an exchange term, a summer program), or within one year when months are unknown."""
    if start[1] and end[1]:
        return (end[0] * 12 + end[1]) - (start[0] * 12 + start[1]) < 6
    return end[0] == start[0]


def pdl_education(person: dict) -> dict | None:
    """The most recent post-secondary education entry in a PDL person record.

    Returns {"school": {short, full, city}, "program": str | None,
    "end": (year, month | None) | None, "postgrad": bool}. Most recent = latest
    end date; an entry with a start but no end date is ongoing (PDL leaves
    end_date empty while someone is enrolled). Entries shorter than about a
    term (summer programs, exchanges) are not someone's school.
    """
    best, best_key = None, None
    for i, e in enumerate(person.get("education") or []):
        if not isinstance(e, dict):
            continue
        sch = e.get("school") or {}
        name = sch.get("name") if isinstance(sch, dict) else None
        if not name:
            continue
        stype = (sch.get("type") or "").lower()
        if stype and stype != "post-secondary institution":
            continue
        if re.search(r"high school|secondary school|collegiate|\bschools$|\bacademy$", name.strip(), re.I):
            continue  # PDL types some high schools as post-secondary ('university of toronto schools')
        end, start = _pdl_date(e.get("end_date")), _pdl_date(e.get("start_date"))
        if end and start and _short_stay(start, end):
            continue
        when = (end[0], end[1] or 0) if end else ((9999, 0) if start else (-1, 0))
        key = (when, (start[0], start[1] or 0) if start else (-1, 0), -i)
        if best_key is None or key > best_key:
            best, best_key = (e, sch, end), key
    if best is None:
        return None
    e, sch, end = best
    school = school_from_name(sch["name"])
    if school is None:
        loc = sch.get("location") if isinstance(sch.get("location"), dict) else {}
        city = None
        if loc.get("locality"):
            city = known_city(loc["locality"], loc.get("region"), loc.get("country")) or _city_label(loc["locality"], loc.get("region"), loc.get("country"))
        full = _titlecase(sch["name"])
        school = {"short": full, "full": full, "city": city}
    names = []
    for mj in e.get("majors") or []:
        if isinstance(mj, str) and mj.strip():
            n = _program_name(mj) or _titlecase(mj)
            if n not in names:
                names.append(n)
    if not names:  # 'bachelor of software engineering'
        for dg in e.get("degrees") or []:
            for rx, name, weak in _PROGRAM_RES:
                if isinstance(dg, str) and not weak and rx.search(dg) and name not in names:
                    names.append(name)
    postgrad = any(isinstance(d, str) and _POSTGRAD_DEGREE.search(d) for d in e.get("degrees") or [])
    return {"school": school, "program": " and ".join(names[:2]) or None, "end": end, "postgrad": postgrad}


def pdl_city(person: dict) -> str | None:
    """The person's city from PDL's location fields (a known city, else any named city)."""
    loc = person.get("location_locality")
    if not isinstance(loc, str) or not loc.strip():
        return None
    region = person.get("location_region") if isinstance(person.get("location_region"), str) else None
    country = person.get("location_country") if isinstance(person.get("location_country"), str) else None
    return known_city(loc, region, country) or _city_label(loc, region, country)


# ------------------------------------------------------------------ field notes

def _tagline_for(profile: dict, member_note: str) -> dict:
    """Parse the profile bio; fall back to the project-page member note as a whole (texts are never mixed)."""
    first = parse_tagline(profile.get("bio") or "")
    if first["hs"] or any(first[k] is not None for k in ("school", "program", "year", "grad_year")):
        return first
    return parse_tagline(member_note or "")


def person_facts(profile: dict, pdl: dict | None, *, member_note: str = "", today: date) -> dict:
    """Field notes facts: school (short), schoolFull, program, grad, year, city.

    `pdl` is the PDL person record from pdl_enrich: a dict when PDL was checked
    ({} = checked, nothing usable), None when it was not (no LinkedIn on Devpost,
    no key, no budget, or an error). Only checked sources are listed in `looked`.
    A Devpost tagline fills gaps next to PDL only when it names the same school
    (or none); a high-school tagline overrides PDL education (often a summer
    program at a university).
    """
    profile = profile or {}
    looked = ([PDL] if pdl is not None else []) + [DEVPOST]
    person = pdl["data"] if isinstance(pdl, dict) and "status" in pdl and isinstance(pdl.get("data"), dict) else (pdl or {})
    tag = _tagline_for(profile, member_note)
    edu = pdl_education(person) if person and not tag["hs"] else None
    tag_ok = edu is None or tag["school"] is None or tag["school"]["short"] == edu["school"]["short"]

    school = school_src = program = program_src = None
    if edu:
        school, school_src = edu["school"], PDL
        if edu["program"]:
            program, program_src = edu["program"], PDL
        elif tag["program"] and tag_ok:
            program, program_src = tag["program"], DEVPOST
    elif tag["school"] or tag["program"]:
        school, school_src = tag["school"], DEVPOST
        program, program_src = tag["program"], DEVPOST

    grad = grad_src = year = year_src = None
    no_year = tag["postgrad"] or bool(edu and edu["postgrad"])  # a master's year is not a year of study
    if edu and edu["end"]:
        gy, gm = edu["end"]
        grad, grad_src = grad_label(gy, gm), PDL
        if not no_year:
            year, year_src = year_from_grad(gy, gm, today), PDL
    if tag_ok and grad is None and tag["grad_year"]:
        grad, grad_src = grad_label(tag["grad_year"], tag["grad_month"]), DEVPOST
    if tag_ok and year is None and not no_year and not (edu and edu["end"]):
        if tag["year"] is not None:
            year, year_src = tag["year"], DEVPOST
        elif tag["grad_year"]:
            year, year_src = year_from_grad(tag["grad_year"], tag["grad_month"], today), DEVPOST

    city, city_src = (pdl_city(person) if person else None), PDL
    if city is None:
        city, city_src = city_from_location(profile.get("location")), DEVPOST
    if city is None and school and school.get("city"):
        city, city_src = school["city"], school_src

    return {
        "school": fact(school["short"] if school else None, school_src, looked),
        "schoolFull": fact(school["full"] if school else None, school_src, looked),
        "program": fact(program, program_src, looked),
        "grad": fact(grad, grad_src, looked),
        "year": fact(year, year_src, looked),
        "city": fact(city, city_src, looked),
    }


def github_facts(login: str | None) -> dict:
    """{"repos": public repo count | None, "lastActive": Fact of the latest public push (ISO)}.

    `login` is the GitHub account linked on the person's own Devpost profile.
    """
    looked = [GITHUB]
    if not login:
        return {"repos": None, "lastActive": fact(None, None, looked)}
    u = github.user(login)
    if u is None:  # the account is gone or renamed
        return {"repos": None, "lastActive": fact(None, None, looked)}
    repos = u.get("public_repos")
    last = github.latest_push(login)
    return {"repos": repos if isinstance(repos, int) else None, "lastActive": fact(last or None, GITHUB, looked)}


# ------------------------------------------------------------------ People Data Labs

PDL_URL = "https://api.peopledatalabs.com/v5/person/enrich"
PDL_DIR = CACHE_DIR / "pdl"
# Hard budget: the account has about 99 lookups left and every call may use one.
PDL_MAX_CALLS = int(os.environ.get("PDL_MAX_CALLS") or 90)
# Answers about the URL itself; never asked again. 401/402/403/429/5xx are about
# the account or the moment, so they stop PDL for this run instead.
ANSWERED = {200, 400, 404, 422}
_KEEP_HEADERS = ("x-call-credits-spent", "x-call-credits-type", "x-ratelimit-limit", "x-ratelimit-remaining",
                 "x-ratelimit-reset", "x-lifetime-used", "x-totallimit-remaining", "x-totallimit-purchased-remaining",
                 "x-totallimit-overages-remaining", "retry-after")
# One attempt per call (a retry could cost another credit); the key goes in a header per request.
_http = Http("pdl", min_interval=1.0, max_retries=1, keep_headers=_KEEP_HEADERS)
_lock = threading.Lock()
_stopped: str | None = None  # why PDL calls stopped for this run, if they did
stats = {"calls": 0, "cached": 0, "no_key": 0, "no_budget": 0, "errors": 0, "rejected": 0}

_LINKEDIN = re.compile(r"^(?:https?://)?(?:[a-z]{2,3}\.)?(?:www\.)?linkedin\.com/in/([^/?#\s]+)", re.I)


def normalize_linkedin(url: str | None) -> str | None:
    """'https://ca.linkedin.com/in/Eu-Lee?trk=x' -> 'https://www.linkedin.com/in/eu-lee/' (None if not a profile)."""
    m = _LINKEDIN.match((url or "").strip())
    if not m:
        return None
    slug = unquote(m.group(1)).strip().lower()
    if not slug or len(slug) > 100 or re.search(r"[\s/]", slug):
        return None
    return f"https://www.linkedin.com/in/{slug}/"


def _slug(norm: str) -> str:
    return norm.rstrip("/").rsplit("/", 1)[-1]


def _request_url(norm: str) -> str:
    return PDL_URL + "?" + urlencode({"profile": f"linkedin.com/in/{_slug(norm)}"})


def _answer_path(norm: str):
    return PDL_DIR / (hashlib.sha1(norm.encode()).hexdigest() + ".json")


def _read_answer(norm: str) -> dict | None:
    p = _answer_path(norm)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_answer(norm: str, r: Resp) -> dict:
    try:
        body, raw = json.loads(r.text), None
    except ValueError:
        body, raw = None, r.text[:2000]
    rec = {"url": norm, "request": _request_url(norm), "status": r.status, "headers": dict(r.headers),
           "body": body, "text": raw, "fetched_at": time.time()}
    p = _answer_path(norm)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec))
    tmp.replace(p)
    return rec


def calls_used() -> int:
    """PDL calls ever made from this cache (this process included): one ledger line per call."""
    ledger = PDL_DIR / "calls.jsonl"
    lines = sum(1 for ln in ledger.read_text().splitlines() if ln.strip()) if ledger.exists() else 0
    answers = len(list(PDL_DIR.glob("*.json"))) if PDL_DIR.exists() else 0
    return max(lines, answers)


def budget_left() -> int:
    return max(0, PDL_MAX_CALLS - calls_used())


@contextmanager
def _exclusive() -> Iterator[None]:
    """One PDL call at a time across threads and processes, so the budget and the cache stay exact."""
    PDL_DIR.mkdir(parents=True, exist_ok=True)
    with _lock, open(PDL_DIR / ".lock", "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _linkedin_matches(person: dict, norm: str) -> bool | None:
    """Does the PDL record carry the LinkedIn URL we asked about? None when it lists none."""
    seen = set()
    for v in [person.get("linkedin_url"), *[p.get("url") for p in person.get("profiles") or [] if isinstance(p, dict) and p.get("network") == "linkedin"]]:
        n = normalize_linkedin(v) if isinstance(v, str) else None
        if n:
            seen.add(_slug(n))
    if isinstance(person.get("linkedin_username"), str):
        seen.add(person["linkedin_username"].lower())
    if not seen:
        return None
    return _slug(norm) in seen


def _person_from(rec: dict, norm: str) -> dict | None:
    """Raw answer -> person record ({} when PDL has nothing usable, None when it was not really checked)."""
    if rec.get("status") == 404:
        return {}
    if rec.get("status") != 200:
        return None  # 400/422: the request itself was refused
    data = (rec.get("body") or {}).get("data") if isinstance(rec.get("body"), dict) else None
    if not isinstance(data, dict):
        return {}
    if _linkedin_matches(data, norm) is False:
        stats["rejected"] += 1
        return {}
    return data


def pdl_record(linkedin_url: str | None) -> dict | None:
    """The cached raw PDL answer for a LinkedIn URL (never calls the network)."""
    norm = normalize_linkedin(linkedin_url)
    return _read_answer(norm) if norm else None


def pdl_enrich(linkedin_url: str | None) -> dict | None:
    """People Data Labs person record for a LinkedIn URL posted on the person's own Devpost profile.

    Returns the PDL `data` record on a match, {} when PDL answered but has no
    usable record (404, or a record for a different LinkedIn URL), and None when
    PDL was not asked: no key, budget used up, an error earlier in this run, or
    not a LinkedIn profile URL. Each URL is sent at most once, ever.
    """
    global _stopped
    norm = normalize_linkedin(linkedin_url)
    if norm is None:
        return None
    rec = _read_answer(norm)
    if rec is not None:
        stats["cached"] += 1
        return _person_from(rec, norm)
    key = config.PDL_API_KEY
    if not key:
        stats["no_key"] += 1
        return None
    with _exclusive():
        rec = _read_answer(norm)
        if rec is None:  # an answer Http cached but we never filed (e.g. a crash in between)
            hit = _http.cached(_request_url(norm), "application/json")
            rec = _write_answer(norm, hit) if hit is not None and hit.status in ANSWERED else None
        if rec is not None:
            stats["cached"] += 1
            return _person_from(rec, norm)
        if _stopped:
            return None
        if calls_used() >= PDL_MAX_CALLS:
            stats["no_budget"] += 1
            return None
        # Count the call before making it: one that dies half-way may still have used a credit.
        with open(PDL_DIR / "calls.jsonl", "a") as fh:
            fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "url": norm}) + "\n")
        stats["calls"] += 1
        try:
            r = _http.get(_request_url(norm), accept="application/json", extra_headers={"X-Api-Key": key})
        except Exception as e:  # network failure, or 429/5xx after the single attempt
            _stopped = f"PDL request failed ({type(e).__name__}); no more PDL calls this run"
            stats["errors"] += 1
            print(f"[pdl] {_stopped}", flush=True)
            return None
        if r.status in ANSWERED:
            return _person_from(_write_answer(norm, r), norm)
        _stopped = f"PDL answered HTTP {r.status}; no more PDL calls this run"
        stats["errors"] += 1
        print(f"[pdl] {_stopped}", flush=True)
        return None

__all__ = [
    "parse_tagline", "year_from_grad", "grad_label", "person_facts", "github_facts", "pdl_enrich", "pdl_record",
    "normalize_linkedin", "budget_left", "calls_used", "known_city", "city_from_location", "school_from_name",
    "pdl_education", "pdl_city", "fact", "stats", "PDL_MAX_CALLS",
]


# ------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    """Print field notes for a Devpost project's team (warms the Devpost and GitHub caches).

        python -m talentdex.enrich plant-hopper            # tagline + Devpost + GitHub only
        python -m talentdex.enrich plant-hopper --pdl      # may spend PDL credits (each URL once)
    """
    from . import devpost

    ap = argparse.ArgumentParser(description=main.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", help="Devpost software slug or URL")
    ap.add_argument("--pdl", action="store_true", help="ask People Data Labs (uses budget for uncached URLs)")
    args = ap.parse_args(argv)
    project = devpost.fetch_project(args.project)
    if project is None:
        raise SystemExit(f"Devpost project not found: {args.project}")
    today = date.today()
    for m in project["members"]:
        prof = devpost.fetch_profile(m["username"]) or {}
        li = prof.get("linkedin")
        if args.pdl and li:
            pdl = pdl_enrich(li)
        else:
            cached = pdl_record(li)
            pdl = _person_from(cached, normalize_linkedin(li)) if cached else None
        facts = person_facts(prof, pdl, member_note=m.get("note", ""), today=today)
        print(f"{m['username']}  bio={prof.get('bio')!r}  note={m.get('note')!r}  location={prof.get('location')!r}")
        print(f"  tagline: {parse_tagline(prof.get('bio') or m.get('note') or '')}")
        for k, f in facts.items():
            print(f"  {k:<10} {f['value']!r:<32} {f['source'] or '-':<17} looked {f['looked']}")
        gh = github_facts(prof.get("github"))
        print(f"  repos      {gh['repos']!r}   lastActive {gh['lastActive']['value']!r}")
    print(f"PDL: {stats}  budget left {budget_left()} of {PDL_MAX_CALLS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
