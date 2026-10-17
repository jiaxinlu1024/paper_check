"""The reference policy of DESIGN section 6, as code.

For each reference:

1. **Identifier first.** A DOI is resolved through Crossref, then through its registration
   agency (DataCite, or doi.org content negotiation for others), and looked up in OpenAlex
   and, when two databases have not yet agreed, Semantic Scholar. arXiv IDs, NBER numbers
   (10.3386/w#####) and SSRN IDs (10.2139/ssrn.#####) are resolved the same way. Each
   record is validated against the citation; an identifier whose records all describe a
   different work is an identifier conflict.
2. **Search-based matching.** Unless two databases already agree, Crossref is searched with
   the raw reference string (`query.bibliographic`), OpenAlex with the title, and Semantic
   Scholar with its title match. Every candidate is validated field by field: title
   similarity, family-name overlap (spaces and accents ignored), year, and venue.
3. **Two sources for verified.** "verified" needs identity matches in two independent
   databases (records.VERIFYING). One database gives "single_source".
4. **Not found is not fake.** A script cannot run the final web search, so a reference no
   database matches gets the verdict "not_found_in_databases" and `needs_web_check: true`.
   It becomes a Critical finding with status "likely": medium confidence when at least two
   databases were searched, low when only one was. A reference that no database could be
   searched for at all (offline, throttled, errors) is "unverified" and gets no finding;
   the coverage table says so.
5. **Severity by kind.** Non-existent Critical, chimeric Major, metadata drift Minor (Major
   when the author list is substantially wrong), status drift Suggestion.
6. **Thresholds** are all in THRESHOLDS below, with their sources and calibration.
7. **Evidence card** for every reference: the record matched, its fields, the similarity
   of each field, the closest candidates, every query made and the databases reached.

Adapted, with attribution in THIRD_PARTY_NOTICES.md, from RefChecker (thresholds and the
three-stage hallucination policy), Crossref's search-based reference matcher and its
preprint matcher (search on the raw string, then validate; the score window), and
bib-check-agent and citecheck (field-by-field checks). All are MIT-licensed.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from . import identifiers
from .matching import (compare_authors, compare_pages, compare_simple, container_similarity, family_key, fold,
                       is_short_title, looks_abbreviated, main_title, parse_year, title_similarity, year_difference)
from .nber import nber_doi
from .records import VERIFYING, Query, Record, author_label, display_name

# Calibration on tests/fixtures/latex_basic (live lookups, 2026-10-17):
#   five correct references   title 1.00, authors 1.00, year 0 in Crossref and OpenAlex by DOI
#   laibson1997               title 1.00, authors 1.00, year off by one (cited 1998, records 1997)
#   brown2015                 its DOI's record (Kahneman and Tversky 1979): title 0.37, authors 0.00.
#                             Search candidates: the closest title, "Quasi-Hyperbolic Discounting and
#                             Delayed Retirement", scores 0.77 with no author in common; candidates
#                             by a Brown score at most 0.49 on title
#   smithson2019              best candidate in any database (Crossref, Habla and Muller 2018):
#                             title 0.63, authors 0.00; one with a shared author scores title 0.49
# So the title alone would be a close call (0.77 against 0.80); the author criterion carries the
# decision. Every wrong candidate fails at least one of the two by a wide margin, so RefChecker's
# values were kept, and both criteria are required whenever both sides list authors. In
# tests/fixtures/lookups/extra_refs.json
# DellaVigna and Malmendier's working paper scores title 0.37 against its retitled journal version,
# so the version matcher abstains rather than guess.
THRESHOLDS = {
    # identity: does a database record describe the cited work?
    "title": 0.80,             # RefChecker similarity_threshold
    "title_strong": 0.90,      # with matching authors, enough whatever the year
    "title_short": 0.90,       # titles under 4 words or 25 characters also need authors and year
    "title_no_authors": 0.95,  # when no author list can be compared
    "author": 0.60,            # RefChecker: share of cited family names found in the record
    "author_partial": 0.30,    # exact title, same year, this much overlap: same work, wrong author list
    "year_tolerance": 1,       # RefChecker year_tolerance; a difference within it is still drift
    "year_window": 3,          # Crossref preprint matcher's upper bound; title 0.80-0.90 must fall within it
    # chimeric: a real title with the wrong authors
    "title_only": 0.95,
    "author_conflict": 0.30,
    # metadata drift (CIT-03)
    "title_drift": 0.95,       # a matched title below this is reported as different
    "container_drift": 0.60,
    # ranking of candidates
    "weights": {"title": 0.5, "author": 0.3, "year": 0.2},
    "candidate_gap": 0.04,     # Crossref matchers: top two candidates this close are ambiguous
    "search_rows": 10,
    # working paper or preprint to published version (CIT-04)
    "version_score": 0.85,     # Crossref preprint matcher accepts at 0.87 on an equal-weight mean
    "version_author": 0.75,    # author sets must largely agree
    "version_title": 0.50,     # titles often change between versions
    "version_weights": {"author": 0.5, "title": 0.3, "year": 0.2},
    "version_years": [-1, 8],  # Crossref uses -1..+3; economics publication lags are longer
}
SEVERITY_BY_KIND = {"non_existent": "critical", "chimeric": "major", "metadata_drift": "minor",
                    "status_drift": "suggestion"}
IDENTIFIER_VIAS = ("doi", "arxiv", "nber", "ssrn")
VERDICTS = ("verified", "metadata_drift", "single_source", "chimeric", "not_found_in_databases", "unverified")
SOURCE_PREFERENCE = ("crossref", "datacite", "openalex", "semanticscholar", "arxiv", "doi.org", "nber")
WP_RECORD_TYPES = ("report", "posted-content", "preprint")
ARTICLE_ENTRY_TYPES = {"article", "article-journal", "journal-article"}
_WP_SERIES = re.compile(r"national bureau of economic research|\bnber\b|\bssrn\b|social science research network|"
                        r"\biza\b|\bcepr\b|working papers?|discussion papers?|\barxiv\b|\bpreprints?\b", re.I)


_SERIES_WORDS = re.compile(r"\b(?:papers?|series|reports?|briefs?|cent(?:er|re)|institute|bureau|foundation)\b", re.I)


def cited_is_article(cited: dict) -> bool:
    """The entry cites a journal article: it names a journal with a volume, issue or pages, or its type
    says article and its venue does not look like a paper series. (Reference managers often type a
    working paper as a journal article: "Example Research Center Paper", with no volume.)"""
    container = str(cited.get("container") or "")
    details = bool(cited.get("volume") or cited.get("issue") or cited.get("pages"))
    series = bool(_WP_SERIES.search(container) or _SERIES_WORDS.search(container))
    if (cited.get("type") or "").lower() in ARTICLE_ENTRY_TYPES:
        return details or not series
    return bool(container) and details and not series


def record_is_working_paper(rec) -> bool:
    if (rec.type or "").lower() in WP_RECORD_TYPES:
        return True
    if (rec.doi or "").lower().startswith(("10.3386/", "10.2139/", "10.48550/")):
        return True
    return bool(_WP_SERIES.search(" ".join([rec.container or "", rec.publisher or ""])))
POORLY_INDEXED = ("book", "inbook", "incollection", "booklet", "misc", "techreport", "unpublished", "manual", "online",
                  "phdthesis", "mastersthesis", "dataset", "software", "electronic", "report")
DATA_HINT = re.compile(r"\b(data ?set|data|software|replication (?:package|data)|zenodo|dataverse|icpsr|osf)\b", re.I)


# ---------------------------------------------------------------- the cited side
def guess_title(raw: str) -> str:
    """A title from a reference string without parsed fields (PDF and \\bibitem entries)."""
    raw = raw or ""
    m = re.search(r"[\"“]([^\"”]{10,})[\"”]", raw)
    if m:
        return m.group(1).strip(" ,.")
    m = re.search(r"\(?\b(1[89]\d\d|20\d\d)[a-z]?\)?[.,:]?\s+(.*)", raw)
    rest = m.group(2) if m else raw
    for seg in re.split(r"(?<=[.?!])\s+", rest):
        seg = seg.strip(" ,.")
        if len(seg.split()) >= 3:
            return seg
    return rest.strip(" ,.")[:200]


def guess_authors(raw: str) -> list:
    m = re.search(r"\(?\b(1[89]\d\d|20\d\d)[a-z]?\)?", raw or "")
    head = (raw[: m.start()] if m else "").strip(" ,.(")
    if not head:
        return []
    out = []
    for piece in re.split(r";|\band\b|&", head):
        piece = piece.strip(" ,.")
        if not piece:
            continue
        family = piece.split(",")[0].strip() if "," in piece else (piece.split()[-1] if piece.split() else "")
        if len(re.sub(r"[^A-Za-z]", "", family)) >= 2:
            out.append({"family": family})
    return out


def cited_view(ref) -> dict:
    f = ref.fields or {}
    title = f.get("title") or guess_title(ref.raw)
    authors = f.get("authors") or guess_authors(ref.raw)
    return {
        "title": title or "", "title_from": "fields" if f.get("title") else "reference text",
        "authors": authors, "year": f.get("year") or (str(parse_year(ref.raw)) if parse_year(ref.raw) else None),
        "container": f.get("container"), "volume": f.get("volume"), "issue": f.get("issue"),
        "pages": f.get("pages"), "doi": identifiers.clean_doi(f.get("doi")), "type": f.get("type"),
        "publisher": f.get("publisher"), "number": f.get("number"),
    }


def search_string(ref) -> str:
    """The raw reference for Crossref's bibliographic search, minus DOIs and URLs, which
    would pull the search toward the identifier's record."""
    text = identifiers.URL_RE.sub(" ", ref.raw or "")
    text = re.sub(r"\bdoi:\s*\S+", " ", text, flags=re.I)
    text = identifiers.DOI_RE.sub(" ", text)
    return " ".join(text.split())[:500]


