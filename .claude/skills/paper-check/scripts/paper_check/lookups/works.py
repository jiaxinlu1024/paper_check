"""`pc.py works WORK "query"`: search the scholarly literature for candidate works.

Agents use this to find replacement citations for claims a cited work does not
support (CIT-15) and related work (CIT-09). It queries OpenAlex, with abstracts,
and Crossref, through the shared polite and cached HTTP client, prints the
candidates as JSON, and appends the search to WORK/citations/searches.jsonl so the
report can show what was searched. A candidate is only a lead: before proposing
it, an agent checks that it supports the claim, from its abstract or full text.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Optional

from .openalex import BASE

SELECT = ("id,doi,display_name,publication_year,authorships,primary_location,cited_by_count,"
          "abstract_inverted_index,type,open_access")


def _abstract(index: Optional[dict], limit: int = 1500) -> str:
    if not index:
        return ""
    words = sorted((pos, w) for w, positions in index.items() for pos in positions)
    text = " ".join(w for _, w in words)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _openalex_item(w: dict) -> dict:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
    return {"source": "OpenAlex", "title": w.get("display_name"), "year": w.get("publication_year"),
            "authors": [(a.get("author") or {}).get("display_name") for a in (w.get("authorships") or [])][:10],
            "venue": src.get("display_name"), "type": w.get("type"), "doi": doi,
            "cited_by": w.get("cited_by_count"), "open_access_url": (w.get("open_access") or {}).get("oa_url"),
            "abstract": _abstract(w.get("abstract_inverted_index")), "id": w.get("id")}


def search_works(services, query: str, limit: int = 8, year_from: Optional[int] = None) -> tuple:
    """(candidates, notes) from OpenAlex and Crossref."""
    query = re.sub(r"\s+", " ", query or "").strip()[:300]
    notes, items, seen = [], [], set()
    params = {"search": query, "per_page": limit, "select": SELECT}
    if year_from:
        params["filter"] = f"from_publication_date:{year_from}-01-01"
    oa = services.openalex
    if oa.search_blocked:
        notes.append(f"OpenAlex skipped: {oa.search_blocked}")
    else:
        resp = oa._get(f"{BASE}/works", params)
        if resp.ok:
            for w in (resp.json() or {}).get("results") or []:
                it = _openalex_item(w)
                key = (it["doi"] or it["title"] or "").lower()
                if key and key not in seen:
                    seen.add(key)
                    items.append(it)
        else:
            notes.append(f"OpenAlex: {resp.describe()}")
    recs, q = services.crossref.search(query, rows=limit,
                                       filters={"from-pub-date": str(year_from)} if year_from else None)
    for r in recs:
        key = (r.doi or r.title or "").lower()
        if key and key not in seen:
            seen.add(key)
            items.append({"source": "Crossref", "title": r.title, "year": r.year,
                          "authors": [a.get("family") or a.get("name") for a in r.authors][:10],
                          "venue": r.container, "type": r.type, "doi": r.doi, "cited_by": None,
                          "open_access_url": None, "abstract": "", "id": r.doi})
    if getattr(q, "status", None) not in (None, "ok") and not recs:
        notes.append(f"Crossref: {getattr(q, 'status', 'no result')}")
    return items[: limit * 2], notes


def works_command(work: Path, query: str, limit: int = 8, year_from: Optional[int] = None,
                  offline: bool = False) -> int:
    from .services import Services

    services = Services.create(work, offline=offline)
    items, notes = search_works(services, query, limit=limit, year_from=year_from)
    record = {"query": query, "year_from": year_from, "searched": dt.datetime.now().isoformat(timespec="seconds"),
              "databases": ["OpenAlex", "Crossref"], "notes": notes,
              "results": [{k: it[k] for k in ("title", "year", "authors", "venue", "doi", "source")} for it in items]}
    log = Path(work) / "citations" / "searches.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({"query": query, "notes": notes, "candidates": items}, ensure_ascii=False, indent=1))
    return 0
