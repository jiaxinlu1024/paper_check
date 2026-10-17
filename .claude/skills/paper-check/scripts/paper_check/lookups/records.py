"""Record: one database's view of a work. Query: one logged request.

Every service client returns Records and appends a Query to the run's log, so each
evidence card can list every query made, with its outcome, and the database that
answered. A Query's `url` never contains a key or the contact email.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .http import Response

# Databases that count toward the two-source rule of the reference policy. doi.org answers
# from the registration agency (Crossref or DataCite), so it is not independent of them,
# and an NBER page is the publisher's own deposit source.
VERIFYING = ("crossref", "openalex", "semanticscholar", "datacite", "arxiv")
DATABASE_NAMES = {
    "crossref": "Crossref", "openalex": "OpenAlex", "semanticscholar": "Semantic Scholar",
    "datacite": "DataCite", "arxiv": "arXiv", "doi.org": "doi.org", "nber": "NBER",
    "fred": "FReD", "retractionwatch": "Retraction Watch", "archive.org": "Internet Archive",
}


def display_name(database: str) -> str:
    return DATABASE_NAMES.get(database, database)


@dataclass
class Record:
    source: str
    id: str
    title: str = ""
    authors: list = field(default_factory=list)      # [{"family", "given", "name"}]; any may be missing
    year: Optional[int] = None
    years: list = field(default_factory=list)        # every year the record gives: print, online, issued
    container: Optional[str] = None
    containers: list = field(default_factory=list)   # container names, including short forms
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    publisher: Optional[str] = None
    number: Optional[str] = None
    is_retracted: Optional[bool] = None
    notices: list = field(default_factory=list)      # editorial notices about this work
    update_to: list = field(default_factory=list)    # when the record is itself a notice: what it updates
    locations: list = field(default_factory=list)    # OpenAlex copies, with version labels
    relations: dict = field(default_factory=dict)
    api_url: Optional[str] = None
    score: Optional[float] = None
    extra: dict = field(default_factory=dict)

    @property
    def group(self) -> str:
        """Which independent database this record stands for."""
        if self.source == "doi.org":
            return (self.extra.get("agency") or "doi.org").lower()
        return self.source

    def all_years(self) -> list:
        ys = [y for y in ([self.year] + list(self.years)) if isinstance(y, int)]
        return sorted(set(ys))

    def to_dict(self) -> dict:
        data = {k: v for k, v in asdict(self).items() if v not in (None, "", [], {})}
        return data

    def summary(self) -> dict:
        """The fields an evidence card shows."""
        keep = ("source", "id", "doi", "title", "authors", "year", "container", "volume", "issue", "pages", "type",
                "url", "publisher", "number", "is_retracted")
        data = {k: getattr(self, k) for k in keep if getattr(self, k) not in (None, "", [], {})}
        if self.authors:
            data["authors"] = [author_label(a) for a in self.authors]
        years = self.all_years()
        if len(years) > 1:
            data["years"] = years
        if self.api_url:
            data["api_url"] = self.api_url
        return data

    def label(self) -> str:
        names = [author_family(a) for a in self.authors[:3]]
        names = [n for n in names if n]
        who = ", ".join(names) + (" et al." if len(self.authors) > 3 else "")
        bits = [who, f"({self.year})" if self.year else "", f'"{self.title}"' if self.title else ""]
        if self.container:
            bits.append(self.container)
        if self.doi:
            bits.append(f"doi:{self.doi}")
        return " ".join(b for b in bits if b)


def author_family(a: dict) -> str:
    if not isinstance(a, dict):
        return str(a)
    if a.get("family"):
        return str(a["family"])
    name = str(a.get("name") or "").strip()
    if "," in name:
        return name.split(",")[0].strip()
    return name.split()[-1] if name.split() else ""


def author_label(a: dict) -> str:
    if not isinstance(a, dict):
        return str(a)
    if a.get("family"):
        given = (a.get("given") or "").strip()
        return f"{a['family']}, {given}" if given else str(a["family"])
    return str(a.get("name") or "")


@dataclass
class Query:
    database: str
    kind: str                       # doi, search, title_search, match, page, updates, handle, agency, url, data
    query: str                      # what was asked, readable: a DOI, a search string, a URL
    url: Optional[str] = None       # the request URL, without secrets
    status: str = "ok"              # ok, not_found, no_results, throttled, error, offline, skipped
    http_status: Optional[int] = None
    results: int = 0
    from_cache: bool = False
    detail: Optional[str] = None
    stage: Optional[str] = None     # identity, versions, retractions, replications, links

    @property
    def completed(self) -> bool:
        """The database answered the question, whether or not it found anything."""
        return self.status in ("ok", "not_found", "no_results")

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", [], {}) or k in ("results",)}


def query_from(database: str, kind: str, query: str, resp: Response, results: int = 0,
               detail: Optional[str] = None, empty_is_no_results: bool = True) -> Query:
    outcome = resp.outcome
    if outcome == "ok":
        status = "no_results" if (empty_is_no_results and results == 0) else "ok"
    else:
        status = outcome
    return Query(database=database, kind=kind, query=query, url=resp.url, status=status, http_status=resp.status,
                 results=results, from_cache=resp.from_cache,
                 detail=detail or (None if resp.ok or resp.not_found else resp.describe()))


def skipped(database: str, kind: str, query: str, reason: str) -> Query:
    return Query(database=database, kind=kind, query=query, status="skipped", detail=reason)
