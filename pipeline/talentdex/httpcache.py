"""Polite, cached HTTP GETs.

Every response we may need again is stored under cache/http/<namespace>/ keyed
by URL, so re-running the pipeline makes no network calls. 200 and 404/410
answers are cached (a missing profile stays missing); 429/5xx are retried with
backoff and never cached. Auth headers are never written to disk or logs.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from .config import CACHE_DIR, USER_AGENT

CACHEABLE = {200, 404, 410}


@dataclass
class Resp:
    url: str
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return self.status == 200

    def json(self) -> Any:
        return json.loads(self.text)


class RateLimitError(RuntimeError):
    pass


class Http:
    """A cached GET client for one service (one namespace, one rate limit)."""

    def __init__(
        self,
        namespace: str,
        *,
        min_interval: float = 0.0,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 6,
        keep_headers: tuple[str, ...] = (),
    ) -> None:
        self.dir = CACHE_DIR / "http" / namespace
        self.dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.keep_headers = tuple(h.lower() for h in keep_headers)
        self._headers = {"User-Agent": USER_AGENT, **(headers or {})}
        self._lock = threading.Lock()
        self._next_at = 0.0
        self._local = threading.local()
        self.network_calls = 0

    # -- cache -------------------------------------------------------------
    def _key(self, url: str, accept: str | None) -> Path:
        h = hashlib.sha1((url + "\n" + (accept or "")).encode()).hexdigest()
        return self.dir / h[:2] / (h + ".json")

    def cached(self, url: str, accept: str | None = None) -> Resp | None:
        p = self._key(url, accept)
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return Resp(d["url"], d["status"], d["text"], d.get("headers", {}), from_cache=True)

    def _store(self, r: Resp, accept: str | None) -> None:
        p = self._key(r.url, accept)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"url": r.url, "status": r.status, "headers": r.headers, "text": r.text, "fetched_at": time.time()}))
        tmp.replace(p)

    # -- network -----------------------------------------------------------
    def _session(self) -> requests.Session:
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            self._local.s = s
        return s

    def _wait_turn(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            self._next_at = max(now, self._next_at) + self.min_interval
        if wait > 0:
            time.sleep(wait)

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        accept: str | None = None,
        use_cache: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> Resp:
        if params:
            url = url + ("&" if "?" in url else "?") + urlencode(params, doseq=True)
        if use_cache:
            hit = self.cached(url, accept)
            if hit is not None:
                return hit
        headers = dict(self._headers)
        if accept:
            headers["Accept"] = accept
        if extra_headers:
            headers.update(extra_headers)
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            self._wait_turn()
            try:
                r = self._session().get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
                self.network_calls += 1
            except requests.RequestException as e:  # network blip
                last_err = e
                time.sleep(min(60, 2**attempt + random.random()))
                continue
            if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(r.headers.get("X-RateLimit-Reset", "0") or 0)
                sleep_for = max(5, reset - int(time.time()) + 3)
                if sleep_for > 3700:
                    raise RateLimitError(f"rate limited until {reset}")
                print(f"[http:{self.dir.name}] rate limited; sleeping {sleep_for}s", flush=True)
                time.sleep(sleep_for)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                retry_after = r.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(90, 2 ** (attempt + 1) + random.random())
                print(f"[http:{self.dir.name}] {r.status_code} on attempt {attempt + 1}; retrying in {delay:.0f}s", flush=True)
                time.sleep(delay)
                continue
            kept = {k: v for k, v in r.headers.items() if k.lower() in self.keep_headers}
            resp = Resp(url, r.status_code, r.text, kept)
            if r.status_code in CACHEABLE:
                self._store(resp, accept)
            return resp
        raise RuntimeError(f"GET failed after {self.max_retries} attempts: {url} ({last_err})")
