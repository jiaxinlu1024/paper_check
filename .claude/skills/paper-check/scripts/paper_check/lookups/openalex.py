"""OpenAlex: works by DOI, title search, retraction flags and version-labelled locations.

- Key: sent as `api_key` when configured. Single-DOI lookups are free and also work
  without a key; searches cost $0.001 each against a daily budget ($1 with a key, a small
  budget shared by everyone on the IP address without one). A key that is refused (401,
  or 403 such as key_not_activated) is dropped for the rest of the run and the request is
  repeated without it.
- An exhausted budget is answered with HTTP 429 and a wait of hours. The client then stops
  searching for the rest of the run and says why; DOI lookups go on, since they are free.
- `is_retracted` comes from Retraction Watch. `locations[].version` labels each copy as
  submittedVersion, acceptedVersion or publishedVersion, with its source and source type.
- Searches: `filter=title.search:` (title words, stemmed) first, then `search=` (title,
  abstract and full text). Commas, pipes and colons are removed from filter values because
  they are filter syntax.
"""

from __future__ import annotations

import re
from typing import Optional

from .http import HttpClient, Response
from .records import Query, Record, query_from, skipped

BASE = "https://api.openalex.org"
SELECT = ("id,doi,title,display_name,publication_year,publication_date,type,authorships,primary_location,"
          "locations,best_oa_location,is_retracted,biblio,ids,open_access")


def _strip_doi(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", str(value), flags=re.I).lower()


def _given_family(name: str) -> dict:
    name = (name or "").strip()
    out = {"name": name}
    parts = name.split()
    if len(parts) >= 2:
        out["given"] = " ".join(parts[:-1])
    return out


def parse_work(w: dict, api_url: Optional[str] = None) -> Record:
    authors = []
    for a in w.get("authorships") or []:
        person = _given_family((a.get("author") or {}).get("display_name") or a.get("raw_author_name") or "")
        raw = a.get("raw_author_name")
        if raw and raw != person.get("name"):
            person["raw"] = raw
        authors.append(person)
    primary = w.get("primary_location") or {}
    source = primary.get("source") or {}
    biblio = w.get("biblio") or {}
    first, last = biblio.get("first_page"), biblio.get("last_page")
    pages = f"{first}-{last}" if first and last and last != first else (first or None)
    locations = []
    for loc in w.get("locations") or []:
        src = loc.get("source") or {}
        loc_id = str(loc.get("id") or "")
        loc_doi = _strip_doi(loc.get("doi")) or (_strip_doi(loc_id[4:]) if loc_id.startswith("doi:") else None)
        locations.append({k: v for k, v in {
            "version": loc.get("version"), "source": src.get("display_name"), "source_type": src.get("type"),
            "landing_page_url": loc.get("landing_page_url"), "pdf_url": loc.get("pdf_url"),
            "is_oa": loc.get("is_oa"), "doi": loc_doi,
        }.items() if v not in (None, "")})
    best = w.get("best_oa_location") or {}
    year = w.get("publication_year")
    return Record(
        source="openalex", id=str(w.get("id") or "").rsplit("/", 1)[-1], title=w.get("title") or w.get("display_name") or "",
        authors=authors, year=year if isinstance(year, int) else None, years=[year] if isinstance(year, int) else [],
        container=source.get("display_name"), containers=[source["display_name"]] if source.get("display_name") else [],
        volume=biblio.get("volume"), issue=biblio.get("issue"), pages=pages, doi=_strip_doi(w.get("doi")),
        url=primary.get("landing_page_url"), type=w.get("type"), is_retracted=w.get("is_retracted"),
        locations=locations, api_url=api_url,
        extra={k: v for k, v in {"source_type": source.get("type"), "best_oa_url": best.get("pdf_url") or best.get("landing_page_url"),
                                  "publication_date": w.get("publication_date")}.items() if v},
    )


def clean_filter_value(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[,|:;!()\"\[\]{}<>]", " ", text or "")).strip()[:300]


def _empty(resp: Response) -> bool:
    return not (resp.json() or {}).get("results")


def _message(resp: Response) -> str:
    data = resp.json()
    if isinstance(data, dict):
        msg = data.get("error") or data.get("message") or ""
        return str(msg)[:160]
    return resp.text()[:160]


class OpenAlex:
    name = "openalex"

    def __init__(self, http: HttpClient, api_key: Optional[str] = None):
        self.http = http
        self.key = api_key or None
        self.key_status = "configured" if self.key else "not configured"
        self.search_blocked: Optional[str] = None

    def _get(self, url: str, params: dict) -> Response:
        p = dict(params)
        if self.key:
            p["api_key"] = self.key
        negative = _empty if url.endswith("/works") else None
        resp = self.http.get(url, p, bucket="openalex", headers={"Accept": "application/json"}, negative_if=negative)
        if self.key and resp.status in (401, 403):
            self.key_status = f"refused (HTTP {resp.status}: {_message(resp) or 'no reason given'}); keyless calls used"
            self.key = None
            resp = self.http.get(url, params, bucket="openalex", headers={"Accept": "application/json"},
                                 negative_if=negative)
        return resp

    def work_by_doi(self, doi: str) -> tuple:
        resp = self._get(f"{BASE}/works/doi:{doi.strip()}", {"select": SELECT})
        rec = parse_work(resp.json(), resp.url) if resp.ok and isinstance(resp.json(), dict) else None
        return rec, query_from(self.name, "doi", doi, resp, 1 if rec else 0)

    def _list(self, kind: str, label: str, params: dict) -> tuple:
        if self.search_blocked:
            return [], skipped(self.name, kind, label, self.search_blocked)
        resp = self._get(f"{BASE}/works", params)
        if resp.status == 429 and not resp.from_cache:
            self.search_blocked = (f"OpenAlex search budget exhausted ({_message(resp) or resp.describe()}); "
                                   "searches skipped for the rest of the run")
        recs = []
        if resp.ok:
            for w in (resp.json() or {}).get("results") or []:
                recs.append(parse_work(w, resp.url))
        return recs, query_from(self.name, kind, label, resp, len(recs))

    def search_title(self, title: str, filters: Optional[dict] = None, per_page: int = 10) -> tuple:
        value = clean_filter_value(title)
        if not value:
            return [], skipped(self.name, "title_search", title, "no title to search for")
        filt = [f"title.search:{value}"] + [f"{k}:{v}" for k, v in (filters or {}).items()]
        return self._list("title_search", value + (f" [{', '.join(filt[1:])}]" if filters else ""),
                          {"filter": ",".join(filt), "per_page": per_page, "select": SELECT})

    def search(self, text: str, per_page: int = 10) -> tuple:
        text = re.sub(r"\s+", " ", text or "").strip()[:300]
        if not text:
            return [], skipped(self.name, "search", text, "nothing to search for")
        return self._list("search", text, {"search": text, "per_page": per_page, "select": SELECT})
