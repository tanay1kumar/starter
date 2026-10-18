"""files.py: which files count as code, on synthetic path lists (no git, no network)."""

from __future__ import annotations

import json

import pytest

from talentdex.files import LONG_LINE, code_like, counted_reason, is_readme, looks_minified, repo_layout

B64 = "iVBORw0KGgoAAAANSUhEUgAAAoAAAAHgCAYAAAA10dzk" * 1600  # ~70 KB of base64: an inline image or font


def facts(text: str, long_lines: bool = True, code: bool = True) -> dict:
    """A head_files entry, measured like gitrepo.file_facts (long_lines=False or code=False: older
    cached extracts, without those counts)."""
    lines = text.splitlines()
    f = {"lines": len(lines), "chars": len(text), "max_line": max((len(x) for x in lines), default=0)}
    long = [x for x in lines if len(x) > LONG_LINE]
    if long_lines:
        f["long_lines"] = len(long)
    if long_lines and code:
        f["long_code"] = sum(map(code_like, long))
        f["long_code_chars"] = sum(len(x) for x in long if code_like(x))
    return f


def test_layout_shape_is_json():
    layout = repo_layout(["src/app.py"])
    assert layout == {"project_roots": [""], "unity_roots": [], "lens_roots": [], "vendored": [], "vendored_globs": [],
                      "generated": [], "own_files": [], "build_dirs": []}
    assert json.loads(json.dumps(layout)) == layout


# 1. Minified by content: long lines must dominate.

def test_one_long_line_does_not_make_a_file_minified():
    html = ("<html><body>\n" + "".join(f"<p class='row'>Section {i} of the landing page</p>\n" for i in range(200))
            + f'<img src="data:image/png;base64,{B64}">\n</body></html>\n')
    css = "".join(f".c{i} {{ color: red; }}\n" for i in range(150)) + f"@font-face {{ src: url(data:font/woff2;base64,{B64}); }}\n"
    prompt = "You are a helpful hackathon assistant. " * 95  # 3,705 characters
    py = "import os\n" + f'PROMPT = "{prompt}"\n' + "".join(f"def handler_{i}(req):\n    return {i}\n" for i in range(150))
    for path, text in [("public/index.html", html), ("src/styles/brand.css", css), ("backend/main.py", py)]:
        assert not looks_minified(facts(text), path), path
        assert not looks_minified(facts(text, code=False), path), path
        assert not looks_minified(facts(text, long_lines=False), path), path
    # Several long prompts in a short file are prose, not minified code.
    prompts = "".join(f'PROMPT_{i} = "' + "You are a careful plant-care assistant. Answer in JSON only. " * 20 + '"\n'
                      for i in range(6)) + "".join(f"def f{i}():\n    return PROMPT_{i % 6}\n" for i in range(5))
    assert not looks_minified(facts(prompts), "backend/prompts.py")
    assert not looks_minified(facts("".join(f"LINE_{i} = '{'Plain words for the model. ' * 30}'\n" for i in range(9))),
                              "backend/prompts.py")


def test_bundles_are_minified_by_content():
    one_line = "var a=1;" * 900 + "\n"
    many = "".join("!function(e){var t={};" * 200 + "\n" for _ in range(40))
    licence = "/*! For license information please see main.js.LICENSE.txt */\n" + "var a=1;" * 5000 + "\n"
    mostly_long = "".join(("var a={b:1,c:[2,3]};" * 40 if i % 3 else "y = 1") + "\n" for i in range(30))
    banner = "/*!\n" + "".join(f" * Library v1.{i} | (c) Somebody | MIT license line {i}\n" for i in range(30)) + " */\n"
    header = banner + "".join(f"var a{i}=function(e){{return e*{i}}};" for i in range(9000)) + "\n"
    assert looks_minified(facts(one_line), "web/app.js")
    assert looks_minified(facts(many), "src/lib/charts.js")
    assert looks_minified(facts(many, long_lines=False), "static/bundle.js")
    assert looks_minified(facts(licence), "public/main.js")
    assert looks_minified(facts(mostly_long), "src/data.js")
    assert looks_minified(facts(header), "web/lib.js")  # one bundle line under a 32-line licence header
    assert looks_minified(facts("x = 1\n" + "x" * 800 + "\n" + "x" * 800 + "\n", code=False), "src/data.js")


