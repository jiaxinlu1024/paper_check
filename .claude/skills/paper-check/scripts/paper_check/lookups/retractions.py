"""Retractions, corrections and expressions of concern on cited works (CIT-05).

Sources:
1. Crossref. A work's `updated-by` list names each notice with its type and `source`
   ("publisher", or "retraction-watch" since Crossref acquired the Retraction Watch
   database), and `filter=updates:{doi}` returns the notices themselves, whose
   `update-to` points back at the work. Both are read for every DOI.
2. OpenAlex `is_retracted`, which comes from Retraction Watch.
3. The Retraction Watch CSV (gitlab.com/crossref/retraction-watch-data), downloaded at most
   weekly into ~/.paper-check/cache/retraction_watch/, only when a work was matched
   without any DOI: notices are then matched by title and first author.

Every notice for a DOI is listed, merged across sources. Nothing is ever filtered by
subject: the behavioral cases that matter most are tagged Psychology, Ethics or Sociology
in Retraction Watch, not Economics.
"""

from __future__ import annotations

import csv
import re
from typing import Optional

from . import datasets
from .matching import family_key, fold, squeeze
from .records import Query

RW_URL = "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv"
RW_MAX_BYTES = 150_000_000
RW_MAX_AGE_DAYS = 7
NOTICE_SEVERITY = {
    "retraction": "critical", "partial_retraction": "critical", "withdrawal": "critical", "removal": "critical",
    "expression_of_concern": "major",
    "correction": "minor", "corrigendum": "minor", "erratum": "minor", "addendum": "minor",
}
RETRACTION_TYPES = {"retraction", "partial_retraction", "withdrawal", "removal"}
SOURCE_NAMES = {"publisher": "Crossref (publisher)", "retraction-watch": "Crossref (Retraction Watch)"}


def normalize_type(value: Optional[str]) -> str:
    v = re.sub(r"[\s\-]+", "_", (value or "").strip().lower())
    return {"expression_of_concern": "expression_of_concern", "eoc": "expression_of_concern",
            "retracted": "retraction"}.get(v, v)


class Notices:
    """Notices for one work, merged by (notice DOI or record id, type)."""

    def __init__(self):
        self.items: dict = {}

    def add(self, ntype: str, source: str, *, doi: Optional[str] = None, title: Optional[str] = None,
            date: Optional[str] = None, label: Optional[str] = None, record_id: Optional[str] = None,
            reason: Optional[str] = None) -> None:
        ntype = normalize_type(ntype)
        key = ((doi or "").lower() or (f"rw:{record_id}" if record_id else f"{source}:{ntype}"), ntype)
        # Retraction Watch rows carry the same notice DOI as Crossref's entries, so merge on it.
        item = self.items.get(key)
        if item is None:
            for (kdoi, ktype), other in self.items.items():
                if ktype == ntype and record_id and other.get("record_id") == str(record_id):
                    item = other
                    break
        if item is None and ntype in RETRACTION_TYPES:
            # A bare retraction flag (OpenAlex is_retracted) is the same event as the notice.
            for other in self.items.values():
                if other["type"] in RETRACTION_TYPES and not other.get("notice_doi") and not other.get("record_id"):
                    item = other
                    break
        if item is None:
            item = {"type": ntype, "label": label or ntype.replace("_", " ").capitalize(), "sources": []}
            self.items[key] = item
        for k, v in (("notice_doi", doi), ("notice_title", title), ("date", date), ("record_id", record_id),
                     ("reason", reason)):
            if v and not item.get(k):
                item[k] = str(v)
        if source not in item["sources"]:
            item["sources"].append(source)

    def flag_retracted(self, source: str) -> None:
        """A retraction flag without a notice, such as OpenAlex is_retracted."""
        for item in self.items.values():
            if item["type"] in RETRACTION_TYPES:
                if source not in item["sources"]:
                    item["sources"].append(source)
                return
        self.add("retraction", source)

    def as_list(self) -> list:
        return sorted(self.items.values(), key=lambda n: (n.get("date") or "", n["type"]))


