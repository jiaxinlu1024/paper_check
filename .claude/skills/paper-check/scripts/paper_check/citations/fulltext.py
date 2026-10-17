"""Full text of cited works, fetched legally, best source first (DESIGN section 7, step 2).

For each cited reference the cascade stops at the first full text it can verify:

   1. sources            the user's folder of PDFs, matched by DOI or title on each PDF's first pages
   2. openalex           the work's best open-access location, then its other open-access locations
   3. unpaywall          best_oa_location, then the other oa_locations
   4. semantic_scholar   openAccessPdf
   5. arxiv              the arXiv id in the reference or found on the way, else an arXiv title search
   6. nber               the reference's NBER number, or an NBER working paper with the same title and
                         authors listed by OpenAlex or Crossref (NBER papers are free 18 months after release)
   7. openalex_versions  open-access copies attached to other OpenAlex records of the same work
   8. core               only with a CORE API key
   9. openalex_content   OpenAlex's paid cached PDF, only when the paper's settings say paid_pdfs: true
  10. abstract           OpenAlex abstract_inverted_index, then Crossref, then Semantic Scholar

Rules:
  - No shadow libraries, no search-engine scraping, and no bypassing of bot protection: a challenge
    page counts as "not available" and the next source is tried.
  - A record found by the reference's DOI must have a matching title; otherwise the DOI is reported
    as belonging to another work and is not used.
  - A downloaded PDF must show the reference's title (or its DOI and title) on its first pages, or it
    is rejected as a different work.
  - Queries are built from reference metadata only. Nothing from the paper's text is sent anywhere.
  - The version read is always recorded: published, accepted, submitted, unknown, or abstract.

Networking follows dev/ARCHITECTURE.md: the user agent is
"paper-check/<version> (+https://github.com/jiaxinlu1024/paper_check; mailto:<email>)", with the
mailto part sent only to scholarly APIs. Requests to one host are spaced (arXiv 3 s, Semantic
Scholar 1 s, NBER 1 s), 429 and 5xx answers are retried with exponential backoff, and responses are
cached in WORK/citations/cache/: 7 days for answers, 24 hours for misses. API keys and the contact
email are stripped from cache keys, logs and saved metadata.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import html
import io
import json
import logging
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from .. import __version__

PROJECT_URL = "https://github.com/jiaxinlu1024/paper_check"
POSITIVE_TTL = 7 * 86400
NEGATIVE_TTL = 86400
MAX_DOWNLOAD = 80 * 1024 * 1024
MAX_PAGES = 400
RETRY_STATUSES = {429, 500, 502, 503, 504}
API_HOSTS = {"api.openalex.org", "content.openalex.org", "api.crossref.org", "api.unpaywall.org",
             "api.semanticscholar.org", "export.arxiv.org", "api.core.ac.uk"}
MIN_INTERVAL = {"export.arxiv.org": 3.0, "arxiv.org": 3.0, "api.semanticscholar.org": 1.1,
                "www.nber.org": 1.0, "api.core.ac.uk": 1.0, "api.openalex.org": 0.15,
                "content.openalex.org": 0.2, "api.crossref.org": 0.15, "api.unpaywall.org": 0.15}
DEFAULT_INTERVAL = 1.0
SECRET_PARAMS = {"api_key", "apikey", "key", "email", "mailto", "token"}

STEPS = ("sources", "openalex", "unpaywall", "semantic_scholar", "arxiv", "nber", "openalex_versions",
         "core", "openalex_content", "abstract")
VERSION_NAMES = {"publishedversion": "published", "acceptedversion": "accepted", "submittedversion": "submitted",
                 "published": "published", "accepted": "accepted", "submitted": "submitted"}
VERSION_RANK = {"published": 0, "accepted": 1, "submitted": 2, "unknown": 3}

ABSTRACT_NOTE = ("cannot verify: no full text (abstract only). An abstract can support or contradict a claim, "
                 "but can never show a topic absent.")
NOT_FOUND_NOTE = "cannot verify: no full text"


# ================================================================ HTTP
def user_agent(email: Optional[str] = None) -> str:
    return f"paper-check/{__version__} (+{PROJECT_URL}" + (f"; mailto:{email})" if email else ")")


def strip_secrets(url: str) -> str:
    """The URL without keys or email addresses in its query string."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in SECRET_PARAMS]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


@dataclass
class Response:
    url: str                      # request URL without secrets
    status: Optional[int]
    body: bytes = b""
    content_type: str = ""
    final_url: str = ""
    error: Optional[str] = None
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8"))
        except Exception:
            return None

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def describe(self) -> str:
        if self.status is None:
            return self.error or "no response"
        return f"HTTP {self.status}" + (f" ({self.error})" if self.error else "")

    @property
    def transient(self) -> bool:
        """A failure worth retrying on the next run: rate limits, server errors, network errors."""
        return self.status is None or self.status in RETRY_STATUSES


def urllib_transport(url: str, headers: dict, timeout: float, max_bytes: int):
    """Default transport: (status, lower-cased headers, body, final URL). Honours HTTPS_PROXY."""
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read(2_000_000) if exc.fp else b""
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, body, exc.geturl() or url
    with response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"response larger than {max_bytes // (1024 * 1024)} MB")
        return response.status, {k.lower(): v for k, v in response.headers.items()}, body, response.geturl()


