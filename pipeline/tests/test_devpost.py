from talentdex.devpost import parse_project

PAGE = """<html><body>
<div id="software-header"><h1 id="app-title">Plant Hopper</h1><p class="large">Water each plant on its own schedule</p></div>
<div id="app-details-left">
  <div id="gallery"><ul><li><p>Our 5 plant setup</p></li></ul></div>
  <div><h2>Inspiration</h2><p>Sprinklers waste   water.</p><h2>What it does</h2><p>Computer vision finds each plant.</p></div>
  <div id="built-with"><h2>Built With</h2><ul><li><span class="cp-tag">arduino</span></li></ul></div>
  <nav class="app-links section"><a href="https://github.com/jello-2/PlantHopper">github.com</a></nav>
</div>
</body></html>"""


def test_story_is_the_write_up_only():
    p = parse_project(PAGE, "https://devpost.com/software/plant-hopper")
    assert p["story"] == "Inspiration\nSprinklers waste water.\n\nWhat it does\nComputer vision finds each plant."
    assert p["built_with"] == ["arduino"]
    assert p["story_chars"] > len(p["story"])  # the whole section, gallery and links included


def test_no_story_section():
    p = parse_project("<html><body><h1 id='app-title'>X</h1></body></html>", "https://devpost.com/software/x")
    assert p["story"] == "" and p["story_chars"] == 0
