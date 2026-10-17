"""Working papers and preprints that have a published version (CIT-04).

No open tool links economics working papers to their journal versions, so this part is
new. For a reference that is a working paper or preprint (an NBER, SSRN, IZA, CEPR or
arXiv identifier, a report-like entry type, a series name in the entry, or a matched
record of type report or posted-content):

1. NBER: the paper page's "Published Versions" section names the journal or book version
   (citation courtesy of RePEc). Each one is looked up in Crossref and validated.
2. Crossref: journal articles found with the title and author names, in a wide window of
   years after the working paper.
3. OpenAlex: the working paper's own record may list a published copy among its
   locations; a title search restricted to journals finds the rest.
4. RePEc would link versions directly, but its API needs an access code, so it is noted as
   unused rather than called.

Candidates are scored with authors weighted above the title, because titles often change
between versions (DellaVigna and Malmendier's "Overestimating Self-Control" became "Paying
Not to Go to the Gym"); a changed title is accepted only when the author sets agree and
the year falls in the window. The weights and cut-offs are policy.THRESHOLDS["version_*"],
adapted from Crossref's preprint matcher (MIT). A published version is reported as a
Suggestion, and its DOI is recorded on the card so later checks can read that version.
"""

from __future__ import annotations

import re
from typing import Optional

from .matching import compare_authors, family_key, fold, parse_year, title_similarity
from .policy import THRESHOLDS, ReferenceCheck
from .records import Record

WP_WORDS = re.compile(r"working\s+papers?|discussion\s+papers?|\bmimeo\b|\bpreprint\b|\bmanuscript\b|"
                      r"technical\s+report|work\s+in\s+progress|\bunpublished\b|policy\s+research\s+working", re.I)
WP_TYPES = {"techreport", "report", "unpublished", "preprint", "posted-content", "working-paper", "manuscript"}
WP_SOURCES = re.compile(r"ssrn|\bnber\b|national bureau of economic research|repec|\biza\b|\bcepr\b|arxiv|"
                        r"\bosf\b|psyarxiv|socarxiv|research square|preprints?\b|working paper|discussion paper|"
                        r"econstor|mpra|policy research working paper", re.I)
PUBLISHED_TYPES = {"journal-article", "article", "book-chapter", "proceedings-article"}
SERIES = (("nber", "NBER"), ("ssrn", "SSRN"), ("iza", "IZA"), ("cepr", "CEPR"), ("arxiv", "arXiv"))
PUBLISHED_ENTRY_TYPES = {"article", "book", "inbook", "incollection", "inproceedings", "conference", "phdthesis",
                         "mastersthesis", "proceedings"}


def is_working_paper(rc: ReferenceCheck) -> tuple:
    """(True or False, why). A journal article that mentions its working-paper number in a
    note is still a journal article, so the entry type is read before series numbers."""
    ids = rc.ids
    doi = ids.get("doi") or ""
    if doi.startswith("10.3386/w"):
        return True, f"NBER DOI {doi}"
    if doi.startswith("10.2139/ssrn"):
        return True, f"SSRN DOI {doi}"
    series = next((f"{name} working paper {ids[key]}" for key, name in SERIES if ids.get(key)), None)
    entry_type = (rc.cited.get("type") or "").lower()
    if entry_type in WP_TYPES:
        return True, series or f"entry type {entry_type}"
    venue = " ".join(str(rc.ref.fields.get(k) or "") for k in ("container", "publisher"))
    m = WP_SOURCES.search(venue)
    if m:
        return True, f'the venue is "{m.group(0)}"'
    if entry_type in PUBLISHED_ENTRY_TYPES:
        return False, f"entry type {entry_type}"
    if series:
        return True, series
    text = " ".join(str(rc.ref.fields.get(k) or "") for k in ("container", "note", "publisher", "type", "number"))
    m = WP_WORDS.search(text) or WP_WORDS.search(rc.ref.raw or "")
    if m:
        return True, f'the entry says "{m.group(0)}"'
    primary = rc.primary_record()
    if primary is not None and (primary.type or "").lower() in WP_TYPES:
        return True, f"{primary.source} lists it as type {primary.type}"
    return False, "a journal article, book or chapter"


def _wp_like(rec: Record) -> bool:
    if (rec.type or "").lower() in WP_TYPES:
        return True
    names = " ".join([rec.container or ""] + list(rec.containers or []) + [rec.publisher or ""])
    return bool(WP_SOURCES.search(names)) or (rec.doi or "").startswith(("10.3386/", "10.2139/", "10.48550/", "10.31234/",
                                                                          "10.31235/", "10.17605/"))


def version_score(wp: dict, rec: Record) -> dict:
    T = THRESHOLDS
    w = T["version_weights"]
    au = compare_authors(wp.get("authors"), rec.authors) if wp.get("authors") and rec.authors else None
    a = (au or {}).get("jaccard") or 0.0
    t = title_similarity(wp.get("title"), rec.title) if wp.get("title") and rec.title else 0.0
    wy = parse_year(wp.get("year"))
    years = rec.all_years()
    lo, hi = T["version_years"]
    dy = min((y - wy for y in years), key=abs) if (wy and years) else None
    year_ok = 1.0 if dy is not None and lo <= dy <= hi else 0.0
    score = w["author"] * a + w["title"] * t + w["year"] * year_ok
    accepted = (a >= T["version_author"] and t >= T["version_title"] and year_ok == 1.0
                and score >= T["version_score"])
    return {"score": round(score, 3), "authors": round(a, 3), "title": round(t, 3), "year_difference": dy,
            "accepted": accepted}


