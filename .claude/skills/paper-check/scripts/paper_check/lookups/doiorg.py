"""doi.org: does a DOI exist, who registered it, and its metadata by content negotiation.

- `/api/handles/{doi}`: responseCode 1 means the DOI exists, with the URL it resolves to;
  100 (HTTP 404) means no such DOI. This is the CIT-12 check, and it never touches the
  publisher's site, which often blocks scripts.
- `/ra/{doi}`: the registration agency, such as Crossref or DataCite.
- `https://doi.org/{doi}` with `Accept: application/vnd.citationstyles.csl+json`: CSL-JSON
  from the agency. For a Crossref DOI that is Crossref's own record, so it does not count
  as a second, independent database.
"""

from __future__ import annotations

from typing import Optional

from .crossref import doi_path
from .http import HttpClient
from .records import Record, query_from

BASE = "https://doi.org"
CSL = "application/vnd.citationstyles.csl+json"


def parse_csl(c: dict, agency: Optional[str] = None, api_url: Optional[str] = None) -> Record:
    def year(key):
        try:
            return int((c.get(key) or {}).get("date-parts", [[None]])[0][0])
        except (TypeError, ValueError, IndexError):
            return None
    years = [y for y in (year("issued"), year("published-print"), year("published-online")) if y]
    authors = [{k: v for k, v in {"family": a.get("family"), "given": a.get("given"),
                                  "name": a.get("literal") or a.get("name")}.items() if v}
               for a in c.get("author") or []]
    container = c.get("container-title")
    if isinstance(container, list):
        container = container[0] if container else None
    title = c.get("title")
    if isinstance(title, list):
        title = title[0] if title else ""
    return Record(source="doi.org", id=(c.get("DOI") or "").lower(), title=" ".join((title or "").split()),
                  authors=authors,
                  year=years[0] if years else None, years=sorted(set(years)), container=container,
                  containers=[container] if container else [], volume=c.get("volume"), issue=c.get("issue"),
                  pages=c.get("page"), doi=(c.get("DOI") or "").lower() or None, url=c.get("URL"),
                  type=c.get("type"), publisher=c.get("publisher"), api_url=api_url,
                  extra={"agency": agency} if agency else {})


class DoiOrg:
    name = "doi.org"

    def __init__(self, http: HttpClient):
        self.http = http

    def handle(self, doi: str) -> tuple:
        """(exists: True, False or None when unknown, target URL, Query)."""
        resp = self.http.get(f"{BASE}/api/handles/{doi_path(doi)}", bucket="doi.org",
                             headers={"Accept": "application/json"})
        data = resp.json() if resp.status is not None else None
        code = data.get("responseCode") if isinstance(data, dict) else None
        exists, target = None, None
        if resp.ok and code == 1:
            exists = True
            for v in data.get("values") or []:
                if v.get("type") == "URL":
                    target = (v.get("data") or {}).get("value")
                    break
        elif resp.not_found or code in (100, 200):
            exists = False
        q = query_from(self.name, "handle", doi, resp, 1 if exists else 0)
        if exists is False:
            q.status = "not_found"
        return exists, target, q

    def agency(self, doi: str) -> tuple:
        """(agency name or None, Query). 'DOI does not exist' gives None with status not_found."""
        resp = self.http.get(f"{BASE}/ra/{doi_path(doi)}", bucket="doi.org", headers={"Accept": "application/json"})
        data = resp.json() if resp.ok else None
        ra = None
        if isinstance(data, list) and data:
            ra = data[0].get("RA")
            status = data[0].get("status")
            q = query_from(self.name, "agency", doi, resp, 1 if ra else 0)
            if not ra and status:
                q.status, q.detail = "not_found", status
            return ra, q
        return None, query_from(self.name, "agency", doi, resp, 0)

    def csl(self, doi: str, agency: Optional[str] = None) -> tuple:
        resp = self.http.get(f"{BASE}/{doi_path(doi)}", bucket="doi.org", headers={"Accept": CSL})
        data = resp.json() if resp.ok else None
        rec = parse_csl(data, agency, resp.url) if isinstance(data, dict) else None
        return rec, query_from(self.name, "content_negotiation", doi, resp, 1 if rec else 0)
