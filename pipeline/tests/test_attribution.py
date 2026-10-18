"""Attribution tests.

The synthetic-repo tests run offline. The PlantHopper test reads Devpost and
GitHub once and is served from pipeline/cache/ afterwards.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from talentdex.attribution import (
    SHARED_LAPTOP, Member, attribute, commit_identity, file_share, identity_key, norm_name, resolve_identities,
)
from talentdex.gitrepo import extract_dir

START = datetime.fromisoformat("2025-10-03T20:00:00-04:00")
END = datetime.fromisoformat("2025-10-05T10:00:00-04:00")
PRE = "2025-10-01T12:00:00-04:00"  # before the event


def lines(n: int, word: str = "x") -> str:
    return "".join(f"{word} = {i}\n" for i in range(n))


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=repo, env={**os.environ, **(env or {})}, capture_output=True, text=True, check=True)
    return r.stdout


def ident(spec: dict) -> dict:
    return {
        "GIT_AUTHOR_NAME": spec["name"], "GIT_AUTHOR_EMAIL": spec["email"], "GIT_AUTHOR_DATE": spec["date"],
        "GIT_COMMITTER_NAME": spec["name"], "GIT_COMMITTER_EMAIL": spec["email"], "GIT_COMMITTER_DATE": spec["date"],
    }


def make_repo(root: Path, commits: list[dict]) -> Path:
    """Build a repo where every commit has a chosen author and author date.

    A spec with "run" runs that git command instead (branch, merge, cherry-pick,
    revert), as the spec's author when it names one."""
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "commit.gpgsign", "false")
    for spec in commits:
        if "run" in spec:
            git(repo, *spec["run"], env=ident(spec) if "name" in spec else None)
            continue
        for path, content in spec.get("write", {}).items():
            f = repo / path
            f.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                f.write_bytes(content)
            else:
                f.write_text(content)
        for old, new in spec.get("rename", []):
            (repo / new).parent.mkdir(parents=True, exist_ok=True)
            git(repo, "mv", old, new)
        for path in spec.get("delete", []):
            git(repo, "rm", "-q", path)
        for path, extra in spec.get("append", {}).items():
            with open(repo / path, "a") as fh:
                fh.write(extra)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "--allow-empty", "-m", spec.get("msg", "commit"), env=ident(spec))
    return repo


TEAM = [
    Member("alice-dp", "Alice Wong", github="alicew"),
    Member("bobby", "Bob Singh", github="bsingh", email="bob@example.com"),
    Member("cara-l", "Cara Lopez", github=None),
]