def test_notebooks_and_svg_exports_are_never_minified():
    huge = {"lines": 1, "chars": 50_000, "max_line": 50_000, "long_lines": 1}
    assert looks_minified(huge, "web/app.js")
    assert not looks_minified(huge, "ml/train.ipynb")
    assert not looks_minified(huge, "ml/Train.IPYNB")
    svg = '<svg viewBox="0 0 1440 900">\n' + "".join(f'<path d="{"C1 2 3 4 5 6 " * 150}"/>\n' for _ in range(25)) + "</svg>\n"
    assert not looks_minified(facts(svg), "design/hero-illustration.svg")
    assert not looks_minified({}, "a.js")
    assert not looks_minified({"lines": 0, "chars": 0, "max_line": 0, "long_lines": 0}, "a.js")


@pytest.mark.parametrize("path", ["public/app.min.js", "static/css/site.min.css", "js/vendor-min.js",
                                  "static/js/main.4f3a2.chunk.js", "web/app.bundle.js", "web/app.js.map"])
def test_minified_by_name(path):
    assert counted_reason(path) == "minified"


# 2. Vendored code.

@pytest.mark.parametrize("path, reason", [
    (".pio/libdeps/esp32dev/Adafruit NeoPixel/Adafruit_NeoPixel.cpp", "vendored"),
    ("firmware/.pio/libdeps/esp32/PubSubClient/src/PubSubClient.cpp", "vendored"),
    ("firmware/.piolibdeps/Servo/Servo.cpp", "vendored"),
    ("managed_components/espressif__esp32-camera/driver/cam_hal.c", "vendored"),
    ("robot/managed_components/lvgl__lvgl/src/core/lv_obj.c", "vendored"),
    ("cmake-build-debug/CMakeFiles/3.27.0/CompilerIdC/CMakeCCompilerId.c", "build-output"),
    ("engine/cmake-build-release/gen/shaders.cpp", "build-output"),
    ("contracts/typechain-types/factories/Token__factory.ts", "generated"),
    ("docs/_build/html/_static/doctools.js", "build-output"),
    ("htmlcov/coverage_html.js", "build-output"),
    ("web/storybook-static/main.js", "build-output"),
    ("Assets/Plugins/Firebase/FirebaseApp.cs", "vendored"),
    ("Game/Assets/TextMesh Pro/Scripts/Runtime/TMP_Text.cs", "vendored"),
])
def test_tool_caches_are_excluded_at_any_depth(path, reason):
    assert counted_reason(path) == reason


@pytest.mark.parametrize("path", ["Assets/Scripts/Player.cs", "src/pio/sensor.c", "src/cmake-helpers/find.cpp",
                                  "docs/build.py", "src/build_tools/pack.py", "contracts/Token.sol"])
def test_similar_names_still_count(path):
    assert counted_reason(path) is None


def test_unity_folders_only_next_to_assets_and_project_settings():
    paths = ["Game/Assets/Scripts/Player.cs", "Game/ProjectSettings/ProjectVersion.txt",
             "Game/Library/PackageCache/com.unity.ugui/Runtime/UI/Button.cs", "Game/Temp/Bee/gen.cs",
             "Game/obj/Debug/Assembly.cs", "Game/Logs/shader.cs", "Game/Builds/WebGL/Build/game.loader.js",
             "web/package.json", "web/src/Library/Shelf.tsx"]
    layout = repo_layout(paths)
    assert layout["unity_roots"] == ["Game/"]
    for p in paths[2:7]:
        assert counted_reason(p, layout) == "build-output", p
    assert counted_reason("Game/Assets/Scripts/Player.cs", layout) is None
    assert counted_reason("web/src/Library/Shelf.tsx", layout) is None
    # Without a Unity project these are ordinary folders.
    other = repo_layout(["package.json", "Library/Book.cs", "Temp/convert.py"])
    assert counted_reason("Library/Book.cs", other) is None
    assert counted_reason("Temp/convert.py", other) is None


