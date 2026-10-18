"""Areas tests: the rules for each type, manifests, and the Gemini step for leftovers.

All offline: gemini.generate_json is replaced by a fake in every test.
"""

from __future__ import annotations

import json
import re

import pytest

from talentdex import classify, gemini
from talentdex.classify import classify_many, classify_repo, repo_context, rule_type

IMPORT_LINE = re.compile(r"^\s*(import |from |#include|require\(|const .*= require\(|using |@import|use )")


def facts(text: str) -> dict:
    """A head_files entry the way gitrepo builds it."""
    lines = text.splitlines()
    return {"lines": len(lines), "chars": len(text), "max_line": max((len(x) for x in lines), default=0),
            "long_lines": 0, "sample": "\n".join(lines[:60])[:4000], "notebook": False,
            "imports": [x.strip()[:200] for x in lines[:400] if IMPORT_LINE.match(x)][:60]}


def extract(files: dict[str, str], manifests: dict[str, str] | None = None, *, version: int = 3,
            history: tuple[str, ...] | list[str] = ()) -> dict:
    """A small extract: files at HEAD (path -> text), manifest texts (v3 only), paths only seen in history."""
    paths = [*files, *(manifests or {}), *history]
    rows = [[p, 1, 0, None, "A", "0" * 40, None, None] if version >= 3 else [p, 1, 0, None] for p in paths]
    ex = {"version": version, "slug": "t/repo", "url": "https://github.com/t/repo", "branch": "main", "head": "f" * 40,
          "commits": [{"sha": "a" * 40, "an": "A", "ae": "a@x.com", "ad": "2025-10-04T00:00:00-04:00",
                       "at": 1759550400, "parents": 0, "files": rows}],
          "roots": [], "head_files": {p: facts(t) for p, t in files.items()}, "readme": None}
    if version >= 3:
        ex["manifests"] = dict(manifests or {})
        ex["layout"] = {"project_roots": [""], "unity_roots": [], "vendored": [], "vendored_globs": [], "generated": []}
    return ex


def rules(ex: dict, paths=None) -> dict[str, str]:
    return classify_repo(ex, list(paths or ex["head_files"]), use_gemini=False)


def pkg(deps: dict, dev: dict | None = None) -> str:
    return json.dumps({"name": "app", "dependencies": deps, "devDependencies": dev or {}})


def payload(prompt: str) -> dict:
    return json.loads(prompt.split("\n\n", 1)[1])


@pytest.fixture(autouse=True)
def fake_gemini(monkeypatch):
    """Every test is offline; a test that expects Gemini sets its own fake."""
    calls: list[tuple[str, dict]] = []

    def fake(prompt, schema, **kw):
        calls.append((prompt, kw))
        return {"files": []}

    monkeypatch.setattr(gemini, "generate_json", fake)
    return calls


# ------------------------------------------------------------------ rules


def test_ml_imports_notebooks_and_paths():
    ex = extract({
        "notebooks/explore.ipynb": "",
        "ml/train.py": "import torch\n",
        "app/llm.py": "from google import genai\n",
        "web/lib/ai.ts": 'import { openai } from "@ai-sdk/openai";\nimport { streamText } from "ai";\n',
        "web/lib/claude.ts": 'import Anthropic from "@anthropic-ai/sdk";\n',
        "vision/detect.py": "import cv2\nimport numpy as np\n",
        "src/models/heads.py": "from .resnet import Block\n",  # models/ in an ML-flavoured repo
        "src/inference.py": "import json\n",
    }, {"requirements.txt": "torch==2.3\nnumpy\n"})
    assert rules(ex) == {p: "ml" for p in ex["head_files"]}


def test_flask_route_calling_openai_is_ml():
    ex = extract({
        "api/routes.py": "from flask import Blueprint, request\nfrom openai import OpenAI\n\nbp = Blueprint('x', __name__)\n",
        "api/health.py": "from flask import Blueprint\n",
    }, {"requirements.txt": "flask\nopenai\n"})
    assert rules(ex) == {"api/routes.py": "ml", "api/health.py": "backend"}