# ---------------------------------------------------------------- one candidate
def year_score(dy: Optional[int]) -> float:
    if dy is None:
        return 0.5
    if abs(dy) <= THRESHOLDS["year_tolerance"]:
        return 1.0
    if abs(dy) <= THRESHOLDS["year_window"]:
        return 0.5
    return 0.0


def decide_identity(t: Optional[float], a: Optional[float], dy: Optional[int], short: bool) -> tuple:
    """(is the same work, rule used). See THRESHOLDS for the values."""
    T = THRESHOLDS
    if t is None:
        return False, "no title to compare"
    near = dy is not None and abs(dy) <= T["year_tolerance"]
    if a is not None:
        if a >= T["author"]:
            if short:
                if t >= T["title_short"] and near:
                    return True, "short title: title, authors and year agree"
                return False, "short title: needs title, authors and year to agree"
            if t >= T["title_strong"]:
                return True, "title and authors agree"
            if t >= T["title"] and (dy is None or abs(dy) <= T["year_window"]):
                return True, "title, authors and year agree"
            return False, "title differs"
        if a >= T["author_partial"] and not short and t >= T["title_strong"] and near:
            return True, "title and year agree; the author list differs"
        return False, "authors differ"
    if not short and t >= T["title_no_authors"] and near:
        return True, "title and year agree; no author list to compare"
    return False, "no author list to compare, and title or year not close enough"


