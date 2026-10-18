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

from talentdex.attribution import SHARED_LAPTOP, Member, attribute, file_share, parse_date
from talentdex.gitrepo import extract_dir

START = datetime.fromisoformat("2025-10-03T20:00:00-04:00")
END = datetime.fromisoformat("2025-10-05T10:00:00-04:00")


def lines(n: int, word: str = "x") -> str:
    return "".join(f"{word} = {i}\n" for i in range(n))


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=repo, env={**os.environ, **(env or {})}, capture_output=True, text=True, check=True)
    return r.stdout


def make_repo(root: Path, commits: list[dict]) -> Path:
    """Build a repo where every commit has a chosen author and author date."""
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "commit.gpgsign", "false")
    for spec in commits:
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
        for path, extra in spec.get("append", {}).items():
            with open(repo / path, "a") as fh:
                fh.write(extra)
        git(repo, "add", "-A")
        env = {
            "GIT_AUTHOR_NAME": spec["name"], "GIT_AUTHOR_EMAIL": spec["email"], "GIT_AUTHOR_DATE": spec["date"],
            "GIT_COMMITTER_NAME": spec["name"], "GIT_COMMITTER_EMAIL": spec["email"], "GIT_COMMITTER_DATE": spec["date"],
        }
        git(repo, "commit", "-q", "--allow-empty", "-m", spec.get("msg", "commit"), env=env)
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
         "write": {"src/App.js": lines(10), "README.md": "# Starter\nhello\n"}},
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
    assert all(start <= parse_date(c["ad"]) <= end for c in touching)
