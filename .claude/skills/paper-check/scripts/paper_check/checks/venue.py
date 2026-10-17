"""Checks driven by the venue profile and by journal and data-editor policies.

FMT-01  venue limits: abstract words, manuscript words or pages, exhibits, file size
FMT-03  required statements that belong in the manuscript (disclosure, funding,
        data availability, ethics, declarations sections)
BEH-06  registration claims without a registry ID; AEA field RCTs without a registration
BEH-12  where the IRB or ethics statement is, against the venue rule
BEH-16  JEL codes, keywords and highlights the journal asks for

A profile rule may be confirmed (quoted from the journal's own pages) or
unconfirmed. Unconfirmed rules are used, but their findings say so and are marked
likely. Profile `detail` texts are free text, so where a statement must go is read
from cue phrases; anything this module cannot place is listed as a reminder rather
than reported as missing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..model import Anchor, Evidence, Fix
from ..textutil import word_count
from . import register
from .format import (PROSE_KINDS, add_location, block_quote, compact, doc_anchor, in_appendix, input_format, is_hidden,
                     note_coverage, pdf_facts, prose, quote_at, related, review_type, rule_caveat, rule_confirmed,
                     rule_evidence, rule_status, sentence_bounds, sentence_quote, setting, venue_name, venue_other,
                     venue_rule, venue_steps)

SCRIPT = "checks/venue.py"


def _ws_words(text: str) -> int:
    """Whitespace-delimited strings, the way the AEA word counter counts."""
    return len(text.split())


# =============================================================== FMT-01 venue limits
_HARD = re.compile(r"returned without review|rejected without review|desk[- ]reject|will not be (?:reviewed|considered)|"
                   r"hard limit|strict(?:ly)? (?:limit|enforced)|must not exceed|may not exceed", re.I)
_SOFT = re.compile(r"recommend|not a hard cap|guideline|strongly suggest|no mechanical limit|accepted papers|"
                   r"invited revisions", re.I)


_NOT_HARD = re.compile(r"not a hard cap|not a desk[- ]reject|recommend|no mechanical limit|no size limit|"
                       r"enforced from the first revision|no limit on first|no (?:size )?limit at (?:first )?submission", re.I)


def _limit_strength(ctx, r: dict) -> str:
    """'hard' (returned without review), 'soft' (a recommendation) or 'stated'."""
    value = r.get("value")
    text = " ".join(str(x) for x in ((" ".join(str(v) for v in value.values()) if isinstance(value, dict) else value),
                                     r.get("note") or "", r.get("quote") or ""))
    enforcement = venue_other(ctx, "length_enforcement")
    if enforcement:
        text += " " + str(enforcement.get("value") or "")
    if _NOT_HARD.search(text):
        return "soft"
    if _HARD.search(text):
        return "hard"
    if _SOFT.search(text):
        return "soft"
    return "stated"


def _scope_parts(scope: str) -> dict:
    """Which parts of the paper a word limit counts, from the profile's scope text."""
    scope = (scope or "").lower()
    head, _, tail = scope.partition("exclud")
    def says(part_words, text):
        return any(w in text for w in part_words)
    parts = {
        "main text": True,
        "footnotes": not says(("footnote",), tail),
        "appendices": says(("appendi",), head) or not says(("appendi",), tail),
        "abstract": says(("abstract",), head) and not says(("abstract",), tail),
        "references": says(("reference",), head) and not says(("reference",), tail),
        "tables and figures": (says(("table", "figure", "exhibit", "caption"), head)
                               and not says(("table", "figure", "exhibit"), tail)),
        "title and authors": False,
    }
    if "online appendix" in tail or "supplemental appendix" in tail or "supplementary appendix" in tail:
        parts["online appendix"] = False
    if "total text" in head or "all inclusive" in head:
        parts.update({"abstract": True, "references": True, "tables and figures": True})
    return parts


def _online_appendix(pm, b) -> bool:
    return any(re.search(r"online appendix|supplement(?:al|ary)? appendix|web appendix", s, re.I) for s in b.section or [])


def _manuscript_words(pm, scope: str) -> tuple:
    parts = _scope_parts(scope)
    kinds = {"paragraph", "list_item", "heading", "equation"}
    if parts["footnotes"]:
        kinds.add("footnote")
    if parts["abstract"]:
        kinds.add("abstract")
    if parts["references"]:
        kinds.add("reference")
    if parts["tables and figures"]:
        kinds.update({"table", "caption"})
    total, by_kind = 0, {}
    for b in pm.blocks:
        if b.kind not in kinds or is_hidden(b) or b.attrs.get("generated") and b.kind == "heading":
            continue
        if not parts["appendices"] and in_appendix(pm, b):
            continue
        if _online_appendix(pm, b):
            continue
        n = _ws_words(b.text.replace(" | ", " "))
        total += n
        by_kind[b.kind] = by_kind.get(b.kind, 0) + n
    return total, by_kind, parts


def _exhibits(pm, which: str = "exhibit") -> int:
    """Tables and figures outside an online appendix; `which` is exhibit, figure or table."""
    n = 0
    objs = {"figure": list(pm.figures), "table": list(pm.tables)}.get(which, list(pm.tables) + list(pm.figures))
    for o in objs:
        cap = pm.block(o.caption_block) if o.caption_block else None
        if cap is not None and _online_appendix(pm, cap):
            continue
        n += 1
    return n


def _per_exhibit(ctx, scope: str) -> tuple:
    """(words deducted per item, which items: exhibit, figure or table)."""
    m = re.search(r"(\d{2,4})\s*words?\s*(?:per|for each|each)\s*(?:standard\s+)?(exhibit|figure|table)", scope or "", re.I)
    if m:
        return int(m.group(1)), m.group(2).lower()
    m = re.search(r"(?:falls|reduces?|deduct)\D{0,30}(\d{2,4})\s*words", scope or "", re.I)
    if m:
        return int(m.group(1)), "exhibit"
    o = venue_other(ctx, "figure_word_deduction")
    if o and isinstance(o.get("value"), dict) and o["value"].get("words_per_figure"):
        return int(o["value"]["words_per_figure"]), "figure"
    return 0, "exhibit"


def _page_count(pm) -> Optional[int]:
    md = pm.metadata or {}
    for k in ("page_count", "pages", "n_pages", "num_pages"):
        v = md.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, list):
            return len(v)
    if input_format(pm) == "pdf":
        n = pdf_facts(pm).get("page_count")
        return int(n) if isinstance(n, int) else None
    return None


