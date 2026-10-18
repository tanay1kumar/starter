"""crawl.py tests.

Most tests are pure functions on inline fixtures and run offline. The Hack the
Valley X tests read Devpost once and are served from pipeline/cache/ afterwards.
"""

from __future__ import annotations

import json

import pytest
import requests

from talentdex import crawl, devpost


@pytest.fixture
def steps(tmp_path, monkeypatch):
    """Point the step files and the live-check cache at a temp dir."""
    monkeypatch.setattr(crawl, "WINDOWS_JSON", tmp_path / "steps" / "windows.json")
    monkeypatch.setattr(crawl, "TARGETS_JSON", tmp_path / "steps" / "targets.json")
    monkeypatch.setattr(crawl, "LIVE_DIR", tmp_path / "live")
    monkeypatch.setattr(crawl, "_wmemo", None)
    return tmp_path


# ------------------------------------------------------------------- gallery

GALLERY_HTML = """
<div id="submission-gallery">
  <form><p>Filter submissions</p></form>
  <div class="row"><p>1 &ndash; 3 of 3</p></div>
  <div class="large-4 small-12 columns gallery-item" data-software-id="1076416">
    <a class="block-wrapper-link fade link-to-software" href="https://devpost.com/software/plant-hopper">
      <figure><figcaption><div class="software-entry-name entry-body"><h5>Plant Hopper</h5>
        <p class="small tagline">We water plants with 0% waste.</p></div></figcaption></figure>
      <aside class="entry-badge"><img alt="Winner" class="winner" src="ribbon.png"> Winner</aside>
    </a>
  </div>
  <div class="gallery-item" data-software-id="2"><a class="link-to-software" href="/software/tutoroo"><h5>Tutoroo</h5></a></div>
  <div class="gallery-item" data-software-id="3"><a class="link-to-software" href="https://devpost.com/software/tutoroo/"><h5>Again</h5></a></div>
  <div class="gallery-item"><a href="https://devpost.com/software/built-with/react">React</a></div>
</div>
"""


def test_parse_gallery_items_winners_and_total():
    g = devpost.parse_gallery(GALLERY_HTML)
    assert [i["slug"] for i in g["items"]] == ["plant-hopper", "tutoroo"]
    assert [i["winner"] for i in g["items"]] == [True, False]
    assert g["items"][1]["url"] == "https://devpost.com/software/tutoroo"
    assert g["items"][0]["name"] == "Plant Hopper"
    assert g["total"] == 3 and g["message"] == ""


def test_parse_gallery_empty_pages_say_why():
    unpublished = '<div id="submission-gallery"><p>The hackathon managers haven\'t published this gallery yet, but hang tight!</p></div>'
    past_end = '<div id="submission-gallery"><form><p>Sort</p></form><p>There are no submissions which match your criteria.</p></div>'
    assert devpost.parse_gallery(unpublished)["message"].startswith("The hackathon managers haven't published")
    assert devpost.parse_gallery(past_end) == {"items": [], "total": None,
                                               "message": "There are no submissions which match your criteria."}


def item(slug, winner=False):
    return {"slug": slug, "url": f"https://devpost.com/software/{slug}", "winner": winner, "name": slug}


def test_gallery_items_pages_until_empty_or_repeated(monkeypatch):
    pages = {1: [item("a", True), item("b")], 2: [item("c")], 3: [], 4: [item("d")]}
    monkeypatch.setattr(crawl, "gallery_page", lambda h, n: {"items": pages.get(n, []), "total": None, "message": ""})
    assert [i["slug"] for i in crawl.gallery_items({"url": "x"})] == ["a", "b", "c"]
    # Devpost repeating the last page is also the end.
    pages = {1: [item("a")], 2: [item("a")], 3: [item("z")]}
    assert [i["slug"] for i in crawl.gallery_items({"url": "x"})] == ["a"]