class Fetcher:
    """Small polite HTTP client: identifying user agent, per-host spacing, backoff, cache.

    `transport(url, headers, timeout, max_bytes)` can be replaced, which is how the tests replay
    recorded responses. In offline mode only the cache answers, stale entries included."""

    def __init__(self, cache_dir: Optional[Path] = None, email: Optional[str] = None, offline: bool = False,
                 transport: Optional[Callable] = None, sleep: Callable = time.sleep, secrets: Iterable[str] = ()):
        self.cache_dir = Path(cache_dir) / "http" if cache_dir else None
        self.email = email
        self.offline = offline
        self.transport = transport or urllib_transport
        self.sleep = sleep
        self.requests = 0
        self._last: dict = {}
        self._cooldown: dict = {}   # host -> monotonic time before which it is not asked again
        self._failures: dict = {}   # host -> consecutive calls that ended in a network error
        self._secrets = [s for s in [*secrets, email] if s]

    def scrub(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "<redacted>")
        return text

    def get(self, url: str, *, headers: Optional[dict] = None, api: bool = False, accept: str = "*/*",
            timeout: float = 30.0, retries: int = 3, use_cache: bool = True,
            max_bytes: int = MAX_DOWNLOAD) -> Response:
        clean = strip_secrets(url)
        if use_cache:
            cached = self._cache_get(clean)
            if cached is not None:
                return cached
        if self.offline:
            return Response(clean, None, error="offline, and not in the cache")
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        until = self._cooldown.get(host)
        if until is not None and time.monotonic() < until:
            if self._failures.get(host, 0) >= 2:
                return Response(clean, None, error=f"{host} was unreachable earlier in this run; not asked again")
            return Response(clean, 429, error=f"rate limited by {host} earlier in this run; not asked again")
        hdrs = {"User-Agent": user_agent(self.email if api else None), "Accept": accept}
        hdrs.update(headers or {})
        status, rheaders, body, final, error = None, {}, b"", url, None
        for attempt in range(retries + 1):
            self._throttle(host)
            try:
                status, rheaders, body, final = self.transport(url, hdrs, timeout, max_bytes)
                error = None
            except Exception as exc:  # network failure: report it, never crash the run
                status, rheaders, body, final = None, {}, b"", url
                error = self.scrub(f"{type(exc).__name__}: {exc}")[:300]
            self._last[host] = time.monotonic()
            self.requests += 1
            wait = self._retry_after(rheaders)
            if status in RETRY_STATUSES and wait is not None and wait > 60:
                # the server asks for a long pause: respect it by leaving the host alone for this run
                self._cooldown[host] = time.monotonic() + wait
                error = f"rate limited: {host} asks to wait {int(wait)} s"
                break
            if attempt < retries and (status in RETRY_STATUSES or (status is None and attempt == 0)):
                self.sleep(wait if wait is not None else min(60.0, 2.0 * (2 ** attempt)))
                continue
            break
        if status is None:  # two calls in a row that cannot reach a host: leave it alone for this run
            self._failures[host] = self._failures.get(host, 0) + 1
            if self._failures[host] >= 2:
                self._cooldown[host] = time.monotonic() + 6 * 3600
        else:
            self._failures[host] = 0
        response = Response(clean, status, body or b"", str(rheaders.get("content-type") or ""),
                            strip_secrets(final or url), error)
        if use_cache and status is not None and status not in RETRY_STATUSES:
            self._cache_put(clean, response)
        return response

    # ---- internals
    def _throttle(self, host: str) -> None:
        interval = MIN_INTERVAL.get(host, DEFAULT_INTERVAL)
        last = self._last.get(host)
        if last is not None:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                self.sleep(wait)

    @staticmethod
    def _retry_after(headers: dict) -> Optional[float]:
        value = str((headers or {}).get("retry-after") or "").strip()
        return float(value) if value.isdigit() else None

    def _cache_base(self, clean_url: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        h = hashlib.sha1(clean_url.encode("utf-8")).hexdigest()
        return self.cache_dir / h[:2] / h

    def _cache_get(self, clean_url: str) -> Optional[Response]:
        base = self._cache_base(clean_url)
        if base is None or not base.with_suffix(".json").exists():
            return None
        try:
            meta = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
            ttl = POSITIVE_TTL if 200 <= int(meta["status"]) < 300 and not meta.get("negative") else NEGATIVE_TTL
            if not self.offline and time.time() - float(meta["fetched"]) > ttl:
                return None
            body_path = base.with_suffix(".bin")
            body = body_path.read_bytes() if body_path.exists() else b""
        except Exception:
            return None
        return Response(clean_url, int(meta["status"]), body, meta.get("content_type", ""),
                        meta.get("final_url") or clean_url, None, from_cache=True)

    def mark_negative(self, url: str) -> None:
        """Keep a cached answer for 24 hours only, such as a bot-protection page served with HTTP 200."""
        base = self._cache_base(strip_secrets(url))
        if base is None or not base.with_suffix(".json").exists():
            return
        try:
            meta = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
            meta["negative"] = True
            base.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
        except (OSError, ValueError):
            pass

    def _cache_put(self, clean_url: str, response: Response) -> None:
        base = self._cache_base(clean_url)
        if base is None:
            return
        try:
            base.parent.mkdir(parents=True, exist_ok=True)
            base.with_suffix(".bin").write_bytes(response.body)
            base.with_suffix(".json").write_text(json.dumps({
                "url": clean_url, "status": response.status, "content_type": response.content_type,
                "final_url": response.final_url, "fetched": time.time()}), encoding="utf-8")
        except OSError:
            pass


# ================================================================ text helpers
_MARKS = dict.fromkeys(map(ord, "™®©"), None)


def norm_text(text: Optional[str]) -> str:
    """Lowercase ASCII words separated by single spaces: for comparing titles and finding names."""
    text = unicodedata.normalize("NFKD", (text or "").translate(_MARKS))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().replace("&", " and ")
    text = re.sub(r"\\[a-z]+", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def title_similarity(a: Optional[str], b: Optional[str]) -> float:
    """0-100. A title that is the other plus a subtitle counts as 95."""
    from rapidfuzz import fuzz

    a, b = norm_text(a), norm_text(b)
    if not a or not b:
        return 0.0
    score = float(fuzz.ratio(a, b))
    short, long_ = sorted((a, b), key=len)
    if len(short.split()) >= 3 and long_.startswith(short + " "):
        score = max(score, 95.0)
    return round(score, 1)


def family_keys(authors) -> list:
    """Last word of each author's normalized family name: 'O'Donoghue' -> 'donoghue'."""
    out = []
    for a in authors or []:
        if isinstance(a, dict):
            name = a.get("family") or a.get("name") or a.get("display_name") or ""
            if not a.get("family"):
                name = name.split(",")[0] if "," in name else (name.split()[-1] if name.split() else "")
        else:
            name = str(a)
            name = name.split(",")[0] if "," in name else (name.split()[-1] if name.split() else "")
        words = norm_text(name).split()
        if words:
            out.append(words[-1])
    return out


def names_from_display(names: Iterable[str]) -> list:
    """Family-name keys from display names such as 'Brigitte C. Madrian' -> 'madrian'."""
    keys = []
    for name in names:
        words = norm_text(name).split()
        if words:
            keys.append(words[-1])
    return keys


def author_overlap(ref_keys: list, record_keys: list) -> Optional[float]:
    if not ref_keys or not record_keys:
        return None
    rec = set(record_keys)
    return round(sum(1 for k in ref_keys if k in rec) / len(ref_keys), 2)


_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+)", re.I)


def norm_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = re.sub(r"^\s*(https?://(dx\.)?doi\.org/|doi:\s*)", "", str(doi).strip(), flags=re.I)
    d = d.rstrip(".,;]}'\"")
    while d.endswith(")") and d.count(")") > d.count("("):
        d = d[:-1]
    return d.lower() if d.lower().startswith("10.") else None


def dois_in(text: str) -> list:
    out = []
    for m in _DOI.finditer(text or ""):
        d = norm_doi(m.group(1))
        if d and d not in out:
            out.append(d)
    return out


_ARXIV_ID = r"(\d{4}\.\d{4,5}|[a-z][a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?"


def arxiv_ids(fields: dict, raw: str = "") -> list:
    """arXiv identifiers named by a reference (URL, arXiv DOI, eprint field or 'arXiv:...')."""
    hay = " ".join(str(fields.get(k) or "") for k in ("url", "doi", "eprint", "note", "number", "container")) + " " + (raw or "")
    out = []
    for pattern in (rf"arxiv\.org/(?:abs|pdf)/{_ARXIV_ID}", rf"10\.48550/arxiv\.{_ARXIV_ID}", rf"arxiv\s*:?\s*{_ARXIV_ID}"):
        for m in re.finditer(pattern, hay, re.I):
            if m.group(1) not in out:
                out.append(m.group(1))
    eprint = str(fields.get("eprint") or "").strip()
    m = re.fullmatch(_ARXIV_ID, eprint)
    if m and m.group(1) not in out:
        out.append(m.group(1))
    return out


def nber_numbers(fields: dict, raw: str = "") -> list:
    """NBER working-paper numbers named by a reference, without the 'w'."""
    hay = " ".join(str(fields.get(k) or "") for k in ("doi", "url", "number", "note", "container", "publisher")) + " " + (raw or "")
    out = []
    patterns = (r"10\.3386/w(\d{1,6})\b", r"nber\.org/(?:papers|system/files/working_papers)/w(\d{1,6})\b",
                r"\bNBER\s+Working\s+Papers?(?:\s+Series)?\s*[,:]?\s*(?:No\.?|Number|#)?\s*w?(\d{1,6})\b")
    for pattern in patterns:
        for m in re.finditer(pattern, hay, re.I):
            if m.group(1) not in out:
                out.append(m.group(1))
    number = str(fields.get("number") or "").strip()
    m = re.fullmatch(r"w?(\d{1,6})", number, re.I)
    context = " ".join(str(fields.get(k) or "") for k in ("container", "publisher", "type", "note")) + " " + (raw or "")
    if m and re.search(r"\bNBER\b|National Bureau of Economic Research", context, re.I) and m.group(1) not in out:
        out.append(m.group(1))
    return out


# ================================================================ PDF text
_INVISIBLE = dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None)
PAGE_MARKER = re.compile(r"^\[\[(?:page (\d+)|abstract|text)\]\]$", re.M)