def evaluate(cited: dict, rec: Record, via: str) -> dict:
    T = THRESHOLDS
    t = title_similarity(cited.get("title"), rec.title) if cited.get("title") and rec.title else None
    authors = compare_authors(cited.get("authors"), rec.authors) if cited.get("authors") and rec.authors else None
    a = authors["fraction"] if authors else None
    dy = year_difference(cited.get("year"), rec.all_years())
    c = container_similarity(cited.get("container"), rec.containers or [rec.container])
    short = is_short_title(cited.get("title") or rec.title)
    identity, rule = decide_identity(t, a, dy, short)
    title_only = (not identity and t is not None and t >= T["title_only"] and not short and a is not None
                  and a < T["author_conflict"])
    w = T["weights"]
    parts = [(w["title"], t or 0.0), (w["year"], year_score(dy))]
    if a is not None:
        parts.append((w["author"], a))
    score = sum(x * v for x, v in parts) / sum(x for x, _ in parts)
    return {"record": rec, "via": via, "title": t, "authors": authors, "author_fraction": a, "year_diff": dy,
            "container": c, "short_title": short, "identity": identity, "rule": rule, "title_only": title_only,
            "score": round(score, 3)}


def similarity_view(ev: dict) -> dict:
    out = {"title": ev["title"], "authors": ev["author_fraction"], "year_difference": ev["year_diff"],
           "container": ev["container"], "score": ev["score"], "same_work": ev["identity"], "rule": ev["rule"]}
    if ev.get("authors"):
        au = ev["authors"]
        out["authors_detail"] = {k: au[k] for k in ("matched", "cited_count", "record_count", "cited_not_in_record",
                                                     "record_not_cited", "first_author", "same_order") if k in au}
    return {k: v for k, v in out.items() if v is not None}