def test_select_targets_winners_first_needs_repo_and_stops_at_quota(monkeypatch):
    gallery = [item("n1"), item("w1", True), item("n2"), item("w2", True), item("n3"), item("n4")]
    pages = {"w1": ["o/w1"], "w2": [], "n1": ["o/n1"], "n2": None, "n3": ["o/n3"], "n4": ["o/n4"]}
    fetched = []

    def fake_fetch(url):
        slug = url.rsplit("/", 1)[-1]
        fetched.append(slug)
        return None if pages[slug] is None else {"slug": slug, "repos": pages[slug]}

    monkeypatch.setattr(crawl, "gallery_items", lambda h: gallery)
    monkeypatch.setattr(devpost, "fetch_project", fake_fetch)
    st = {}
    assert crawl.select_targets({"url": "x"}, 3, stats=st) == ["w1", "n1", "n3"]
    assert fetched == ["w1", "w2", "n1", "n2", "n3"]  # n4 never fetched: quota met
    assert st == {"gallery_items": 6, "winners": 2, "pages_fetched": 5, "kept": 3, "kept_winners": 1,
                  "no_repo": 1, "missing": 1, "duplicates": 0}
    st = {}
    assert crawl.select_targets({"url": "x"}, 3, skip={"w1"}, stats=st) == ["n1", "n3", "n4"]
    assert st["duplicates"] == 1


# ---------------------------------------------------------------- hackathons

def test_query_variants():
    assert crawl.query_variants("UofTHacks 12") == ["UofTHacks 12", "UofTHacks", "UofTHacks XII", "UofTHacks12"]
    assert crawl.query_variants("Hack the Valley X") == ["Hack the Valley X", "Hack the Valley", "Hack the Valley 10"]
    assert crawl.query_variants("Hack the 6ix 2025") == ["Hack the 6ix 2025", "Hack the 6ix"]


def test_find_target_tries_variants_and_matches_titles_exactly(monkeypatch):
    listed = {"UofTHacks XII": [{"title": "UofTHacks XIII"}, {"title": "UofTHacks XII", "url": "https://u12.devpost.com/"}]}
    monkeypatch.setattr(devpost, "find_hackathon", lambda name: None)
    monkeypatch.setattr(devpost, "search_hackathons", lambda q: listed.get(q, [{"title": "UofTHacks 13"}]))
    h, tried = crawl.find_target("UofTHacks 12")
    assert h["url"] == "https://u12.devpost.com/" and "UofTHacks XII" in tried
    h, tried = crawl.find_target("UofTHacks 14")
    assert h is None and tried == ["UofTHacks 14", "UofTHacks", "UofTHacks XIV", "UofTHacks14"]


def test_quota():
    assert crawl.quota_for(214, 6) == 36
    assert crawl.quota_for(214, 5) == 43
    assert crawl.quota_for(214, 0) == 0


# --------------------------------------------------------------------- demos

def test_live_candidates_excludes_non_demo_links():
    project = {"links": [
        "https://github.com/jello-2/PlantHopper", "https://gist.github.com/x/1", "https://gitlab.com/a/b",
        "https://devpost.com/software/x", "https://hack-the-valley-x.devpost.com/",
        "https://www.youtube.com/watch?v=1", "https://youtu.be/1", "https://www.loom.com/share/1",
        "https://docs.google.com/presentation/d/1", "https://drive.google.com/file/d/1/view",
        "https://www.canva.com/design/1/view", "https://www.figma.com/proto/1", "https://www.notion.so/x",
        "https://www.linkedin.com/in/x/", "https://x.com/someone", "https://www.instagram.com/x",
        "http://localhost:3000", "http://127.0.0.1:5000/", "http://192.168.1.4", "https://example.com/deck.pdf",
        "https://huggingface.co/someone/model", "https://cad.onshape.com/documents/1/w",
        "http://trasee.vercel.app", "https://tutoroohtv.netlify.app/", "www.storybites.vip",
        "https://huggingface.co/spaces/someone/app", "https://someone.github.io/app", "https://www.dropboxcdn.app",
        "http://trasee.vercel.app",
    ]}
    assert crawl.live_candidates(project) == [
        "http://trasee.vercel.app", "https://tutoroohtv.netlify.app/", "http://www.storybites.vip",
        "https://huggingface.co/spaces/someone/app", "https://someone.github.io/app", "https://www.dropboxcdn.app",
    ]


