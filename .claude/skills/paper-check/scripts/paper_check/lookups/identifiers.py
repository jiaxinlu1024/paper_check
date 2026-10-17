"""Identifiers in a reference entry: DOI, arXiv, NBER, SSRN, IZA and CEPR, plus URLs.

The parsed fields are read first and the printed reference text second, so a DOI typed
into a note or an NBER number written as "NBER Working Paper 7682" is still found.
"""

from __future__ import annotations

import re
from typing import Optional

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>{}\\]+)", re.I)
URL_RE = re.compile(r"https?://[^\s\"<>{}\\]+", re.I)
ARXIV_NEW = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(v\d+)?(?!\d)")
ARXIV_OLD = re.compile(r"\b([a-z][a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?\b")
ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:\.pdf)?(?:[?#]|\s|$)", re.I)
NBER_PATTERNS = [
    re.compile(r"10\.3386/w(\d{3,6})", re.I),
    re.compile(r"nber\.org/papers/w(\d{3,6})", re.I),
    re.compile(r"\bNBER\s+(?:Working\s+Papers?|WP|Work\.\s*Pap\.)\s*(?:Series\s*)?(?:No\.?|Number|#)?\s*w?(\d{3,6})", re.I),
    re.compile(r"(?:National\s+Bureau\s+of\s+Economic\s+Research|\bNBER\b)[^.;]{0,80}?(?:Working\s+Papers?|WP)"
               r"\s*(?:Series\s*)?(?:No\.?|Number|#)?\s*w?(\d{3,6})", re.I),
]
SSRN_PATTERNS = [
    re.compile(r"10\.2139/ssrn\.(\d{4,9})", re.I),
    re.compile(r"ssrn\.com/abstract=(\d{4,9})", re.I),
    re.compile(r"abstract_id=(\d{4,9})", re.I),
    re.compile(r"\bSSRN\s+(?:Working\s+Paper\s+|Electronic\s+Journal\s+)?(?:No\.?\s*)?(\d{5,9})\b", re.I),
]
IZA_PATTERNS = [
    re.compile(r"iza\.org/(?:en/)?publications/dp/(\d{2,6})", re.I),
    re.compile(r"\bIZA\s+(?:Discussion\s+Papers?|DP)(?:\s+Series)?,?\s*(?:No\.?|Number|#)?\s*(\d{2,6})", re.I),
]
CEPR_PATTERNS = [
    re.compile(r"cepr\.org/(?:publications|active/publications/discussion_papers/dp\.php\?dpno=)/?(?:dp)?(\d{2,6})", re.I),
    re.compile(r"\bCEPR\s+Discussion\s+Papers?(?:\s+Series)?,?\s*(?:No\.?|Number|#)?\s*(?:DP)?(\d{2,6})", re.I),
]
TRAILING = ".,;:)]}'\""


def clean_doi(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip()
    v = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", v, flags=re.I)
    v = re.sub(r"^doi:\s*", "", v, flags=re.I)
    m = DOI_RE.search(v)
    if not m:
        return None
    doi = m.group(1)
    while doi and doi[-1] in TRAILING:
        # keep a closing parenthesis that has its opening partner inside the DOI
        if doi[-1] == ")" and doi.count("(") >= doi.count(")"):
            break
        doi = doi[:-1]
    return doi.lower() or None


def _clean_url(u: str) -> str:
    while u and u[-1] in TRAILING:
        if u[-1] == ")" and u.count("(") >= u.count(")"):
            break
        u = u[:-1]
    return u


def _first(patterns: list, text: str) -> Optional[str]:
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(1)
    return None


def extract(fields: dict, raw: str = "") -> dict:
    """Identifiers of one reference. Values are None when absent."""
    fields = fields or {}
    parts = [raw or ""] + [str(fields.get(k) or "") for k in ("doi", "url", "note", "number", "container",
                                                                "publisher", "eprint", "howpublished", "type")]
    hay = " ".join(p for p in parts if p)
    doi = clean_doi(fields.get("doi"))
    if not doi:
        for source in (fields.get("url"), fields.get("note"), raw):
            if source and re.search(r"doi", str(source), re.I) or (source and DOI_RE.search(str(source))):
                doi = clean_doi(str(source))
                if doi:
                    break
    arxiv = None
    eprint = str(fields.get("eprint") or "").strip()
    if eprint and (ARXIV_NEW.fullmatch(re.sub(r"^arxiv:", "", eprint, flags=re.I).split("v")[0] if False else "")
                   or ARXIV_NEW.search(eprint) or ARXIV_OLD.search(eprint)):
        m = ARXIV_NEW.search(eprint) or ARXIV_OLD.search(eprint)
        arxiv = m.group(1)
    if not arxiv:
        m = ARXIV_URL.search(hay)
        if m:
            arxiv = re.sub(r"v\d+$", "", m.group(1))
    if not arxiv and re.search(r"\barxiv\b", hay, re.I):
        m = re.search(r"arxiv[:\s]*(?:preprint\s*)?(?:arxiv:)?\s*(\d{4}\.\d{4,5}|[a-z][a-z\-]+(?:\.[A-Z]{2})?/\d{7})",
                      hay, re.I)
        if m:
            arxiv = m.group(1)
    if not arxiv and doi and doi.startswith("10.48550/arxiv."):
        arxiv = doi.split("arxiv.", 1)[1]
    nber = _first(NBER_PATTERNS, hay)
    container = " ".join(str(fields.get(k) or "") for k in ("container", "publisher", "note"))
    number = str(fields.get("number") or "").strip()
    if not nber and number and re.search(r"National Bureau of Economic Research|\bNBER\b", container, re.I):
        m = re.fullmatch(r"w?(\d{3,6})", number, re.I)
        if m:
            nber = m.group(1)
    ssrn = _first(SSRN_PATTERNS, hay)
    iza = _first(IZA_PATTERNS, hay)
    if not iza and number and re.search(r"\bIZA\b|Institute of Labor Economics|Forschungsinstitut zur Zukunft der Arbeit",
                                        container, re.I):
        m = re.fullmatch(r"(?:DP\s*)?(\d{2,6})", number, re.I)
        iza = m.group(1) if m else None
    cepr = _first(CEPR_PATTERNS, hay)
    if not cepr and number and re.search(r"\bCEPR\b|Centre for Economic Policy Research", container, re.I):
        m = re.fullmatch(r"(?:DP\s*)?(\d{2,6})", number, re.I)
        cepr = m.group(1) if m else None
    urls = []
    for source in (fields.get("url"), fields.get("howpublished"), fields.get("note"), raw):
        for m in URL_RE.finditer(str(source or "")):
            u = _clean_url(m.group(0))
            if u and u not in urls:
                urls.append(u)
    return {"doi": doi, "arxiv": arxiv, "nber": nber, "ssrn": ssrn, "iza": iza, "cepr": cepr, "urls": urls}


def working_paper_series(ids: dict) -> list:
    """Names of the working-paper series the identifiers point to."""
    names = []
    for key, name in (("nber", "NBER"), ("ssrn", "SSRN"), ("iza", "IZA"), ("cepr", "CEPR"), ("arxiv", "arXiv")):
        if ids.get(key):
            names.append(name)
    return names


def is_doi_url(url: str) -> bool:
    return bool(re.match(r"^https?://(dx\.)?doi\.org/10\.", url or "", re.I))
