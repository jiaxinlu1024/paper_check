"""NBER working papers: DOIs 10.3386/w##### and the paper pages on nber.org.

The DOI resolves through Crossref, where NBER deposits its papers as type "report". The
paper page carries citation_* meta tags and, when NBER knows one, a "Published Versions"
section with the journal or book version, "citation courtesy of RePEc". That section is
the most direct working-paper-to-journal link available without RePEc API access.

Only the meta tags and that section are cached; the page itself is large. The page is
read as data: its text is parsed for citations and never followed as instructions.
"""

from __future__ import annotations

import html
import re
from typing import Optional

from .http import HttpClient
from .records import Record, query_from

PAGE = "https://www.nber.org/papers/w{number}"
DOI_PREFIX = "10.3386/"
_META = re.compile(r'<meta\s+name="(citation_[a-z_]+)"\s+content="([^"]*)"\s*/?>', re.I)
_PUBLISHED = re.compile(r'<h2[^>]*>\s*Published Versions?\s*</h2>(.*?)</div>', re.I | re.S)
_PARA = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
_HREF = re.compile(r'href="([^"]+)"', re.I)
_ANCHOR = re.compile(r"<a\b[^>]*>(.*?)</a>", re.I | re.S)


def nber_doi(number: str) -> str:
    return f"{DOI_PREFIX}w{str(number).lstrip('wW')}"


def _keep_relevant(body: bytes) -> bytes:
    text = body.decode("utf-8", errors="replace")
    metas = [m.group(0) for m in _META.finditer(text)]
    pub = _PUBLISHED.search(text)
    kept = "<html><head>\n" + "\n".join(metas) + "\n</head><body>\n"
    if pub:
        kept += pub.group(0) + "\n"
    return (kept + "</body></html>\n").encode("utf-8")


def _strip_tags(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_page(text: str, number: str, api_url: Optional[str] = None) -> tuple:
    """(Record of the working paper, [published versions as {"text", "links"}])."""
    meta: dict = {}
    for name, value in _META.findall(text):
        meta.setdefault(name.lower(), []).append(html.unescape(value).strip())
    title = (meta.get("citation_title") or [""])[0]
    authors = [{"name": n} for n in meta.get("citation_author", []) if n]
    date = (meta.get("citation_publication_date") or [""])[0]
    year = int(date[:4]) if date[:4].isdigit() else None
    doi = (meta.get("citation_doi") or [None])[0]
    rec = Record(source="nber", id=f"w{number}", title=title, authors=authors, year=year,
                 years=[year] if year else [], container="NBER Working Paper", containers=["NBER Working Paper",
                                                                                            "National Bureau of Economic Research"],
                 doi=doi.lower() if doi else None, url=PAGE.format(number=number), type="report", number=f"w{number}",
                 publisher="National Bureau of Economic Research", api_url=api_url)
    versions = []
    pub = _PUBLISHED.search(text)
    if pub:
        for para in _PARA.findall(pub.group(1)):
            cite = _strip_tags(para)
            cite = re.sub(r"\s*citation courtesy of\s*$", "", cite, flags=re.I).strip()
            if not cite:
                continue
            # The first link is the title, in both the journal style ("Title," Journal, year)
            # and the book-chapter style (Title, authors. in Book).
            first = _ANCHOR.search(para)
            title = _strip_tags(first.group(1)).strip(" ,.\"“”") if first else ""
            versions.append({"text": cite, "title": title, "links": _HREF.findall(para)})
    return rec, versions


class Nber:
    name = "nber"

    def __init__(self, http: HttpClient):
        self.http = http

    def paper(self, number: str) -> tuple:
        """(Record or None, [published versions], Query) for working paper w<number>."""
        number = str(number).lstrip("wW")
        url = PAGE.format(number=number)
        resp = self.http.get(url, bucket="nber", headers={"Accept": "text/html"}, transform=_keep_relevant,
                             max_bytes=3_000_000)
        rec, versions = (None, [])
        if resp.ok:
            rec, versions = parse_page(resp.text(), number, resp.url)
            if not rec.title:
                rec = None
        q = query_from(self.name, "page", f"w{number}", resp, 1 if rec else 0,
                       detail=f"{len(versions)} published version(s) listed" if rec else None)
        return rec, versions, q