def test_lens_studio_cache_and_packages_next_to_esproj():
    # jasonnpan/ARchemy committed Lens Studio's Cache/ (compiled TypeScript, 4,778 files).
    paths = ["infinite-craft.esproj", "Assets/Scripts/MergeManager.ts", "Cache/TypeScript/Src/Assets/Scripts/MergeManager.ts",
             "Cache/TypeScript/Out/Assets/Scripts/MergeManager.js", "Support/StudioLib.d.ts",
             "Workspaces/WorkspacesState.yaml", "Packages/SpectaclesInteractionKit.lspkg/Components/Interactable.ts"]
    layout = repo_layout(paths)
    assert layout["lens_roots"] == [""]
    for p in paths[2:5]:
        assert counted_reason(p, layout) == "build-output", p
    assert counted_reason(paths[6], layout) == "vendored"
    assert counted_reason("Assets/Scripts/MergeManager.ts", layout) is None
    # A Visual Studio JavaScript project (.esproj without Assets/) keeps its folders.
    vs = repo_layout(["client/client.esproj", "client/src/support/api.ts", "client/Cache/lru.ts"])
    assert vs["lens_roots"] == []
    assert counted_reason("client/Cache/lru.ts", vs) is None


def test_pip_target_folders_follow_record():
    # JaydenYip3/htv_serverless: `pip install -t lambda` committed twilio, aiohttp, six...
    record_twilio = "twilio/__init__.py,sha256=x,10\ntwilio/rest/client.py,sha256=y,20\ntwilio-9.0.0.dist-info/RECORD,,\n"
    record_six = "six.py,sha256=z,30\nsix-1.16.0.dist-info/METADATA,sha256=w,5\n../../bin/sixer,sha256=v,1\n"
    files = {"lambda/twilio-9.0.0.dist-info/RECORD": record_twilio, "lambda/six-1.16.0.dist-info/RECORD": record_six}
    paths = ["lambda/lambda_function.py", "lambda/twilio/__init__.py", "lambda/twilio/rest/client.py", "lambda/six.py",
             "lambda/sixteen.py", *files]
    layout = repo_layout(paths, files.get)
    assert counted_reason("lambda/twilio/rest/client.py", layout) == "vendored"
    assert counted_reason("lambda/six.py", layout) == "vendored"
    assert counted_reason("lambda/lambda_function.py", layout) is None
    assert counted_reason("lambda/sixteen.py", layout) is None
    assert not any(v.startswith("bin") or ".." in v for v in layout["vendored"])
    # Without the RECORD text, the distribution name stands in.
    blind = repo_layout(paths)
    assert counted_reason("lambda/twilio/rest/client.py", blind) == "vendored"
    assert counted_reason("lambda/six.py", blind) == "vendored"
    assert counted_reason("lambda/lambda_function.py", blind) is None


def test_django_collectstatic_output_is_build_output():
    # ssadras/SafeOStroll committed STATIC_ROOT (Django admin's assets plus copies of their own).
    paths = ["manage.py", "static_cdn/static_root/admin/js/core.js", "static_cdn/static_root/admin/css/base.css",
             "static_cdn/static_root/js/map.js", "Members/static/js/map.js", "frontend/src/App.jsx"]
    layout = repo_layout(paths)
    assert layout["build_dirs"] == ["static_cdn/static_root/"]
    assert counted_reason("static_cdn/static_root/js/map.js", layout) == "build-output"
    assert counted_reason("Members/static/js/map.js", layout) is None
    assert counted_reason("frontend/src/App.jsx", layout) is None
    # manalafzal47/htv_app set STATIC_ROOT to the app folder itself: only Django's admin/ copy goes.
    app = repo_layout(["manage.py", "saveabite/models.py", "saveabite/views.py", "saveabite/admin.py",
                       "saveabite/admin/js/core.js", "saveabite/static/app.js"])
    assert app["build_dirs"] == ["saveabite/admin/"]
    assert counted_reason("saveabite/admin/js/core.js", app) == "build-output"
    assert counted_reason("saveabite/views.py", app) is None
    assert counted_reason("saveabite/admin.py", app) is None
    # admin/ at the repo root never excludes the whole repo.
    assert repo_layout(["admin/js/core.js", "app.py"])["build_dirs"] == []


