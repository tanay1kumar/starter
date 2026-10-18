"""Choose what to scan: target hackathons, their galleries, demos, people, windows.

BUILD.md "Data pipeline" steps 1-3. Rules implemented here:
- Hackathons come from Devpost's hackathon search API (paginated) and must match
  the asked-for title exactly after normalisation ("DeltaHacks 11" = "DeltaHacks XI").
  No fuzzy picks: an event that isn't there is reported as not found, with the
  queries we tried.
- An event that is still running (Hack the Valley 11) is scanned only if its project
  gallery is published and has projects. Its first gallery page is re-checked on
  every run, since it changes; everything else is served from the cache.
- Projects come from each event's own gallery in Devpost's default order (winners
  first). A project is kept only if "Try it out" links at least one GitHub repo,
  until the quota is met. A project in two target galleries is kept once.
- devpost.com/software/search (JSON) is not used. It is a full-text search over all
  of Devpost (6 results a page, no hackathon filter), and what it adds over the
  project page (has_video, winner, tags, members) is on the page we fetch anyway.
  On Hack the Valley X page 1 its has_video agreed with the page for 19 of 19
  projects it returned; 5 of the 24 projects were not on its first page by name.
- Demos: a project has a demo when Devpost shows a demo video (embedded, or a video
  link under "Try it out"), or a "Try it out" link answers 2xx/3xx after redirects,
  is not a parked/expired domain and does not land on a non-demo page. Repo hosts,
  Devpost, video, document/file (incl. CAD) and social links, and local addresses,
  are never live demos.
- People are read only from their own Devpost profile and /challenges page.
- Everything is cached under CACHE_DIR (http/devpost, live/, steps/), so a re-run
  makes no requests.

    python -m talentdex.crawl              # resolve, select, save cache/steps/targets.json
    python -m talentdex.crawl --demos      # also check every kept project's live links
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests

from . import devpost
from .config import CACHE_DIR

TARGETS = ["Hack the Valley X", "Hack the Valley 9", "Hack the 6ix 2025", "UofTHacks 12", "DeltaHacks 11",
           "Hack the North 2025", "Hack the Valley 11"]

# The design's "214 projects": split evenly across the events we can scan.
TOTAL_PROJECTS = 214

STEPS_DIR = CACHE_DIR / "steps"
TARGETS_JSON = STEPS_DIR / "targets.json"
WINDOWS_JSON = STEPS_DIR / "windows.json"
LIVE_DIR = CACHE_DIR / "live"


def log(msg: str) -> None:
    print(f"[crawl] {msg}", file=sys.stderr, flush=True)


def _write_json(path: Path, data: object) -> None:
    """Atomic write (safe when several threads write different files)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str))
    tmp.replace(path)


def _norm_url(url: str) -> str:
    """'http://Hack-The-Valley-X.devpost.com' -> 'https://hack-the-valley-x.devpost.com/'."""
    p = urlparse((url or "").strip())
    if not p.netloc:
        return ""
    return f"https://{p.netloc.lower()}{p.path.rstrip('/')}/"


# ---------------------------------------------------------------- hackathons

_INT_TO_ROMAN = {n: r.upper() for r, n in devpost.ROMAN.items()}


def query_variants(name: str) -> list[str]:
    """Search queries for one event, most specific first.

    'UofTHacks 12' -> ['UofTHacks 12', 'UofTHacks', 'UofTHacks XII', 'UofTHacks12'];
    'Hack the Valley X' -> [..., 'Hack the Valley', 'Hack the Valley 10'].
    The match itself is always an exact normalised title, whatever the query.
    """
    name = re.sub(r"\s+", " ", name.strip())
    out = [name]
    m = re.match(r"^(.*\S)\s+(\d+|[ivxIVX]+)$", name)
    if m:
        series, num = m.group(1), m.group(2)
        out.append(series)
        if num.isdigit() and int(num) in _INT_TO_ROMAN:
            out.append(f"{series} {_INT_TO_ROMAN[int(num)]}")
        elif num.lower() in devpost.ROMAN:
            out.append(f"{series} {devpost.ROMAN[num.lower()]}")
        if " " not in series:  # brand names are sometimes written as one word
            out.append(f"{series}{num}")
    return list(dict.fromkeys(out))


