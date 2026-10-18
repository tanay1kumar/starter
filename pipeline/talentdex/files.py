"""Which files count as code, and why a file is excluded.

BUILD.md excludes build output (.next/ dist/ build/ out/ __pycache__/ *.pyc),
lockfiles, node_modules/, vendored code, binaries, minified files, and starter
template files (handled in attribution.py). How that is decided here:

- Tool folders (node_modules, .next, __pycache__, virtualenvs, Pods, .pio,
  managed_components, cmake-build-*, ...) are excluded at any depth. Generic
  names (dist, build, out, target, vendor, external, coverage, ...) only right
  under a project root: the repo root or a folder with its own manifest. So
  frontend/dist/ is build output while src/app/build/page.tsx is a route.
  lib/ is never excluded as a whole.
- repo_layout() reads the paths at HEAD once and finds those project roots,
  Unity projects, third-party library folders (a library with its own manifest
  or licence under lib/ libs/ libraries/ components/, an Arduino library layout
  under libraries/, Godot addons, a composer or Go vendor/, a committed
  virtualenv, packages installed with `pip install -t` as listed in their
  *.dist-info/RECORD), Lens Studio projects (Cache/, Support/, Workspaces/,
  Packages/ next to a *.esproj), Django collectstatic output (a folder holding
  admin/js/core.js) and .gitattributes linguist-vendored / linguist-generated
  paths. Callers pass it back as `layout`.
- Well-known browser libraries (jquery, three, p5, chart, d3, ...) are vendored
  by file name. Names that are everyday words (chart, anime, matter, ...) are the
  team's own when the HEAD file is short with no licence or version banner. Minified files are caught by name, and by
  content only when long code-like lines dominate (looks_minified), so inline
  images, base64 fonts or long prompt strings never drop a hand-written file.
- Only source-like files count: docs, data and config are not code, so README
  lines never become EVs (READMEs are measured separately for Documentation).
  Templates (ejs, jinja, erb, ...), notebooks and design-token JSON are code.
"""

from __future__ import annotations

import csv
import json
import re
import shlex
from collections.abc import Callable
from functools import lru_cache
from pathlib import PurePosixPath

# Excluded wherever they appear: dependency caches, tool output, editor state.
VENDOR_DIRS = {"node_modules", "bower_components", "jspm_packages", "Pods", "Carthage", "site-packages", ".venv", "venv",
               "virtualenv", ".tox", ".git", ".yarn", ".pnp", ".gradle", ".dart_tool", ".pub-cache", ".build", ".terraform",
               ".pio", ".piolibdeps", "managed_components", ".godot", ".import",
               ".idea", ".vscode", ".vs", ".history", ".ipynb_checkpoints", ".pytest_cache", ".mypy_cache", ".cache", "xcuserdata"}
BUILD_DIRS = {".next", "__pycache__", ".nuxt", ".svelte-kit", ".output", ".expo", ".turbo", ".vercel", ".parcel-cache",
              "DerivedData", ".angular", ".astro", ".docusaurus", ".serverless", ".aws-sam", ".wrangler",
              "_build", "htmlcov", "storybook-static"}  # and cmake-build-*
GENERATED_DIRS = {"typechain-types", "typechain"}
# Generic names, excluded only right under a project root (any case).
ROOT_VENDOR_DIRS = {"vendor", "vendors", "third_party", "third-party", "thirdparty", "external", "extern", "deps"}
ROOT_BUILD_DIRS = {"dist", "build", "out", "target", "coverage", "obj"}
ROOT_DIRS = ROOT_VENDOR_DIRS | ROOT_BUILD_DIRS
# What Unity writes next to Assets/ and ProjectSettings/ (any case).
UNITY_DIRS = {"library", "temp", "obj", "logs", "build", "builds", "usersettings", "memorycaptures"}
# Lens Studio writes these next to the *.esproj; Packages/ holds Snap's asset-library packages.
LENS_BUILD_DIRS = {"cache", "support", "workspaces", "pluginsuserpreferences"}
LENS_VENDOR_DIRS = {"packages"}
LENS_PROJECT = (".esproj", ".lsproj")
# Django's own admin assets: the folder holding them is collectstatic output (STATIC_ROOT).
DJANGO_ADMIN_STATIC = ("admin/js/core.js", "admin/css/base.css")