def test_not_a_demo():
    porkbun = "<html><head><title>porkbun.com | expired domain</title></head></html>"
    assert "parked" in crawl.not_a_demo("http://www.storybites.vip", "http://storybites.vip", porkbun)
    assert "lander" in crawl.not_a_demo("http://a.tech", "http://a.tech/lander", "<title>a.tech</title>")
    assert "sedoparking.com" in crawl.not_a_demo("http://a.xyz", "https://sedoparking.com/a.xyz", "")
    assert "for sale" in crawl.not_a_demo("http://a.xyz", "http://a.xyz/", "<h1>This domain is for sale!</h1>")
    assert "default page" in crawl.not_a_demo("http://1.2.3.4", "http://1.2.3.4/", "<title>Welcome to nginx!</title>")
    assert crawl.not_a_demo("http://layoffs.work", "https://devpost.com/software/layoff-evaders", "") == \
        "redirects to a devpost page (devpost.com)"
    assert crawl.not_a_demo("https://a.app", "https://github.com/a/b", "") == "redirects to a repo page (github.com)"
    assert crawl.not_a_demo("http://trasee.vercel.app", "https://trasee.vercel.app/", "<title>Trasee</title>") is None
    assert crawl.not_a_demo("https://www.studysync.study", "https://virellis.site", "<title>Study</title>") is None


def test_check_live_records_and_caches_results(steps, monkeypatch):
    calls = []
    answers = {
        "https://ok.app": (200, "https://ok.app/", "<title>Ok</title>"),
        "https://gone.app": (404, "https://gone.app/", "Not found"),
        "https://paused.vercel.app": (402, "https://paused.vercel.app/", "<title>Deployment Paused</title>"),
        "http://parked.vip": (200, "http://parked.vip/", "<title>porkbun.com | expired domain</title>"),
    }
    waking = iter([(503, "https://slow.onrender.com/", "<title>Render - Application loading</title>"),
                   (200, "https://slow.onrender.com/", "<title>Slow</title>")])

    def fake_get(url, read_timeout, verify=True):
        calls.append((url, read_timeout, verify))
        if url == "https://nodns.health":
            raise requests.exceptions.ConnectionError("Failed to resolve: NameResolutionError(...)")
        if url == "https://sleepy.app" and read_timeout == crawl.LIVE_TIMEOUT:
            raise requests.exceptions.ReadTimeout("read timed out")
        if url == "https://chain.ca" and verify:
            raise requests.exceptions.SSLError("certificate verify failed: unable to get local issuer certificate")
        if url == "https://handshake.us":
            raise requests.exceptions.SSLError("ssl/tls alert handshake failure")
        if url == "https://slow.onrender.com":
            return next(waking)
        if url in ("https://sleepy.app", "https://chain.ca"):
            return 200, url + "/", "<title>Up</title>"
        return answers[url]

    monkeypatch.setattr(crawl, "_get", fake_get)
    monkeypatch.setattr(crawl, "RETRY_WAIT", 0)
    assert crawl.check_live("https://ok.app") == {"ok": True, "status": 200, "final_url": "https://ok.app/", "error": None}
    assert crawl.check_live("https://gone.app") == {"ok": False, "status": 404, "final_url": "https://gone.app/", "error": "HTTP 404"}
    assert crawl.check_live("https://paused.vercel.app")["error"] == "HTTP 402 (Deployment Paused)"
    parked = crawl.check_live("http://parked.vip")
    assert parked["ok"] is False and parked["status"] == 200 and "expired domain" in parked["error"]
    assert crawl.check_live("https://nodns.health") == {"ok": False, "status": None, "final_url": None, "error": "DNS lookup failed"}
    assert crawl.check_live("https://handshake.us")["error"] == "TLS/SSL error"
    # Retries: a read timeout and a waking app get one more try; a missing intermediate certificate is fetched unverified.
    assert crawl.check_live("https://sleepy.app")["ok"] is True
    assert [t for u, t, v in calls if u == "https://sleepy.app"] == [crawl.LIVE_TIMEOUT, crawl.COLD_START_TIMEOUT]
    assert crawl.check_live("https://slow.onrender.com") == {"ok": True, "status": 200, "final_url": "https://slow.onrender.com/", "error": None}
    assert crawl.check_live("https://chain.ca")["ok"] is True
    assert [v for u, t, v in calls if u == "https://chain.ca"] == [True, False]

    urls = ["https://ok.app", "https://gone.app", "https://paused.vercel.app", "http://parked.vip", "https://nodns.health",
            "https://handshake.us", "https://sleepy.app", "https://slow.onrender.com", "https://chain.ca"]
    n = len(calls)
    for u in urls:
        crawl.check_live(u)
    assert len(calls) == n  # all served from cache/live/, failures included
    assert len(list((steps / "live").rglob("*.json"))) == len(urls)
    record = json.loads(crawl._live_path("https://chain.ca").read_text())
    assert record["note"] == "incomplete certificate chain" and record["title"] == "Up"
    crawl.check_live("https://ok.app", refresh=True)
    assert len(calls) == n + 1