@register("FMT-01")
def venue_limits(pm, ctx):
    if not ctx.venue:
        ctx.skip("FMT-01", "no venue profile given; limits are checked against a profile (pc.py ingest PAPER --venue ID)")
        return
    fmt = input_format(pm)
    vname = venue_name(ctx)
    steps = venue_steps(ctx)
    compared, not_checked = [], []
    any_rule = False

    # abstract length
    r = venue_rule(ctx, "abstract_max_words")
    if r and isinstance(r.get("value"), (int, float)):
        any_rule = True
        limit = int(r["value"])
        abstracts = [b for b in pm.blocks if b.kind == "abstract" and not is_hidden(b)]
        if not abstracts:
            yield add_location(ctx.finding(
                "FMT-01", "No abstract found", "major",
                f"{vname} asks for an abstract of at most {limit} words, but no abstract was found in the paper map."
                + rule_caveat(r), status="likely", confidence="medium",
                evidence=[rule_evidence(ctx, "abstract_max_words", r),
                          Evidence(type="checked_absence", text="abstract",
                                   data={"scope": "all blocks", "terms": {"abstract block": 0}})],
                trajectory=steps + ["Looked for a block of kind abstract."],
                fix=Fix(action="insert", detail=f"Add an abstract of at most {limit} words.",
                        resolved_when="The paper opens with an abstract within the limit."),
                script=SCRIPT), doc_anchor(pm))
        else:
            text = " ".join(b.text for b in abstracts)
            n_ws, n_tok = _ws_words(text), word_count(text)
            compared.append(f"abstract {n_ws} words against {limit}")
            if min(n_ws, n_tok) > limit or max(n_ws, n_tok) > limit:
                over = min(n_ws, n_tok) > limit
                b = abstracts[0]
                quote = sentence_quote(b, max(0, len(b.text) - 2), 30)
                yield ctx.finding(
                    "FMT-01", "Abstract over the word limit" if over else "Abstract at the word limit",
                    "critical" if over else "suggestion",
                    f"The abstract has {n_ws} words (whitespace-delimited; {n_tok} by word tokens), and {vname} allows "
                    f"at most {limit}." + ("" if over else " The two counts straddle the limit, so check with the "
                                           "journal's own counter.") + rule_caveat(r),
                    block=b, quote=quote, status=(rule_status(r) if over else "needs_human"),
                    evidence=[Evidence(type="computed_result", text="abstract word count",
                                       data={"formula": "number of whitespace-delimited strings", "inputs":
                                             {"blocks": [x.id for x in abstracts]}, "output": n_ws, "tolerance": 0,
                                             "word_tokens": n_tok, "limit": limit}),
                              rule_evidence(ctx, "abstract_max_words", r)],
                    trajectory=steps + [f"Counted the abstract's words: {n_ws} strings, {n_tok} word tokens; limit "
                                        f"{limit}."],
                    fix=Fix(action="investigate", detail=f"Cut the abstract by at least {n_ws - limit} words.",
                            resolved_when=f"The abstract has at most {limit} words."),
                    script=SCRIPT, extra={"words": n_ws, "limit": limit})

    # manuscript length
    r = venue_rule(ctx, "manuscript_limit")
    if r and isinstance(r.get("value"), dict) and r["value"].get("amount"):
        any_rule = True
        v = r["value"]
        amount, unit, scope = int(v["amount"]), str(v.get("unit") or "").lower(), str(v.get("scope") or "")
        strength = _limit_strength(ctx, r)
        sev_over = {"hard": "critical", "soft": "minor", "stated": "major"}[strength]
        if unit.startswith("word"):
            count, by_kind, parts = _manuscript_words(pm, scope)
            per, which = _per_exhibit(ctx, scope)
            exhibits = _exhibits(pm, which)
            limit = amount - per * exhibits
            counted = ", ".join(k for k, inc in parts.items() if inc)
            compared.append(f"{count} words against {limit} ({amount}" + (f" less {per} x {exhibits} {which}s" if per else "")
                            + f"); counted: {counted}")
            approx = "approximate: counted from the source text, not the journal's own counter"
            if count > limit * 1.03 or (count > limit and count - limit > 60):
                yield add_location(ctx.finding(
                    "FMT-01", "Manuscript over the word limit", sev_over,
                    f"By this count the manuscript has about {count} words, over {vname}'s limit of {limit}"
                    + (f" ({amount} less {per} for each of {exhibits} {which}s)" if per else "") + f". Counted: {counted}."
                    + (" Over-limit papers are returned without review." if strength == "hard" else "")
                    + rule_caveat(r),
                    status="likely", confidence="medium",
                    evidence=[Evidence(type="computed_result", text="manuscript word count",
                                       data={"formula": "whitespace-delimited strings in the counted blocks", "inputs":
                                             by_kind, "output": count, "limit": limit, "tolerance": "3%", "note": approx}),
                              rule_evidence(ctx, "manuscript_limit", r)],
                    trajectory=steps + [f"Counted words by block kind: {by_kind}.",
                                        f"Limit {amount}" + (f" - {per} x {exhibits} {which}s = {limit}" if per else "") + "."],
                    fix=Fix(action="investigate", detail=f"Cut about {count - limit} words, or move material to an "
                                                         "online appendix if the journal allows it.",
                            resolved_when=f"The journal's own count is at most {limit} words."),
                    script=SCRIPT, extra={"words": count, "limit": limit}), doc_anchor(pm))
            elif count > limit * 0.95:
                yield add_location(ctx.finding(
                    "FMT-01", "Manuscript close to the word limit", "suggestion",
                    f"By this count the manuscript has about {count} words against {vname}'s limit of {limit}. The "
                    "journal's own count may differ by a few percent; check it before submitting." + rule_caveat(r),
                    status="needs_human", confidence="medium",
                    evidence=[Evidence(type="computed_result", text="manuscript word count",
                                       data={"formula": "whitespace-delimited strings", "inputs": by_kind, "output": count,
                                             "limit": limit, "note": approx}),
                              rule_evidence(ctx, "manuscript_limit", r)],
                    trajectory=steps + [f"Counted words by block kind: {by_kind}."],
                    fix=Fix(action="investigate", detail="Run the journal's word counter on the final PDF.",
                            resolved_when=f"The official count is at most {limit} words."),
                    script=SCRIPT, extra={"words": count, "limit": limit}), doc_anchor(pm))
        elif unit.startswith("page"):
            pages = _page_count(pm)
            desk = venue_other(ctx, "desk_reject_length")
            desk_max = (desk.get("value") or {}).get("max_pages") if desk and isinstance(desk.get("value"), dict) else None
            if pages is None:
                what = f"the {amount}-page {'limit' if strength != 'soft' else 'recommendation'}"
                if desk_max:
                    what += f" ({desk_max} pages or more is rejected without review)"
                not_checked.append(f"{what}: the page count is not computable from {fmt} input")
                if strength == "hard" or desk_max:
                    yield add_location(ctx.finding(
                        "FMT-01", "Page limit not checked", "suggestion",
                        f"{vname} enforces a page limit ({compact(v, 200)}), and the page count cannot be computed "
                        f"from {fmt} input. Check the compiled PDF." + rule_caveat(r),
                        status="needs_human", confidence="high",
                        evidence=[rule_evidence(ctx, "manuscript_limit", r)],
                        trajectory=steps + [f"Looked for a page count in the paper map: none for {fmt} input."],
                        fix=Fix(action="investigate", detail="Count the pages of the compiled PDF, or run this check on "
                                                             "the PDF (pc.py ingest paper.pdf).",
                                resolved_when=f"The compiled manuscript has at most {amount} pages."),
                        script=SCRIPT), doc_anchor(pm))
            else:
                compared.append(f"{pages} pages against {amount}")
                over_desk = bool(desk_max) and pages > int(desk_max)
                if pages > amount or over_desk:
                    sev = "critical" if over_desk else ("major" if desk_max and sev_over == "critical" else sev_over)
                    yield add_location(ctx.finding(
                        "FMT-01", "Manuscript over the page limit", sev,
                        f"The PDF has {pages} pages; {vname}'s limit is {amount} ({compact(scope, 200)})."
                        + (f" Papers over {desk_max} pages are rejected without review." if over_desk else "")
                        + rule_caveat(r), status=rule_status(r),
                        evidence=[Evidence(type="computed_result", text="page count",
                                           data={"formula": "pages in the PDF", "output": pages, "limit": amount}),
                                  rule_evidence(ctx, "manuscript_limit", r)],
                        trajectory=steps + [f"Read the page count: {pages}."],
                        fix=Fix(action="investigate", detail="Shorten the paper or move material to an online appendix; "
                                                             "check the journal's formatting assumptions (font size, "
                                                             "spacing, margins).",
                                resolved_when=f"The manuscript has at most {amount} pages in the journal's format."),
                        script=SCRIPT, extra={"pages": pages, "limit": amount}),
                        Anchor(file=Path(str(pm.source.get("path", ""))).name, page=pages))

    # exhibit limit
    o = venue_other(ctx, "exhibit_limit")
    if o and isinstance(o.get("value"), dict) and o["value"].get("max_exhibits"):
        any_rule = True
        mx = int(o["value"]["max_exhibits"])
        n = _exhibits(pm)
        compared.append(f"{n} exhibits against {mx}")
        if n > mx:
            yield add_location(ctx.finding(
                "FMT-01", "Too many exhibits", "critical" if venue_other(ctx, "length_enforcement") else "major",
                f"The paper has {n} tables and figures; {vname} allows at most {mx}." + rule_caveat(o),
                status=rule_status(o),
                evidence=[Evidence(type="computed_result", text="exhibits",
                                   data={"formula": "tables + figures outside an online appendix", "output": n, "limit": mx}),
                          rule_evidence(ctx, "other.exhibit_limit", o)],
                trajectory=steps + [f"Counted {len(pm.tables)} tables and {len(pm.figures)} figures."],
                fix=Fix(action="investigate", detail="Merge exhibits or move some to the online appendix.",
                        resolved_when=f"The paper has at most {mx} exhibits."),
                script=SCRIPT, extra={"exhibits": n, "limit": mx}), doc_anchor(pm))

    # file type and size
    r = venue_rule(ctx, "file_format")
    if r and r.get("value"):
        any_rule = True
        text = str(r["value"])
        m = re.search(r"(\d+(?:\.\d+)?)\s*MB", text)
        if fmt == "pdf" and m:
            size = pdf_facts(pm).get("file_size")
            if size:
                mb = size / (1024 * 1024)
                compared.append(f"file size {mb:.1f} MB against {m.group(1)} MB")
                if mb > float(m.group(1)):
                    yield add_location(ctx.finding(
                        "FMT-01", "PDF larger than the journal asks", "minor",
                        f"The PDF is {mb:.1f} MB; {vname} asks for files under {m.group(1)} MB." + rule_caveat(r),
                        status=rule_status(r),
                        evidence=[Evidence(type="computed_result", text="file size",
                                           data={"formula": "bytes / 2^20", "inputs": {"bytes": size},
                                                 "output": round(mb, 2), "limit_mb": float(m.group(1))}),
                                  rule_evidence(ctx, "file_format", r)],
                        trajectory=steps + ["Read the size of the PDF file."],
                        fix=Fix(action="investigate", detail="Compress images (for example with Ghostscript) or "
                                                             "downsample figures.",
                                resolved_when=f"The PDF is under {m.group(1)} MB."),
                        script=SCRIPT), Anchor(file=Path(str(pm.source.get("path", ""))).name))
        elif fmt != "pdf":
            not_checked.append(f"the submitted file's type and size ({compact(text, 120)}) cannot be checked from "
                               f"{fmt} input")
    if not any_rule:
        ctx.skip("FMT-01", f"the {vname} profile records no length, exhibit or file limits")
        return
    note_coverage(ctx, "FMT-01", "; ".join(["compared " + ", ".join(compared)] if compared else [])
                  + ("; not checked: " + "; ".join(not_checked) if not_checked else ""))