@pytest.fixture
def scenario(tmp_path):
    commits = [
        # Starter template committed weeks before the event.
        {"name": "Template Bot", "email": "bot@example.com", "date": "2025-09-01T12:00:00-04:00",
         "write": {"src/App.js": lines(10, "tpl"), "README.md": "# Starter\nhello\n"}},
        # Before the window: never counted.
        {"name": "Alice Wong", "email": "alice@personal.com", "date": "2025-10-03T19:00:00-04:00",
         "write": {"early.py": lines(100)}},
        # In the window; GitHub links alice@personal.com to the account "alicew".
        {"name": "Alice Wong", "email": "alice@personal.com", "date": "2025-10-03T21:00:00-04:00", "msg": "model",
         "write": {"src/model.py": lines(40), "node_modules/pkg/index.js": lines(100), "package-lock.json": lines(50),
                   ".next/static/chunk.js": lines(30), "dist/out.js": lines(25), "app.min.js": lines(20),
                   "img/logo.png": bytes(range(256)) * 4},
         "append": {"src/App.js": lines(5, "y")}},
        # Exact email match (public email on Bob's GitHub account).
        {"name": "bob", "email": "bob@example.com", "date": "2025-10-04T10:00:00-04:00",
         "write": {"server/api.py": lines(30)}},
        # GitHub noreply address for "bsingh".
        {"name": "b singh", "email": "123456+bsingh@users.noreply.github.com", "date": "2025-10-04T11:00:00-04:00",
         "write": {"server/db.sql": lines(10)}},
        # Same words as a teammate's Devpost name, in another order: name match within the team.
        {"name": "Lopez Cara", "email": "cara@uni.ca", "date": "2025-10-04T12:00:00-04:00",
         "write": {"web/index.html": lines(20)}},
        # Only a first name: not guessed.
        {"name": "Alice", "email": "alice2@other.com", "date": "2025-10-04T13:00:00-04:00",
         "write": {"notes.py": lines(5)}},
        # Renaming a template file keeps it excluded.
        {"name": "Alice Wong", "email": "alice@personal.com", "date": "2025-10-04T14:00:00-04:00",
         "rename": [("src/App.js", "src/Main.js")], "append": {"src/Main.js": lines(2, "z")}},
        # After the event: code commit (kept building) and a README-only commit (not).
        {"name": "bob", "email": "bob@example.com", "date": "2025-10-06T12:00:00-04:00",
         "append": {"server/api.py": lines(3, "w")}},
        {"name": "Lopez Cara", "email": "cara@uni.ca", "date": "2025-10-07T12:00:00-04:00",
         "append": {"README.md": lines(10, "doc") + "".join("More words about the project. " for _ in range(12))}},
    ]
    repo = make_repo(tmp_path, commits)
    ex = extract_dir(repo, "test/scenario")
    shas = {c["ae"]: c["sha"] for c in ex["commits"]}
    logins = {shas["alice@personal.com"]: "alicew"}  # what GitHub's commits API would say
    return ex, attribute(ex, START, END, TEAM, logins)


def test_window_exclusions_and_shares(scenario):
    _, r = scenario
    assert r["people"]["alice-dp"]["lines"] == 40  # model.py only; early.py is before the window
    assert r["people"]["bobby"]["lines"] == 40  # api.py 30 + db.sql 10, post-event lines excluded
    assert r["people"]["cara-l"]["lines"] == 20
    assert r["unknown"]["alice2@other.com"]["lines"] == 5
    assert r["lines_total"] == 105
    assert r["people"]["alice-dp"]["share"] == 38
    assert r["people"]["cara-l"]["share"] == 19
    ex = r["excluded"]
    assert ex["node_modules"] == 100 and ex["lockfile"] == 50
    assert ex["build-output"] == 55  # .next/ and dist/
    assert ex["minified"] == 20
    assert ex["starter-template"] == 7  # App.js +5, then Main.js +2 after the rename
    assert ex["binary"] >= 1
    assert r["template"]["applied"] is True
    assert "src/App.js" not in r["files"] and "src/Main.js" not in r["files"]


def test_identity_mapping_order(scenario):
    _, r = scenario
    ids = r["identities"]
    assert ids["alice@personal.com"] == {**ids["alice@personal.com"], "member": "alice-dp", "method": "github-login"}
    assert ids["bob@example.com"]["method"] == "email" and ids["bob@example.com"]["member"] == "bobby"
    assert ids["123456+bsingh@users.noreply.github.com"]["method"] == "github-noreply"
    assert ids["cara@uni.ca"] == {**ids["cara@uni.ca"], "member": "cara-l", "method": "name-in-team"}
    assert ids["alice2@other.com"]["member"] is None  # "Alice" alone is not enough
    assert ids["bot@example.com"]["member"] is None


def test_kept_building_and_readme(scenario):
    _, r = scenario
    assert r["kept"] == ["bobby"]  # Cara's later commit only touched the README
    assert r["readme"]["author"] == "cara-l"
    assert r["readme"]["chars"] > 300
    assert r["flags"] == []