MANIFESTS = {"package.json", "pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "Cargo.toml", "go.mod", "pom.xml",
             "build.gradle", "build.gradle.kts", "composer.json", "pubspec.yaml", "Podfile", "Package.swift", "platformio.ini",
             "CMakeLists.txt", "Gemfile", "mix.exs", "deno.json", "project.godot"}
MANIFEST_SUFFIXES = (".csproj", ".fsproj", ".sln")

# A folder under lib/ libs/ libraries/ components/ is a third-party library when it has its own
# library manifest or licence. package.json / CMakeLists.txt only say so in a hardware project,
# where <project>/lib/<name>/ is where PlatformIO, Arduino and ESP-IDF libraries live.
LIB_DIRS = {"lib", "libs", "libraries", "components"}
LIB_MARKER = re.compile(r"^(library\.properties|idf_component\.yml|(licen[cs]e|copying)([.-][^/]*)?)$", re.I)
HARDWARE_LIB_MARKERS = {"package.json", "CMakeLists.txt", "component.mk"}
# Common names for a team's own files too, so their content must say "library": Arduino's
# syntax-highlighting list, and a PlatformIO manifest with published-library fields (a private
# library's library.json only sets build flags).
KEYWORDS_TXT = re.compile(r"^\S+\t+(KEYWORD[1-3]|LITERAL[12])\b", re.M)
PUBLISHED_LIB_KEYS = ("repository", "authors", "homepage")
# An Arduino sketchbook library: libraries/<name>/ with src/, examples/ or utility/, in a hardware
# project or holding C/C++ sources.
ARDUINO_LIB_LAYOUT = {"src", "examples", "utility"}
C_SOURCE = re.compile(r"\.(c|cc|cpp|cxx|h|hh|hpp|ino)$", re.I)
HARDWARE = re.compile(r"(\.ino|(^|/)(platformio\.ini|sdkconfig[^/]*|idf_component\.yml|library\.properties"
                      r"|pico_sdk_import\.cmake|[^/]+\.ioc))$")

# Python virtualenvs committed as env/ (only when they look like one).
VENV_PREFIX = re.compile(r"(^|/)(env|ENV|\.env)/(lib|Lib|bin|Scripts|include|Include)/")
# Unity packages imported into Assets/, and Font Awesome kits.
VENDOR_PATH = re.compile(r"(^|/)(Assets/(Plugins|TextMesh Pro|Standard Assets|Samples|Oculus|Photon)|(?i:font-?awesome)[^/]*)/")
# Browser libraries committed as plain files (a subset of GitHub Linguist's vendor.yml). After the
# name only a version or build variant may follow: leaflet-src.js is Leaflet, leaflet-map.js is not.
_VARIANT = r"(?:[.-](?:v?\d[\w.]*|min|slim|esm|es\d*|umd|cjs|module|bundle|global|prod|esm-browser|latest|rtl))*"
_JS_LIBS = (r"three(?:\.(?:core|webgpu|tsl))?|p5(?:\.sound)?|chart|d3|popper(?:-(?:utils|base|lite))?|lodash(?:\.(?:core|fp))?"
            r"|moment(?:-with-locales|-timezone(?:-with-data)?)?|socket\.io|aframe(?:-(?:master|extras))?|phaser|plotly(?:-basic)?"
            r"|highlight(?:\.pack)?|tf|tfjs(?:-[a-z]+)*|ammo(?:\.wasm)?|matter|anime|gsap|alpine(?:js)?|htmx|vue(?:\.runtime)?"
            r"|react(?:-dom)?\.(?:development|production|profiling)|pdf\.worker|html2canvas|jspdf|underscore|require|marked"
            r"|howler(?:\.core)?|pixi|babylon(?:\.max)?|ml5|face-api|dat\.gui|lil-gui|cannon(?:-es)?"
            r"|(?:Orbit|Trackball|PointerLock|Transform|FirstPerson|Fly)Controls|(?:GLTF|OBJ|MTL|FBX|DRACO|RGBE|STL)Loader")