def test_godot_addons_with_plugin_cfg_are_vendored():
    paths = ["project.godot", "scripts/player.gd", "addons/godot-xr-tools/plugin.cfg",
             "addons/godot-xr-tools/player/player_body.gd", "addons/my_tools/helpers.gd"]
    layout = repo_layout(paths)
    assert counted_reason("addons/godot-xr-tools/player/player_body.gd", layout) == "vendored"
    assert counted_reason("addons/my_tools/helpers.gd", layout) is None  # no plugin.cfg
    assert counted_reason("scripts/player.gd", layout) is None


def test_hardware_library_folders_are_vendored():
    paths = ["firmware/platformio.ini", "firmware/src/main.cpp",
             "firmware/lib/Adafruit_NeoPixel/library.properties", "firmware/lib/Adafruit_NeoPixel/Adafruit_NeoPixel.cpp",
             "firmware/lib/ArduinoJson/library.json", "firmware/lib/ArduinoJson/src/ArduinoJson.h",
             "firmware/lib/u8g2/CMakeLists.txt", "firmware/lib/u8g2/csrc/u8g2_font.c",
             "firmware/lib/Motors/Motors.cpp",  # the team's own private library: no manifest
             "CMakeLists.txt", "main/idf_component.yml", "main/app_main.c",
             "components/esp32-camera/LICENSE", "components/esp32-camera/driver/cam_hal.c",
             "components/lcd/CMakeLists.txt", "components/lcd/lcd.c",
             "sketchbook/libraries/Servo/library.properties", "sketchbook/libraries/Servo/src/Servo.cpp",
             "web/package.json", "web/src/components/Navbar/package.json", "web/src/components/Navbar/Navbar.jsx"]
    arduinojson = '{"name": "ArduinoJson", "version": "7.2.0", "repository": {"type": "git", "url": "https://github.com/bblanchon/ArduinoJson.git"}}'
    layout = repo_layout(paths, {"firmware/lib/ArduinoJson/library.json": arduinojson}.get)
    for p in ["firmware/lib/Adafruit_NeoPixel/Adafruit_NeoPixel.cpp", "firmware/lib/ArduinoJson/src/ArduinoJson.h",
              "firmware/lib/u8g2/csrc/u8g2_font.c", "components/esp32-camera/driver/cam_hal.c", "components/lcd/lcd.c",
              "sketchbook/libraries/Servo/src/Servo.cpp"]:
        assert counted_reason(p, layout) == "vendored", p
    for p in ["firmware/src/main.cpp", "firmware/lib/Motors/Motors.cpp", "main/app_main.c",
              "web/src/components/Navbar/Navbar.jsx"]:  # Navbar's package.json is not under a project root's lib dir
        assert counted_reason(p, layout) is None, p
    assert "firmware/lib/u8g2/" not in layout["project_roots"]  # a manifest inside a vendored library
    assert json.loads(json.dumps(layout)) == layout