def _link(rec: Record, sc: dict, basis: str) -> dict:
    return {"doi": rec.doi, "title": rec.title, "year": rec.year, "container": rec.container, "type": rec.type,
            "volume": rec.volume, "issue": rec.issue, "pages": rec.pages,
            "author_list": [{"family": a.get("family") or a.get("name"), "given": a.get("given")}
                            for a in rec.authors][:20],
            "authors": [a.get("family") or a.get("name") for a in rec.authors][:8], "database": rec.source,
            "similarity": sc, "basis": [basis], "url": f"https://doi.org/{rec.doi}" if rec.doi else rec.url}


def find_published_versions(rc: ReferenceCheck, services) -> dict:
    """Return {"is_working_paper", "why", "links", "notes"}; queries go to rc.queries."""
    is_wp, why = is_working_paper(rc)
    out = {"is_working_paper": is_wp, "why": why, "links": [], "notes": []}
    if not is_wp:
        return out
    T = THRESHOLDS
    s = services
    wp = dict(rc.cited)
    primary = next(iter(rc.identity_records()), None)
    if primary is not None:
        wp["title"] = wp.get("title") or primary.title
        wp["year"] = wp.get("year") or (str(primary.year) if primary.year else None)
        if not wp.get("authors"):
            wp["authors"] = primary.authors
    own_dois = {d for d in [rc.ids.get("doi")] + [r.doi for r in rc.identity_records()] if d}
    found: dict = {}

    def consider(rec: Record, basis: str, require: Optional[dict] = None) -> None:
        if rec is None or (rec.doi and rec.doi in own_dois) or _wp_like(rec):
            return
        if (rec.type or "journal-article").lower() not in PUBLISHED_TYPES:
            return
        sc = version_score(wp, rec)
        if require is not None:
            sc["accepted"] = sc["accepted"] or (require["title"] >= T["title_strong"] and sc["authors"] >= 0.5)
            sc["stated_title"] = require["title"]
        if not sc["accepted"]:
            return
        key = rec.doi or fold(rec.title)
        if key in found:
            found[key]["basis"] = sorted(set(found[key]["basis"] + [basis]))
            if sc["score"] > found[key]["similarity"]["score"]:
                found[key]["similarity"] = sc
            return
        found[key] = _link(rec, sc, basis)

    # 1. NBER's own page
    number = rc.ids.get("nber")
    if not number:
        for d in own_dois:
            if d.startswith("10.3386/w"):
                number = d.split("/w", 1)[1]
    if number:
        _rec, versions, q = s.nber.paper(number)
        rc.log(q)
        for v in versions:
            recs, q = s.crossref.search(v["text"], rows=3)
            rc.log(q)
            for r in recs:
                stated = title_similarity(v.get("title") or v["text"], r.title)
                if stated >= T["title_strong"]:
                    consider(r, "listed on the NBER paper page (citation courtesy of RePEc)", {"title": stated})
        if not versions and q.completed:
            out["notes"].append(f"The NBER page for w{number} lists no published version.")
    # 2. Crossref journal articles in a wide year window
    title = wp.get("title") or ""
    wy = parse_year(wp.get("year"))
    fams = " ".join(family_key(a) for a in (wp.get("authors") or [])[:4])
    if title:
        filters = {"type": "journal-article"}
        if wy:
            lo, hi = T["version_years"]
            filters["from-pub-date"] = str(wy + lo)
            filters["until-pub-date"] = str(wy + hi)
        recs, q = s.crossref.search(f"{title} {fams}".strip(), rows=10, filters=filters)
        rc.log(q)
        for r in recs:
            consider(r, "Crossref search for journal articles")
    # 3. OpenAlex: published copies among the working paper's locations, then a journal search
    oa = rc.record_from("openalex")
    if oa is not None:
        for loc in oa.locations:
            if loc.get("version") == "publishedVersion" and loc.get("source_type") == "journal" and loc.get("doi") \
                    and loc["doi"] not in own_dois and not WP_SOURCES.search(loc.get("source") or ""):
                rec, q = s.crossref.work(loc["doi"])
                rc.log(q)
                consider(rec, "OpenAlex lists it as the published version")
    if title:
        recs, q = s.openalex.search_title(title, filters={"primary_location.source.type": "journal"}, per_page=10)
        rc.log(q)
        for r in recs:
            if r.type == "article":
                r.type = "journal-article"
            consider(r, "OpenAlex search for journal articles")
    links = sorted(found.values(), key=lambda l: (-len(l["basis"]), -l["similarity"]["score"]))
    for l in links:
        sc = l["similarity"]
        if any("NBER" in b for b in l["basis"]) or (sc["title"] >= T["title_strong"] and sc["authors"] >= 0.99):
            l["confidence"] = "high"
        elif sc["title"] >= T["title"]:
            l["confidence"] = "medium"
        else:
            l["confidence"] = "low"
    if len(links) > 1 and abs(links[0]["similarity"]["score"] - links[1]["similarity"]["score"]) < T["candidate_gap"]:
        out["notes"].append("Two candidate published versions score within "
                            f"{T['candidate_gap']}; check which one is meant.")
        for l in links[:2]:
            if l["confidence"] == "high":
                l["confidence"] = "medium"
    out["links"] = links
    if not services.credentials.get("repec_access_code"):
        out["notes"].append("RePEc was not consulted: its API needs an access code.")
    return out