def test_name_match_never_crosses_teams(tmp_path):
    repo = make_repo(tmp_path, [
        {"name": "Dana Kim", "email": "dana@x.com", "date": "2025-10-04T10:00:00-04:00", "write": {"a.py": lines(10)}},
    ])
    ex = extract_dir(repo, "test/other-team")
    r = attribute(ex, START, END, TEAM)  # Dana is not on this team
    assert r["people"] == {}
    assert r["unknown"]["dana@x.com"]["lines"] == 10


def test_shared_laptop_flag(tmp_path):
    repo = make_repo(tmp_path, [
        {"name": "Alice Wong", "email": "a@x.com", "date": "2025-10-04T10:00:00-04:00", "write": {"a.py": lines(95)}},
        {"name": "Bob Singh", "email": "b@x.com", "date": "2025-10-04T11:00:00-04:00", "write": {"b.py": lines(5)}},
    ])
    ex = extract_dir(repo, "test/laptop")
    assert attribute(ex, START, END, TEAM)["flags"] == [SHARED_LAPTOP]  # 95% with a 3-person team
    assert attribute(ex, START, END, TEAM[:2])["flags"] == []  # 2-person team: no caveat


def test_template_rule_only_when_first_commit_predates_event(tmp_path):
    repo = make_repo(tmp_path, [
        {"name": "Alice Wong", "email": "a@x.com", "date": "2025-10-03T21:00:00-04:00", "write": {"main.py": lines(10)}},
        {"name": "Alice Wong", "email": "a@x.com", "date": "2025-10-04T09:00:00-04:00", "append": {"main.py": lines(4, "q")}},
    ])
    ex = extract_dir(repo, "test/fresh")
    r = attribute(ex, START, END, TEAM)
    assert r["template"]["applied"] is False
    assert r["people"]["alice-dp"]["lines"] == 14


# ---------------------------------------------------------------- review fixes

ANN = {"name": "Ann Lee", "email": "ann@x.com"}
BEN = {"name": "Ben Ode", "email": "ben@x.com"}
CY = {"name": "Cy Park", "email": "cy@x.com"}
TEAM3 = [Member("ann", "Ann Lee", github="ann"), Member("ben", "Ben Ode", github="ben"), Member("cy", "Cy Park", github="cy")]
LOGINS = {"ann@x.com": "ann", "ben@x.com": "ben", "cy@x.com": "cy"}


def run(tmp_path, commits, team=TEAM3, **kw) -> tuple[dict, dict]:
    ex = extract_dir(make_repo(tmp_path, commits), "test/x")
    logins = {c["sha"]: LOGINS.get(c["ae"]) for c in ex["commits"]}
    return ex, attribute(ex, START, END, team, logins, **kw)


def at(hhmm: str, day: int = 4) -> str:
    return f"2025-10-0{day}T{hhmm}:00-04:00"


def test_merge_replay_credits_the_original_author_once(tmp_path):
    """PlantHopper's shape: a merge drops Ann's work, then Ben commits it back."""
    _, r = run(tmp_path, [
        {**ANN, "date": at("21:00", 3), "write": {"main.py": lines(5)}},
        {"run": ["checkout", "-q", "-b", "ben"]},
        {**BEN, "date": at("22:00", 3), "write": {"cv.py": lines(10, "ben")}},
        {"run": ["checkout", "-q", "main"]},
        {**ANN, "date": at("23:00", 3), "write": {"web/page.tsx": lines(100, "ann")}},
        {"run": ["checkout", "-q", "ben"]},
        {**BEN, "date": at("01:00"), "run": ["merge", "-q", "-s", "ours", "--no-edit", "main"]},
        {"run": ["checkout", "main", "--", "web/page.tsx"]},
        {**BEN, "date": at("01:01"), "msg": "merged my code..."},
        {"run": ["checkout", "-q", "main"]},
        {**ANN, "date": at("02:00"), "run": ["merge", "-q", "--no-edit", "ben"]},
    ])
    assert r["files"]["web/page.tsx"] == {"ann": 100}
    assert r["lines_total"] == 115 and r["replayed_lines"] == 100
    assert r["people"]["ben"]["lines"] == 10