_JS_CSS_LIBS = (r"bootstrap(?:-(?:grid|reboot|utilities|icons))?|leaflet(?:-src)?|prism(?:-[\w-]+)?|swiper(?:-bundle)?"
                r"|materialize|font-?awesome[\w-]*|katex|mapbox-gl|codemirror")
VENDOR_FILE = re.compile(rf"^(?:(?:jquery|modernizr)[^/]*\.(?:[cm]?js|css)|(?:{_JS_LIBS}){_VARIANT}\.[cm]?js"
                         rf"|(?:{_JS_CSS_LIBS}){_VARIANT}\.(?:[cm]?js|css)|(?:normalize|animate){_VARIANT}\.css)$", re.I)
# Some of those names are everyday words: such a file is the team's own (static/js/chart.js drawing
# their charts) when it is short and its first comment lines carry no licence, copyright or version banner.
WORD_LIB_FILE = re.compile(rf"^(?:chart|anime|matter|moment|highlight|marked|popper|prism|swiper|animate){_VARIANT}"
                           rf"\.(?:[cm]?js|css)$", re.I)
OWN_FILE_MAX_LINES = 1000
BANNER = re.compile(r"@license|licen[cs]e|copyright|\(c\)|©|spdx|released under|\bv?\d+\.\d+\.\d+\b", re.I)

LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock",
             "Pipfile.lock", "Gemfile.lock", "composer.lock", "bun.lockb", "bun.lock", "uv.lock",
             "pubspec.lock", "Podfile.lock", "go.sum", "gradle.lockfile", "flake.lock", "packages.lock.json", "npm-shrinkwrap.json"}

MINIFIED = re.compile(r"(\.min\.(js|mjs|css)|-min\.js|\.bundle\.js|\.chunk\.(js|css)|\.map)$", re.I)
GENERATED = re.compile(r"(\.g\.dart|\.g(\.i)?\.cs|\.pb\.go|_pb2(_grpc)?\.py|\.generated\.[a-z]+|\.designer\.cs|^\.pnp\.(c?js|loader\.mjs))$", re.I)
# gitrepo.py counts lines longer than this as a file's "long_lines".
LONG_LINE = 500
# Minified code is dense with these; prose, base64 and URLs are not.
_DROP_CODE_PUNCT = str.maketrans("", "", ";{}()=,:")