def test_library_marker_names_need_library_content():
    web = {
        "package.json": "{}\n",
        "components/SearchBar/SearchBar.tsx": "", "components/SearchBar/keywords.txt": "plant\nwater\n",
        "lib/moderation/filter.ts": "", "lib/moderation/keywords.txt": "badword\n",
        "lib/books/search.ts": "", "lib/books/library.json": '[{"title": "Dune", "authors": ["Frank Herbert"]}]\n',
        "lib/db/package.json": "{}\n", "lib/db/index.ts": "",  # a data library.json must not make this a hardware repo
    }
    layout = repo_layout(list(web), web.get)
    for p in ["components/SearchBar/SearchBar.tsx", "lib/moderation/filter.ts", "lib/books/search.ts", "lib/db/index.ts"]:
        assert counted_reason(p, layout) is None, p
    firmware = {
        "platformio.ini": "[env:esp32]\n", "src/main.cpp": "",
        "lib/MotorDriver/MotorDriver.cpp": "", "lib/MotorDriver/library.json": '{"name": "MotorDriver", "build": {"flags": "-DFOO"}}',
        "lib/OneWire/OneWire.cpp": "", "lib/OneWire/keywords.txt": "OneWire\tKEYWORD1\nreset\tKEYWORD2\n",
        "lib/FastLED/FastLED.cpp": "", "lib/FastLED/library.json": '{"name": "FastLED", "authors": [{"name": "Daniel Garcia"}]}',
    }
    layout = repo_layout(list(firmware), firmware.get)
    assert counted_reason("src/main.cpp", layout) is None
    assert counted_reason("lib/MotorDriver/MotorDriver.cpp", layout) is None  # a private PlatformIO library
    for p in ["lib/OneWire/OneWire.cpp", "lib/FastLED/FastLED.cpp"]:
        assert counted_reason(p, layout) == "vendored", p


def test_arduino_libraries_folder_without_a_manifest():
    servo = ["firmware/libraries/Servo/src/Servo.cpp", "firmware/libraries/Servo/examples/Sweep/Sweep.ino", "firmware/src/main.cpp"]
    layout = repo_layout(servo)
    assert counted_reason("firmware/libraries/Servo/src/Servo.cpp", layout) == "vendored"
    assert counted_reason("firmware/src/main.cpp", layout) is None
    # A web monorepo's own libraries/ folder is not an Arduino library.
    web = repo_layout(["package.json", "libraries/ui-kit/src/Button.tsx", "libraries/ui-kit/package.json"])
    assert counted_reason("libraries/ui-kit/src/Button.tsx", web) is None


def test_own_files_named_like_libraries_count():
    team = "".join(f"export function draw{i}(ctx) {{ ctx.fillRect({i}, 0, 4, 4); }}\n" for i in range(80))
    files = {
        "static/js/chart.js": "// Charts for the dashboard, see https://www.chartjs.org/docs\n" + team,
        "static/js/anime.js": team, "src/matter.js": team, "src/tfjsModel.js": team, "static/js/dashboard.js": team,
        "static/vendor-js/anime.js": "/*\n * anime.js v3.2.1\n * (c) 2020 Julian Garnier\n */\n" + team,
        "lib/chart.js": "/*!\n * Chart.js\n * Released under the MIT License\n */\n" + team,
        "js/chart.umd.js": team * 20,  # no banner, but far too long to be the team's
        "public/js/p5.js": team,  # not an everyday word: the name decides
    }
    layout = repo_layout(list(files), files.get)
    for p in ["static/js/chart.js", "static/js/anime.js", "src/matter.js", "src/tfjsModel.js", "static/js/dashboard.js"]:
        assert counted_reason(p, layout) is None, p
    for p in ["static/vendor-js/anime.js", "lib/chart.js", "js/chart.umd.js", "public/js/p5.js"]:
        assert counted_reason(p, layout) == "vendored", p
    assert counted_reason("static/js/chart.js") == "vendored"  # without the HEAD content, the name decides
    assert counted_reason("src/tfjsModel.js") is None and counted_reason("js/tfjs-backend-webgl.js") == "vendored"


def test_lib_folders_outside_hardware_projects():
    paths = ["package.json", "lib/utils.ts", "lib/db/package.json", "lib/db/index.ts", "src/lib/auth.ts",
             "app/pubspec.yaml", "app/lib/main.dart",
             "CMakeLists.txt", "libs/glfw/LICENSE.md", "libs/glfw/src/window.c",
             "libs/engine/CMakeLists.txt", "libs/engine/renderer.cpp"]
    layout = repo_layout(paths)
    assert counted_reason("libs/glfw/src/window.c", layout) == "vendored"  # ships its own licence
    for p in ["lib/utils.ts", "lib/db/index.ts", "src/lib/auth.ts", "app/lib/main.dart", "libs/engine/renderer.cpp"]:
        assert counted_reason(p, layout) is None, p  # lib/ is never excluded as a whole


