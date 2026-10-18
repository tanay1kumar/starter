"""Words tests: the facts JSON, the line checks, the template and the retry flow.

All offline. Gemini is replaced by a fake, except test_sample_lines_are_valid,
which serves the design samples from pipeline/cache/ (or falls back to the
template) with the Gemini client switched off, so it never calls out.
"""

from __future__ import annotations

import json
import re

import pytest

from talentdex import gemini, words
from talentdex.config import DATA_DIR
from talentdex.words import (
    SUM_MAX, WHY_MAX, clean, count_words, facts_for_words, problems, template_words, words_for, write_words,
)


def fact(v, source="Devpost"):
    return {"value": v, "source": source, "looked": ["résumé", "People Data Labs", "Devpost"]}


def builder(**over) -> dict:
    """A builder in the final data shape with distinctive personal details to look for."""
    b = {
        "id": "zxquinn",
        "name": "Quinn Zabrowski",
        "dex": "0613",
        "types": ["ml", "backend"],
        "school": fact("Trent"),
        "schoolFull": fact("Trent University"),
        "program": fact("Systems Design Engineering"),
        "grad": fact("April 2027"),
        "year": fact(3),
        "city": fact("Peterborough"),
        "lastActive": fact("2026-09-30T12:00:00Z", "GitHub"),
        "links": {"devpost": "https://devpost.com/zxquinn", "github": "https://github.com/zxq-gh",
                  "linkedin": "https://www.linkedin.com/in/quinn-z"},
        "email": "quinn@example.com",
        "photo": "https://example.com/quinn.png",
        "hacks": 5, "wins": 2, "repos": 17,
        "why": "old why", "sum": "old sum",
        "ev": {"ml": 200, "backend": 150, "frontend": 40, "design": 0, "mobile": 0, "hardware": 0},
        "evFrom": {"ml": ["Leaf Lens"], "backend": ["Queue Less"]},
        "iv": [20, 25, 18, 9, 14, 30],
        "n": {"demo": 4, "own": 3, "mates": 8, "kept": 1, "docs": 2},
        "codeProjects": 4,
        "typeProjects": {"ml": 3, "backend": 2, "frontend": 1, "design": 0, "mobile": 0, "hardware": 0},
        "projects": [
            {"id": "leaf-lens", "name": "Leaf Lens", "abbr": "Ll", "type": "ml", "event": "DeltaHacks 11",
             "desc": "Spot crop disease from one photo with a PyTorch model.", "prize": "Best Use of AI",
             "prizes": ["Best Use of AI"], "kept": True, "share": 64, "url": "https://devpost.com/software/leaf-lens",
             "repo": "https://github.com/zxq-gh/leaf-lens", "demo": True, "flags": [], "inScan": True},
            {"id": "queue-less", "name": "Queue Less", "abbr": "Ql", "type": "backend", "event": "Hack the 6ix 2025",
             "desc": "Real-time ER wait estimates from public data feeds.", "prize": "", "prizes": [],
             "kept": False, "share": None, "url": "https://devpost.com/software/queue-less", "repo": None,
             "demo": False, "flags": [], "inScan": True},
        ],
    }
    b.update(over)
    return b


SECRETS = ["Quinn", "Zabrowski", "zxquinn", "0613", "Trent", "Systems Design", "April 2027", "2027",
           "Peterborough", "devpost.com", "github.com", "linkedin", "zxq-gh", "example.com", "quinn@", "http"]


# ---------------------------------------------------------------- facts

def test_facts_keep_only_the_allowed_fields():
    f = facts_for_words(builder())
    assert list(f) == ["hacks", "wins", "repos", "top_types", "ev", "codeProjects", "typeProjects", "n", "projects"]
    assert set(f["projects"][0]) == {"name", "tagline", "event", "prizes", "wrote_pct", "kept", "demo", "main_type"}
    assert f["n"] == {"demo": 4, "own": 3, "mates": 8, "kept": 1, "docs": 2}


def test_facts_never_leak_identity():
    dump = json.dumps(facts_for_words(builder()), ensure_ascii=False).lower()
    for s in SECRETS:
        assert s.lower() not in dump, s