CODE_EXTS = {
    # web
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte", ".astro", ".html", ".htm",
    ".css", ".scss", ".sass", ".less", ".styl", ".coffee", ".elm", ".cljs",
    # server-side templates and markup
    ".ejs", ".hbs", ".handlebars", ".pug", ".njk", ".jinja", ".jinja2", ".j2", ".erb", ".twig", ".liquid", ".mdx",
    ".razor", ".cshtml",
    # python, data science, notebooks
    ".py", ".pyx", ".ipynb", ".r", ".jl", ".cu", ".cuh",
    # backend and systems
    ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".rb", ".php", ".cs", ".fs", ".ex", ".exs", ".erl",
    ".hs", ".clj", ".lua", ".luau", ".pl", ".sql", ".prisma", ".graphql", ".gql", ".proto", ".sh", ".bash", ".zsh",
    ".ps1", ".tf", ".sol", ".move", ".cairo", ".zig", ".nim",
    # mobile
    ".swift", ".m", ".mm", ".dart", ".storyboard", ".xib",
    # c / c++ / embedded / hdl / cad
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".ino", ".pde", ".s", ".asm", ".v", ".sv", ".vhd", ".vhdl",
    ".scad", ".kicad_pcb", ".kicad_sch", ".kicad_pro", ".sch", ".brd",
    # design
    ".svg",
    # games / graphics
    ".gd", ".gdshader", ".shader", ".glsl", ".hlsl", ".wgsl", ".frag", ".vert", ".comp", ".geom", ".metal",
}
CODE_FILENAMES = {"Makefile", "CMakeLists.txt", "Procfile"}
DOCKERFILE = re.compile(r"^(?!.*\.dockerignore$)((docker|container)file([.-][\w.-]+)?|[\w.-]+\.(docker|container)file)$", re.I)
BIN_WWW = re.compile(r"(^|/)bin/www$")
# Design tokens are Design work (BUILD.md); other JSON is data or config.
TOKENS_JSON = re.compile(r"(^|/)(tokens|[^/]*\.tokens|design-tokens[^/]*|figma[^/]*tokens[^/]*)\.json$"
                         r"|(^|/)tokens/(.*/)?(?!package\.json$|tsconfig)[^/]+\.json$", re.I)

ANDROID_XML = re.compile(r"(^|/)(res/(layout|values|drawable|navigation|menu|xml)[^/]*/[^/]+\.xml|AndroidManifest\.xml)$")
README = re.compile(r"^readme(\.(md|markdown|rst|txt))?$", re.I)
# A .gitattributes pattern that names one folder: "static/vendor/**", "static/vendor/*", "static/vendor/".
DIR_GLOB = re.compile(r"([^*?\[]+)/\*{0,2}")


def _tool_folder(dirs: list[str]) -> str | None:
    """Reason for a folder that is excluded wherever it appears."""
    if "node_modules" in dirs:
        return "node_modules"
    if any(d in VENDOR_DIRS for d in dirs):
        return "vendored"
    if any(d in BUILD_DIRS or d.startswith("cmake-build-") for d in dirs):
        return "build-output"
    if any(d in GENERATED_DIRS for d in dirs):
        return "generated"
    return None


def _root_folder(dirs: list[str], layout: dict) -> str | None:
    """Reason for a generic folder (dist/, vendor/, Unity's Library/) right under a project root."""
    roots = {"", *layout.get("project_roots", ())}
    unity = set(layout.get("unity_roots", ()))
    lens = set(layout.get("lens_roots", ()))
    prefix = ""
    for d in dirs:
        low = d.lower()
        if prefix in roots and low in ROOT_VENDOR_DIRS:
            return "vendored"
        if prefix in roots and low in ROOT_BUILD_DIRS:
            return "build-output"
        if prefix in unity and low in UNITY_DIRS:
            return "build-output"
        if prefix in lens and low in LENS_BUILD_DIRS:
            return "build-output"
        if prefix in lens and low in LENS_VENDOR_DIRS:
            return "vendored"
        prefix += d + "/"
    return None


@lru_cache(maxsize=1024)
def _glob_re(glob: str) -> re.Pattern:
    """A .gitattributes pattern (anchored at the repo root) as a regex. A pattern that names a
    folder also covers everything inside it, which is what people mean by `vendor/*`."""
    out = []
    for tok in re.split(r"(\*\*/|\*\*|\*|\?|\[[^\]/]+\])", glob.rstrip("/")):
        if tok == "**/":
            out.append("(?:.*/)?")
        elif tok == "**":
            out.append(".*")
        elif tok == "*":
            out.append("[^/]*")
        elif tok == "?":
            out.append("[^/]")
        elif tok.startswith("[") and tok.endswith("]") and len(tok) > 2:
            out.append("[^" + tok[2:-1] + "]" if tok[1] == "!" else tok)
        else:
            out.append(re.escape(tok))
    try:
        return re.compile("".join(out) + "(?:/.*)?")
    except re.error:
        return re.compile("(?!)")


