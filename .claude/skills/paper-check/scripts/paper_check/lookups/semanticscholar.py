"""Semantic Scholar Graph API: paper by DOI or arXiv ID, and title match.

- Key: sent in the `x-api-key` header when configured; a key allows 1 request per second.
- Without a key, requests share a pool with every unauthenticated user and are often
  answered 429. The client then waits once, tries once more, and if it is still refused
  stops calling Semantic Scholar for the rest of the run, recording why. That is the
  polite reading of the service's rule that clients must back off.
- `/paper/search/match` returns the single closest title match, or 404 when there is none.
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

from .http import HttpClient, Response
from .records import Query, Record, query_from, skipped

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "paperId,externalIds,title,year,authors,venue,journal,publicationTypes,publicationDate,url"


def parse_paper(p: dict, api_url: Optional[str] = None) -> Record:
    ext = p.get("externalIds") or {}
    journal = p.get("journal") or {}
    venue = journal.get("name") or p.get("venue") or None
    authors = [{"name": a.get("name")} for a in p.get("authors") or [] if a.get("name")]
    doi = (ext.get("DOI") or "").lower() or None
    return Record(
        source="semanticscholar", id=p.get("paperId") or "", title=" ".join((p.get("title") or "").split()),
        authors=authors,
        year=p.get("year") if isinstance(p.get("year"), int) else None,
        years=[p["year"]] if isinstance(p.get("year"), int) else [],
        container=venue, containers=[v for v in {journal.get("name"), p.get("venue")} if v],
        volume=journal.get("volume"), pages=(journal.get("pages") or "").strip() or None, doi=doi,
        url=p.get("url"), type=",".join(p.get("publicationTypes") or []) or None, api_url=api_url,
        score=p.get("matchScore"),
        extra={k: v for k, v in {"arxiv": ext.get("ArXiv"), "ssrn": ext.get("SSRN") if "SSRN" in ext else None}.items() if v},
    )


class SemanticScholar:
    name = "semanticscholar"

    def __init__(self, http: HttpClient, api_key: Optional[str] = None):
        self.http = http
        self.key = api_key or None
        self.blocked: Optional[str] = None
        self.throttled = 0

    def _get(self, path: str, params: dict) -> Response:
        headers = {"Accept": "application/json"}
        if self.key:
            headers["x-api-key"] = self.key
        resp = self.http.get(f"{BASE}{path}", params, headers=headers, bucket="semanticscholar",
                             max_retries=4 if self.key else 1, retry_after_cap=60 if self.key else 10)
        if resp.status == 429 and not resp.from_cache:
            self.throttled += 1
            if not self.key:
                self.blocked = ("throttled (HTTP 429) without an API key; Semantic Scholar was skipped for the rest "
                                "of the run")
            elif self.throttled >= 3:
                self.blocked = "throttled (HTTP 429) three times despite the API key; skipped for the rest of the run"
        return resp

    def paper(self, paper_id: str) -> tuple:
        """paper_id such as DOI:10.1257/aer.96.3.694 or ARXIV:1710.02926."""
        if self.blocked:
            return None, skipped(self.name, "doi", paper_id, self.blocked)
        resp = self._get(f"/paper/{urllib.parse.quote(paper_id, safe=':/._-()')}", {"fields": FIELDS})
        rec = parse_paper(resp.json(), resp.url) if resp.ok and isinstance(resp.json(), dict) else None
        kind = "doi" if paper_id.upper().startswith("DOI:") else "id"
        return rec, self._query(kind, paper_id, resp, 1 if rec else 0)

    def _query(self, kind: str, query: str, resp: Response, results: int) -> Query:
        q = query_from(self.name, kind, query, resp, results)
        if resp.status == 429:
            q.detail = self.blocked or "throttled (HTTP 429)"
        return q

    def match(self, title: str) -> tuple:
        title = " ".join((title or "").split())[:300]
        if not title:
            return None, skipped(self.name, "match", title, "no title to match")
        if self.blocked:
            return None, skipped(self.name, "match", title, self.blocked)
        resp = self._get("/paper/search/match", {"query": title, "fields": FIELDS})
        rec = None
        if resp.ok:
            data = (resp.json() or {}).get("data") or []
            if data:
                rec = parse_paper(data[0], resp.url)
        q = self._query("match", title, resp, 1 if rec else 0)
        if resp.not_found:
            q.status = "no_results"
        return rec, q