@pytest.mark.parametrize("path", [
    "static/libs/jquery-3.7.1.js", "static/js/jquery-ui.css", "static/js/lib/three.module.js", "js/three.js",
    "public/js/p5.js", "public/js/p5.sound.js", "static/Chart.js", "js/chart.umd.js", "js/d3.v7.js", "js/d3.js",
    "css/bootstrap.css", "js/bootstrap.bundle.js", "js/popper.js", "js/lodash.js", "js/moment-with-locales.js",
    "js/socket.io.js", "js/aframe-master.js", "js/phaser.js", "js/plotly-2.27.0.js", "css/leaflet.css", "js/leaflet-src.js",
    "js/highlight.pack.js", "css/prism.css", "js/prism.js", "css/normalize.css", "css/animate.css", "css/font-awesome.css",
    "vendor-css/fontawesome-free-6.5.1-web/css/all.css", "js/materialize.js", "js/tf.js", "js/tfjs-core.js",
    "js/ammo.wasm.js", "js/matter.js", "js/anime.es.js", "js/gsap.js", "css/swiper-bundle.css", "js/alpine.js",
    "js/htmx.js", "js/vue.global.prod.js", "js/vue.esm-browser.js", "js/react.development.js",
    "js/react-dom.development.js", "js/OrbitControls.js", "js/GLTFLoader.js", "public/pdf.worker.mjs",
])
def test_well_known_library_files_are_vendored(path):
    assert counted_reason(path) == "vendored"


@pytest.mark.parametrize("path", [
    "lib/prisma.js", "src/moments.js", "src/utils/normalize.js", "src/animate.js", "src/highlights.js",
    "src/map/leaflet-map.js", "src/game/phaser-game.js", "src/anime/animeList.js", "src/styles/anime.css",
    "public/js/sketch.js", "vue.config.js", "src/three-scene.js", "src/bootstrap-overrides.css",
    "src/components/ammoCounter.js", "src/chartConfig.js", "src/api/axios.js",
])
def test_own_files_with_library_like_names_count(path):
    assert counted_reason(path) is None


def test_committed_virtualenv_with_any_name():
    paths = ["myenv/pyvenv.cfg", "myenv/Scripts/Activate.ps1", "myenv/Lib/site-packages/flask/app.py",
             "app.py", "requirements.txt"]
    layout = repo_layout(paths)
    assert counted_reason("myenv/Scripts/Activate.ps1", layout) == "vendored"
    assert counted_reason("myenv/Lib/site-packages/flask/app.py", layout) == "vendored"
    assert counted_reason("app.py", layout) is None
    # A venv made in the repo root itself must not vendor the whole repo.
    assert counted_reason("app.py", repo_layout(["pyvenv.cfg", "bin/activate", "app.py"])) is None


def test_gitattributes_linguist_vendored_and_generated():
    files = {
        ".gitattributes": "\n".join([
            "# third-party code", "* text=auto", "static/vendor/** linguist-vendored", "public/engine.js linguist-vendored",
            "src/gen/* linguist-generated=true", '"Assets/Third Party/**" linguist-vendored',
            "*.ipynb linguist-vendored", "**/*.html linguist-vendored",  # language-bar tweaks, not third-party code
            "docs/** linguist-documentation", "api/schema.ts -linguist-generated", ""]),
        "web/.gitattributes": "lib/** linguist-vendored\nsdk.js linguist-generated\n",
        "node_modules/x/.gitattributes": "* linguist-vendored\n",
    }
    read_paths = []

    def read(p):
        read_paths.append(p)
        return files.get(p)

    paths = [*files, "static/vendor/chartist/chartist.js", "public/engine.js", "src/gen/api/client.ts",
             "Assets/Third Party/Tween.cs", "web/lib/a.js", "web/sdk.js", "web/src/sdk.js", "ml/train.ipynb",
             "index.html", "docs/demo.js", "api/schema.ts", "lib/a.js", "app/engine.js"]
    layout = repo_layout(paths, read)
    assert sorted(read_paths) == [".gitattributes", "web/.gitattributes"]
    assert json.loads(json.dumps(layout)) == layout
    for p in ["static/vendor/chartist/chartist.js", "public/engine.js", "Assets/Third Party/Tween.cs", "web/lib/a.js"]:
        assert counted_reason(p, layout) == "vendored", p
    for p in ["src/gen/api/client.ts", "web/sdk.js", "web/src/sdk.js"]:
        assert counted_reason(p, layout) == "generated", p
    for p in ["ml/train.ipynb", "index.html", "docs/demo.js", "api/schema.ts", "lib/a.js", "app/engine.js"]:
        assert counted_reason(p, layout) is None, p
    assert counted_reason("static/vendor/chartist/chartist.js") is None  # the rule comes from the layout