def test_revert_and_cherry_pick_credit_nothing_new(tmp_path):
    _, r = run(tmp_path / "revert", [
        {**ANN, "date": at("21:00", 3), "write": {"server.py": lines(120)}},
        {**BEN, "date": at("01:00"), "delete": ["server.py"], "msg": "oops"},
        {**BEN, "date": at("01:05"), "run": ["revert", "--no-edit", "HEAD"]},
    ])
    assert file_share(r, "server.py") == {"ann": 1.0} and "ben" not in r["people"]
    assert r["replayed_lines"] == 120

    _, r = run(tmp_path / "cherry", [
        {**ANN, "date": at("21:00", 3), "write": {"base.py": lines(1)}},
        {"run": ["checkout", "-q", "-b", "feat"]},
        {**ANN, "date": at("22:00", 3), "write": {"api.py": lines(60, "ann")}},
        {"run": ["checkout", "-q", "main"]},
        {**BEN, "date": at("23:00", 3), "write": {"ui.py": lines(60, "ben")}},
        {**BEN, "date": at("00:00"), "run": ["cherry-pick", "feat"]},
        {**BEN, "date": at("01:00"), "run": ["merge", "-q", "--no-edit", "feat"]},
    ])
    assert {u: d["lines"] for u, d in r["people"].items()} == {"ann": 61, "ben": 60}
    assert r["files"]["api.py"] == {"ann": 60}


def test_shared_placeholder_email_is_resolved_per_name(tmp_path):
    team = [Member("ann", "Ann Lee", github="ann"), Member("ben", "Ben Ode", github="ben")]
    _, r = run(tmp_path / "a", [
        {"name": "Ann Lee", "email": "you@example.com", "date": at("21:00", 3), "write": {"a.py": lines(20)}},
        {"name": "Dan Mentor", "email": "you@example.com", "date": at("02:00"), "write": {"infra.py": lines(300)}},
    ], team=team)
    assert r["people"]["ann"]["files"] == {"a.py": 20}  # the mentor's lines never go to Ann
    assert r["identities"]["you@example.com|ann lee"]["member"] == "ann"
    assert r["unknown"]["you@example.com|dan mentor"]["lines"] == 300

    _, r = run(tmp_path / "b", [
        {"name": "Alice Wong", "email": "you@example.com", "date": at("01:00"), "write": {"a.py": lines(30)}},
        {"name": "Bob Singh", "email": "you@example.com", "date": at("02:00"), "write": {"b.py": lines(20)}},
    ], team=TEAM)
    assert {u: d["lines"] for u, d in r["people"].items()} == {"alice-dp": 30, "bobby": 20}
    assert r["unknown"] == {}


def commit(name: str, email: str, sha: str = "s1") -> dict:
    return {"sha": sha, "an": name, "ae": email, "at": 0, "files": []}


def member_of(name: str, team: list[Member], email: str = "x@uni.ca", logins: dict | None = None, extra: list | None = None) -> str | None:
    ids = resolve_identities([commit(name, email), *(extra or [])], logins or {}, team)
    return ids[commit_identity(ids, email, name)]["member"]


