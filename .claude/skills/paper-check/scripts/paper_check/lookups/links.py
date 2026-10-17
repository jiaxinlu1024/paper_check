"""DOIs and URLs in references resolve; dead links get an archived alternative (CIT-12).

- A DOI is checked with the doi.org handle API, which says whether the DOI exists without
  visiting the publisher's site.
- A URL is fetched with a small byte limit and no stored body. Outcomes follow the
  categories of Crossref's 2026 reference-rot sprint, simplified: ok, redirected to another
  site, blocked (401, 403, 429: the site answers but refuses scripts, which is not a dead
  link), missing (404, 410), server error, unreachable. Missing and unreachable links are
  dead, and the Internet Archive's availability API is asked for a snapshot.
- Requests to arbitrary sites do not carry the contact email; only scholarly APIs get it.
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

from . import identifiers
from .http import PROJECT_URL
from .records import query_from
from .. import __version__

WAYBACK = "https://archive.org/wayback/available"
PLAIN_UA = f"paper-check/{__version__} (+{PROJECT_URL})"


def _host(url: Optional[str]) -> str:
    return urllib.parse.urlsplit(url or "").netloc.lower().removeprefix("www.")


def check_url(url: str, services) -> tuple:
    http = services.http
    resp = http.get(url, headers={"User-Agent": PLAIN_UA, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8"},
                    max_bytes=65536, store_body=False, max_retries=1, retry_after_cap=10, timeout=20)
    q = query_from("web", "url", url, resp, 1 if resp.ok else 0)
    st = resp.status
    if resp.offline_miss:
        status = "unchecked"
    elif st is None:
        status = "unreachable"
    elif 200 <= st < 300:
        status = "redirected" if resp.final_url and _host(resp.final_url) != _host(url) else "ok"
    elif st in (401, 403, 429, 451):
        status = "blocked"
    elif st in (404, 410):
        status = "missing"
    elif st >= 500:
        status = "server_error"
    else:
        status = f"http_{st}"
    out = {"kind": "url", "value": url, "status": status, "http_status": st,
           "dead": status in ("missing", "unreachable")}
    if resp.final_url and resp.final_url != url:
        out["final_url"] = resp.final_url
    if resp.error and st is None:
        out["error"] = resp.error
    return out, q


def wayback(url: str, services) -> tuple:
    resp = services.http.get(WAYBACK, {"url": url}, bucket="archive.org", headers={"Accept": "application/json"},
                             max_retries=1, timeout=30)
    snap = (((resp.json() or {}).get("archived_snapshots") or {}).get("closest") or {}) if resp.ok else {}
    found = snap.get("url") if snap.get("available") else None
    q = query_from("archive.org", "wayback", url, resp, 1 if found else 0)
    return ({"url": found, "timestamp": snap.get("timestamp")} if found else None), q


def check_links(rc, services) -> list:
    """Every DOI and URL of one reference (policy.ReferenceCheck after run())."""
    out, seen = [], set()
    dois = [rc.ids.get("doi")] if rc.ids.get("doi") else []
    urls = []
    for u in rc.ids.get("urls") or []:
        if identifiers.is_doi_url(u):
            d = identifiers.clean_doi(u)
            if d and d not in dois:
                dois.append(d)
        else:
            urls.append(u)
    for d in dois:
        if d in seen:
            continue
        seen.add(d)
        exists, target, q = services.doiorg.handle(d)
        rc.log(q)
        status = {True: "resolves", False: "does_not_exist"}.get(exists, "unchecked")
        item = {"kind": "doi", "value": d, "status": status, "dead": exists is False}
        if target:
            item["target"] = target
        if exists is None:
            item["error"] = q.detail or q.status
        out.append(item)
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        item, q = check_url(u, services)
        rc.log(q)
        if item["dead"]:
            snap, q2 = wayback(u, services)
            rc.log(q2)
            item["archived"] = snap
        out.append(item)
    return out
