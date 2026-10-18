"""Devpost: hackathons, project pages, user profiles.

Only public pages and the public hackathon search API are read, slowly, and
every response is cached. People are identified by their Devpost username;
GitHub and LinkedIn come only from links they posted on their own profile.
"""

from __future__ import annotations

import re
from datetime import datetime, time as dtime
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .config import DEFAULT_TZ
from .httpcache import Http

DEVPOST = Http("devpost", min_interval=0.7)

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
         "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15}


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def text(el: Any) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


# ---------------------------------------------------------------- hackathons

def norm_title(t: str) -> str:
    """'DeltaHacks XI' and 'DeltaHacks 11' normalise to the same key."""
    words = re.sub(r"[^a-z0-9 ]+", " ", t.lower()).split()
    return " ".join(str(ROMAN[w]) if w in ROMAN else w for w in words)


def search_hackathons(query: str, pages: int = 6) -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        r = DEVPOST.get("https://devpost.com/api/hackathons", params={"search": query, "page": page}, accept="application/json")
        if not r.ok:
            break
        d = r.json()
        out.extend(d.get("hackathons", []))
        meta = d.get("meta", {})
        if page * int(meta.get("per_page", 9) or 9) >= int(meta.get("total_count", 0) or 0):
            break
    return out


def find_hackathon(name: str) -> dict | None:
    """Exact (normalised) title match from the hackathon search API."""
    want = norm_title(name)
    for h in search_hackathons(name):
        if norm_title(h.get("title", "")) == want:
            return h
    # Some events are listed under a slightly different query; try the series name.
    series = re.sub(r"\s+(\d+|[ivx]+|20\d\d)$", "", name.strip(), flags=re.I)
    if series != name:
        for h in search_hackathons(series):
            if norm_title(h.get("title", "")) == want:
                return h
    return None


def _day_range(dates: str, tz: str) -> tuple[datetime, datetime] | None:
    """Parse Devpost's 'Oct 03 - 05, 2025' / 'Dec 30, 2024 - Jan 02, 2025' / 'Oct 24, 2026'."""
    s = dates.replace("–", "-").strip()
    m = re.match(r"^([A-Za-z]{3}) (\d{1,2})(?:, (\d{4}))? - (?:([A-Za-z]{3}) )?(\d{1,2}), (\d{4})$", s)
    one = re.match(r"^([A-Za-z]{3}) (\d{1,2}), (\d{4})$", s)
    try:
        if m:
            m1, d1, y1, m2, d2, y2 = m.groups()
            start = datetime.strptime(f"{m1} {d1} {y1 or y2}", "%b %d %Y")
            end = datetime.strptime(f"{m2 or m1} {d2} {y2}", "%b %d %Y")
        elif one:
            start = end = datetime.strptime(f"{one.group(1)} {one.group(2)} {one.group(3)}", "%b %d %Y")
        else:
            return None
    except ValueError:
        return None
    z = ZoneInfo(tz)
    return datetime.combine(start.date(), dtime(0, 0), z), datetime.combine(end.date(), dtime(23, 59, 59), z)


def hackathon_window(h: dict) -> dict:
    """The submission window used for attribution.

    Prefer the exact 'Submissions' begin/end from <hackathon>/details/dates
    (data-iso-date attributes, with offsets). Fall back to whole days from the
    API's submission_period_dates in Toronto time.
    """
    base = h["url"].rstrip("/") + "/"
    r = DEVPOST.get(urljoin(base, "details/dates"))
    if r.ok:
        s = soup(r.text)
        for row in s.select("tr"):
            cells = row.find_all(["td", "th"])
            if cells and text(cells[0]).lower().startswith("submission"):
                isos = [c.get("data-iso-date") for c in row.select("[data-iso-date]")]
                isos = [i for i in isos if i]
                if len(isos) >= 2:
                    return {"start": isos[0], "end": isos[1], "source": "devpost:details/dates"}
    rng = _day_range(h.get("submission_period_dates", ""), DEFAULT_TZ)
    if rng:
        return {"start": rng[0].isoformat(), "end": rng[1].isoformat(), "source": "devpost:api-days"}
    raise ValueError(f"no submission window for {h.get('title')}")


# ------------------------------------------------------------------ projects

