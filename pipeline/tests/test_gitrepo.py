"""Extract (gitrepo.py) and GitHub lookup tests. All offline."""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess

import pytest
from test_attribution import END, START, git, lines, make_repo

from talentdex import github, gitrepo
from talentdex.analyze import window_for
from talentdex.attribution import Member, attribute
from talentdex.gitrepo import RepoSkip, extract_dir
from talentdex.httpcache import Resp

ALICE = {"name": "Alice Wong", "email": "alice@gmail.com"}
BOB = {"name": "Bob Singh", "email": "bob@gmail.com"}
CARA = {"name": "Cara Lopez", "email": "cara@gmail.com"}
TEAM = [Member("alice-dp", "Alice Wong", github="alicew"), Member("bobby", "Bob Singh", github="bsingh"),
        Member("cara-l", "Cara Lopez", github="caral")]
LOGINS = {"alice@gmail.com": "alicew", "bob@gmail.com": "bsingh", "cara@gmail.com": "caral"}
D = "2025-10-04T10:00:00-04:00"
OID = re.compile(r"^[0-9a-f]{40}$")


def run(ex: dict, **kw) -> dict:
    return attribute(ex, START, END, TEAM, {c["sha"]: LOGINS.get(c["ae"]) for c in ex["commits"]}, **kw)


def entry(ex: dict, path: str, n: int = 0) -> list:
    """The n-th file entry for a path across the extract's commits."""
    return [f for c in ex["commits"] for f in c["files"] if f[0] == path][n]


def test_log_parsing_odd_paths_binary_and_renames(tmp_path):
    odd = ["sp ace.py", "ta\tb.py", "new\nline.py", "üñí/çödé 文件.py"]
    repo = make_repo(tmp_path, [
        {**ALICE, "date": D, "write": {**{p: lines(3) for p in odd}, "img.png": bytes(range(256)) * 4, "gone.py": lines(2)}},
        {**BOB, "date": "2025-10-04T11:00:00-04:00", "rename": [("sp ace.py", "dir/sp ace 2.py")],
         "append": {"dir/sp ace 2.py": lines(1, "b")}, "delete": ["gone.py"]},
    ])
    ex = extract_dir(repo, "test/parse")
    first, second = ex["commits"]
    assert first["parents"] == 0 and second["parents"] == 1
    assert first["at"] == 1759586400 and first["ad"] == D
    paths = {f[0]: f for f in first["files"]}
    assert set(paths) == {*odd, "img.png", "gone.py"}
    for p in odd:
        assert paths[p][1:5] == [3, 0, None, "A"] and OID.match(paths[p][5]) and paths[p][6] is None
    assert paths["img.png"][1:3] == [None, None]  # binary
    renamed = {f[0]: f for f in second["files"]}
    assert renamed["dir/sp ace 2.py"][1:5] == [1, 0, "sp ace.py", "R"]
    assert renamed["dir/sp ace 2.py"][6] == paths["sp ace.py"][5]  # pre-image blob
    assert renamed["gone.py"][4] == "D" and renamed["gone.py"][5] is None
    assert set(ex["head_files"]) == {"dir/sp ace 2.py", *odd[1:]}


def test_user_git_config_is_ignored(tmp_path, monkeypatch):
    """log.showSignature, a log encoding and colours in the user's config must not leak into parsing."""
    repo = make_repo(tmp_path, [{"name": "José Núñez", "email": "j@x.com", "date": D, "write": {"a.py": lines(5)}}])
    if shutil.which("ssh-keygen"):  # GitHub signs web commits; signature output used to break the parser
        key = tmp_path / "key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        (repo / "b.py").write_text(lines(7))
        git(repo, "add", "-A")
        git(repo, "-c", "gpg.format=ssh", "-c", f"user.signingkey={key}", "commit", "-q", "-S", "-m", "signed",
            env={"GIT_AUTHOR_NAME": "Bob Singh", "GIT_AUTHOR_EMAIL": "bob@gmail.com", "GIT_AUTHOR_DATE": D,
                 "GIT_COMMITTER_NAME": "Bob Singh", "GIT_COMMITTER_EMAIL": "bob@gmail.com", "GIT_COMMITTER_DATE": D})
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[log]\n\tshowSignature = true\n[i18n]\n\tlogOutputEncoding = ISO-8859-1\n"
                   "[color]\n\tui = always\n[diff]\n\trenames = false\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    ex = extract_dir(repo, "test/config")
    assert all(OID.match(c["sha"]) for c in ex["commits"])
    assert ex["commits"][0]["an"] == "José Núñez" and ex["commits"][0]["files"][0][:2] == ["a.py", 5]
    if shutil.which("ssh-keygen"):
        assert ex["commits"][1]["an"] == "Bob Singh" and ex["commits"][1]["files"][0][:2] == ["b.py", 7]