def test_orm_models_are_backend_even_in_an_ml_repo():
    ex = extract({
        "ml/train.py": "import torch\n",
        "app/models.py": "from django.db import models\n\nclass Plant(models.Model):\n    name = models.CharField(max_length=80)\n",
        "api/models/user.py": "from sqlalchemy import Column, Integer\n",
        "api/schemas/models.py": "from pydantic import BaseModel\nfrom typing import Optional\n\nclass Item(BaseModel):\n    name: str\n",
        "server/models/User.js": "const mongoose = require('mongoose');\n",
        "ml/models/heads.py": "from .resnet import Block\n",
    })
    got = rules(ex)
    for p in ("app/models.py", "api/models/user.py", "api/schemas/models.py", "server/models/User.js"):
        assert got[p] == "backend", p
    assert got["ml/models/heads.py"] == "ml"

    # Without ML signals the model/train path rule stays off.
    plain = extract({"app.py": "from flask import Flask\n", "models/user.py": "from dataclasses import dataclass\n",
                     "train_times.py": "import csv\n"})
    got = rules(plain)
    assert got["models/user.py"] == "backend" and got["train_times.py"] == "backend"


def test_expo_project_is_mobile_and_react_web_is_frontend():
    mobile = extract({
        "app/(tabs)/index.tsx": 'import { View, Text } from "react-native";\n',
        "components/Card.tsx": 'import React from "react";\nexport function Card() { return null }\n',
        "lib/format.ts": "export const money = (n: number) => n.toFixed(2);\n",
        "server/index.ts": 'import express from "express";\n',
    }, {"package.json": pkg({"expo": "~51.0.0", "react": "18.2.0", "react-native": "0.74.0"})})
    assert rules(mobile) == {"app/(tabs)/index.tsx": "mobile", "components/Card.tsx": "mobile",
                             "lib/format.ts": "mobile", "server/index.ts": "backend"}
    assert repo_context(mobile)["roots"][""]["kind"] == "expo"

    web = extract({
        "src/App.tsx": 'import React from "react";\n',
        "src/components/Card.tsx": "export function Card() { return <div/> }\n",
        "src/lib/format.ts": "export const money = (n: number) => n.toFixed(2);\n",
        "src/api/client.ts": "export async function getPlants() { return fetch('/api/plants') }\n",
    }, {"package.json": pkg({"react": "18.2.0", "react-dom": "18.2.0"}, {"vite": "5.0.0"})})
    assert rules(web) == {p: "frontend" for p in web["head_files"]}
    assert repo_context(web)["roots"][""]["kind"] == "react"

    # The same api/ path in an Express project is server code.
    api = extract({"src/api/plants.ts": "export const list = () => [];\n"}, {"package.json": pkg({"express": "4.19.0"})})
    assert rules(api) == {"src/api/plants.ts": "backend"}


def test_platformio_cpp_is_hardware():
    ex = extract({
        "src/main.cpp": "#include <vector>\nint main() { return 0; }\n",
        "include/pins.h": "#define LED 2\n",
        "src/motor.cpp": '#include "motor.h"\n',
    }, {"platformio.ini": "[env:esp32dev]\nplatform = espressif32\nframework = arduino\n"
                          "lib_deps =\n  adafruit/Adafruit NeoPixel@^1.12.0\n"})
    assert rules(ex) == {p: "hardware" for p in ex["head_files"]}
    root = repo_context(ex)["roots"][""]
    assert root["kind"] == "platformio" and "Adafruit NeoPixel" in root["deps"]

    # Arduino headers settle it without a manifest; a desktop C++ program does not.
    assert rule_type("fw/blink.cpp", facts("#include <Arduino.h>\n")) == "hardware"
    desktop = extract({"src/solver.cpp": "#include <iostream>\nint main() {}\n"})
    assert rules(desktop) == {}


def test_hardware_python_and_local_modules():
    ex = extract({
        "pi/pump.py": "import RPi.GPIO as GPIO\n",
        "bridge.py": "import serial, time\n",
        "sketch/sketch.ino": "void setup() {}\n",
        "fpga/top.v": "module top(); endmodule\n",
        "pcb/robot.kicad_pcb": "(kicad_pcb)\n",
    })
    assert rules(ex) == {p: "hardware" for p in ex["head_files"]}
    # A chess game's own board.py is not CircuitPython's board module.
    chess = extract({"board.py": "class Board:\n    pass\n", "game.py": "import board\nfrom board import Board\n"})
    assert "game.py" not in rules(chess)