GITHUB_REPO = re.compile(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:[/?#].*)?$")
NOT_REPO_OWNERS = {"orgs", "topics", "features", "marketplace", "sponsors", "settings", "apps", "collections", "about", "login"}


def repo_slug(url: str) -> str | None:
    """'https://github.com/jello-2/PlantHopper/tree/main' -> 'jello-2/PlantHopper'."""
    m = GITHUB_REPO.match(url.strip())
    if not m or m.group(1).lower() in NOT_REPO_OWNERS:
        return None
    return f"{m.group(1)}/{m.group(2)}"


def project_slug(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


STORY_MAX = 6000  # characters of the write-up kept for the topic search


def parse_project(html: str, url: str) -> dict:
    s = soup(html)
    name = text(s.select_one("#app-title"))
    header = s.select_one("#software-header")
    tagline = text(header.select_one("p.large")) if header else ""
    if not tagline:
        og = s.select_one('meta[property="og:description"]')
        tagline = (og.get("content") or "").strip() if og else ""

    submissions = []
    for li in s.select("#submissions ul.software-list-with-thumbnail > li"):
        a = li.select_one(".software-list-content p a") or li.select_one("a")
        prizes = []
        for p in li.select(".software-list-content ul li"):
            if p.select_one(".winner"):
                label = text(p).replace("Winner", "", 1).strip()
                if label:
                    prizes.append(label)
        if a:
            submissions.append({"hackathon": text(a), "url": a.get("href", ""), "prizes": prizes})

    members = []
    for li in s.select("#app-team li.software-team-member"):
        links = [a for a in li.select("a.user-profile-link") if a.get("href")]
        if not links:
            continue
        href = links[-1]["href"]
        username = urlparse(href).path.strip("/").split("/")[0]
        members.append({"username": username, "name": text(links[-1]) or username, "note": text(li.select_one("small"))})

    links = []
    for a in s.select('nav.app-links ul[data-role="software-urls"] a[href]'):
        links.append(a["href"].strip())
    repos: list[str] = []
    for l in links:
        slug = repo_slug(l)
        if slug and slug.lower() not in {r.lower() for r in repos}:
            repos.append(slug)

    video = False
    for f in s.select("#gallery iframe[src]"):
        if re.search(r"youtube\.com|youtu\.be|vimeo\.com|loom\.com|player\.", f["src"]):
            video = True
    built_with = [text(t) for t in s.select("#built-with .cp-tag")]
    story = s.select_one("#app-details-left")
    story_chars = len(text(story)) if story else 0
    # The write-up itself: the untitled block between the gallery and "Built With".
    body = next((d for d in story.find_all("div", recursive=False) if not d.get("id")), None) if story else None
    sections: list[tuple[str, list[str]]] = [("", [])]
    for el in body.find_all(recursive=False) if body else ():
        if el.name in ("h1", "h2", "h3", "h4"):
            sections.append((text(el), []))
        elif text(el):
            sections[-1][1].append(text(el))
    return {
        "slug": project_slug(url),
        "url": url,
        "name": name,
        "tagline": tagline,
        "submissions": submissions,
        "members": members,
        "links": links,
        "repos": repos,
        "video": video,
        "built_with": built_with,
        "story_chars": story_chars,
        # One section per paragraph block: "Heading\ntext", blank line between sections.
        "story": "\n\n".join(f"{h}\n{' '.join(t)}".strip() for h, t in sections if t)[:STORY_MAX],
    }


def fetch_project(url_or_slug: str) -> dict | None:
    url = url_or_slug if url_or_slug.startswith("http") else f"https://devpost.com/software/{url_or_slug}"
    r = DEVPOST.get(url)
    if not r.ok:
        return None
    return parse_project(r.text, url)


# ----------------------------------------------------------------- galleries

def parse_gallery(html: str) -> dict:
    """One page of a hackathon's project gallery (<hackathon>/project-gallery?page=N).

    Returns {"items": [{slug, url, name, winner, software_id}], "total": int | None,
    "message": str}. Items are in page order; `winner` is Devpost's winner ribbon;
    `url` is always https://devpost.com/software/<slug> (the same key fetch_project
    caches under). `total` comes from the "1 – 24 of 124" line; `message` is the
    note Devpost shows instead of items (e.g. "The hackathon managers haven't
    published this gallery yet, but hang tight!").
    """
    s = soup(html)
    items: list[dict] = []
    for item in s.select(".gallery-item"):
        a = item.select_one("a.link-to-software[href]") or item.select_one("a[href*='/software/']")
        if not a or "/software/built-with/" in a["href"]:
            continue
        slug = project_slug(a["href"])
        if not slug or any(i["slug"] == slug for i in items):
            continue
        items.append({
            "slug": slug,
            "url": f"https://devpost.com/software/{slug}",
            "name": text(item.select_one("h5")),
            "winner": item.select_one("img.winner") is not None,
            "software_id": item.get("data-software-id"),
        })
    notes = []
    g = s.select_one("#submission-gallery")
    if g:
        notes = [text(p) for p in g.find_all("p") if p.find_parent("form") is None and p.find_parent(class_="gallery-item") is None]
        notes = [n for n in notes if n]
    total = None
    for n in notes:
        m = re.search(r"\bof\s+([\d,]+)\s*$", n)
        if m:
            total = int(m.group(1).replace(",", ""))
    message = "" if items else (notes[0] if notes else "")
    return {"items": items, "total": total, "message": message}


# ------------------------------------------------------------------ profiles

def _github_user(url: str) -> str | None:
    m = re.match(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9-]+)/?(?:[?#].*)?$", url.strip())
    return m.group(1) if m and m.group(1).lower() not in NOT_REPO_OWNERS else None


def _linkedin(url: str) -> str | None:
    m = re.match(r"^https?://(?:[a-z]{2,3}\.)?(?:www\.)?linkedin\.com/in/([^/?#]+)/?", url.strip(), re.I)
    return f"https://www.linkedin.com/in/{m.group(1)}/" if m else None


def parse_profile(html: str, username: str) -> dict:
    s = soup(html)
    name_el = s.select_one("#portfolio-user-name")
    name = ""
    if name_el:
        small = name_el.select_one("small")
        if small:
            small.extract()
        name = text(name_el)
    bio = text(s.select_one("#portfolio-user-bio"))
    location = ""
    links: dict[str, str] = {}
    for li in s.select("#portfolio-user-links li"):
        icon = li.select_one(".ss-icon")
        cls = " ".join(icon.get("class", [])) if icon else ""
        a = li.select_one("a[href]")
        if "ss-location" in cls and not a:
            location = text(li)
            continue
        if not a:
            continue
        href = a["href"].strip()
        if "ss-octocat" in cls:
            links.setdefault("github", href)
        elif "ss-linkedin" in cls:
            links.setdefault("linkedin", href)
        elif "ss-twitter" in cls:
            links.setdefault("twitter", href)
        else:
            links.setdefault("website", href)

    # A "Website" link that is a GitHub profile or LinkedIn page was still posted by them.
    gh = _github_user(links.get("github", "")) if links.get("github") else None
    if not gh and links.get("website"):
        gh = _github_user(links["website"])
    li_url = _linkedin(links.get("linkedin", "")) if links.get("linkedin") else None
    if not li_url and links.get("website"):
        li_url = _linkedin(links["website"])

    counts: dict[str, int] = {}
    for a in s.select("#portfolio-navigation li a"):
        tot = a.select_one(".totals")
        if not tot:
            continue
        n = re.sub(r"[^\d]", "", text(tot))
        label = text(a).replace(text(tot), "", 1).strip().lower()
        if n:
            counts[label] = int(n)

    projects = []
    for a in s.select(".gallery-item a.link-to-software[href], .gallery-item a[href*='/software/']"):
        href = a["href"]
        if "/software/built-with/" in href:
            continue
        if href not in projects:
            projects.append(href)
    winners = []
    for item in s.select(".gallery-item"):
        a = item.select_one("a[href*='/software/']")
        if a and item.select_one("img.winner, .winner"):
            winners.append(a["href"])

    return {
        "username": username,
        "name": name or username,
        "bio": bio,
        "location": location,
        "links": links,
        "github": gh,
        "linkedin": li_url,
        "counts": counts,
        "projects": projects,
        "winner_projects": winners,
        "skills": [text(t) for t in s.select(".portfolio-tags .cp-tag")],
    }


def fetch_profile(username: str) -> dict | None:
    r = DEVPOST.get(f"https://devpost.com/{username}")
    if not r.ok:
        return None
    return parse_profile(r.text, username)


def fetch_challenges(username: str) -> list[str]:
    r = DEVPOST.get(f"https://devpost.com/{username}/challenges")
    if not r.ok:
        return []
    s = soup(r.text)
    return [text(h) for h in s.select("h2.title")]


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def window_bounds(win: dict) -> tuple[datetime, datetime]:
    return parse_iso(win["start"]), parse_iso(win["end"])


__all__ = [
    "DEVPOST", "find_hackathon", "search_hackathons", "hackathon_window", "fetch_project", "parse_project",
    "parse_gallery", "fetch_profile", "parse_profile", "fetch_challenges", "repo_slug", "project_slug",
    "norm_title", "window_bounds", "parse_iso",
]
