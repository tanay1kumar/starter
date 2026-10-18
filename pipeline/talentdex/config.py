"""Paths, secrets and tunables for the pipeline."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent
CACHE_DIR = Path(os.environ.get("TALENTDEX_CACHE", PIPELINE_DIR / "cache"))
WORK_DIR = Path(os.environ.get("TALENTDEX_WORK", PIPELINE_DIR / "work"))
DATA_DIR = REPO_ROOT / "data"

# Secrets live in keys.env at the repo root. Never print or log their values.
load_dotenv(REPO_ROOT / "keys.env")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or None
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or None
DATABASE_URL = os.environ.get("DATABASE_URL") or None
PDL_API_KEY = os.environ.get("PDL_API_KEY") or None

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

USER_AGENT = "TalentDex/1.0 (hackathon recruiting research; contact via devpost)"

# Repos bigger than this are not cloned (BUILD.md: skip repos over 300 MB).
MAX_REPO_KB = 300 * 1024

# Hackathon windows are in the organisers' local time when Devpost only gives days.
DEFAULT_TZ = "America/Toronto"
