"""Which files count as code, and why a file is excluded.

BUILD.md exclusions: build output (.next/ dist/ build/ out/ __pycache__/ *.pyc),
lockfiles, node_modules/, vendored code, binaries, minified files, and starter
template files (handled in attribution.py). On top of that, only source-like
files are counted (docs, data and config are not code), so README lines never
become EVs; READMEs are measured separately for the Documentation trait.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

BUILD_DIRS = {".next", "dist", "build", "out", "__pycache__",
              # same idea for other toolchains
              ".nuxt", ".svelte-kit", ".output", ".expo", ".turbo", ".vercel", ".parcel-cache", "DerivedData", "target"}

LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock",
             "Pipfile.lock", "Gemfile.lock", "composer.lock", "bun.lockb", "bun.lock", "uv.lock",
             "pubspec.lock", "Podfile.lock", "go.sum", "gradle.lockfile", "flake.lock", "packages.lock.json", "npm-shrinkwrap.json"}

VENDOR_DIRS = {"node_modules", "vendor", "vendors", "third_party", "third-party", "thirdparty", "external", "extern",
               "bower_components", "jspm_packages", "Pods", "Carthage", "site-packages", ".venv", "venv", "virtualenv",
               ".tox", ".git", ".yarn", ".pnp", ".gradle", ".dart_tool", ".pub-cache", ".idea", ".vscode",
               ".ipynb_checkpoints", ".pytest_cache", ".mypy_cache", ".cache", "coverage", "xcuserdata"}

# Python virtualenvs committed as env/ (only when they look like one).
VENV_PREFIX = re.compile(r"(^|/)(env|ENV|\.env)/(lib|Lib|bin|Scripts|include|Include)/")

MINIFIED = re.compile(r"(\.min\.(js|mjs|css)|-min\.js|\.bundle\.js|\.chunk\.(js|css)|\.map)$", re.I)
GENERATED = re.compile(r"(\.g\.dart|\.pb\.go|_pb2(_grpc)?\.py|\.generated\.[a-z]+|\.designer\.cs)$", re.I)

CODE_EXTS = {
    # web
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte", ".astro", ".html", ".htm",
    ".css", ".scss", ".sass", ".less", ".styl",
    # python, data science, notebooks
    ".py", ".pyx", ".ipynb", ".r", ".jl",
    # backend and systems
    ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".rb", ".php", ".cs", ".fs", ".ex", ".exs", ".erl",
    ".hs", ".clj", ".lua", ".pl", ".sql", ".prisma", ".graphql", ".gql", ".proto", ".sh", ".bash", ".zsh",
    ".ps1", ".tf", ".sol", ".move", ".cairo", ".zig", ".nim",
    # mobile
    ".swift", ".m", ".mm", ".dart", ".storyboard", ".xib",
    # c / c++ / embedded / hdl / cad
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".ino", ".pde", ".s", ".asm", ".v", ".sv", ".vhd", ".vhdl",
    ".scad", ".kicad_pcb", ".kicad_sch", ".kicad_pro", ".sch", ".brd",
    # design
    ".svg",
    # games / graphics
    ".gd", ".gdshader", ".shader", ".glsl", ".hlsl", ".wgsl",
}
CODE_FILENAMES = {"Dockerfile", "Makefile", "CMakeLists.txt", "Procfile"}

ANDROID_XML = re.compile(r"(^|/)(res/(layout|values|drawable|navigation|menu|xml)[^/]*/[^/]+\.xml|AndroidManifest\.xml)$")
README = re.compile(r"^readme(\.(md|markdown|rst|txt))?$", re.I)


def exclusion_reason(path: str) -> str | None:
    """Why a path is never counted (None when it may count)."""
    p = PurePosixPath(path)
    parts = p.parts
    name = p.name
    if any(seg in VENDOR_DIRS for seg in parts[:-1]) or VENV_PREFIX.search(path):
        return "node_modules" if "node_modules" in parts else "vendored"
    if any(seg in BUILD_DIRS for seg in parts[:-1]) or name.endswith(".pyc"):
        return "build-output"
    if name in LOCKFILES:
        return "lockfile"
    if MINIFIED.search(name):
        return "minified"
    if GENERATED.search(name) or any(seg.endswith((".xcodeproj", ".xcworkspace")) for seg in parts[:-1]):
        return "generated"
    return None


def is_code_path(path: str) -> bool:
    """Source-like file (by name). Docs, data and config are not code."""
    p = PurePosixPath(path)
    if p.name in CODE_FILENAMES:
        return True
    suffix = p.suffix.lower()
    if suffix == ".xml":
        return bool(ANDROID_XML.search(path))
    return suffix in CODE_EXTS


def counted_reason(path: str) -> str | None:
    """None when the file's lines count; otherwise the reason they don't."""
    r = exclusion_reason(path)
    if r:
        return r
    if not is_code_path(path):
        return "not-code"
    return None


def is_readme(path: str) -> bool:
    """A README at the repo root."""
    return "/" not in path and bool(README.match(path))


def looks_minified(lines: int, chars: int, max_line: int) -> bool:
    """Content check for bundles that are not named *.min.js."""
    if lines <= 0:
        return False
    return max_line > 3000 or (lines >= 3 and chars / lines > 250)