def find_target(name: str) -> tuple[dict | None, list[str]]:
    """The hackathon API entry titled `name` (normalised), and the queries tried.

    devpost.find_hackathon covers the name and its series name (up to 6 result
    pages each); the extra queries add the roman/arabic and one-word spellings.
    """
    h = devpost.find_hackathon(name)
    tried = query_variants(name)
    if h is not None:
        return h, tried[:1]
    want = devpost.norm_title(name)
    for q in tried[1:]:
        for cand in devpost.search_hackathons(q):
            if devpost.norm_title(cand.get("title", "")) == want:
                return cand, tried
    return None, tried


def gallery_url(h: dict) -> str:
    return h.get("gallery_url") or h.get("submission_gallery_url") or h["url"].rstrip("/") + "/project-gallery"


def _running(h: dict) -> bool:
    """Open or upcoming: its gallery can still change."""
    return h.get("open_state") not in (None, "ended")


def gallery_page(h: dict, page: int) -> dict:
    """devpost.parse_gallery of <gallery_url>?page=N (fresh for a running event)."""
    r = devpost.DEVPOST.get(f"{gallery_url(h)}?page={page}", use_cache=not _running(h))
    if not r.ok:
        return {"items": [], "total": None, "message": f"HTTP {r.status}"}
    return devpost.parse_gallery(r.text)


def resolve_targets(names: Iterable[str] = TARGETS) -> list[dict]:
    """One entry per asked-for event, found or not.

    {name, title, id, url, gallery_url, dates, open_state, window: {start, end, source},
     gallery_public, gallery_total, note}. Not found -> everything None, gallery_public
    False and `note` names the queries tried.
    """
    out = []
    for name in names:
        h, tried = find_target(name)
        if h is None:
            note = ("not on Devpost: no exact title match in the hackathon search API for "
                    + ", ".join(repr(q) for q in tried))
            log(f"{name}: {note}")
            out.append({"name": name, "title": None, "id": None, "url": None, "gallery_url": None, "dates": None,
                        "open_state": None, "window": None, "gallery_public": False, "gallery_total": None,
                        "note": note})
            continue
        entry = {"name": name, "title": h["title"], "id": h.get("id"), "url": h["url"], "gallery_url": gallery_url(h),
                 "dates": h.get("submission_period_dates"), "open_state": h.get("open_state")}
        win = target_window(h)
        first = gallery_page(entry, 1)
        public = bool(first["items"])
        note = "" if public else (first["message"] or "the gallery has no projects")
        entry.update({
            "window": {k: win[k] for k in ("start", "end", "source")} if win else None,
            "gallery_public": public,
            "gallery_total": first["total"],
            "note": note,
        })
        log(f"{name}: {h['title']} (id {h.get('id')}, {h.get('submission_period_dates')}, {h.get('open_state')}) "
            f"window {win['start'] if win else '?'} -> {win['end'] if win else '?'} [{win['source'] if win else 'none'}]; "
            + (f"gallery public, {first['total']} projects" if public else f"gallery not public: {note}"))
        out.append(entry)
    return out


# ------------------------------------------------------------------- gallery

def gallery_items(h: dict, max_pages: int = 60) -> list[dict]:
    """Every project card in the event's gallery, in Devpost's default order.

    [{slug, url, winner, name}] from <gallery_url>?page=1..N (24 a page), stopping at
    the first page with no new items.
    """
    items: list[dict] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        new = [i for i in gallery_page(h, page)["items"] if i["slug"] not in seen]
        if not new:
            break
        for i in new:
            seen.add(i["slug"])
            items.append({"slug": i["slug"], "url": i["url"], "winner": i["winner"], "name": i["name"]})
    return items