def test_one_word_names_and_shared_first_names():
    cara = Member("cara-l", "Cara Lopez")
    # Two Alexes: a bare "Alex" is never given to either of them.
    assert member_of("Alex", [Member("alexchen", "Alex", github="achen"), Member("alexwang", "Alex Wang"), cara]) is None
    assert member_of("Alex", [Member("alex", "Alex Chen"), Member("alexwang", "Alex Wang"), cara]) is None
    assert member_of("Alex Wang", [Member("alex", "Alex Chen"), Member("alexwang", "Alex Wang"), cara]) == "alexwang"
    # One Alex: a one-word name may match a username/login or a one-word display name...
    assert member_of("alex", [Member("alex", "Alex Chen"), cara]) == "alex"
    assert member_of("B-Singh-99", [Member("bobby", "Bob Singh", github="bsingh99"), cara]) == "bobby"
    assert member_of("Alex", [Member("ac", "Alex"), cara]) == "ac"
    # ...but never the first name of a multi-word display name.
    assert member_of("Alex", [Member("ac", "Alex Chen"), cara]) is None
    # Hyphens and emoji don't get in the way of a full name.
    assert member_of("Sean ChanSato", [Member("s1", "Sean Chan-Sato"), cara]) == "s1"
    assert member_of("Alice Wong 🚀", [Member("aw", "Alice Wong"), cara]) == "aw"
    assert member_of("🔥🔥🔥", [Member("aw", "Alice Wong"), cara]) is None


def test_non_latin_names_and_special_letters():
    pairs = [("刘杰", "刘杰"), ("Иван Петров", "Иван Петров"), ("김민준", "김민준"), ("Lukasz Zolw", "Łukasz Żółw"),
             ("Minh Dang", "Minh Đặng"), ("Soren Kierkegaard", "Søren Kierkegaard"), ("Fatma Yildiz", "Fatma Yıldız"),
             ("Jurgen Gross", "Jürgen Groß"), ("Jose Nunez", "José Núñez")]
    for git_name, devpost_name in pairs:
        assert member_of(git_name, [Member("m", devpost_name), Member("bobby", "Bob Singh")]) == "m", git_name
    # A lone first name stays unknown whatever the script of the surname.
    assert member_of("Anna", [Member("annai", "Anna Иванова"), Member("bobby", "Bob Singh")]) is None
    assert norm_name("Łukasz Żółw") == "lukasz zolw" and norm_name("刘杰") == "刘杰"
    # Two people without an email never collapse into one identity.
    assert identity_key("", "刘杰") != identity_key("", "王伟")
    assert identity_key("", "🔥") == "name:🔥"


def test_short_name_on_the_same_email_is_the_same_person(tmp_path):
    """One unlinked laptop email used as "Ann" and as "Ann Lee" over the weekend."""
    team = [Member("annlee", "Ann Lee", github="ann-gh"), Member("bobby", "Bob Singh"), Member("cara-l", "Cara Lopez")]
    _, r = run(tmp_path / "a", [
        {"name": "Ann", "email": "ann@Anns-MacBook.local", "date": at("01:00"), "write": {"a.py": lines(60)}},
        {"name": "Ann Lee", "email": "ann@Anns-MacBook.local", "date": at("02:00"), "write": {"b.py": lines(40)}},
        {"name": "Dan Mentor", "email": "ann@Anns-MacBook.local", "date": at("03:00"), "write": {"c.py": lines(7)}},
    ], team=team)
    assert r["people"]["annlee"]["lines"] == 100
    assert {k: d["lines"] for k, d in r["unknown"].items()} == {"ann@anns-macbook.local|dan mentor": 7}
    # Not when the email's names match two members, nor for a first name two teammates share.
    two = [commit("Alice Wong", "you@example.com"), commit("Bob Singh", "you@example.com", "s2")]
    assert member_of("Alice", TEAM, "you@example.com", extra=two) is None
    alexes = [Member("achen", "Alex Chen"), Member("awang", "Alex Wang"), Member("cara-l", "Cara Lopez")]
    assert member_of("Alex", alexes, "alex@laptop", extra=[commit("Alex Wang", "alex@laptop", "s2")]) is None
    assert member_of("Wang", alexes, "alex@laptop", extra=[commit("Alex Wang", "alex@laptop", "s2")]) == "awang"