def test_facts_use_type_labels_and_project_fields():
    f = facts_for_words(builder())
    assert f["top_types"] == ["ML / AI", "Backend"]
    assert f["ev"] == {"ML / AI": 200, "Backend": 150, "Frontend": 40, "Design": 0, "Mobile": 0, "Hardware": 0}
    assert f["typeProjects"]["ML / AI"] == 3
    leaf, queue = f["projects"]
    assert leaf == {"name": "Leaf Lens", "tagline": "Spot crop disease from one photo with a PyTorch model.",
                    "event": "DeltaHacks 11", "prizes": ["Best Use of AI"], "wrote_pct": 64, "kept": True,
                    "demo": True, "main_type": "ML / AI"}
    assert queue["wrote_pct"] is None and queue["prizes"] == [] and queue["main_type"] == "Backend"


def test_missing_numbers_stay_none():
    b = builder(repos=None)
    del b["n"]
    b["projects"][0]["type"] = None
    f = facts_for_words(b)
    assert f["repos"] is None
    assert f["n"] == {"demo": None, "own": None, "mates": None, "kept": None, "docs": None}
    assert f["projects"][0]["main_type"] is None


def test_project_text_loses_links_and_taglines_naming_the_builder():
    b = builder()
    b["projects"][0]["desc"] = "Crop scans in seconds. Try https://leaflens.dev/app, mail team@leaflens.dev or ping @leaflens"
    b["projects"][1]["desc"] = "Quinn's weekend take on ER wait times."
    b["projects"][1]["flags"] = ["possible shared laptop or squashed commits"]
    leaf, queue = facts_for_words(b)["projects"]
    assert leaf["tagline"].startswith("Crop scans in seconds. Try")
    assert "http" not in leaf["tagline"] and "@" not in leaf["tagline"] and "leaflens.dev" not in leaf["tagline"]
    assert queue["tagline"] is None
    assert queue["caveats"] == ["possible shared laptop or squashed commits"]


def test_long_taglines_are_clipped():
    b = builder()
    b["projects"][0]["desc"] = "word " * 100
    assert len(facts_for_words(b)["projects"][0]["tagline"]) <= words.MAX_TAGLINE + 1


def test_sample_facts_never_leak_identity():
    for b in json.loads((DATA_DIR / "sample.json").read_text())["builders"]:
        f = facts_for_words(b)
        # Event names are hackathon facts and may name a school ("Hack Western 11"); check the rest.
        for p in f["projects"]:
            p["event"] = None
        dump = json.dumps(f, ensure_ascii=False)
        private = [b["id"], b["dex"], *b["name"].split(), *[v for v in b["links"].values() if v]]
        private += [b[k]["value"] for k in ("school", "schoolFull", "program", "grad", "city") if b[k]["value"]]
        for s in private:
            # Whole words: "UofTHacks 12" is an event name, not the school "UofT".
            assert not re.search(rf"(?<!\w){re.escape(str(s))}(?!\w)", dump), (b["id"], s)


# ---------------------------------------------------------------- checks

F = facts_for_words(builder())


def test_count_words():
    assert count_words("ML / AI builder across 4 projects.") == 6
    assert count_words("Turns messy real-world data into demos.") == 6
    assert count_words("") == 0


@pytest.mark.parametrize("line", [
    "Won Best Use of AI with Leaf Lens at DeltaHacks 11.",
    "Wrote 64% of Leaf Lens, a PyTorch crop-disease spotter.",
    "Backend and ML / AI work across 4 hackathon projects. Kept building twice.",  # twice: 2 is in the facts
    "No wins yet, but they wrote most of 3 projects.",
])
def test_good_lines_pass(line):
    assert problems(line, F, SUM_MAX) == []


