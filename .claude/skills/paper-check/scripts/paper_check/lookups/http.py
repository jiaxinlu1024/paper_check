"""One HTTP client for every lookup service.

Every request to a scholarly service goes through `HttpClient.get`, which:

- identifies the skill as ``paper-check/<version> (+https://github.com/jiaxinlu1024/paper_check;
  mailto:<contact>)``, the mailto part only when a contact email is configured;
- keeps a minimum interval between requests in the same rate bucket. There is one bucket
  per service, and two for Crossref, whose searches have a lower limit than DOI lookups.
  A service's own rate-limit headers can only make the interval longer;
- retries 429 and 5xx answers and network errors with exponential backoff and jitter,
  honours ``Retry-After`` up to a cap, and gives up at once when a service asks for a
  longer wait (OpenAlex answers an exhausted daily budget with a wait of hours);
- caches answers on disk, normally in ``<work>/cache/http/``: positive answers for 7 days,
  negative ones (404, 410, or an empty result as the caller defines it) for 24 hours, so a
  temporary failure is retried soon. Errors are never cached;
- in offline mode reads only the cache, whatever the age of an entry.

Secrets never reach the disk: API keys and the contact email are removed from cache keys
and stored URLs and redacted from stored bodies. Request headers are not stored.
`export_bundle` and `import_bundle` turn a cache folder into one JSON file and back; the
recorded responses in tests/fixtures/lookups/ were made that way.

Large data files (FReD, Retraction Watch) are fetched with `download`, which streams to a
file and refuses files above a size limit.
"""

from __future__ import annotations

import base64
import email.utils
import hashlib
import http.client
import json
import os
import random
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .. import __version__

PROJECT_URL = "https://github.com/jiaxinlu1024/paper_check"
POSITIVE_TTL = 7 * 24 * 3600
NEGATIVE_TTL = 24 * 3600
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
NEGATIVE_STATUSES = frozenset({404, 410})
# Query parameters that carry credentials or the contact address. They are dropped from
# cache keys and from every URL that is stored or shown.
SECRET_PARAMS = frozenset({"api_key", "apikey", "api-key", "mailto", "email", "key", "access_code", "token"})
KEEP_HEADERS = (
    "content-type", "content-length", "retry-after", "location", "last-modified", "link",
    "x-api-pool", "x-rate-limit-limit", "x-rate-limit-interval", "x-concurrency-limit",
    "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-remaining-usd", "x-ratelimit-cost-usd",
    "x-ratelimit-reset",
)
REDACTED = "<redacted>"

# Minimum seconds between two requests in a bucket. Sources: Crossref's limits since
# December 2025 (10/s for DOI lookups, 3/s for searches); OpenAlex's docs; Semantic Scholar's
# 1 request per second per key; arXiv's 3 seconds; DataCite's 1,000 requests per 5 minutes,
# which also caps doi.org content negotiation. The rest are deliberately gentle.
RATE_LIMITS = {
    "crossref": 0.1,
    "crossref-search": 0.34,
    "openalex": 0.1,
    "semanticscholar": 1.05,
    "arxiv": 3.0,
    "doi.org": 0.35,
    "datacite": 0.35,
    "nber": 1.0,
    "github": 0.5,
    "gitlab": 1.0,
    "osf": 1.0,
    "archive.org": 1.0,
    "default": 1.0,
}
HOST_BUCKETS = {
    "api.crossref.org": "crossref",
    "api.openalex.org": "openalex",
    "api.semanticscholar.org": "semanticscholar",
    "export.arxiv.org": "arxiv",
    "doi.org": "doi.org",
    "dx.doi.org": "doi.org",
    "api.datacite.org": "datacite",
    "www.nber.org": "nber",
    "nber.org": "nber",
    "raw.githubusercontent.com": "github",
    "gitlab.com": "gitlab",
    "api.osf.io": "osf",
    "osf.io": "osf",
    "archive.org": "archive.org",
}


class TransportError(Exception):
    """No HTTP answer was received: DNS failure, refused connection, timeout, TLS error."""


Transport = Callable[[str, str, dict, float, Optional[int]], tuple]


def _read(stream, max_bytes: Optional[int]) -> bytes:
    if max_bytes is None:
        return stream.read()
    return stream.read(max_bytes + 1)