def test_git_names_proven_by_github_map_other_emails():
    team = [Member("priya-p", "Priya P.", github="ppatel"), Member("bobby", "Bob Singh"), Member("cara-l", "Cara Lopez")]
    linked = commit("Priya Patel", "priya@gmail.com", "s0")
    assert member_of("Priya Patel", team, "ppatel@mail.utoronto.ca", {"s0": "ppatel"}, [linked]) == "priya-p"
    assert member_of("Priya", team, "ppatel@mail.utoronto.ca", {"s0": "ppatel"}, [linked]) is None
    # The GitHub profile name is a candidate too.
    team = [Member("priya-p", "Priya P.", github="ppatel", gh_name="Priya Patel"), Member("bobby", "Bob Singh")]
    assert member_of("Patel Priya", team) == "priya-p"


def test_readme_author_by_blame(tmp_path):
    cra = "".join(f"Getting Started with Create React App, line {i}: npm start runs the app.\n" for i in range(70))
    ours = "# PlantPal\n" + "".join(f"PlantPal waters your plants; section {i} explains the sensors.\n" for i in range(25))
    # Ann's init commit brought a 70-line boilerplate README; Ben replaced it after the event.
    _, r = run(tmp_path / "a", [
        {**ANN, "date": at("21:00", 3), "write": {"src/App.js": lines(25), "README.md": cra}},
        {**BEN, "date": "2025-10-07T12:00:00-04:00", "write": {"README.md": ours}},
    ])
    assert r["readme"]["author"] == "ben" and r["readme"]["chars"] > 300
    assert set(r["readme"]["by"]) == {"ben"}
    # Lines from a pre-event template root don't count, even when a teammate made that root.
    _, r = run(tmp_path / "b", [
        {**ANN, "date": PRE, "write": {"README.md": cra, "index.js": lines(10)}},
        {**CY, "date": at("12:00"), "append": {"README.md": ours}},
    ])
    assert r["readme"]["author"] == "cy" and "ann" not in r["readme"]["by"]


def test_template_follows_renames_deletes_copies_and_every_root(tmp_path):
    # Renamed away, then a brand-new file at the old path: the new file counts.
    _, r = run(tmp_path / "a", [
        {**ANN, "date": PRE, "write": {"src/App.js": lines(10)}},
        {**ANN, "date": at("21:00", 3), "rename": [("src/App.js", "src/Legacy.js")]},
        {**BEN, "date": at("09:00"), "write": {"src/App.js": lines(50, "ben")}},
    ])
    assert r["files"] == {"src/App.js": {"ben": 50}}
    # Deleted, then rewritten from scratch: counts. Edits to a template file don't.
    _, r = run(tmp_path / "b", [
        {**ANN, "date": PRE, "write": {"src/App.js": lines(10), "src/index.js": lines(3)}},
        {**ANN, "date": at("21:00", 3), "delete": ["src/App.js"], "append": {"src/index.js": lines(2, "a")}},
        {**BEN, "date": at("09:00"), "write": {"src/App.js": lines(50, "ben")}},
    ])
    assert r["files"] == {"src/App.js": {"ben": 50}} and r["excluded"]["starter-template"] == 2
    # An exact copy of a template file is template, but later edits to the copy are the team's.
    _, r = run(tmp_path / "c", [
        {**ANN, "date": PRE, "write": {"pages/index.js": lines(40)}},
        {**BEN, "date": at("09:00"), "write": {"pages/about.js": lines(40)}},
        {**BEN, "date": at("10:00"), "append": {"pages/about.js": lines(30, "b")}},
    ])
    assert r["files"] == {"pages/about.js": {"ben": 30}} and r["excluded"]["starter-template"] == 40
    # A rename chain whose author dates run backwards (a reordering rebase).
    _, r = run(tmp_path / "d", [
        {**ANN, "date": PRE, "write": {"src/App.js": lines(30)}},
        {**ANN, "date": at("09:00"), "rename": [("src/App.js", "src/Home.js")]},
        {**ANN, "date": at("08:00"), "rename": [("src/Home.js", "src/pages/Home.js")]},
        {**BEN, "date": at("10:00"), "append": {"src/pages/Home.js": lines(3, "ben")}},
    ])
    assert r["files"] == {} and r["excluded"]["starter-template"] == 3
    # Two roots before the event (GitHub's README commit + a scaffold), joined later.
    ex, r = run(tmp_path / "e", [
        {**ANN, "date": "2025-09-30T12:00:00-04:00", "write": {"README.md": "# proj\n"}},
        {"run": ["checkout", "-q", "--orphan", "scaffold"]},
        {"run": ["rm", "-rq", "--cached", "."]},
        {"run": ["clean", "-fq"]},
        {**ANN, "date": PRE, "write": {"src/App.js": lines(30), "src/index.js": lines(5)}},
        {"run": ["checkout", "-q", "main"]},
        {**ANN, "date": PRE, "run": ["merge", "-q", "--allow-unrelated-histories", "--no-edit", "scaffold"]},
        {**BEN, "date": at("09:00"), "append": {"src/App.js": lines(20, "ben")}},
    ])
    assert len(ex["roots"]) == 2
    assert r["template"] == {"applied": True, "files": 3, "roots": 2}
    assert r["files"] == {} and r["excluded"]["starter-template"] == 20


