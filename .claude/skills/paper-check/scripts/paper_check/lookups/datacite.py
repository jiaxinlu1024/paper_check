"""DataCite REST API: dataset, software and repository DOIs (Zenodo, OSF, ICPSR, Dataverse).

Rate limits since 2025: 1,000 requests per 5 minutes for clients that give a contact
address in the user agent, which the shared client does.
"""

from __future__ import annotations

from typing import Optional

from .crossref import doi_path
from .http import HttpClient, Response
from .records import Record, query_from, skipped

BASE = "https://api.datacite.org"


def parse_doi(item: dict, api_url: Optional[str] = None) -> Record:
    a = item.get("attributes") or {}
    titles = a.get("titles") or []
    title = titles[0].get("title") if titles else ""
    authors = []
    for c in a.get("creators") or []:
        authors.append({k: v for k, v in {"family": c.get("familyName"), "given": c.get("givenName"),
                                          "name": None if c.get("familyName") else c.get("name")}.items() if v})
    publisher = a.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")
    container = (a.get("container") or {}).get("title") or publisher
    year = a.get("publicationYear")
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    types = a.get("types") or {}
    return Record(source="datacite", id=(a.get("doi") or item.get("id") or "").lower(),
                  title=" ".join((title or "").split()),
                  authors=authors, year=year, years=[year] if year else [], container=container,
                  containers=[c for c in {container, publisher} if c], doi=(a.get("doi") or "").lower() or None,
                  url=a.get("url"), type=types.get("resourceTypeGeneral") or types.get("resourceType"),
                  publisher=publisher, api_url=api_url,
                  extra={k: v for k, v in {"version": a.get("version")}.items() if v})


def _empty(resp: Response) -> bool:
    return not (resp.json() or {}).get("data")


class DataCite:
    name = "datacite"

    def __init__(self, http: HttpClient):
        self.http = http

    def doi(self, doi: str) -> tuple:
        resp = self.http.get(f"{BASE}/dois/{doi_path(doi)}", bucket="datacite",
                             headers={"Accept": "application/vnd.api+json"})
        data = (resp.json() or {}).get("data") if resp.ok else None
        rec = parse_doi(data, resp.url) if isinstance(data, dict) else None
        return rec, query_from(self.name, "doi", doi, resp, 1 if rec else 0)

    def search(self, title: str, rows: int = 5) -> tuple:
        title = " ".join((title or "").replace('"', " ").split())[:250]
        if not title:
            return [], skipped(self.name, "search", title, "no title to search for")
        resp = self.http.get(f"{BASE}/dois", {"query": f'titles.title:"{title}"', "page[size]": rows},
                             bucket="datacite", headers={"Accept": "application/vnd.api+json"}, negative_if=_empty)
        recs = [parse_doi(d, resp.url) for d in ((resp.json() or {}).get("data") or [])] if resp.ok else []
        return recs, query_from(self.name, "search", title, resp, len(recs))