def assess(notices: list) -> Optional[dict]:
    """The finding a list of notices calls for: severity, status, title, or None."""
    relevant = [n for n in notices if n["type"] in NOTICE_SEVERITY or n["type"] == "reinstatement"]
    if not relevant:
        return None
    retractions = [n for n in relevant if n["type"] in RETRACTION_TYPES]
    reinstated = [n for n in relevant if n["type"] == "reinstatement"]
    sources = {s for n in relevant for s in n["sources"]}
    if retractions:
        last_retraction = max((n.get("date") or "") for n in retractions)
        if reinstated and max((n.get("date") or "") for n in reinstated) >= last_retraction:
            return {"severity": "major", "status": "needs_human", "title": "Cited work was retracted and later reinstated",
                    "kind": "reinstated"}
        n_sources = len({s for n in retractions for s in n["sources"]})
        return {"severity": "critical", "status": "confirmed" if n_sources >= 2 else "likely",
                "title": "Cited work has been retracted", "kind": "retraction"}
    if any(n["type"] == "expression_of_concern" for n in relevant):
        return {"severity": "major", "status": "confirmed" if len(sources) >= 2 else "likely",
                "title": "Cited work carries an expression of concern", "kind": "expression_of_concern"}
    if reinstated and not any(n["type"] in NOTICE_SEVERITY for n in relevant):
        return None
    return {"severity": "minor", "status": "needs_human", "title": "Cited work has a published correction",
            "kind": "correction"}