def test_copies_of_empty_or_boilerplate_template_files_stay_the_teams(tmp_path):
    # The template has an empty .gitkeep; in the event Ann scaffolds empty files that Ben and Cy fill.
    _, r = run(tmp_path / "empty", [
        {**ANN, "date": PRE, "write": {"README.md": "# hack\n", "data/.gitkeep": ""}},
        {**ANN, "date": at("21:00", 3), "write": {"server/routes.py": "", "server/models.py": "", "web/app.js": ""}},
        {**BEN, "date": at("01:00"), "write": {"server/routes.py": lines(120), "server/models.py": lines(80)}},
        {**CY, "date": at("02:00"), "write": {"web/app.js": lines(90)}},
    ])
    assert {u: d["lines"] for u, d in r["people"].items()} == {"ben": 200, "cy": 90}
    assert r["excluded"].get("starter-template", 0) == 0
    # Django scaffolded before the event; `startapp api` in the event repeats core's boilerplate files.
    boiler = {"models.py": "from django.db import models\n\n# Create your models here.\n",
              "views.py": "from django.shortcuts import render\n\n# Create your views here.\n"}
    _, r = run(tmp_path / "django", [
        {**ANN, "date": PRE, "write": {"manage.py": lines(22), "core/__init__.py": "",
                                       **{f"core/{n}": t for n, t in boiler.items()}}},
        {**ANN, "date": at("21:00", 3), "write": {"api/__init__.py": "", "api/apps.py": "class ApiConfig: name = 'api'\n",
                                                  **{f"api/{n}": t for n, t in boiler.items()}}},
        {**BEN, "date": at("01:00"), "append": {"api/views.py": lines(150, "view")}},
        {**CY, "date": at("02:00"), "append": {"api/models.py": lines(80, "model")}},
    ])
    assert {u: d["lines"] for u, d in r["people"].items()} == {"ann": 1, "ben": 150, "cy": 80}
    assert r["excluded"]["starter-template"] == 6  # the two copied boilerplate files only


def test_template_edits_on_parallel_branches(tmp_path):
    """Ben renames the template App.js on his branch; Cy edits App.js on hers. Cy's lines are
    edits to a template file whichever author date comes first."""
    for ben_at, cy_at in [("10:00", "11:00"), ("11:00", "10:00")]:
        _, r = run(tmp_path / ben_at[:2], [
            {**ANN, "date": PRE, "write": {"src/App.js": lines(25), "src/index.js": lines(17)}},
            {**ANN, "date": at("21:00", 3), "write": {"src/api.js": lines(30, "api")}},
            {"run": ["checkout", "-q", "-b", "ben"]},
            {**BEN, "date": at(ben_at), "rename": [("src/App.js", "src/pages/Home.js")]},
            {"run": ["checkout", "-q", "main"]},
            {"run": ["checkout", "-q", "-b", "cy"]},
            {**CY, "date": at(cy_at), "append": {"src/App.js": lines(100, "cy")}},
            {"run": ["checkout", "-q", "main"]},
            {**ANN, "date": at("12:00"), "run": ["merge", "-q", "--no-ff", "--no-edit", "cy"]},
            {**ANN, "date": at("12:05"), "run": ["merge", "-q", "--no-ff", "--no-edit", "ben"]},
            {**BEN, "date": at("13:00"), "append": {"src/pages/Home.js": lines(5, "ben")}},
        ])
        assert r["files"] == {"src/api.js": {"ann": 30}}, (ben_at, cy_at)
        assert r["excluded"]["starter-template"] == 105, (ben_at, cy_at)