def _describe(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, BaseException):
        exc = reason
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timed out"
    if isinstance(exc, socket.gaierror):
        return "host name could not be resolved"
    if isinstance(exc, ssl.SSLError):
        return f"TLS error: {exc}"
    if isinstance(exc, ConnectionRefusedError):
        return "connection refused"
    return f"{type(exc).__name__}: {exc}"


def urllib_transport(method: str, url: str, headers: dict, timeout: float, max_bytes: Optional[int] = None) -> tuple:
    """Send one request with urllib. Returns (status, headers, body, final_url).

    HTTP error statuses are returned, not raised. Proxy settings and the CA bundle come
    from the environment (HTTPS_PROXY, SSL_CERT_FILE), as urllib and OpenSSL read them."""
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        try:
            body = _read(exc, max_bytes)
        except Exception:
            body = b""
        hdrs = dict(exc.headers.items()) if exc.headers else {}
        return exc.code, hdrs, body, exc.geturl() if hasattr(exc, "geturl") else url
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as exc:
        raise TransportError(_describe(exc)) from None
    try:
        with resp:
            body = _read(resp, max_bytes)
            return resp.status, dict(resp.headers.items()), body, resp.geturl()
    except (OSError, http.client.HTTPException) as exc:
        raise TransportError(_describe(exc)) from None


def parse_retry_after(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """Seconds to wait from a Retry-After header: a number of seconds or an HTTP date."""
    if value is None:
        return None
    value = str(value).strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    return max(0.0, when.timestamp() - (now if now is not None else time.time()))


def _human_wait(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} hours"
    if seconds >= 120:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds:.0f} seconds"


def canonical_url(url: str, params: Optional[dict] = None) -> str:
    """The URL with params merged, secret parameters removed and the rest sorted."""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if params:
        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, (list, tuple)):
                query.extend((k, str(x)) for x in v)
            else:
                query.append((k, str(v)))
    kept = sorted((k, v) for k, v in query if k.lower() not in SECRET_PARAMS)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, urllib.parse.urlencode(kept), ""))


def build_url(url: str, params: Optional[dict] = None) -> str:
    """The URL with params appended, in the order given."""
    if not params:
        return url
    pairs = []
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            pairs.extend((k, str(x)) for x in v)
        else:
            pairs.append((k, str(v)))
    if not pairs:
        return url
    sep = "&" if urllib.parse.urlsplit(url).query else "?"
    return url + sep + urllib.parse.urlencode(pairs)


def bucket_for(url: str) -> str:
    host = urllib.parse.urlsplit(url).netloc.lower().split("@")[-1].split(":")[0]
    return HOST_BUCKETS.get(host, host or "default")


@dataclass
class Response:
    """One answer, live or from the cache. `url` never contains secrets."""

    url: str
    status: Optional[int] = None
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    final_url: Optional[str] = None
    from_cache: bool = False
    stale: bool = False
    error: Optional[str] = None
    attempts: int = 0
    fetched_at: Optional[float] = None
    truncated: bool = False
    offline_miss: bool = False

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    @property
    def not_found(self) -> bool:
        return self.status in NEGATIVE_STATUSES

    @property
    def throttled(self) -> bool:
        return self.status == 429

    @property
    def outcome(self) -> str:
        """ok, not_found, throttled, offline or error."""
        if self.ok:
            return "ok"
        if self.not_found:
            return "not_found"
        if self.throttled:
            return "throttled"
        if self.offline_miss:
            return "offline"
        return "error"

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8", errors="replace") or "null")
        except ValueError:
            return None

    def describe(self) -> str:
        """A short account of a failed answer, for coverage reasons and trajectories."""
        if self.ok:
            return f"HTTP {self.status}"
        if self.offline_miss:
            return "offline, and no cached answer"
        if self.status is None:
            return self.error or "no answer"
        return self.error or f"HTTP {self.status}"


