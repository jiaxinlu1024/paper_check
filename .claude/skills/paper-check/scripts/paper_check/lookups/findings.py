"""Evidence cards to findings and coverage for CIT-02, -03, -04, -05, -12 and -14.

Every finding quotes its reference block's text verbatim, points to that block, carries
lookup_record evidence with the database, the query and the record, and a trajectory of
the queries made. Coverage never records a pass for a check that could not run: a lookup
that failed gives a skipped entry with the reason, beside the run entry for the rest.
"""

from __future__ import annotations

from typing import Optional

from ..model import Coverage, Evidence, Fix
from .policy import THRESHOLDS
from .records import display_name

CHECKS = ("CIT-02", "CIT-03", "CIT-04", "CIT-05", "CIT-12", "CIT-14")
PRODUCER = "refs"
SCRIPT = "lookups"
FIELD_NAMES = {"title": "title", "authors": "author list", "year": "year", "container": "journal or series",
               "volume": "volume", "issue": "issue", "pages": "pages", "version": "version", "doi": "DOI"}


def format_citation(rec: dict) -> str:
    """An author-year citation from a record, for the writer to adapt to the journal's style."""
    people = rec.get("author_list") or [{"family": a} for a in rec.get("authors") or []]
    names = []
    for a in people:
        fam = (a.get("family") or "").strip()
        if not fam:
            continue
        given = (a.get("given") or "").replace(".", " ").split()
        initials = " ".join(g[0] + "." for g in given if g[:1].isalpha())
        names.append(f"{fam}, {initials}" if initials else fam)
    if len(names) > 1:
        who = ", ".join(names[:-1]) + ", & " + names[-1]
    else:
        who = names[0] if names else ""
    out = f"{who} ({rec.get('year') or 'n.d.'}). {str(rec.get('title') or '').rstrip('.')}."
    if rec.get("container"):
        out += f" {rec['container']}"
        if rec.get("volume"):
            out += f", {rec['volume']}" + (f"({rec['issue']})" if rec.get("issue") else "")
        if rec.get("pages"):
            out += f", {str(rec['pages']).replace('-', '–')}"
        out += "."
    if rec.get("doi"):
        out += f" https://doi.org/{rec['doi']}"
    return out
IDENTIFIER_NAMES = {"doi": "DOI", "arxiv": "arXiv ID", "nber": "NBER number", "ssrn": "SSRN ID"}