def select_targets(h: dict, quota: int, *, skip: Iterable[str] = (), stats: dict | None = None) -> list[str]:
    """Up to `quota` project slugs from h's gallery that link a GitHub repo.

    Winners first (in gallery order), then the rest. Each candidate's project page
    is fetched (cached) and kept only if project["repos"] is non-empty. Slugs in
    `skip` (already chosen for another event) are passed over. `stats`, if given,
    is filled with what happened (gallery_items, winners, pages_fetched, kept,
    kept_winners, no_repo, missing, duplicates).
    """
    items = gallery_items(h)
    order = [i for i in items if i["winner"]] + [i for i in items if not i["winner"]]
    skip = set(skip)
    kept: list[str] = []
    st = {"gallery_items": len(items), "winners": sum(i["winner"] for i in items), "pages_fetched": 0,
          "kept": 0, "kept_winners": 0, "no_repo": 0, "missing": 0, "duplicates": 0}
    for it in order:
        if len(kept) >= quota:
            break
        if it["slug"] in skip:
            st["duplicates"] += 1
            continue
        p = devpost.fetch_project(it["url"])
        st["pages_fetched"] += 1
        if p is None:
            st["missing"] += 1
        elif not p["repos"]:
            st["no_repo"] += 1
        else:
            kept.append(it["slug"])
            st["kept_winners"] += int(it["winner"])
    st["kept"] = len(kept)
    if stats is not None:
        stats.update(st)
    return kept


# --------------------------------------------------------------------- demos

# Matched as host suffixes on a dot boundary: "x.com" covers "www.x.com", and
# "box.com" does not cover "dropbox.com".
REPO_HOSTS = ("github.com", "githubusercontent.com", "gitlab.com", "bitbucket.org")
VIDEO_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com", "loom.com", "streamable.com",
               "wistia.com", "twitch.tv")
DOC_HOSTS = ("docs.google.com", "drive.google.com", "forms.gle", "colab.research.google.com", "dropbox.com",
             "dropboxusercontent.com", "notion.so", "notion.site", "canva.com", "figma.com", "slides.com",
             "prezi.com", "pitch.com", "gamma.app", "docsend.com", "onedrive.live.com", "1drv.ms", "sharepoint.com",
             "box.com", "slideshare.net", "scribd.com", "medium.com", "dev.to", "hashnode.dev", "substack.com",
             "kaggle.com", "onshape.com")
SOCIAL_HOSTS = ("linkedin.com", "twitter.com", "x.com", "instagram.com", "facebook.com", "fb.com", "tiktok.com",
                "discord.gg", "discord.com", "reddit.com", "threads.net")
FILE_EXTS = (".pdf", ".ppt", ".pptx", ".key", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".mp4", ".mov")


def _host_in(host: str, suffixes: Iterable[str]) -> bool:
    return any(host == s or host.endswith("." + s) for s in suffixes)


def _with_scheme(url: str) -> str:
    url = (url or "").strip()
    if url and "://" not in url and not re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
        url = "http://" + url
    return url


def _local_host(host: str) -> bool:
    if host in ("localhost", "0.0.0.0") or host.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified


def link_kind(url: str) -> str:
    """'live' (could be a working demo), 'video', or why it can't be: 'repo', 'devpost',
    'doc', 'social', 'local', 'file', 'invalid'."""
    p = urlparse(_with_scheme(url))
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not host or ("." not in host and host != "localhost"):
        return "invalid"
    if _local_host(host):
        return "local"
    if _host_in(host, REPO_HOSTS):
        return "repo"
    if _host_in(host, ("devpost.com",)):
        return "devpost"
    if _host_in(host, VIDEO_HOSTS):
        return "video"
    if _host_in(host, DOC_HOSTS):
        return "doc"
    if _host_in(host, SOCIAL_HOSTS):
        return "social"
    if host == "huggingface.co" and not p.path.startswith("/spaces/"):
        return "doc"  # model and dataset pages; Spaces are live apps
    if p.path.lower().endswith(FILE_EXTS):
        return "file"
    return "live"