@pytest.mark.parametrize("line, expected", [
    ("Shipped 9 ML projects.", "the number 9 is not in the facts"),
    ("Shipped nine ML projects.", "the number 9 is not in the facts"),
    ("Won Best Use of AI thrice.", "the number 3"),  # 3 is in the facts
    ("Built Leaf Lens, see leaflens.dev for the demo.", 'contains a link or "@"'),
    ("Built Leaf Lens with @zxq.", 'contains a link or "@"'),
    ("Wrote the inference API for Leaf Lens.", "names a technology the facts do not mention: api"),
    ("Built Leaf Lens in React and Flask.", "names a technology the facts do not mention: flask, react"),
    ("His backend work on Queue Less stands out.", "uses a gendered word: his"),
    ("252 ML / AI EVs from Leaf Lens.", "uses internal score words (EV, IV, dex)"),
    ("Won Best Use of AI. 3rd year student.", "mentions year of study or graduation"),
    ("Won Best Use of AI. Graduating soon.", "mentions year of study or graduation"),
    ("Won Best Use of AI. Based in Toronto.", "mentions a school, program or place that is not in the facts"),
    ("Waterloo builder who won Best Use of AI.", "mentions a school, program or place that is not in the facts"),
    ("Leaf Lens won Best Use of AI.", "has 7 words; the limit is 5"),
    ("Leaf Lens.", "has 2 words; write at least 3"),
])
def test_bad_lines_fail(line, expected):
    limit = 5 if "limit is 5" in expected else SUM_MAX
    found = problems(line, F, limit)
    if expected == "the number 3":
        assert found == []
    else:
        assert expected in found, found


def test_words_from_the_facts_are_allowed():
    b = builder()
    b["projects"][0]["desc"] = "Helps her grandmother's clinic in Toronto triage with the Gemini API, built by grad students."
    f = facts_for_words(b)
    assert problems("Built a Gemini API triage tool for a clinic in Toronto, with grad students.", f, SUM_MAX) == []


def test_private_terms_are_checked_but_never_quoted():
    b = builder()
    found = problems("Systems Design Engineering builder behind Leaf Lens.", F, SUM_MAX, private=words.private_terms(b))
    assert found == ["mentions a school, program or place that is not in the facts"]
    assert not any("Systems" in p for p in found)


def test_clean():
    assert clean('  "Won Best UI with Lumen"  ') == "Won Best UI with Lumen."
    assert clean("Ships demos.\n") == "Ships demos."
    assert clean(None) == ""


# ---------------------------------------------------------------- template

def test_template_prefers_a_prize_then_a_share():
    t = template_words(builder())
    assert t == {"why": "Won Best Use of AI at DeltaHacks 11.",
                 "sum": "ML / AI and Backend builder across 4 hackathon projects.", "source": "template"}
    b = builder(wins=0)
    for p in b["projects"]:
        p["prizes"], p["prize"] = [], ""
    assert template_words(b)["why"] == "Wrote 64% of Leaf Lens at DeltaHacks 11."


def test_template_falls_back_to_shorter_lines():
    b = builder()
    b["projects"][0]["prizes"] = ["[MLH] Best Use of Something With A Very Long Sponsor Name For Students In Canada"]
    b["projects"][0]["share"] = 12  # too little to lead with
    t = template_words(b)
    assert t["why"] == "ML / AI code on 3 of 4 hackathon projects."
    b["projects"][0]["prizes"] = ["[MLH] Best Use of Gemini API"]
    assert template_words(b)["why"] == "Won MLH Best Use of Gemini API at DeltaHacks 11."


def test_template_with_no_code_or_projects():
    b = builder(types=[], codeProjects=0, projects=[], hacks=1, wins=0)
    t = template_words(b)
    assert t["why"] == "1 hackathon on Devpost."
    assert t["sum"] == "Hackathon builder with 1 hackathon on Devpost."
    for line, limit in ((t["why"], WHY_MAX), (t["sum"], SUM_MAX)):
        assert problems(line, facts_for_words(b), limit) == []


def test_sample_templates_pass_their_own_checks():
    for b in json.loads((DATA_DIR / "sample.json").read_text())["builders"]:
        t, f = template_words(b), facts_for_words(b)
        assert problems(t["why"], f, WHY_MAX) == [] and problems(t["sum"], f, SUM_MAX) == [], b["id"]