# =============================================================== FMT-03 required statements
_DISCLOSURE = re.compile(r"conflicts? of interests?|competing (?:financial )?interests?|declarations? of (?:competing )?"
                         r"interests?|disclosure statement|nothing to disclose|(?:have|has|declare[sd]?) no (?:relevant |"
                         r"competing |financial |conflicting )*(?:conflicts?|interests?)|no (?:relevant )?(?:financial )?"
                         r"(?:conflicts?|competing interests?)", re.I)
_FUNDING = re.compile(r"\bfunding\b|financial support|funded by|financially supported|grant (?:no|number|agreement)|"
                      r"supported by (?:a |the )?(?:grant|national|european|foundation)|received no (?:specific )?funding|"
                      r"acknowledge[sd]? (?:the )?(?:financial )?support", re.I)
_DATA = re.compile(r"data (?:and code )?availability|replication (?:package|files|materials?)|data (?:and code )?(?:are|is|will "
                   r"be) (?:publicly |openly )?(?:available|deposited)|available (?:at|from|on) (?:https?://|the |openicpsr|"
                   r"zenodo|harvard dataverse|osf|icpsr)|openicpsr|zenodo|dataverse", re.I)
_ETHICS = re.compile(r"\bIRB\b|institutional review board|ethics (?:committee|board|council|review)|ethic(?:al|s) "
                     r"(?:approval|clearance|review)|research ethics|human subjects? (?:committee|review|protection)|"
                     r"approved by the [^.]{0,80}(?:board|committee)|exempt(?:ion)? (?:from|by|under) [^.]{0,60}"
                     r"(?:review|board|committee|IRB)", re.I)
