"""Field-notes enrichment tests.

Everything here runs offline. People Data Labs is never called: a fake
transport stands in for the network and the cache lives in a temp folder.
The PlantHopper test reads Devpost and GitHub once and is served from
pipeline/cache/ afterwards.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from talentdex import enrich, github
from talentdex.enrich import (
    city_from_location, github_facts, grad_label, normalize_linkedin, parse_tagline, pdl_education,
    person_facts, school_from_name, year_from_grad,
)
from talentdex.httpcache import Resp

TODAY = date(2026, 10, 17)


# ------------------------------------------------------------------ taglines

@pytest.mark.parametrize("text, school, program, year, grad", [
    ("cs @ waterloo", "Waterloo", "Computer Science", None, None),
    ("se @ uwaterloo", "Waterloo", "Software Engineering", None, None),
    ("mechatronics @ waterloo", "Waterloo", "Mechatronics Engineering", None, None),
    ("3rd year CS at UofT", "UofT", "Computer Science", 3, None),
    ("Computer Engineering @ McMaster '27", "McMaster", "Computer Engineering", None, 2027),
    ("UofT CS 2027", "UofT", "Computer Science", None, 2027),
    ("Software Eng @ UW", "Waterloo", "Software Engineering", None, None),
    ("BBA/CS @ Laurier", "Laurier", "Business and Computer Science", None, None),
    ("second-year SYDE @ Waterloo", "Waterloo", "Systems Design Engineering", 2, None),
    ("Year 2 Comp Sci at Western", "Western", "Computer Science", 2, None),
    ("3A SE @ UW", "Waterloo", "Software Engineering", 3, None),
    ("U3 CS @ McGill", "McGill", "Computer Science", 3, None),
    ("BMath CS @ Waterloo, 2B", "Waterloo", "Computer Science", 2, None),
    ("UW SE '29", "Waterloo", "Software Engineering", None, 2029),
    ("UofT CS 2023 – 2027", "UofT", "Computer Science", None, 2027),
    ("cs + stats @ uoft", "UofT", "Computer Science and Statistics", None, None),
    ("Math and CS @ Waterloo", "Waterloo", "Mathematics and Computer Science", None, None),
    ("UofT Engineering, ECE", "UofT", "Electrical and Computer Engineering", None, None),
    ("Comp Eng @ Queen's", "Queen's", "Computer Engineering", None, None),
    ("ECE @ UofT", "UofT", "Electrical and Computer Engineering", None, None),
    ("Final year Mechatronics student", None, "Mechatronics Engineering", 4, None),
    ("cs @ uoft · 2nd year", "UofT", "Computer Science", 2, None),
    ("U of T | Class of '27 | Computer Science | Machine Learning", "UofT", "Computer Science", None, 2027),
    ("Sophomore CS student @ UWaterloo. Passionate about databases", "Waterloo", "Computer Science", 2, None),
    ("Hi, I'm a Third year CS student at UofT, interested in ML and entrepreneurship.", "UofT", "Computer Science", 3, None),
    ("Software engineering intern @ Shopify | CS @ UofT", "UofT", "Computer Science", None, None),
    ("CS major, math minor @ UofT", "UofT", "Computer Science", None, None),
    ("cs @ uoft! i like to design and make mobile apps :)", "UofT", "Computer Science", None, None),
    ("Graduating May 2027 from Queen's", "Queen's", None, None, 2027),
    ("new grad", None, None, 0, None),
    ("UofT alum", "UofT", None, 0, None),
    ("Recent graduate from TMU", "TMU", None, 0, None),
    ("class of 2027", None, None, None, 2027),
])
def test_parse_tagline(text, school, program, year, grad):
    r = parse_tagline(text)
    assert (r["school"] or {}).get("short") == school
    assert r["program"] == program
    assert r["year"] == year
    assert r["grad_year"] == grad
    assert r["hs"] is False


def test_parse_tagline_school_record():
    assert parse_tagline("cs @ waterloo")["school"] == {"short": "Waterloo", "full": "University of Waterloo", "city": "Waterloo"}
    assert parse_tagline("Grad: Apr 2028 | SE @ UW")["grad_month"] == 4


@pytest.mark.parametrize("text", [
    "Waterloo",                                  # the city or the school? unsure
    "uw",
    "I love CS",                                 # an interest, not a program
    "SE @ Shopify",                              # a job
    "Software Engineer at Google",
    "NYC based dev from New York",
    "CS @ UW-Madison",
    "York Region robotics",
    "Queens, NY",
    "western blot enthusiast",
    "Brock Lesnar fan",
    "e-commerce founder",
    "My 3rd year at Hack the North!",            # a hackathon count, not a year of study
    "love to code & do math :)",
    "University of Toronto Schools '26",         # a high school
])
def test_parse_tagline_is_conservative(text):
    r = parse_tagline(text)
    assert (r["school"], r["program"], r["year"], r["grad_year"]) == (None, None, None, None), r


def test_parse_tagline_does_not_take_hackathon_or_since_years():
    assert parse_tagline("Hack the North 2025 winner | CS @ UofT")["grad_year"] is None
    assert parse_tagline("CS @ UofT, 2025 hackathon winner")["grad_year"] is None
    assert parse_tagline("coding since '18, cs @ waterloo")["grad_year"] is None
    assert parse_tagline("UW SE '29 from Toronto")["grad_year"] == 2029


@pytest.mark.parametrize("text", [
    "Grade 12 student",
    "High school student @ Earl Haig",
    "I'm Ananth, a high school student in Waterloo, Ontario",
    "Student at Marc Garneau Collegiate",
    "currently in high school",
])
def test_parse_tagline_high_school(text):
    r = parse_tagline(text)
    assert r["hs"] is True
    assert (r["school"], r["year"], r["grad_year"]) == (None, None, None)


def test_parse_tagline_high_school_in_the_past_is_not_high_school():
    r = parse_tagline("Started coding in high school, now CS @ UofT")
    assert r["hs"] is False and r["school"]["short"] == "UofT"
    assert parse_tagline("post-secondary student at Humber College")["school"]["short"] == "Humber"


def test_parse_tagline_postgrad_has_no_year():
    r = parse_tagline("2nd year PhD in CS at UofT")
    assert r["postgrad"] is True and r["year"] is None and r["school"]["short"] == "UofT"
    assert parse_tagline("MEng @ UofT")["postgrad"] is True


def test_parse_tagline_empty():
    assert parse_tagline("") == {"school": None, "program": None, "year": None, "grad_year": None,
                                 "grad_month": None, "hs": False, "postgrad": False}


# ------------------------------------------------------------------ years

@pytest.mark.parametrize("grad_year, month, today, want", [
    (2027, None, TODAY, 4),           # final year
    (2027, 4, TODAY, 4),
    (2028, 4, TODAY, 3),              # the sample's "April 2028" -> Year 3
    (2029, None, TODAY, 2),
    (2030, None, TODAY, 1),
    (2031, None, TODAY, 1),           # clamped
    (2026, 6, TODAY, 0),              # graduated in June
    (2026, None, TODAY, 0),
    (2026, 12, TODAY, 4),             # finishing in December: still in the final year
    (2020, None, TODAY, 0),
    (2027, None, date(2026, 7, 1), 3),  # summer: the academic year that just ended is the current one
    (2026, None, date(2026, 3, 1), 4),
    (2026, 4, date(2026, 5, 10), 0),
    (2026, None, date(2026, 5, 10), 4),  # no month: taken as May
])
def test_year_from_grad(grad_year, month, today, want):
    assert year_from_grad(grad_year, month, today) == want


def test_grad_label():
    assert grad_label(2028, 4) == "April 2028"
    assert grad_label(2028, None) == "2028"


# ------------------------------------------------------------------ places

@pytest.mark.parametrize("location, city", [
    ("Toronto, Ontario, Canada", "Toronto"),
    ("Waterloo, Ontario, Canada", "Waterloo"),
    ("North York, Ontario, Canada", "Toronto"),
    ("Ontario, Canada", None),
    ("Canada", None),
    ("", None),
    (None, None),
    ("Coquitlam, British Columbia, Canada", "Coquitlam, BC"),
    ("Thornhill, ON", "Thornhill"),                        # in places.json since the real run
    ("Bracebridge, ON", "Bracebridge, ON"),                # not in places.json: keeps its province
    ("Toronto, ON, CA", "Toronto"),                        # Devpost's country code
    ("Oakville, ON, CA", "Oakville"),
    ("Saanich, BC, CA", "Saanich, BC"),
    ("London, England, United Kingdom", "London, England"),   # not London, Ontario
    ("Waterloo, Iowa, United States", "Waterloo, Iowa"),
    ("Toronto, ON", "Toronto"),
    ("Toronto, Canada", "Toronto"),
    ("Remote", None),
    ("London", None),                        # London, Ontario or London, England? places.json leaves it out on purpose
    ("London, Ontario, Canada", "London"),
    ("Cambridge, Massachusetts, United States", "Cambridge, Massachusetts"),
])
def test_city_from_location(location, city):
    assert city_from_location(location) == city


@pytest.mark.parametrize("name, short", [
    ("university of waterloo", "Waterloo"),
    ("the university of western ontario", "Western"),
    ("university of toronto mississauga", "UTM"),
    ("york university - lassonde school of engineering", "York"),
    ("queen's university at kingston", "Queen's"),
    ("new york university", None),
    ("stanford university", None),
])
def test_school_from_name(name, short):
    s = school_from_name(name)
    assert (s or {}).get("short") == short


# ------------------------------------------------------------------ PDL records -> facts

def pdl_person(slug: str = "jane-doe-123", **over) -> dict:
    """A made-up PDL person record in the shape the API returns (lowercase values)."""
    person = {
        "id": "made-up",
        "linkedin_url": f"linkedin.com/in/{slug}",
        "linkedin_username": slug,
        "location_locality": "waterloo",
        "location_region": "ontario",
        "location_country": "canada",
        "profiles": [{"network": "linkedin", "url": f"linkedin.com/in/{slug}", "username": slug}],
        "education": [
            {"school": {"name": "some secondary school", "type": "secondary school"},
             "start_date": "2018", "end_date": "2022", "majors": [], "degrees": []},
            {"school": {"name": "university of waterloo", "type": "post-secondary institution"},
             "start_date": "2022-09", "end_date": "2027-04", "majors": ["software engineering"], "degrees": ["bachelors"]},
            {"school": {"name": "eth zurich", "type": "post-secondary institution"},
             "start_date": "2025-01", "end_date": "2025-04", "majors": ["computer science"], "degrees": []},
        ],
    }
    person.update(over)
    return person


def values(facts: dict) -> dict:
    return {k: f["value"] for k, f in facts.items()}


def test_person_facts_pdl_first():
    prof = {"bio": "cs @ uoft '28", "location": "Toronto, Ontario, Canada"}
    f = person_facts(prof, pdl_person(), today=TODAY)
    assert set(f) == {"school", "schoolFull", "program", "grad", "year", "city"}
    assert values(f) == {"school": "Waterloo", "schoolFull": "University of Waterloo", "program": "Software Engineering",
                         "grad": "April 2027", "year": 4, "city": "Waterloo"}
    assert all(x["source"] == "People Data Labs" for x in f.values())
    assert all(x["looked"] == ["People Data Labs", "Devpost"] for x in f.values())


def test_person_facts_unwraps_a_full_pdl_response():
    f = person_facts({}, {"status": 200, "likelihood": 10, "data": pdl_person()}, today=TODAY)
    assert f["school"]["value"] == "Waterloo"


def test_person_facts_pdl_without_end_date_falls_back_to_tagline():
    person = pdl_person(location_locality=None, education=[
        {"school": {"name": "university of toronto", "type": "post-secondary institution"},
         "start_date": "2024", "end_date": None, "majors": [], "degrees": []}])
    f = person_facts({"bio": "2nd year CS @ UofT", "location": "Ontario, Canada"}, person, today=TODAY)
    assert (f["school"]["value"], f["school"]["source"]) == ("UofT", "People Data Labs")
    assert (f["program"]["value"], f["program"]["source"]) == ("Computer Science", "Devpost")
    assert (f["year"]["value"], f["year"]["source"]) == (2, "Devpost")
    assert (f["grad"]["value"], f["grad"]["looked"]) == (None, ["People Data Labs", "Devpost"])
    assert (f["city"]["value"], f["city"]["source"]) == ("Toronto", "People Data Labs")  # the school's city


def test_person_facts_does_not_mix_two_schools():
    person = pdl_person(education=[
        {"school": {"name": "university of toronto", "type": "post-secondary institution"}, "start_date": "2024"}])
    f = person_facts({"bio": "SE @ Waterloo '27"}, person, today=TODAY)
    assert f["school"]["value"] == "UofT"
    assert (f["program"]["value"], f["grad"]["value"], f["year"]["value"]) == (None, None, None)


def test_person_facts_postgrad_and_short_entries():
    person = pdl_person(education=[
        {"school": {"name": "university of toronto", "type": "post-secondary institution"},
         "start_date": "2025-09", "end_date": "2027-04", "majors": ["computer science"], "degrees": ["masters"]},
        {"school": {"name": "university of waterloo", "type": "post-secondary institution"},
         "start_date": "2026-05", "end_date": "2026-08", "majors": [], "degrees": []},  # a summer program
    ])
    f = person_facts({}, person, today=TODAY)
    assert (f["school"]["value"], f["grad"]["value"], f["year"]["value"]) == ("UofT", "April 2027", None)


def test_person_facts_high_school_tagline_beats_pdl_education():
    person = pdl_person(education=[
        {"school": {"name": "university of waterloo", "type": "post-secondary institution"},
         "start_date": "2024-07", "end_date": "2025-06", "majors": [], "degrees": []}])
    f = person_facts({"bio": "Grade 12 student"}, person, today=TODAY)
    assert (f["school"]["value"], f["year"]["value"]) == (None, None)
    assert f["city"]["value"] == "Waterloo"  # where they live still comes from PDL


def test_person_facts_pdl_checked_with_nothing():
    f = person_facts({"bio": "cs @ waterloo", "location": "Toronto, Ontario, Canada"}, {}, today=TODAY)
    assert (f["school"]["value"], f["school"]["source"]) == ("Waterloo", "Devpost")
    assert (f["city"]["value"], f["city"]["source"]) == ("Toronto", "Devpost")
    assert f["year"] == {"value": None, "source": None, "looked": ["People Data Labs", "Devpost"]}


def test_person_facts_devpost_only():
    f = person_facts({"bio": "", "location": "Ontario, Canada"}, None, member_note="", today=TODAY)
    assert all(x == {"value": None, "source": None, "looked": ["Devpost"]} for x in f.values())


def test_person_facts_member_note_and_school_city():
    f = person_facts({"bio": "", "location": "Ontario, Canada"}, None, member_note="Computer Engineering @ McMaster '27", today=TODAY)
    assert values(f) == {"school": "McMaster", "schoolFull": "McMaster University", "program": "Computer Engineering",
                         "grad": "2027", "year": 4, "city": "Hamilton"}
    assert f["city"]["source"] == "Devpost"
    # The bio wins as a whole; the note is not mixed in.
    g = person_facts({"bio": "cs @ uoft"}, None, member_note="SE @ Waterloo '27", today=TODAY)
    assert (g["school"]["value"], g["grad"]["value"]) == ("UofT", None)


def test_person_facts_never_claims_a_resume():
    for pdl in (None, {}, pdl_person()):
        f = person_facts({"bio": "cs @ waterloo"}, pdl, today=TODAY)
        assert all("résumé" not in x["looked"] and x["source"] != "résumé" for x in f.values())


def test_pdl_education_skips_high_schools_typed_as_post_secondary():
    # Seen in real PDL answers: high schools with type "post-secondary institution".
    person = {"education": [
        {"school": {"name": "university of toronto schools", "type": "post-secondary institution"}, "start_date": "2019", "end_date": "2025-06"},
        {"school": {"name": "port moody secondary school", "type": "post-secondary institution"}, "start_date": "2021", "end_date": "2025"},
    ]}
    assert pdl_education(person) is None
    assert school_from_name("university of toronto schools") is None


def test_pdl_education_picks_latest_post_secondary():
    e = pdl_education(pdl_person())
    assert e["school"]["short"] == "Waterloo" and e["end"] == (2027, 4) and e["postgrad"] is False
    unknown = pdl_education({"education": [{"school": {"name": "stanford university", "type": "post-secondary institution",
                                                       "location": {"locality": "stanford", "region": "california", "country": "united states"}},
                                            "start_date": "2023", "end_date": "2027", "majors": ["symbolic systems"]}]})
    assert unknown["school"] == {"short": "Stanford University", "full": "Stanford University", "city": "Stanford, California"}
    assert unknown["program"] == "Symbolic Systems"


# ------------------------------------------------------------------ PDL client (fake transport)

class FakeHttp:
    """Stands in for the network: returns queued responses and records each call."""

    def __init__(self) -> None:
        self.queue: list = []
        self.calls: list[tuple[str, dict]] = []
        self.http_cache: dict[str, Resp] = {}

    def cached(self, url, accept=None):
        return self.http_cache.get(url)

    def get(self, url, *, accept=None, extra_headers=None, **_kw):
        self.calls.append((url, dict(extra_headers or {})))
        r = self.queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


KEY = "fake-key-do-not-store-1234"


@pytest.fixture
def fake(tmp_path, monkeypatch):
    f = FakeHttp()
    monkeypatch.setattr(enrich, "_http", f)
    monkeypatch.setattr(enrich, "PDL_DIR", tmp_path / "pdl")
    monkeypatch.setattr(enrich, "PDL_MAX_CALLS", 3)
    monkeypatch.setattr(enrich, "_stopped", None)
    monkeypatch.setattr(enrich, "stats", {k: 0 for k in enrich.stats})
    monkeypatch.setattr(enrich.config, "PDL_API_KEY", KEY)
    return f


def resp(status: int, body: dict | None = None, url: str = "x") -> Resp:
    return Resp(url, status, json.dumps(body if body is not None else {"status": status}), {"x-call-credits-spent": "1"})


def test_normalize_linkedin():
    assert normalize_linkedin("https://ca.linkedin.com/in/Eu-Lee?trk=abc") == "https://www.linkedin.com/in/eu-lee/"
    assert normalize_linkedin("linkedin.com/in/jason-liu-646b30273") == "https://www.linkedin.com/in/jason-liu-646b30273/"
    assert normalize_linkedin("https://www.linkedin.com/in/eu-lee/en/") == "https://www.linkedin.com/in/eu-lee/"
    assert normalize_linkedin("https://www.linkedin.com/company/acme") is None
    assert normalize_linkedin("https://github.com/eu-lee") is None
    assert normalize_linkedin(None) is None


def test_pdl_match_is_cached_and_never_asked_twice(fake, tmp_path, capsys):
    fake.queue = [resp(200, {"status": 200, "likelihood": 10, "data": pdl_person("jane-doe-123")})]
    person = enrich.pdl_enrich("https://www.linkedin.com/in/jane-doe-123/")
    assert person["location_locality"] == "waterloo"
    url, headers = fake.calls[0]
    assert headers == {"X-Api-Key": KEY} and KEY not in url and "profile=linkedin.com%2Fin%2Fjane-doe-123" in url
    # Same person, another spelling of the URL: served from the cache, no second call.
    assert enrich.pdl_enrich("https://ca.linkedin.com/in/Jane-Doe-123?trk=x") == person
    assert len(fake.calls) == 1 and enrich.calls_used() == 1 and enrich.budget_left() == 2
    rec = enrich.pdl_record("linkedin.com/in/jane-doe-123")
    assert rec["status"] == 200 and rec["headers"] == {"x-call-credits-spent": "1"}
    # The key is never written or printed.
    for p in (tmp_path / "pdl").iterdir():
        assert KEY not in p.read_text()
    assert KEY not in capsys.readouterr().out


def test_pdl_404_is_an_answer(fake):
    fake.queue = [resp(404, {"status": 404, "error": {"type": "not_found"}})]
    assert enrich.pdl_enrich("linkedin.com/in/nobody") == {}
    assert enrich.pdl_enrich("linkedin.com/in/nobody") == {}
    assert len(fake.calls) == 1


def test_pdl_record_for_another_linkedin_is_not_used(fake):
    fake.queue = [resp(200, {"status": 200, "data": pdl_person("someone-else")})]
    assert enrich.pdl_enrich("linkedin.com/in/jane-doe-123") == {}
    assert enrich.stats["rejected"] == 1


def test_pdl_budget_counts_calls_from_earlier_runs(fake, monkeypatch):
    monkeypatch.setattr(enrich, "PDL_MAX_CALLS", 2)
    (enrich.PDL_DIR).mkdir(parents=True)
    (enrich.PDL_DIR / "calls.jsonl").write_text('{"url": "a"}\n{"url": "b"}\n')
    assert enrich.pdl_enrich("linkedin.com/in/jane-doe-123") is None
    assert fake.calls == [] and enrich.stats["no_budget"] == 1


def test_pdl_without_key_does_not_call(fake, monkeypatch):
    monkeypatch.setattr(enrich.config, "PDL_API_KEY", None)
    assert enrich.pdl_enrich("linkedin.com/in/jane-doe-123") is None
    assert fake.calls == []


def test_pdl_error_stops_further_calls_but_counts(fake, capsys):
    fake.queue = [RuntimeError("GET failed after 1 attempts")]
    assert enrich.pdl_enrich("linkedin.com/in/jane-doe-123") is None
    assert enrich.pdl_enrich("linkedin.com/in/another-one") is None
    assert len(fake.calls) == 1 and enrich.calls_used() == 1
    assert enrich.pdl_record("linkedin.com/in/jane-doe-123") is None  # not an answer: may be asked in a later run
    assert "no more PDL calls" in capsys.readouterr().out


def test_pdl_account_errors_are_not_cached_as_answers(fake):
    fake.queue = [resp(402, {"status": 402, "error": {"type": "payment_required"}})]
    assert enrich.pdl_enrich("linkedin.com/in/jane-doe-123") is None
    assert enrich.pdl_record("linkedin.com/in/jane-doe-123") is None
    assert enrich.pdl_enrich("linkedin.com/in/another-one") is None
    assert len(fake.calls) == 1


def test_pdl_adopts_an_answer_the_http_cache_already_has(fake):
    norm = normalize_linkedin("linkedin.com/in/jane-doe-123")
    fake.http_cache[enrich._request_url(norm)] = resp(200, {"status": 200, "data": pdl_person("jane-doe-123")})
    assert enrich.pdl_enrich(norm)["linkedin_username"] == "jane-doe-123"
    assert fake.calls == [] and enrich.pdl_record(norm)["status"] == 200


def test_pdl_ignores_non_profile_urls(fake):
    assert enrich.pdl_enrich("https://www.linkedin.com/company/acme") is None
    assert enrich.pdl_enrich("") is None
    assert fake.calls == []


# ------------------------------------------------------------------ GitHub

def test_github_facts(monkeypatch):
    monkeypatch.setattr(github, "user", lambda login: {"login": login, "public_repos": 41})
    monkeypatch.setattr(github, "latest_push", lambda login: "2026-10-15T16:00:00Z")
    assert github_facts("someone") == {"repos": 41, "lastActive": {"value": "2026-10-15T16:00:00Z", "source": "GitHub", "looked": ["GitHub"]}}
    monkeypatch.setattr(github, "user", lambda login: None)
    assert github_facts("gone") == {"repos": None, "lastActive": {"value": None, "source": None, "looked": ["GitHub"]}}
    assert github_facts(None) == {"repos": None, "lastActive": {"value": None, "source": None, "looked": ["GitHub"]}}


# ------------------------------------------------------------------ PlantHopper (cached Devpost + GitHub)

def test_planthopper_team_field_notes():
    from talentdex import devpost

    project = devpost.fetch_project("plant-hopper")
    notes = {m["username"]: m["note"] for m in project["members"]}
    want = {
        "eu-lee": ("Waterloo", "Software Engineering", "Coquitlam, BC"),
        "austinjian07": ("Waterloo", "Computer Science", "Toronto"),
        "pekachoo": (None, None, None),  # empty bio; location is just "Ontario, Canada"
        "seanchansato": ("Waterloo", "Mechatronics Engineering", "Waterloo"),
    }
    for username, (school, program, city) in want.items():
        prof = devpost.fetch_profile(username)
        f = person_facts(prof, None, member_note=notes[username], today=TODAY)
        assert (f["school"]["value"], f["program"]["value"], f["city"]["value"]) == (school, program, city), username
        assert f["year"]["value"] is None and f["year"]["looked"] == ["Devpost"]
        gh = github_facts(prof["github"])
        assert isinstance(gh["repos"], int) and gh["repos"] > 0
        assert gh["lastActive"]["source"] == "GitHub" and gh["lastActive"]["value"].startswith("20")


def test_planthopper_pdl_answers_from_cache(monkeypatch):
    """The two PDL answers cached during development. With no key, a missing answer can never become a live call."""
    from talentdex import devpost

    monkeypatch.setattr(enrich.config, "PDL_API_KEY", None)
    want = {"pekachoo": ("Waterloo", "Computer Science", "Waterloo", "People Data Labs"),
            "eu-lee": ("Waterloo", "Software Engineering", "Coquitlam, BC", "Devpost")}
    for username, (school, program, city, city_source) in want.items():
        prof = devpost.fetch_profile(username)
        person = enrich.pdl_enrich(prof["linkedin"])
        if person is None:
            pytest.skip("PDL answer not cached here (tests never call PDL)")
        f = person_facts(prof, person, today=TODAY)
        assert (f["school"]["value"], f["school"]["source"]) == (school, "People Data Labs")
        assert (f["program"]["value"], f["city"]["value"], f["city"]["source"]) == (program, city, city_source)
        # PDL leaves end_date empty while someone is enrolled, so it gives no year here.
        assert f["year"] == {"value": None, "source": None, "looked": ["People Data Labs", "Devpost"]}