def test_stylesheets_are_design_but_tailwind_entry_is_frontend():
    ex = extract({
        "styles/main.css": ".card { color: #333; padding: 4px; }\n",
        "app/globals.css": "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n"
                           "@layer components {\n  .btn { @apply px-4 py-2 rounded; }\n}\n",
        "src/index.css": '@import "tailwindcss";\n',
        "app/theme.css": '@import "tailwindcss";\n:root {\n  --brand: #e8382b;\n}\n',
        "public/logo.svg": "<svg/>",
        "tailwind.config.ts": "export default { content: [] }\n",
        "src/theme/colors.ts": 'export const colors = { ink: "#2A1715", paper: "#FFF6EE", accent: "#E8382B" };\n',
        "src/components/icons/Leaf.tsx": 'export const Leaf = () => (<svg viewBox="0 0 24 24"><path d="M1 1"/></svg>);\n',
        "src/components/Header.tsx": "export function Header() { return <h1>Hi</h1> }\n",
    }, {"package.json": pkg({"next": "14.2.0", "react": "18.3.0"}, {"tailwindcss": "3.4.0"})})
    got = rules(ex)
    for p in ("styles/main.css", "app/theme.css", "public/logo.svg", "src/theme/colors.ts", "src/components/icons/Leaf.tsx"):
        assert got[p] == "design", p
    for p in ("app/globals.css", "src/index.css", "tailwind.config.ts", "src/components/Header.tsx"):
        assert got[p] == "frontend", p


def test_backend_rules():
    ex = extract({
        "server/index.js": "const express = require('express');\n",
        "app/api/chat/route.ts": 'import { NextResponse } from "next/server";\n',
        "pages/api/hello.ts": "export default function handler(req, res) { res.json({}) }\n",
        "app/actions.ts": '"use server";\nexport async function save() {}\n',
        "db/schema.sql": "create table t (id int);\n",
        "prisma/schema.prisma": "model User {\n  id Int @id\n}\n",
        "Dockerfile": "FROM node:20\n",
        "scripts/deploy.sh": "#!/bin/sh\necho hi\n",
        "svc/main.go": 'package main\n\nimport "net/http"\n',
        "backend/utils.py": "import json\n",
        "api/app.py": "from fastapi import FastAPI\n",
    }, {"package.json": pkg({"next": "14.2.0", "react": "18.3.0"})})
    assert rules(ex) == {p: "backend" for p in ex["head_files"]}


def test_frontend_rules():
    ex = extract({
        "src/components/Button.jsx": "export default function Button() { return <button/> }\n",
        "index.html": "<!doctype html>\n<html></html>\n",
        "views/index.ejs": "<h1><%= title %></h1>\n",
        "static/main.js": "document.getElementById('app').innerHTML = 'hi';\n",
        "src/pages/About.vue": "<template><p/></template>\n",
        "templates/home.jinja": "<h1>{{ title }}</h1>\n",
    })
    assert rules(ex) == {p: "frontend" for p in ex["head_files"]}


def test_mobile_rules():
    ex = extract({
        "ios/App/ContentView.swift": "import SwiftUI\n",
        "lib/main.dart": "import 'package:flutter/material.dart';\n",
        "android/app/src/main/java/com/x/MainActivity.kt": "package com.x\nimport androidx.appcompat.app.AppCompatActivity\n",
        "app/src/main/java/com/y/Helper.java": "package com.y;\npublic class Helper {}\n",
        "app/src/main/res/layout/activity_main.xml": "<LinearLayout/>\n",
        "ios/App/ViewController.m": "#import <UIKit/UIKit.h>\n@implementation ViewController\n@end\n",
    }, history=["app/src/main/AndroidManifest.xml"])
    assert rules(ex) == {p: "mobile" for p in ex["head_files"]}