def _glob_hit(path: str, globs: list[str] | None) -> bool:
    return any(_glob_re(g).fullmatch(path) for g in globs or ())


def _linguist_rules(text: str, base: str):
    """(attribute, glob anchored at the repo root) for linguist-vendored / linguist-generated lines
    of a .gitattributes file in folder `base`."""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            pattern, *attrs = shlex.split(line)
        except ValueError:
            continue
        core = re.sub(r"^(\*\*/)+", "", pattern.lstrip("/"))
        if not core.strip("/") or ("/" not in core.rstrip("/") and core.startswith("*")):
            continue  # "*.ipynb linguist-vendored" only hides a language from GitHub's bar; the files are theirs
        anchored = "/" in pattern.rstrip("/")
        glob = base + (pattern.lstrip("/") if anchored else "**/" + pattern)
        for attr in ("linguist-vendored", "linguist-generated"):
            if attr in attrs or f"{attr}=true" in attrs:
                yield attr, glob


def _lib_marker(path: str, name: str, read: Callable[[str], str | None] | None) -> bool:
    """A file that makes its folder under lib/ libs/ libraries/ components/ a third-party library."""
    if LIB_MARKER.match(name):
        return True
    if name not in ("keywords.txt", "library.json") or not read:
        return False
    text = read(path) or ""
    if name == "keywords.txt":
        return bool(KEYWORDS_TXT.search(text))
    try:
        d = json.loads(text)
    except (ValueError, RecursionError):
        return False
    return isinstance(d, dict) and any(k in d for k in PUBLISHED_LIB_KEYS)


def _installed(target: str, dist_info: str, record: str | None) -> set[str]:
    """Prefixes of what `pip install -t target` put there, from the package's RECORD
    (or, unreadable, the distribution name: Foo_Bar-1.0.dist-info -> foo_bar/ and foo_bar.py)."""
    if record is None:
        name = dist_info.rsplit(".dist-info", 1)[0].split("-", 1)[0].lower().replace("-", "_").replace(".", "_")
        return {f"{target}{name}/", f"{target}{name}.py"}
    out = set()
    for row in csv.reader(record.splitlines()):
        p = row[0].strip() if row else ""
        if not p or p.startswith(("/", "..")):
            continue
        first, _, rest = p.partition("/")
        out.add(target + first + ("/" if rest else ""))
    return out


def _own_file(text: str | None) -> bool:
    """A file named like a library (WORD_LIB_FILE) that is the team's own: short, and no licence,
    copyright or version banner in the comments of its first lines."""
    if text is None:
        return False
    lines = text.splitlines()
    if len(lines) > OWN_FILE_MAX_LINES:
        return False
    in_block = False
    for line in lines[:20]:
        s = line.strip()
        if (in_block or s.startswith(("/*", "*", "//", "#", "<!--"))) and BANNER.search(s):
            return False
        if "/*" in s:
            in_block = True
        if "*/" in s:
            in_block = False
    return True


