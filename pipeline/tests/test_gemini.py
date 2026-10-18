import json

from talentdex import gemini


def test_cached_only_finds_what_generate_json_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini, "CACHE_DIR", tmp_path)
    schema = {"type": "OBJECT"}
    path = gemini._cache_path("words", gemini._key(gemini.GEMINI_MODEL, "words", "be brief", "hello", schema))
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"response": {"ok": True}}))
    assert gemini.generate_json("hello", schema, namespace="words", system="be brief") == {"ok": True}
    assert gemini.cached_only("words", "hello", schema, system="be brief") == {"ok": True}
    assert gemini.cached_only("words", "hello", schema) is None  # another system prompt is another answer


def test_network_errors_are_retried(tmp_path, monkeypatch):
    import httpx

    monkeypatch.setattr(gemini, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    calls = []

    class Models:
        def generate_content(self, **kw):
            calls.append(kw)
            if len(calls) == 1:
                raise httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known")
            return type("R", (), {"text": '{"ok": true}'})()

    monkeypatch.setattr(gemini, "_get_client", lambda: type("C", (), {"models": Models()})())
    assert gemini.generate_json("hi", {"type": "OBJECT"}, namespace="t") == {"ok": True}
    assert len(calls) == 2