# Human-subjects research the paper ran itself, not a literature review mentioning experiments,
# "seminar participants" or "market participants".
_HUMAN = re.compile(
    r"\bwe (?:ran|run|conduct(?:ed)?|carr(?:y|ied) out|recruit(?:ed)?|survey(?:ed)?|interview(?:ed)?|randomi[sz]e(?:d)?|"
    r"invite(?:d)?|pa(?:y|id)|elicit(?:ed)?)\b"
    r"|\bour (?:lab(?:oratory)? |field |online |survey )?(?:experiments?|survey|participants|subjects|respondents|trial|"
    r"sessions?|intervention|sample of (?:participants|employees|students|workers|respondents))\b"
    r"|\b(?:participants|subjects|respondents|employees|students|workers) (?:were|was) (?:paid|told|randomly|recruited|"
    r"assigned|asked|invited|informed|shown|given|randomi[sz]ed)\b"
    r"|\b(?:Prolific|MTurk|Mechanical Turk|z-?Tree|oTree|ORSEE|hroot|Qualtrics)\b", re.I)
_EMPIRICAL = re.compile(r"\b(?:data(?:set)?s?|sample|survey|experiment|regression|observations|administrative records|"
                        r"participants)\b", re.I)

_OUTSIDE = re.compile(r"separate (?:pdf|page|file|document)|upload|submission (?:form|system|interface|process)|online "
                      r"submission|readme|replication package|cover letter|disclosure form|after (?:conditional )?acceptance|"
                      r"before acceptance|prior to acceptance|on conditional acceptance|after the data editor|due before", re.I)
_NOT_INSIDE = re.compile(r"not in the (?:submitted )?manuscript|need not contain|do(?:es)? not ask for an? [^.]{0,60}in the "
                         r"manuscript|omit [^.]{0,60}from the manuscript", re.I)
_INSIDE = re.compile(r"in the manuscript|in the paper|declarations section|under (?:a|the|this|its own) (?:\"[^\"]+\" )?"
                     r"heading|at the (?:back|end) of the (?:manuscript|article|text)|before the reference|footnote|first page|"
                     r"methods section|statement in the manuscript|title page", re.I)

_STATEMENT_RULES = [
    # (rule key or other name, label, pattern, applies-to test)
    ("disclosure_statement", "disclosure or competing-interest statement", _DISCLOSURE, None),
    ("data_availability_statement", "data availability statement", _DATA, "empirical"),
    ("ethics_approval", "ethics approval statement", _ETHICS, "human"),
    ("other.funding_statement", "funding statement", _FUNDING, None),
    ("other.declarations_section", "Declarations section", re.compile(r"\bdeclarations\b", re.I), None),
    ("other.statements_and_declarations", "\"Statements and Declarations\" section",
     re.compile(r"statements and declarations|competing interests?|conflicts? of interests?", re.I), None),
    ("other.back_matter_statements", "funding and competing-interest declarations",
     re.compile(r"competing interests?|conflicts? of interests?", re.I), None),
]


def _rule_by_name(ctx, key: str):
    return venue_other(ctx, key.split(".", 1)[1]) if key.startswith("other.") else venue_rule(ctx, key)


def _required(r) -> Optional[bool]:
    """True, False, or None when the profile does not know (an unconfirmed rule without a value)."""
    v = (r or {}).get("value")
    if v is None:
        return None
    if isinstance(v, dict) and "required" in v:
        return v.get("required")
    return True


def _detail(r) -> str:
    v = (r or {}).get("value")
    if isinstance(v, dict):
        return " ".join(str(v.get(k) or "") for k in ("detail", "heading", "summary"))
    return str(v or "")


def statement_location(ctx, r) -> str:
    """'inside', 'outside' or 'unknown': where the profile says the statement goes.

    The profile's detail is free text, so the first place cue wins. Under double-anonymous
    review, anything bound for the title page or acknowledgment footnote leaves the manuscript."""
    text = _detail(r)
    double = review_type(ctx)[0] == "double_anonymous"
    if double and re.search(r"title page|acknowledg\w*\)? footnote|omit [^.]{0,60}from the manuscript", text, re.I):
        return "outside"
    if _NOT_INSIDE.search(text):
        return "outside"
    cues = [(m.start(), "outside") for m in _OUTSIDE.finditer(text)] + [(m.start(), "inside") for m in _INSIDE.finditer(text)]
    return min(cues)[1] if cues else "unknown"


def _statement_hits(pm, pattern) -> list:
    hits = []
    for b in pm.blocks:
        if b.kind in ("reference", "table", "equation") or is_hidden(b) or not b.text:
            continue
        m = pattern.search(b.text)
        if m:
            hits.append((b, m))
    return hits


_SECTION_RULES = ("other.declarations_section", "other.statements_and_declarations", "other.back_matter_statements")
# statements that a declarations-type section is meant to hold, recognized in the section rule's detail
_FOLDS = {"disclosure_statement": r"competing|conflicts? of interest",
          "other.funding_statement": r"\bfunding\b|financial support",
          "ethics_approval": r"\bethic",
          "data_availability_statement": r"\bdata\b"}


