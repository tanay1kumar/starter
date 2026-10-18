"""Score math, exactly as BUILD.md defines it."""

from talentdex.scores import (
    ProjectView, card_types, dex_numbers, evs, iv_raw, percentile_ivs, project_view, signature, trait_counts,
)


def pv(name, lines_by_type, **kw):
    v = ProjectView(slug=name.lower(), name=name, tagline="", url="", event="E", prizes=kw.pop("prizes", []), repos=["o/r"],
                    in_scan=kw.pop("in_scan", True), demo=kw.pop("demo", False), teammates=kw.pop("teammates", []))
    v.analyzed = True
    v.lines_by_type = lines_by_type
    v.lines = sum(lines_by_type.values())
    v.total_lines = kw.pop("total", v.lines)
    for k, val in kw.items():
        setattr(v, k, val)
    return v


def test_ev_formula_and_caps():
    # 6+ projects with code -> maturity 1; one type only -> capped at 252.
    ev, ev_from, code = evs([pv(f"P{i}", {"ml": 100}) for i in range(7)])
    assert code == 7 and ev["ml"] == 252 and sum(ev.values()) == 252
    # 3 projects -> maturity 0.5; shares 75% / 25% -> 191 / 64.
    ev, ev_from, code = evs([pv("A", {"ml": 300}), pv("B", {"backend": 100}), pv("C", {"ml": 0})])
    assert code == 2  # C has no counted lines
    assert ev["ml"] == round(510 * (2 / 6) * 0.75) and ev["backend"] == round(510 * (2 / 6) * 0.25)
    assert ev_from == {"ml": ["A"], "backend": ["B"]}
    # Six projects split evenly across two types -> 255 each, capped at 252 -> "Fully trained" is not reached.
    ev, _, _ = evs([pv(f"P{i}", {"ml": 50, "frontend": 50}) for i in range(6)])
    assert ev["ml"] == 252 and ev["frontend"] == 252


def test_card_types_second_only_at_60_percent():
    assert card_types({"ml": 252, "backend": 168, "frontend": 64, "design": 0, "mobile": 0, "hardware": 0}) == ["ml", "backend"]
    assert card_types({"ml": 230, "backend": 90, "frontend": 0, "design": 0, "mobile": 0, "hardware": 0}) == ["ml"]
    assert card_types({t: 0 for t in ["ml", "backend", "frontend", "design", "mobile", "hardware"]}) == []


def test_percentile_ivs_are_relative_and_ties_share_rank():
    n = {"demo": 1, "own": 1, "mates": 3, "kept": 0, "docs": 0}
    raw = {
        "a": iv_raw({**n, "demo": 4}, wins=2, hacks=4),
        "b": iv_raw({**n, "demo": 2}, wins=2, hacks=8),  # same prizes, fewer per hackathon -> lower
        "c": iv_raw({**n, "demo": 0}, wins=0, hacks=2),
    }
    iv = percentile_ivs(raw)
    assert iv["a"][0] == 31 and iv["b"][0] == 16 and iv["c"][0] == 0  # ships demos
    assert iv["a"][1] == 31 and iv["b"][1] == 16 and iv["c"][1] == 0  # wins with tie-break
    assert iv["a"][3] == iv["b"][3] == iv["c"][3] == 0  # identical teamwork -> nobody is strictly ahead


def test_dex_numbers_are_stable_and_unique():
    a = dex_numbers(["pekachoo", "eu-lee", "austinjian07"])
    b = dex_numbers(["austinjian07", "pekachoo", "eu-lee", "someone-else"])
    assert a["pekachoo"] == b["pekachoo"] and len(a["pekachoo"]) == 4
    assert len(set(b.values())) == 4


def test_project_view_combines_repos_and_finds_owner():
    project = {"slug": "p", "name": "P", "tagline": "t", "url": "u", "repos": ["o/front", "o/back"],
               "submissions": [{"hackathon": "HTV X", "url": "h", "prizes": ["1st Place"]}],
               "members": [{"username": "me"}, {"username": "you"}], "window": {"hackathon": "HTV X"}}
    results = [
        {"repo": "o/front", "lines_total": 100, "people": {"me": {"lines": 30, "files": {"a.tsx": 30}}, "you": {"lines": 70, "files": {}}},
         "unknown": {}, "kept": [], "readme": {"author": "me", "chars": 900, "by": {"me": 900}}, "flags": []},
        {"repo": "o/back", "lines_total": 100, "people": {"me": {"lines": 90, "files": {"api.py": 90}}}, "unknown": {"x@y": {"lines": 10}},
         "kept": ["me"], "readme": None, "flags": []},
    ]
    classes = {"o/front": {"a.tsx": "frontend"}, "o/back": {"api.py": "backend"}}
    v = project_view("me", project, results, classes, demo=True, in_scan=True)
    assert v.lines == 120 and v.total_lines == 200 and v.share == 60
    assert v.lines_by_type == {"frontend": 30, "backend": 90} and v.main_type == "backend"
    assert v.top and v.kept and v.readme and v.prizes == ["1st Place"] and v.teammates == ["you"]
    n = trait_counts([v])
    assert n == {"demo": 1, "own": 1, "mates": 1, "kept": 1, "docs": 1}


def test_signature_prefers_code_then_prizes():
    a = pv("NoCode", {}, prizes=["Best UI"])
    b = pv("Winner", {"ml": 50}, prizes=["1st"])
    c = pv("Big", {"ml": 500})
    assert [p.name for p in signature([a, b, c])] == ["Winner", "Big", "NoCode"]
