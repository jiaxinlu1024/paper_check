"""Crossref REST API: DOI lookups, bibliographic search, editorial updates.

- Polite pool: every request carries `mailto=<contact>`, and the user agent names it too.
  Limits since December 2025: 10 requests per second for DOI lookups, 3 for searches and
  lists, 3 concurrent. The client uses two rate buckets for that.
- Search: `query.bibliographic` on the raw reference string, as Crossref's search-based
  matcher does, then field-by-field validation by the policy. Crossref's relevance score
  is kept but never used as a threshold; Crossref staff say no score works for every query.
- Notices: a work's `updated-by` lists retractions, corrections and expressions of
  concern, with `source` "publisher" or "retraction-watch". The notices themselves come from
  `filter=updates:{doi}`; each one's `update-to` points back at the work. Repeating the
  filter ORs it, so up to 20 DOIs go in one request.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Optional

from .http import HttpClient, Response
from .records import Query, Record, query_from

BASE = "https://api.crossref.org"
SELECT = ("DOI,title,subtitle,author,editor,issued,published,published-print,published-online,posted,"
          "container-title,short-container-title,volume,issue,page,article-number,type,score,publisher,"
          "update-to,updated-by,relation,URL,group-title")
UPDATES_BATCH = 20


def doi_path(doi: str) -> str:
    return urllib.parse.quote(doi.strip(), safe="/:()._-;")


def _year(date: Optional[dict]) -> Optional[int]:
    try:
        y = (date or {}).get("date-parts", [[None]])[0][0]
        return int(y) if y else None
    except (TypeError, ValueError, IndexError):
        return None


def _date(date: Optional[dict]) -> Optional[str]:
    try:
        parts = [p for p in (date or {}).get("date-parts", [[]])[0] if p]
    except (TypeError, IndexError):
        return None
    return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts)) if parts else None


def _first(value) -> Optional[str]:
    if isinstance(value, list):
        return str(value[0]).strip() if value else None
    return str(value).strip() if value else None


def _notice(u: dict) -> dict:
    return {k: v for k, v in {
        "doi": (u.get("DOI") or "").lower() or None, "type": u.get("type"), "label": u.get("label"),
        "source": u.get("source"), "date": _date(u.get("updated")), "record_id": u.get("record-id"),
    }.items() if v}


def parse_work(m: dict, api_url: Optional[str] = None) -> Record:
    title = _first(m.get("title")) or ""
    subtitle = _first(m.get("subtitle"))
    if subtitle and subtitle.lower() not in title.lower():
        title = f"{title}: {subtitle}" if title else subtitle
    people = m.get("author") or m.get("editor") or []
    authors = []
    for a in people:
        fam = (a.get("family") or "").strip()
        authors.append({k: v for k, v in {"family": fam or None, "given": (a.get("given") or "").strip() or None,
                                          "name": a.get("name") if not fam else None}.items() if v})
    years = [y for y in (_year(m.get(k)) for k in ("issued", "published-print", "published-online", "published",
                                                    "posted")) if y]
    containers = [c for c in (m.get("container-title") or []) + (m.get("short-container-title") or []) if c]
    if not containers and m.get("group-title"):
        containers = [m["group-title"]]
    doi = (m.get("DOI") or "").lower() or None
    number = None
    if doi and doi.startswith("10.3386/"):
        number = doi.split("/", 1)[1]
    pages = m.get("page") or m.get("article-number")
    return Record(
        source="crossref", id=doi or "", title=title, authors=authors,
        year=_year(m.get("issued")) or (years[0] if years else None), years=sorted(set(years)),
        container=containers[0] if containers else None, containers=containers,
        volume=m.get("volume"), issue=m.get("issue"), pages=pages, doi=doi, url=m.get("URL"),
        type=m.get("type"), publisher=m.get("publisher"), number=number,
        notices=[_notice(u) for u in (m.get("updated-by") or [])],
        update_to=[_notice(u) for u in (m.get("update-to") or [])],
        relations=m.get("relation") or {}, api_url=api_url, score=m.get("score"),
        extra={k: v for k, v in {"article_number": m.get("article-number")}.items() if v},
    )


def _trim_work(body: bytes) -> bytes:
    """Drop the deposited reference list, which can be large and is never used."""
    try:
        data = json.loads(body)
    except ValueError:
        return body
    msg = data.get("message") if isinstance(data, dict) else None
    if isinstance(msg, dict):
        for k in ("reference", "assertion", "link", "license"):
            msg.pop(k, None)
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _empty_list(resp: Response) -> bool:
    data = resp.json() or {}
    return not ((data.get("message") or {}).get("items"))


class Crossref:
    name = "crossref"

    def __init__(self, http: HttpClient, mailto: Optional[str] = None):
        self.http = http
        self.mailto = mailto

    def _params(self, extra: Optional[dict] = None) -> dict:
        params = dict(extra or {})
        if self.mailto:
            params["mailto"] = self.mailto
        return params

    def work(self, doi: str) -> tuple:
        """(Record or None, Query) for one DOI."""
        resp = self.http.get(f"{BASE}/works/{doi_path(doi)}", self._params(), bucket="crossref",
                             headers={"Accept": "application/json"}, transform=_trim_work)
        rec = None
        if resp.ok:
            msg = (resp.json() or {}).get("message")
            if isinstance(msg, dict):
                rec = parse_work(msg, resp.url)
        q = query_from(self.name, "doi", doi, resp, 1 if rec else 0)
        if resp.ok and rec is None:
            q.status, q.detail = "error", "unreadable answer"
        return rec, q

    def search(self, text: str, rows: int = 10, filters: Optional[dict] = None) -> tuple:
        """([Record], Query) for a bibliographic search, best first."""
        text = re.sub(r"\s+", " ", text or "").strip()[:500]
        params = {"query.bibliographic": text, "rows": rows, "select": SELECT}
        if filters:
            params["filter"] = ",".join(f"{k}:{v}" for k, v in filters.items())
        resp = self.http.get(f"{BASE}/works", self._params(params), bucket="crossref-search",
                             headers={"Accept": "application/json"}, negative_if=_empty_list)
        recs = []
        if resp.ok:
            for item in ((resp.json() or {}).get("message") or {}).get("items") or []:
                recs.append(parse_work(item, resp.url))
        label = text if not filters else f"{text} [{params['filter']}]"
        return recs, query_from(self.name, "search", label, resp, len(recs))

    def updates(self, dois: list) -> tuple:
        """Notices that update any of the DOIs: ({doi: [notice]}, [Query])."""
        found: dict = {}
        queries = []
        dois = sorted({d.lower() for d in dois if d})
        for i in range(0, len(dois), UPDATES_BATCH):
            batch = dois[i:i + UPDATES_BATCH]
            params = {"filter": ",".join(f"updates:{d}" for d in batch), "rows": 100,
                      "select": "DOI,title,type,update-to,issued,published,container-title"}
            resp = self.http.get(f"{BASE}/works", self._params(params), bucket="crossref-search",
                                 headers={"Accept": "application/json"})
            items = ((resp.json() or {}).get("message") or {}).get("items") or [] if resp.ok else []
            for item in items:
                notice_doi = (item.get("DOI") or "").lower()
                title = _first(item.get("title"))
                for u in item.get("update-to") or []:
                    target = (u.get("DOI") or "").lower()
                    if target in batch:
                        n = _notice(u)
                        n["doi"] = notice_doi or n.get("doi")
                        if title:
                            n["title"] = title
                        n["via"] = "updates filter"
                        found.setdefault(target, []).append(n)
            queries.append(query_from(self.name, "updates", "updates:" + ", ".join(batch), resp, len(items),
                                      empty_is_no_results=True))
        return found, queries