@register("FMT-03")
def required_statements(pm, ctx):
    if not ctx.venue:
        ctx.skip("FMT-03", "no venue profile given; required statements depend on the journal (pc.py ingest PAPER "
                           "--venue ID)")
        return
    vname = venue_name(ctx)
    steps = venue_steps(ctx)
    text_all = " ".join(b.text for b in prose(pm, PROSE_KINDS))
    human = bool(_HUMAN.search(text_all))
    empirical = bool(_EMPIRICAL.search(text_all))
    found, outside, results = [], [], []
    for key, label, pattern, applies in _STATEMENT_RULES:
        r = _rule_by_name(ctx, key)
        if not r or not _required(r):
            continue
        if applies == "human" and not human:
            found.append(f"{label}: not needed, no human-subjects research detected")
            continue
        if applies == "empirical" and not empirical:
            continue
        results.append((key, label, pattern, r, statement_location(ctx, r), _statement_hits(pm, pattern)))
    if not results and not found:
        ctx.skip("FMT-03", f"the {vname} profile records no required statements")
        return
    # A missing declarations-type section absorbs the statements it is meant to hold: one finding, not several.
    folded = {}
    for key, label, pattern, r, where, hits in results:
        if key in _SECTION_RULES and where == "inside" and not hits:
            for k2, pat in _FOLDS.items():
                if re.search(pat, _detail(r), re.I):
                    folded.setdefault(k2, key)
    for key, label, pattern, r, where, hits in results:
        if where == "outside":
            outside.append((key, label, r))
            continue
        if hits:
            b, m = hits[0]
            found.append(f"{label} at {b.anchor.label()}")
            if key not in folded:
                continue
        if key in folded:
            continue
        if where == "unknown":
            outside.append((key, label, r))
            continue
        holds = [(lab, h) for k2, lab, _, _, _, h in results if folded.get(k2) == key]
        add = [lab for lab, h in holds if not h]
        move = [f"{lab} (now at {h[0][0].anchor.label()})" for lab, h in holds if h]
        extra = ((f" It should hold: {', '.join(add)}." if add else "")
                 + (f" Move into it: {', '.join(move)}." if move else ""))
        yield add_location(ctx.finding(
            "FMT-03", f"Missing {label}", "major",
            f"{vname} asks for a {label} in the manuscript ({compact(_detail(r), 220)}), and none was found.{extra}"
            + rule_caveat(r), status=rule_status(r), confidence="medium",
            evidence=[rule_evidence(ctx, key, r),
                      Evidence(type="checked_absence", text=label,
                               data={"scope": "every text block, headings included",
                                     "terms": {pattern.pattern[:120]: 0}})],
            trajectory=steps + [f"The profile places the {label} inside the manuscript.",
                                f"Searched every block for the {label}: no match."]
            + ([f"Folded into this finding: {', '.join(lab for lab, _ in holds)}."] if holds else []),
            fix=Fix(action="insert", detail=f"Add the {label} where {vname} asks for it: {compact(_detail(r), 200)}",
                    resolved_when=f"The manuscript contains the {label}"
                                  + (" with " + ", ".join(lab for lab, _ in holds) if holds else "") + "."),
            script=SCRIPT, extra={"rule": key, "holds": [lab for lab, _ in holds]}), doc_anchor(pm))
    if outside:
        listing = "; ".join(f"{label} ({compact(_detail(r), 160)})" for _, label, r in outside)
        unconfirmed = [label for _, label, r in outside if not rule_confirmed(r)]
        yield add_location(ctx.finding(
            "FMT-03", "Required statements that go outside the manuscript", "suggestion",
            f"{vname} asks for items that are submitted outside the manuscript or after acceptance, or does not say "
            f"where they go, so this check cannot see them: {listing}."
            + (f" Unconfirmed rules: {', '.join(unconfirmed)}." if unconfirmed else "")
            + " Missing items can make a submission incomplete.",
            status="needs_human", confidence="high",
            evidence=[rule_evidence(ctx, key, r) for key, _, r in outside],
            trajectory=steps + ["Read where the profile places each required statement: outside the manuscript, or "
                                "not stated."],
            fix=Fix(action="investigate", detail="Prepare each item for the submission system or the replication "
                                                 "package, as the profile describes.",
                    resolved_when="Each item is ready to upload or is in the replication package."),
            script=SCRIPT, extra={"items": [key for key, _, _ in outside]}), doc_anchor(pm))
    bits = []
    if found:
        bits.append("found: " + "; ".join(found))
    if outside:
        bits.append(f"{len(outside)} required item(s) go outside the manuscript or have no stated place, listed as "
                    "a reminder")
    note_coverage(ctx, "FMT-03", "; ".join(bits) or "no statement is required inside the manuscript")


# =============================================================== BEH-06 registration
_PREREG_CLAIM = re.compile(
    r"\b(?:was|were|is|are|been|being)\s+(?:pre-?registered|registered\s+(?:at|with|in|on|before|prior))"
    r"|\b(?:we|I)\s+(?:have\s+)?(?:pre-?registered|registered\s+(?:the|our|this|it|at|with|in|on))"
    r"|\bour\s+pre-?registration\b|\bthe\s+pre-?registration\s+(?:of\s+(?:this|the|our)|is|was|for)"
    r"|\bpre-?registered\s+(?:experiment|study|trial|analysis|analyses|hypothes[ie]s|design|outcomes?|plan|"
    r"specification|sample|prediction)"
    r"|\b(?:our|the)\s+pre-?analysis\s+plan\b", re.I)
_NEGATION = re.compile(r"\b(?:not|never|no|without|nor)\b|n['’]t\b", re.I)
_REG_ID = re.compile(
    r"AEARCTR-?\s?\d{4,}|socialscienceregistry\.org/trials/\d+|aspredicted\.org/\S+|AsPredicted\s*(?:#|no\.?|number)?\s*"
    r"\(?#?\s?\d{3,}|osf\.io/\w+|10\.17605/OSF\.IO/\w+|\bNCT\d{8}\b|\bISRCTN\d+|\bDRKS\d+|\bEGAP\s*(?:ID\s*)?\d{8}\w*|"
    r"RIDIE-STUDY-ID-\w+|\bAEA RCT Registry\b[^.]{0,60}\d{4,}", re.I)
_FIELD_RCT = re.compile(r"\bfield experiments?\b|\brandomi[sz]ed controlled trials?\b|\bRCTs?\b|\bnatural field experiment",
                        re.I)