def clean_page_text(text: str) -> str:
    """NFKC (ligatures become letters), invisible characters removed, line ends kept."""
    text = unicodedata.normalize("NFKC", text or "").translate(_INVISIBLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def extract_pdf(source, max_pages: int = MAX_PAGES, check: Optional[Callable[[str], bool]] = None) -> dict:
    """Text of each page with pdfplumber. `source` is a path or the PDF's bytes.

    With `check`, the first three pages are passed to it first, and extraction stops early when it
    returns False ("rejected": True), so a wrong PDF is not read to the end.
    Returns {"pages": [text per page], "n_pages", "truncated", "error", "rejected"}."""
    import pdfplumber

    for name in ("pdfminer", "pdfplumber"):
        logging.getLogger(name).setLevel(logging.ERROR)
    out = {"pages": [], "n_pages": 0, "truncated": False, "error": None, "rejected": False}
    try:
        handle = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else str(source)
        with pdfplumber.open(handle) as pdf:
            out["n_pages"] = len(pdf.pages)
            out["truncated"] = out["n_pages"] > max_pages
            for i, page in enumerate(pdf.pages[:max_pages]):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                out["pages"].append(clean_page_text(text))
                try:
                    page.close()
                except Exception:
                    pass
                if check is not None and i == min(2, out["n_pages"] - 1, max_pages - 1):
                    if not check("\n".join(out["pages"])):
                        out["rejected"] = True
                        break
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


def pages_to_text(pages: list) -> str:
    return "".join(f"[[page {i}]]\n{text}\n\n" for i, text in enumerate(pages, 1))


def text_quality(pages: list) -> dict:
    chars = sum(len(p.strip()) for p in pages)
    with_text = sum(1 for p in pages if len(p.strip()) >= 40)
    cid = sum(p.count("(cid:") for p in pages)
    usable = bool(pages) and chars >= 300 and with_text >= max(1, round(0.3 * len(pages))) and cid * 6 < chars / 10
    return {"chars": chars, "pages_with_text": with_text, "unmapped_glyphs": cid, "usable": usable}


def identify(fields: dict, first_text: str) -> dict:
    """Does this text (a PDF's first pages) belong to the reference? Title, authors and DOI."""
    from rapidfuzz import fuzz

    title = norm_text(fields.get("title"))
    text = norm_text(first_text[:15000])
    doi = norm_doi(fields.get("doi"))
    result = {"title_score": None, "author_score": None, "doi_found": bool(doi and doi in (first_text or "").lower())}
    if title and text:
        if len(title) <= len(text):
            alignment = fuzz.partial_ratio_alignment(title, text)
            result["title_score"] = round(alignment.score, 1)
            result["title_position"] = alignment.dest_start
        else:
            result["title_score"] = round(float(fuzz.ratio(title, text)), 1)
    keys = family_keys(fields.get("authors"))
    if keys and text:
        words = set(text.split())
        result["author_score"] = round(sum(1 for k in keys if k in words) / len(keys), 2)
    ts = result["title_score"] or 0.0
    au = result["author_score"]
    need = 92.0 if len(title.split()) <= 4 else 85.0
    if not title:
        ok = result["doi_found"] or (au or 0) >= 0.5
        basis = "no title in the reference; " + ("DOI found" if result["doi_found"] else "authors found" if ok else "nothing to match")
    elif result["doi_found"] and ts >= 70:
        ok, basis = True, "DOI and title on the first pages"
    elif result["doi_found"]:
        ok, basis = False, "the reference's DOI is on the first pages but the title is not: possibly a different work"
    elif ts >= need and (au is None or au >= 0.5 or ts >= 97):
        ok, basis = True, "title" + (" and authors" if au else "") + " on the first pages"
    elif ts >= 78 and au is not None and au >= 0.99:
        ok, basis = True, "most of the title and every author on the first pages (the title may differ between versions)"
    else:
        ok, basis = False, "the reference's title was not found on the first pages"
    result["ok"], result["basis"] = ok, basis
    return result


def guess_version(page1: str, fields: dict) -> tuple:
    """Version of a user-supplied PDF, judged from its first page."""
    head = (page1 or "")[:4000]
    low = head.lower()
    if re.search(r"working papers? series|working paper no|discussion paper|\bpreprint\b|\bdraft\b|not for (?:citation|quotation)|do not (?:cite|quote)|this version:", low):
        return "submitted", "working-paper or preprint wording on the first page"
    if re.search(r"accepted manuscript|author accepted|accepted for publication|postprint|author'?s final", low):
        return "accepted", "accepted-manuscript wording on the first page"
    doi = norm_doi(fields.get("doi"))
    container = norm_text(fields.get("container"))
    if (doi and doi in low) or (container and len(container) > 6 and container in norm_text(head)):
        return "published", "journal name or DOI on the first page"
    return "unknown", "no version statement on the first page"


# ================================================================ HTML pages
_CHALLENGE_STRONG = re.compile(rb"<title>\s*just a moment|cf-chl|cf-browser-verification|attention required! \| cloudflare|"
                               rb"anubis_challenge|protected by <a[^>]*anubis|checking your browser before|"
                               rb"pardon our interruption|incapsula incident", re.I)
_CHALLENGE_WEAK = re.compile(rb"captcha|are you a robot|access denied|unusual traffic", re.I)


def is_challenge(response: Response) -> bool:
    """A bot-protection page. Strong markers count on any status; weak ones only on refusals."""
    head = response.body[:30000]
    if not head or head.lstrip()[:5].startswith(b"%PDF"):
        return False
    if _CHALLENGE_STRONG.search(head):
        return True
    return response.status in (401, 403, 429, 503) and bool(_CHALLENGE_WEAK.search(head))


def citation_pdf_url(body: bytes, base_url: str) -> Optional[str]:
    """The PDF link a landing page declares in its citation_pdf_url meta tag."""
    text = body[:400000].decode("utf-8", errors="replace")
    for pattern in (r"<meta[^>]+name=[\"']citation_pdf_url[\"'][^>]*content=[\"']([^\"']+)[\"']",
                    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*name=[\"']citation_pdf_url[\"']"):
        m = re.search(pattern, text, re.I)
        if m:
            return urllib.parse.urljoin(base_url, html.unescape(m.group(1).strip()))
    return None


def strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return re.sub(r"^(abstract|summary)[\s.:]+", "", text, flags=re.I)


def openalex_abstract(inverted: Optional[dict]) -> Optional[str]:
    if not inverted:
        return None
    words = sorted((i, w) for w, positions in inverted.items() for i in positions)
    return strip_tags(" ".join(w for _, w in words)) or None


# ================================================================ sources folder
def _pdf_meta_title(path: Path) -> str:
    try:
        from pypdf import PdfReader

        info = PdfReader(str(path)).metadata
        return str((info or {}).get("/Title") or "")
    except Exception:
        return ""


def index_sources_folder(folder: Path, cache_file: Optional[Path] = None) -> list:
    """Every PDF in the folder (recursively) with the text of its first three pages.

    Cached by path, size and modification time, so re-runs read only new or changed files."""
    cache = {}
    if cache_file and cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    entries, fresh = [], {}
    folder = Path(folder).resolve()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"):
        st = path.stat()
        key = str(path.resolve())
        hit = cache.get(key)
        if hit and hit.get("size") == st.st_size and hit.get("mtime") == st.st_mtime:
            entry = hit
        else:
            ext = extract_pdf(path, max_pages=3)
            first = "\n".join(ext["pages"])
            entry = {"file": key, "rel": str(path.relative_to(folder)), "size": st.st_size, "mtime": st.st_mtime,
                     "first_text": first[:20000], "page1": (ext["pages"][0] if ext["pages"] else "")[:6000],
                     "dois": dois_in(first), "meta_title": _pdf_meta_title(path), "error": ext["error"],
                     "has_text": text_quality(ext["pages"])["chars"] >= 200}
        fresh[key] = entry
        entries.append(entry)
    if cache_file:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return entries


def _title_guess(entry: dict) -> str:
    if entry.get("meta_title") and len(entry["meta_title"]) > 8:
        return entry["meta_title"][:150]
    for line in (entry.get("page1") or "").split("\n"):
        if len(line.strip()) > 8:
            return line.strip()[:150]
    return ""


def match_sources(folder: Optional[Path], references: list, cache_file: Optional[Path] = None) -> dict:
    """Match each PDF in the sources folder to at most one reference, by DOI or title.

    File names are ignored. A PDF that carries a reference's DOI but shows another title is not
    matched to it, and the mismatch is reported (it is the mark of a chimeric reference)."""
    from rapidfuzz import fuzz

    result = {"folder": str(folder) if folder else None, "exists": bool(folder and Path(folder).is_dir()),
              "pdfs": [], "matches": {}, "unmatched_pdfs": [], "warnings": []}
    if not result["exists"]:
        return result
    entries = index_sources_folder(Path(folder).resolve(), cache_file)
    pairs = []
    for i, entry in enumerate(entries):
        if not entry.get("has_text"):
            continue
        words = set(norm_text(entry["first_text"][:15000] + " " + (entry.get("meta_title") or "")).split())
        for ref in references:
            fields = ref.fields or {}
            doi = norm_doi(fields.get("doi"))
            doi_hit = bool(doi and doi in entry.get("dois", []))
            title_words = [w for w in norm_text(fields.get("title")).split() if len(w) >= 4]
            if not doi_hit and (not title_words or sum(w in words for w in title_words) < 0.6 * len(title_words)):
                continue  # cheap filter before the fuzzy alignment
            ident = identify(fields, entry["first_text"])
            ts = ident["title_score"] or 0.0
            meta_ts = float(fuzz.ratio(norm_text(fields.get("title")), norm_text(entry.get("meta_title")))) if entry.get("meta_title") and fields.get("title") else 0.0
            au = ident["author_score"]
            early = ident.get("title_position") is not None and ident["title_position"] < 2500
            score, basis = 0.0, None
            if doi_hit and (ts >= 70 or meta_ts >= 80 or not fields.get("title")):
                score, basis = 300 + ts, "DOI and title"
            elif doi_hit:
                result["warnings"].append(
                    f"{entry['rel']} carries the DOI of {ref.id} ({ref.key or ''}, {doi}) but its first pages show another "
                    f"title ({_title_guess(entry)!r}); not matched to {ref.id}, whose DOI may belong to a different work.")
            elif max(ts, meta_ts) >= 90 and (au is None or au >= 0.5):
                score, basis = 200 + max(ts, meta_ts) + 20 * (au or 0) + (10 if early else 0), "title and authors" if au else "title"
            elif ts >= 97 and len(norm_text(fields.get("title")).split()) >= 6 and early:
                score, basis = 150 + ts, "title"
            if score:
                pairs.append((score, i, ref.id, basis, ident, doi_hit))
    taken_pdf, taken_ref = set(), set()
    for score, i, rid, basis, ident, doi_hit in sorted(pairs, key=lambda p: -p[0]):
        if i in taken_pdf or rid in taken_ref:
            continue
        taken_pdf.add(i)
        taken_ref.add(rid)
        e = entries[i]
        result["matches"][rid] = {"file": e["file"], "rel": e["rel"], "size": e["size"], "mtime": e["mtime"],
                                  "basis": basis, "score": round(score, 1), "doi_found": doi_hit,
                                  "title_score": ident["title_score"], "author_score": ident["author_score"]}
    by_file = {m["file"]: rid for rid, m in result["matches"].items()}
    for e in entries:
        rid = by_file.get(e["file"])
        info = {"file": e["rel"], "title_guess": _title_guess(e), "dois": e.get("dois", [])[:5], "matched_ref": rid}
        if not e.get("has_text"):
            info["problem"] = e.get("error") or "no text layer on the first pages (scanned PDF?); OCR is not available"
        result["pdfs"].append(info)
        if rid is None:
            result["unmatched_pdfs"].append(info)
    return result


# ================================================================ the cascade
@dataclass
class Candidate:
    url: str
    source: str
    version: str = "unknown"
    landing_page: Optional[str] = None
    license: Optional[str] = None
    oa_status: Optional[str] = None
    note: Optional[str] = None
    headers: dict = field(default_factory=dict)
    api: bool = False
    shown_url: Optional[str] = None      # what to record when `url` carries a secret


@dataclass
class _State:
    ref: object
    fields: dict
    doi: Optional[str]
    title: str
    keys: list
    year: Optional[int]
    doi_ok: Optional[bool] = None
    attempts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    tried: set = field(default_factory=set)
    ids: dict = field(default_factory=dict)
    arxiv: list = field(default_factory=list)
    nber: list = field(default_factory=list)
    abstracts: dict = field(default_factory=dict)
    candidate_versions: list = field(default_factory=list)
    openalex_work: Optional[dict] = None
    openalex_done: bool = False
    versions: Optional[list] = None
    s2_done: bool = False
    paid_hint: Optional[str] = None
    transient: bool = False
    result: Optional[dict] = None

    def attempt(self, step: str, outcome: str, url: Optional[str] = None) -> None:
        row = {"step": step, "outcome": outcome}
        if url:
            row["url"] = url
        self.attempts.append(row)

    def failed(self, step: str, what: str, response: "Response", url: Optional[str] = None) -> None:
        """Log a failed request; a rate limit or network error makes the next run try again."""
        if response.transient:
            self.transient = True
        self.attempt(step, f"{what}: {response.describe()}" if what else response.describe(), url)

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)


def _year(value) -> Optional[int]:
    m = re.search(r"\d{4}", str(value or ""))
    return int(m.group(0)) if m else None


def _version(value) -> str:
    return VERSION_NAMES.get(str(value or "").replace(" ", "").lower(), "unknown")


class Cascade:
    """Runs the full-text cascade for one reference at a time and writes WORK/citations/sources/."""

    def __init__(self, fetcher: Fetcher, out_dir: Path, *, email: Optional[str] = None,
                 openalex_key: Optional[str] = None, s2_key: Optional[str] = None, core_key: Optional[str] = None,
                 paid_pdfs: bool = False, source_matches: Optional[dict] = None, sources_folder: Optional[str] = None,
                 offline: bool = False):
        self.fetcher = fetcher
        self.out_dir = Path(out_dir)
        self.email = email
        self.openalex_key = openalex_key
        self.s2_key = s2_key
        self.core_key = core_key
        self.paid_pdfs = paid_pdfs
        self.source_matches = source_matches or {}
        self.sources_folder = sources_folder
        self.offline = offline
        self.service_notes: dict = {}
        self.disabled: dict = {}
        self._openalex_key_off = False

    # ---------------------------------------------------------------- driver
    def run(self, ref, steps: Optional[Iterable[str]] = None) -> dict:
        fields = dict(ref.fields or {})
        st = _State(ref=ref, fields=fields, doi=norm_doi(fields.get("doi")), title=fields.get("title") or "",
                    keys=family_keys(fields.get("authors")), year=_year(fields.get("year")))
        st.arxiv = arxiv_ids(fields, ref.raw)
        st.nber = nber_numbers(fields, ref.raw)
        wanted = list(steps) if steps else list(STEPS)
        for step in STEPS:
            if step not in wanted:
                continue
            if step in self.disabled:
                st.attempt(step, f"skipped: {self.disabled[step]}")
                continue
            try:
                if getattr(self, f"_step_{step}")(st):
                    break
            except Exception as exc:  # one broken service must not stop the run
                st.attempt(step, f"error: {type(exc).__name__}: {self.fetcher.scrub(str(exc))[:200]}")
        if st.result is None:
            st.result = self._finish_not_found(st)
        return st.result

    # ---------------------------------------------------------------- shared pieces
    def _matches(self, st: _State, title: Optional[str], keys: list, year, by_id: bool) -> bool:
        """Is this record the referenced work? Stricter for search results than for identifier lookups."""
        sim = title_similarity(st.title, title)
        overlap = author_overlap(st.keys, keys)
        if not st.title:
            return bool(by_id) and (overlap is None or overlap >= 0.5)
        if by_id:
            return sim >= 75 or (sim >= 50 and overlap is not None and overlap >= 0.5)
        y = _year(year)
        if st.year and y and abs(st.year - y) > 8:
            return False
        if overlap is None:
            return sim >= 95 and (not st.year or not y or abs(st.year - y) <= 2)
        return (sim >= 92 and overlap >= 0.5) or (sim >= 85 and overlap >= 0.99)

    def _openalex_url(self, path: str) -> str:
        sep = "&" if "?" in path else "?"
        if self.openalex_key and not self._openalex_key_off:
            return f"https://api.openalex.org{path}{sep}api_key={urllib.parse.quote(self.openalex_key)}"
        if self.email:
            return f"https://api.openalex.org{path}{sep}mailto={urllib.parse.quote(self.email)}"
        return f"https://api.openalex.org{path}"

    def _openalex_get(self, path: str) -> Response:
        response = self.fetcher.get(self._openalex_url(path), api=True, accept="application/json")
        if (response.status in (401, 403) and self.openalex_key and not self._openalex_key_off
                and b"key" in response.body[:2000].lower()):
            reason = self.fetcher.scrub(response.text()[:120]).strip()
            self._openalex_key_off = True
            self.service_notes["openalex"] = f"API key refused ({reason}); OpenAlex was used without it"
            response = self.fetcher.get(self._openalex_url(path), api=True, accept="application/json")
        return response

    @staticmethod
    def _oa_keys(work: dict) -> list:
        return names_from_display(((a.get("author") or {}).get("display_name") or a.get("raw_author_name") or "")
                                  for a in work.get("authorships") or [])

    def _openalex_work(self, st: _State) -> Optional[dict]:
        if st.openalex_done:
            return st.openalex_work
        st.openalex_done = True
        work = None
        if st.doi and st.doi_ok is not False:
            response = self._openalex_get(f"/works/doi:{urllib.parse.quote(st.doi, safe='/')}")
            record = response.json() if response.ok else None
            if record and record.get("id"):
                if self._matches(st, record.get("title") or record.get("display_name"), self._oa_keys(record),
                                 record.get("publication_year"), by_id=True):
                    work = record
                    st.doi_ok = True
                else:
                    st.doi_ok = False
                    names = ", ".join(((a.get("author") or {}).get("display_name") or "") for a in (record.get("authorships") or [])[:3])
                    st.warn(f"The DOI {st.doi} belongs to a different work in OpenAlex: "
                            f"'{record.get('title')}' ({names}, {record.get('publication_year')}). It was not used.")
            elif response.status == 404:
                st.attempt("openalex", "DOI not found in OpenAlex")
            else:
                st.failed("openalex", "DOI lookup failed", response)
        if work is None and st.title:
            for record in self._openalex_title_search(st):
                if self._matches(st, record.get("title"), self._oa_keys(record), record.get("publication_year"), by_id=False):
                    work = record
                    break
        st.openalex_work = work
        if work:
            st.ids["openalex"] = (work.get("id") or "").rsplit("/", 1)[-1]
            abstract = openalex_abstract(work.get("abstract_inverted_index"))
            if abstract:
                st.abstracts.setdefault("openalex", abstract)
            self._collect_ids(st, work)
            if (work.get("has_content") or {}).get("pdf"):
                st.paid_hint = ("OpenAlex holds a cached PDF of this work. It is a paid download and stays off "
                                "unless paid_pdfs: true is set in paper-check.yaml.")
        return work

    def _openalex_title_search(self, st: _State) -> list:
        words = " ".join(norm_text(st.title).split()[:30])
        if not words:
            return []
        response = self._openalex_get(f"/works?filter=title.search:{urllib.parse.quote(words)}&per_page=10")
        data = response.json() if response.ok else None
        if not data:
            st.failed("openalex", "title search failed", response)
            return []
        return data.get("results") or []

    def _collect_ids(self, st: _State, work: dict) -> None:
        """arXiv ids and NBER numbers that an OpenAlex record reveals."""
        doi = norm_doi(work.get("doi"))
        hay = " ".join(filter(None, [doi] + [(loc.get("landing_page_url") or "") + " " + (loc.get("pdf_url") or "")
                                             for loc in work.get("locations") or []]))
        for m in re.finditer(rf"arxiv\.org/(?:abs|pdf)/{_ARXIV_ID}|10\.48550/arxiv\.{_ARXIV_ID}", hay, re.I):
            aid = m.group(1) or m.group(2)
            if aid and aid not in st.arxiv:
                st.arxiv.append(aid)
        for m in re.finditer(r"10\.3386/w(\d{1,6})\b|nber\.org/papers/w(\d{1,6})\b", hay, re.I):
            number = m.group(1) or m.group(2)
            if number not in st.nber:
                st.nber.append(number)

    def _openalex_versions(self, st: _State) -> list:
        """Other OpenAlex records of the same work: working papers, preprints, repository copies."""
        if st.versions is not None:
            return st.versions
        st.versions = []
        if not st.title:
            return st.versions
        main = self._openalex_work(st)
        main_id = (main or {}).get("id")
        for record in self._openalex_title_search(st):
            if record.get("id") == main_id:
                continue
            if title_similarity(st.title, record.get("title")) < 92:
                continue
            overlap = author_overlap(st.keys, self._oa_keys(record))
            if overlap is None or overlap < 0.5:
                continue  # without author agreement a same-titled record may be another work
            y = _year(record.get("publication_year"))
            if st.year and y and abs(st.year - y) > 8:
                continue
            st.versions.append(record)
            self._collect_ids(st, record)
        return st.versions

    def _location_candidates(self, work: dict, source: str, note: Optional[str] = None) -> list:
        out, seen = [], set()
        best = work.get("best_oa_location") or {}
        locations = [best] + sorted((loc for loc in work.get("locations") or [] if loc.get("is_oa")),
                                    key=lambda loc: VERSION_RANK.get(_version(loc.get("version")), 3))
        for loc in locations:
            if not loc:
                continue
            url = loc.get("pdf_url") or (loc.get("landing_page_url") if loc.get("is_oa") else None)
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(Candidate(url=url, source=source, version=_version(loc.get("version")),
                                 landing_page=loc.get("landing_page_url"), license=loc.get("license"),
                                 oa_status=(work.get("open_access") or {}).get("oa_status"), note=note))
        return out

    # ---------------------------------------------------------------- fetching one candidate
    def _try(self, st: _State, cand: Candidate, hop: int = 0) -> bool:
        if cand.url.startswith("http://") and not cand.shown_url:
            secure = "https://" + cand.url[len("http://"):]   # prefer HTTPS; fall back to the address as listed
            if secure not in st.tried and self._try(st, dataclasses.replace(cand, url=secure), hop):
                return True
        shown = cand.shown_url or strip_secrets(cand.url)
        if cand.url in st.tried:
            st.attempt(cand.source, "same URL as an earlier step; not fetched again", shown)
            return False
        st.tried.add(cand.url)
        response = self.fetcher.get(cand.url, accept="application/pdf, */*;q=0.5", api=cand.api,
                                    headers=cand.headers, timeout=90)
        if not response.ok:
            if is_challenge(response):
                st.attempt(cand.source, "blocked by bot protection (not bypassed)", shown)
            else:
                st.failed(cand.source, "", response, shown)
            return False
        body = response.body
        if not body.lstrip()[:8].startswith(b"%PDF"):
            link = citation_pdf_url(body, response.final_url or cand.url) if b"<" in body[:4000] else None
            if link and hop == 0 and link not in st.tried:
                follow = dataclasses.replace(cand, url=link, shown_url=None,
                                             landing_page=cand.landing_page or strip_secrets(cand.url))
                st.attempt(cand.source, "landing page; following its citation_pdf_url", shown)
                return self._try(st, follow, hop=1)
            if is_challenge(response):
                self.fetcher.mark_negative(cand.url)
                st.attempt(cand.source, "blocked by bot protection (not bypassed)", shown)
            else:
                st.attempt(cand.source, f"not a PDF ({response.content_type or 'unknown type'})", shown)
            return False
        verdict = {}

        def check(first_pages: str) -> bool:
            verdict.update(identify(st.fields, first_pages))
            return bool(verdict["ok"]) or not text_quality([first_pages])["usable"]

        ext = extract_pdf(body, check=check)
        if ext["error"]:
            st.attempt(cand.source, f"PDF could not be read: {ext['error']}", shown)
            return False
        quality = text_quality(ext["pages"])
        if not quality["usable"]:
            st.attempt(cand.source, "PDF has no usable text layer (scanned?); OCR is not available", shown)
            st.warn(f"A PDF was found at {shown} but has no usable text layer; OCR is not available.")
            return False
        ident = verdict or identify(st.fields, "\n".join(ext["pages"][:3]))
        if ext["rejected"] or not ident["ok"]:
            st.attempt(cand.source, f"PDF rejected: {ident['basis']} (title score {ident['title_score']})", shown)
            return False
        st.attempt(cand.source, "ok", shown)
        self._save_fulltext(st, ext, quality, ident, cand, shown, pdf_bytes=body)
        return True

    # ---------------------------------------------------------------- steps
    def _step_sources(self, st: _State) -> bool:
        match = self.source_matches.get(st.ref.id)
        if not match:
            st.attempt("sources", "no matching PDF in the sources folder" if self.sources_folder else "no sources folder")
            return False
        ext = extract_pdf(Path(match["file"]))
        quality = text_quality(ext["pages"]) if not ext["error"] else {"usable": False}
        if ext["error"] or not quality["usable"]:
            st.attempt("sources", f"matched PDF {match['rel']} has no usable text ({ext['error'] or 'scanned?'})")
            st.warn(f"The sources-folder PDF {match['rel']} matched this reference but has no usable text layer; OCR is not available.")
            return False
        version, basis = guess_version(ext["pages"][0] if ext["pages"] else "", st.fields)
        ident = identify(st.fields, "\n".join(ext["pages"][:3]))
        cand = Candidate(url=match["file"], source="sources", version=version,
                         note=f"user-supplied PDF, matched by {match['basis']}")
        st.attempt("sources", "ok", match["rel"])
        self._save_fulltext(st, ext, quality, ident, cand, match["file"], pdf_path=match["file"], version_basis=basis,
                            extra={"sources_match": match})
        return True

    def _step_openalex(self, st: _State) -> bool:
        work = self._openalex_work(st)
        if not work:
            st.attempt("openalex", "no matching OpenAlex record")
            return False
        candidates = self._location_candidates(work, "openalex")
        if not candidates:
            st.attempt("openalex", f"no open-access location ({(work.get('open_access') or {}).get('oa_status') or 'closed'})")
            return False
        return any(self._try(st, c) for c in candidates)

    def _step_unpaywall(self, st: _State) -> bool:
        if not st.doi:
            st.attempt("unpaywall", "skipped: the reference has no DOI")
            return False
        if st.doi_ok is False:
            st.attempt("unpaywall", "skipped: the DOI belongs to a different work")
            return False
        if not self.email:
            st.attempt("unpaywall", "skipped: no contact email configured (Unpaywall requires one)")
            return False
        response = self.fetcher.get(f"https://api.unpaywall.org/v2/{urllib.parse.quote(st.doi, safe='/')}"
                                    f"?email={urllib.parse.quote(self.email)}", api=True, accept="application/json")
        record = response.json() if response.ok else None
        if not record:
            if response.status == 404:
                st.attempt("unpaywall", "DOI not in Unpaywall")
            else:
                st.failed("unpaywall", "lookup failed", response)
            return False
        keys = family_keys(record.get("z_authors") or [])
        if not self._matches(st, record.get("title"), keys, record.get("year"), by_id=True):
            st.doi_ok = False
            st.warn(f"The DOI {st.doi} belongs to a different work in Unpaywall: '{record.get('title')}'. It was not used.")
            st.attempt("unpaywall", "DOI belongs to a different work")
            return False
        locations = [record.get("best_oa_location")] + sorted(record.get("oa_locations") or [],
                                                               key=lambda l: VERSION_RANK.get(_version(l.get("version")), 3))
        candidates, seen = [], set()
        for loc in locations:
            if not loc:
                continue
            url = loc.get("url_for_pdf") or loc.get("url")
            if url and url not in seen:
                seen.add(url)
                candidates.append(Candidate(url=url, source="unpaywall", version=_version(loc.get("version")),
                                            landing_page=loc.get("url_for_landing_page") or loc.get("url"),
                                            license=loc.get("license"), oa_status=record.get("oa_status")))
        if not candidates:
            st.attempt("unpaywall", f"no open-access location ({record.get('oa_status') or 'closed'})")
            return False
        return any(self._try(st, c) for c in candidates)

    def _s2_record(self, st: _State) -> Optional[dict]:
        if st.s2_done:
            return st.ids.get("_s2")
        st.s2_done = True
        base = "https://api.semanticscholar.org/graph/v1/paper"
        fields = "title,year,authors,externalIds,openAccessPdf,isOpenAccess,abstract"
        headers = {"x-api-key": self.s2_key} if self.s2_key else {}
        if st.doi and st.doi_ok is not False:
            url, by_id = f"{base}/DOI:{urllib.parse.quote(st.doi, safe='/')}?fields={fields}", True
        elif st.arxiv:
            url, by_id = f"{base}/ARXIV:{st.arxiv[0]}?fields={fields}", True
        elif st.title:
            url, by_id = f"{base}/search/match?query={urllib.parse.quote(norm_text(st.title))}&fields={fields}", False
        else:
            return None
        response = self.fetcher.get(url, api=True, headers=headers, accept="application/json")
        if response.status == 404 and by_id and st.title:
            # its DOI index misses many older economics articles; the title match often finds them
            url, by_id = f"{base}/search/match?query={urllib.parse.quote(norm_text(st.title))}&fields={fields}", False
            response = self.fetcher.get(url, api=True, headers=headers, accept="application/json")
        if response.status == 429:
            self.disabled["semantic_scholar"] = "rate limited" + ("" if self.s2_key else " (no API key)")
            st.attempt("semantic_scholar", self.disabled["semantic_scholar"])
            return None
        data = response.json() if response.ok else None
        if data and "data" in data:
            data = (data.get("data") or [None])[0]
        if not data:
            if response.status in (200, 404):
                st.attempt("semantic_scholar", "no matching record")
            else:
                st.failed("semantic_scholar", "lookup failed", response)
            return None
        keys = names_from_display(a.get("name") or "" for a in data.get("authors") or [])
        if not self._matches(st, data.get("title"), keys, data.get("year"), by_id=by_id):
            if by_id and st.doi:
                st.doi_ok = False
                st.warn(f"The DOI {st.doi} belongs to a different work in Semantic Scholar: '{data.get('title')}'. It was not used.")
            st.attempt("semantic_scholar", "the record found is a different work")
            return None
        ext_ids = data.get("externalIds") or {}
        if ext_ids.get("ArXiv") and ext_ids["ArXiv"] not in st.arxiv:
            st.arxiv.append(ext_ids["ArXiv"])
        if data.get("abstract"):
            st.abstracts.setdefault("semantic_scholar", strip_tags(data["abstract"]))
        st.ids["semantic_scholar"] = data.get("paperId")
        st.ids["_s2"] = data
        return data

    def _step_semantic_scholar(self, st: _State) -> bool:
        data = self._s2_record(st)
        if not data:
            return False
        pdf = data.get("openAccessPdf") or {}
        if not pdf.get("url"):
            st.attempt("semantic_scholar", f"no open-access PDF ({pdf.get('status') or 'closed'})")
            return False
        status = str(pdf.get("status") or "").upper()
        version = "published" if status in ("GOLD", "HYBRID", "BRONZE") else "unknown"
        return self._try(st, Candidate(url=pdf["url"], source="semantic_scholar", version=version,
                                       license=pdf.get("license"), oa_status=status.lower() or None))

    def _arxiv_search(self, st: _State) -> list:
        from lxml import etree

        words = " ".join(norm_text(st.title).split()[:20])
        if not words:
            return []
        query = urllib.parse.quote(f'ti:"{words}"')
        response = self.fetcher.get(f"https://export.arxiv.org/api/query?search_query={query}&max_results=5",
                                    api=True, accept="application/atom+xml")
        if not response.ok:
            st.failed("arxiv", "title search failed", response)
            return []
        parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
        try:
            root = etree.fromstring(response.body, parser)
        except Exception:
            return []
        ns = {"a": "http://www.w3.org/2005/Atom"}
        found = []
        for entry in root.findall("a:entry", ns):
            title = " ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split())
            names = [n.findtext("a:name", default="", namespaces=ns) for n in entry.findall("a:author", ns)]
            year = (entry.findtext("a:published", default="", namespaces=ns) or "")[:4]
            m = re.search(rf"arxiv\.org/abs/{_ARXIV_ID}", entry.findtext("a:id", default="", namespaces=ns) or "")
            if m and self._matches(st, title, names_from_display(names), year, by_id=False):
                found.append(m.group(1))
        return found

    def _step_arxiv(self, st: _State) -> bool:
        if not st.arxiv and st.title:
            self._openalex_versions(st)
        if not st.arxiv and st.title:
            st.arxiv.extend(a for a in self._arxiv_search(st) if a not in st.arxiv)
        if not st.arxiv:
            st.attempt("arxiv", "no arXiv version found")
            return False
        for aid in st.arxiv:
            st.ids.setdefault("arxiv", aid)
            cand = Candidate(url=f"https://arxiv.org/pdf/{aid}", source="arxiv", version="submitted",
                             landing_page=f"https://arxiv.org/abs/{aid}",
                             note="arXiv preprint; it may differ from the published article")
            if self._try(st, cand):
                return True
        return False

    def _nber_search(self, st: _State) -> None:
        """Crossref search restricted to NBER's DOI prefix, matched strictly on title and authors."""
        query = " ".join([norm_text(st.title)] + st.keys)
        url = (f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(query)}"
               f"&filter=prefix:10.3386&rows=5&select=DOI,title,author,issued")
        if self.email:
            url += f"&mailto={urllib.parse.quote(self.email)}"
        response = self.fetcher.get(url, api=True, accept="application/json")
        data = response.json() if response.ok else None
        if not data:
            st.failed("nber", "Crossref search failed", response)
            return
        for item in (data.get("message") or {}).get("items") or []:
            title = (item.get("title") or [""])[0]
            keys = family_keys(item.get("author") or [])
            m = re.match(r"10\.3386/w(\d+)$", (item.get("DOI") or "").lower())
            if not m:
                continue
            sim, overlap = title_similarity(st.title, title), author_overlap(st.keys, keys)
            year = ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            if sim >= 92 and (overlap is None or overlap >= 0.5):
                if m.group(1) not in st.nber:
                    st.nber.append(m.group(1))
            elif (st.keys and sorted(set(keys)) == sorted(set(st.keys)) and st.year and year
                  and st.year - 6 <= int(year) <= st.year + 1):
                # same author team, a working paper up to six years before the cited version
                st.candidate_versions.append({
                    "doi": item.get("DOI"), "title": title, "year": year,
                    "note": "NBER working paper by the same authors under another title; possibly an earlier "
                            "version of this work. Not used automatically: add its PDF to the sources folder if it is."})

    def _step_nber(self, st: _State) -> bool:
        if not st.nber and st.title:
            self._openalex_versions(st)
        if not st.nber and st.title:
            self._nber_search(st)
        if not st.nber:
            st.attempt("nber", "no NBER working paper found")
            return False
        for number in st.nber:
            st.ids.setdefault("nber", f"w{number}")
            cand = Candidate(url=f"https://www.nber.org/system/files/working_papers/w{number}/w{number}.pdf",
                             source="nber", version="submitted", landing_page=f"https://www.nber.org/papers/w{number}",
                             note=f"NBER working paper w{number}; it may differ from the published article")
            if self._try(st, cand):
                return True
        return False

    def _step_openalex_versions(self, st: _State) -> bool:
        versions = self._openalex_versions(st)
        candidates = []
        for record in versions:
            kind = record.get("type") or "record"
            source_name = ((record.get("primary_location") or {}).get("source") or {}).get("display_name")
            note = (f"another OpenAlex record of the same work ({kind}{', ' + source_name if source_name else ''}, "
                    f"{record.get('publication_year')}); it may differ from the published article")
            candidates.extend(self._location_candidates(record, "openalex_versions", note))
        if not candidates:
            st.attempt("openalex_versions", "no open-access copy among other records of this work")
            return False
        return any(self._try(st, c) for c in candidates)

    def _step_core(self, st: _State) -> bool:
        if not self.core_key:
            st.attempt("core", "skipped: no CORE API key (core_api_key in ~/.paper-check/config.yaml)")
            return False
        if st.doi and st.doi_ok is not False:
            query, by_id = f'doi:"{st.doi}"', True
        elif st.title:
            query, by_id = f'title:"{norm_text(st.title)}"', False
        else:
            st.attempt("core", "skipped: no DOI or title")
            return False
        response = self.fetcher.get(f"https://api.core.ac.uk/v3/search/works?q={urllib.parse.quote(query)}&limit=5",
                                    api=True, accept="application/json",
                                    headers={"Authorization": f"Bearer {self.core_key}"})
        data = response.json() if response.ok else None
        if not data:
            st.failed("core", "search failed", response)
            return False
        texts = []
        for item in data.get("results") or []:
            keys = names_from_display(a.get("name") or "" for a in item.get("authors") or [])
            if not self._matches(st, item.get("title"), keys, item.get("yearPublished"), by_id=by_id):
                continue
            if item.get("downloadUrl"):
                cand = Candidate(url=item["downloadUrl"], source="core", version="unknown",
                                 landing_page=(item.get("links") or [{}])[0].get("url") if item.get("links") else None)
                if self._try(st, cand):
                    return True
            if item.get("fullText") and len(item["fullText"]) > 2000:
                texts.append(item)
        if texts:
            item = texts[0]
            self._save_plain_text(st, item["fullText"], source="core",
                                  url=f"https://core.ac.uk/works/{item.get('id')}" if item.get("id") else None)
            st.attempt("core", "ok (full text without page numbers)")
            return True
        st.attempt("core", "no matching full text")
        return False

    def _step_openalex_content(self, st: _State) -> bool:
        if not self.paid_pdfs:
            st.attempt("openalex_content", "skipped: paid PDFs are off (paid_pdfs: false)")
            return False
        if not self.openalex_key or self._openalex_key_off:
            st.attempt("openalex_content", "skipped: needs a working OpenAlex API key")
            return False
        work = self._openalex_work(st)
        if not work or not (work.get("has_content") or {}).get("pdf"):
            st.attempt("openalex_content", "OpenAlex holds no cached PDF of this work")
            return False
        wid = (work.get("id") or "").rsplit("/", 1)[-1]
        url = f"https://content.openalex.org/works/{wid}.pdf"
        cand = Candidate(url=f"{url}?api_key={urllib.parse.quote(self.openalex_key)}", source="openalex_content",
                         version="unknown", shown_url=url, api=True,
                         note="OpenAlex cached PDF (paid download, allowed by paid_pdfs)")
        return self._try(st, cand)

    def _step_abstract(self, st: _State) -> bool:
        if not st.openalex_done and "openalex" not in self.disabled:
            self._openalex_work(st)
        text, source = st.abstracts.get("openalex"), "openalex_abstract"
        if not text and st.doi and st.doi_ok is not False:
            url = f"https://api.crossref.org/works/{urllib.parse.quote(st.doi, safe='/')}"
            if self.email:
                url += f"?mailto={urllib.parse.quote(self.email)}"
            response = self.fetcher.get(url, api=True, accept="application/json")
            message = ((response.json() or {}).get("message") or {}) if response.ok else {}
            if message.get("abstract") and self._matches(st, (message.get("title") or [""])[0],
                                                         family_keys(message.get("author") or []), None, by_id=True):
                text, source = strip_tags(message["abstract"]), "crossref_abstract"
        if not text and st.abstracts.get("semantic_scholar"):
            text, source = st.abstracts["semantic_scholar"], "semantic_scholar_abstract"
        if not text:
            st.attempt("abstract", "no abstract found")
            return False
        st.attempt("abstract", f"ok ({source})")
        out = self.out_dir
        out.mkdir(parents=True, exist_ok=True)
        body = f"[[abstract]]\n{text}\n"
        (out / f"{st.ref.id}.txt").write_text(body, encoding="utf-8")
        self._remove(out / f"{st.ref.id}.pdf")
        meta = self._base_meta(st)
        if source == "openalex_abstract" and st.openalex_work:
            url = st.openalex_work.get("id")
        elif source == "crossref_abstract":
            url = f"https://doi.org/{st.doi}"
        elif st.ids.get("semantic_scholar"):
            url = f"https://www.semanticscholar.org/paper/{st.ids['semantic_scholar']}"
        else:
            url = None
        meta.update({"status": "abstract_only", "source": source, "url": url, "version": "abstract",
                     "pages": 0, "abstract_only": True, "chars": len(text), "file": f"sources/{st.ref.id}.txt",
                     "note": ABSTRACT_NOTE, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()})
        st.result = self._write_meta(st, meta)
        return False  # an abstract is not full text; the cascade ends here anyway

    # ---------------------------------------------------------------- outputs
    @staticmethod
    def _remove(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _base_meta(self, st: _State) -> dict:
        now = dt.datetime.now(dt.timezone.utc)
        meta = {"ref": st.ref.id, "key": st.ref.key, "title": st.title or None, "doi": st.doi,
                "fetched": now.date().isoformat(), "fetched_at": now.isoformat(timespec="seconds"),
                "offline": self.offline, "transient_failure": st.transient, "attempts": st.attempts,
                "warnings": st.warnings, "ids": {k: v for k, v in st.ids.items() if not k.startswith("_") and v}}
        abstract = st.abstracts.get("openalex") or st.abstracts.get("semantic_scholar")
        if abstract:
            meta["abstract"] = abstract[:4000]
        if st.candidate_versions:
            meta["candidate_versions"] = st.candidate_versions
        if st.paid_hint and not self.paid_pdfs:
            meta["paid_pdf_available"] = st.paid_hint
        return meta

    def _write_meta(self, st: _State, meta: dict) -> dict:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / f"{st.ref.id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return meta

    def _save_fulltext(self, st: _State, ext: dict, quality: dict, ident: dict, cand: Candidate, shown: str,
                       pdf_bytes: Optional[bytes] = None, pdf_path: Optional[str] = None,
                       version_basis: Optional[str] = None, extra: Optional[dict] = None) -> None:
        out = self.out_dir
        out.mkdir(parents=True, exist_ok=True)
        text = pages_to_text(ext["pages"])
        (out / f"{st.ref.id}.txt").write_text(text, encoding="utf-8")
        if pdf_bytes is not None:
            (out / f"{st.ref.id}.pdf").write_bytes(pdf_bytes)
            pdf = f"sources/{st.ref.id}.pdf"
        else:
            self._remove(out / f"{st.ref.id}.pdf")
            pdf = pdf_path
        meta = self._base_meta(st)
        meta.update({
            "status": "full_text", "source": cand.source, "url": shown, "landing_page": cand.landing_page,
            "version": cand.version,
            "version_basis": version_basis or ("as labelled by the service" if cand.version != "unknown" else "not labelled"),
            "license": cand.license, "oa_status": cand.oa_status, "pages": ext["n_pages"],
            "pages_with_text": quality["pages_with_text"], "chars": len(text), "truncated": ext["truncated"],
            "abstract_only": False, "file": f"sources/{st.ref.id}.txt", "pdf": pdf, "identity": ident,
            "note": cand.note, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
        if ext["truncated"]:
            st.warn(f"Only the first {MAX_PAGES} of {ext['n_pages']} pages were extracted.")
        meta.update(extra or {})
        meta = {k: v for k, v in meta.items() if v is not None}
        st.result = self._write_meta(st, meta)

    def _save_plain_text(self, st: _State, text: str, source: str, url: Optional[str]) -> None:
        out = self.out_dir
        out.mkdir(parents=True, exist_ok=True)
        body = f"[[text]]\n{clean_page_text(text)}\n"
        (out / f"{st.ref.id}.txt").write_text(body, encoding="utf-8")
        self._remove(out / f"{st.ref.id}.pdf")
        meta = self._base_meta(st)
        meta.update({"status": "full_text", "source": source, "url": url, "version": "unknown",
                     "version_basis": "not labelled", "pages": None, "abstract_only": False, "chars": len(body),
                     "file": f"sources/{st.ref.id}.txt",
                     "note": "full text without page numbers; cite passages without a page",
                     "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()})
        st.result = self._write_meta(st, {k: v for k, v in meta.items() if v is not None})

    def _finish_not_found(self, st: _State) -> dict:
        self._remove(self.out_dir / f"{st.ref.id}.txt")
        self._remove(self.out_dir / f"{st.ref.id}.pdf")
        meta = self._base_meta(st)
        meta.update({"status": "not_found", "source": None, "url": None, "version": None, "pages": None,
                     "abstract_only": False, "file": None,
                     "note": NOT_FOUND_NOTE + (" (offline: network sources were not tried)" if self.offline else "")})
        return self._write_meta(st, meta)