def test_project_demo(monkeypatch):
    monkeypatch.setattr(crawl, "check_live", lambda u: {"ok": "good" in u, "status": 200, "final_url": u, "error": None})
    p = {"video": False, "links": ["https://github.com/a/b", "https://good.app", "https://bad.app"]}
    assert crawl.project_demo(p) == {"video": False, "live_urls": ["https://good.app", "https://bad.app"],
                                     "live_ok": ["https://good.app"], "demo": True}
    p = {"video": False, "links": ["https://github.com/a/b", "https://youtu.be/xyz", "https://bad.app"]}
    assert crawl.project_demo(p) == {"video": True, "live_urls": ["https://bad.app"], "live_ok": [], "demo": True}
    assert crawl.project_demo({"video": False, "links": ["https://bad.app"]})["demo"] is False


def test_prefetch_live_checks_each_candidate_once(monkeypatch):
    seen = []
    monkeypatch.setattr(crawl, "check_live", lambda u: seen.append(u) or {"ok": True, "status": 200, "final_url": u, "error": None})
    projects = [{"links": ["https://a.app", "https://github.com/a/b"]}, None, {"links": ["https://a.app", "https://b.app"]}]
    assert sorted(crawl.prefetch_live(projects, workers=2)) == ["https://a.app", "https://b.app"]
    assert sorted(seen) == ["https://a.app", "https://b.app"]


# -------------------------------------------------------------------- people

def test_portfolio_slugs():
    profile = {"projects": [
        "https://devpost.com/software/adify", "https://devpost.com/software/built-with/react",
        "/software/plant-hopper", "https://devpost.com/software/adify", "https://example.com/software/nope",
        "https://devpost.com/software/notes-max?ref=profile", "https://devpost.com/software/four",
    ]}
    assert crawl.portfolio_slugs(profile) == ["adify", "plant-hopper", "notes-max", "four"]
    assert crawl.portfolio_slugs(profile, cap=2) == ["adify", "plant-hopper"]
    assert crawl.portfolio_slugs(None) == []


def test_hackathon_projects_keeps_submitted_only(monkeypatch):
    pages = {"a": {"slug": "a", "submissions": [{"hackathon": "H", "url": "https://h.devpost.com/", "prizes": []}]},
             "b": {"slug": "b", "submissions": []}, "c": None}
    monkeypatch.setattr(devpost, "fetch_project", lambda s: pages[s])
    assert list(crawl.hackathon_projects(["a", "b", "c", "a"])) == ["a"]


def test_load_people_skips_challenges_for_missing_profiles(monkeypatch):
    asked = []
    monkeypatch.setattr(devpost, "fetch_profile", lambda u: None if u == "ghost" else {"username": u})
    monkeypatch.setattr(devpost, "fetch_challenges", lambda u: asked.append(u) or ["Hack the Valley X"])
    assert crawl.load_people(["eu-lee", "ghost", "eu-lee"]) == {
        "eu-lee": {"profile": {"username": "eu-lee"}, "challenges": ["Hack the Valley X"]},
        "ghost": {"profile": None, "challenges": []},
    }
    assert asked == ["eu-lee"]


# ------------------------------------------------------------------- windows

WIN = {"start": "2025-10-03T20:00:00-04:00", "end": "2025-10-05T10:00:00-04:00", "source": "devpost:details/dates"}