def live_candidates(project: dict) -> list[str]:
    """"Try it out" URLs that could be a working live demo, in page order."""
    out: list[str] = []
    for raw in project.get("links") or []:
        url = _with_scheme(raw)
        if link_kind(url) == "live" and url not in out:
            out.append(url)
    return out


# Says who we are, in the browser-compatible form: some hosts drop requests whose
# User-Agent does not start with "Mozilla/5.0" (sematic.ca did).
LIVE_UA = "Mozilla/5.0 (compatible; TalentDex/1.0; hackathon recruiting research)"
LIVE_TIMEOUT = 10.0
COLD_START_TIMEOUT = 30.0  # free tiers (Render, Heroku...) can take this long to wake an app
RETRY_STATUSES = {429, 502, 503, 504}  # busy or waking up ("Render - Application loading")
RETRY_WAIT = 45.0
BODY_BYTES = 200_000

# Parking and domain-sale services an expired hackathon domain ends up on.
PARKING_HOSTS = ("porkbun.com", "sedoparking.com", "parkingcrew.net", "bodis.com", "above.com", "parklogic.com",
                 "dan.com", "afternic.com", "hugedomains.com", "godaddy.com", "domainmarket.com", "sav.com",
                 "undeveloped.com", "squadhelp.com", "atom.com", "brandbucket.com", "uniregistry.com", "epik.com",
                 "namecheap.com", "expireddomains.net")
PARKED_TEXT = re.compile(
    r"expired domain|parked domain|domain (?:name )?(?:is|may be) for sale|domain has expired|buy this domain"
    r"|parked free|this domain is parked|sedoparking|parkingcrew|renew (?:this|your) domain"
    r"|future home of something quite cool", re.I)
DEFAULT_PAGE_TITLE = re.compile(
    r"^(?:welcome to nginx!?|apache2 .*default page.*|index of /|iis windows server|test page for the .*http server.*"
    r"|domain default page|web server's default page)$", re.I)

# verify=False is only used for sites whose certificate chain is incomplete (see _fetch).
warnings.filterwarnings("ignore", message="Unverified HTTPS request")


