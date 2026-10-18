"""arXiv export API: preprints by identifier and by title. arXiv asks for 3 seconds
between requests, which the shared client's "arxiv" bucket enforces."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from .http import HttpClient, Response
from .records import Record, query_from, skipped

BASE = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def parse_feed(body: bytes, api_url: Optional[str] = None) -> list:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    out = []
    for e in root.findall("a:entry", NS):
        ident = (e.findtext("a:id", default="", namespaces=NS) or "").strip()
        title = " ".join((e.findtext("a:title", default="", namespaces=NS) or "").split())
        if not ident or title.lower() == "error":
            continue
        arxiv_id = re.sub(r"^https?://arxiv\.org/abs/", "", ident)
        published = e.findtext("a:published", default="", namespaces=NS) or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        authors = [{"name": " ".join((a.findtext("a:name", default="", namespaces=NS) or "").split())}
                   for a in e.findall("a:author", NS)]
        doi = (e.findtext("arxiv:doi", default="", namespaces=NS) or "").strip().lower() or None
        journal = (e.findtext("arxiv:journal_ref", default="", namespaces=NS) or "").strip() or None
        out.append(Record(source="arxiv", id=arxiv_id, title=title, authors=[a for a in authors if a["name"]],
                          year=year, years=[year] if year else [], container="arXiv", containers=["arXiv"],
                          doi=doi, url=ident, type="preprint", api_url=api_url,
                          extra={k: v for k, v in {"journal_ref": journal}.items() if v}))
    return out


def _empty(resp: Response) -> bool:
    return not parse_feed(resp.body)


class Arxiv:
    name = "arxiv"

    def __init__(self, http: HttpClient):
        self.http = http

    def by_id(self, arxiv_id: str) -> tuple:
        bare = re.sub(r"v\d+$", "", arxiv_id.strip())
        resp = self.http.get(BASE, {"id_list": bare, "max_results": 1}, bucket="arxiv",
                             headers={"Accept": "application/atom+xml"}, negative_if=_empty)
        recs = parse_feed(resp.body, resp.url) if resp.ok else []
        rec = recs[0] if recs else None
        q = query_from(self.name, "id", bare, resp, 1 if rec else 0)
        if resp.ok and rec is None:
            q.status = "not_found"
        return rec, q

    def search(self, title: str, max_results: int = 5) -> tuple:
        clean = " ".join(re.sub(r"[^\w\s-]", " ", title or "").split())[:200]
        if not clean:
            return [], skipped(self.name, "search", title, "no title to search for")
        resp = self.http.get(BASE, {"search_query": f'ti:"{clean}"', "max_results": max_results}, bucket="arxiv",
                             headers={"Accept": "application/atom+xml"}, negative_if=_empty)
        recs = parse_feed(resp.body, resp.url) if resp.ok else []
        return recs, query_from(self.name, "search", clean, resp, len(recs))