_LAB = re.compile(r"\blab(?:oratory)? experiments?\b|\bexperimental (?:lab|laboratory)\b|\bz-?Tree\b|\bORSEE\b", re.I)
_OWN_FIELD = re.compile(r"\b(?:we|our|this paper|this study|this article)\b[^.]{0,100}?\b(?:field experiments?|"
                        r"randomi[sz]ed controlled trials?|RCTs?|natural field experiments?)\b", re.I)
_OSF_ONLY = re.compile(r"osf\.io|aspredicted|10\.17605/OSF", re.I)


@register("BEH-06")
def registration(pm, ctx):
    steps = venue_steps(ctx) + ["Searched every block, footnotes and references included, for registry IDs "
                                "(AEARCTR, AsPredicted, OSF, ClinicalTrials.gov, ISRCTN, EGAP, RIDIE, DRKS), and the "
                                "text for statements that the study was registered."]
    ids = []
    for b in pm.blocks:
        for m in _REG_ID.finditer(b.text or ""):
            ids.append((b, m))
    for r_ in pm.references:
        for m in _REG_ID.finditer(r_.raw or ""):
            ids.append((None, m))
    claims = []
    for b in prose(pm, PROSE_KINDS + ("acknowledgment",)):
        for m in _PREREG_CLAIM.finditer(b.text):
            s0, _ = sentence_bounds(b, m.start())
            lead = b.text[max(s0, m.start() - 40):m.end()]
            if _NEGATION.search(lead):
                continue
            claims.append((b, m))
    trial = venue_rule(ctx, "trial_registration")
    aea = bool(trial) and re.search(r"AEA RCT Registry", compact(trial.get("value"), 600), re.I)
    text_all = " ".join(b.text for b in prose(pm))
    study_type = str(setting(ctx, "study_type") or "").lower()
    field = ("field" in study_type or "rct" in study_type) or (bool(_OWN_FIELD.search(text_all)) and "lab" not in study_type)
    evidence_rules = [rule_evidence(ctx, "trial_registration", trial)] if trial else []

    if claims and not ids:
        b, m = claims[0]
        quote = sentence_quote(b, m.start(), 30)
        aea_text = (f" {venue_name(ctx)} requires field experiments to be registered in the AEA RCT Registry, with "
                    "the AEARCTR ID cited in the title footnote and the registration in the reference list."
                    + rule_caveat(trial) if aea and field else "")
        yield ctx.finding(
            "BEH-06", "Registration claimed without a registry ID", "major",
            f"The paper says the study was registered (\"{m.group(0)}\") but gives no registry or registration ID "
            "anywhere, so readers cannot compare the analysis with the plan." + aea_text,
            block=b, quote=quote, status="confirmed",
            related=[related(b2, sentence_quote(b2, m2.start(), 30)) for b2, m2 in claims[1:5]],
            evidence=[Evidence(type="quote", text=quote, block=b.id),
                      Evidence(type="checked_absence", text="registry IDs",
                               data={"scope": "all blocks and references",
                                     "terms": {"AEARCTR-#": 0, "AsPredicted #": 0, "osf.io/": 0, "NCT#": 0,
                                               "ISRCTN#": 0, "EGAP": 0, "RIDIE": 0}})] + evidence_rules,
            trajectory=steps + [f"Found {len(claims)} registration statement(s); found no registry ID."],
            fix=Fix(action="insert",
                    detail=("Give the registry and ID, e.g. 'registered in the AEA RCT Registry as AEARCTR-0001234', "
                            "in the title footnote, and cite the registration in the references."
                            if aea or not trial else "Name the registry and give the registration ID or link."),
                    resolved_when="The registry name and the registration ID or URL appear in the paper"
                                  + (" and the registration is in the reference list" if aea else "") + "."),
            script=SCRIPT, extra={"claim": m.group(0)})
        return
    if aea and field and not claims and not ids and not _LAB.search(text_all):
        target = next((b for b in prose(pm) if _OWN_FIELD.search(b.text)), None)
        m = _OWN_FIELD.search(target.text) if target else None
        quote = sentence_quote(target, m.start(), 30) if target else None
        yield ctx.finding(
            "BEH-06", "Field experiment without an AEA RCT Registry entry", "major",
            f"The paper reports a field experiment, and {venue_name(ctx)} requires field experiments to be registered "
            "in the AEA RCT Registry and the registration cited (title footnote and references). The paper mentions no "
            "registration and gives no AEARCTR ID." + rule_caveat(trial),
            block=target, quote=quote, status="likely", confidence="medium",
            evidence=([Evidence(type="quote", text=quote, block=target.id)] if target else [])
            + [Evidence(type="checked_absence", text="registration", data={"scope": "all blocks and references",
                                                                          "terms": {"AEARCTR": 0, "registered": 0}})]
            + evidence_rules,
            trajectory=steps + ["Detected a field experiment; found no registration statement or ID."],
            fix=Fix(action="insert", detail="Cite the AEA RCT Registry entry (AEARCTR-...) in the title footnote and "
                                            "the references; under anonymized review cite it in the third person.",
                    resolved_when="The AEARCTR ID appears in the paper and the registration is in the references."),
            script=SCRIPT)
        return
    if aea and field and ids and all(_OSF_ONLY.search(m.group(0)) for _, m in ids):
        b, m = next(((b, m) for b, m in ids if b is not None), (None, ids[0][1]))
        quote = quote_at(b, m.start(), m.end(), 4, 2) if b is not None else None
        f = ctx.finding(
            "BEH-06", "Registered only on OSF or AsPredicted", "minor",
            f"The study is registered at {m.group(0)}, not in the AEA RCT Registry. {venue_name(ctx)} requires field "
            "experiments to be in the AEA registry, and the AEA Data Editor's template flags registration only "
            "elsewhere." + rule_caveat(trial),
            block=b, quote=quote, status="likely", confidence="medium",
            evidence=([Evidence(type="quote", text=quote, block=b.id)] if b is not None else []) + evidence_rules,
            trajectory=steps + ["Every registry ID found is an OSF or AsPredicted one."],
            fix=Fix(action="investigate", detail="Register the trial in the AEA RCT Registry as well and cite it.",
                    resolved_when="An AEARCTR ID is cited in the paper."),
            script=SCRIPT)
        if b is None:
            add_location(f, doc_anchor(pm))
        yield f


# =============================================================== BEH-12 ethics approval placement
_APPROVAL_NUMBER = re.compile(r"(?:protocol|approval|reference|ref\.|number|no\.|#|ID|IRB)\s*(?:no\.?|number|#|:)?\s*"
                              r"[A-Z]{0,8}[-/ ]?\d[\w/.-]{2,}|\b\d{2,4}-\d{2,}\b|#\s?\d{3,}", re.I)