def test_v2_extract_without_manifests():
    ex = extract({
        "web/app/page.tsx": 'import Link from "next/link";\n',
        "web/lib/format.ts": "export const f = 1;\n",
        "web/app/api/x/route.ts": 'import { NextResponse } from "next/server";\n',
        "fw/fw.ino": "void setup() {}\n",
        "fw/util.h": "#define X 1\n",
        "bot/main.py": "from flask import Flask\n",
        "bot/helpers.py": "import json\n",
    }, version=2, history=["web/package.json", "bot/requirements.txt"])
    assert "manifests" not in ex and len(ex["commits"][0]["files"][0]) == 4
    assert rules(ex) == {"web/app/page.tsx": "frontend", "web/lib/format.ts": "frontend",
                         "web/app/api/x/route.ts": "backend", "fw/fw.ino": "hardware", "fw/util.h": "hardware",
                         "bot/main.py": "backend", "bot/helpers.py": "backend"}
    ctx = repo_context(ex)
    assert ctx["roots"]["web"] == {"deps": [], "kinds": ["next"], "kind": "next"} and ctx["deps"] == []


def test_manifests_parse_tolerantly():
    ex = extract({}, {
        # cut off at 20000 characters: not valid JSON any more
        "package.json": '{"name": "x", "dependencies": {"next": "14.2.0", "react": "18"}, "devDependencies": {"tailwindcss": "3"',
        "api/requirements.txt": "fastapi==0.110\n# comment\n-r base.txt\ngit+https://github.com/x/y.git\nuvicorn[standard]>=0.29\n",
        "ml/pyproject.toml": '[project]\nname = "m"\ndependencies = ["torch>=2", "scikit-learn"]\n',
        "app/pubspec.yaml": "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n  http: ^1.2.0\n",
        "svc/Cargo.toml": '[dependencies]\naxum = "0.7"\n',
        "broken/pyproject.toml": "[project\nnot toml",
    })
    r = repo_context(ex)["roots"]
    assert {"next", "react", "tailwindcss"} <= set(r[""]["deps"]) and r[""]["kind"] == "next"
    assert r["api"]["deps"] == ["fastapi", "uvicorn"] and r["api"]["kind"] == "fastapi"
    assert r["ml"]["deps"] == ["scikit-learn", "torch"] and "ml" in r["ml"]["kinds"]
    assert r["app"]["kind"] == "flutter" and "http" in r["app"]["deps"]
    assert r["svc"]["kind"] == "rust-server"
    assert r["broken"]["deps"] == [] and repo_context(ex)["ml"] is True


def test_renamed_paths_use_the_new_paths_facts():
    ex = extract({"hw/bridge.py": "import serial\n"})
    ex["commits"].append({"sha": "b" * 40, "an": "A", "ae": "a@x.com", "ad": "2025-10-04T01:00:00-04:00", "at": 1759554000,
                          "parents": 1, "files": [["hw/bridge.py", 0, 0, "old/cam.py", "R", "1" * 40, "1" * 40, None]]})
    assert rules(ex, ["old/cam.py"]) == {"old/cam.py": "hardware"}


# ------------------------------------------------------------------ Gemini for leftovers


def test_leftovers_go_to_gemini_in_stable_batches(monkeypatch):
    calls = []

    def fake(prompt, schema, **kw):
        calls.append((prompt, kw))
        return {"files": [{"i": f["i"], "type": "backend"} for f in payload(prompt)["files"]]}

    monkeypatch.setattr(gemini, "generate_json", fake)
    paths = [f"scripts/tool_{i:02d}.py" for i in range(65)]
    ex = extract({p: "import json\n" for p in paths} | {"web/app.css": "a { color: red; }\n"})
    got = classify_repo(ex, [*reversed(paths), "web/app.css"])
    assert got == {p: "backend" for p in paths} | {"web/app.css": "design"}
    assert [len(payload(p)["files"]) for p, _ in calls] == [30, 30, 5]
    assert all(kw["namespace"] == "classify" and kw["temperature"] == 0 and kw["system"] == classify.SYSTEM
               for _, kw in calls)
    assert payload(calls[0][0])["files"][0]["path"] == "scripts/tool_00.py"
    first = [p for p, _ in calls]
    calls.clear()
    classify_repo(ex, paths)
    assert [p for p, _ in calls] == first  # same prompts on a re-run, so the Gemini cache hits