def candidate_view(ev: dict) -> dict:
    rec = ev["record"]
    return {"database": rec.source, "via": ev["via"], "record": rec.summary(), "similarity": similarity_view(ev)}


# ---------------------------------------------------------------- field-by-field drift
def _primary(evs: list) -> Optional[dict]:
    if not evs:
        return None
    order = {s: i for i, s in enumerate(SOURCE_PREFERENCE)}
    return sorted(evs, key=lambda e: (e["via"] not in IDENTIFIER_VIAS, order.get(e["record"].source, 99),
                                       -e["score"]))[0]


def field_checks(cited: dict, evs: list) -> list:
    """Compare each cited field with every record that matched the work."""
    T = THRESHOLDS
    checks = []
    primary = _primary(evs)
    if primary is None:
        return checks
    # A journal article that the databases know only as its working paper (Card and Krueger's 1994 AER
    # article as NBER WP 4509, 1993): the record is a version of the cited work, so its year, series and
    # missing journal details say nothing about errors in the entry.
    # (An entry that gives the working paper's DOI itself is wrong, and is reported below as a version error.)
    wp_version = (cited_is_article(cited) and all(record_is_working_paper(e["record"]) for e in evs)
                  and not any(e["via"] == "doi" for e in evs))

    def values(attr):
        return {e["record"].source: getattr(e["record"], attr) for e in evs if getattr(e["record"], attr)}

    # title
    if cited.get("title"):
        sims = {e["record"].source: e["title"] for e in evs if e["title"] is not None}
        best = max(sims.values()) if sims else None
        if best is not None:
            status = "match" if best >= T["title_drift"] else "differs"
            check = {"field": "title", "cited": cited["title"], "found": primary["record"].title, "status": status,
                     "similarity": best, "sources": values("title")}
            if status == "differs":
                mc, mf = main_title(cited["title"]), main_title(primary["record"].title)
                if mf and not mc and fold(cited["title"]) == mf:
                    check["detail"] = "the subtitle is missing"
            checks.append(check)
    # authors
    if cited.get("authors"):
        comps = [(e, e["authors"]) for e in evs if e.get("authors")]
        if comps:
            def clean(au):
                missing = au["record_not_cited"] if not au["truncated"] else []
                return not au["cited_not_in_record"] and not missing and au["same_order"] and au["first_author"]
            ok = any(clean(au) for _, au in comps)
            e, au = sorted(comps, key=lambda p: (p[0] is not primary, -(p[1]["fraction"] or 0)))[0]
            check = {"field": "authors", "cited": [author_label(a) for a in cited["authors"]],
                     "found": [author_label(a) for a in e["record"].authors], "status": "match" if ok else "differs",
                     "similarity": au["fraction"], "sources": {x["record"].source: [author_label(a) for a in x["record"].authors]
                                                               for x, _ in comps}}
            if not ok:
                problems = []
                if au["cited_not_in_record"]:
                    problems.append("not in the record: " + "; ".join(au["cited_not_in_record"]))
                if au["record_not_cited"] and not au["truncated"]:
                    problems.append("missing from the reference: " + "; ".join(au["record_not_cited"]))
                if not au["first_author"]:
                    problems.append("the first author differs")
                elif not au["same_order"]:
                    problems.append("the order differs")
                check["detail"] = "; ".join(problems)
                check["severity"] = ("major" if (au["fraction"] or 0) < T["author"] or not au["first_author"]
                                     else "minor")
            checks.append(check)
    if wp_version:
        rec = primary["record"]
        where = rec.container or rec.publisher or display_name(rec.source)
        checks.append({"field": "version", "cited": "journal article", "found": f"{rec.type or 'working paper'} ({where}, "
                       f"{rec.year or 'no year'})", "status": "note", "sources": {rec.source: rec.type},
                       "detail": "only a working-paper or preprint version of the cited article was found, so the "
                                 "entry's year, journal, volume and pages could not be checked against a record"})
        return checks
    # year
    if cited.get("year"):
        # Crossref holds the publisher's own dates (print, online, issued); when it matched,
        # those decide, so that a wrong year in a secondary database cannot hide an error.
        if primary["record"].source == "crossref" and primary["record"].all_years():
            years = primary["record"].all_years()
        else:
            years = sorted({y for e in evs for y in e["record"].all_years()})
        if years:
            cy = parse_year(cited["year"])
            status = "match" if cy in years else "differs"
            counts = Counter(e["record"].year for e in evs if e["record"].year)
            found = primary["record"].year or (counts.most_common(1)[0][0] if counts else None)
            by_source = {e["record"].source: e["record"].all_years() for e in evs if e["record"].all_years()}
            check = {"field": "year", "cited": cited["year"], "found": found, "status": status, "sources": by_source}
            if status == "differs":
                check["contradicting"] = sorted(s for s, ys in by_source.items() if cy not in ys)
                check["agreeing"] = sorted(s for s, ys in by_source.items() if cy in ys)
                dy = year_difference(cy, years)
                check["difference"] = dy
                if dy is not None and abs(dy) > T["year_window"]:
                    check["detail"] = "a difference of several years; check whether another edition or reprint is meant"
            checks.append(check)
    # venue
    if cited.get("container"):
        sims = {e["record"].source: e["container"] for e in evs if e["container"] is not None}
        if sims:
            best = max(sims.values())
            status = "match" if best >= T["container_drift"] else (
                "unknown" if looks_abbreviated(cited["container"]) else "differs")
            checks.append({"field": "container", "cited": cited["container"], "found": primary["record"].container,
                           "status": status, "similarity": best, "sources": values("container")})
    # volume, issue, pages
    for name, attr, func in (("volume", "volume", lambda a, b: compare_simple(a, b)),
                             ("issue", "issue", lambda a, b: compare_simple(a, b, numeric_only=True)),
                             ("pages", "pages", compare_pages)):
        if not cited.get(name):
            continue
        results = {e["record"].source: func(cited[name], getattr(e["record"], attr)) for e in evs
                   if getattr(e["record"], attr)}
        known = [r for r in results.values() if r is not None]
        if not known:
            continue
        status = "match" if any(known) else "differs"
        checks.append({"field": name, "cited": cited[name], "found": getattr(primary["record"], attr) or
                       next(iter(values(attr).values()), None), "status": status, "sources": values(attr)})
    # version: a journal article cited with the DOI of its working paper or preprint
    if cited_is_article(cited):
        for e in evs:
            rtype = (e["record"].type or "").lower()
            if e["via"] == "doi" and rtype in WP_RECORD_TYPES:
                where = e["record"].container or e["record"].publisher or display_name(e["record"].source)
                checks.append({"field": "version", "cited": "journal article", "found": f"{rtype} ({where})",
                               "status": "differs", "sources": {e["record"].source: rtype},
                               "detail": "the DOI belongs to a working-paper or preprint version, not to the journal "
                                         "article"})
                break
    # parts the entry leaves out that the matched record gives (missing DOI, volume, issue, pages, ...)
    rec = primary["record"]
    rtype = (rec.type or "").lower()
    is_article = rtype in ("journal-article", "article", "article-journal") or \
        (cited.get("type") or "").lower() in ("article", "article-journal")
    wanted = [("doi", rec.doi), ("year", rec.year)]
    if is_article:
        wanted += [("container", rec.container), ("volume", rec.volume), ("issue", rec.issue), ("pages", rec.pages)]
    if rec.authors:
        wanted.append(("authors", [author_label(a) for a in rec.authors[:12]]))
    for name, value in wanted:
        if value and not cited.get(name):
            checks.append({"field": name, "cited": None, "found": value, "status": "missing",
                           "sources": {rec.source: value}})
    return checks