def test_bad_timezone_offset_keeps_the_repo(tmp_path):
    repo = make_repo(tmp_path, [{**ALICE, "date": D, "write": {"a.py": lines(10)}}])
    for tz in ["+2400", "-9999"]:  # fsck accepts these; %aI prints "+24:00", "-99:99"
        (repo / "b.py").write_text(lines(5, tz[1:]))
        git(repo, "add", "-A")
        tree, parent = git(repo, "write-tree").strip(), git(repo, "rev-parse", "HEAD").strip()
        body = (f"tree {tree}\nparent {parent}\nauthor Bob Singh <bob@gmail.com> 1759590000 {tz}\n"
                f"committer Bob Singh <bob@gmail.com> 1759590000 {tz}\n\nbad tz\n")
        sha = subprocess.run(["git", "hash-object", "-t", "commit", "-w", "--literally", "--stdin"], cwd=repo,
                             input=body, capture_output=True, text=True, check=True).stdout.strip()
        git(repo, "update-ref", "refs/heads/main", sha)
        git(repo, "reset", "-q", "--hard")
    ex = extract_dir(repo, "test/badtz")
    assert [c["at"] for c in ex["commits"][1:]] == [1759590000, 1759590000]
    r = run(ex)
    assert r["people"]["bobby"]["lines"] == 10 and r["people"]["bobby"]["commits"] == 2


def notebook(code: list[str], png: str, nbformat: int = 4) -> str:
    out = [{"output_type": "display_data", "metadata": {}, "data": {"image/png": png, "text/plain": ["<Figure>"]}}]
    cells = [{"cell_type": "markdown", "metadata": {}, "source": ["# Training\n", "Notes\n"]},
             {"cell_type": "code", "execution_count": 1, "metadata": {}, "source": code, "outputs": out}]
    if nbformat == 3:
        for c in cells:
            if c["cell_type"] == "code":
                c["input"] = c.pop("source")
        return json.dumps({"nbformat": 3, "nbformat_minor": 0, "metadata": {}, "worksheets": [{"cells": cells}]}, indent=1)
    return json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}, indent=1) + "\n"


def test_notebooks_count_code_cells_only(tmp_path):
    code = ["import torch\n", "import matplotlib.pyplot as plt\n"] + [f"x{i} = torch.randn(3)\n" for i in range(60)] + ["plt.plot(x0)"]
    png1, png2 = (base64.b64encode(bytes(range(256)) * 40 * k).decode() for k in (1, 2))  # one 13-27 KB line each
    repo = make_repo(tmp_path, [
        {**ALICE, "date": D, "write": {"ml/train.ipynb": notebook(code, png1), "model.py": lines(10),
                                       "old.ipynb": notebook(code[:5], png1, nbformat=3)}},
        {**BOB, "date": "2025-10-04T11:00:00-04:00", "write": {"ml/train.ipynb": notebook(code, png2)}, "msg": "re-run"},
        {**BOB, "date": "2025-10-04T12:00:00-04:00",
         "write": {"ml/train.ipynb": notebook(code + ["\n", "y = 1\n", "z = 2\n"], png2)}},
    ])
    ex = extract_dir(repo, "test/nb")
    assert [entry(ex, "ml/train.ipynb", n)[1:3] for n in range(3)] == [[63, 0], [0, 0], [2, 0]]
    assert entry(ex, "ml/train.ipynb")[7] == "notebook-source"
    assert entry(ex, "old.ipynb")[1] == 5  # nbformat 3 keeps code in "input"
    facts = ex["head_files"]["ml/train.ipynb"]
    assert facts["notebook"] is True and facts["lines"] == 65 and facts["max_line"] < 100
    r = run(ex)
    assert r["files"]["ml/train.ipynb"] == {"alice-dp": 63, "bobby": 2}
    assert r["people"]["alice-dp"]["lines"] == 63 + 10 + 5 and "minified" not in r["excluded"]