def test_invalid_gemini_answers_are_ignored(monkeypatch):
    answers = [{"files": [{"i": 0, "type": "frontend"}, {"i": 0, "type": "ml"}, {"i": 9, "type": "ml"},
                          {"i": -1, "type": "ml"}, {"i": 1, "type": "gaming"}, {"i": "2", "type": "ml"},
                          {"i": True, "type": "ml"}, {"i": 2.0, "type": "ml"}, "junk", {"type": "ml"}]},
               ["not", "a", "dict"],
               {"files": "nope"}]
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, schema, **kw: answers.pop(0))
    ex = extract({"a.py": "x = 1\n", "b.py": "y = 2\n", "c.py": "z = 3\n"})
    assert classify_repo(ex, ["a.py", "b.py", "c.py"]) == {"a.py": "frontend"}
    assert classify_repo(ex, ["a.py"]) == {}
    assert classify_repo(ex, ["a.py"]) == {}


def test_gemini_errors_leave_files_unclassified(monkeypatch):
    def boom(prompt, schema, **kw):
        raise gemini.GeminiError("Gemini failed after 8 attempts")

    monkeypatch.setattr(gemini, "generate_json", boom)
    ex = extract({"a.py": "x = 1\n", "page.html": "<p/>\n"})
    assert classify_repo(ex, ["a.py", "page.html"]) == {"page.html": "frontend"}


def test_no_gemini_call_when_off_or_nothing_left(fake_gemini):
    ex = extract({"a.py": "x = 1\n", "b.ino": "void setup() {}\n"})
    assert classify_repo(ex, ["a.py", "b.ino"], use_gemini=False) == {"b.ino": "hardware"}
    assert classify_repo(ex, ["b.ino"]) == {"b.ino": "hardware"}
    assert fake_gemini == []


def test_prompt_never_carries_names_emails_urls_or_handles(fake_gemini):
    sample = ("# Author: Quinn Zabrowski\n"
              "# Copyright (c) 2025 zxq-gh\n"
              '"""Helpers written for team Zabrowski."""\n'
              "import requests\n"
              "OWNER = 'quinn@example.com'  # ping @zxqgh or @someoneelse on discord\n"
              "BASE = 'https://zxq-gh.github.io/api'\n"
              "def fetch():\n    return requests.get(BASE)\n")
    ex = extract({"tools/quinn_utils.py": sample}, {"package.json": pkg({"@zxq-gh/ui": "1.0.0", "react": "18.3.0"})})
    classify_repo(ex, ["tools/quinn_utils.py"], private=["Quinn Zabrowski", "zxqgh", "zxq-gh", "quinnz"])
    assert len(fake_gemini) == 1
    prompt, kw = fake_gemini[0]
    text = (prompt + kw["system"]).lower()
    for leak in ("quinn", "zabrowski", "zxq", "example.com", "https://", "github.io", "@someoneelse", "author", "copyright"):
        assert leak not in text, leak
    sent = payload(prompt)
    assert sent["files"][0]["path"] == "tools/[redacted]_utils.py"
    assert "@[redacted]/ui" in sent["dependencies"] and "react" in sent["dependencies"]
    assert "import requests" in sent["files"][0]["head"]


def test_redact_keeps_code_shapes():
    s = ('@app.route("/x")\n'
         'import { Root } from "@radix-ui/react-dialog";\n'
         ".btn { @apply px-4; }\n"
         "  @Override\n"
         "// thanks @jdoe and jane@doe.org, see https://x.dev/a\n")
    out = classify.redact(s, classify._private_re(["Jane Doe"]))
    assert '@app.route("/x")' in out and '"@radix-ui/react-dialog"' in out and "@apply" in out and "@Override" in out
    assert "@jdoe" not in out and "jane@doe.org" not in out and "x.dev" not in out


def test_classify_many_keeps_job_order():
    a = extract({"x.ino": "void setup() {}\n"})
    b = extract({"y.svg": "<svg/>"})
    assert classify_many([(a, ["x.ino"], []), (b, ["y.svg"], ["Some Name"])], workers=2) == [
        {"x.ino": "hardware"}, {"y.svg": "design"}]
