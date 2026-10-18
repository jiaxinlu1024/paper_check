"""Reference checks that need no network (CIT-01, CIT-10, FMT-08) and software citations (BEH-11).

CIT-01  citations without a reference entry; entries never cited. With BibTeX only
        cited entries are printed, so only missing keys are reported; with a
        hand-made list (thebibliography, PDF, Word) both directions are.
CIT-10  an informational summary of reference ages.
FMT-08  reference list consistency: duplicate keys and entries, required fields,
        acronyms that BibTeX may lowercase, venue name variants, DOI format,
        author name format, title capitalization style.
BEH-11  oTree, z-Tree, ORSEE and hroot used without citing Chen, Schonger and Wickens
        (2016), Fischbacher (2007), Greiner (2015) and Bock, Baetge and Nicklisch (2014).
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from collections import Counter, defaultdict
from typing import Optional

from ..model import Anchor, Evidence, Fix
from ..textutil import find_quote, normalize
from . import register
from .format import (PROSE_KINDS, add_location, block_quote, doc_anchor, input_format, note_coverage, prose, related,
                     sentence_quote)

SCRIPT = "checks/references_local.py"


def _ref_block(pm, ref):
    return next((b for b in pm.blocks if b.kind == "reference" and (b.attrs.get("ref") == ref.id
                                                                     or (ref.key and b.attrs.get("key") == ref.key))), None)


def _ref_quote(pm, ref, text: Optional[str] = None) -> tuple:
    """(block, quote) for a reference: `text` if it appears in the reference's block, else the block's start."""
    b = _ref_block(pm, ref)
    if b is None:
        return None, None
    if text:
        span = find_quote(text, b.text)
        if span:
            return b, b.text[span[0]:span[1]]
    return b, block_quote(b, 25)


def _ref_anchor(ref) -> Anchor:
    return ref.anchor if ref.anchor else Anchor()


def _citations(pm) -> dict:
    cited = defaultdict(list)
    for b in pm.blocks:
        if b.kind == "reference":
            continue
        for c in b.citations:
            for k in c.keys:
                cited[k].append((b, c))
    return cited


# =============================================================== CIT-01
MAX_UNCITED = 5  # more uncited entries than this are reported in one finding


@register("CIT-01")
def citations_have_entries(pm, ctx):
    md = pm.metadata or {}
    cited = _citations(pm)
    bibtex = md.get("bib_mode") == "bibtex" or any(r.source == "bibtex" for r in pm.references)
    if not cited and not md.get("cited_keys_missing_from_bib"):
        if pm.references:
            ctx.skip("CIT-01", "no in-text citations were recognized, so citations cannot be matched to the "
                               f"{len(pm.references)} references")
        else:
            ctx.skip("CIT-01", "the paper map has no in-text citations and no reference list")
        return
    ref_keys = {r.key for r in pm.references if r.key} | {r.id for r in pm.references}
    missing = set(md.get("cited_keys_missing_from_bib") or [])
    for k, uses in cited.items():
        if k not in ref_keys and (not bibtex or any(not c.resolved for _, c in uses)):
            missing.add(k)
    missing.discard("*")
    steps = [f"Collected {sum(len(v) for v in cited.values())} citations of {len(cited)} keys and "
             f"{len(pm.references)} reference entries" + (" (BibTeX: only cited entries are printed)" if bibtex else "")
             + "."]
    for k in sorted(missing):
        uses = cited.get(k, [])
        bib = ", ".join(f if f.endswith(".bib") else f + ".bib" for f in md.get("bib_files") or []) or "the reference list"
        if uses:
            b, c = uses[0]
            quote = sentence_quote(b, c.start, 35)
            where = f" It is cited {len(uses)} times." if len(uses) > 1 else ""
            f = ctx.finding(
                "CIT-01", "Citation without a reference entry", "major",
                (f"The citation key \"{k}\" has no entry in {bib}, so the compiled paper prints a question mark "
                 "instead of the citation and the work is missing from the reference list." if bibtex else
                 f"The citation \"{b.text[c.start:c.end]}\" matches no entry in the reference list.") + where,
                block=b, quote=quote, status="confirmed",
                related=[related(b2, sentence_quote(b2, c2.start, 35)) for b2, c2 in uses[1:6]],
                evidence=[Evidence(type="quote", text=quote, block=b.id),
                          Evidence(type="checked_absence", text=k,
                                   data={"scope": f"entries of {bib}", "terms": {k: 0},
                                         "entries": len(pm.references)})],
                trajectory=steps + [f"\"{k}\" is cited at {b.anchor.label()} and matches no entry."],
                fix=Fix(action="insert", detail=f"Add the entry for \"{k}\" to {bib}, or correct the key in the citation.",
                        resolved_when=f"\"{k}\" resolves and the work appears in the reference list."),
                script=SCRIPT, extra={"key": k, "uses": len(uses)})
        else:
            f = ctx.finding(
                "CIT-01", "Citation without a reference entry", "major",
                f"The key \"{k}\" is cited (for example with \\nocite) but has no entry in {bib}.", status="confirmed",
                evidence=[Evidence(type="checked_absence", text=k, data={"scope": bib, "terms": {k: 0}})],
                trajectory=steps,
                fix=Fix(action="insert", detail=f"Add the entry for \"{k}\" or remove the citation.",
                        resolved_when=f"\"{k}\" resolves."),
                script=SCRIPT, extra={"key": k})
            add_location(f, doc_anchor(pm))
        yield f
    if bibtex:
        n_unc = md.get("uncited_bib_entries")
        note_coverage(ctx, "CIT-01", f"{len(missing)} cited key(s) without an entry; "
                                     + (f"{n_unc} uncited .bib entr{'y is' if n_unc == 1 else 'ies are'} not printed by "
                                        "BibTeX, so not reported" if n_unc else "BibTeX prints only cited entries"))
        return
    cited_ids = set(cited)
    if isinstance(md.get("uncited_references"), list):
        listed = set(md["uncited_references"])  # the reader matched citations to entries itself
        uncited = [r for r in pm.references if r.id in listed and (not r.key or r.key not in cited_ids)]
    else:
        uncited = [r for r in pm.references if r.id not in cited_ids and (not r.key or r.key not in cited_ids)]
    status = "confirmed" if input_format(pm) == "latex" else "likely"
    if len(uncited) > MAX_UNCITED:
        # many at once: report them together; from a PDF or Word file this many usually means some citation
        # formats were not recognized, so a person should check
        share = len(uncited) / max(1, len(pm.references))
        status = status if status == "confirmed" or share <= 0.5 else "needs_human"
        located = [(r, *_ref_quote(pm, r)) for r in uncited]
        first = next(((r, b, q) for r, b, q in located if b is not None), (uncited[0], None, None))
        names = ", ".join(r.key or r.id for r in uncited)
        f = ctx.finding(
            "CIT-01", f"{len(uncited)} references never cited", "minor",
            f"{len(uncited)} of {len(pm.references)} entries of the reference list match no in-text citation: "
            f"{names[:400]}{'...' if len(names) > 400 else ''}."
            + ("" if status == "confirmed" else
               " So many unmatched entries can also mean that some citations were not recognized in the text, so "
               "check a few by hand before deleting anything." if status == "needs_human" else
               " (as far as the in-text citations could be matched)"),
            block=first[1], quote=first[2], status=status,
            confidence="high" if status == "confirmed" else "medium" if status == "likely" else "low",
            related=[related(b, q) for _, b, q in located if b is not None and b is not first[1]][:6],
            evidence=[Evidence(type="checked_absence", text=names[:300],
                               data={"scope": "every in-text citation", "terms": {r.key or r.id: 0 for r in uncited}})],
            trajectory=steps + [f"No citation points to {len(uncited)} entries."],
            fix=Fix(action="investigate", detail="Cite each work where it is used, or delete its entry.",
                    resolved_when="Every entry in the reference list is cited at least once."),
            script=SCRIPT, extra={"keys": [r.key or r.id for r in uncited]})
        if first[1] is None:
            add_location(f, _ref_anchor(first[0]))
        yield f
        return
    for r in uncited:
        b, quote = _ref_quote(pm, r)
        f = ctx.finding(
            "CIT-01", "Reference never cited", "minor",
            f"This entry of the reference list is never cited in the text"
            + ("" if status == "confirmed" else " (as far as the in-text citations could be matched)") + ".",
            block=b, quote=quote, status=status, confidence="high" if status == "confirmed" else "medium",
            evidence=[Evidence(type="checked_absence", text=r.key or r.id,
                               data={"scope": "every in-text citation", "terms": {r.key or r.id: 0}})],
            trajectory=steps + [f"No citation points to {r.key or r.id}."],
            fix=Fix(action="investigate", detail="Cite the work where it is used, or delete the entry.",
                    resolved_when="Every entry in the reference list is cited at least once."),
            script=SCRIPT, extra={"key": r.key, "ref": r.id})
        if b is None:
            add_location(f, _ref_anchor(r))
        yield f


# =============================================================== CIT-10
def _paper_year(pm) -> int:
    for b in pm.blocks[:15]:
        if b.kind in ("front_matter", "title", "author", "acknowledgment"):
            m = re.search(r"\b(19[89]\d|20\d\d)\b", b.text)
            if m and b.kind == "front_matter":
                return int(m.group(1))
    return dt.date.today().year


@register("CIT-10")
def reference_ages(pm, ctx):
    years = []
    for r in pm.references:
        y = str((r.fields or {}).get("year") or "")
        m = re.match(r"(1[5-9]\d\d|20\d\d)", y) or re.search(r"\b(1[5-9]\d\d|20\d\d)\b", r.raw or "")
        if m:
            years.append((int(m.group(1)), r))
    if len(years) < 3:
        ctx.skip("CIT-10", f"only {len(years)} references with a year; too few to summarize")
        return
    now = _paper_year(pm)
    ys = sorted(y for y, _ in years)
    ages = [now - y for y in ys]
    med = statistics.median(ys)
    last5 = sum(1 for y in ys if now - y <= 5)
    last10 = sum(1 for y in ys if now - y <= 10)
    older30 = sum(1 for y in ys if now - y > 30)
    newest = max(years, key=lambda x: x[0])
    summary = (f"{len(ys)} references with a year, from {ys[0]} to {ys[-1]}; median year {med:g} "
               f"({now - med:g} years before {now}). {last5} ({100 * last5 / len(ys):.0f}%) "
               f"{'is' if last5 == 1 else 'are'} from the last 5 years, {last10} ({100 * last10 / len(ys):.0f}%) from the "
               f"last 10, and {older30} {'is' if older30 == 1 else 'are'} more than 30 years old.")
    # A summary is information, not a problem: it goes in the coverage note, where CIT-09's searches can use it.
    ctx.note("CIT-10", summary)


# =============================================================== FMT-08 reference list consistency

# Acronyms that titles in economics often contain; a lowercase form in a printed title is suspect.
KNOWN_ACRONYMS = {"OECD", "RCT", "RCTS", "GDP", "IMF", "NBER", "CEPR", "IZA", "SSRN", "USA", "EU", "UK", "US",
                  "IRA", "IRAS", "SAT", "CEO", "CEOS", "ESG", "COVID", "HIV", "AIDS", "NGO", "NGOS", "PISA",
                  "EEG", "FMRI", "MTURK", "BDM", "WTP", "WTA", "CRRA", "CARA", "IV", "OLS", "DID", "RDD",
                  "LATE", "ATE", "CPI", "FDI", "WTO", "UN", "WHO", "ECB", "FED", "ETF", "IPO"}
_REQUIRED = {
    "article": (("author",), ("title",), ("journal", "container"), ("year",)),
    "book": (("author", "editor"), ("title",), ("publisher",), ("year",)),
    "incollection": (("author",), ("title",), ("booktitle", "container"), ("year",)),
    "inproceedings": (("author",), ("title",), ("booktitle", "container"), ("year",)),
    "techreport": (("author",), ("title",), ("institution", "container"), ("year",)),
    "phdthesis": (("author",), ("title",), ("school", "container", "publisher"), ("year",)),
    "unpublished": (("author",), ("title",)),
}
_FIELD_ALIAS = {"author": "authors", "journal": "container", "booktitle": "container", "institution": "container",
                "school": "container", "editor": "authors"}
_ACRONYM = re.compile(r"^(?=[^a-z]*[A-Z][^a-z]*[A-Z])[A-Z0-9&-]{2,}s?$|^[A-Z]?[a-z]+[A-Z][A-Za-z]*$")
_JOURNAL_ABBREV = {
    "american economic review": {"aer", "am econ rev", "amer econ rev", "american econ rev", "the american economic review"},
    "quarterly journal of economics": {"qje", "q j econ", "quart j econ", "quarterly j econ"},
    "journal of political economy": {"jpe", "j polit econ", "j political econ", "j pol econ"},
    "review of economic studies": {"restud", "res", "rev econ stud"},
    "review of economics and statistics": {"restat", "rev econ stat"},
    "journal of the european economic association": {"jeea", "j eur econ assoc"},
    "economic journal": {"ej", "econ j"},
    "journal of economic behavior and organization": {"jebo", "j econ behav organ"},
    "experimental economics": {"exp econ", "expecon"},
    "games and economic behavior": {"geb", "games econ behav"},
    "management science": {"mnsc", "manage sci", "manag sci", "management sci"},
    "journal of risk and uncertainty": {"jru", "j risk uncertain", "j risk uncertainty"},
    "journal of economic perspectives": {"jep", "j econ perspect"},
    "journal of economic literature": {"jel", "j econ lit"},
    "journal of public economics": {"jpube", "j public econ", "j pub econ"},
    "journal of behavioral and experimental economics": {"jbee", "j behav exp econ"},
    "journal of economic psychology": {"joep", "j econ psychol"},
    "journal of finance": {"jf", "j finance"},
    "journal of the economic science association": {"jesa", "j econ sci assoc"},
    "proceedings of the national academy of sciences": {"pnas", "proc natl acad sci", "proc natl acad sci usa",
                                                        "proceedings of the national academy of sciences usa",
                                                        "proceedings of the national academy of sciences of the "
                                                        "united states of america"},
}
_STOP = {"of", "the", "and", "for", "in", "on", "a", "an", "&"}


def _norm_venue(name: str) -> str:
    text = normalize(name).lower().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^the ", "", text)


def _canonical_venue(name: str) -> str:
    n = _norm_venue(name)
    for full, abbrevs in _JOURNAL_ABBREV.items():
        if n == full or n in abbrevs:
            return full
    return n


def _initials(name: str) -> str:
    return "".join(w[0] for w in _norm_venue(name).split() if w not in _STOP)


def _unprotected_acronyms(raw_title: str) -> list:
    """Words at brace depth 0 that a sentence-case BibTeX style would lowercase."""
    out, depth, word, word_depth0 = [], 0, "", True
    i = 0
    while i <= len(raw_title):
        ch = raw_title[i] if i < len(raw_title) else " "
        if ch == "\\" and i + 1 < len(raw_title):
            m = re.match(r"\\[A-Za-z]+|\\.", raw_title[i:])
            word += m.group(0)
            word_depth0 = False
            i += len(m.group(0))
            continue
        if ch == "{":
            depth += 1
            word_depth0 = False if word else word_depth0
        elif ch == "}":
            depth = max(0, depth - 1)
        if ch in " {}:;,.!?()\"'/" or i == len(raw_title):
            token = word.strip("-")
            if token and word_depth0 and depth == 0 and _ACRONYM.match(token) and not token.isdigit():
                out.append(token)
            word, word_depth0 = "", depth == 0
        else:
            if not word:
                word_depth0 = depth == 0
            word += ch
        i += 1
    return out


def _title_style(title: str) -> Optional[str]:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", title)]
    content = [w for w in words[1:] if w.lower() not in _STOP and len(w) > 3]
    if len(content) < 3:
        return None
    caps = sum(1 for w in content if w[0].isupper())
    if caps / len(content) >= 0.8:
        return "title case"
    if caps / len(content) <= 0.25:
        return "sentence case"
    return None


@register("FMT-08")
def reference_list(pm, ctx):
    refs = list(pm.references)
    md = pm.metadata or {}
    if not refs and not md.get("bib_duplicate_keys"):
        ctx.skip("FMT-08", "the paper map has no reference list")
        return
    steps = [f"Read {len(refs)} reference entries" + (f" from {', '.join(md.get('bib_files') or [])}"
                                                       if md.get("bib_files") else "") + "."]
    # duplicate keys in the .bib
    for key in sorted(set(md.get("bib_duplicate_keys") or [])):
        ref = pm.reference(key)
        b, quote = _ref_quote(pm, ref) if ref else (None, None)
        f = ctx.finding(
            "FMT-08", "Duplicate BibTeX key", "minor",
            f"The key \"{key}\" is defined more than once in the .bib file. BibTeX uses one of the entries and "
            "ignores the others, which may not be the one you meant.",
            block=b, quote=quote, status="confirmed",
            evidence=[Evidence(type="script_output", text=f"duplicate key: {key}",
                               data={"script": "bibtexparser", "source": "metadata.bib_duplicate_keys"})],
            trajectory=steps + ["bibtexparser reported a duplicate key."],
            fix=Fix(action="investigate", detail=f"Keep one entry for \"{key}\" and rename or delete the others.",
                    resolved_when="Every key in the .bib file is unique."),
            script=SCRIPT, extra={"key": key})
        if b is None:
            add_location(f, Anchor(file=(md.get("bib_files") or ["refs"])[0] + ".bib"))
        yield f

    # same DOI on two entries; same title and year under two keys
    by_doi = defaultdict(list)
    by_title = defaultdict(list)
    for r in refs:
        doi = str((r.fields or {}).get("doi") or "").strip().lower()
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi)
        if doi:
            by_doi[doi].append(r)
        title = re.sub(r"[^a-z0-9]", "", str((r.fields or {}).get("title") or "").lower())
        if len(title) > 15:
            by_title[(title, str((r.fields or {}).get("year") or ""))].append(r)
    seen_pairs = set()
    for doi, group in by_doi.items():
        if len(group) < 2:
            continue
        titles = {re.sub(r"[^a-z0-9]", "", str(r.fields.get("title") or "").lower()) for r in group}
        same = len(titles) == 1
        a, b_ = group[0], group[1]
        seen_pairs.add(frozenset(r.id for r in group))
        blk, quote = _ref_quote(pm, b_)
        blk_a, quote_a = _ref_quote(pm, a)
        names = ", ".join(r.key or r.id for r in group)
        yield ctx.finding(
            "FMT-08", "Duplicate reference entry" if same else "Two different works share one DOI", "minor",
            (f"The entries {names} describe the same work (DOI {doi}); the reference list prints it twice."
             if same else
             f"The entries {names} give the same DOI, {doi}, for different titles. A DOI identifies one work, so at "
             "least one of these DOIs is wrong; the reference lookups (CIT-02, CIT-03) show which."),
            block=blk, quote=quote, status="confirmed",
            related=[related(blk_a, quote_a)] if blk_a is not None else [],
            evidence=[Evidence(type="script_output", text=f"DOI {doi}: {names}", data={"script": SCRIPT})],
            trajectory=steps + ["Grouped entries by DOI."],
            fix=Fix(action="investigate", detail="Merge the duplicate entries." if same else
                    "Look up each work's DOI (doi.org) and correct the wrong one.",
                    resolved_when="Each DOI appears on exactly one entry, and it belongs to that entry's work."),
            script=SCRIPT, extra={"keys": [r.key for r in group], "doi": doi})
    for (title, year), group in by_title.items():
        if len(group) < 2 or frozenset(r.id for r in group) in seen_pairs:
            continue
        blk, quote = _ref_quote(pm, group[1], group[1].fields.get("title"))
        blk_a, quote_a = _ref_quote(pm, group[0], group[0].fields.get("title"))
        names = ", ".join(r.key or r.id for r in group)
        yield ctx.finding(
            "FMT-08", "Duplicate reference entry", "minor",
            f"The entries {names} have the same title and year; the reference list prints the work twice.",
            block=blk, quote=quote, status="likely", confidence="medium",
            related=[related(blk_a, quote_a)] if blk_a is not None else [],
            evidence=[Evidence(type="script_output", text=names, data={"script": SCRIPT})],
            trajectory=steps + ["Grouped entries by normalized title and year."],
            fix=Fix(action="investigate", detail="Merge the entries under one key.",
                    resolved_when="Each work appears once in the reference list."),
            script=SCRIPT, extra={"keys": [r.key for r in group]})

    bib_refs = [r for r in refs if r.source == "bibtex"]
    # required BibTeX fields
    for r in bib_refs:
        f_ = r.fields or {}
        etype = str(f_.get("type") or "").lower()
        needed = _REQUIRED.get(etype)
        if not needed:
            continue
        missing = [alts[0] for alts in needed if not any(f_.get(_FIELD_ALIAS.get(a, a)) for a in alts)]
        incomplete = etype == "article" and not f_.get("volume") and not f_.get("pages") \
            and not re.search(r"forthcoming|in press|accepted|to appear", " ".join(str(f_.get(k) or "")
                                                                                   for k in ("note", "volume", "year")), re.I)
        if not missing and not incomplete:
            continue
        b, quote = _ref_quote(pm, r)
        what = (f"lacks the required field(s) {', '.join(missing)}" if missing else "") + \
               (" and " if missing and incomplete else "") + \
               ("has neither volume nor pages (mark it 'forthcoming' if it is not yet published)" if incomplete else "")
        f = ctx.finding(
            "FMT-08", "Reference entry incomplete", "minor",
            f"The @{etype} entry \"{r.key}\" {what}.", block=b, quote=quote, status="confirmed",
            evidence=[Evidence(type="script_output", text=f"{r.key}: fields {sorted(k for k, v in f_.items() if v)}",
                               data={"script": SCRIPT})],
            trajectory=steps + [f"Compared the fields of {r.key} with those BibTeX requires for @{etype}."],
            fix=Fix(action="investigate", detail="Complete the entry from the published record.",
                    resolved_when=f"\"{r.key}\" has every required field."),
            script=SCRIPT, extra={"key": r.key, "missing": missing})
        if b is None:
            add_location(f, _ref_anchor(r))
        yield f

    # acronyms and CamelCase words not protected by braces
    for r in bib_refs:
        raw_title = (r.fields or {}).get("raw_title")
        if not raw_title:
            continue
        words = _unprotected_acronyms(str(raw_title))
        if not words:
            continue
        b, quote = _ref_quote(pm, r, (r.fields or {}).get("title"))
        protected = str(raw_title)
        for w in words:
            protected = re.sub(rf"(?<![{{\w]){re.escape(w)}(?![}}\w])", "{" + w + "}", protected, count=1)
        f = ctx.finding(
            "FMT-08", "Acronym in a title not protected from lowercasing", "minor",
            f"The title of \"{r.key}\" contains {', '.join(words)} without braces. BibTeX styles that set titles in "
            f"sentence case print {', '.join(w.lower() if w.isupper() else w.capitalize() for w in words)} instead.",
            block=b, quote=quote, status="confirmed",
            evidence=[Evidence(type="script_output", text=f"title field: {raw_title}",
                               data={"script": SCRIPT, "file": r.anchor.label() if r.anchor else None,
                                     "unprotected": words})],
            trajectory=steps + [f"Scanned the raw .bib title of {r.key} for capitalized acronyms outside braces."],
            fix=Fix(action="replace", original=str(raw_title), replacement=protected,
                    detail="Edit the title field in the .bib file.",
                    resolved_when=f"Each of {', '.join(words)} sits inside braces in the .bib title."),
            script=SCRIPT, extra={"key": r.key, "acronyms": words})
        if b is None:
            add_location(f, _ref_anchor(r))
        yield f

    # printed reference lists (PDF, Word, thebibliography): acronyms already lowercased
    printed = [r for r in refs if r.source != "bibtex"]
    if printed:
        body_caps = Counter(w for b in pm.blocks if b.kind != "reference"
                            for w in re.findall(r"\b[A-Z]{3,6}\b", b.text))
        for r in printed:
            title = str((r.fields or {}).get("title") or "")
            if not title:
                continue
            lowered = []
            for w in re.findall(r"\b[a-z]{3,6}\b", title):
                up = w.upper()
                if up in KNOWN_ACRONYMS or body_caps.get(up, 0) >= 2:
                    lowered.append(w)
            if not lowered:
                continue
            b, quote = _ref_quote(pm, r, title)
            fixed = title
            for w in lowered:
                fixed = re.sub(rf"\b{re.escape(w)}\b", w.upper(), fixed, count=1)
            f = ctx.finding(
                "FMT-08", "Acronym printed in lowercase in a reference title", "minor",
                f"The printed title of this reference has {', '.join(lowered)}, which the paper or common usage writes as "
                f"{', '.join(w.upper() for w in lowered)}. A citation style or a reference manager probably lowercased it.",
                block=b, quote=quote, status="likely", confidence="medium",
                evidence=[Evidence(type="script_output", text=f"printed title: {title}",
                                   data={"script": SCRIPT, "lowercased": lowered,
                                         "known_or_in_body": [w.upper() for w in lowered]})],
                trajectory=steps + ["Scanned printed reference titles for lowercase words that are acronyms in "
                                    "the paper's own text or in a list of common acronyms."],
                fix=Fix(action="replace", original=title, replacement=fixed,
                        detail="Fix the title in the reference manager or bibliography source, protecting the acronym.",
                        resolved_when=f"The printed title shows {', '.join(w.upper() for w in lowered)} in capitals."),
                script=SCRIPT, extra={"ref": r.id, "acronyms": [w.upper() for w in lowered]})
            if b is None:
                add_location(f, _ref_anchor(r))
            yield f

    # one venue under several names
    venues = defaultdict(list)
    for r in refs:
        name = (r.fields or {}).get("container")
        if name:
            venues[_canonical_venue(str(name))].append((str(name), r))
    initials = {}
    for canon in list(venues):
        ini = _initials(canon)
        if len(ini) >= 3:
            initials[ini] = canon
    for canon in list(venues):
        if canon in initials and initials[canon] != canon and initials[canon] in venues:
            venues[initials[canon]].extend(venues.pop(canon))
    for canon, items in venues.items():
        spellings = Counter(name.strip() for name, _ in items)
        if len(spellings) < 2:
            continue
        common, n_common = spellings.most_common(1)[0]
        odd_name, odd_ref = next((name, r) for name, r in items if name.strip() != common)
        b, quote = _ref_quote(pm, odd_ref, odd_name)
        listing = "; ".join(f"\"{s}\" ({n})" for s, n in spellings.most_common())
        f = ctx.finding(
            "FMT-08", "Journal named in different ways", "minor",
            f"The reference list names one journal in {len(spellings)} ways: {listing}.",
            block=b, quote=quote, status="likely", confidence="medium",
            evidence=[Evidence(type="script_output", text=listing, data={"script": SCRIPT})],
            trajectory=steps + ["Grouped journal names after normalizing case, punctuation, a leading 'The' and "
                                "common abbreviations."],
            fix=Fix(action="replace", original=odd_name, replacement=common,
                    detail="Use one form of each journal name, full or abbreviated, throughout.",
                    resolved_when="Each journal is named one way."),
            script=SCRIPT, extra={"spellings": dict(spellings)})
        if b is None:
            add_location(f, _ref_anchor(odd_ref))
        yield f

    # DOI format
    bad_doi = []
    forms = Counter()
    for r in refs:
        doi = str((r.fields or {}).get("doi") or "").strip()
        if not doi:
            continue
        if re.match(r"https?://", doi, re.I):
            forms["URL"] += 1
        elif doi.lower().startswith("doi:"):
            forms["doi: prefix"] += 1
        else:
            forms["bare"] += 1
        core = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
        if not re.fullmatch(r"10\.\d{4,9}/\S+", core) or re.search(r"[.,;]$", core):
            bad_doi.append((r, doi))
    for r, doi in bad_doi:
        b, quote = _ref_quote(pm, r)
        f = ctx.finding(
            "FMT-08", "Malformed DOI", "minor",
            f"The DOI of \"{r.key or r.id}\", \"{doi}\", is not in the form 10.NNNN/suffix, so the link will not resolve.",
            block=b, quote=quote, status="confirmed",
            evidence=[Evidence(type="script_output", text=doi, data={"script": SCRIPT, "pattern": r"10\.\d{4,9}/\S+"})],
            trajectory=steps + ["Checked each DOI against the pattern 10.NNNN/suffix."],
            fix=Fix(action="investigate", detail="Copy the DOI from the publisher's page or doi.org.",
                    resolved_when="Every DOI has the form 10.NNNN/suffix with no trailing punctuation or spaces."),
            script=SCRIPT, extra={"key": r.key, "doi": doi})
        if b is None:
            add_location(f, _ref_anchor(r))
        yield f
    if bib_refs and (forms["URL"] or forms["doi: prefix"]):
        style = ", ".join(f"{k} {v}" for k, v in forms.items())
        r = next(r for r in bib_refs if re.match(r"https?://|doi:", str(r.fields.get("doi") or ""), re.I))
        b, quote = _ref_quote(pm, r)
        f = ctx.finding(
            "FMT-08", "DOI field holds a URL or prefix", "minor",
            f"Some .bib DOI fields are not bare DOIs ({style}). Bibliography styles add their own prefix, so these print "
            "as \"doi:https://doi.org/...\" or similar.",
            block=b, quote=quote, status="confirmed",
            evidence=[Evidence(type="script_output", text=style, data={"script": SCRIPT})],
            trajectory=steps + ["Classified each DOI field as bare, URL or 'doi:' prefixed."],
            fix=Fix(action="investigate", detail="Store bare DOIs (10.NNNN/suffix) in the doi field.",
                    resolved_when="Every doi field holds a bare DOI."),
            script=SCRIPT)
        if b is None:
            add_location(f, _ref_anchor(r))
        yield f

    # author name format and title capitalization
    initials_only, full = [], []
    for r in refs:
        for a in (r.fields or {}).get("authors") or []:
            given = str(a.get("given") or "").strip() if isinstance(a, dict) else ""
            if not given:
                continue
            (initials_only if re.fullmatch(r"(?:[A-Z]\.?[\s-]*){1,3}", given) else full).append(r)
            break
    # each entry is counted once, by its first author with a given name
    if len(initials_only) >= 2 and len(full) >= 2:
        r = initials_only[0] if len(initials_only) <= len(full) else full[0]
        b, quote = _ref_quote(pm, r)
        f = ctx.finding(
            "FMT-08", "Author names in two formats", "minor",
            f"{len(initials_only)} entries give authors' first names as initials and {len(full)} spell them "
            "out, so the reference list will look inconsistent unless the style abbreviates all of them.",
            block=b, quote=quote, status="likely", confidence="medium",
            evidence=[Evidence(type="script_output", text=f"initials: {[x.key or x.id for x in initials_only][:10]}; "
                                                          f"full: {[x.key or x.id for x in full][:10]}",
                               data={"script": SCRIPT})],
            trajectory=steps + ["Classified the first author's given name of each entry as initials or full."],
            fix=Fix(action="investigate", detail="Use one form for given names in every entry.",
                    resolved_when="All entries give first names the same way."),
            script=SCRIPT)
        if b is None:
            add_location(f, _ref_anchor(r))
        yield f
    styles = defaultdict(list)
    for r in refs:
        st = _title_style(str((r.fields or {}).get("title") or ""))
        if st:
            styles[st].append(r)
    if len(styles.get("title case", [])) >= 2 and len(styles.get("sentence case", [])) >= 2:
        minority = min(styles.values(), key=len)
        r = minority[0]
        b, quote = _ref_quote(pm, r, (r.fields or {}).get("title"))
        f = ctx.finding(
            "FMT-08", "Titles in two capitalization styles", "minor",
            f"{len(styles['title case'])} titles are in title case and {len(styles['sentence case'])} in sentence case."
            + (" Unless the bibliography style recases titles, the printed list mixes the two."
               if r.source == "bibtex" else ""),
            block=b, quote=quote, status="likely", confidence="medium",
            evidence=[Evidence(type="script_output", text=", ".join(x.key or x.id for x in minority[:10]),
                               data={"script": SCRIPT})],
            trajectory=steps + ["Classified each title (four or more content words) as title or sentence case."],
            fix=Fix(action="investigate", detail="Use one capitalization style for titles, or a style file that sets it.",
                    resolved_when="All titles follow one capitalization style."),
            script=SCRIPT)
        if b is None:
            add_location(f, _ref_anchor(r))
        yield f


# =============================================================== BEH-11 software and recruitment citations
_SOFTWARE = [
    ("oTree", re.compile(r"\boTree\b|\bo-Tree\b", re.I), ("chen",), ("schonger", "wickens"), "2016",
     re.compile(r"\boTree\b", re.I), "Chen, Schonger and Wickens (2016), \"oTree: An open-source platform for laboratory, "
     "online, and field experiments\", Journal of Behavioral and Experimental Finance 9: 88-97", "minor",
     "oTree's documentation says that research done with oTree must cite this paper"),
    ("z-Tree", re.compile(r"\bz-?Tree\b", re.I), ("fischbacher",), (), "2007", re.compile(r"z-?Tree", re.I),
     "Fischbacher (2007), \"z-Tree: Zurich toolbox for ready-made economic experiments\", Experimental Economics 10: "
     "171-178", "suggestion", "citing it is customary; whether z-Tree's license requires it is unconfirmed"),
    ("ORSEE", re.compile(r"\bORSEE\b"), ("greiner",), (), "2015", re.compile(r"ORSEE|subject pool recruitment", re.I),
     "Greiner (2015), \"Subject pool recruitment procedures: organizing experiments with ORSEE\", Journal of the "
     "Economic Science Association 1: 114-125", "minor", "ORSEE's license requires users to cite this article"),
    ("hroot", re.compile(r"\bhroot\b", re.I), ("bock",), ("baetge", "nicklisch"), "2014", re.compile(r"\bhroot\b", re.I),
     "Bock, Baetge and Nicklisch (2014), \"hroot: Hamburg registration and organization online tool\", European "
     "Economic Review 71: 117-120", "suggestion",
     "citing it is customary; whether hroot's terms require it is unconfirmed"),
]


def _ref_matches(r, families, others, year, title_pat) -> bool:
    f = r.fields or {}
    fams = [str(a.get("family") or "").lower() for a in f.get("authors") or [] if isinstance(a, dict)]
    raw = (r.raw or "").lower()
    has_first = any(any(x in fam for fam in fams) for x in families) or any(x in raw for x in families)
    has_other = not others or any(any(o in fam for fam in fams) for o in others) or any(o in raw for o in others)
    title_hit = bool(title_pat.search(str(f.get("title") or "") + " " + (r.raw or "")))
    year_ok = year in str(f.get("year") or "") or year in raw
    return (has_first and has_other and (year_ok or title_hit)) or (title_hit and has_first)


@register("BEH-11")
def software_citations(pm, ctx):
    texts = prose(pm, PROSE_KINDS + ("acknowledgment",))
    checked = []
    for name, use_pat, families, others, year, title_pat, citation, severity, why in _SOFTWARE:
        uses = [(b, m) for b in texts for m in use_pat.finditer(b.text)]
        if not uses:
            continue
        checked.append(name)
        if any(_ref_matches(r, families, others, year, title_pat) for r in pm.references):
            continue
        b, m = uses[0]
        quote = sentence_quote(b, m.start(), 35)
        yield ctx.finding(
            "BEH-11", f"{name} used without its citation", severity,
            f"The paper uses {name} but does not cite {citation}; {why}.",
            block=b, quote=quote, status="confirmed" if severity == "minor" else "likely",
            related=[related(b2, sentence_quote(b2, m2.start(), 35)) for b2, m2 in uses[1:4]],
            evidence=[Evidence(type="quote", text=quote, block=b.id),
                      Evidence(type="checked_absence", text=citation,
                               data={"scope": f"all {len(pm.references)} reference entries",
                                     "terms": {f"{families[0].title()} {year}": 0}})],
            trajectory=[f"Found {name} mentioned {len(uses)} time(s); the first is at {b.anchor.label()}.",
                        f"Searched the reference list for {citation.split(',')[0]} by author, year and title: none."],
            fix=Fix(action="insert", detail=f"Cite {citation} where {name} is first mentioned, and add it to the "
                                            "references.",
                    resolved_when=f"The reference list contains the {name} citation and the text cites it."),
            script=SCRIPT, extra={"software": name})
    note_coverage(ctx, "BEH-11", ("software mentioned: " + ", ".join(checked)) if checked else
                  "no oTree, z-Tree, ORSEE or hroot mention found")