_BOARD_NAME = re.compile(r"\b(?:of|at|from)\s+(?:the\s+)?[A-Z][\w&.'’-]+|[A-Z][\w&.'’-]+\s+(?:University|College|"
                         r"Institute)|\b[A-Z]{2,}\b\s+(?:IRB|[Ee]thics)")


def _ethics_place(ctx, r) -> str:
    """outside, title footnote, declarations, manuscript or unknown."""
    text = _detail(r)
    where = statement_location(ctx, r)
    if where == "outside":
        return "outside"
    if re.search(r"title (?:\(acknowledg\w*\) )?footnote|acknowledg\w* footnote", text, re.I):
        return "title footnote"
    if re.search(r"declarations section", text, re.I):
        return "declarations"
    if where == "inside" or re.search(r"give the name of the approving", text, re.I):
        return "manuscript"
    return "unknown"


@register("BEH-12")
def ethics_placement(pm, ctx):
    if not ctx.venue:
        ctx.skip("BEH-12", "no venue profile given; where the ethics statement goes depends on the journal")
        return
    r = venue_rule(ctx, "ethics_approval")
    if not r or not _required(r):
        ctx.skip("BEH-12", f"the {venue_name(ctx)} profile does not require an ethics statement")
        return
    text_all = " ".join(b.text for b in prose(pm, PROSE_KINDS))
    if not _HUMAN.search(text_all):
        note_coverage(ctx, "BEH-12", "no human-subjects research detected")
        return
    place = _ethics_place(ctx, r)
    hits = _statement_hits(pm, _ETHICS)
    steps = venue_steps(ctx) + [f"The profile places the ethics statement: {place} ({compact(_detail(r), 200)}).",
                                f"Found {len(hits)} block(s) mentioning ethics approval."]
    vname = venue_name(ctx)
    if place == "outside":
        where = ", ".join(b.anchor.label() for b, _ in hits) or "none in the manuscript"
        note_coverage(ctx, "BEH-12", f"{vname} takes the ethics statement outside the manuscript; statement found: "
                                     f"{where}" + ("; its presence in an anonymized manuscript is reported under FMT-02"
                                                   if hits else ""))
        return
    if not hits:
        yield add_location(ctx.finding(
            "BEH-12", "No ethics approval statement", "major",
            f"The paper reports research with human participants, and {vname} asks for an ethics approval statement "
            f"({compact(_detail(r), 220)}). None was found." + rule_caveat(r),
            status=rule_status(r), confidence="medium",
            evidence=[rule_evidence(ctx, "ethics_approval", r),
                      Evidence(type="checked_absence", text="ethics approval",
                               data={"scope": "all text blocks", "terms": {"IRB|ethics committee|approved by": 0}})],
            trajectory=steps,
            fix=Fix(action="insert", detail="State the approving board, the approval number and date, and the consent "
                                            "obtained, where the journal asks for it.",
                    resolved_when="The manuscript names the approving board and gives the approval number."),
            script=SCRIPT), doc_anchor(pm))
        return
    b, m = hits[0]
    s0, e0 = sentence_bounds(b, m.start())
    sentence = b.text[s0:e0]
    quote = sentence_quote(b, m.start(), 40)
    missing = []
    if not _APPROVAL_NUMBER.search(b.text):
        missing.append("the approval or protocol number")
    if not _BOARD_NAME.search(sentence) and not re.search(r"University|College|Institute|Committee of", b.text):
        missing.append("the name of the approving board")
    misplaced = None
    title_note = b.kind == "acknowledgment" or (b.kind == "footnote" and (b.attrs or {}).get("number") in ("*", "1")
                                                 and pm.block(b.parent or "") is not None
                                                 and pm.block(b.parent).kind in ("title", "author"))
    if place == "title footnote" and not title_note:
        misplaced = "the title footnote"
    elif place == "declarations" and not any(re.search(r"declarations", s, re.I) for s in b.section or []):
        misplaced = "the Declarations section before the references"
    if missing or misplaced:
        problem = (f"The ethics statement " + (f"is not in {misplaced}, where {vname} wants it" if misplaced else "")
                   + (" and " if misplaced and missing else "") + (f"does not give {' or '.join(missing)}"
                                                                   if missing else "") + f". {vname}: "
                   f"{compact(_detail(r), 220)}" + rule_caveat(r))
        yield ctx.finding(
            "BEH-12", "Ethics statement incomplete or misplaced", "major" if misplaced else "minor",
            problem, block=b, quote=quote, status=rule_status(r), confidence="medium",
            evidence=[Evidence(type="quote", text=quote, block=b.id), rule_evidence(ctx, "ethics_approval", r)],
            trajectory=steps + [f"Checked the statement at {b.anchor.label()} for a board name and an approval number"
                                + (f", and its place against: {place}" if place != "unknown" else "") + "."],
            fix=Fix(action="investigate", detail=("Move the statement to " + misplaced + ". " if misplaced else "")
                    + ("Add " + " and ".join(missing) + "." if missing else ""),
                    resolved_when="The ethics statement names the board, gives the approval number, and sits where the "
                                  "journal asks."),
            script=SCRIPT)
    else:
        note_coverage(ctx, "BEH-12", f"ethics statement found at {b.anchor.label()} with a board name and an approval "
                                     "number")


# =============================================================== BEH-16 JEL codes, keywords, highlights
_JEL_CODE = re.compile(r"\b[A-Z]\d{1,2}\b")


def _front_items(block) -> list:
    text = re.sub(r"^\s*(?:JEL(?:\s+(?:codes?|classification(?:s)?))?|Keywords?|Key\s+words)\s*[:.—–-]*\s*", "",
                  block.text.strip(), flags=re.I)
    return [p.strip(" .") for p in re.split(r"[;,·•]|\s{2,}", text) if p.strip(" .")]


def _highlights(pm) -> list:
    items, on = [], False
    for b in pm.blocks:
        if b.kind == "heading":
            on = bool(re.match(r"\s*(?:\d+\s+)?highlights\b", b.text, re.I))
            continue
        if on and b.kind == "list_item":
            items.append(b)
        elif on and b.kind == "paragraph" and items:
            on = False
    if not items:
        for b in pm.blocks:
            if b.kind == "list_item" and (b.attrs or {}).get("env") == "highlights":
                items.append(b)
    return items