def repo_layout(head_paths: list[str], read: Callable[[str], str | None] | None = None) -> dict:
    """What exclusion_reason() needs to know about the tree at HEAD (JSON-serialisable).

    project_roots   folders holding a manifest, as prefixes ("" = repo root, always present)
    unity_roots     folders holding both Assets/ and ProjectSettings/
    lens_roots      Lens Studio projects: folders holding a *.esproj (or *.lsproj) and Assets/
    vendored        third-party folder prefixes: libraries with their own manifest or licence
                    under lib/ libs/ libraries/ components/, Arduino libraries/<name>/ with
                    src/ examples/ or utility/ (C/C++ or a hardware project), Godot addons with
                    plugin.cfg, a composer/Go vendor/, a committed virtualenv, linguist-vendored folders,
                    and what `pip install -t` put next to a *.dist-info (from its RECORD)
    build_dirs      Django collectstatic output: folders holding admin/js/core.js or admin/css/base.css
                    (just their admin/ when the folder also holds Python files, i.e. it is an app)
    vendored_globs  other .gitattributes linguist-vendored patterns
    generated       .gitattributes linguist-generated patterns
    own_files       files with a library name that is an everyday word (chart.js) that are the
                    team's own (_own_file)
    read(path) returns a file's text or None. Only .gitattributes, keywords.txt and library.json
    under a library folder, *.dist-info/RECORD and WORD_LIB_FILE names are read; without read,
    those files are taken by name alone (library names are vendored, the two markers are not,
    installed packages go by their distribution name).
    """
    roots, vendored, globs, generated, own = {""}, set(), set(), set(), set()
    assets, settings, lens, collected, py_folders = set(), set(), set(), set(), set()
    records = []  # (pip target folder, *.dist-info folder name, RECORD path)
    libs = []  # (library folder, folder holding lib/, has a library manifest or licence)
    arduino: dict[str, bool] = {}  # libraries/<name>/ with an Arduino library layout -> holds C/C++
    hardware = False
    for path in head_paths:
        *dirs, name = path.split("/")
        if _tool_folder(dirs) or (dirs and dirs[0].lower() in ROOT_DIRS):
            continue
        folder = "".join(d + "/" for d in dirs)
        hardware = hardware or bool(HARDWARE.search(path))
        if name in MANIFESTS or name.endswith(MANIFEST_SUFFIXES):
            roots.add(folder)
        if "Assets" in dirs:
            assets.add("".join(d + "/" for d in dirs[:dirs.index("Assets")]))
        if "ProjectSettings" in dirs:
            settings.add("".join(d + "/" for d in dirs[:dirs.index("ProjectSettings")]))
        if name.endswith(LENS_PROJECT):
            lens.add(folder)
        if name == "RECORD" and dirs and dirs[-1].endswith(".dist-info"):
            records.append(("".join(d + "/" for d in dirs[:-1]), dirs[-1], path))
        if len(dirs) >= 3 and dirs[-2] == "admin" and path.endswith(DJANGO_ADMIN_STATIC):
            collected.add("".join(d + "/" for d in dirs[:-2]))
        if name.endswith(".py"):
            py_folders.add(folder)
        if len(dirs) >= 2 and dirs[-2].lower() in LIB_DIRS:
            strong = _lib_marker(path, name, read)
            if strong or name in HARDWARE_LIB_MARKERS:
                libs.append((folder, "".join(d + "/" for d in dirs[:-2]), strong))
        for i, d in enumerate(dirs[:-2]):
            if d.lower() == "libraries" and dirs[i + 2] in ARDUINO_LIB_LAYOUT:
                lib = "".join(x + "/" for x in dirs[:i + 2])
                arduino[lib] = arduino.get(lib, False) or bool(C_SOURCE.search(name))
                break
        if read and WORD_LIB_FILE.match(name) and _own_file(read(path)):
            own.add(path)
        if ((name == "plugin.cfg" and len(dirs) >= 2 and dirs[-2] == "addons")
                or (name in ("autoload.php", "modules.txt") and dirs and dirs[-1] == "vendor")
                or (name == "pyvenv.cfg" and dirs)):
            vendored.add(folder)
        if name == ".gitattributes" and read:
            for attr, glob in _linguist_rules(read(path) or "", folder):
                if attr == "linguist-generated":
                    generated.add(glob)
                elif m := DIR_GLOB.fullmatch(glob):
                    vendored.add(m.group(1) + "/")
                else:
                    globs.add(glob)
    vendored |= {lib for lib, holder, strong in libs if strong or (hardware and holder in roots)}
    vendored |= {lib for lib, c_source in arduino.items() if c_source or hardware}
    for target, dist_info, record in records:
        vendored |= _installed(target, dist_info, read(record) if read else None)
    layout = {"project_roots": sorted(roots), "unity_roots": sorted(assets & settings),
              "lens_roots": sorted(lens & assets), "vendored": sorted(vendored), "vendored_globs": sorted(globs),
              "generated": sorted(generated), "own_files": sorted(own),
              # STATIC_ROOT pointed at an app folder (models.py next to admin/): only Django's admin/ copy goes.
              "build_dirs": sorted(f if f not in py_folders else f + "admin/" for f in collected)}
    # A manifest inside excluded code (frontend/dist/pkg/package.json, a vendored library) is no project root.
    layout["project_roots"] = [r for r in layout["project_roots"] if not r or exclusion_reason(r + "_", layout) is None]
    return layout