# ---------------------------------------------------------------- one reference
class ReferenceCheck:
    """Runs the policy for one reference and builds its evidence card."""

    def __init__(self, ref, block, services):
        self.ref = ref
        self.block = block
        self.s = services
        self.cited = cited_view(ref)
        self.ids = identifiers.extract(ref.fields, ref.raw)
        self.queries: list = []
        self.evals: list = []
        self.doi_status: dict = {}
        self.card: dict = {}
        self.stage = "identity"

    # -- logging
    def log(self, q) -> None:
        for x in (q if isinstance(q, list) else [q]):
            if isinstance(x, Query):
                if x.stage is None:
                    x.stage = self.stage
                self.queries.append(x)

    def add(self, rec: Optional[Record], via: str) -> Optional[dict]:
        if rec is None:
            return None
        ev = evaluate(self.cited, rec, via)
        self.evals.append(ev)
        return ev

    def _rank(self, ev: dict) -> tuple:
        """Order of preference among records of one database that all match: found by the
        identifier, higher score, same kind of work as cited, with a DOI, closer year."""
        rec = ev["record"]
        cited_article = (self.cited.get("type") or "").lower() in ("article", "inproceedings", "incollection")
        wp_type = (rec.type or "").lower() in ("preprint", "posted-content", "report", "dataset", "other")
        same_kind = not (cited_article and wp_type)
        dy = ev["year_diff"]
        return (ev["via"] in IDENTIFIER_VIAS, ev["score"], same_kind, bool(rec.doi), -(abs(dy) if dy is not None else 9))

    def identity_groups(self) -> dict:
        groups: dict = {}
        for ev in self.evals:
            if not ev["identity"]:
                continue
            g = ev["record"].group
            if g not in VERIFYING:
                continue
            best = groups.get(g)
            if best is None or self._rank(ev) > self._rank(best):
                groups[g] = ev
        return groups

    # -- stage 1: identifiers
    def resolve_doi(self, doi: str, via: str) -> None:
        s = self.s
        rec, q = s.crossref.work(doi)
        self.log(q)
        if rec is not None:
            self.add(rec, via)
            self.doi_status[doi] = "registered"
        elif q.status == "not_found":
            ra, q2 = s.doiorg.agency(doi)
            self.log(q2)
            if ra and ra.lower() == "datacite":
                rec, q3 = s.datacite.doi(doi)
                self.log(q3)
                self.add(rec, via)
                self.doi_status[doi] = "registered" if rec else "unknown"
            elif ra:
                rec, q3 = s.doiorg.csl(doi, agency=ra)
                self.log(q3)
                self.add(rec, via)
                self.doi_status[doi] = "registered" if rec else "unknown"
            elif q2.status == "not_found":
                self.doi_status[doi] = "does_not_exist"
        oa, q = s.openalex.work_by_doi(doi)
        self.log(q)
        self.add(oa, via)
        mine = [e for e in self.evals if e["via"] == via and e["identity"]]
        if len({e["record"].group for e in mine}) < 2:
            rec, q = s.semanticscholar.paper(f"DOI:{doi}")
            self.log(q)
            self.add(rec, via)

    def identifier_stage(self) -> None:
        """The DOI field first. A series number (NBER, SSRN) is resolved only when there is
        no DOI, since a journal article often mentions its working paper."""
        ids = self.ids
        if ids.get("doi"):
            self.resolve_doi(ids["doi"], "doi")
        elif ids.get("nber"):
            self.resolve_doi(nber_doi(ids["nber"]), "nber")
        elif ids.get("ssrn"):
            self.resolve_doi(f"10.2139/ssrn.{ids['ssrn']}", "ssrn")
        if ids.get("arxiv"):
            rec, q = self.s.arxiv.by_id(ids["arxiv"])
            self.log(q)
            self.add(rec, "arxiv")
            if len(self.identity_groups()) < 2:
                rec, q = self.s.semanticscholar.paper(f"ARXIV:{ids['arxiv']}")
                self.log(q)
                self.add(rec, "arxiv")

    # -- stage 2: search
    def search_stage(self) -> None:
        s, title = self.s, self.cited.get("title")
        recs, q = s.crossref.search(search_string(self.ref), rows=THRESHOLDS["search_rows"])
        self.log(q)
        for r in recs:
            self.add(r, "search")
        first = family_key(self.cited["authors"][0]) if self.cited.get("authors") else ""
        if title and "openalex" not in self.identity_groups():
            recs, q = s.openalex.search_title(title)
            self.log(q)
            for r in recs:
                self.add(r, "search")
            if "openalex" not in self.identity_groups():
                recs, q = s.openalex.search(f"{title} {first}".strip())
                self.log(q)
                for r in recs:
                    self.add(r, "search")
        if title and len(self.identity_groups()) < 2:
            rec, q = s.semanticscholar.match(title)
            self.log(q)
            self.add(rec, "search")
        hint = " ".join(str(self.cited.get(k) or "") for k in ("type", "container", "publisher")) + " " + self.ref.raw
        if title and "datacite" not in self.identity_groups() and (
                DATA_HINT.search(hint) or (self.cited.get("type") or "") in ("misc", "dataset", "software", "data")):
            recs, q = s.datacite.search(title)
            self.log(q)
            for r in recs:
                self.add(r, "search")
        if title and "arxiv" not in self.identity_groups() and re.search(r"arxiv", hint, re.I):
            recs, q = s.arxiv.search(title)
            self.log(q)
            for r in recs:
                self.add(r, "search")

    # -- stage 3: decide
    def databases(self) -> tuple:
        reached, failed = [], {}
        for q in self.queries:
            if q.completed:
                if q.database not in reached:
                    reached.append(q.database)
        for q in self.queries:
            if q.database not in reached and not q.completed:
                failed[q.database] = q.detail or q.status
        return reached, failed

    def searched_databases(self) -> list:
        """Verifying databases that answered a search or an identifier lookup."""
        out = []
        for q in self.queries:
            if q.database in VERIFYING and q.completed and q.database not in out:
                out.append(q.database)
        return out

    def decide(self) -> dict:
        T = THRESHOLDS
        groups = self.identity_groups()
        identity_evs = list(groups.values())
        conflicts, other_versions = {}, []
        for via in IDENTIFIER_VIAS:
            evs = [e for e in self.evals if e["via"] == via]
            if not evs or any(e["identity"] for e in evs):
                continue
            # The DOI field must point at the cited work. A derived identifier (series number,
            # arXiv ID) may point at another version with another title: a conflict only when
            # the authors differ too.
            if via != "doi" and any((e["author_fraction"] or 0) >= T["author"] for e in evs):
                other_versions.extend(evs)
                continue
            conflicts[via] = evs
        title_only = [e for e in self.evals if e["title_only"]] if not groups else []
        checks = field_checks(self.cited, identity_evs) if identity_evs else []
        drift = [c for c in checks if c["status"] == "differs"]
        searched = self.searched_databases()
        verdict, kind, basis, exists = "unverified", None, None, None
        if conflicts:
            verdict, kind, basis = "chimeric", "chimeric", "identifier_conflict"
            exists = True if groups else None
        elif title_only:
            verdict, kind, basis, exists = "chimeric", "chimeric", "author_conflict", None
        elif groups:
            exists = True
            if drift:
                verdict, kind = "metadata_drift", "metadata_drift"
            else:
                verdict = "verified" if len(groups) >= 2 else "single_source"
        elif searched:
            # Not found is not fake: existence stays unknown until the web check.
            verdict, kind, exists = "not_found_in_databases", "non_existent", None
        severity = None
        if kind == "metadata_drift":
            severity = "major" if any(c.get("severity") == "major" for c in drift) else "minor"
        elif kind:
            severity = SEVERITY_BY_KIND[kind]
        needs_web = verdict == "not_found_in_databases" or (verdict == "chimeric" and not groups)
        primary = _primary(identity_evs)
        ranked = sorted(self.evals, key=lambda e: (-e["identity"], -e["score"]))
        closest = None if primary else (ranked[0] if ranked else None)
        reached, failed = self.databases()
        card = {
            "ref": self.ref.id, "key": self.ref.key, "raw": self.ref.raw,
            "block": self.block.id if self.block is not None else None,
            "anchor": self.block.anchor.to_dict() if self.block is not None else self.ref.anchor.to_dict(),
            "cited": {k: (v if k != "authors" else [author_label(a) for a in v]) for k, v in self.cited.items()
                      if v not in (None, "", [])},
            "identifiers": {k: v for k, v in self.ids.items() if v and k != "urls"},
            "verdict": verdict, "kind": kind, "basis": basis, "severity": severity, "exists": exists,
            "needs_web_check": needs_web,
            "matched": primary["record"].summary() if primary else None,
            "matched_in": [display_name(g) for g in groups],
            "agreeing_databases": sorted(display_name(g) for g in groups) if len(groups) >= 2 else [],
            "similarity": similarity_view(primary) if primary else None,
            "field_checks": checks,
            "closest": candidate_view(closest) if closest else None,
            "candidates": [candidate_view(e) for e in ranked[:6]],
            "searched_databases": [display_name(d) for d in searched],
            "databases_reached": [display_name(d) for d in reached],
            "databases_failed": [{"database": display_name(d), "reason": r} for d, r in failed.items()],
            "doi_status": self.doi_status,
        }
        if conflicts:
            via, evs = next(iter(conflicts.items()))
            best = sorted(evs, key=lambda e: -e["score"])[0]
            card["identifier_conflict"] = {
                "identifier": via, "value": self.ids.get(via) if via != "nber" else nber_doi(self.ids["nber"]),
                "records": [candidate_view(e) for e in evs],
                "resolves_to": best["record"].summary(), "similarity": similarity_view(best),
                "cited_work_found_elsewhere": bool(groups),
            }
        if title_only:
            best = sorted(title_only, key=lambda e: -e["score"])[0]
            card["author_conflict"] = {"record": best["record"].summary(), "similarity": similarity_view(best)}
        if other_versions:
            card["identifier_versions"] = [candidate_view(e) for e in other_versions]
        if needs_web:
            title = self.cited.get("title") or ""
            card["web_check"] = {
                "query": f'"{title}"' if title else self.ref.raw[:200],
                "title": title, "authors": card["cited"].get("authors", []), "year": self.cited.get("year"),
                "instructions": ("Search the web for the exact title. Count only a page dedicated to the work "
                                 "(publisher, repository, working-paper series, author homepage), not a mention in "
                                 "another paper's reference list. If such a page exists, the work exists; re-check "
                                 "its title, authors and year against it. If none exists, the reference is "
                                 "non-existent; a second reviewer must agree before the finding is confirmed."),
            }
        if verdict == "not_found_in_databases":
            reasons = []
            if len(searched) < 2:
                reasons.append("only one database could be searched")
            if (self.cited.get("type") or "").lower() in POORLY_INDEXED:
                reasons.append(f"entries of type {self.cited['type']} are poorly indexed in scholarly databases")
            if not self.cited.get("title"):
                reasons.append("the entry has no title to search for")
            card["confidence"] = "low" if reasons else "medium"
            if reasons:
                card["confidence_reasons"] = reasons
        self._ranked = ranked
        self._identity = identity_evs
        self._groups = groups
        self._conflicts = conflicts
        self.card = card
        return card

    def run(self) -> dict:
        self.identifier_stage()
        if len(self.identity_groups()) < 2:
            self.search_stage()
        return self.decide()

    # -- helpers for later stages
    def identity_records(self) -> list:
        return [e["record"] for e in getattr(self, "_identity", [])]

    def work_dois(self) -> list:
        """DOIs that identify the cited work: the cited DOI when it matched, else matched records' DOIs."""
        out = []
        for e in getattr(self, "_identity", []):
            if e["record"].doi and e["record"].doi not in out:
                out.append(e["record"].doi)
        if not out and self.ids.get("doi") and not getattr(self, "_conflicts", {}) and \
                self.doi_status.get(self.ids["doi"]) == "registered":
            out.append(self.ids["doi"])
        return out

    def primary_record(self) -> Optional[Record]:
        ev = _primary(getattr(self, "_identity", []))
        return ev["record"] if ev else None

    def record_from(self, source: str) -> Optional[Record]:
        for e in getattr(self, "_identity", []):
            if e["record"].source == source:
                return e["record"]
        return None