def _title(body: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def not_a_demo(url: str, final_url: str | None, body: str) -> str | None:
    """Why a 2xx/3xx answer is still not a working demo, else None.

    Parked or expired domains, server default pages, a missing Streamlit app, and
    links that end up on a repo, Devpost, video, document or social page.
    """
    final = final_url or url
    host = (urlparse(final).hostname or "").lower()
    first_host = (urlparse(url).hostname or "").lower()
    title = _title(body)
    if host != first_host and _host_in(host, PARKING_HOSTS):
        return f"parked or expired domain (redirects to {host})"
    if urlparse(final).path.rstrip("/") == "/lander":
        return "parked domain (registrar lander page)"
    m = PARKED_TEXT.search(title) or PARKED_TEXT.search(body)
    if m:
        return f"parked or expired domain ({m.group(0).lower()!r} on the page)"
    if DEFAULT_PAGE_TITLE.match(title):
        return f"server default page ({title!r})"
    if host == "share.streamlit.io" and first_host.endswith(".streamlit.app"):
        return "Streamlit app missing or private"
    kind = link_kind(final)
    if kind != "live":
        return f"redirects to a {kind} page ({host})"
    return None


def _short_error(e: Exception) -> str:
    s = str(e)
    if isinstance(e, requests.exceptions.SSLError):
        return "TLS/SSL error"
    if isinstance(e, requests.exceptions.Timeout):
        return "timed out"
    if isinstance(e, requests.exceptions.TooManyRedirects):
        return "too many redirects"
    if any(k in s for k in ("NameResolution", "Name or service not known", "nodename nor servname", "getaddrinfo")):
        return "DNS lookup failed"
    if "Connection refused" in s:
        return "connection refused"
    if isinstance(e, (requests.exceptions.InvalidURL, requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema)):
        return "invalid URL"
    return type(e).__name__


def _get(url: str, read_timeout: float, verify: bool = True) -> tuple[int, str, str]:
    """One GET following redirects: (status, final URL, first BODY_BYTES of the body)."""
    headers = {"User-Agent": LIVE_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    with requests.get(url, headers=headers, timeout=(LIVE_TIMEOUT, read_timeout), allow_redirects=True,
                      stream=True, verify=verify) as r:
        chunks, n = [], 0
        for c in r.iter_content(16384):
            chunks.append(c)
            n += len(c)
            if n >= BODY_BYTES:
                break
        return r.status_code, r.url, b"".join(chunks).decode(r.encoding or "utf-8", "replace")


def _fetch(url: str) -> tuple[int, str, str, str | None]:
    """_get with at most one retry: (status, final URL, body, note).

    A read timeout, or a busy/waking answer (429/502/503/504, after RETRY_WAIT), is
    tried once more with COLD_START_TIMEOUT. A certificate chain missing an
    intermediate (browsers fetch it themselves) is fetched without verification and
    noted. Other errors raise.
    """
    verify, note = True, None
    try:
        first = _get(url, LIVE_TIMEOUT)
    except requests.exceptions.ReadTimeout:
        first = None
    except requests.exceptions.SSLError as e:
        if "unable to get local issuer certificate" not in str(e):
            raise
        verify, note = False, "incomplete certificate chain"
        first = _get(url, LIVE_TIMEOUT, verify=False)
    if first is not None and first[0] not in RETRY_STATUSES:
        return (*first, note)
    if first is not None:
        time.sleep(RETRY_WAIT)
    return (*_get(url, COLD_START_TIMEOUT, verify=verify), note)


def _probe(url: str) -> dict:
    try:
        status, final, body, note = _fetch(url)
    except requests.RequestException as e:
        return {"ok": False, "status": None, "final_url": None, "error": _short_error(e)}
    except Exception as e:  # malformed URLs can raise ValueError/UnicodeError inside requests
        return {"ok": False, "status": None, "final_url": None, "error": type(e).__name__}
    title = _title(body)[:200]  # kept in the cache record only, to audit these rules
    if 200 <= status < 400:
        why = not_a_demo(url, final, body)
    else:
        why = f"HTTP {status}" + (f" ({title})" if title else "")
    return {"ok": why is None, "status": status, "final_url": final, "error": why, "title": title, "note": note}


def _live_path(url: str) -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()
    return LIVE_DIR / h[:2] / f"{h}.json"


def check_live(url: str, *, refresh: bool = False) -> dict:
    """Does this URL answer like a working site? {ok, status, final_url, error}.

    GET with a 10 s timeout, following redirects (one retry for apps waking up, see
    _fetch). ok = 2xx/3xx and not_a_demo() finds nothing wrong. Failures are
    recorded with why (status None for network errors). Cached in cache/live/ with
    the page title, so a re-run makes no requests; refresh=True checks again.
    """
    path = _live_path(url)
    if not refresh and path.exists():
        try:
            rec = json.loads(path.read_text())
            return {k: rec.get(k) for k in ("ok", "status", "final_url", "error")}
        except (OSError, json.JSONDecodeError):
            pass
    rec = _probe(url)
    _write_json(path, {**rec, "url": url, "checked_at": time.time()})
    return {k: rec.get(k) for k in ("ok", "status", "final_url", "error")}


def check_live_many(urls: Iterable[str], workers: int = 8) -> dict[str, dict]:
    """check_live for many URLs, a few at a time (they are almost all different hosts)."""
    todo = list(dict.fromkeys(urls))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        return dict(zip(todo, ex.map(check_live, todo)))


def prefetch_live(projects: Iterable[dict | None], workers: int = 8) -> dict[str, dict]:
    """Check every live candidate of these projects in parallel (warms the cache, so a
    later project_demo() per project makes no requests). {url: check_live result}."""
    return check_live_many((u for p in projects if p for u in live_candidates(p)), workers=workers)


def project_demo(project: dict) -> dict:
    """{"video", "live_urls", "live_ok", "demo"} for one parsed project page.

    video: Devpost embeds a demo video, or "Try it out" links a video site.
    live_urls: live_candidates(project); live_ok: the ones check_live says work.
    """
    video = bool(project.get("video")) or any(link_kind(u) == "video" for u in project.get("links") or [])
    live = live_candidates(project)
    ok = [u for u in live if check_live(u)["ok"]]
    return {"video": video, "live_urls": live, "live_ok": ok, "demo": video or bool(ok)}


# -------------------------------------------------------------------- people

def load_people(usernames: Iterable[str]) -> dict[str, dict]:
    """{username: {"profile": devpost.parse_profile(...) | None, "challenges": [hackathon names]}}.

    A profile that 404s gives profile None and no challenges (its /challenges page
    is not requested).
    """
    out: dict[str, dict] = {}
    for u in dict.fromkeys(usernames):
        prof = devpost.fetch_profile(u)
        out[u] = {"profile": prof, "challenges": devpost.fetch_challenges(u) if prof else []}
    return out


_SOFTWARE = re.compile(r"^https?://(?:www\.)?devpost\.com/software/([A-Za-z0-9_-]+)/?(?:[?#].*)?$")


def portfolio_slugs(profile: dict | None, cap: int = 12) -> list[str]:
    """Software slugs on a profile, as listed (most recent first), without built-with links."""
    out: list[str] = []
    for href in (profile or {}).get("projects") or []:
        m = _SOFTWARE.match(urljoin("https://devpost.com/", href.strip()))
        if not m or m.group(1) == "built-with" or m.group(1) in out:
            continue
        out.append(m.group(1))
        if len(out) >= cap:
            break
    return out


def hackathon_projects(slugs: Iterable[str]) -> dict[str, dict]:
    """{slug: project} for the projects submitted to at least one hackathon."""
    out: dict[str, dict] = {}
    for slug in dict.fromkeys(slugs):
        p = devpost.fetch_project(slug)
        if p is not None and p["submissions"]:
            out[slug] = p
    return out


# ------------------------------------------------------------------- windows

_wlock = threading.Lock()
_wmemo: dict | None = None


def _windows() -> dict:
    global _wmemo
    if _wmemo is None:
        try:
            _wmemo = json.loads(WINDOWS_JSON.read_text())
        except (OSError, json.JSONDecodeError):
            _wmemo = {}
    return _wmemo


def _window(url: str, title: str, api: dict | None = None) -> dict | None:
    """Memoised window for one hackathon, by URL (or by title when there is no URL)."""
    url = _norm_url(url)
    key = url or f"title:{devpost.norm_title(title)}"
    with _wlock:
        memo = _windows()
        if key in memo:
            return dict(memo[key]) if memo[key] else None
    win = None
    first = api or ({"url": url, "title": title} if url else None)
    if first:
        try:
            win = {**devpost.hackathon_window(first), "hackathon": first.get("title") or title, "url": url or _norm_url(first["url"])}
        except ValueError:
            pass
    if win is None and title and not api:
        # No dates on <url>/details/dates: the search API's days for the same event.
        h = devpost.find_hackathon(title)
        if h is not None and (not url or _norm_url(h["url"]) == url):
            try:
                win = {**devpost.hackathon_window(h), "hackathon": h["title"], "url": _norm_url(h["url"])}
            except ValueError:
                pass
    with _wlock:
        memo = _windows()
        memo[key] = win
        _write_json(WINDOWS_JSON, memo)
    return dict(win) if win else None


def submission_window(sub: dict) -> dict | None:
    """Submission window for one project submission {"hackathon", "url", "prizes"}.

    <url>/details/dates first (exact times), else the hackathon search API by title,
    accepted only when it finds the same event URL (its days, Toronto time).
    Returns {start, end, source, hackathon, url} or None when neither has dates.
    Memoised per hackathon URL in memory and in cache/steps/windows.json.
    """
    return _window(sub.get("url") or "", (sub.get("hackathon") or "").strip())


def target_window(h: dict) -> dict | None:
    """Window for a hackathon API entry (memoised like submission_window)."""
    return _window(h["url"], h.get("title", ""), api=h)


# --------------------------------------------------------------------- crawl

def quota_for(total: int, events: int) -> int:
    return math.ceil(total / events) if events else 0


def save_targets(hackathons: list[dict], projects: dict[str, list[str]], extra: dict | None = None,
                 path: Path | None = None) -> Path:
    """cache/steps/targets.json: {"hackathons": [...], "projects": {hackathon_url: [slugs]}, ...extra}."""
    path = path or TARGETS_JSON
    _write_json(path, {"hackathons": hackathons, "projects": projects, **(extra or {})})
    return path


def load_targets(path: Path | None = None) -> dict | None:
    try:
        return json.loads((path or TARGETS_JSON).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def crawl(names: Iterable[str] = TARGETS, total: int = TOTAL_PROJECTS) -> dict:
    """Resolve the targets, pick each public event's projects, save targets.json."""
    hackathons = resolve_targets(names)
    public = [h for h in hackathons if h["gallery_public"]]
    quota = quota_for(total, len(public))
    log(f"{len(public)} of {len(hackathons)} events have a public gallery; quota {quota} projects each")
    projects: dict[str, list[str]] = {}
    stats: dict[str, dict] = {}
    chosen: set[str] = set()
    for h in public:
        st: dict = {}
        before = devpost.DEVPOST.network_calls
        slugs = select_targets(h, quota, skip=chosen, stats=st)
        st["network_requests"] = devpost.DEVPOST.network_calls - before
        chosen.update(slugs)
        projects[h["url"]] = slugs
        stats[h["url"]] = st
        log(f"{h['title']}: {st['gallery_items']} in gallery ({st['winners']} winners); fetched {st['pages_fetched']} "
            f"project pages ({st['network_requests']} new requests); kept {st['kept']} ({st['kept_winners']} winners), "
            f"{st['no_repo']} without a GitHub repo, {st['missing']} missing, {st['duplicates']} already chosen")
    extra = {"quota": quota, "total_asked": total, "stats": stats, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    save_targets(hackathons, projects, extra)
    return {"hackathons": hackathons, "projects": projects, **extra}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--total", type=int, default=TOTAL_PROJECTS, help="projects to scan across all events")
    ap.add_argument("--demos", action="store_true", help="also check the live links of every kept project")
    args = ap.parse_args(argv)

    res = crawl(TARGETS, args.total)
    slugs = [s for v in res["projects"].values() for s in v]
    members: set[str] = set()
    for s in slugs:
        p = devpost.fetch_project(s)
        members.update(m["username"] for m in (p or {}).get("members", []))
    print(f"kept {len(slugs)} projects ({len(set(slugs))} unique), {len(members)} unique team members")
    if args.demos:
        projects = [devpost.fetch_project(s) for s in slugs]
        checks = prefetch_live(projects)
        demos = [project_demo(p) for p in projects if p]
        print(f"live links: {len(checks)} checked, {sum(c['ok'] for c in checks.values())} working; "
              f"projects with a video {sum(d['video'] for d in demos)}, with a working live link "
              f"{sum(bool(d['live_ok']) for d in demos)}, with a demo {sum(d['demo'] for d in demos)} of {len(demos)}")
    print(f"saved {TARGETS_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