def test_notebooks_that_do_not_parse_add_nothing(tmp_path):
    png = base64.b64encode(bytes(range(256)) * 40).decode()
    code = [f"x{i} = torch.randn({i})\n" for i in range(100)]
    good = notebook(code, png)
    log = {"output_type": "stream", "name": "stdout", "text": [f"epoch {i}\n" for i in range(3000)]}
    with_log = json.dumps({**json.loads(good), "cells": [{**json.loads(good)["cells"][1], "outputs": [log]}]}, indent=1)
    conflict = "<<<<<<< HEAD\n" + good + "=======\n" + with_log + "\n>>>>>>> branch\n"
    repo = make_repo(tmp_path, [
        {**ALICE, "date": D, "write": {"ml/train.ipynb": good}},
        {**BOB, "date": "2025-10-04T11:00:00-04:00", "write": {"ml/train.ipynb": conflict}, "msg": "merge, markers committed"},
        {**CARA, "date": "2025-10-04T12:00:00-04:00", "write": {"ml/train.ipynb": notebook(code + ["y = 1\n"] * 10, png)}},
        {**ALICE, "date": "2025-10-04T13:00:00-04:00", "write": {
            "ml/bom.ipynb": "\ufeff" + notebook(code[:40], png), "ml/cut.ipynb": good[: len(good) // 2],
            "ml/odd.ipynb": json.dumps({"cells": None, "worksheets": 5}), "ml/odd3.ipynb": json.dumps({"worksheets": [{"cells": 5}]}),
            "ml/deep.ipynb": "[" * 100000 + "]" * 100000, "app.py": lines(5)}},
    ])
    ex = extract_dir(repo, "test/nb-bad")
    assert [entry(ex, "ml/train.ipynb", n)[1] for n in range(3)] == [100, 0, 10]
    assert entry(ex, "ml/train.ipynb", 1)[7] == "notebook-unparsed"
    assert entry(ex, "ml/bom.ipynb")[1] == 40 and entry(ex, "ml/cut.ipynb")[1] == 0
    assert [entry(ex, p)[1] for p in ("ml/odd.ipynb", "ml/odd3.ipynb", "ml/deep.ipynb")] == [0, 0, 0]
    r = run(ex)
    assert r["files"]["ml/train.ipynb"] == {"alice-dp": 100, "cara-l": 10} and r["capped_lines"] == 0
    assert r["people"]["alice-dp"]["lines"] == 100 + 40 + 5


def test_a_bundle_under_a_licence_header_is_minified_and_prompts_are_not(tmp_path):
    banner = "/*!\n" + "".join(f" * Library v1.{i} | (c) Somebody | MIT license line {i}\n" for i in range(30)) + " */\n"
    bundle = banner + "".join(f"var a{i}=function(e){{return e*{i}}};" for i in range(3000)) + "\n"
    prompts = "".join(f'PROMPT_{i} = "' + "You are a careful plant-care assistant. Answer in JSON only. " * 20 + '"\n'
                      for i in range(6)) + "".join(f"def f{i}():\n    return PROMPT_{i % 6}\n" for i in range(5))
    ex = extract_dir(make_repo(tmp_path, [{**ALICE, "date": D, "write": {"web/lib.js": bundle, "backend/prompts.py": prompts}}]),
                     "test/minified")
    assert ex["head_files"]["web/lib.js"]["long_code"] == 1 and ex["head_files"]["backend/prompts.py"]["long_code"] == 0
    r = run(ex)
    assert r["files"] == {"backend/prompts.py": {"alice-dp": 16}} and r["excluded"]["minified"] == 33


def test_binary_turned_text_counts_its_lines(tmp_path):
    txt = "".join(f"void step{i}() {{ digitalWrite({i % 13}, HIGH); delay({i}); }}\n" for i in range(200))
    repo = make_repo(tmp_path, [
        {**ALICE, "date": "2025-10-03T21:00:00-04:00", "write": {"firmware/robot.ino": txt.encode("utf-16")}},
        {**BOB, "date": "2025-10-04T00:00:00-04:00", "write": {"firmware/robot.ino": txt}, "msg": "re-save as utf-8"},
        {**CARA, "date": "2025-10-04T01:00:00-04:00", "append": {"firmware/robot.ino": "void extra() {}\n" * 10}},
    ])
    ex = extract_dir(repo, "test/bin2text")
    assert entry(ex, "firmware/robot.ino")[1] is None  # UTF-16 is binary to git
    assert entry(ex, "firmware/robot.ino", 1)[1] == 200 and entry(ex, "firmware/robot.ino", 1)[7] == "binary-to-text"
    r = run(ex)
    assert r["files"]["firmware/robot.ino"] == {"bobby": 200, "cara-l": 10}


def test_head_files_are_filtered_before_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(gitrepo, "HEAD_FILES_CAP", 10)
    files = {f"node_modules/p{i}/index.js": f"module.exports = {i}\n" for i in range(30)}
    files["web/app.js"] = "var a=1;" * 900 + "\n"  # a 7,200-character bundle not named *.min.js
    files["web/main.py"] = lines(5)
    ex = extract_dir(make_repo(tmp_path, [{**ALICE, "date": D, "write": files}]), "test/cap")
    assert set(ex["head_files"]) == {"web/app.js", "web/main.py"}
    assert ex["head_files"]["web/app.js"]["long_lines"] == 1
    r = run(ex)
    assert r["files"] == {"web/main.py": {"alice-dp": 5}} and r["excluded"]["minified"] == 1


def test_extract_has_layout_manifests_and_readme_blame(tmp_path):
    repo = make_repo(tmp_path, [
        {**ALICE, "date": D, "write": {"package.json": "{}\n", "web/package.json": '{"name": "web"}\n',
                                       "node_modules/x/package.json": "{}\n", "ml/requirements-dev.txt": "torch\n",
                                       "a/b/c/pyproject.toml": "[project]\n", "app/App.csproj": "<Project/>\n",
                                       "README.md": "# Hi\n" + "Alice wrote this.\n" * 3,
                                       ".mailmap": "Robert S <rob@x.com> <bob@gmail.com>\n"}},  # blame would apply it
        {**BOB, "date": "2025-10-04T11:00:00-04:00", "append": {"README.md": "Bob added this line.\n"}},
    ])
    ex = extract_dir(repo, "test/meta")
    assert list(ex["manifests"]) == ["package.json", "app/App.csproj", "ml/requirements-dev.txt", "web/package.json",
                                     "a/b/c/pyproject.toml"]
    assert "" in ex["layout"]["project_roots"] and "web/" in ex["layout"]["project_roots"]
    rd = ex["readme"]
    assert rd["path"] == "README.md" and rd["chars"] == len("# Hi\n" + "Alice wrote this.\n" * 3 + "Bob added this line.\n")
    assert {(b["an"], b["ae"], b["lines"]) for b in rd["blame"]} == {("Alice Wong", "alice@gmail.com", 4),
                                                                      ("Bob Singh", "bob@gmail.com", 1)}
    assert sum(b["chars"] for b in rd["blame"]) == rd["chars"]


def test_only_permanent_skips_are_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(gitrepo, "GIT_DIR", tmp_path / "git")
    monkeypatch.setattr(gitrepo, "WORK_DIR", tmp_path / "work")
    cache = tmp_path / "git" / "o__r.json"

    monkeypatch.setattr(github, "repo_status", lambda slug: ("temporary", None))  # 403/429/5xx/network
    with pytest.raises(RepoSkip) as e:
        gitrepo.extract("o/r")
    assert e.value.retryable and not cache.exists()

    monkeypatch.setattr(github, "repo_status", lambda slug: ("ok", {"size_kb": 10, "fork": False}))
    real_git = gitrepo._git

    def no_network(args, cwd=None, timeout=600):
        if args[0] == "clone":
            raise RepoSkip("git clone failed: Could not resolve host: github.com", retryable=True)
        return real_git(args, cwd, timeout)

    monkeypatch.setattr(gitrepo, "_git", no_network)
    with pytest.raises(RepoSkip) as e:
        gitrepo.extract("o/r")
    assert e.value.retryable and str(e.value).startswith("clone failed") and not cache.exists()

    monkeypatch.setattr(github, "repo_status", lambda slug: ("missing", None))  # 404/410
    with pytest.raises(RepoSkip) as e:
        gitrepo.extract("o/r")
    assert not e.value.retryable and json.loads(cache.read_text()) == {"version": 3, "slug": "o/r", "skip": "repo not found or private"}
    monkeypatch.setattr(github, "repo_status", lambda slug: pytest.fail("cached skip should not ask GitHub"))
    with pytest.raises(RepoSkip) as e:
        gitrepo.extract("o/r")
    assert not e.value.retryable

    monkeypatch.setattr(github, "repo_status", lambda slug: ("ok", {"size_kb": 400 * 1024, "fork": False}))
    with pytest.raises(RepoSkip) as e:
        gitrepo.extract("o/big")
    assert not e.value.retryable and (tmp_path / "git" / "o__big.json").exists()


def test_repo_status_tells_missing_from_temporary(monkeypatch):
    def answer(status):
        return lambda url, **kw: Resp(url, status, json.dumps({"size": 5, "fork": True, "default_branch": "dev"}))

    for status, want in [(200, "ok"), (404, "missing"), (410, "missing"), (403, "temporary"), (429, "temporary"),
                         (502, "temporary")]:
        monkeypatch.setattr(github.API, "get", answer(status))
        assert github.repo_status("o/r")[0] == want, status

    def boom(url, **kw):
        raise RuntimeError("GET failed after 6 attempts")

    monkeypatch.setattr(github.API, "get", boom)
    assert github.repo_status("o/r") == ("temporary", None) and github.repo_meta("o/r") is None


def test_commit_logins_reach_commits_older_than_the_pages(monkeypatch):
    n = 1150  # newest first: the hackathon commits are the oldest 150
    listed = [{"sha": f"sha{i:05d}", "author": {"login": "ann" if i >= 1000 else "ben"}} for i in range(n)]
    calls = []

    def fake_get(url, params=None, accept=None, **kw):
        calls.append(params)
        if params["sha"] == "main":
            page = params["page"]
            return Resp(url, 200, json.dumps(listed[(page - 1) * 100: page * 100]))
        i = int(params["sha"][3:])
        return Resp(url, 200, json.dumps(listed[i: i + params["per_page"]]))

    monkeypatch.setattr(github.API, "get", fake_get)
    commits = [{"sha": f"sha{i:05d}", "ae": "Ann@x.com" if i >= 1000 else "ben@x.com"} for i in range(n)]
    logins = github.commit_logins("o/r", "main", commits)
    assert logins["sha01100"] == "ann" and logins["sha00000"] == "ben"
    assert len(calls) == 11  # 10 pages, then one lookup for ann@x.com
    assert github.commit_logins("o/r", "main")["sha00999"] == "ben"


def test_login_lookup_errors_are_retried_not_cached(tmp_path, monkeypatch):
    from talentdex import code

    monkeypatch.setattr(code, "ATTR_DIR", tmp_path / "attr")
    ex = extract_dir(make_repo(tmp_path, [{"name": "annie", "email": "ann.personal@x.com", "date": D, "write": {"app.py": lines(100)}},
                                          {**BOB, "date": "2025-10-04T11:00:00-04:00", "write": {"b.py": lines(20)}}]), "o/r")
    monkeypatch.setattr(code, "extract", lambda repo: ex)
    login = {"ann.personal@x.com": "ann-gh", "bob@gmail.com": "bsingh"}
    items = [{"sha": c["sha"], "author": {"login": login[c["ae"]]}} for c in reversed(ex["commits"])]
    team = [Member("ann", "Ann Lee", github="ann-gh"), Member("bobby", "Bob Singh", github="bsingh")]
    window = {"start": START.isoformat(), "end": END.isoformat()}

    def api(status):
        def get(url, params=None, accept=None, **kw):
            if status != 200:
                return Resp(url, status, '{"message": "You have exceeded a secondary rate limit"}')
            return Resp(url, 200, json.dumps(items if params.get("page", 1) == 1 else []))
        return get

    for status in (403, 401, 502):
        monkeypatch.setattr(github.API, "get", api(status))
        with pytest.raises(RuntimeError):
            github.commit_logins("o/r", "main", ex["commits"])
        r = code.analyze_job("p", "o/r", window, team)
        assert r["retryable"] and "login lookup failed" in r["skip"]
        assert not (tmp_path / "attr").exists() or not list((tmp_path / "attr").iterdir())
    monkeypatch.setattr(github.API, "get", api(404))
    assert github.commit_logins("o/r", "main", ex["commits"]) == {c["sha"]: None for c in ex["commits"]}
    monkeypatch.setattr(github.API, "get", api(200))
    r = code.analyze_job("p", "o/r", window, team)
    assert {u: d["lines"] for u, d in r["people"].items()} == {"ann": 100, "bobby": 20}


def test_window_for_never_uses_another_event():
    project = {"slug": "plant-hopper", "submissions": [{"hackathon": "Hack the Valley X", "url": "https://hackthevalley-x.devpost.com/"}]}
    with pytest.raises(ValueError, match="no submission to 'UofTHacks 12'"):
        window_for(project, "UofTHacks 12")