@register("BEH-16")
def journal_requirements(pm, ctx):
    if not ctx.venue:
        ctx.skip("BEH-16", "no venue profile given; JEL codes, keywords and highlights are checked against a profile")
        return
    vname = venue_name(ctx)
    steps = venue_steps(ctx)
    compared, any_rule = [], False
    for key, label, kind in (("jel_codes", "JEL codes", "jel"), ("keywords", "keywords", "keywords")):
        r = venue_rule(ctx, key)
        if not r or not isinstance(r.get("value"), dict):
            continue
        any_rule = True
        v = r["value"]
        blocks = [b for b in pm.blocks if b.kind == kind]
        if not blocks:
            if v.get("required"):
                yield add_location(ctx.finding(
                    "BEH-16", f"No {label}", "major",
                    f"{vname} asks for {label}" + (f" ({v.get('min')} to {v.get('max')})" if v.get("min") or v.get("max")
                                                   else "") + ", and none were found in the manuscript. If the journal "
                    "collects them only in the submission form, enter them there." + rule_caveat(r),
                    status="likely", confidence="medium",
                    evidence=[rule_evidence(ctx, key, r),
                              Evidence(type="checked_absence", text=label,
                                       data={"scope": "front matter", "terms": {f"{label} line": 0}})],
                    trajectory=steps + [f"Looked for a {label} line after the abstract: none."],
                    fix=Fix(action="insert", detail=f"Add a line '{label.capitalize()}: ...' after the abstract.",
                            resolved_when=f"The manuscript lists its {label}."),
                    script=SCRIPT, extra={"rule": key}), doc_anchor(pm))
            continue
        b = blocks[0]
        items = _front_items(b)
        if kind == "jel":
            body = re.sub(r"\([^)]*\)", " ", re.sub(r"^\s*JEL[^:]*:\s*", "", b.text, flags=re.I))
            items = [t for t in re.split(r"[;,\s·•]+", body) if t and t.lower() not in ("and", "&")]
        codes = _JEL_CODE.findall(b.text) if kind == "jel" else items
        n = len(codes)
        compared.append(f"{label}: {n}")
        lo, hi = v.get("min"), v.get("max")
        problems = []
        if lo and n < int(lo):
            problems.append(f"{n} given, at least {lo} required")
        if hi and n > int(hi):
            problems.append(f"{n} given, at most {hi} allowed")
        if kind == "jel":
            bad = [i for i in items if not _JEL_CODE.fullmatch(i.strip())]
            if bad and len(bad) <= len(items):
                problems.append("not in JEL format (a letter and one or two digits, e.g. D91): " + ", ".join(bad[:5]))
        if problems:
            yield ctx.finding(
                "BEH-16", f"{label.capitalize()} do not meet the journal's rule", "major",
                f"{label.capitalize()}: {'; '.join(problems)}. {vname}: {compact(v, 120)}." + rule_caveat(r),
                block=b, quote=block_quote(b, 30), status=rule_status(r),
                evidence=[Evidence(type="quote", text=block_quote(b, 30), block=b.id), rule_evidence(ctx, key, r)],
                trajectory=steps + [f"Counted {label}: {n}."],
                fix=Fix(action="investigate", detail=f"Give {label} as the journal asks.",
                        resolved_when=f"The {label} meet {vname}'s rule."),
                script=SCRIPT, extra={"rule": key, "count": n})
    r = venue_rule(ctx, "highlights")
    o = venue_other(ctx, "highlights_format")
    if r and isinstance(r.get("value"), dict):
        any_rule = True
        v = dict(r["value"])
        if o and isinstance(o.get("value"), dict):
            v = {**o["value"], **{k: x for k, x in v.items() if x is not None}}
        items = _highlights(pm)
        if not items:
            if v.get("required"):
                yield add_location(ctx.finding(
                    "BEH-16", "No highlights found", "minor",
                    f"{vname} asks for {v.get('count_min', 3)} to {v.get('count_max', 5)} highlights of at most "
                    f"{v.get('max_chars_each', 85)} characters each. None are in the manuscript; Elsevier journals "
                    "usually collect them as a separate file, so make sure you upload them." + rule_caveat(r),
                    status="needs_human", confidence="medium",
                    evidence=[rule_evidence(ctx, "highlights", r)],
                    trajectory=steps + ["Looked for a Highlights heading or environment: none."],
                    fix=Fix(action="investigate", detail="Prepare the highlights file.",
                            resolved_when="The highlights are ready to upload and meet the count and length limits."),
                    script=SCRIPT), doc_anchor(pm))
        else:
            compared.append(f"highlights: {len(items)}")
            problems = []
            if v.get("count_min") and len(items) < int(v["count_min"]):
                problems.append(f"{len(items)} highlights, at least {v['count_min']} required")
            if v.get("count_max") and len(items) > int(v["count_max"]):
                problems.append(f"{len(items)} highlights, at most {v['count_max']} allowed")
            long_ones = [b for b in items if v.get("max_chars_each") and len(b.text.strip()) > int(v["max_chars_each"])]
            if long_ones:
                problems.append(f"{len(long_ones)} longer than {v['max_chars_each']} characters")
            if problems:
                b = long_ones[0] if long_ones else items[0]
                yield ctx.finding(
                    "BEH-16", "Highlights do not meet the journal's rule", "major",
                    f"Highlights: {'; '.join(problems)}." + rule_caveat(r),
                    block=b, quote=block_quote(b, 30), status=rule_status(r),
                    evidence=[Evidence(type="computed_result", text="highlights",
                                       data={"formula": "count and characters per highlight",
                                             "output": [len(x.text.strip()) for x in items]}),
                              rule_evidence(ctx, "highlights", r)],
                    trajectory=steps + ["Counted the highlights and their characters, spaces included."],
                    fix=Fix(action="investigate", detail="Shorten or merge highlights.",
                            resolved_when="The highlights meet the count and length limits."),
                    script=SCRIPT)
    if not any_rule:
        note_coverage(ctx, "BEH-16", f"the {vname} profile asks for no JEL codes, keywords or highlights; disclosure "
                                     "statements are checked under FMT-03")
        return
    note_coverage(ctx, "BEH-16", ("compared " + ", ".join(compared) + "; " if compared else "")
                  + "disclosure statements are checked under FMT-03")