def _f(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _label(rec: Optional[dict]) -> str:
    if not rec:
        return "no record"
    names = [a.split(",")[0] for a in rec.get("authors", [])[:3]]
    who = ", ".join(n for n in names if n) + (" et al." if len(rec.get("authors", [])) > 3 else "")
    bits = [who, f"({rec['year']})" if rec.get("year") else "", f'"{rec.get("title", "")}"']
    if rec.get("container"):
        bits.append(rec["container"])
    return " ".join(b for b in bits if b)


def _join(names: list) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def rule_text() -> str:
    T = THRESHOLDS
    return (f"Settings: paper-check lookups; same work when title similarity >= {T['title']:.2f} and author overlap "
            f">= {T['author']:.2f} (RefChecker), the year within {T['year_window']} for titles below "
            f"{T['title_strong']:.2f}; verified only when two independent databases agree.")


def query_step(q: dict) -> str:
    db = display_name(q["database"])
    kind = {"doi": "DOI lookup", "search": "search", "title_search": "title search", "match": "title match",
            "handle": "DOI handle check", "agency": "registration agency", "updates": "notices filter",
            "page": "paper page", "id": "ID lookup", "content_negotiation": "content negotiation",
            "url": "link check", "wayback": "archive lookup", "title": "title lookup"}.get(q["kind"], q["kind"])
    query = q.get("query") or ""
    if len(query) > 120:
        query = query[:117] + "..."
    outcome = {"ok": f"{q.get('results', 0)} result(s)", "no_results": "no results", "not_found": "not found",
               "throttled": "throttled", "offline": "offline, not in the cache", "skipped": "skipped",
               "error": "failed"}.get(q["status"], q["status"])
    detail = f" ({q['detail']})" if q.get("detail") and q["status"] not in ("ok",) else ""
    cached = " [cached]" if q.get("from_cache") else ""
    return f'{db} {kind} "{query}": {outcome}{detail}{cached}'


def _lookup(db: str, query: str, record: Optional[dict], url: Optional[str], text: Optional[str] = None,
            **data) -> Evidence:
    rec_id = None
    if record:
        rec_id = record.get("doi") or record.get("id")
    d = {"database": display_name(db), "query": query, "record": rec_id or "no matching record"}
    if record:
        d["fields"] = {k: record[k] for k in ("title", "authors", "year", "container", "volume", "issue", "pages",
                                               "doi", "type") if record.get(k)}
    d.update({k: v for k, v in data.items() if v is not None})
    return Evidence(type="lookup_record", url=url, text=text, data=d)


def _identifier_steps(card: dict) -> list:
    ids = card.get("identifiers") or {}
    named = [f"{IDENTIFIER_NAMES.get(k, k.upper())} {v}" for k, v in ids.items() if k in IDENTIFIER_NAMES and v]
    for k in ("iza", "cepr"):
        if ids.get(k):
            named.append(f"{k.upper()} discussion paper {ids[k]}")
    if named:
        return [f"Identifiers in the entry: {'; '.join(named)}."]
    return ["No DOI, arXiv, NBER, SSRN, IZA or CEPR identifier in the entry."]


class Builder:
    def __init__(self, ctx, blocks: dict):
        self.ctx = ctx
        self.blocks = blocks
        self.findings: list = []

    def make(self, card: dict, check_id: str, title: str, severity: str, problem: str, *, evidence=None,
             trajectory=None, fix=None, confidence="high", status="confirmed", extra=None):
        block = self.blocks.get(card["ref"])
        quote = block.text if block is not None else None
        ex = {"ref": card["ref"], "key": card.get("key"), "verdict": card.get("verdict")}
        ex.update(extra or {})
        f = self.ctx.finding(check_id, title, severity, problem, block=block, quote=quote, evidence=evidence,
                             trajectory=trajectory, fix=fix, confidence=confidence, status=status, extra=ex,
                             script=SCRIPT)
        self.findings.append(f)
        return f

    # ---- CIT-02 --------------------------------------------------------------
    def existence(self, card: dict) -> None:
        verdict = card["verdict"]
        queries = card.get("queries") or []
        steps = _identifier_steps(card) + [query_step(q) for q in queries if q["kind"] not in ("handle", "updates")
                                           and q["database"] not in ("fred", "web", "archive.org", "retractionwatch")]
        if verdict == "not_found_in_databases":
            searched = card.get("searched_databases") or []
            closest = card.get("closest")
            sim = (closest or {}).get("similarity") or {}
            problem = (f"No scholarly database has a record matching this reference. {_join(searched)} "
                       f"{'were' if len(searched) > 1 else 'was'} searched with the reference text and its title")
            if closest:
                problem += (f"; the closest record, {_label(closest['record'])} in {display_name(closest['database'])}, "
                            f"shares little with it (title similarity {_f(sim.get('title'))}, author overlap "
                            f"{_f(sim.get('authors'))})")
            problem += (". A web search for the exact title is still needed before the reference can be called "
                        "non-existent.")
            if card.get("confidence_reasons"):
                problem += " Confidence is low because " + "; ".join(card["confidence_reasons"]) + "."
            failed = card.get("databases_failed") or []
            if failed:
                problem += " Not searched: " + "; ".join(f"{d['database']} ({d['reason']})" for d in failed) + "."
            evidence = [Evidence(type="checked_absence", text="No candidate passed the identity rule.",
                                 data={"scope": f"{_join(searched)} search results", "version": "live lookups",
                                       "terms": {card.get("cited", {}).get("title") or card["raw"][:120]: 0}})]
            closest_by_db = {}
            for c in card.get("candidates") or []:
                closest_by_db.setdefault(c["database"], c)
            for q in queries:
                if q["kind"] not in ("search", "title_search", "match") or q["status"] not in ("ok", "no_results"):
                    continue
                if not q.get("results"):
                    evidence.append(_lookup(q["database"], q["query"], None, q.get("url"), text="No results.",
                                            results=0))
                    continue
                best = closest_by_db.get(q["database"])
                text = f"{q['results']} candidate(s); none passed the identity rule."
                if best:
                    text += (f" Closest in {display_name(q['database'])}, not a match: {_label(best['record'])} "
                             f"(title {_f(best['similarity'].get('title'))}, authors {_f(best['similarity'].get('authors'))}).")
                evidence.append(_lookup(q["database"], q["query"], None, q.get("url"), text=text, results=q["results"],
                                        closest=best["record"] if best else None))
            steps += [f"No record passed the identity rule; closest: {_label((closest or {}).get('record'))}.",
                      rule_text(),
                      "Verdict: not found in databases. The skill's orchestration must search the web for the "
                      "exact title before the finding is confirmed."]
            self.make(card, "CIT-02", "Reference not found in any database", "critical", problem, evidence=evidence,
                      trajectory=steps, confidence=card.get("confidence") or "medium", status="likely",
                      fix=Fix(action="investigate",
                              detail=(f"Search the web for the exact title {card.get('web_check', {}).get('query', '')}. "
                                      "If no page is dedicated to the work, remove the reference or replace it with "
                                      "the work actually meant. If the work exists, add its DOI or URL."),
                              resolved_when="The reference matches a record in a scholarly database or a page "
                                            "dedicated to the work, or it is removed."),
                      extra={"needs_web_check": True, "web_check": card.get("web_check")})
        elif verdict == "chimeric" and card.get("basis") == "identifier_conflict":
            conflict = card["identifier_conflict"]
            ident = IDENTIFIER_NAMES.get(conflict["identifier"], conflict["identifier"])
            other = conflict["resolves_to"]
            sim = conflict["similarity"]
            dbs = sorted({display_name(r["database"]) for r in conflict["records"]})
            problem = (f"The {ident} {conflict['value']} belongs to a different work: {_join(dbs)} "
                       f"{'resolve' if len(dbs) > 1 else 'resolves'} it to {_label(other)}, not to the cited work "
                       f"(title similarity {_f(sim.get('title'))}, author overlap {_f(sim.get('authors'))}).")
            matched = card.get("matched")
            if conflict.get("cited_work_found_elsewhere") and matched:
                problem += f" The cited work itself is {_label(matched)}" + (
                    f", whose DOI is {matched['doi']}." if matched.get("doi") else ".")
                fix = (Fix(action="replace", original=conflict["value"], replacement=matched["doi"],
                           detail=f"In the {ident} of entry {card.get('key') or card['ref']}.",
                           resolved_when=f"The {ident} resolves to the cited work.")
                       if matched.get("doi") and conflict["identifier"] == "doi" else
                       Fix(action="investigate", detail=f"Correct the {ident} so that it points to the cited work.",
                           resolved_when=f"The {ident} resolves to the cited work."))
            else:
                problem += (" The cited title was not found in any database either, so the reference may pair a "
                            "real identifier with a work that does not exist; a web search for the exact title is "
                            "needed.")
                fix = Fix(action="investigate",
                          detail=("Find the work this reference means: search the web for the exact title. Then "
                                  f"correct or remove the {ident}, or remove the reference if the work does not exist."),
                          resolved_when=f"The {ident}, title and authors describe the same work.")
            evidence = [_lookup(r["database"], conflict["value"], r["record"], r["record"].get("api_url"),
                                similarity=r["similarity"]) for r in conflict["records"]]
            steps += [f"The {ident}'s records describe another work: {_label(other)}.", rule_text(),
                      "Verdict: chimeric (identifier conflict)."]
            status = "confirmed" if len(dbs) >= 2 else "likely"
            self.make(card, "CIT-02", f"{ident} belongs to a different work", "major", problem, evidence=evidence,
                      trajectory=steps, fix=fix, confidence="high" if len(dbs) >= 2 else "medium", status=status,
                      extra={"needs_web_check": card.get("needs_web_check", False),
                             "web_check": card.get("web_check")})
        elif verdict == "chimeric":
            conflict = card["author_conflict"]
            rec, sim = conflict["record"], conflict["similarity"]
            problem = (f"A work with this title exists, {_label(rec)}, but its authors are "
                       f"{_join(rec.get('authors', [])[:6])}, not {_join(card.get('cited', {}).get('authors', [])[:6])} "
                       f"(title similarity {_f(sim.get('title'))}, author overlap {_f(sim.get('authors'))}).")
            steps += [f"Exact title found with other authors: {_label(rec)}.", rule_text(),
                      "Verdict: chimeric (a real title with other authors)."]
            self.make(card, "CIT-02", "Title belongs to a work by other authors", "major", problem,
                      evidence=[_lookup(rec.get("source", ""), card.get("cited", {}).get("title", ""), rec,
                                        rec.get("api_url"), similarity=sim)],
                      trajectory=steps, confidence="medium", status="likely",
                      fix=Fix(action="investigate", detail="Check which work is meant, then correct the authors or "
                                                           "the title.",
                              resolved_when="Title and authors describe the same published work."),
                      extra={"needs_web_check": card.get("needs_web_check", False)})

    # ---- CIT-03 --------------------------------------------------------------
    def metadata(self, card: dict) -> None:
        if card["verdict"] != "metadata_drift":
            return
        drift = [c for c in card["field_checks"] if c["status"] == "differs"]
        if not drift:
            return
        parts, all_confirmed = [], True
        for c in drift:
            against = c.get("contradicting", list(c.get("sources") or {}))
            srcs = sorted({display_name(s) for s in against})
            name = FIELD_NAMES.get(c["field"], c["field"])
            if c["field"] == "authors":
                parts.append(f"the author list differs from {_join(srcs)}'s ({'; '.join(c['found'][:8])}): "
                             f"{c.get('detail', '')}")
            elif c["field"] == "title":
                parts.append(f"the title differs from the record's \"{c['found']}\" (similarity {_f(c.get('similarity'))}"
                             + (f"; {c['detail']}" if c.get("detail") else "") + ")")
            elif c["field"] == "version":
                parts.append(f"the DOI points to a {c['found']} record, not to the journal article cited")
            elif c["field"] == "year":
                agree = sorted(display_name(s) for s in c.get("agreeing") or [])
                parts.append(f"the year is {c['cited']}, but {_join(srcs)} {'give' if len(srcs) > 1 else 'gives'} "
                             f"{c['found']}" + (f" ({c['detail']})" if c.get("detail") else "")
                             + (f"; {_join(agree)} {'give' if len(agree) > 1 else 'gives'} {c['cited']}, as cited"
                                if agree else ""))
                if agree:
                    all_confirmed = False
            else:
                parts.append(f"the {name} is {c['cited']}, but {_join(srcs)} {'give' if len(srcs) > 1 else 'gives'} "
                             f"{c['found']}")
            if len(srcs) < 2:
                all_confirmed = False
        matched = card.get("matched") or {}
        problem = (f"The reference does not match the published record ({_label(matched)}"
                   + (f", doi:{matched['doi']}" if matched.get("doi") else "") + "): " + "; ".join(parts) + ".")
        fields = ", ".join(FIELD_NAMES.get(c["field"], c["field"]) for c in drift)
        if len(drift) == 1 and drift[0]["field"] not in ("authors", "title", "version"):
            c = drift[0]
            fix = Fix(action="replace", original=str(c["cited"]), replacement=str(c["found"]),
                      detail=f"In the {FIELD_NAMES.get(c['field'], c['field'])} of entry {card.get('key') or card['ref']}"
                             f" ({(card.get('anchor') or {}).get('file', '')}"
                             f"{':' + str(card['anchor']['line']) if (card.get('anchor') or {}).get('line') else ''}).",
                      resolved_when=f"The reference's {FIELD_NAMES.get(c['field'], c['field'])} matches the "
                                    f"published record ({c['found']}).")
        else:
            fix = Fix(action="investigate",
                      detail="Correct the entry from the published record: " + "; ".join(
                          f"{FIELD_NAMES.get(c['field'], c['field'])}: {c['found'] if not isinstance(c['found'], list) else '; '.join(c['found'])}"
                          for c in drift) + ".",
                      resolved_when="Every field of the entry matches the published record.")
        evidence = []
        for q in card.get("queries") or []:
            if q["kind"] == "doi" and q["status"] == "ok":
                rec = next((c["record"] for c in card.get("candidates") or []
                            if c["database"] == q["database"] and c["similarity"].get("same_work")), None)
                if rec:
                    evidence.append(_lookup(q["database"], q["query"], rec, q.get("url")))
        if not evidence and matched:
            evidence.append(_lookup(matched.get("source", ""), card["raw"][:200], matched, matched.get("api_url")))
        steps = _identifier_steps(card) + [query_step(q) for q in card.get("queries") or []
                                           if q["kind"] in ("doi", "search", "title_search", "match", "agency",
                                                            "content_negotiation")]
        steps += [f"Matched in {_join(card.get('matched_in') or [])}; compared title, authors, year, venue, volume, "
                  f"issue and pages.", f"Differs: {fields}.", rule_text()]
        sev = card.get("severity") or "minor"
        self.make(card, "CIT-03", f"Reference metadata differs from the published record: {fields}", sev, problem,
                  evidence=evidence, trajectory=steps, fix=fix,
                  confidence="high" if all_confirmed else "medium", status="confirmed" if all_confirmed else "likely",
                  extra={"field_checks": drift})

    # ---- CIT-03, missing parts -----------------------------------------------
    def missing_parts(self, card: dict) -> None:
        """Report the parts an entry leaves out that its matched record gives, with their values."""
        if card.get("verdict") not in ("verified", "metadata_drift", "single_source"):
            return
        raw = (card.get("raw") or "").lower()
        missing = [c for c in card.get("field_checks") or [] if c.get("status") == "missing"]
        # a DOI printed in the entry but not parsed into its own field is not missing
        missing = [c for c in missing if not (c["field"] == "doi" and str(c["found"]).lower() in raw)]
        if not missing:
            return
        core = {"year", "authors", "container", "volume", "pages"}
        sev = "minor" if any(c["field"] in core for c in missing) else "suggestion"
        names = [FIELD_NAMES.get(c["field"], c["field"]) for c in missing]

        def show(c):
            v = c["found"]
            return "; ".join(v) if isinstance(v, list) else str(v)
        values = "; ".join(f"{FIELD_NAMES.get(c['field'], c['field'])}: {show(c)}" for c in missing)
        matched = card.get("matched") or {}
        problem = (f"The reference leaves out its {_join(names)}. The published record ({_label(matched)}"
                   + (f", doi:{matched['doi']}" if matched.get("doi") else "") + f") gives {values}.")
        evidence = [_lookup(matched.get("source", ""), card["raw"][:200], matched, matched.get("api_url"))] if matched else []
        where = (card.get("anchor") or {}).get("file", "")
        line = (card.get("anchor") or {}).get("line")
        fix = Fix(action="insert",
                  detail=f"Add to entry {card.get('key') or card['ref']}" + (f" ({where}:{line})" if where and line else "")
                         + f": {values}. A complete version from the record: {format_citation(matched)}",
                  resolved_when="The entry gives every part its citation style requires: authors, year, title, "
                                "journal, volume, issue, pages, and the DOI where the style uses DOIs.")
        steps = [f"Matched in {_join(card.get('matched_in') or [])}.",
                 f"Compared the entry's parts with the record: {_join(names)} absent from the entry."]
        self.make(card, "CIT-03", f"Reference entry is missing its {_join(names)}", sev, problem,
                  evidence=evidence, trajectory=steps, fix=fix,
                  confidence="high" if card.get("verdict") == "verified" else "medium",
                  status="confirmed" if card.get("verdict") == "verified" else "likely",
                  extra={"missing": [c["field"] for c in missing], "values": {c["field"]: c["found"] for c in missing}})

    # ---- CIT-04 --------------------------------------------------------------
    def versions(self, card: dict) -> None:
        info = card.get("version_check") or {}
        links = card.get("version_links") or []
        if not links:
            return
        best = links[0]
        who = _join([a for a in best.get("authors", [])[:4] if a])
        problem = (f"This reference cites a working paper or preprint ({info.get('why')}), but a published version "
                   f"exists: {who} ({best.get('year')}), \"{best.get('title')}\""
                   + (f", {best['container']}" if best.get("container") else "")
                   + (f", doi:{best['doi']}" if best.get("doi") else "")
                   + f". Found by: {'; '.join(best['basis'])}. Cite the published version, or say why the working "
                     f"paper is cited.")
        if len(links) > 1:
            problem += " Other candidates: " + "; ".join(f"\"{l['title']}\" ({l.get('year')})" for l in links[1:3]) + "."
        evidence = [_lookup(l["database"], card.get("cited", {}).get("title") or card["raw"][:200],
                            {"doi": l.get("doi"), "title": l.get("title"), "year": l.get("year"),
                             "container": l.get("container"), "authors": l.get("authors"), "type": l.get("type")},
                            l.get("url"), similarity=l.get("similarity"), basis=l.get("basis")) for l in links[:3]]
        steps = [f"Working paper or preprint: {info.get('why')}."]
        steps += [query_step(q) for q in card.get("queries") or [] if q.get("stage") == "versions"]
        steps += [f"Accepted {best.get('doi') or best.get('title')}: author overlap {_f(best['similarity'].get('authors'))}, "
                  f"title similarity {_f(best['similarity'].get('title'))}, year difference "
                  f"{best['similarity'].get('year_difference')}; score {_f(best['similarity'].get('score'))} against "
                  f"{THRESHOLDS['version_score']:.2f} (authors weighted above the title)."]
        steps += info.get("notes") or []
        self.make(card, "CIT-04", "A published version of this working paper exists", "suggestion", problem,
                  evidence=evidence, trajectory=steps, confidence=best.get("confidence", "medium"), status="likely",
                  fix=Fix(action="replace", original=card.get("raw"), replacement=format_citation(best),
                          detail="Replace the entry with the published version, in the journal's citation style, "
                                 "unless the working paper is cited on purpose; check that the cited claims still "
                                 "hold in the published version.",
                          resolved_when="The reference cites the published version, or the text says why the working "
                                        "paper is cited."),
                  extra={"published_version": best})

    # ---- CIT-05 --------------------------------------------------------------
    def retractions(self, card: dict, assessment: Optional[dict]) -> None:
        if not assessment:
            return
        notices = [n for n in card.get("retraction_notices") or []]
        parts = []
        for n in notices:
            bit = f"{n.get('label') or n['type']}"
            if n.get("notice_doi"):
                bit += f" {n['notice_doi']}"
            if n.get("date"):
                bit += f" ({n['date']})"
            if n.get("notice_title"):
                bit += f", \"{n['notice_title']}\""
            bit += f" [{', '.join(n['sources'])}]"
            if n.get("reason"):
                bit += f"; reason: {n['reason']}"
            parts.append(bit)
        advice = {"retraction": " A retracted work should be cited only to discuss the retraction.",
                  "expression_of_concern": " Check whether the paper relies on the results the notice questions, and "
                                           "say so if it does.",
                  "correction": " Check whether the correction changes the result the paper cites.",
                  "reinstated": " Check the notices and say in the paper how they bear on the cited result."}
        problem = (f"Editorial notices are recorded for this work ({_label(card.get('matched'))}): "
                   + "; ".join(parts) + "." + advice.get(assessment["kind"], ""))
        evidence = [_lookup("crossref" if any(s.startswith("Crossref") for s in n["sources"]) else
                            ("openalex" if "OpenAlex is_retracted" in n["sources"] else "retractionwatch"),
                            ", ".join(card.get("retraction_dois") or []) or card.get("cited", {}).get("title", ""),
                            {"doi": n.get("notice_doi"), "title": n.get("notice_title"), "type": n["type"]},
                            f"https://doi.org/{n['notice_doi']}" if n.get("notice_doi") else None,
                            notice_type=n["type"], date=n.get("date"), sources=n["sources"]) for n in notices]
        steps = [f"DOIs checked: {', '.join(card.get('retraction_dois') or []) or 'none'}."]
        steps += [query_step(q) for q in card.get("queries") or [] if q["kind"] in ("updates", "title")
                  or q.get("stage") == "retractions"]
        steps += [f"Sources read: {', '.join(card.get('retraction_checked') or [])}. Notices are never filtered by "
                  f"subject."]
        self.make(card, "CIT-05", assessment["title"], assessment["severity"], problem, evidence=evidence,
                  trajectory=steps, confidence="high" if assessment["status"] == "confirmed" else "medium",
                  status=assessment["status"],
                  fix=Fix(action="investigate", detail=advice.get(assessment["kind"], "").strip() or
                          "Check how the notices bear on the cited result.",
                          resolved_when="The paper cites the work only in ways the notices allow, and says so where "
                                        "it matters."),
                  extra={"notices": notices})

    # ---- CIT-12 --------------------------------------------------------------
    def links(self, card: dict) -> None:
        for item in card.get("links") or []:
            if not item.get("dead"):
                continue
            if item["kind"] == "doi":
                matched = card.get("matched") or {}
                problem = f"The DOI {item['value']} does not exist: the doi.org handle service answers 'not found'."
                if matched.get("doi") and matched["doi"] != item["value"]:
                    problem += f" The work matched in {_join(card.get('matched_in') or [])} has DOI {matched['doi']}."
                    fix = Fix(action="replace", original=item["value"], replacement=matched["doi"],
                              detail=f"In the DOI of entry {card.get('key') or card['ref']}.",
                              resolved_when="The DOI resolves at doi.org to the cited work.")
                else:
                    fix = Fix(action="investigate", detail="Correct the DOI, or remove it if the work has none.",
                              resolved_when="The DOI resolves at doi.org to the cited work.")
                self.make(card, "CIT-12", "DOI does not resolve", "minor", problem,
                          evidence=[_lookup("doi.org", item["value"], None, f"https://doi.org/api/handles/{item['value']}",
                                            text="Handle not found (responseCode 100).")],
                          trajectory=[query_step(q) for q in card.get("queries") or [] if q["kind"] == "handle"]
                                     + ["A DOI that does not exist cannot be followed by readers."],
                          fix=fix, confidence="high", status="confirmed", extra={"link": item})
            else:
                snap = item.get("archived")
                what = {"missing": f"answers HTTP {item.get('http_status')} (not found)",
                        "unreachable": f"could not be reached ({item.get('error', 'no answer')})"}.get(item["status"],
                                                                                                    item["status"])
                problem = f"The link {item['value']} {what}."
                problem += (f" An archived copy exists: {snap['url']}." if snap else
                            " No archived copy was found in the Internet Archive.")
                fix = (Fix(action="replace", original=item["value"], replacement=snap["url"],
                           detail=f"In the URL of entry {card.get('key') or card['ref']}, or use the work's current "
                                  "address.", resolved_when="The link opens the cited material.")
                       if snap else Fix(action="investigate", detail="Find the material's current address, or remove "
                                                                     "the link.",
                                        resolved_when="The link opens the cited material."))
                self.make(card, "CIT-12", "Link is dead", "minor", problem,
                          evidence=[_lookup("web", item["value"], None, item["value"],
                                            http_status=item.get("http_status"), outcome=item["status"])],
                          trajectory=[query_step(q) for q in card.get("queries") or [] if q["kind"] in ("url", "wayback")],
                          fix=fix, confidence="medium", status="likely", extra={"link": item})

    # ---- CIT-14 --------------------------------------------------------------
    def replications(self, card: dict) -> None:
        reps = [r for r in card.get("replications") or [] if r.get("severity")]
        if not reps:
            return
        order = {"major": 0, "minor": 1}
        sev = min((r["severity"] for r in reps), key=lambda s: order.get(s, 9))
        total = len(card.get("replications") or [])
        parts = []
        for r in reps[:6]:
            who = (r.get("replication_reference") or r.get("replication_title") or r.get("replication_doi") or "").strip()
            bit = f"{who.rstrip('.')}. FReD labels it \"{r.get('outcome')}\"."
            if r.get("outcome_quote"):
                q = r["outcome_quote"].strip()
                bit += f" In its own words: \"{q}\"" + ("" if q[-1:] in ".!?" else ".")
            parts.append(bit)
        labels = sorted({r.get("outcome") for r in reps})
        problem = (f"The FORRT Replication Database lists {total} replication or reproduction record(s) of this work. "
                   + " ".join(parts)
                   + " If the paper relies on this result, say how the replication bears on it and cite the "
                     "replication. FReD's label describes the replication attempt; it is not a verdict that the "
                     "original result is false.")
        evidence = [_lookup("fred", r.get("original_doi") or card.get("cited", {}).get("title", ""),
                            {"doi": r.get("replication_doi"), "title": r.get("replication_title"),
                             "year": r.get("replication_year")}, r.get("url"),
                            text=f"Replication conclusion ({r.get('quote_source') or 'source not given'}): "
                                 f"\"{r.get('outcome_quote', '')}\"",
                            outcome=r.get("outcome"), type=r.get("type"), matched_by=r.get("matched_by"))
                    for r in reps]
        steps = [f"Looked up {', '.join(card.get('retraction_dois') or []) or 'the title'} in FReD's paper-level file "
                 f"(FLoRA, CC BY 4.0).",
                 f"{total} record(s) found; outcomes needing a look: {', '.join(labels)}.",
                 "Whether the paper relies on the result without saying so is a reading question, so the status is "
                 "needs human judgment."]
        title = ("A replication of this work was labelled failed" if sev == "major" else
                 "Replications of this work report mixed or qualified results")
        self.make(card, "CIT-14", title, sev, problem, evidence=evidence, trajectory=steps, confidence="medium",
                  status="needs_human",
                  fix=Fix(action="investigate", detail="Read the replication, then mention it and its outcome where "
                                                       "the paper relies on the original result.",
                          resolved_when="The paper acknowledges the replication wherever it relies on the result."),
                  extra={"replications": reps})


def coverage_entries(check_id: str, run_note: Optional[str], count: int, skipped: Optional[str] = None,
                     not_applicable: Optional[str] = None) -> list:
    out = []
    if run_note is not None:
        out.append(Coverage(check_id, "run", run_note, PRODUCER, count))
    if skipped:
        out.append(Coverage(check_id, "skipped", skipped, PRODUCER))
    if not_applicable and run_note is None and not skipped:
        out.append(Coverage(check_id, "not_applicable", not_applicable, PRODUCER))
    return out
