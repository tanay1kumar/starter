"""Extract the readable parts of design/talent-dex-v3.html.

The design file is a bundled page: the screen markup lives in a JSON-encoded
string inside <script type="__bundler/template">. This writes:
  design/extracted/markup.html   the <x-dc> template (font-face blocks stripped)
  design/extracted/component.js  the `class Component extends DCLogic` logic
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = (ROOT / "design" / "talent-dex-v3.html").read_text(encoding="utf-8")
raw = re.search(r'<script type="__bundler/template">(.*?)</script>', src, re.S).group(1)
template = json.loads(raw)
template = re.sub(r"(/\*[^*]*\*/\s*)?@font-face\s*\{[^}]*\}\s*", "", template)
m = re.search(r'<script type="text/x-dc"[^>]*>(.*?)</script>', template, re.S)
out = ROOT / "design" / "extracted"
out.mkdir(parents=True, exist_ok=True)
(out / "component.js").write_text(m.group(1).strip() + "\n", encoding="utf-8")
(out / "markup.html").write_text(template[: m.start()] + template[m.end():], encoding="utf-8")
print("wrote", out / "markup.html", "and", out / "component.js")