# ---------------------------------------------------------------- Retraction Watch file
class RetractionWatch:
    """The Retraction Watch CSV, indexed by original DOI and by folded title."""

    def __init__(self, rows: list, meta: dict):
        self.meta = meta
        self.by_doi: dict = {}
        self.by_title: dict = {}
        for row in rows:
            doi = (row.get("OriginalPaperDOI") or "").strip().lower()
            if doi and doi not in ("unavailable", "0"):
                self.by_doi.setdefault(doi, []).append(row)
            t = fold(row.get("Title"))
            if t:
                self.by_title.setdefault(t, []).append(row)

    @classmethod
    def load(cls, dataset: "datasets.Dataset") -> "RetractionWatch":
        keep = ("Record ID", "Title", "Subject", "Journal", "Author", "RetractionDate", "RetractionDOI",
                "OriginalPaperDate", "OriginalPaperDOI", "RetractionNature", "Reason")
        rows = []
        csv.field_size_limit(1 << 26)
        with open(dataset.path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            for row in csv.DictReader(fh):
                rows.append({k: (row.get(k) or "").strip() for k in keep})
        return cls(rows, dataset.describe())

    def for_doi(self, doi: str) -> list:
        return self.by_doi.get((doi or "").lower(), [])

    def for_title(self, title: str, authors: list) -> list:
        """Rows with the same title and the cited first author among the row's authors."""
        rows = self.by_title.get(fold(title), [])
        if not rows or not authors:
            return rows if rows and not authors else []
        first = family_key(authors[0])
        return [r for r in rows if first and first in squeeze(r.get("Author"))]


def _rw_date(value: str) -> Optional[str]:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", value or "")
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None


def add_rw_rows(notices: Notices, rows: list, how: str) -> None:
    for r in rows:
        nature = normalize_type(r.get("RetractionNature")) or "retraction"
        notices.add(nature, f"Retraction Watch file ({how})", doi=(r.get("RetractionDOI") or "").lower() or None,
                    date=_rw_date(r.get("RetractionDate", "")), label=r.get("RetractionNature") or None,
                    record_id=r.get("Record ID") or None, reason=(r.get("Reason") or "").strip("; ") or None)


def load_retraction_watch(http, root=None) -> tuple:
    """(RetractionWatch or None, dataset description)."""
    ds = datasets.ensure(http, "retraction_watch", RW_URL, "retraction_watch.csv", max_bytes=RW_MAX_BYTES,
                         max_age_days=RW_MAX_AGE_DAYS, root=root,
                         extra_meta={"publisher": "Crossref (Retraction Watch database)",
                                     "terms": "openly available from Crossref; the README states no license"})
    if not ds.available:
        return None, ds.describe()
    try:
        return RetractionWatch.load(ds), ds.describe()
    except (OSError, csv.Error) as exc:
        d = ds.describe()
        d["unavailable"] = f"could not read the file: {exc}"
        return None, d


# ---------------------------------------------------------------- per reference
def check_all(checks: list, services, rw_loader=None) -> dict:
    """Notices for every reference: {ref id: {"dois", "notices", "is_retracted", "checked", "reason"}}.

    `checks` are policy.ReferenceCheck objects after run(). Queries are logged on each."""
    out: dict = {}
    by_doi: dict = {}
    for rc in checks:
        dois = rc.work_dois()
        out[rc.ref.id] = {"dois": dois, "notices": Notices(), "is_retracted": {}, "checked": [], "failed": []}
        for d in dois:
            by_doi.setdefault(d, []).append(rc)
    # Crossref notices pointing at the DOIs, in batches
    if by_doi:
        found, queries = services.crossref.updates(list(by_doi))
        for q in queries:
            batch = q.query.replace("updates:", "").split(", ")
            for d in batch:
                for rc in by_doi.get(d, []):
                    if q not in rc.queries:
                        rc.log(q)
                    (out[rc.ref.id]["checked"] if q.completed else out[rc.ref.id]["failed"]).append(
                        "Crossref updates filter" if q.completed else f"Crossref updates filter: {q.detail or q.status}")
        for d, notices in found.items():
            for rc in by_doi.get(d, []):
                for n in notices:
                    out[rc.ref.id]["notices"].add(n.get("type"), SOURCE_NAMES.get(n.get("source"), "Crossref"),
                                                  doi=n.get("doi"), title=n.get("title"), date=n.get("date"),
                                                  label=n.get("label"), record_id=n.get("record_id"))
    rw = None
    rw_state: dict = {}
    for rc in checks:
        entry = out[rc.ref.id]
        notices: Notices = entry["notices"]
        # Crossref updated-by on the work's own record, and OpenAlex is_retracted
        for rec in rc.identity_records():
            if rec.source == "crossref":
                entry["checked"].append("Crossref updated-by")
                for n in rec.notices:
                    notices.add(n.get("type"), SOURCE_NAMES.get(n.get("source"), "Crossref"), doi=n.get("doi"),
                                date=n.get("date"), label=n.get("label"), record_id=n.get("record_id"))
            if rec.source == "openalex" and rec.is_retracted is not None:
                entry["is_retracted"]["OpenAlex"] = rec.is_retracted
                entry["checked"].append("OpenAlex is_retracted")
                if rec.is_retracted:
                    notices.flag_retracted("OpenAlex is_retracted")
        if entry["dois"] and "OpenAlex is_retracted" not in entry["checked"]:
            for d in entry["dois"][:1]:
                rec, q = services.openalex.work_by_doi(d)
                rc.log(q)
                if rec is not None and rec.is_retracted is not None:
                    entry["is_retracted"]["OpenAlex"] = rec.is_retracted
                    entry["checked"].append("OpenAlex is_retracted")
                    if rec.is_retracted:
                        notices.flag_retracted("OpenAlex is_retracted")
                elif not q.completed:
                    entry["failed"].append(f"OpenAlex: {q.detail or q.status}")
        # No DOI, but the work was matched: the Retraction Watch file, by title and first author
        if not entry["dois"] and rc.identity_records():
            if rw is None and not rw_state:
                rw, rw_state = rw_loader() if rw_loader else (None, {"unavailable": "no loader"})
            title = rc.cited.get("title") or rc.identity_records()[0].title
            if rw is not None:
                rows = rw.for_title(title, rc.cited.get("authors") or [])
                add_rw_rows(notices, rows, "title and first author")
                entry["checked"].append("Retraction Watch file by title")
                rc.log(Query("retractionwatch", "title", title, status="ok" if rows else "no_results", results=len(rows),
                             detail="local copy of the Retraction Watch CSV"))
            else:
                entry["failed"].append(f"Retraction Watch file: {rw_state.get('unavailable')}")
        entry["notices"] = notices.as_list()
        entry["checked"] = sorted(set(entry["checked"]))
        if not entry["dois"] and not rc.identity_records():
            entry["reason"] = "the work was not identified, so there is nothing to check for notices"
        elif not entry["checked"]:
            entry["reason"] = "; ".join(entry["failed"]) or "no source could be checked"
    if rw_state:
        out["_retraction_watch"] = rw_state
    return out