def test_kept_building_rules(tmp_path):
    later = "2025-11-20T12:00:00-05:00"
    _, r = run(tmp_path / "delete", [
        {**ANN, "date": at("09:00"), "write": {"app.py": lines(50), "old.py": lines(20)}},
        {**BEN, "date": later, "delete": ["old.py"]},
    ])
    assert r["kept"] == []
    _, r = run(tmp_path / "rename", [
        {**ANN, "date": at("09:00"), "write": {"app.py": lines(50)}},
        {**CY, "date": later, "rename": [("app.py", "src/app.py")]},
    ])
    assert r["kept"] == []
    # A real feature after the event counts even in a template-path file.
    _, r = run(tmp_path / "template", [
        {**ANN, "date": PRE, "write": {"src/App.js": lines(10)}},
        {**ANN, "date": later, "append": {"src/App.js": lines(80, "later")}},
    ])
    assert r["kept"] == ["ann"]
    # A fix during judging (same day as the deadline) is not "after the event"...
    ex, r = run(tmp_path / "judging", [
        {**ANN, "date": at("09:00"), "write": {"app.py": lines(50)}},
        {**BEN, "date": "2025-10-05T11:30:00-04:00", "append": {"app.py": "fix_demo = True\n"}},
        {"name": "Stranger", "email": "s@x.com", "date": later, "append": {"app.py": lines(5, "s")}},
    ])
    assert r["kept"] == [] and r["window"]["kept_after"] == "2025-10-05T23:59:59-04:00"
    # ...unless the caller says the event ended at the deadline. Unknown authors never count.
    assert attribute(ex, START, END, TEAM3, {c["sha"]: LOGINS.get(c["ae"]) for c in ex["commits"]}, kept_after=END)["kept"] == ["ben"]


PLANTHOPPER_FILE = "Arduino_Files/UniversalControl/UniversalControl.ino"


def test_planthopper_universalcontrol_is_all_pekachoo():
    """Hack the Valley X, 1st place. GitHub user pekachoo wrote every line of
    UniversalControl.ino: 21 of 21 commits all-time, and all 21 fall inside the
    submission window (Oct 3 8:00pm to Oct 5 10:00am EDT), so nothing is lost
    to the window."""
    from talentdex.analyze import analyze_project
    from talentdex.devpost import window_bounds
    from talentdex.gitrepo import extract

    out = analyze_project("plant-hopper", "Hack the Valley X")
    assert out["window"]["source"] == "devpost:details/dates"
    r = out["repos"]["jello-2/PlantHopper"]

    assert file_share(r, PLANTHOPPER_FILE) == {"pekachoo": 1.0}
    assert r["identities"]["jliu6162@gmail.com"]["member"] == "pekachoo"

    ex = extract("jello-2/PlantHopper")
    touching = [c for c in ex["commits"] if any(PLANTHOPPER_FILE in (f[0], f[3]) for f in c["files"])]
    assert len(touching) == 21
    assert {c["an"] for c in touching} == {"pekachoo"}
    start, end = window_bounds(out["window"])
    assert all(start.timestamp() <= c["at"] <= end.timestamp() for c in touching)