# ---------------------------------------------------------------- Gemini flow (faked)

class FakeGemini:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, prompt, schema, *, namespace, system=None, **kw):
        self.calls.append({"prompt": prompt, "schema": schema, "namespace": namespace, "system": system})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


GOOD = {"why": "Won Best Use of AI with Leaf Lens.", "sum": "Builds ML / AI projects like Leaf Lens with a solid backend behind them."}


def test_valid_first_answer_is_used(monkeypatch):
    fake = FakeGemini(GOOD)
    monkeypatch.setattr(gemini, "generate_json", fake)
    assert words_for(builder()) == {**GOOD, "source": "gemini"}
    (call,) = fake.calls
    assert call["namespace"] == "words"
    assert call["schema"]["required"] == ["why", "sum"]
    sent = (call["prompt"] + call["system"]).lower()
    for s in SECRETS:
        assert s.lower() not in sent, s


def test_bad_line_gets_one_stricter_retry(monkeypatch):
    bad = {"why": "Wrote the inference API for Leaf Lens. Based in Peterborough.", "sum": GOOD["sum"]}
    fake = FakeGemini(bad, {"why": GOOD["why"], "sum": "Something else entirely, never used."})
    monkeypatch.setattr(gemini, "generate_json", fake)
    out = words_for(builder())
    assert out == {**GOOD, "source": "gemini"}  # the retry fixes why; sum is kept from the first answer
    first, second = fake.calls
    assert first["prompt"] != second["prompt"] and first["system"] != second["system"]
    assert "why: names a technology the facts do not mention: api" in second["prompt"]
    assert "why: mentions a school, program or place that is not in the facts" in second["prompt"]
    assert "Peterborough" not in second["prompt"] + second["system"]


def test_two_bad_answers_fall_back_to_the_template(monkeypatch):
    bad = {"why": "Won Best Use of AI with Leaf Lens.", "sum": "He shipped 9 apps."}
    fake = FakeGemini(bad, bad)
    monkeypatch.setattr(gemini, "generate_json", fake)
    out = words_for(builder())
    assert len(fake.calls) == 2
    assert out == {"why": "Won Best Use of AI with Leaf Lens.",
                   "sum": "ML / AI and Backend builder across 4 hackathon projects.", "source": "template"}


def test_gemini_errors_fall_back_to_the_template(monkeypatch):
    fake = FakeGemini(gemini.GeminiError("Gemini error 400: bad request"))
    monkeypatch.setattr(gemini, "generate_json", fake)
    assert words_for(builder()) == template_words(builder())


def test_malformed_answers_are_rejected(monkeypatch):
    fake = FakeGemini(["not", "an", "object"], {"why": None, "sum": 7})
    monkeypatch.setattr(gemini, "generate_json", fake)
    assert words_for(builder())["source"] == "template"


def test_write_words_keys_by_builder_id(monkeypatch):
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: GOOD)
    a, b = builder(), builder(id="other-builder")
    out = write_words([a, b], workers=2)
    assert list(out) == ["zxquinn", "other-builder"]
    assert all(v == {**GOOD, "source": "gemini"} for v in out.values())


# ---------------------------------------------------------------- design samples (cached, offline)

def test_sample_lines_are_valid(monkeypatch):
    """Cached Gemini lines for the design samples pass every check; no live call is made."""
    def offline():
        raise gemini.GeminiError("offline test: no live Gemini calls")

    monkeypatch.setattr(gemini, "_get_client", offline)
    builders = json.loads((DATA_DIR / "sample.json").read_text())["builders"]
    calls = gemini.stats["calls"]
    out = write_words(builders)
    assert gemini.stats["calls"] == calls
    assert set(out) == {b["id"] for b in builders}
    for b in builders:
        w, f = out[b["id"]], facts_for_words(b)
        assert w["source"] in {"gemini", "template"}
        assert problems(w["why"], f, WHY_MAX, private=words.private_terms(b)) == [], (b["id"], w["why"])
        assert problems(w["sum"], f, SUM_MAX, private=words.private_terms(b)) == [], (b["id"], w["sum"])
