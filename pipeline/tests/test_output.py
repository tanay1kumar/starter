"""The dataset check that guards data/builders.json."""

import copy
import json

import pytest

from talentdex.config import DATA_DIR
from talentdex.output import validate


def sample():
    return json.loads((DATA_DIR / "sample.json").read_text())


def test_sample_matches_the_ui_contract():
    validate(sample())


@pytest.mark.parametrize("breakage, message", [
    (lambda b: b.update(dex="42"), "dex"),
    (lambda b: b.update(types=["ml", "backend", "frontend"]), "types"),
    (lambda b: b["school"].update(source="LinkedIn"), "unknown source"),
    (lambda b: b["city"].update(value=None), "source without a value"),
    (lambda b: b["ev"].update(ml=300), "ev"),
    (lambda b: b.update(iv=[31, 30, 27, 22, 19]), "iv"),
    (lambda b: b.update(why="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen"), "15 words"),
    (lambda b: b["projects"][0].update(share=140), "share"),
])
def test_broken_builders_are_rejected(breakage, message):
    d = copy.deepcopy(sample())
    breakage(d["builders"][0])
    with pytest.raises(ValueError, match=message):
        validate(d)


def test_real_data_must_count_its_builders():
    d = sample()
    d["source"] = "real"
    with pytest.raises(ValueError, match="buildersFound"):
        validate(d)
    d["scan"]["buildersFound"] = len(d["builders"])
    validate(d)