class CacheStore:
    """Answers on disk, one JSON file per request, fanned out by the first two hex digits."""

    def __init__(self, root: Path):
        self.root = Path(root)

    @staticmethod
    def key(method: str, canonical: str, accept: str = "") -> str:
        return hashlib.sha256(f"{method} {canonical} {accept}".encode("utf-8")).hexdigest()

    def path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> Optional[dict]:
        path = self.path(key)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, key: str, entry: dict) -> None:
        path = self.path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass  # a cache that cannot be written is not an error

    def entries(self) -> Iterable[dict]:
        if not self.root.exists():
            return []
        out = []
        for path in sorted(self.root.glob("*/*.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out


BUNDLE_FORMAT = "paper-check-http-bundle"


def export_bundle(cache_dir: Path, path: Path, note: str = "", redact: Optional[Callable[[str], str]] = None) -> int:
    """Write every cache entry under cache_dir into one JSON file. Returns the count.

    Entries are already redacted when cached; `redact` is a second pass for safety."""
    entries = sorted(CacheStore(cache_dir).entries(), key=lambda e: (e.get("url", ""), e.get("accept", "")))
    if redact:
        clean = []
        for e in entries:
            text = redact(json.dumps(e, ensure_ascii=False))
            clean.append(json.loads(text))
        entries = clean
    data = {"format": BUNDLE_FORMAT, "version": 1, "note": note, "entries": entries}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(entries)


def import_bundle(path: Path, cache_dir: Path) -> int:
    """Load a bundle written by export_bundle into a cache folder. Returns the count."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != BUNDLE_FORMAT:
        raise ValueError(f"{path} is not a paper-check HTTP bundle")
    store = CacheStore(cache_dir)
    for entry in data.get("entries", []):
        store.put(entry["key"], entry)
    return len(data.get("entries", []))


@dataclass
class Download:
    ok: bool
    url: str
    path: Optional[Path] = None
    size: int = 0
    status: Optional[int] = None
    sha256: Optional[str] = None
    reason: Optional[str] = None
    last_modified: Optional[str] = None


class HttpClient:
    """The shared client. One instance per run; it is not thread-safe."""

    def __init__(self, cache_dir: Optional[Path] = None, *, offline: bool = False, contact: Optional[str] = None,
                 secrets: Iterable[Optional[str]] = (), transport: Optional[Transport] = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 rand: Callable[[], float] = random.random, max_retries: int = 4, backoff_base: float = 1.0,
                 backoff_cap: float = 60.0, retry_after_cap: float = 60.0, timeout: float = 30.0,
                 rate_limits: Optional[dict] = None):
        self.cache = CacheStore(cache_dir) if cache_dir else None
        self.offline = offline
        self.contact = contact or None
        self.transport = transport or urllib_transport
        self.sleep = sleep
        self.clock = clock
        self.rand = rand
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.retry_after_cap = retry_after_cap
        self.timeout = timeout
        self.rate_limits = dict(RATE_LIMITS, **(rate_limits or {}))
        self._intervals: dict = {}
        self._last: dict = {}
        self.stats: dict = {}
        secret_values = [s for s in [contact, *secrets] if s]
        variants = set()
        for s in secret_values:
            s = str(s)
            for v in (s, urllib.parse.quote(s, safe=""), urllib.parse.quote_plus(s), urllib.parse.quote(s)):
                variants.add(v)
                variants.add(v.lower())
        self._secret_variants = sorted((v for v in variants if len(v) >= 4), key=len, reverse=True)

    # ---- identity and redaction -----------------------------------------
    @property
    def user_agent(self) -> str:
        tail = f"; mailto:{self.contact}" if self.contact else ""
        return f"paper-check/{__version__} (+{PROJECT_URL}{tail})"

    def redact(self, text: Optional[str]) -> str:
        if not text:
            return text or ""
        for v in self._secret_variants:
            if v in text:
                text = text.replace(v, REDACTED)
        return text

    def redact_url(self, url: Optional[str]) -> str:
        if not url:
            return url or ""
        parts = urllib.parse.urlsplit(url)
        if parts.query:
            query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                     if k.lower() not in SECRET_PARAMS]
            url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query),
                                           parts.fragment))
        return self.redact(url)

    # ---- rate limiting and backoff ----------------------------------------
    def _interval(self, bucket: str) -> float:
        return self._intervals.get(bucket, self.rate_limits.get(bucket, self.rate_limits["default"]))

    def _wait(self, bucket: str) -> None:
        last = self._last.get(bucket)
        if last is not None:
            delay = self._interval(bucket) - (self.clock() - last)
            if delay > 0:
                self.sleep(delay)
        self._last[bucket] = self.clock()

    def _adapt(self, bucket: str, headers: dict) -> None:
        """Slow down when a service reports a lower limit than the configured one."""
        limit, interval = headers.get("x-rate-limit-limit"), headers.get("x-rate-limit-interval")
        if not limit or not interval:
            return
        try:
            n = float(limit)
            secs = float(str(interval).rstrip("s"))
        except ValueError:
            return
        if n > 0:
            reported = secs / n
            if reported > self._interval(bucket):
                self._intervals[bucket] = reported

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with equal jitter: half fixed, half random."""
        d = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        return d / 2 + self.rand() * d / 2

    def _count(self, bucket: str, what: str) -> None:
        s = self.stats.setdefault(bucket, {"requests": 0, "cache_hits": 0, "errors": 0, "throttled": 0})
        s[what] = s.get(what, 0) + 1

    # ---- requests ---------------------------------------------------------
    def get(self, url: str, params: Optional[dict] = None, *, headers: Optional[dict] = None,
            bucket: Optional[str] = None, use_cache: bool = True,
            negative_if: Optional[Callable[[Response], bool]] = None, max_retries: Optional[int] = None,
            retry_after_cap: Optional[float] = None, max_bytes: Optional[int] = None, store_body: bool = True,
            transform: Optional[Callable[[bytes], bytes]] = None, timeout: Optional[float] = None) -> Response:
        """GET a URL through the cache. `transform` reduces a successful body before it is
        cached and returned, so live and cached answers look the same to the parser."""
        full = build_url(url, params)
        shown = self.redact_url(full)
        bucket = bucket or bucket_for(full)
        accept = (headers or {}).get("Accept", "")
        key = CacheStore.key("GET", canonical_url(full), accept)
        entry = None
        if use_cache and self.cache is not None:
            entry = self.cache.get(key)
            if entry is not None:
                age = time.time() - float(entry.get("fetched_at") or 0)
                ttl = POSITIVE_TTL if entry.get("class") == "positive" else NEGATIVE_TTL
                if self.offline or age <= ttl:
                    self._count(bucket, "cache_hits")
                    return self._from_entry(entry, stale=age > ttl)
        if self.offline:
            return Response(url=shown, error="offline, and no cached answer", offline_miss=True)
        resp = self._fetch(full, shown, headers or {}, bucket,
                           self.max_retries if max_retries is None else max_retries,
                           self.retry_after_cap if retry_after_cap is None else retry_after_cap,
                           max_bytes, timeout or self.timeout)
        if entry is not None and (resp.status is None or resp.status in RETRY_STATUSES):
            # A failed refresh keeps the answer we already have; it is marked stale.
            self._count(bucket, "cache_hits")
            return self._from_entry(entry, stale=True)
        if resp.ok and transform is not None:
            try:
                resp.body = transform(resp.body)
            except Exception:
                pass
        if use_cache and self.cache is not None and resp.status is not None:
            cls = None
            if resp.ok:
                cls = "negative" if (negative_if is not None and _safe(negative_if, resp)) else "positive"
            elif resp.status in NEGATIVE_STATUSES:
                cls = "negative"
            if cls:
                self.cache.put(key, self._entry(key, resp, cls, accept, store_body))
        return resp

    def _fetch(self, full: str, shown: str, headers: dict, bucket: str, max_retries: int,
               retry_after_cap: float, max_bytes: Optional[int], timeout: float) -> Response:
        req_headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        req_headers.update(headers)
        attempts = 0
        status, hdrs, body, final = None, {}, b"", None
        for attempt in range(max_retries + 1):
            self._wait(bucket)
            attempts += 1
            self._count(bucket, "requests")
            try:
                status, raw_headers, body, final = self.transport("GET", full, req_headers, timeout, max_bytes)
            except TransportError as exc:
                self._count(bucket, "errors")
                if attempt < max_retries:
                    self.sleep(self._backoff(attempt))
                    continue
                return Response(url=shown, error=self.redact(str(exc)), attempts=attempts)
            hdrs = {str(k).lower(): v for k, v in (raw_headers or {}).items()}
            self._adapt(bucket, hdrs)
            if status in RETRY_STATUSES:
                if status == 429:
                    self._count(bucket, "throttled")
                wait = parse_retry_after(hdrs.get("retry-after"))
                if wait is not None and wait > retry_after_cap:
                    return Response(url=shown, status=status, headers=_keep(hdrs), body=self._redact_body(body),
                                    attempts=attempts, fetched_at=time.time(),
                                    error=f"HTTP {status}; the service asks to wait {_human_wait(wait)}, "
                                          f"longer than paper-check waits")
                if attempt < max_retries:
                    self.sleep(wait if wait is not None else self._backoff(attempt))
                    continue
            break
        truncated = max_bytes is not None and len(body) > max_bytes
        if truncated:
            body = body[:max_bytes]
        error = None if (status is not None and status < 400) else f"HTTP {status}"
        return Response(url=shown, status=status, headers=_keep(hdrs), body=self._redact_body(body),
                        final_url=self.redact_url(final) if final else None, attempts=attempts,
                        fetched_at=time.time(), truncated=truncated, error=error)

    def _redact_body(self, body: bytes) -> bytes:
        if not self._secret_variants or not body:
            return body
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return body
        clean = self.redact(text)
        return body if clean == text else clean.encode("utf-8")

    def _entry(self, key: str, resp: Response, cls: str, accept: str, store_body: bool) -> dict:
        entry = {"key": key, "url": resp.url, "accept": accept, "status": resp.status, "headers": resp.headers,
                 "fetched_at": resp.fetched_at or time.time(), "class": cls}
        if resp.final_url and resp.final_url != resp.url:
            entry["final_url"] = resp.final_url
        if resp.truncated:
            entry["truncated"] = True
        if store_body and resp.body:
            try:
                entry["body"] = self.redact(resp.body.decode("utf-8"))
            except UnicodeDecodeError:
                entry["body_b64"] = base64.b64encode(resp.body).decode("ascii")
        return entry

    @staticmethod
    def _from_entry(entry: dict, stale: bool) -> Response:
        if "body" in entry:
            body = entry["body"].encode("utf-8")
        elif "body_b64" in entry:
            body = base64.b64decode(entry["body_b64"])
        else:
            body = b""
        status = entry.get("status")
        return Response(url=entry.get("url", ""), status=status, headers=entry.get("headers") or {}, body=body,
                        final_url=entry.get("final_url"), from_cache=True, stale=stale,
                        fetched_at=entry.get("fetched_at"), truncated=bool(entry.get("truncated")),
                        error=None if status is not None and status < 400 else f"HTTP {status}")

    # ---- large files --------------------------------------------------------
    def download(self, url: str, dest: Path, *, max_bytes: int, bucket: Optional[str] = None,
                 timeout: float = 180.0) -> Download:
        """Stream a data file to dest, refusing anything above max_bytes."""
        shown = self.redact_url(url)
        if self.offline:
            return Download(False, shown, reason="offline")
        bucket = bucket or bucket_for(url)
        self._wait(bucket)
        self._count(bucket, "requests")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + f".{os.getpid()}.part")
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "*/*"})
        limit_mb = max_bytes / 1e6
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                length = resp.headers.get("Content-Length")
                if length and length.isdigit() and int(length) > max_bytes:
                    return Download(False, shown, status=resp.status, size=int(length),
                                    reason=f"the file is {int(length) / 1e6:.1f} MB, above the {limit_mb:.0f} MB limit")
                digest, size = hashlib.sha256(), 0
                with open(tmp, "wb") as fh:
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            fh.close()
                            tmp.unlink(missing_ok=True)
                            return Download(False, shown, status=resp.status, size=size,
                                            reason=f"the file is larger than the {limit_mb:.0f} MB limit")
                        digest.update(chunk)
                        fh.write(chunk)
                tmp.replace(dest)
                return Download(True, shown, dest, size, resp.status, digest.hexdigest(),
                                last_modified=resp.headers.get("Last-Modified"))
        except urllib.error.HTTPError as exc:
            self._count(bucket, "errors")
            return Download(False, shown, status=exc.code, reason=f"HTTP {exc.code}")
        except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as exc:
            self._count(bucket, "errors")
            tmp.unlink(missing_ok=True)
            return Download(False, shown, reason=self.redact(_describe(exc)))


def _keep(headers: dict) -> dict:
    return {k: v for k, v in headers.items() if k in KEEP_HEADERS}


def _safe(func: Callable[[Response], bool], resp: Response) -> bool:
    try:
        return bool(func(resp))
    except Exception:
        return False