# 3. Folder names: tool folders at any depth, generic names only at a project root.

@pytest.mark.parametrize("path, reason", [
    ("packages/web/node_modules/react/index.js", "node_modules"),
    ("apps/site/.next/server/app/page.js", "build-output"),
    ("web/.nuxt/components.d.ts", "build-output"),
    ("frontend/.svelte-kit/generated/root.js", "build-output"),
    ("api/__pycache__/main.py", "build-output"),
    ("backend/venv/lib/python3.11/site-packages/flask/app.py", "vendored"),
    ("server/.venv/bin/activate.py", "vendored"),
    ("tools/virtualenv/run.py", "vendored"),
    ("ml/site-packages/torch/nn.py", "vendored"),
    ("web/bower_components/jq/dist/jq.js", "vendored"),
    ("mobile/ios/Pods/Alamofire/Source/AF.swift", "vendored"),
    ("app/.dart_tool/flutter_build/main.dart", "vendored"),
    ("android/.gradle/8.0/Gen.java", "vendored"),
    ("ios/DerivedData/Build/Gen.swift", "build-output"),
    ("mobile/.expo/web/cache.js", "build-output"),
    ("web/.turbo/cache.js", "build-output"),
    ("web/.vercel/output/functions/index.js", "build-output"),
    ("web/.parcel-cache/x.js", "build-output"),
    ("site/.output/server/index.mjs", "build-output"),
    ("app/.idea/scratch.py", "vendored"),
    ("app/.history/src/App_20251004123456.js", "vendored"),
])
def test_tool_folders_at_any_depth(path, reason):
    assert counted_reason(path, repo_layout(["package.json", path])) == reason


@pytest.mark.parametrize("path", [
    "app/vendor/page.tsx", "app/vendor/dashboard/page.tsx", "src/pages/vendor/Dashboard.jsx",
    "src/components/vendors/VendorCard.jsx", "src/app/build/page.tsx", "src/components/build/PcBuilder.tsx",
    "src/target/Target.ts", "lib/external/stripe.ts", "backend/services/external/openai_client.py",
    "app/coverage/page.tsx", "app/out/page.tsx", "src/extern/api.ts", "src/dist/format.ts",
])
def test_generic_folder_names_below_a_project_root_count(path):
    layout = repo_layout(["package.json", "backend/requirements.txt", path])
    assert counted_reason(path, layout) is None
    assert counted_reason(path) is None