def test_submission_window_is_memoised_in_memory_and_on_disk(steps, monkeypatch):
    calls = []
    monkeypatch.setattr(devpost, "hackathon_window", lambda h: calls.append(h["url"]) or dict(WIN))
    sub = {"hackathon": "Hack the Valley X", "url": "https://hack-the-valley-x.devpost.com/", "prizes": []}
    w = crawl.submission_window(sub)
    assert w == {**WIN, "hackathon": "Hack the Valley X", "url": "https://hack-the-valley-x.devpost.com/"}
    assert crawl.submission_window({**sub, "url": "http://Hack-The-Valley-X.devpost.com"}) == w
    assert len(calls) == 1
    saved = json.loads(crawl.WINDOWS_JSON.read_text())
    assert saved == {"https://hack-the-valley-x.devpost.com/": w}
    monkeypatch.setattr(crawl, "_wmemo", None)  # a new run reads the file
    assert crawl.submission_window(sub) == w and len(calls) == 1


def test_submission_window_falls_back_to_the_same_event_in_the_api(steps, monkeypatch):
    api_days = {"start": "2025-01-11T00:00:00-05:00", "end": "2025-01-12T23:59:59-05:00", "source": "devpost:api-days"}

    def fake_window(h):
        if "submission_period_dates" not in h:
            raise ValueError("no dates page")
        return dict(api_days)

    found = {"DeltaHacks XI": {"title": "DeltaHacks XI", "url": "https://deltahacks-xi.devpost.com/",
                               "submission_period_dates": "Jan 11 - 12, 2025"},
             "Other": {"title": "Other", "url": "https://another-event.devpost.com/", "submission_period_dates": "Jan 1, 2025"}}
    monkeypatch.setattr(devpost, "hackathon_window", fake_window)
    monkeypatch.setattr(devpost, "find_hackathon", lambda t: found.get(t))
    w = crawl.submission_window({"hackathon": "DeltaHacks XI", "url": "https://deltahacks-xi.devpost.com/", "prizes": []})
    assert w["source"] == "devpost:api-days" and w["url"] == "https://deltahacks-xi.devpost.com/"
    # A same-titled event at another URL is not this event: no window (and that is remembered).
    assert crawl.submission_window({"hackathon": "Other", "url": "https://other.devpost.com/", "prizes": []}) is None
    assert json.loads(crawl.WINDOWS_JSON.read_text())["https://other.devpost.com/"] is None


def test_save_and_load_targets(steps):
    path = crawl.save_targets([{"name": "H", "url": "https://h.devpost.com/"}], {"https://h.devpost.com/": ["a"]}, {"quota": 1})
    assert path == crawl.TARGETS_JSON
    assert crawl.load_targets() == {"hackathons": [{"name": "H", "url": "https://h.devpost.com/"}],
                                    "projects": {"https://h.devpost.com/": ["a"]}, "quota": 1}


# ------------------------------------------------ real data (cached responses)

def test_hack_the_valley_x_resolves_with_exact_window_and_public_gallery(steps):
    [h] = crawl.resolve_targets(["Hack the Valley X"])
    assert h["id"] == 25485 and h["url"] == "https://hack-the-valley-x.devpost.com/"
    assert h["window"] == WIN
    assert h["gallery_public"] is True and h["gallery_total"] == 124


def test_hack_the_valley_x_gallery_is_winners_first():
    h = {"url": "https://hack-the-valley-x.devpost.com/", "gallery_url": "https://hack-the-valley-x.devpost.com/project-gallery",
         "open_state": "ended"}
    items = crawl.gallery_items(h)
    assert len(items) == 124 and len({i["slug"] for i in items}) == 124
    assert items[0]["slug"] == "plant-hopper"
    flags = [i["winner"] for i in items]
    assert sum(flags) == 20 and flags == sorted(flags, reverse=True)


def test_plant_hopper_team_and_window_from_devpost(steps):
    p = devpost.fetch_project("plant-hopper")
    assert crawl.submission_window(p["submissions"][0]) == {**WIN, "hackathon": "Hack the Valley X",
                                                           "url": "https://hack-the-valley-x.devpost.com/"}
    people = crawl.load_people(["eu-lee"])
    assert people["eu-lee"]["profile"]["github"] == "eu-lee"
    assert "Hack the Valley X" in people["eu-lee"]["challenges"]
    assert "plant-hopper" in crawl.portfolio_slugs(people["eu-lee"]["profile"])