def exclusion_reason(path: str, layout: dict | None = None) -> str | None:
    """Why a path is never counted (None when it may count). layout comes from repo_layout();
    without one only the repo root counts as a project root."""
    layout = layout or {}
    *dirs, name = path.split("/")
    r = _tool_folder(dirs) or _root_folder(dirs, layout)
    if r:
        return r
    if (VENV_PREFIX.search(path) or VENDOR_PATH.search(path)
            or (VENDOR_FILE.match(name) and path not in layout.get("own_files", ()))
            or path.startswith(tuple(layout.get("vendored", ()))) or _glob_hit(path, layout.get("vendored_globs"))):
        return "vendored"
    if name.endswith(".pyc") or path.startswith(tuple(layout.get("build_dirs", ()))):
        return "build-output"
    if name in LOCKFILES:
        return "lockfile"
    if MINIFIED.search(name):
        return "minified"
    if (GENERATED.search(name) or any(d.endswith((".xcodeproj", ".xcworkspace")) for d in dirs)
            or _glob_hit(path, layout.get("generated"))):
        return "generated"
    return None


def is_code_path(path: str) -> bool:
    """Source-like file (by name). Docs, data and config are not code."""
    p = PurePosixPath(path)
    if p.name in CODE_FILENAMES or DOCKERFILE.match(p.name) or BIN_WWW.search(path) or TOKENS_JSON.search(path):
        return True
    suffix = p.suffix.lower()
    if suffix == ".xml":
        return bool(ANDROID_XML.search(path))
    return suffix in CODE_EXTS


def counted_reason(path: str, layout: dict | None = None) -> str | None:
    """None when the file's lines count; otherwise the reason they don't."""
    r = exclusion_reason(path, layout)
    if r:
        return r
    if not is_code_path(path):
        return "not-code"
    return None


def is_readme(path: str) -> bool:
    """A README at the repo root."""
    return "/" not in path and bool(README.match(path))


def code_like(line: str) -> bool:
    """A long line that reads like (minified) code or inline data, not prose, base64 or a URL."""
    return len(line) - len(line.translate(_DROP_CODE_PUNCT)) >= len(line) / 10


def looks_minified(facts: dict, path: str = "") -> bool:
    """Content check (a head_files entry) for bundles that are not named *.min.js.

    Long code-like lines must dominate the lines or the text (a bundle under a licence
    header): inline images, base64 fonts and long prompt strings in a hand-written file
    are not minification. Notebooks (an output image is one long line) and SVG exports
    (one long line per path; Design work in BUILD.md) never are.
    """
    if not facts or path.lower().endswith((".ipynb", ".svg")):
        return False
    lines, chars, max_line = facts.get("lines", 0), facts.get("chars", 0), facts.get("max_line", 0)
    if lines <= 0:
        return False
    if "long_code" in facts:
        return facts["long_code"] > lines / 2 or facts.get("long_code_chars", 0) > chars / 2
    # Older extracts can't tell code from prose in long lines.
    if facts.get("long_lines", 0) > lines / 2:
        return True
    if lines <= 5 and max_line > 1000:
        return True
    # Average of the other lines, so a single huge line can't tip it.
    return lines >= 3 and (chars - max_line) / (lines - 1) > 250