def test_generic_folder_names_at_a_project_root_are_excluded():
    paths = ["package.json", "build/index.js", "dist/app.js", "out/index.html", "coverage/lcov-report/prettify.js",
             "vendor/lib.php", "third_party/glad/glad.c", "external/imgui/imgui.cpp", "Target/release/build.rs",
             "frontend/package.json", "frontend/dist/assets/index-4f3a.js", "frontend/src/App.tsx",
             "android/app/build.gradle", "android/app/build/generated/source/BuildConfig.java",
             "android/app/src/main/java/MainActivity.java", "server/pom.xml", "server/target/classes/App.java",
             "docs/dist/demo.js"]
    layout = repo_layout(paths)
    assert layout["project_roots"] == ["", "android/app/", "frontend/", "server/"]
    expected = {"build/index.js": "build-output", "dist/app.js": "build-output", "out/index.html": "build-output",
                "coverage/lcov-report/prettify.js": "build-output", "vendor/lib.php": "vendored",
                "third_party/glad/glad.c": "vendored", "external/imgui/imgui.cpp": "vendored",
                "Target/release/build.rs": "build-output", "frontend/dist/assets/index-4f3a.js": "build-output",
                "android/app/build/generated/source/BuildConfig.java": "build-output",
                "server/target/classes/App.java": "build-output"}
    for p, reason in expected.items():
        assert counted_reason(p, layout) == reason, p
    for p in ["frontend/src/App.tsx", "android/app/src/main/java/MainActivity.java", "docs/dist/demo.js"]:
        assert counted_reason(p, layout) is None, p
    # Without a layout only the repo root is a project root.
    assert counted_reason("build/index.js") == "build-output"
    assert counted_reason("frontend/dist/assets/index-4f3a.js") is None


def test_manifests_inside_excluded_folders_are_not_project_roots():
    paths = ["package.json", *[f"node_modules/p{i}/package.json" for i in range(50)], "vendor/acme/x/composer.json",
             "frontend/package.json", "frontend/dist/pkg/package.json", "frontend/dist/pkg/build/x.js"]
    layout = repo_layout(paths)
    assert layout["project_roots"] == ["", "frontend/"]
    assert counted_reason("frontend/dist/pkg/build/x.js", layout) == "build-output"


def test_vendor_folder_with_dependency_markers():
    paths = ["web/package.json", "web/app/vendor/page.tsx",
             "api/php/vendor/autoload.php", "api/php/vendor/guzzlehttp/guzzle/src/Client.php", "api/php/index.php",
             "svc/go/vendor/modules.txt", "svc/go/vendor/github.com/gin-gonic/gin/gin.go", "svc/go/main.go"]
    layout = repo_layout(paths)
    assert counted_reason("api/php/vendor/guzzlehttp/guzzle/src/Client.php", layout) == "vendored"
    assert counted_reason("svc/go/vendor/github.com/gin-gonic/gin/gin.go", layout) == "vendored"
    for p in ["web/app/vendor/page.tsx", "api/php/index.php", "svc/go/main.go"]:
        assert counted_reason(p, layout) is None, p


# 4. What counts as code.

@pytest.mark.parametrize("path", [
    "views/index.ejs", "views/layouts/main.hbs", "templates/email.handlebars", "views/home.pug", "templates/base.njk",
    "templates/base.jinja", "templates/base.jinja2", "templates/page.j2", "app/views/users/show.html.erb",
    "templates/page.twig", "sections/header.liquid", "content/blog/post.mdx", "Components/Counter.razor",
    "Pages/Index.cshtml", "src/server.mts", "src/config.cts",
    "design/tokens.json", "src/styles/colors.tokens.json", "design-tokens.json", "design-tokens.dark.json",
    "figma-tokens.json", "tokens/color/base.json",
    "Dockerfile", "Dockerfile.dev", "docker/Dockerfile.prod", "web.Dockerfile", "bin/www", "api/bin/www",
    "ml/train.ipynb", "src/App.vue", "lib/main.dart", "shaders/water.frag", "design/logo.svg",
])
def test_code_files_count(path):
    assert counted_reason(path) is None


@pytest.mark.parametrize("path", [
    "README.md", "docs/setup.md", "requirements.txt", "package.json", "tsconfig.json", "data/users.json",
    "figma/export/frame.json", "tokens/package.json", ".github/workflows/deploy.yml", "k8s/deployment.yaml",
    "docker-compose.yml", ".dockerignore", "Dockerfile.dockerignore", "data/train.csv", "bin/setup", "notes.txt",
    "android/app/build.gradle",
])
def test_docs_data_and_config_are_not_code(path):
    assert counted_reason(path) == "not-code"


def test_is_readme_is_root_only():
    assert is_readme("README.md") and is_readme("readme.rst") and is_readme("README")
    assert not is_readme("docs/README.md") and not is_readme("README-old.md")
