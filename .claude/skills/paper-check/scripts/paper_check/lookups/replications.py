"""Replications of cited work, from the FORRT Replication Database (FReD), for CIT-14.

Where the data is. FReD's R package (github.com/forrtproject/FReD, MIT) loads the data
from OSF; its companion repository forrtproject/FReD-data publishes the processed files
on GitHub. This module reads `output/flora.csv` from raw.githubusercontent.com: the
paper-level file, one row per original and replication (or reproduction) pair, with the
outcome label FReD assigned and a quote of the replication's own conclusion. The data is
licensed CC BY 4.0 on its OSF project (osf.io/9r62x); the license is read from the OSF API
when the file is downloaded and recorded with the copy. The copy lives in
~/.paper-check/cache/fred/ and is refreshed weekly. A file above the size limit, or one
that cannot be fetched, gives skipped coverage with the reason.

Reporting rules (DESIGN section 6): each replication is reported with FReD's outcome label
and a verbatim quote of the replication's conclusion. A finding never calls the original
result false; it asks whether the paper relies on the result without saying so, which a
reader has to judge, so its status is needs_human.
"""

from __future__ import annotations

import csv
import json
from typing import Optional

from . import datasets
from .http import HttpClient
from .matching import compare_authors, fold, title_similarity

FLORA_URL = "https://raw.githubusercontent.com/forrtproject/FReD-data/main/output/flora.csv"
CITATION_URL = "https://raw.githubusercontent.com/forrtproject/FReD-data/main/output/citation.txt"
OSF_NODE = "https://api.osf.io/v2/nodes/9r62x/"
DATA_REPO = "https://github.com/forrtproject/FReD-data"
PACKAGE_REPO = "https://github.com/forrtproject/FReD"
MAX_BYTES = 60_000_000
MAX_AGE_DAYS = 7
ATTRIBUTION = ("FORRT Replication Database (FReD) and FORRT Library of Reproduction and Replication Attempts "
               "(FLoRA), https://osf.io/9r62x, licensed CC BY 4.0.")


def outcome_severity(label: Optional[str]) -> Optional[str]:
    """Severity of a replication outcome for CIT-14, or None when it raises no question."""
    l = (label or "").strip().lower()
    if not l or l == "na":
        return None
    parts = [p.strip() for p in l.split("||")]
    if any(p == "failed" for p in parts):
        return "major"
    if any(p in ("mixed", "statistically successful but flawed") or "robustness challenges" in p
           or p.startswith("computational issues") for p in parts):
        return "minor"
    return None


def check_license(http: HttpClient) -> dict:
    """Read the FReD project's license from the OSF API."""
    resp = http.get(OSF_NODE, bucket="osf", headers={"Accept": "application/json"})
    data = resp.json() if resp.ok else None
    if not isinstance(data, dict):
        return {"checked": False, "reason": resp.describe(), "known": "CC-By Attribution 4.0 International (2026-10-17)"}
    rel = (((data.get("data") or {}).get("relationships") or {}).get("license") or {})
    href = ((rel.get("links") or {}).get("related") or {}).get("href")
    if not href:
        return {"checked": False, "reason": "no license on the OSF project"}
    lic = http.get(href, bucket="osf", headers={"Accept": "application/json"})
    name = (((lic.json() or {}).get("data") or {}).get("attributes") or {}).get("name") if lic.ok else None
    return {"checked": bool(name), "name": name, "source": OSF_NODE, "permits_use": bool(name and (
        "cc-by" in name.lower() or "cc by" in name.lower() or "cc0" in name.lower() or "public domain" in name.lower()))}


class Fred:
    def __init__(self, rows: list, meta: dict):
        self.meta = meta
        self.by_doi: dict = {}
        self.by_title: dict = {}
        for row in rows:
            doi = (row.get("doi_o") or "").strip().lower()
            if doi and doi != "na":
                self.by_doi.setdefault(doi, []).append(row)
            t = fold(row.get("title_o"))
            if t:
                self.by_title.setdefault(t, []).append(row)
        self.size = len(rows)

    @classmethod
    def load(cls, dataset: "datasets.Dataset") -> "Fred":
        csv.field_size_limit(1 << 26)
        rows = []
        with open(dataset.path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            for row in csv.DictReader(fh):
                rows.append({(k or "").strip().strip('"'): v for k, v in row.items()})
        meta = dataset.describe()
        meta["rows"] = len(rows)
        return cls(rows, meta)

    def for_doi(self, doi: str) -> list:
        return self.by_doi.get((doi or "").lower(), [])

    def for_title(self, title: str, authors: list, year=None) -> list:
        rows = list(self.by_title.get(fold(title), []))
        out = []
        for r in rows:
            if title_similarity(title, r.get("title_o")) < 0.95:
                continue
            if authors:
                try:
                    found = json.loads(r.get("author_o") or "[]")
                except ValueError:
                    found = []
                au = compare_authors(authors, found if isinstance(found, list) else [])
                if (au["fraction"] or 0) < 0.6:
                    continue
            out.append(r)
        return out


def _na(v):
    v = (v or "").strip()
    return None if v in ("", "NA") else v


def replication_view(row: dict, matched_by: str) -> dict:
    return {k: v for k, v in {
        "original_doi": _na(row.get("doi_o")), "original_title": _na(row.get("title_o")),
        "replication_doi": _na(row.get("doi_r")), "replication_title": _na(row.get("title_r")),
        "replication_reference": _na(row.get("apa_ref_r")), "replication_year": _na(row.get("year_r")),
        "outcome": _na(row.get("outcome")), "outcome_quote": _na(row.get("outcome_quote")),
        "quote_source": _na(row.get("outcome_quote_source")), "type": _na(row.get("type")),
        "url": _na(row.get("url_r")) or (f"https://doi.org/{row['doi_r']}" if _na(row.get("doi_r")) else None),
        "fred_source": _na(row.get("source")), "matched_by": matched_by,
        "severity": outcome_severity(row.get("outcome")),
    }.items() if v is not None}


def load_fred(http: HttpClient, root=None) -> tuple:
    """(Fred or None, dataset description)."""
    ds = datasets.ensure(http, "fred", FLORA_URL, "flora.csv", max_bytes=MAX_BYTES, max_age_days=MAX_AGE_DAYS,
                         root=root, license_check=check_license,
                         extra_meta={"repository": DATA_REPO, "package": PACKAGE_REPO, "attribution": ATTRIBUTION})
    if not ds.available:
        return None, ds.describe()
    try:
        fred = Fred.load(ds)
        return fred, fred.meta
    except (OSError, csv.Error, UnicodeError) as exc:
        d = ds.describe()
        d["unavailable"] = f"could not read the file: {exc}"
        return None, d


def check(rc, fred: Fred) -> list:
    """Replication records for one reference (policy.ReferenceCheck after run())."""
    seen, out = set(), []
    for doi in rc.work_dois():
        for row in fred.for_doi(doi):
            key = (row.get("doi_r"), row.get("title_r"))
            if key not in seen:
                seen.add(key)
                out.append(replication_view(row, "doi"))
    if not out and rc.identity_records():
        title = rc.cited.get("title") or rc.identity_records()[0].title
        for row in fred.for_title(title, rc.cited.get("authors") or []):
            key = (row.get("doi_r"), row.get("title_r"))
            if key not in seen:
                seen.add(key)
                out.append(replication_view(row, "title and authors"))
    return out
