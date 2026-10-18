"""Gemini (Flash) JSON calls: cached, at most 8 at a time, backoff on 429, 5xx and network errors.

Every response is cached by (model, namespace, prompt, schema), so a re-run
costs nothing and the demo never calls Gemini live. Callers must keep names,
schools and photos out of scoring and classification prompts.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .config import CACHE_DIR, GEMINI_API_KEY, GEMINI_MODEL

CONCURRENCY = 8
TIMEOUT_MS = 90_000
_sem = threading.BoundedSemaphore(CONCURRENCY)
_client = None
_client_lock = threading.Lock()
stats = {"calls": 0, "cached": 0, "retries": 0}


class GeminiError(RuntimeError):
    pass


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            if not GEMINI_API_KEY:
                raise GeminiError("GEMINI_API_KEY is not set in keys.env")
            from google import genai
            from google.genai import types

            # A request that hangs (a dropped VPN route, say) times out and is retried.
            _client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        return _client


def _cache_path(namespace: str, key: str) -> Path:
    return CACHE_DIR / "gemini" / namespace / key[:2] / f"{key}.json"


def _key(model: str, namespace: str, system: str | None, prompt: str, schema: dict) -> str:
    return hashlib.sha1(json.dumps([model, namespace, (system or "") + "\n" + prompt, schema], sort_keys=True).encode()).hexdigest()


def cached_only(namespace: str, prompt: str, schema: dict, *, system: str | None = None,
                model: str = GEMINI_MODEL) -> Any | None:
    """The cached response generate_json() would return, or None; never calls Gemini."""
    p = _cache_path(namespace, _key(model, namespace, system, prompt, schema))
    if p.exists():
        return json.loads(p.read_text())["response"]
    return None


def generate_json(
    prompt: str,
    schema: dict,
    *,
    namespace: str,
    system: str | None = None,
    temperature: float = 0.2,
    model: str = GEMINI_MODEL,
    max_attempts: int = 8,
) -> Any:
    """Return the parsed JSON response for prompt, constrained to schema (OpenAPI subset)."""
    path = _cache_path(namespace, _key(model, namespace, system, prompt, schema))
    if path.exists():
        stats["cached"] += 1
        return json.loads(path.read_text())["response"]

    from google.genai import errors, types

    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
        system_instruction=system,
    )
    last: Exception | None = None
    for attempt in range(max_attempts):
        with _sem:
            try:
                resp = _get_client().models.generate_content(model=model, contents=prompt, config=cfg)
                stats["calls"] += 1
                text = resp.text or ""
                data = json.loads(text)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps({"model": model, "namespace": namespace, "response": data, "at": time.time()}))
                tmp.replace(path)
                return data
            except errors.APIError as e:
                last = e
                code = getattr(e, "code", 0) or 0
                if code not in (429, 500, 502, 503, 504):
                    raise GeminiError(f"Gemini error {code}: {str(e)[:300]}") from e
            except (json.JSONDecodeError, ValueError) as e:  # truncated/invalid JSON: retry
                last = e
            except (httpx.TransportError, OSError) as e:  # network blip (DNS, reset, timeout): retry
                last = e
        stats["retries"] += 1
        time.sleep(min(60.0, (2 ** attempt) + random.random()))
    raise GeminiError(f"Gemini failed after {max_attempts} attempts: {last}")
