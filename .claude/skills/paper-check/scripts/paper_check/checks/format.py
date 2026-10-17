"""Format and compliance checks (FMT) that a script can decide.

Each check reads the paper map and, where a rule depends on the journal, the
venue profile in ctx.venue. Quotes are verbatim slices of block text, so that
`pc.py verify` can find them. Comments, build logs and file metadata are not
block text: findings about them carry that text as evidence, point to the
source file, and have no quote.

Rules marked with a TeXtidote rule id (sh:...) are reimplemented in Python from
the rule list published in TeXtidote's README
(https://github.com/sylvainhalle/textidote, GPL-3). Only the list of rules was
used; no TeXtidote code was read or copied.

This module also holds small helpers that the other script check modules in
this package (venue, coherence, language, references_local) import.
"""

from __future__ import annotations

import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

from ..model import Anchor, Evidence, Fix, Location
from ..textutil import find_quote, normalize, split_sentences
from . import register

SCRIPT = "checks/format.py"

PROSE_KINDS = ("abstract", "paragraph", "list_item", "footnote", "caption")
BODY_KINDS = ("paragraph", "list_item", "footnote", "caption")
FRONT_KINDS = ("title", "author", "acknowledgment", "front_matter")
CONTENT_KINDS = ("paragraph", "list_item", "footnote", "caption", "table", "equation", "abstract", "reference")
_REFLIST_HEADING = re.compile(r"\s*(?:[A-Z]|\d+)?\.?\s*(?:references|bibliography|works cited|literature cited)\s*$", re.I)


# =============================================================== shared helpers
def input_format(pm) -> str:
    return str((pm.source or {}).get("format") or "unknown")


def is_hidden(block) -> bool:
    return bool((block.attrs or {}).get("hidden"))


def prose(pm, kinds: Iterable[str] = PROSE_KINDS, include_hidden: bool = False) -> list:
    kinds = tuple(kinds)
    return [b for b in pm.blocks if b.kind in kinds and b.text and (include_hidden or not is_hidden(b))]


_APPENDIX_HEADING = re.compile(r"\s*(?:[A-Z](?:\.\d+)*\.?\s+)?(?:online\s+|supplementary\s+|supplemental\s+|web\s+)?"
                               r"appendi(?:x|ces)\b", re.I)


def appendix_titles(pm) -> set:
    """Texts of the headings that belong to an appendix (cached on the paper map)."""
    cached = getattr(pm, "_pc_appendix_titles", None)
    if cached is not None:
        return cached
    out, inside_app = set(), False
    for b in pm.blocks:
        if b.kind != "heading" or b.attrs.get("generated"):
            continue
        if b.attrs.get("appendix") or _APPENDIX_HEADING.match(b.text):
            inside_app = True
        elif b.level is not None and b.level <= 1 and b.attrs.get("appendix") is False:
            inside_app = False
        if inside_app:
            out.add(b.text)
    object.__setattr__(pm, "_pc_appendix_titles", out)
    return out


def in_appendix(pm, block) -> bool:
    if block.kind == "heading" and (block.attrs.get("appendix") or _APPENDIX_HEADING.match(block.text)):
        return True
    titles = appendix_titles(pm)
    return any(s in titles for s in (block.section or []))


def sentence_bounds(block, pos: int) -> tuple:
    """(start, end) of the sentence of block.text that contains pos."""
    spans = [(s.start, s.end) for s in (block.sentences or [])] or split_sentences(block.text) or [(0, len(block.text))]
    best = spans[0]
    for s, e in spans:
        if s <= pos < e:
            return s, e
        if s <= pos:
            best = (s, e)
    return best


def window(text: str, start: int, end: int, before: int = 6, after: int = 6, bounds=None) -> str:
    """A verbatim slice of text around [start, end), widened to whole words and by up to
    `before` and `after` more words, never leaving `bounds` (usually the sentence)."""
    lo, hi = bounds if bounds else (0, len(text))
    lo, hi = max(0, lo), min(len(text), hi)
    s = max(lo, min(start, hi))
    e = max(s, min(max(end, start), hi))
    while s > lo and not text[s - 1].isspace():
        s -= 1
    while e < hi and not text[e].isspace():
        e += 1
    for _ in range(before):
        j = s
        while j > lo and text[j - 1].isspace():
            j -= 1
        while j > lo and not text[j - 1].isspace():
            j -= 1
        if j >= s:
            break
        s = j
    for _ in range(after):
        j = e
        while j < hi and text[j].isspace():
            j += 1
        while j < hi and not text[j].isspace():
            j += 1
        if j <= e:
            break
        e = j
    return text[s:e].strip().rstrip(",;:").strip()


def quote_at(block, start: int, end: Optional[int] = None, before: int = 6, after: int = 6) -> str:
    """Verbatim quote around a span, kept inside its sentence."""
    end = start if end is None else end
    return window(block.text, start, end, before, after, bounds=sentence_bounds(block, start))


def sentence_quote(block, pos: int, max_words: int = 40) -> str:
    """The sentence containing pos; long sentences are shortened with "..." (find_quote accepts it)."""
    s, e = sentence_bounds(block, pos)
    text = block.text[s:e].strip()
    words = text.split()
    if len(words) <= max_words:
        return text
    head = " ".join(words[:(max_words * 2) // 3])
    tail = " ".join(words[-(max_words // 3):])
    return f"{head} ... {tail}"


def block_quote(block, max_words: int = 40) -> str:
    text = block.text.strip()
    if len(text.split()) <= max_words:
        return text
    return sentence_quote(block, 0, max_words)


def related(block, quote: str) -> dict:
    return {"quote": quote, "block": block.id}


def span_list(block, citations: bool = True, crossrefs: bool = True) -> list:
    out = []
    if citations:
        out += [(c.start, c.end) for c in block.citations]
    if crossrefs:
        out += [(r.start, r.end) for r in block.crossrefs]
    return out


def math_spans(text: str) -> list:
    return [(m.start(), m.end()) for m in re.finditer(r"\$[^$]{0,400}\$", text)]


def inside(pos: int, spans: list) -> bool:
    return any(s <= pos < e for s, e in spans)


def add_location(f, anchor: Optional[Anchor] = None, section=None, block_id: Optional[str] = None):
    f.locations.append(Location(block=block_id, anchor=anchor, section=list(section or [])))
    return f


def doc_anchor(pm) -> Anchor:
    """An anchor for the whole document: the main LaTeX file, or the PDF or Word file's name."""
    src = pm.source or {}
    return Anchor(file=src.get("main") or (Path(str(src["path"])).name if src.get("path") else None))


def paper_paths(pm) -> tuple:
    """(paper folder, main file) for LaTeX input; either may be None."""
    src = pm.source or {}
    folder = Path(src["paper_dir"]) if src.get("paper_dir") else None
    main = folder / src["main"] if folder and src.get("main") else None
    return folder, main


def compact(value, limit: int = 300) -> str:
    if isinstance(value, dict):
        text = "; ".join(f"{k}: {compact(v, 120)}" for k, v in value.items() if v not in (None, "", [], {}))
    elif isinstance(value, (list, tuple)):
        text = ", ".join(compact(v, 80) for v in value)
    else:
        text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def note_coverage(ctx, check_id: str, text: str) -> None:
    """Attach a note to a check that ran (shown in the coverage table)."""
    if hasattr(ctx, "note"):
        ctx.note(check_id, text)


# ---------------------------------------------------------------- venue helpers
def venue_name(ctx) -> str:
    v = ctx.venue or {}
    return v.get("abbreviation") or v.get("name") or v.get("id") or "the venue"


def venue_rule(ctx, key: str) -> Optional[dict]:
    from ..venues import rule
    return rule(ctx.venue, key)


def venue_other(ctx, name: str) -> Optional[dict]:
    for item in (((ctx.venue or {}).get("rules") or {}).get("other") or []):
        if item.get("name") == name and item.get("status") != "not_stated":
            return item
    return None


def rule_url(ctx, r) -> Optional[str]:
    sid = (r or {}).get("source")
    for s in (ctx.venue or {}).get("sources") or []:
        if s.get("id") == sid:
            return s.get("url")
    return None


def rule_confirmed(r) -> bool:
    return bool(r) and r.get("status") == "confirmed"


def rule_status(r, confirmed: str = "confirmed") -> str:
    return confirmed if rule_confirmed(r) else "likely"


def rule_caveat(r) -> str:
    if rule_confirmed(r):
        return ""
    note = " ".join(str((r or {}).get("note") or "").split())
    if len(note) > 220:
        note = note[:217].rstrip() + "..."
    return (" This venue rule is unconfirmed" + (f" ({note})" if note else "")
            + ", so the finding is marked likely; check the journal's current guidelines.")


def rule_evidence(ctx, key: str, r: dict) -> Evidence:
    v = ctx.venue or {}
    return Evidence(type="note", url=rule_url(ctx, r),
                    text=f"{v.get('name', 'Venue')} profile, rule {key} ({r.get('status')}): {compact(r.get('value'))}",
                    data={"venue": v.get("id"), "rule": key, "status": r.get("status"), "quote": r.get("quote"),
                          "note": r.get("note"), "checked_on": v.get("checked_on")})


def venue_steps(ctx) -> list:
    v = ctx.venue or {}
    if not v:
        return []
    step = f"Loaded the {v.get('name')} venue profile (rules checked {v.get('checked_on')})."
    if v.get("_stale"):
        step += f" The profile is {v.get('_age_days')} days old, past the 180-day limit; recheck the journal's rules."
    return [step]


def review_type(ctx) -> tuple:
    """(value, rule): value is None without a venue, else the review_type value or 'unknown'."""
    if not ctx.venue:
        return None, None
    r = venue_rule(ctx, "review_type")
    if not r:
        return "unknown", None
    return (r.get("value") or "unknown"), r


def setting(ctx, name: str, default=None):
    return getattr(ctx.settings, name, default) if ctx.settings is not None else default


def author_names(pm) -> list:
    """Name tokens of the paper's authors (family and given names), lowercased."""
    names = []
    for b in pm.blocks:
        if b.kind == "author" and not _ANON.search(b.text):
            for tok in re.findall(r"[A-Z][a-zà-ÿ'’-]{2,}", b.text):
                if tok.lower() not in _NAME_STOP:
                    names.append(tok.lower())
    for a in pm.authors or []:
        for tok in re.findall(r"[A-Z][a-zà-ÿ'’-]{2,}", str(a)):
            if tok.lower() not in _NAME_STOP and tok.lower() not in names:
                names.append(tok.lower())
    return names


_ANON = re.compile(r"anonym|blind(?:ed)?\b|removed|withheld|redacted|for review", re.I)
_NAME_STOP = {"and", "university", "college", "institute", "department", "school", "center", "centre", "the",
              "economics", "email", "mail", "corresponding", "author", "authors", "research", "laboratory"}


# =============================================================== FMT-02 anonymization
_SELF_CITE = re.compile(
    r"\b(?:our|my)\s+(?:own\s+)?(?:previous|prior|earlier|companion|related|past|other|forthcoming|ongoing|recent)\s+"
    r"(?:work|works|paper|papers|study|studies|research|article|articles|working\s+papers?|book|experiments?)\b"
    r"|\bour\s+own\s+(?:work|paper|papers|study|studies|research)\b"
    r"|\bthe\s+(?:present\s+)?authors?['’]?(?:s)?['’]?\s+(?:own\s+)?(?:previous|prior|earlier|own|other)\s+"
    r"(?:work|works|paper|papers|study|studies|research)\b"
    r"|\b(?:we|I)\s+(?:have\s+)?(?:previously\s+|earlier\s+|already\s+)?"
    r"(?:showed|shown|found|demonstrated|documented|argued|established|reported|proposed)\s+(?:in|elsewhere)\b",
    re.I)
_NOT_PAPER_AFTER = re.compile(
    r"\s*(?:the\s+)?(?:section|sections|table|tables|figure|figures|fig\.|appendix|appendices|column|columns|panel|"
    r"equation|eq\.|proposition|lemma|theorem|corollary|chapter|part|this|the\s+(?:previous|next|following|last)|"
    r"(?:the\s+)?(?:above|below)|\(\d|\d)", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_REPO_URL = re.compile(r"(?:https?://)?(?:www\.)?(github\.com|gitlab\.com|bitbucket\.org|huggingface\.co)/([\w.-]+)", re.I)
_PERSONAL_URL = re.compile(
    r"(?:https?://)?[\w-]+(?:\.[\w-]+)+/~[\w.-]+|(?:https?://)?sites\.google\.com/(?:site|view)/[\w.-]+"
    r"|(?:https?://)?[\w-]+\.github\.io\b", re.I)
_GRANT = re.compile(
    r"\b(?:grants?|awards?)\b[^.;]{0,60}?(?:(?:\bno\.?|\bnumbers?|#)\s*:?\s*[A-Z0-9][\w/-]{2,}"
    r"|(?-i:\b[A-Z]{1,6}[-/]?[A-Z]?\d{3,}[\w/-]*)|\b\d{5,}\b)", re.I)
_INSTITUTION = re.compile(
    r"\b(?:Universit(?:y|ät|at|é|à|e)|College|Institute|Institut|School of|Department of|Dept\.|Laborator(?:y|ies)|"
    r"Research Cent(?:er|re)|Business School)\b")
_IRB_NAMED = re.compile(
    r"(?:Institutional Review Board|\bIRB\b|[Ee]thics (?:[Cc]ommittee|[Bb]oard|[Cc]ouncil))(?:\s*\([A-Z]+\))?\s+(?:of|at)\s+"
    r"(?:the\s+)?(?:[A-Z][\w&.'’-]*\s+){0,6}(?:Universit\w*|College|Institute|School)\b(?:\s+of\s+(?:[A-Z][\w-]*\s?){1,4})?"
    r"|(?:[A-Z][\w&.'’-]*\s+){1,5}(?:University|College|Institute)(?:\s+of\s+[A-Z][\w-]*)?(?:['’]s)?\s+"
    r"(?:Institutional Review Board|IRB|[Ee]thics (?:[Cc]ommittee|[Bb]oard))")
_OWN_REPO = re.compile(r"\b(?:our|my)\b|replication|(?:data|code|materials|programs?)(?: and (?:data|code|materials))? "
                       r"(?:are|is|will be) (?:available|posted|at|on|in)|available (?:at|from|on)|can be (?:found|downloaded)")
_THIRD_PARTY = re.compile(r"\b(?:package|library|toolbox|software|module|developed by|written by|implemented by|"
                          r"maintained by)\b")
_THANKS = re.compile(r"^\s*(?:we|i)\s+(?:are\s+(?:very\s+)?)?(?:thank|grateful|gratefully\s+acknowledge|acknowledge)\b"
                     r"|^\s*acknowledge?ments?\b", re.I)
_SOFTWARE = re.compile(r"latex|tex\b|pdftex|xetex|luatex|microsoft|word|acrobat|overleaf|libreoffice|openoffice|"
                       r"google|pages|quartz|ghostscript|writer|distiller|pandoc|r markdown|knitr", re.I)


def _self_citations(pm):
    for b in prose(pm, PROSE_KINDS + ("acknowledgment",)):
        cites = span_list(b, crossrefs=False)
        for m in _SELF_CITE.finditer(b.text):
            low = m.group(0).lower()
            s0, e0 = sentence_bounds(b, m.start())
            has_cite = any(s0 <= s < e0 for s, _ in cites)
            if low.startswith(("we ", "i ")) and not low.endswith("elsewhere"):
                after = b.text[m.end():m.end() + 60]
                if _NOT_PAPER_AFTER.match(after):
                    continue
                if not any(m.end() <= s < m.end() + 40 for s, _ in cites) and not re.match(r"\s*\[\d", after):
                    continue
            yield b, m.start(), m.end(), has_cite


def _identifying_items(pm) -> dict:
    """block id -> {"block": b, "reasons": [...], "spans": [(start, end, reason)]}."""
    items: dict = {}
    names = author_names(pm)

    def add(b, start, end, reason):
        entry = items.setdefault(b.id, {"block": b, "reasons": [], "spans": []})
        if reason not in entry["reasons"]:
            entry["reasons"].append(reason)
        entry["spans"].append((start, end, reason))

    heading_ack = set()
    current_ack = False
    for b in pm.blocks:
        if b.kind == "heading":
            current_ack = bool(re.search(r"acknowledg", b.text, re.I))
        elif current_ack and b.kind == "paragraph":
            heading_ack.add(b.id)
    for b in pm.blocks:
        if b.kind in ("reference", "table", "equation", "heading", "keywords", "jel") or not b.text.strip() or is_hidden(b):
            continue
        text = b.text
        if b.kind == "author":
            if not _ANON.search(text):
                add(b, 0, len(text), "author name")
            for m in _INSTITUTION.finditer(text):
                add(b, m.start(), m.end(), "affiliation")
        thanks_words = re.search(r"\b(?:thank|grateful|acknowledg|comments|suggestions|support|funding|financ|grant)",
                                 text, re.I)
        if (b.kind == "acknowledgment" and thanks_words) or b.id in heading_ack or \
                (b.kind in ("paragraph", "footnote") and _THANKS.search(text)):
            add(b, 0, min(len(text), sentence_bounds(b, 0)[1]), "acknowledgments")
        if b.kind in ("acknowledgment", "front_matter", "author", "footnote") or b.id in heading_ack:
            if b.kind != "author":
                for m in _INSTITUTION.finditer(text):
                    if b.kind == "acknowledgment" and not _IRB_NAMED.search(text[max(0, m.start() - 120):m.end() + 10]):
                        add(b, m.start(), m.end(), "affiliation")
            for m in _GRANT.finditer(text):
                add(b, m.start(), m.end(), "grant number")
        for m in _EMAIL.finditer(text):
            add(b, m.start(), m.end(), "e-mail address")
        for m in _IRB_NAMED.finditer(text):
            add(b, m.start(), m.end(), "ethics approval naming an institution")
        for m in _PERSONAL_URL.finditer(text):
            add(b, m.start(), m.end(), "personal web page")
        for m in _REPO_URL.finditer(text):
            user = m.group(2).lower()
            s0, e0 = sentence_bounds(b, m.start())
            ctx_text = text[s0:e0].lower()
            own = _OWN_REPO.search(ctx_text) and not (_THIRD_PARTY.search(ctx_text) and not re.search(r"\b(?:our|my)\b",
                                                                                                    ctx_text))
            if any(n in user for n in names) or own:
                add(b, m.start(), m.end(), "code repository under a user name")
    return items


def _metadata_authors(pm) -> list:
    out = []
    fmt = input_format(pm)
    md = pm.metadata or {}
    for key in ("pdf_info", "document_info", "info", "pdf_metadata", "xmp", "core_properties", "document_properties",
                "docx_properties", "properties", "docx_core"):
        d = md.get(key)
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            kl = str(k).lower().lstrip("/").replace(" ", "_")
            ok = kl in ("author", "authors", "lastmodifiedby", "last_modified_by", "dc:creator", "manager", "company")
            ok = ok or (kl == "creator" and fmt == "docx")
            if ok and v and str(v).strip() and not _SOFTWARE.search(str(v)) and not _ANON.search(str(v)):
                out.append((f"{key}.{k}", str(v).strip()))
    for k in ("author", "pdf_author", "document_author", "last_modified_by"):
        v = md.get(k)
        if isinstance(v, str) and v.strip() and not _SOFTWARE.search(v):
            out.append((k, v.strip()))
    xmp = md.get("xmp")
    if isinstance(xmp, dict) and isinstance(xmp.get("creator"), list):
        out += [("xmp.creator", str(v).strip()) for v in xmp["creator"]
                if str(v).strip() and not _SOFTWARE.search(str(v)) and not _ANON.search(str(v))]
    if fmt == "latex":
        out += _latex_pdfauthor(pm)
    seen, uniq = set(), []
    for k, v in out:
        if (k, v) not in seen:
            seen.add((k, v))
            uniq.append((k, v))
    return uniq


def _identifying_metadata(pm) -> list:
    """Author fields, plus links, running heads and page headers that name the authors or their pages."""
    out = list(_metadata_authors(pm))
    md = pm.metadata or {}
    names = author_names(pm)
    for link in md.get("links") or []:
        uri = str(link.get("uri") if isinstance(link, dict) else link)
        repo = _REPO_URL.search(uri)
        if _PERSONAL_URL.search(uri) or (repo and any(n in repo.group(2).lower() for n in names)):
            out.append(("link" + (f" on page {link.get('page')}" if isinstance(link, dict) and link.get("page") else ""),
                        uri))
    heads = [str(h.get("text") if isinstance(h, dict) else h) for h in (md.get("running_heads") or [])]
    heads += [str(h.get("text")) for h in (md.get("headers_footers") or []) if isinstance(h, dict)]
    for text in heads:
        if any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in names if len(n) > 3):
            out.append(("running head or page header", " ".join(text.split())[:120]))
    return out


def _latex_pdfauthor(pm) -> list:
    folder, main = paper_paths(pm)
    if not main or not main.exists():
        return []
    try:
        text = main.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    text = re.sub(r"(?<!\\)%.*", "", text)
    out = []
    for m in re.finditer(r"pdfauthor\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|[^,}\]\n]+)", text):
        value = m.group(1).strip().strip("{}").strip()
        if value and not _ANON.search(value):
            out.append((f"{pm.source.get('main')}: hyperref pdfauthor", value))
    return out


def _thirdperson(phrase: str) -> Optional[str]:
    """A third-person rewrite of a revealing self-citation phrase, when it is safe."""
    new = re.sub(r"\b(?:our|my)\s+own\s+", "", phrase, flags=re.I)
    new = re.sub(r"\b(?:our|my)\s+", "", new, flags=re.I)
    new = re.sub(r"\bthe\s+(?:present\s+)?authors?['’]?s?['’]?\s+(?:own\s+)?", "", new, flags=re.I)
    if new == phrase or re.match(r"\s*(?:we|i)\b", phrase, re.I):
        return None
    return " ".join(new.split())


@register("FMT-02")
def anonymization(pm, ctx):
    rtype, rrule = review_type(ctx)
    double = rtype == "double_anonymous"
    vname = venue_name(ctx)
    items = _identifying_items(pm)
    selfcites = list(_self_citations(pm))
    meta = _identifying_metadata(pm)
    base = venue_steps(ctx) + [
        "Searched author, acknowledgment and footnote blocks for names, affiliations, grant numbers and e-mail "
        "addresses; all text for self-revealing citations, personal web pages, repositories under a user name and "
        "ethics approvals that name an institution; and the file metadata for author fields."]
    evidence_rules = []
    if ctx.venue:
        if rrule:
            evidence_rules.append(rule_evidence(ctx, "review_type", rrule))
        for name in ("self_citation", "identifying_details", "identifying_links", "title_page", "anonymization"):
            o = venue_other(ctx, name)
            if o:
                evidence_rules.append(rule_evidence(ctx, f"other.{name}", o))
    if double:
        sev, status = "critical", rule_status(rrule)
        caveat = rule_caveat(rrule)
        why = f"{vname} reviews submissions double-anonymously, so the manuscript must not identify its authors."
    elif rtype is None:
        sev, status, caveat = "minor", "likely", ""  # self-citations; other identifying details become a suggestion
        why = ("No venue profile was given, so the review type is unknown. Under double-anonymous review "
               "(all AEA journals now ask for it) this would be Critical.")
    elif rtype == "unknown":
        sev, status, caveat = "minor", "likely", ""
        why = f"The {vname} profile does not record the review type, so whether anonymization is needed is unknown."
    else:
        sev, status, caveat = "suggestion", "confirmed", ""
        why = (f"{vname} uses {rtype.replace('_', '-')} review, so this does not breach its rules; it still tells a "
               "reader who wrote the paper, and some journals ask authors to cite their own work by name.")

    # -- self-revealing citations: always reported
    for b, s, e, has_cite in selfcites:
        phrase = b.text[s:e]
        quote = sentence_quote(b, s, 35)
        repl = _thirdperson(phrase)
        s0, e0 = sentence_bounds(b, s)
        if re.search(r"\b(?:we|our|us|I|my|me)\b", b.text[s0:s] + b.text[e:e0], re.I):
            repl = None  # the rest of the sentence also speaks in the first person
        fix = (Fix(action="replace", original=phrase, replacement=repl,
                   resolved_when="Your own earlier work is cited in the third person, by author name, like any other work.",
                   detail="Cite your own work like anyone else's, by name and year.")
               if repl else
               Fix(action="investigate", resolved_when="Your own earlier work is cited in the third person, by author name.",
                   detail="Rephrase so the sentence does not say that you wrote the cited work, e.g. 'Lu (2024) shows'."))
        problem = (f"\"{phrase}\" tells the reader that the authors wrote the "
                   + ("work cited in this sentence" if has_cite else "work it refers to") + f". {why}{caveat}")
        yield ctx.finding(
            "FMT-02", "Self-revealing citation", sev, problem, block=b, quote=quote, status=status,
            confidence="high" if has_cite else "medium",
            evidence=[Evidence(type="quote", text=quote, block=b.id)] + evidence_rules,
            trajectory=base + [f"Matched the self-citation pattern at {b.anchor.label()}: \"{phrase}\"."
                               + (" A citation is in the same sentence." if has_cite else "")],
            fix=fix, script=SCRIPT, extra={"phrase": phrase})

    authors = [v for v in items.values() if v["block"].kind == "author" and "author name" in v["reasons"]]
    others = [v for v in items.values() if v not in authors]
    if double:
        if authors:
            first = authors[0]["block"]
            names = "; ".join(v["block"].text.strip() for v in authors)
            yield ctx.finding(
                "FMT-02", "Author names in an anonymized manuscript", "critical",
                f"The manuscript names its authors ({names}). {why}{caveat}",
                block=first, quote=block_quote(first, 20), status=status,
                related=[related(v["block"], block_quote(v["block"], 20)) for v in authors[1:]],
                evidence=[Evidence(type="quote", text=block_quote(v["block"], 20), block=v["block"].id) for v in authors]
                + evidence_rules,
                trajectory=base + [f"Found {len(authors)} author block(s) with names."],
                fix=Fix(action="delete", original=None,
                        detail=f"Remove the author block and put names, affiliations and contact details on the separate "
                               f"title page that {vname} asks for.",
                        resolved_when="The compiled manuscript shows no author name, affiliation or e-mail address."),
                script=SCRIPT, extra={"items": [v["block"].text.strip() for v in authors]})
        for v in others:
            b = v["block"]
            reasons = v["reasons"]
            s, e, _ = v["spans"][0]
            short_note = b.kind in ("author", "acknowledgment", "front_matter", "footnote") and len(b.text.split()) <= 40
            quote = block_quote(b, 40) if short_note else quote_at(b, s, e, 4, 8)
            what = ", ".join(reasons)
            kind = "acknowledgment footnote" if b.kind == "acknowledgment" else b.kind.replace("_", " ")
            yield ctx.finding(
                "FMT-02", "Identifying detail in an anonymized manuscript", "critical",
                f"This {kind} identifies the authors ({what}). {why}{caveat}",
                block=b, quote=quote, status=status,
                evidence=[Evidence(type="quote", text=b.text[s0:e0], block=b.id) for s0, e0, _ in v["spans"][:6]]
                + evidence_rules,
                trajectory=base + [f"{b.anchor.label()}: {what}."],
                fix=Fix(action="delete",
                        detail=("Move acknowledgments, affiliations, grant numbers and ethics approvals to the separate "
                                f"title page (or leave them out until acceptance), as {vname} asks."
                                if "acknowledgments" in reasons or "grant number" in reasons or "ethics" in what else
                                "Remove the identifying detail from the anonymized manuscript."),
                        resolved_when="The anonymized manuscript has no passage that names the authors, their "
                                      "institutions, funders or contact details."),
                script=SCRIPT, extra={"reasons": reasons})
        if meta:
            listing = "; ".join(f"{k} = {v}" for k, v in meta)
            f = ctx.finding(
                "FMT-02", "Author identified by the file's metadata, links or running heads", "critical",
                f"The file identifies its authors outside the text ({listing}). Reviewers can read document "
                f"properties, follow links and see running heads. {why}{caveat}", status=status,
                evidence=[Evidence(type="script_output", text=listing, data={"script": SCRIPT, "fields": dict(meta)})]
                + evidence_rules,
                trajectory=base + [f"Read the metadata fields: {listing}."],
                fix=Fix(action="delete",
                        detail="Clear the author field: in LaTeX remove pdfauthor from \\hypersetup; in Word use "
                               "File > Info > Inspect Document; for a PDF, edit the document properties.",
                        resolved_when="The submitted file's properties show no author name."),
                script=SCRIPT, extra={"fields": dict(meta)})
            yield add_location(f, doc_anchor(pm))
        return

    if rtype in (None, "unknown") and (authors or others or meta):
        parts = []
        if authors:
            parts.append("author names (" + "; ".join(v["block"].text.strip() for v in authors) + ")")
        reasons = Counter(r for v in others for r in v["reasons"])
        parts += [f"{r} ({n})" for r, n in reasons.items()]
        if meta:
            parts.append("metadata author fields (" + "; ".join(f"{k} = {v}" for k, v in meta) + ")")
        listing = ", ".join(parts)
        ordered = authors + others
        first = ordered[0]["block"] if ordered else None
        quote = block_quote(first, 20) if first is not None else None
        f = ctx.finding(
            "FMT-02", "Identifying details, if the venue is double-anonymous", "suggestion",
            f"The manuscript identifies its authors through {listing}. {why} If you submit to a journal with "
            "double-anonymous review, remove these before submission.",
            block=first, quote=quote, status="likely", confidence="medium",
            related=[related(v["block"], block_quote(v["block"], 20)) for v in ordered[1:9]],
            evidence=[Evidence(type="script_output", text=listing, data={"script": SCRIPT})],
            trajectory=base + [f"Found: {listing}."],
            fix=Fix(action="investigate",
                    detail="Check the target journal's review type (run with --venue). For double-anonymous review, move "
                           "names, affiliations, acknowledgments and grant numbers to a separate title page and clear "
                           "the file's author metadata.",
                    resolved_when="Either the journal is not double-anonymous, or the manuscript and its metadata "
                                  "no longer identify the authors."),
            script=SCRIPT, extra={"items": parts})
        if first is None:
            add_location(f, doc_anchor(pm))
        yield f


# =============================================================== FMT-04 headings
def _heading_title(b) -> str:
    """The heading's words without its number: '2.1 Setup' gives 'Setup', 'A Additional details' gives
    'Additional details', and 'Appendix A: Additional details' is kept whole."""
    text = b.text.strip()
    num = str((b.attrs or {}).get("number") or "")
    if num and re.match(rf"{re.escape(num)}[\s.:]", text):
        return text[len(num):].lstrip(" .:").strip()
    return re.sub(r"^\d+(?:\.\d+)*[.:]?\s+", "", text)


@register("FMT-04")
def heading_hierarchy(pm, ctx):
    fmt = input_format(pm)
    status = "confirmed" if fmt == "latex" else "likely"
    order = list(pm.blocks)
    heads_all = [(i, b) for i, b in enumerate(order) if b.kind == "heading"]
    heads = [(i, b) for i, b in heads_all if not b.attrs.get("generated") and b.level is not None
             and not _REFLIST_HEADING.match(b.text)]
    if not heads:
        ctx.skip("FMT-04", "no headings were found in the paper map")
        return
    steps = [f"Read {len(heads)} headings with their levels from the paper map ({fmt} input)."]
    levels = [b.level for _, b in heads]
    top = min(levels)

    # sh:secorder: the first heading has the highest level
    i0, first = heads[0]
    if first.level > top:
        yield ctx.finding(
            "FMT-04", "First heading is not a top-level heading", "minor",
            f"The first heading, \"{first.text}\", is at level {first.level}, but the paper uses level {top} headings "
            "later. A document should open with its highest heading level.",
            block=first, quote=first.text, status=status,
            evidence=[Evidence(type="script_output", text=f"heading levels in order: {levels[:12]}",
                               data={"script": SCRIPT, "rule": "TeXtidote sh:secorder (reimplemented)"})],
            trajectory=steps + ["Compared the first heading's level with the highest level used."],
            fix=Fix(action="investigate", detail="Make the first heading a top-level section, or demote the later ones.",
                    resolved_when="The first heading has the highest level used in the paper."),
            script=SCRIPT)

    # sh:secskip: no jump down by more than one level
    for (ia, a), (ib, b) in zip(heads, heads[1:]):
        if b.level > a.level + 1:
            yield ctx.finding(
                "FMT-04", "Heading level skipped", "minor",
                f"\"{b.text}\" (level {b.level}) follows \"{a.text}\" (level {a.level}) with no level {a.level + 1} "
                "heading in between.",
                block=b, quote=b.text, status=status, related=[related(a, a.text)],
                evidence=[Evidence(type="quote", text=a.text, block=a.id), Evidence(type="quote", text=b.text, block=b.id)],
                trajectory=steps + ["Compared each heading's level with the previous heading's (TeXtidote sh:secskip)."],
                fix=Fix(action="investigate", detail=f"Insert a level {a.level + 1} heading, or promote \"{b.text}\".",
                        resolved_when="No heading is more than one level below the heading before it."),
                script=SCRIPT)

    # sh:nsubdiv: a division should not hold a single subdivision
    for k, (ia, a) in enumerate(heads):
        children = []
        for ib, b in heads[k + 1:]:
            if b.level <= a.level:
                break
            if b.level == a.level + 1:
                children.append(b)
        if len(children) == 1:
            c = children[0]
            yield ctx.finding(
                "FMT-04", "Lone subsection", "minor",
                f"\"{a.text}\" contains a single subdivision, \"{c.text}\". A division should have two or more "
                "subdivisions, or none.",
                block=c, quote=c.text, status=status, related=[related(a, a.text)],
                evidence=[Evidence(type="quote", text=a.text, block=a.id), Evidence(type="quote", text=c.text, block=c.id)],
                trajectory=steps + ["Counted the subdivisions one level below each heading (TeXtidote sh:nsubdiv)."],
                fix=Fix(action="investigate",
                        detail="Fold the lone subsection into its parent, or split the material into two subsections.",
                        resolved_when=f"\"{_heading_title(a)}\" has no subsections or at least two."),
                script=SCRIPT)

    # empty sections: nothing between a heading and the next heading of the same or a higher level
    for k, (ia, a) in enumerate(heads):
        nxt = next(((j, b) for j, b in heads_all if j > ia), None)
        stop = nxt[0] if nxt else len(order)
        content = [b for b in order[ia + 1:stop] if b.kind in CONTENT_KINDS and b.text.strip()]
        if content:
            continue
        if nxt and not nxt[1].attrs.get("generated") and nxt[1].level is not None and nxt[1].level > a.level:
            continue  # subsections follow at once: stacked headings, not empty
        after = f"the next heading, \"{nxt[1].text}\"" if nxt else "the end of the document"
        yield ctx.finding(
            "FMT-04", "Empty section", "minor",
            f"\"{a.text}\" has no text before {after}.",
            block=a, quote=a.text, status=status,
            evidence=[Evidence(type="checked_absence", text=f"blocks between {a.anchor.label()} and {after}",
                               data={"scope": "blocks after the heading", "terms": {"text blocks": 0}})],
            trajectory=steps + ["Looked for text, tables, figures or equations between each heading and the next."],
            fix=Fix(action="investigate", detail="Write the section or remove the heading.",
                    resolved_when="Every heading is followed by text before the next heading of the same level."),
            script=SCRIPT)

    # numbering of top-level sections, for formats where numbers come from the text
    if fmt != "latex":
        nums = [(b, (b.attrs or {}).get("number") or (re.match(r"\s*(\d+)\b", b.text) or [None, None])[1])
                for _, b in heads if b.level == top and not in_appendix(pm, b)]
        nums = [(b, int(n)) for b, n in nums if n and str(n).isdigit()]
        for (pa, na), (pb, nb) in zip(nums, nums[1:]):
            if nb != na + 1:
                yield ctx.finding(
                    "FMT-04", "Section numbering is not sequential", "minor",
                    f"Section {nb} follows section {na}.", block=pb, quote=pb.text, status="likely", confidence="medium",
                    related=[related(pa, pa.text)],
                    evidence=[Evidence(type="script_output", text=f"section numbers in order: {[n for _, n in nums]}",
                                       data={"script": SCRIPT})],
                    trajectory=steps + ["Read the number of each top-level heading in order."],
                    fix=Fix(action="investigate", detail="Renumber the sections.",
                            resolved_when="Top-level sections are numbered 1, 2, 3 ... without gaps or repeats."),
                    script=SCRIPT)

    # title style: sh:001 capital letter, sh:002 no closing punctuation, sh:003 not all caps
    for _, b in heads:
        title = _heading_title(b)
        letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", title)
        if not letters:
            continue
        problem, rule = None, None
        first_alpha = next((ch for ch in title if ch.isalpha()), "")
        if first_alpha and first_alpha.islower():
            problem, rule = f"The heading \"{title}\" starts with a lowercase letter.", "sh:001"
        elif re.search(r"[.,;:]\s*$", title) and not title.endswith("..."):
            problem, rule = f"The heading \"{title}\" ends with punctuation.", "sh:002"
        elif fmt == "latex" and len(letters) >= 6 and letters.isupper() and len(title.split()) >= 1:
            problem, rule = f"The heading \"{title}\" is typed in capitals; let the class style set the case.", "sh:003"
        if problem:
            yield ctx.finding(
                "FMT-04", "Heading style", "suggestion", problem, block=b, quote=b.text, status=status,
                evidence=[Evidence(type="quote", text=b.text, block=b.id)],
                trajectory=steps + [f"Checked heading capitalization and punctuation (TeXtidote {rule}, reimplemented)."],
                fix=Fix(action="investigate", detail="Start headings with a capital, without closing punctuation, in "
                                                     "normal case.",
                        resolved_when="Every heading starts with a capital letter, has no closing period, colon or "
                                      "semicolon, and is not typed in capitals."),
                script=SCRIPT)

    # expected sections: a concluding section in a full-length paper
    main_top = [b for _, b in heads if b.level == top and not in_appendix(pm, b)
                and not re.match(r"\s*(?:abstract|keywords?|jel|acknowledge?ments?|highlights)\b", _heading_title(b), re.I)]
    if len(main_top) >= 3 and not any(re.search(r"conclu|concluding|final remarks|summary|discussion|closing",
                                                 b.text, re.I) for _, b in heads):
        last = main_top[-1]
        yield ctx.finding(
            "FMT-04", "No concluding section", "suggestion",
            f"The paper has {len(main_top)} top-level sections but none is a conclusion or discussion "
            f"(the last is \"{last.text}\"). Most economics papers end with one.",
            block=last, quote=last.text, status="likely", confidence="medium",
            evidence=[Evidence(type="checked_absence", text="top-level headings",
                               data={"scope": "all headings", "terms": {"conclu*|concluding|final remarks|summary|"
                                                                        "discussion": 0}})],
            trajectory=steps + ["Searched the headings for a concluding section."],
            fix=Fix(action="insert", detail="Add a short concluding section, or ignore this if the format has none.",
                    resolved_when="The paper ends with a conclusion or discussion section, or the target format "
                                  "does not use one."),
            script=SCRIPT)


# =============================================================== mentions of tables, figures, sections
_MENTION = re.compile(
    r"\b(?P<kind>Sections?|Sec\.|Secs\.|Tables?|Figures?|Fig\.|Figs\.|Appendix|Appendices|Equations?|Eqs?\.)"
    r"(?:\s|~|\xa0)*(?P<nums>\(?(?:[A-Z]?\d+(?:\.\d+)*|[A-Z](?![a-z]))\)?"
    r"(?:\s*(?:,|and|&|–|-|to)\s*\(?(?:[A-Z]?\d+(?:\.\d+)*|[A-Z](?![a-z]))\)?)*)(?![\w-])")
_NUM_TOKEN = re.compile(r"[A-Z]?\d+(?:\.\d+)*|(?<![A-Za-z])[A-Z](?![A-Za-z])")
_KIND_OF = {"section": "section", "sections": "section", "sec.": "section", "secs.": "section",
            "table": "table", "tables": "table", "figure": "figure", "figures": "figure", "fig.": "figure",
            "figs.": "figure", "appendix": "appendix", "appendices": "appendix", "equation": "equation",
            "equations": "equation", "eq.": "equation", "eqs.": "equation"}
_FOREIGN_AFTER = re.compile(r"\s*,?\s*(?:of|in|from)\s+(?:the\s+)?(?:(?:[A-Z][\w'’-]+(?:\s+(?:and|et al\.?|&)\s*[A-Z]?[\w'’-]*)*"
                            r"\s*\(?\d{4})|their|his|her|its|that|this\s+(?:paper|study|article)|the\s+(?:original|cited)"
                            r"|the\s+(?:online|supplementary|web)\s+appendix)")
_FOREIGN_BEFORE = re.compile(r"(?:their|his|her|its|['’]s)\s+(?:\w+\s+)?$", re.I)


def iter_mentions(pm, kinds=BODY_KINDS + ("abstract",)):
    """Textual mentions such as 'Table 3' or 'Sections 2 and 4'.

    Yields (block, kind, number, start, end, in_ref) per number, where in_ref says the
    number came from a resolved or unresolved cross-reference command. Mentions of
    other works' tables ('Table 2 of Smith (2001)') are skipped."""
    for b in prose(pm, kinds):
        # Only generated references (LaTeX \\ref, Word REF fields) count; a PDF reader's textual mentions do not.
        refs = [(r.start, r.end) for r in b.crossrefs if r.command != "text"]
        cites = span_list(b, crossrefs=False)
        for m in _MENTION.finditer(b.text):
            if inside(m.start(), cites):
                continue
            after = b.text[m.end():m.end() + 60]
            if _FOREIGN_AFTER.match(after) or any(m.end() <= s <= m.end() + 25 for s, _ in cites):
                continue
            if _FOREIGN_BEFORE.search(b.text[max(0, m.start() - 30):m.start()]):
                continue
            kind = _KIND_OF[m.group("kind").lower()]
            base = m.start("nums")
            for t in _NUM_TOKEN.finditer(m.group("nums")):
                start = base + t.start()
                yield b, kind, t.group(0), start, base + t.end(), inside(start, refs)


def _objects(pm) -> dict:
    tables = {str(t.number) for t in pm.tables if t.number}
    figures = {str(f.number) for f in pm.figures if f.number}
    equations = {str(b.attrs.get("number")) for b in pm.blocks if b.kind == "equation" and b.attrs.get("number")}
    sections, appendix = set(), set()
    for b in pm.blocks:
        if b.kind != "heading" or b.attrs.get("generated"):
            continue
        # Readers record heading numbers in attrs; without one, only a leading arabic number counts, since a
        # heading such as "A Model of Defaults" starts with a word, not an appendix letter.
        num = b.attrs.get("number")
        if not num:
            m_num = re.match(r"\s*(\d+(?:\.\d+)*)\.?\s", b.text + " ")
            num = m_num.group(1) if m_num else None
        m_app = re.match(r"\s*(?:online\s+|supplementary\s+|web\s+)?appendix\s+([A-Z](?:\.\d+)*|\d+)\b", b.text, re.I)
        if m_app:
            appendix.add(m_app.group(1))
        if num:
            if b.attrs.get("appendix"):
                appendix.add(str(num))
            sections.add(str(num))
    for lab in pm.labels:
        if lab.kind == "appendix" and lab.number:
            appendix.add(str(lab.number))
        elif lab.number and lab.kind in ("table", "figure", "equation", "section"):
            {"table": tables, "figure": figures, "equation": equations, "section": sections}[lab.kind].add(str(lab.number))
    # captions typed in the text, for PDF and Word input
    for b in pm.blocks:
        m = re.match(r"\s*(Table|Figure|Fig\.)\s+([A-Z]?\d+)\b", b.text)
        if m and b.kind in ("caption", "paragraph", "table"):
            (tables if m.group(1) == "Table" else figures).add(m.group(2))
    has_appendix = bool(appendix) or any(b.attrs.get("appendix") for b in pm.blocks if b.kind == "heading")
    return {"table": tables, "figure": figures, "equation": equations, "section": sections, "appendix": appendix,
            "has_appendix": has_appendix}


def _exists(objs: dict, kind: str, num: str, strict: bool = True) -> Optional[bool]:
    """True, False, or None when the paper cannot tell (supplementary material, or a
    non-LaTeX reader that found no objects of that kind)."""
    num = num.strip("()")
    if kind in ("table", "figure"):
        if num in objs[kind]:
            return True
        if num.upper().startswith("S") and num[1:].isdigit():
            return None
        if re.fullmatch(r"[A-Z]\d+", num):
            return None  # appendix-lettered numbering; conventions differ
        return False if (strict or objs[kind]) else None
    if kind == "equation":
        if num in objs["equation"]:
            return True
        return False if objs["equation"] else None
    if kind == "section":
        if num in objs["section"]:
            return True
        return False if objs["section"] else None
    if kind == "appendix":
        if not objs["has_appendix"]:
            return None
        if num in objs["appendix"]:
            return True
        if num.split(".")[0] in objs["appendix"]:
            return True if "." not in num else None
        return False
    return None


# =============================================================== FMT-05 broken cross-references
@register("FMT-05")
def broken_crossrefs(pm, ctx):
    fmt = input_format(pm)
    defined = {lab.name for lab in pm.labels}
    label_kind = {lab.name: lab.kind for lab in pm.labels}
    steps = [f"Read {sum(len(b.crossrefs) for b in pm.blocks)} cross-references and {len(pm.labels)} labels "
             "from the paper map."]

    # unresolved \ref and friends
    unresolved = defaultdict(list)
    for b in pm.blocks:
        for r in b.crossrefs:
            if not r.resolved:
                for lab in r.labels or ["?"]:
                    unresolved[lab].append((b, r))
    for lab, uses in unresolved.items():
        b, r = uses[0]
        quote = quote_at(b, r.start, r.end, before=3, after=4)
        rel = [related(b2, quote_at(b2, r2.start, r2.end, 3, 4)) for b2, r2 in uses[1:6]]
        if r.command in ("REF", "NOTEREF", "PAGEREF"):
            problem = (f"A Word cross-reference field ({r.raw[:60]}) points to the bookmark \"{lab}\", which no longer "
                       "exists. The field still shows its old result, but Word prints \"Error! Reference source not "
                       "found.\" once fields are updated" + (f"; {len(uses)} fields are affected" if len(uses) > 1 else "")
                       + ".")
        elif r.command == "text":
            problem = (f"The text shows \"{r.raw}\"" + (f" in {len(uses)} places" if len(uses) > 1 else "")
                       + ", the mark LaTeX prints for a reference to an undefined label: the table, figure or "
                         "section it should point to has no label in the source, or the label is misspelled.")
        else:
            problem = (f"{r.raw} refers to the label \"{lab}\", which is not defined" + (" anywhere" if lab not in defined
                                                                                       else "")
                       + ", so the compiled paper prints \"??\"" + (f" in {len(uses)} places" if len(uses) > 1 else "")
                       + ".")
        yield ctx.finding(
            "FMT-05", "Undefined cross-reference", "major", problem,
            block=b, quote=quote, related=rel,
            evidence=[Evidence(type="quote", text=quote, block=b.id),
                      Evidence(type="checked_absence", text=f"target of {lab}",
                               data={"scope": {"latex": "every \\label in the source and the .aux file if present",
                                               "docx": "every bookmark in the document"}.get(fmt, "the printed text"),
                                     "terms": {lab: 0}})],
            trajectory=steps + [f"{r.raw[:60]} at {b.anchor.label()} did not resolve to any target."],
            fix=Fix(action="investigate",
                    detail=(f"Add \\label{{{lab}}} to the intended table, figure or section, or correct the label name "
                            "in the reference" + (f" (close labels: {', '.join(_close_labels(lab, defined))})"
                                                  if _close_labels(lab, defined) else "") + "."
                            if fmt == "latex" else
                            "Recreate the cross-reference to the intended caption or heading (Insert > Cross-reference) "
                            "and update all fields." if r.command in ("REF", "NOTEREF", "PAGEREF") else
                            "Fix the reference in the source (the label or cross-reference behind it) and regenerate "
                            "the PDF."),
                    resolved_when="The reference shows the number of an existing table, figure or section, and no "
                                  "\"??\" or error text."),
            script=SCRIPT, extra={"label": lab, "uses": len(uses)})

    # wrong kind: 'Table~\ref{fig:x}'
    for b in pm.blocks:
        for r in b.crossrefs:
            if not r.resolved or not r.labels:
                continue
            kind = label_kind.get(r.labels[0])
            before = b.text[max(0, r.start - 14):r.start]
            m = re.search(r"(Tables?|Figures?|Fig\.|Sections?|Appendix|Equations?|Eq\.)\s*\(?\s*$", before)
            if not m or not kind:
                continue
            word = _KIND_OF[m.group(1).lower()]
            bad = ((word == "table" and kind not in ("table", "other")) or
                   (word == "figure" and kind not in ("figure", "other")) or
                   (word == "equation" and kind not in ("equation", "other")) or
                   (word in ("section", "appendix") and kind in ("table", "figure", "equation")))
            if bad:
                quote = quote_at(b, r.start, r.end, before=2, after=4)
                yield ctx.finding(
                    "FMT-05", "Cross-reference points to the wrong kind of object", "major",
                    f"The text says \"{m.group(1)}\" but {r.raw} points to a {kind} label.",
                    block=b, quote=quote,
                    evidence=[Evidence(type="quote", text=quote, block=b.id),
                              Evidence(type="script_output", text=f"label {r.labels[0]} is a {kind}",
                                       data={"script": SCRIPT})],
                    trajectory=steps + ["Compared the word before each reference with the kind of its label."],
                    fix=Fix(action="investigate", detail="Point the reference to the right label or change the word.",
                            resolved_when="The word before each reference names the kind of object it points to."),
                    script=SCRIPT, extra={"label": r.labels[0]})

    # duplicate labels
    counts = Counter(lab.name for lab in pm.labels)
    for name, n in counts.items():
        if n < 2:
            continue
        labs = [lab for lab in pm.labels if lab.name == name]
        blocks = [pm.block(lab.block) for lab in labs if lab.block and pm.block(lab.block)]
        first = blocks[0] if blocks else None
        f = ctx.finding(
            "FMT-05", "Label defined twice", "major",
            f"The label \"{name}\" is defined {n} times ({', '.join(lab.anchor.label() for lab in labs)}). LaTeX keeps "
            "one of them, so references to it may point to the wrong object.",
            block=first, quote=block_quote(first, 20) if first else None,
            related=[related(b2, block_quote(b2, 20)) for b2 in blocks[1:]],
            evidence=[Evidence(type="script_output", text=f"{name}: {n} definitions", data={"script": SCRIPT})],
            trajectory=steps + ["Counted label definitions by name."],
            fix=Fix(action="investigate", detail="Give each \\label a unique name and update the references.",
                    resolved_when=f"\"{name}\" is defined once and each reference points to the intended object."),
            script=SCRIPT, extra={"label": name})
        if first is None:
            add_location(f, labs[0].anchor)
        yield f

    # literal "??" or "[?]" left in the text (PDF and Word input, or typed by hand)
    for b in prose(pm, BODY_KINDS + ("abstract",)):
        refs = span_list(b)
        for m in re.finditer(r"(?:(?:Tables?|Figures?|Fig\.|Sections?|Appendix|Equations?|Eq\.)\s*\(?|\(|\[|see\s+)(\?\?|\?)(?:\)|\])?",
                             b.text):
            pos = m.start(1)
            if inside(pos, refs):
                continue
            token = m.group(0)
            if m.group(1) == "?" and not re.fullmatch(r"[\[(]\?[\])]", token):
                continue
            quote = quote_at(b, m.start(), m.end(), 3, 4)
            yield ctx.finding(
                "FMT-05", "Broken reference mark in the text", "major",
                f"The text contains \"{token}\", the mark LaTeX prints for an undefined reference or citation.",
                block=b, quote=quote, status="confirmed" if "??" in token else "likely",
                evidence=[Evidence(type="quote", text=quote, block=b.id)],
                trajectory=steps + ["Searched the text for '??', '[?]' and '(?)' outside cross-reference spans."],
                fix=Fix(action="investigate", detail="Fix the undefined label or citation in the source and recompile.",
                        resolved_when="The compiled paper has no '??' or '[?]' marks."),
                script=SCRIPT)

    # textual mentions of objects that do not exist in the paper
    objs = _objects(pm)
    seen = set()
    for b, kind, num, start, end, in_ref in iter_mentions(pm):
        if in_ref:
            continue
        if num.upper().startswith("S") and num[1:].isdigit():
            continue  # supplementary numbering: FMT-16
        ok = _exists(objs, kind, num, strict=fmt == "latex")
        if ok is not False or (kind, num) in seen:
            continue
        if kind == "appendix" and not objs["has_appendix"]:
            continue  # may be a separate appendix: FMT-16
        seen.add((kind, num))
        quote = quote_at(b, start, end, 2, 5)
        have = sorted(objs[kind]) if kind in objs else []
        yield ctx.finding(
            "FMT-05", "Reference to something that does not exist", "major",
            f"The text refers to {kind} {num}, but the paper has no {kind} {num}"
            + (f" (it has {', '.join(have[:12])})" if have else "") + ".",
            block=b, quote=quote, status="confirmed" if fmt == "latex" else "likely",
            confidence="high" if fmt == "latex" else "medium",
            evidence=[Evidence(type="quote", text=quote, block=b.id),
                      Evidence(type="checked_absence", text=f"{kind} {num}",
                               data={"scope": f"every {kind} number in the paper map", "terms": {f"{kind} {num}": 0},
                                     "found": have[:30]})],
            trajectory=steps + [f"Collected textual mentions of tables, figures, sections, equations and appendices; "
                                f"{kind} {num} at {b.anchor.label()} matches no {kind} in the paper."],
            fix=Fix(action="investigate", detail=f"Correct the number, or add the missing {kind}; in LaTeX use \\ref.",
                    resolved_when=f"Every mention of a {kind} points to one that exists."),
            script=SCRIPT, extra={"kind": kind, "number": num})


def _close_labels(lab: str, defined: set) -> list:
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        return []
    return [name for name, score, _ in process.extract(lab, list(defined), scorer=fuzz.ratio, limit=3) if score >= 70]


# =============================================================== FMT-06 numbering and references to floats
@register("FMT-06")
def float_numbering_and_references(pm, ctx):
    fmt = input_format(pm)
    steps = [f"Read {len(pm.tables)} tables, {len(pm.figures)} figures and their labels from the paper map."]
    caption_ids = {o.caption_block for o in list(pm.tables) + list(pm.figures) if o.caption_block}
    float_blocks = {b.id for b in pm.blocks if b.kind == "table"}
    referenced = set()
    for b in pm.blocks:
        if b.id in caption_ids or b.id in float_blocks:
            continue
        for r in b.crossrefs:
            referenced.update(r.labels or [])
    mentioned = defaultdict(list)
    for b, kind, num, start, end, in_ref in iter_mentions(pm, BODY_KINDS + ("abstract",)):
        if b.id in caption_ids:
            continue
        mentioned[(kind, num.strip("()"))].append((b, start, end, in_ref))

    for label, objs in (("Table", pm.tables), ("Figure", pm.figures)):
        kind = label.lower()
        # numbering
        numeric = [o for o in objs if o.number and str(o.number).isdigit()]
        nums = [int(o.number) for o in numeric]
        problems = []
        for k, (o, n) in enumerate(zip(numeric, nums)):
            if k == 0 and n != 1:
                problems.append((o, f"the first {kind} is numbered {n}"))
            elif k > 0 and n == nums[k - 1]:
                problems.append((o, f"two {kind}s are numbered {n}"))
            elif k > 0 and n != nums[k - 1] + 1:
                problems.append((o, f"{label} {n} follows {label} {nums[k - 1]}"))
        for o, what in problems:
            cap = pm.block(o.caption_block) if o.caption_block else None
            f = ctx.finding(
                "FMT-06", f"{label} numbering is not sequential", "minor",
                f"In reading order, {what}.", block=cap, quote=block_quote(cap, 20) if cap else None,
                status="confirmed" if fmt != "latex" else "likely",
                evidence=[Evidence(type="script_output", text=f"{kind} numbers in order: {nums}", data={"script": SCRIPT})],
                trajectory=steps + [f"Listed {kind} numbers in reading order: {nums}."],
                fix=Fix(action="investigate", detail=f"Renumber the {kind}s in the order they appear.",
                        resolved_when=f"{label}s are numbered 1, 2, 3 ... in the order they appear."),
                script=SCRIPT)
            if cap is None:
                add_location(f, o.anchor)
            yield f

        # every float labelled and referenced (TeXtidote sh:figref)
        for o in objs:
            cap = pm.block(o.caption_block) if o.caption_block else None
            by_label = o.label and o.label in referenced
            by_text = o.number and mentioned.get((kind, str(o.number)))
            if by_label or by_text:
                continue
            appendix = cap is not None and in_appendix(pm, cap)
            name = f"{label} {o.number}" if o.number else f"The {kind} at {o.anchor.label()}"
            how = ("It has no \\label, so it cannot be referenced with \\ref. " if fmt == "latex" and not o.label else "")
            f = ctx.finding(
                "FMT-06", f"{label} never referenced in the text", "suggestion" if appendix else "minor",
                f"{name} is never referred to in the text. {how}Every {kind} should be cited in the text, near where "
                "it appears, and the text should say what to see in it.",
                block=cap, quote=block_quote(cap, 20) if cap and cap.text else None,
                evidence=[Evidence(type="checked_absence", text=name,
                                   data={"scope": "all text outside captions",
                                         "terms": {f"\\ref{{{o.label}}}" if o.label else f"{label} {o.number}": 0}})],
                trajectory=steps + [f"Searched every cross-reference and every textual mention for {name}: none."],
                fix=Fix(action="insert", detail=f"Refer to {name} in the text where its content is discussed"
                                                + (", after adding a \\label" if fmt == "latex" and not o.label else "") + ".",
                        resolved_when=f"The text refers to {name} at least once."),
                script=SCRIPT, extra={"float": o.id})
            if cap is None:
                add_location(f, o.anchor)
            yield f

    # hard-coded numbers in LaTeX (sh:hcfig, sh:hctab, sh:hcsec)
    if fmt == "latex":
        objs_all = _objects(pm)
        reported = set()
        for (kind, num), uses in mentioned.items():
            if kind not in ("table", "figure", "section"):
                continue
            hard = [u for u in uses if not u[3]]
            if not hard or _exists(objs_all, kind, num) is not True or (kind, num) in reported:
                continue
            reported.add((kind, num))
            b, start, end, _ = hard[0]
            quote = quote_at(b, start, end, 2, 4)
            yield ctx.finding(
                "FMT-06", "Hard-coded number instead of \\ref", "minor",
                f"{kind.capitalize()} {num} is typed as a number rather than generated with \\ref, so it will be wrong "
                "if the order changes.",
                block=b, quote=quote, related=[related(b2, quote_at(b2, s2, e2, 2, 4)) for b2, s2, e2, _ in hard[1:4]],
                evidence=[Evidence(type="quote", text=quote, block=b.id)],
                trajectory=steps + ["Compared textual mentions with the cross-reference spans (TeXtidote sh:hctab, "
                                    "sh:hcfig, sh:hcsec, reimplemented)."],
                fix=Fix(action="replace", original=b.text[start:end],
                        replacement=f"\\ref{{<label of {kind} {num}>}}",
                        detail=f"Use \\ref with the {kind}'s label.",
                        resolved_when=f"Every mention of {kind} {num} comes from \\ref."),
                script=SCRIPT, extra={"kind": kind, "number": num})


# =============================================================== FMT-07 captions
@register("FMT-07")
def captions(pm, ctx):
    steps = [f"Read the captions of {len(pm.tables)} tables and {len(pm.figures)} figures."]
    for label, objs in (("Table", pm.tables), ("Figure", pm.figures)):
        kind = label.lower()
        with_caption = []
        for o in objs:
            cap = pm.block(o.caption_block) if o.caption_block else None
            text = (o.caption or (cap.text if cap else "")).strip()
            name = f"{label} {o.number}" if o.number else f"the {kind} at {o.anchor.label()}"
            if not text:
                body = next((b for b in pm.blocks if b.kind == "table" and b.attrs.get("table_id") == o.id), None)
                f = ctx.finding(
                    "FMT-07", f"{label} without a caption", "minor",
                    f"{name[0].upper() + name[1:]} has no caption.",
                    block=body, quote=None,
                    evidence=[Evidence(type="checked_absence", text=name,
                                       data={"scope": f"the {kind} environment", "terms": {"\\caption": 0}})],
                    trajectory=steps + [f"{name}: no caption."],
                    fix=Fix(action="insert", detail=f"Add a caption that says what the {kind} shows.",
                            resolved_when=f"{name[0].upper() + name[1:]} has a caption that explains it without the text."),
                    script=SCRIPT, extra={"float": o.id})
                if body is None:
                    add_location(f, o.anchor)
                yield f
                continue
            with_caption.append((o, cap, text))
            if len(re.findall(r"[A-Za-z]{2,}", text)) <= 2 and cap is not None:
                yield ctx.finding(
                    "FMT-07", "Caption too short to stand alone", "minor",
                    f"The caption of {name}, \"{text}\", is too short to explain the {kind} without the text.",
                    block=cap, quote=text, status="likely", confidence="medium",
                    evidence=[Evidence(type="quote", text=text, block=cap.id)],
                    trajectory=steps + ["Counted the words in each caption."],
                    fix=Fix(action="investigate", detail="Say what is shown, for which sample, and in what units.",
                            resolved_when="A reader can tell what the exhibit shows from its caption alone."),
                    script=SCRIPT)
        # one style: closing period (TeXtidote sh:capperiod asks for a period; here only consistency is checked)
        ends = [(o, cap, text, text.rstrip().endswith((".", "!", "?"))) for o, cap, text in with_caption if cap]
        if len(ends) >= 3:
            n_dot = sum(1 for e in ends if e[3])
            minority = None
            if 0 < n_dot <= len(ends) // 3:
                minority = [e for e in ends if e[3]]
            elif 0 < len(ends) - n_dot <= len(ends) // 3:
                minority = [e for e in ends if not e[3]]
            if minority:
                o, cap, text, dot = minority[0]
                yield ctx.finding(
                    "FMT-07", f"{label} captions differ in style", "minor",
                    f"{len(ends) - len(minority)} of {len(ends)} {kind} captions {'do not ' if dot else ''}end with a "
                    f"period, but {len(minority)} {'do' if dot else 'do not'}.",
                    block=cap, quote=text, status="confirmed",
                    related=[related(c2, t2) for _, c2, t2, _ in minority[1:6]],
                    evidence=[Evidence(type="script_output", text=f"{n_dot} of {len(ends)} end with a period",
                                       data={"script": SCRIPT})],
                    trajectory=steps + [f"Compared the closing punctuation of the {kind} captions."],
                    fix=Fix(action="investigate", detail="Use one caption style for all tables and one for all figures.",
                            resolved_when=f"All {kind} captions end the same way."),
                    script=SCRIPT)


# =============================================================== FMT-09 in-text citation style
_NARRATIVE_VERB = re.compile(r"\s*(?:show|shows|showed|find|finds|found|argue|argues|argued|document|documents|"
                             r"demonstrate|demonstrates|report|reports|estimate|estimates|propose|proposes|suggest|"
                             r"suggests|study|studies|develop|develops|examine|examines)\b")


@register("FMT-09")
def citation_style(pm, ctx):
    if input_format(pm) != "latex":
        note_coverage(ctx, "FMT-09", "only 'et al.' spelling is checked by script for non-LaTeX input; citation "
                                     "commands exist only in LaTeX source")
        yield from _et_al(pm, ctx)
        return
    natbib_loaded = "natbib" in (pm.metadata.get("packages") or [])
    steps = ["Read the citation commands of every block (raw LaTeX) and their rendered text."]
    commands = Counter()
    for b in pm.blocks:
        for c in b.citations:
            commands[c.command.lower()] += 1
    natbib = sum(n for k, n in commands.items() if k in ("citep", "citet", "citealt", "citealp", "citeauthor", "citeyear"))
    plain = commands.get("cite", 0)
    # instances per rule: (block, citation, raw text, fix original, fix replacement)
    found = defaultdict(list)
    if plain and natbib:
        for b in pm.blocks:
            for c in b.citations:
                if c.command.lower() == "cite":
                    found["mix"].append((b, c, c.raw, c.raw, c.raw.replace("\\cite{", "\\citep{", 1)))
    for b in pm.blocks:
        raw = b.raw or ""
        if not raw or not b.citations:
            continue
        by_raw = defaultdict(list)
        for c in b.citations:
            by_raw[c.raw].append(c)
        # sh:c:001 a space before the citation
        for m in re.finditer(r"([A-Za-z0-9)\]])(\\(?:cite[a-z]*|parencite|textcite)\*?(?:\[[^\]]*\])*\{[^}]*\})", raw):
            cmd_raw = m.group(2)
            if cmd_raw.startswith(("\\citeyear", "\\citealp", "\\citealt", "\\citeauthor")) or not by_raw.get(cmd_raw):
                continue
            found["space_before"].append((b, by_raw[cmd_raw][0], m.group(0), m.group(0), f"{m.group(1)}~{cmd_raw}"))
        # sh:c:002 no space between the citation and punctuation after it
        for m in re.finditer(r"(\\(?:cite[a-z]*|parencite|textcite)\*?(?:\[[^\]]*\])*\{[^}]*\})([ \t]+)([.,;:])", raw):
            if by_raw.get(m.group(1)):
                found["space_after"].append((b, by_raw[m.group(1)][0], m.group(0), m.group(0), m.group(1) + m.group(3)))
        # sh:c:noin: 'in \citep{x}' reads 'in (Smith, 2000)'; with a numeric style 'in \cite{x}' reads 'in [3]'
        for m in re.finditer(r"\b(in|from|by)\s*~?\s*(\\(?:citep|parencite|cite)\*?(?:\[[^\]]*\])*\{[^}]*\})", raw, re.I):
            if m.group(2).startswith("\\cite{") and (natbib_loaded or natbib):
                continue  # with natbib, \cite is textual: 'in Smith (2000)' is fine
            if by_raw.get(m.group(2)):
                found["noin"].append((b, by_raw[m.group(2)][0], m.group(0), m.group(2),
                                      m.group(2).replace("\\citep", "\\citet", 1).replace("\\parencite", "\\textcite", 1)))
        # sh:c:mul: several citation commands in a row
        for m in re.finditer(r"(\\(cite[pt]?|parencite)\*?\{[^}]*\})\s*[,;]?\s*(\\\2\*?\{[^}]*\})", raw):
            if by_raw.get(m.group(1)):
                keys = re.findall(r"\{([^}]*)\}", m.group(1) + m.group(3))
                found["mul"].append((b, by_raw[m.group(1)][0], m.group(0), m.group(0),
                                     f"\\{m.group(2)}{{{','.join(keys)}}}"))
        # a parenthetical citation used as the subject: '(Smith, 2000) show that'
        for c in b.citations:
            if c.command.lower() not in ("citep", "parencite", "autocite"):
                continue
            s0, _ = sentence_bounds(b, c.start)
            lead = b.text[s0:c.start]
            as_subject = not lead.strip() or re.search(r"(?:^|\s)(?:as|and|while|whereas|but|since)\s*$", lead, re.I)
            if as_subject and _NARRATIVE_VERB.match(b.text[c.end:c.end + 20]):
                found["subject"].append((b, c, c.raw, c.raw, c.raw.replace("\\citep", "\\citet", 1)
                                         .replace("\\parencite", "\\textcite", 1).replace("\\autocite", "\\textcite", 1)))
    rules = {
        "mix": ("\\cite mixed with \\citep and \\citet",
                f"The paper uses \\cite {plain} times and natbib's \\citep or \\citet {natbib} times. With natbib, \\cite "
                "prints a textual citation like \\citet, so parenthetical uses come out wrong.",
                "TeXtidote sh:c:mix", "The source uses \\citep for parenthetical and \\citet for textual citations, "
                                      "and no bare \\cite."),
        "space_before": ("No space before a citation",
                         "Citation commands follow a word or bracket with no space, so the rendered text runs into the "
                         "citation, as in 'effect(Smith, 2000)'.",
                         "TeXtidote sh:c:001", "Every citation is separated from the preceding word by a space or ~."),
        "space_after": ("Space between a citation and punctuation",
                        "A space separates the citation from the punctuation after it.",
                        "TeXtidote sh:c:002", "No space separates a citation from the punctuation after it."),
        "noin": ("Parenthetical citation used as part of the sentence",
                 "A parenthetical citation follows 'in', 'from' or 'by', so it reads as 'in (Smith, 2000)'. The sentence "
                 "should still read correctly if the citation were removed; use a textual citation instead.",
                 "TeXtidote sh:c:noin", "Citations that are part of the sentence are textual: 'in Smith (2000)'."),
        "mul": ("Several citation commands in a row",
                "Adjacent citation commands print separate lists where one command with several keys would print one.",
                "TeXtidote sh:c:mul", "Adjacent citations are combined into one command."),
        "subject": ("Parenthetical citation used as a sentence subject",
                    "A parenthetical citation is followed by a verb, as in '(Smith, 2000) show', so it should be a "
                    "textual citation: 'Smith (2000) show'.",
                    "parenthetical versus narrative use", "Citations that act as the subject of a sentence are textual."),
    }
    for rule, items in found.items():
        title, problem, source, resolved = rules[rule]
        b, c, raw_text, original, replacement = items[0]
        quote = quote_at(b, c.start, c.end, 3, 3)
        count = f" ({len(items)} instance{'s' if len(items) != 1 else ''})"
        yield ctx.finding(
            "FMT-09", title, "minor", problem + count, block=b, quote=quote,
            status="likely" if rule in ("noin", "subject") else "confirmed",
            confidence="medium" if rule in ("noin", "subject") else "high",
            related=[related(b2, quote_at(b2, c2.start, c2.end, 3, 3)) for b2, c2, *_ in items[1:6]],
            evidence=[Evidence(type="script_output", text="; ".join(it[2] for it in items[:8])[:600],
                               data={"script": SCRIPT, "rule": source, "count": len(items),
                                     "commands": dict(commands)})],
            trajectory=steps + [f"Applied the rule ({source}, reimplemented): {len(items)} instance(s); the first is at "
                                f"{b.anchor.label()}."],
            fix=Fix(action="replace", original=original, replacement=replacement,
                    detail="Apply the same change to every instance listed.", resolved_when=resolved),
            script=SCRIPT, extra={"rule": rule, "count": len(items)})
    yield from _et_al(pm, ctx)


def _et_al(pm, ctx):
    hits = []
    for b in prose(pm, BODY_KINDS + ("abstract",)):
        for m in re.finditer(r"\bet\.\s?al\b\.?|\bet al\b(?!\.)|\bet\s+all\b", b.text):
            hits.append((b, m))
    if not hits:
        return
    b, m = hits[0]
    quote = quote_at(b, m.start(), m.end(), 2, 2)
    yield ctx.finding(
        "FMT-09", "Malformed \"et al.\"", "minor",
        f"\"{m.group(0)}\" should be written \"et al.\" ({len(hits)} instance{'s' if len(hits) != 1 else ''}).",
        block=b, quote=quote, related=[related(b2, quote_at(b2, m2.start(), m2.end(), 2, 2)) for b2, m2 in hits[1:6]],
        evidence=[Evidence(type="quote", text=quote, block=b.id)],
        trajectory=["Searched the text for misspelled 'et al.'."],
        fix=Fix(action="replace", original=m.group(0), replacement="et al.",
                resolved_when="'et al.' is written with one period, after 'al'."),
        script=SCRIPT)


# =============================================================== FMT-10 typography and number format
_SUMMARY_ROW = re.compile(
    r"observations|^\s*n\s*$|^\s*n\b|number of|clusters|r-?squared|r2|r²|adj|mean|median|s\.?d\.?\b|std|"
    r"f-?stat|p-?value|controls?\b|fixed effects|\bfe\b|log likelihood|aic|bic|wald|kleibergen|cragg|first[- ]stage|"
    r"sample|period|level|weights?|baseline", re.I)
_CELL_NUM = re.compile(r"^\s*([(\[])?\s*[-−–+]?\$?\s*(\d{1,3}(?:,\d{3})*|\d*)\.(\d+)\s*%?\s*([)\]])?\s*[*†‡a-c]*\s*$")


def _cell_decimals(cell: str):
    m = _CELL_NUM.match(cell.replace("$", ""))
    if not m:
        return None
    kind = "se" if m.group(1) == "(" and m.group(4) == ")" else ("br" if m.group(1) == "[" else "est")
    return kind, len(m.group(3))


@register("FMT-10")
def typography(pm, ctx):
    fmt = input_format(pm)
    steps = ["Read table cells and the text of every paragraph, footnote, caption and list item."]

    # decimals within a table column
    for t in pm.tables:
        block = next((b for b in pm.blocks if b.kind == "table" and b.attrs.get("table_id") == t.id), None)
        if block is None or not t.rows:
            continue
        ncol = max(len(r) for r in t.rows)
        issues = []
        for j in range(1, ncol):
            est, se = [], []
            prev = None
            for i, row in enumerate(t.rows):
                cell = row[j] if j < len(row) else ""
                label = row[0] if row else ""
                d = _cell_decimals(cell)
                if label and _SUMMARY_ROW.search(label):
                    prev = None
                    continue
                if d is None:
                    prev = None
                    continue
                kind, dec = d
                if kind == "est":
                    est.append((i, cell, dec))
                    prev = (i, cell, dec)
                elif kind == "se":
                    se.append((i, cell, dec))
                    if prev and prev[0] == i - 1 and prev[2] != dec:
                        issues.append((row, j, f"the estimate {prev[1]} has {prev[2]} decimals but its standard error "
                                                 f"{cell} has {dec}", cell, prev[1]))
                    prev = None
            for group, what in ((est, "estimates"), (se, "standard errors")):
                if len(group) >= 3:
                    mode, n = Counter(d for _, _, d in group).most_common(1)[0]
                    odd = [g for g in group if g[2] != mode]
                    if len(odd) == 1 and n >= 2:
                        i, cell, dec = odd[0]
                        issues.append((t.rows[i], j, f"column {j} shows its {what} with {mode} decimals, but {cell} "
                                                     f"has {dec}", cell, None))
        if issues:
            row, j, what, cell, other = issues[0]
            lines = block.text.split("\n")
            quote = next((ln for ln in lines if (other or cell) in ln), None) or cell
            pair = any(it[4] for it in issues)
            name = f"Table {t.number}" if t.number else "A table"
            yield ctx.finding(
                "FMT-10", "Inconsistent decimals in a table column", "minor",
                f"In {name.lower() if not t.number else name}: " + "; ".join(it[2] for it in issues[:6])
                + (f"; and {len(issues) - 6} more" if len(issues) > 6 else "") + ".",
                block=block, quote=quote, status="confirmed" if pair else "likely",
                confidence="high" if pair else "medium",
                evidence=[Evidence(type="computed_result", text="decimal places by cell",
                                   data={"formula": "count digits after the decimal point",
                                         "inputs": {"cells": [it[3] for it in issues[:12]]},
                                         "output": [it[2] for it in issues[:12]]})],
                trajectory=steps + [f"Counted decimal places per column in {name}, skipping summary rows such as "
                                    "observations, means and R-squared, and compared each estimate with the standard "
                                    "error below it."],
                fix=Fix(action="investigate", detail="Report each column's estimates and standard errors to the same "
                                                     "number of decimals.",
                        resolved_when="Within each column, estimates share one precision and each standard error "
                                      "matches its estimate."),
                script=SCRIPT, extra={"table": t.id, "issues": len(issues)})

    texts = prose(pm, BODY_KINDS + ("abstract",))

    # ranges written with a hyphen
    ranges = []
    for b in texts:
        skip = span_list(b) + math_spans(b.text)
        for m in re.finditer(r"(?<![\w.,/-])(\d{1,4})-(\d{1,4})(?![\w/-]|[.,]\d)", b.text):
            if inside(m.start(), skip):
                continue
            a, c = m.group(1), m.group(2)
            before = b.text[max(0, m.start() - 14):m.start()].lower()
            if re.search(r"(?:no\.|number|protocol|id|#|isbn|issn|doi|grant|code|version|v\.)\s*$", before):
                continue
            ia, ic = int(a), int(c)
            year_abbrev = len(a) == 4 and len(c) == 2 and 1800 <= ia <= 2100 and ic > ia % 100
            if not (ic > ia or year_abbrev) or (len(a) == 4 and len(c) == 4 and not (1800 <= ia <= 2100 and 1800 <= ic <= 2100)):
                continue
            ranges.append((b, m))
    if ranges:
        b, m = ranges[0]
        quote = quote_at(b, m.start(), m.end(), 3, 2)
        yield ctx.finding(
            "FMT-10", "Number ranges written with a hyphen", "minor",
            f"{len(ranges)} number range(s), such as \"{m.group(0)}\", use a hyphen; ranges take an en dash "
            "(\"--\" in LaTeX).",
            block=b, quote=quote, related=[related(b2, quote_at(b2, m2.start(), m2.end(), 3, 2)) for b2, m2 in ranges[1:8]],
            evidence=[Evidence(type="script_output", text=", ".join(m2.group(0) for _, m2 in ranges[:20]),
                               data={"script": SCRIPT, "count": len(ranges)})],
            trajectory=steps + ["Searched the text outside math for digit-hyphen-digit ranges, skipping identifiers "
                                "such as protocol numbers."],
            fix=Fix(action="replace", original=m.group(0), replacement=f"{m.group(1)}--{m.group(2)}" if fmt == "latex"
                    else f"{m.group(1)}–{m.group(2)}", detail="Write every range with an en dash.",
                    resolved_when="Number ranges use an en dash."),
            script=SCRIPT, extra={"count": len(ranges)})

    # percent: '5 %' against '5%', and '%' against 'percent' in the text
    spaced, tight, word = [], [], []
    for b in texts:
        for m in re.finditer(r"\d\s+%", b.text):
            spaced.append((b, m))
        for m in re.finditer(r"\d%", b.text):
            tight.append((b, m))
        for m in re.finditer(r"\d\s*(?:percent|per cent)\b", b.text):
            word.append((b, m))
    if spaced and tight:
        minority, majority = (spaced, tight) if len(spaced) <= len(tight) else (tight, spaced)
        b, m = minority[0]
        quote = quote_at(b, m.start(), m.end(), 3, 2)
        yield ctx.finding(
            "FMT-10", "Inconsistent spacing before %", "minor",
            f"The paper writes percentages both with a space (\"5 %\", {len(spaced)} times) and without (\"5%\", "
            f"{len(tight)} times).",
            block=b, quote=quote, related=[related(b2, quote_at(b2, m2.start(), m2.end(), 3, 2)) for b2, m2 in minority[1:6]],
            evidence=[Evidence(type="script_output", text=f"with space: {len(spaced)}; without: {len(tight)}",
                               data={"script": SCRIPT})],
            trajectory=steps + ["Counted percentages written with and without a space."],
            fix=Fix(action="investigate", detail="Use one form throughout.",
                    resolved_when="All percentages use the same spacing."),
            script=SCRIPT)
    if len(word) >= 2 and len(spaced) + len(tight) >= 2:
        b, m = (word if len(word) <= len(spaced) + len(tight) else (spaced + tight))[0]
        quote = quote_at(b, m.start(), m.end(), 3, 2)
        yield ctx.finding(
            "FMT-10", "Both \"%\" and \"percent\" in the text", "minor",
            f"The text uses \"%\" {len(spaced) + len(tight)} times and \"percent\" {len(word)} times. Style guides "
            "such as the AEA's use \"percent\" in the text and \"%\" in tables.",
            block=b, quote=quote, status="confirmed",
            evidence=[Evidence(type="script_output", text=f"%: {len(spaced) + len(tight)}; percent: {len(word)}",
                               data={"script": SCRIPT})],
            trajectory=steps + ["Counted '%' and 'percent' after numbers in the text."],
            fix=Fix(action="investigate", detail="Pick one form for the text.",
                    resolved_when="The text uses one form for percentages."),
            script=SCRIPT)

    # LaTeX source: straight double quotes and text-mode minus signs
    if fmt == "latex":
        quotes_found, minus_found = [], []
        for b in texts:
            raw = b.raw or ""
            if not raw:
                continue
            outside_math = re.sub(r"\$[^$]*\$|\\\(.*?\\\)", lambda mm: " " * len(mm.group(0)), raw)
            for m in re.finditer(r"(?<![\\\w])\"(?=[A-Za-z])", outside_math):
                word_m = re.match(r"\"([A-Za-z][\w-]*)", outside_math[m.start():])
                if word_m:
                    target = "\"" + word_m.group(1)
                    pos = b.text.find(target)
                    if pos >= 0:
                        quotes_found.append((b, pos, pos + len(target)))
            text_math = math_spans(b.text)
            for m in re.finditer(r"(?:(?<=\s)|(?<=\())-(?=\d)", outside_math):
                num = re.match(r"-\d[\d.,]*\d|-\d", outside_math[m.start():]).group(0)
                hit = next((t for t in re.finditer(re.escape(num) + r"(?!\d)", b.text) if not inside(t.start(), text_math)),
                           None)
                if hit:
                    minus_found.append((b, hit.start(), hit.end()))
        if quotes_found:
            b, s, e = quotes_found[0]
            quote = quote_at(b, s, e, 2, 2)
            yield ctx.finding(
                "FMT-10", "Straight double quotes in LaTeX", "minor",
                f"{len(quotes_found)} quotation(s) open with a straight \" in the source, which LaTeX prints as a "
                "closing quote mark. Use `` and '' (or \\enquote).",
                block=b, quote=quote, related=[related(b2, quote_at(b2, s2, e2, 2, 2)) for b2, s2, e2 in quotes_found[1:6]],
                evidence=[Evidence(type="script_output", text=f"{len(quotes_found)} opening straight quotes",
                                   data={"script": SCRIPT})],
                trajectory=steps + ["Searched the LaTeX source of each block for straight double quotes outside math."],
                fix=Fix(action="investigate", detail="Open quotations with `` and close them with ''.",
                        resolved_when="The source has no straight double quotes in text."),
                script=SCRIPT)
        if minus_found:
            b, s, e = minus_found[0]
            quote = quote_at(b, s, e, 2, 2)
            yield ctx.finding(
                "FMT-10", "Hyphen used as a minus sign", "minor",
                f"{len(minus_found)} negative number(s) in running text, such as \"{b.text[s:e]}\", are typed with a "
                "hyphen outside math mode, which prints a hyphen rather than a minus sign.",
                block=b, quote=quote, related=[related(b2, quote_at(b2, s2, e2, 2, 2)) for b2, s2, e2 in minus_found[1:6]],
                evidence=[Evidence(type="script_output", text=", ".join(b2.text[s2:e2] for b2, s2, e2 in minus_found[:10]),
                                   data={"script": SCRIPT})],
                trajectory=steps + ["Searched the LaTeX source for negative numbers outside math mode."],
                fix=Fix(action="replace", original=b.text[s:e], replacement=f"${b.text[s:e]}$",
                        detail="Put negative numbers in math mode or use \\textminus.",
                        resolved_when="Negative numbers print with a minus sign."),
                script=SCRIPT)


# =============================================================== FMT-11 draft leftovers
_LEFTOVER = re.compile(
    r"\b(?:TODO|FIXME|TBD|TBA|XXX+)\b:?|\blorem ipsum\b"
    r"|\[(?:citation needed|cite|citation|refs?|references?|add (?:citation|reference|ref)|source\??|\?\?\?)\]"
    r"|\[insert (?!(?:table|figure|fig\.|exhibit|chart|graph|appendix table|appendix figure)\s+[A-Z]?\d+[a-z]?\s+(?:about\s+)?here\b)[^\]]{1,80}\]"
    r"|\[your (?:name|institution|affiliation|university)\]"
    r"|\b(?:Figure|Fig\.|Table|Section|Appendix|Equation|Eq\.)\s+(?:X{1,3}|\?\?\?)(?![\w)])"
    r"|\(\s*(?:cite|ref|citation)\s*\??\s*\)|\bxx+\s*%|\bN\s*=\s*xx+\b", re.I)
_CASED_LEFTOVER = re.compile(r"TODO|FIXME|TBD|TBA|XXX")
_DRAFT_MACRO = re.compile(
    r"\\(todo|todoi|missingfigure|fxnote|fxwarning|fxerror|fxfatal|fixme|marginpar|hl|added|deleted|replaced|st|"
    r"textst|sout|xout)\*?\s*(?:\[[^\]]*\]\s*)*\{|\\(?:textcolor|color|colorbox)\s*\{(red|blue|magenta|orange|green|"
    r"purple|cyan|violet|teal|yellow)\}")
_SENSITIVE = re.compile(
    r"\b(?:reviewers?|referees?|editors?|R[1-4](?=\s*(?::|asked|wants|said|says|comment|point|suggest|request))|"
    r"AE(?=\s*(?::|asked|wants|said|says))|ignore|don['’]?t tell|do not tell|secret|confidential|private|"
    r"internal only|fake|made[- ]up|fudge|cherry[- ]?pick|p-?hack|massag\w*|drop (?:the )?outliers?|embarrass\w*|"
    r"stupid|damn|crap|wtf|hate|annoying|sucks|lol|password|passwd|api[_ ]?key|insignificant results?|"
    r"not significant|doesn['’]?t replicate|weak results?)\b", re.I)


def _comment_notes(pm) -> tuple:
    latex = [n for n in pm.notes if n.kind in ("latex_comment", "latex_comment_block")]
    other = [n for n in pm.notes if n.kind not in ("latex_comment", "latex_comment_block")
             and re.search(r"comment|annot|sticky|note", n.kind, re.I) and "hidden" not in n.kind]
    return latex, other


def _sensitive_reasons(text: str, names: list, cited: list) -> list:
    reasons = []
    for m in _SENSITIVE.finditer(text):
        word = m.group(0).lower()
        if word not in reasons:
            reasons.append(word)
    low = text.lower()
    for n in names:
        if re.search(rf"\b{re.escape(n)}\b", low) and f"names {n.title()}" not in reasons:
            reasons.append(f"names {n.title()}")
    for n in cited:
        if re.search(rf"\b{re.escape(n)}\b", text) and f"names {n}" not in reasons:
            reasons.append(f"names {n}")
    if re.match(r"\s*[A-Z][a-z]+\s*:", text) or re.match(r"\s*[A-Z]{2,3}\s*:", text):
        reasons.append("addressed to a person")
    if _EMAIL.search(text):
        reasons.append("e-mail address")
    return reasons


@register("FMT-11")
def draft_leftovers(pm, ctx):
    fmt = input_format(pm)
    steps = ["Searched every text block for TODO, FIXME, TBD, XXX, 'lorem ipsum', placeholders such as 'Figure X' "
             "and '[citation needed]', and the LaTeX source for draft macros (\\todo, \\hl, colored text)."]
    tables_x = {str(t.number) for t in pm.tables} | {str(f.number) for f in pm.figures}
    for b in prose(pm, PROSE_KINDS + FRONT_KINDS + ("heading", "table")):
        refs = span_list(b, citations=False)
        for m in _LEFTOVER.finditer(b.text):
            token = m.group(0)
            word = re.match(r"[A-Za-z]+", token)
            if word and word.group(0).upper() in ("TODO", "FIXME", "TBD", "TBA") and not _CASED_LEFTOVER.match(token):
                continue  # lowercase 'tbd' or 'fixme' in prose is unlikely to be a marker; stay conservative
            if re.match(r"(?:Figure|Fig\.|Table|Section|Appendix|Equation|Eq\.)\s+X", token) and "X" in tables_x:
                continue
            if inside(m.start(), refs):
                continue
            s0, e0 = sentence_bounds(b, m.start())
            quote = window(b.text, m.start(), m.end(), 0, 10, bounds=(s0, e0)) or token
            if len(quote.split()) < 3:
                quote = quote_at(b, m.start(), m.end(), 4, 6)
            yield ctx.finding(
                "FMT-11", "Draft leftover in the text", "major",
                f"\"{token.strip()}\" is a draft marker or placeholder that would appear in the submitted paper.",
                block=b, quote=quote,
                evidence=[Evidence(type="quote", text=quote, block=b.id)],
                trajectory=steps + [f"Matched \"{token.strip()}\" at {b.anchor.label()}."],
                fix=Fix(action="delete", original=quote,
                        detail="Finish the task the marker stands for, then delete the marker.",
                        resolved_when="No draft markers or placeholders remain in the compiled paper."),
                script=SCRIPT, extra={"marker": token.strip()})
        raw = b.raw or ""
        if fmt == "latex" and raw:
            for m in _DRAFT_MACRO.finditer(raw):
                if m.group(1):
                    macro, arg_start = m.group(1), m.end()  # the pattern ends at the opening brace
                else:
                    cmd = re.match(r"\\(\w+)", m.group(0)).group(1)
                    macro = f"{cmd}{{{m.group(2)}}}"
                    k = m.end()
                    while k < len(raw) and raw[k] in " \t\n":
                        k += 1
                    arg_start = k + 1 if k < len(raw) and raw[k] == "{" else k
                depth, j = 1, arg_start
                while j < len(raw) and depth:
                    depth += {"{": 1, "}": -1}.get(raw[j], 0)
                    j += 1
                arg = re.sub(r"\\[a-zA-Z]+\*?|[{}$]", "", raw[arg_start:max(arg_start, j - 1)][:400]).strip()
                words = arg.split()
                quote = None
                if words:
                    probe = " ".join(words[:8])
                    span = find_quote(probe, b.text)
                    if span:
                        quote = b.text[span[0]:span[1]]
                yield ctx.finding(
                    "FMT-11", "Draft markup in the LaTeX source", "major" if macro in ("todo", "todoi", "missingfigure",
                                                                                     "fxnote", "fxwarning", "fxerror",
                                                                                     "fxfatal", "fixme", "marginpar")
                    else "minor",
                    f"The source uses \\{macro}, which marks a draft note, highlight or tracked edit"
                    + (f" (\"{' '.join(words[:12])}\")" if words else "") + ". It may print in the submitted PDF.",
                    block=b, quote=quote, status="confirmed" if m.group(1) else "likely",
                    confidence="high" if m.group(1) else "medium",
                    evidence=[Evidence(type="script_output", text=raw[m.start():min(len(raw), j)][:300],
                                       data={"script": SCRIPT, "file": b.anchor.label()})],
                    trajectory=steps + [f"Found \\{macro} in the source at {b.anchor.label()}."],
                    fix=Fix(action="delete", detail=f"Resolve and remove the \\{macro} markup before submission.",
                            resolved_when="The source has no draft notes, highlights or tracked-edit macros."),
                    script=SCRIPT, extra={"macro": macro})

    latex_notes, other_notes = _comment_notes(pm)
    names = author_names(pm)
    cited = sorted({a.get("family") for r in pm.references for a in (r.fields.get("authors") or [])
                    if isinstance(a, dict) and a.get("family") and len(a.get("family")) > 3})
    if latex_notes and fmt == "latex":
        rows = []
        for n in latex_notes:
            rows.append((n, _sensitive_reasons(n.text, names, cited)))
        sensitive = [(n, r) for n, r in rows if r]
        ordered = sensitive + [(n, r) for n, r in rows if not r]
        first_note = ordered[0][0]
        listing = "; ".join(f"{n.anchor.label()}: {' '.join(n.text.split())[:80]}"
                            + (f" [{', '.join(r)}]" if r else "") for n, r in ordered[:8])
        blocks_n = sum(1 for n in latex_notes if n.kind == "latex_comment_block")
        f = ctx.finding(
            "FMT-11", "LaTeX comments would ship with an arXiv source upload",
            "major" if sensitive else "suggestion",
            f"The source holds {len(latex_notes)} comment{'s' if len(latex_notes) != 1 else ''}"
            + (f", including {blocks_n} \\iffalse or comment block{'s' if blocks_n != 1 else ''}" if blocks_n else "")
            + ". arXiv publishes the LaTeX source, comments included"
            + ((f", and {'it looks' if len(latex_notes) == 1 else f'{len(sensitive)} of them look'} sensitive: {listing}.")
               if sensitive else f": {listing}.")
            + " arxiv-latex-cleaner, for example, strips comments before upload; this check only reports them.",
            status="confirmed", confidence="high" if sensitive else "medium",
            evidence=[Evidence(type="note", text=n.text[:500],
                               data={"location": n.anchor.label(), "kind": n.kind, "sensitive": r})
                      for n, r in ordered[:20]],
            trajectory=["Listed the comments the LaTeX reader recorded (% comments, \\iffalse blocks and comment "
                        "environments).",
                        "Flagged comments that mention reviewers, editors, 'ignore', secrecy, data manipulation, "
                        "the authors or cited authors by name, or an e-mail address."],
            fix=Fix(action="delete",
                    detail="Remove comments from the files you upload (arxiv-latex-cleaner does this on a copy); at "
                           "least delete the sensitive ones listed here.",
                    resolved_when="The uploaded source has no comments, or none of the remaining ones is sensitive."),
            script=SCRIPT, extra={"count": len(latex_notes), "sensitive": len(sensitive)})
        yield add_location(f, first_note.anchor)
    if other_notes and fmt == "docx":
        note_coverage(ctx, "FMT-11", f"{len(other_notes)} Word comment(s) are reported under FMT-14")
        other_notes = []
    if other_notes:
        first_note = other_notes[0]
        listing = "; ".join(f"{n.anchor.label()}: {' '.join(n.text.split())[:80]}"
                            + (f" (by {n.author})" if n.author else "") for n in other_notes[:8])
        f = ctx.finding(
            "FMT-11", "Comments left in the file", "major",
            f"The file carries {len(other_notes)} {'comment or annotation' if len(other_notes) == 1 else 'comments or annotations'} "
            f"that anyone who opens it can read: {listing}.",
            status="confirmed",
            evidence=[Evidence(type="note", text=n.text[:500], data={"location": n.anchor.label(), "kind": n.kind,
                                                                     "author": n.author}) for n in other_notes[:20]],
            trajectory=["Listed the comments and annotations the reader recorded in the file."],
            fix=Fix(action="delete", detail="Delete the comments before submission.",
                    resolved_when="The submitted file has no comments or annotations."),
            script=SCRIPT, extra={"count": len(other_notes)})
        yield add_location(f, first_note.anchor)


# =============================================================== FMT-12 AI assistant leftovers
_AI_LEFTOVER = re.compile(
    r"\bas an AI (?:language )?model\b|\bas an AI assistant\b|\bas a large language model\b"
    r"|\bI(?:['’]m| am) (?:sorry|unable|not able)\b[^.]{0,60}\b(?:assist|help|provide|comply|access)"
    r"|\bI cannot (?:assist|help|provide|browse|access)\b|\b(?:certainly|sure|absolutely)[,!]\s+here(?:['’]s| is| are)\b"
    r"|\bhere(?:['’]s| is) (?:a|the|an|your) (?:revised|rewritten|improved|polished|edited|updated|shortened|condensed|"
    r"draft|possible) (?:version|draft|paragraph|text|abstract|introduction|section)\b"
    r"|\bregenerate response\b|\bI hope this helps\b|\blet me know if you(?:['’]d| would)? (?:like|want|need)\b"
    r"|\bas of my (?:last )?(?:knowledge|training) (?:cutoff|cut-off|update)\b|\bmy knowledge cut-?off\b"
    r"|\bin this revised version\b|\bI have (?:revised|rewritten|polished) (?:the|your)\b", re.I)


_CONVERSATIONAL = re.compile(r"(?:I(?:['’]m| am)|I cannot|I hope|let me know|sure|certainly|absolutely)", re.I)
_MATERIALS = re.compile(r"\binstructions?\b|\bquestionnaires?\b|\bsurveys?\b|\bscreens?\b|\bscreenshots?\b|"
                        r"\bscripts?\b|\bprotocols?\b|\bmaterials?\b|\bconsent\b", re.I)


@register("FMT-12")
def ai_leftovers(pm, ctx):
    steps = ["Searched every text block for phrases from chat assistants' replies, such as 'As an AI language "
             "model', 'Certainly, here is' and 'Regenerate response'. Placeholders such as '[insert citation]' are "
             "reported as draft leftovers (FMT-11), and placement markers such as '[Insert Table 1 here]' are normal "
             "in submission manuscripts."]
    for b in prose(pm, PROSE_KINDS + FRONT_KINDS + ("heading",)):
        materials = any(_MATERIALS.search(s) for s in b.section or [])
        for m in _AI_LEFTOVER.finditer(b.text):
            if materials and _CONVERSATIONAL.match(m.group(0)):
                continue  # an experimenter's script may say 'let me know if you need help'
            quote = quote_at(b, m.start(), m.end(), 3, 8)
            quoted = bool(re.search(r"[\"“'‘]\s*$", b.text[max(0, m.start() - 3):m.start()]))
            yield ctx.finding(
                "FMT-12", "Leftover AI assistant text", "critical",
                f"\"{m.group(0)}\" is wording from a chat assistant's reply, not part of the paper's argument."
                + (" It is inside quotation marks, so it may be an example; check." if quoted else ""),
                block=b, quote=quote, status="needs_human" if quoted else "confirmed",
                confidence="medium" if quoted else "high",
                evidence=[Evidence(type="quote", text=quote, block=b.id)],
                trajectory=steps + [f"Matched \"{m.group(0)}\" at {b.anchor.label()}."],
                fix=Fix(action="delete", original=quote, detail="Remove the assistant's text and check the passage "
                                                                "around it for other generated wording.",
                        resolved_when="No chat-assistant phrases remain in the text."),
                script=SCRIPT, extra={"phrase": m.group(0)})


# =============================================================== FMT-13 LaTeX build log
_LOG_RULES = [
    ("undefined citations", re.compile(r"(?:LaTeX|Package natbib|Package biblatex) Warning: Citation [`'\"]?([^'`\"\s]+)['\"]? "
                                       r"(?:on page \S+ )?undefined"), "major"),
    ("undefined references", re.compile(r"LaTeX Warning: Reference [`']([^']+)' on page \S+ undefined"), "major"),
    ("labels defined twice", re.compile(r"LaTeX Warning: Label [`']([^']+)' multiply defined"), "major"),
    ("missing files", re.compile(r"(?:LaTeX Warning|! LaTeX Error|Package \w+ Warning): File [`']([^']+)' not found"), "major"),
    ("LaTeX errors", re.compile(r"^! (?!LaTeX Error: File)(.+)$", re.M), "major"),
    ("font substitutions", re.compile(r"LaTeX Font Warning: Font shape [`']([^']+)' (?:undefined|in size)"), "minor"),
    ("rerun requests", re.compile(r"(Rerun to get [^.]+|Label\(s\) may have changed)"), "minor"),
    ("empty bibliography", re.compile(r"(Empty [`']thebibliography' environment)"), "major"),
]
_OVERFULL = re.compile(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt too wide\) (?:in paragraph|detected) at lines? (\d+)(?:--(\d+))?")


def _log_line(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:end if end >= 0 else len(text)].strip()


def _unwrap_log(text: str) -> str:
    lines = text.splitlines()
    out, buf = [], ""
    for line in lines:
        buf += line
        if len(line) != 79:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return "\n".join(out)


@register("FMT-13")
def build_log(pm, ctx):
    fmt = input_format(pm)
    if fmt != "latex":
        ctx.not_applicable("FMT-13", f"build logs exist only for LaTeX input; this input is {fmt}")
        return
    folder, main = paper_paths(pm)
    md = pm.metadata or {}
    log = None
    if main is not None:
        name = md.get("log_file")
        cand = (main.parent / name) if name else main.with_suffix(".log")
        log = cand if cand.exists() else None
    if log is None:
        ctx.skip("FMT-13", "no .log file next to the main .tex file; compile the paper and run the checks again to "
                           "check undefined references, overfull boxes, missing figures and font substitutions")
        return
    text = _unwrap_log(log.read_text(encoding="utf-8", errors="replace"))
    anchor = Anchor(file=str(log.relative_to(folder)) if folder and str(log).startswith(str(folder)) else log.name)
    steps = [f"Read the build log {anchor.label()} ({len(text.splitlines())} lines)."]
    for what, pat, sev in _LOG_RULES:
        hits = [m for m in pat.finditer(text)]
        if not hits:
            continue
        items = []
        for m in hits:
            item = " ".join(m.group(1).split())
            if item not in items:
                items.append(item)
        lines = [_log_line(text, m.start()) for m in hits[:8]]
        f = ctx.finding(
            "FMT-13", f"Build log: {what}", sev,
            f"The LaTeX log reports {len(hits)} {what}: {', '.join(items[:10])}" + (" ..." if len(items) > 10 else "") + ".",
            status="confirmed",
            evidence=[Evidence(type="script_output", text="\n".join(lines), data={"script": SCRIPT, "log": anchor.label(),
                                                                                 "count": len(hits)})],
            trajectory=steps + [f"Matched {len(hits)} log line(s) for {what}."],
            fix=Fix(action="investigate", detail="Fix the cause in the source, then recompile until the log is clean.",
                    resolved_when=f"A fresh build log reports no {what}."),
            script=SCRIPT, extra={"items": items[:30]})
        yield add_location(f, anchor)
    boxes = [m for m in _OVERFULL.finditer(text) if float(m.group(1)) > 2.0]
    if boxes:
        worst = max(boxes, key=lambda m: float(m.group(1)))
        f = ctx.finding(
            "FMT-13", "Build log: text runs into the margin", "minor",
            f"The log reports {len(boxes)} overfull line(s) wider than 2pt; the worst is {worst.group(1)}pt at source "
            f"line {worst.group(2)}. Such lines stick out into the margin.",
            status="confirmed",
            evidence=[Evidence(type="script_output", text="\n".join(m.group(0) for m in boxes[:10]),
                               data={"script": SCRIPT, "count": len(boxes)})],
            trajectory=steps + ["Listed overfull \\hbox warnings wider than 2pt."],
            fix=Fix(action="investigate", detail="Rephrase, allow hyphenation, or break long URLs and formulas at those lines.",
                    resolved_when="The log reports no overfull boxes wider than 2pt."),
            script=SCRIPT, extra={"count": len(boxes)})
        yield add_location(f, anchor)
    # stale .bbl
    bbl_name = md.get("bbl_file")
    bbl = (main.parent / bbl_name) if (main is not None and bbl_name) else None
    if bbl is not None and bbl.exists():
        bibs = [folder / (b if b.endswith(".bib") else b + ".bib") for b in md.get("bib_files") or []] if folder else []
        newer = [p for p in bibs if p.exists() and p.stat().st_mtime > bbl.stat().st_mtime]
        bbl_keys = set(re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", bbl.read_text(encoding="utf-8", errors="replace")))
        cited = {k for b in pm.blocks for c in b.citations for k in c.keys}
        missing = sorted(k for k in cited if k not in bbl_keys and pm.reference(k) is not None)
        if newer or missing:
            f = ctx.finding(
                "FMT-13", "Stale .bbl file", "minor",
                f"The bibliography file {bbl.name} is out of date"
                + (f": {', '.join(p.name for p in newer)} changed after it was built" if newer else "")
                + (f"; it lacks cited keys {', '.join(missing[:8])}" if missing else "")
                + ". arXiv and some journals compile with the uploaded .bbl.", status="confirmed",
                evidence=[Evidence(type="script_output", text=f"missing keys: {missing[:20]}; newer bib files: "
                                                              f"{[p.name for p in newer]}", data={"script": SCRIPT})],
                trajectory=steps + ["Compared the .bbl with the .bib files and the cited keys."],
                fix=Fix(action="investigate", detail="Rerun BibTeX or Biber and LaTeX.",
                        resolved_when="The .bbl is newer than every .bib file and contains every cited key."),
                script=SCRIPT)
            yield add_location(f, Anchor(file=bbl.name))


# =============================================================== FMT-14 Word hygiene
def _note_class(kind: str) -> Optional[str]:
    k = kind.lower()
    if "hidden" in k or "vanish" in k:
        return "hidden text"
    if "comment" in k and "latex" not in k:
        return "comments"
    if re.search(r"insert|ins\b|delet|del\b|tracked|revision|move|pprchange|rprchange|format_change|change", k):
        return "tracked changes"
    if "field" in k and re.search(r"stale|dirty|toc|ref", k):
        return "stale fields"
    return None


def _docx_counts(path: Path) -> dict:
    counts = {}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            doc = z.read("word/document.xml").decode("utf-8", errors="replace") if "word/document.xml" in names else ""
            counts["tracked changes"] = len(re.findall(r"<w:(?:ins|del|moveFrom|moveTo|pPrChange|rPrChange)\b", doc))
            counts["hidden text"] = len(re.findall(r"<w:vanish\b(?![^>]*w:val=\"(?:0|false)\")", doc))
            com = z.read("word/comments.xml").decode("utf-8", errors="replace") if "word/comments.xml" in names else ""
            counts["comments"] = len(re.findall(r"<w:comment\b", com))
            counts["stale fields"] = len(re.findall(r"w:dirty=\"(?:1|true)\"", doc))
    except (OSError, zipfile.BadZipFile, KeyError):
        return {}
    return counts


@register("FMT-14")
def word_hygiene(pm, ctx):
    fmt = input_format(pm)
    if fmt != "docx":
        ctx.not_applicable("FMT-14", f"Word hygiene applies to .docx input; this input is {fmt}")
        return
    md = pm.metadata or {}
    groups = defaultdict(list)
    for n in pm.notes:
        cls = _note_class(n.kind)
        if cls:
            groups[cls].append(n)
    path = Path(str((pm.source or {}).get("path") or ""))
    raw_counts = _docx_counts(path) if path.suffix.lower() in (".docx", ".docm") and path.exists() else {}
    steps = [f"Read {len(pm.notes)} notes (comments, tracked changes, hidden text) from the paper map"
             + (f" and counted the same elements in the raw XML of {path.name}" if raw_counts else "") + "."]
    sev = {"tracked changes": "major", "comments": "major", "hidden text": "major", "stale fields": "minor"}
    nouns = {"tracked changes": ("tracked change", "tracked changes"), "comments": ("comment", "comments"),
             "hidden text": ("hidden-text passage", "hidden-text passages"), "stale fields": ("stale field", "stale fields")}
    names = author_names(pm)
    cited = sorted({a.get("family") for r in pm.references for a in (r.fields.get("authors") or [])
                    if isinstance(a, dict) and a.get("family") and len(a.get("family")) > 3})
    for cls in ("tracked changes", "comments", "hidden text", "stale fields"):
        notes = groups.get(cls, [])
        n_raw = raw_counts.get(cls, 0)
        if not notes and not n_raw:
            continue
        count = max(len(notes), n_raw)
        authors = sorted({n.author for n in notes if n.author})
        sensitive = [(n, _sensitive_reasons(n.text, names, cited)) for n in notes] if cls == "comments" else []
        sensitive = [(n, r) for n, r in sensitive if r]
        ordered = [n for n, _ in sensitive] + [n for n in notes if all(n is not m for m, _ in sensitive)]
        sample = "; ".join(f"{n.anchor.label()}: {' '.join(n.text.split())[:60].rstrip(' .')}" for n in ordered[:5])
        word = nouns[cls][0] if count == 1 else nouns[cls][1]
        extra_text = " Hidden text is also reported under FMT-18." if cls == "hidden text" else ""
        if sensitive:
            extra_text += (f" {len(sensitive)} of the comments look sensitive ("
                           + "; ".join(f"{', '.join(r)}" for _, r in sensitive[:3]) + ").")
        f = ctx.finding(
            "FMT-14", f"Word file contains {cls}", sev[cls],
            f"The document contains {count} {word}" + (f" by {', '.join(authors)}" if authors else "")
            + (f": {sample}" if sample else "") + f". They travel with the file to editors and reviewers.{extra_text}",
            status="confirmed",
            evidence=[Evidence(type="note", text=n.text[:300], data={"location": n.anchor.label(), "kind": n.kind,
                                                                     "author": n.author, "date": n.date})
                      for n in ordered[:15]]
            + ([Evidence(type="script_output", text=f"{n_raw} elements in the raw XML", data={"script": SCRIPT})]
               if n_raw else []),
            trajectory=steps + [f"{cls}: {len(notes)} in the paper map, {n_raw} in the raw XML."],
            fix=Fix(action="investigate",
                    detail={"tracked changes": "Accept or reject all changes (Review > Accept All) and turn off tracking.",
                            "comments": "Delete all comments (Review > Delete All Comments).",
                            "hidden text": "Show hidden text (File > Options > Display) and delete or unhide it.",
                            "stale fields": "Update all fields (select all, F9) before saving."}[cls],
                    resolved_when=f"The saved .docx has no {cls}."),
            script=SCRIPT, extra={"count": count, "sensitive": len(sensitive)})
        add_location(f, ordered[0].anchor if ordered else Anchor(file=path.name))
        yield f
    if md.get("track_revisions"):
        yield add_location(ctx.finding(
            "FMT-14", "Track Changes is still switched on", "minor",
            "Track Changes is switched on in the document settings, so any further edit, including an editor's, is "
            "recorded with the editor's name, and reviewers may see the markup.", status="confirmed",
            evidence=[Evidence(type="script_output", text="w:trackRevisions in word/settings.xml",
                               data={"script": "docx reader", "metadata": "track_revisions"})],
            trajectory=steps + ["Read the Track Changes setting the Word reader recorded."],
            fix=Fix(action="investigate", detail="Turn off Track Changes (Review > Track Changes) after accepting or "
                                                 "rejecting all changes.",
                    resolved_when="The saved .docx has Track Changes switched off."),
            script=SCRIPT, extra={"metadata": ["track_revisions"]}), Anchor(file=path.name))
    stale = md.get("stale_fields") or []
    if stale:
        sample = "; ".join(f"paragraph {s.get('paragraph')}: {s.get('field')} shows \"{s.get('shown')}\""
                           + (f", expected \"{s.get('expected')}\"" if s.get("expected") else "")
                           + (f" ({s.get('reason')})" if s.get("reason") else "")
                           for s in stale[:5] if isinstance(s, dict))
        blk = next((pm.block(s.get("block")) for s in stale if isinstance(s, dict) and s.get("block")
                    and pm.block(s.get("block")) is not None), None)
        f = ctx.finding(
            "FMT-14", "Word fields out of date", "minor",
            f"{len(stale)} field{'s' if len(stale) != 1 else ''} show{'' if len(stale) != 1 else 's'} text that differs "
            f"from what {'they' if len(stale) != 1 else 'it'} would display when updated ({sample}).",
            block=blk, status="confirmed",
            evidence=[Evidence(type="script_output", text=str(s)[:300], data={"script": "docx reader"})
                      for s in stale[:10]],
            trajectory=steps + ["Read the stale fields the Word reader recorded (cross-references and citation fields "
                                "whose shown text differs from their target)."],
            fix=Fix(action="investigate", detail="Update all fields (select all, F9) and check citations edited by hand.",
                    resolved_when="Every field shows what it would show after an update."),
            script=SCRIPT, extra={"count": len(stale), "metadata": ["stale_fields"]})
        if blk is None:
            add_location(f, Anchor(file=path.name))
        yield f
    meta = [(k, v) for k, v in _metadata_authors(pm)]
    if meta and review_type(ctx)[0] == "double_anonymous":
        note_coverage(ctx, "FMT-14", "the author fields in the document properties are reported under FMT-02, "
                                     "because the venue reviews anonymously")
    elif meta:
        listing = "; ".join(f"{k} = {v}" for k, v in meta)
        f = ctx.finding(
            "FMT-14", "Author recorded in the document properties", "minor",
            f"The document properties name people or institutions ({listing}). They travel with the file; under "
            "double-anonymous review this is also an anonymity problem (FMT-02).", status="confirmed",
            evidence=[Evidence(type="script_output", text=listing, data={"script": SCRIPT})],
            trajectory=steps + ["Read the document's core and extended properties."],
            fix=Fix(action="investigate", detail="Use File > Info > Inspect Document to remove personal information.",
                    resolved_when="The document properties show no personal names or institutions."),
            script=SCRIPT, extra={"fields": dict(meta), "metadata": ["document_properties"]})
        yield add_location(f, Anchor(file=path.name))


# =============================================================== FMT-15 PDF technical compliance
_BASE14 = re.compile(r"^(?:[A-Z]{6}\+)?(?:Times|Helvetica|Courier|Symbol|ZapfDingbats)", re.I)
_PAGE_SIZES = {"US Letter": (612, 792), "A4": (595.28, 841.89), "US Legal": (612, 1008)}


def _meta_first(md: dict, *keys):
    for k in keys:
        cur = md
        for part in k.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur not in (None, "", [], {}):
            return cur
    return None


def _font_embedded(font) -> bool:
    try:
        subtype = str(font.get("/Subtype"))
        if subtype == "/Type3":
            return True
        desc = font.get("/FontDescriptor")
        if subtype == "/Type0":
            desc = font["/DescendantFonts"][0].get_object().get("/FontDescriptor")
        desc = desc.get_object() if desc is not None else None
        return bool(desc) and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3"))
    except Exception:
        return False


def pdf_facts(pm) -> dict:
    """Page count, page sizes, fonts and document info for PDF input: from the paper map's
    metadata when the reader recorded them, else read from the PDF with pypdf."""
    md = pm.metadata or {}
    facts = {
        "page_count": _meta_first(md, "page_count", "pages", "n_pages", "num_pages", "pdf.page_count"),
        "page_sizes": _meta_first(md, "page_sizes", "page_size", "pdf.page_sizes"),
        "fonts": _meta_first(md, "fonts", "pdf_fonts", "pdf.fonts"),
        "info": _meta_first(md, "pdf_info", "document_info", "info", "pdf.info"),
        "from": "paper map metadata",
    }
    if isinstance(facts["page_count"], list):
        facts["page_count"] = len(facts["page_count"])
    path = Path(str((pm.source or {}).get("path") or ""))
    need = facts["page_count"] is None or facts["fonts"] is None or facts["page_sizes"] is None
    if need and input_format(pm) == "pdf" and path.suffix.lower() == ".pdf" and path.exists():
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            if facts["page_count"] is None:
                facts["page_count"] = len(reader.pages)
            if facts["page_sizes"] is None:
                facts["page_sizes"] = [[round(float(p.mediabox.width), 2), round(float(p.mediabox.height), 2)]
                                       for p in reader.pages]
            if facts["fonts"] is None:
                fonts = {}
                for i, page in enumerate(reader.pages, 1):
                    res = page.get("/Resources")
                    res = res.get_object() if res is not None else {}
                    fd = res.get("/Font") if res else None
                    fd = fd.get_object() if fd is not None else {}
                    for _, ref in (fd or {}).items():
                        font = ref.get_object()
                        name = str(font.get("/BaseFont") or font.get("/Name") or "unnamed").lstrip("/")
                        entry = fonts.setdefault(name, {"name": name, "type": str(font.get("/Subtype", "")).lstrip("/"),
                                                        "embedded": _font_embedded(font), "pages": []})
                        if len(entry["pages"]) < 20:
                            entry["pages"].append(i)
                facts["fonts"] = list(fonts.values())
            if facts["info"] is None and reader.metadata:
                facts["info"] = {str(k): str(v) for k, v in reader.metadata.items()}
            facts["from"] = "the PDF, read with pypdf" if facts["from"] == "paper map metadata" and need else facts["from"]
        except Exception as exc:  # unreadable or encrypted PDF
            facts["error"] = f"{type(exc).__name__}: {exc}"
    try:
        facts["file_size"] = path.stat().st_size if path.is_file() else None
    except OSError:
        facts["file_size"] = None
    return facts


def _sizes(value) -> list:
    out = []
    if isinstance(value, dict):
        value = [value]
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        value = [value]
    for v in value or []:
        if isinstance(v, dict):
            w, h = v.get("width") or v.get("w"), v.get("height") or v.get("h")
        elif isinstance(v, (list, tuple)) and len(v) >= 2:
            w, h = v[0], v[1]
        elif isinstance(v, str):
            m = re.match(r"\s*([\d.]+)\s*[x×]\s*([\d.]+)", v)
            w, h = (m.group(1), m.group(2)) if m else (None, None)
        else:
            w = h = None
        try:
            out.append((float(w), float(h)))
        except (TypeError, ValueError):
            continue
    return out


def _size_name(w: float, h: float) -> Optional[str]:
    for name, (sw, sh) in _PAGE_SIZES.items():
        if (abs(w - sw) <= 3 and abs(h - sh) <= 3) or (abs(w - sh) <= 3 and abs(h - sw) <= 3):
            return name
    return None


@register("FMT-15")
def pdf_compliance(pm, ctx):
    fmt = input_format(pm)
    if fmt != "pdf":
        ctx.not_applicable("FMT-15", f"PDF checks apply to PDF input; this input is {fmt}. Ingest the compiled PDF "
                                     "to check fonts and page size")
        return
    facts = pdf_facts(pm)
    fonts = facts.get("fonts") or []
    sizes = _sizes(facts.get("page_sizes"))
    if not fonts and not sizes:
        ctx.skip("FMT-15", "no font or page-size data in the paper map, and the PDF could not be read"
                           + (f" ({facts['error']})" if facts.get("error") else ""))
        return
    pdf_name = Path(str(pm.source.get("path", ""))).name
    anchor = Anchor(file=pdf_name)
    steps = [f"Read fonts and page sizes from {facts['from']}: {len(fonts)} fonts, {len(sizes)} pages."]
    norm_fonts = []
    for fnt in fonts:
        if isinstance(fnt, str):
            norm_fonts.append({"name": fnt, "type": "", "embedded": None})
        elif isinstance(fnt, dict):
            emb = fnt.get("embedded", fnt.get("emb"))
            if isinstance(emb, str):
                emb = emb.lower() in ("yes", "true", "1")
            norm_fonts.append({"name": str(fnt.get("name") or fnt.get("basefont") or "unnamed"),
                               "type": str(fnt.get("type") or fnt.get("subtype") or "").lstrip("/"),
                               "embedded": emb})
    not_emb = [f for f in norm_fonts if f["embedded"] is False and f["type"] != "Type3"]
    if not_emb:
        core = [f for f in not_emb if _BASE14.match(f["name"])]
        other = [f for f in not_emb if f not in core]
        f = ctx.finding(
            "FMT-15", "Fonts not embedded in the PDF", "major" if other else "minor",
            f"{len(not_emb)} font(s) are not embedded: {', '.join(x['name'] for x in not_emb[:10])}. Viewers and "
            "printers substitute other fonts, which can change spacing and symbols; many submission systems "
            "reject such PDFs.", status="confirmed",
            evidence=[Evidence(type="script_output", text="; ".join(f"{x['name']} ({x['type'] or '?'})" for x in not_emb[:20]),
                               data={"script": SCRIPT, "source": facts["from"]})],
            trajectory=steps + ["Checked each font for an embedded font file."],
            fix=Fix(action="investigate", detail="Embed all fonts when making the PDF (pdfLaTeX embeds by default; in "
                                                 "Word use 'Embed fonts in the file' or PDF/A export).",
                    resolved_when="Every font in the PDF is embedded."),
            script=SCRIPT, extra={"fonts": [x["name"] for x in not_emb]})
        yield add_location(f, anchor)
    type3 = [f for f in norm_fonts if f["type"] == "Type3"]
    if type3:
        f = ctx.finding(
            "FMT-15", "Type 3 fonts in the PDF", "minor",
            f"{len(type3)} Type 3 font(s) ({', '.join(x['name'] for x in type3[:8])}) are bitmap or procedure fonts that "
            "render poorly on screen and are refused by some journals.", status="confirmed",
            evidence=[Evidence(type="script_output", text=", ".join(x["name"] for x in type3), data={"script": SCRIPT})],
            trajectory=steps + ["Listed fonts of type Type3."],
            fix=Fix(action="investigate", detail="Usually caused by figures or old bitmap fonts; regenerate figures with "
                                                 "Type 1 or TrueType fonts (e.g. matplotlib pdf.fonttype 42).",
                    resolved_when="The PDF has no Type 3 fonts."),
            script=SCRIPT)
        yield add_location(f, anchor)
    if sizes:
        distinct = Counter((round(w), round(h)) for w, h in sizes)
        if len(distinct) > 1:
            (w0, h0), _ = distinct.most_common(1)[0]
            odd = [i for i, (w, h) in enumerate(sizes, 1) if (round(w), round(h)) != (w0, h0)]
            f = ctx.finding(
                "FMT-15", "Pages of different sizes", "minor",
                f"Most pages are {w0} x {h0} pt, but page(s) {', '.join(map(str, odd[:10]))} differ.", status="confirmed",
                evidence=[Evidence(type="script_output", text=str(dict(distinct)), data={"script": SCRIPT})],
                trajectory=steps + ["Compared the page sizes."],
                fix=Fix(action="investigate", detail="Produce every page at one paper size.",
                        resolved_when="All pages have the same size."),
                script=SCRIPT)
            yield add_location(f, Anchor(file=pdf_name, page=odd[0]))
        w, h = sizes[0]
        if _size_name(w, h) is None:
            f = ctx.finding(
                "FMT-15", "Unusual page size", "suggestion",
                f"The page size is {w:.0f} x {h:.0f} pt, which is neither US Letter nor A4.", status="confirmed",
                evidence=[Evidence(type="script_output", text=f"{w} x {h} pt", data={"script": SCRIPT})],
                trajectory=steps + ["Compared the page size with US Letter, A4 and Legal."],
                fix=Fix(action="investigate", detail="Use US Letter or A4 unless the journal asks otherwise.",
                        resolved_when="Pages are US Letter or A4."),
                script=SCRIPT)
            yield add_location(f, anchor)
    note_coverage(ctx, "FMT-15", f"fonts and page sizes from {facts['from']}; broken links are not checked")


# =============================================================== FMT-16 supplementary references
_SUPP = re.compile(
    r"\b(?P<supp>(?:Online|Supplementary|Supplemental|Web)\s+(?:Appendix|Appendices|Materials?|Information|Data))"
    r"(?:\s+(?P<supp_num>[A-Z](?:\.\d+)*|\d+)(?![\w]))?"
    r"|\b(?P<skind>Tables?|Figures?|Fig\.|Sections?|Equations?)\s+(?P<snum>S\d+)\b"
    r"|\bAppendix\s+(?P<akind>Tables?|Figures?)\s+(?P<anum>[A-Z]\.?\d+)\b"
    r"|\bAppendix\s+(?P<app>[A-Z])(?:\.\d+)*\b")


@register("FMT-16")
def supplementary_references(pm, ctx):
    objs = _objects(pm)
    supp_in_paper = any(b.kind == "heading" and re.search(r"online appendix|supplement|web appendix", b.text, re.I)
                        for b in pm.blocks)
    unresolved, missing = [], []
    for b in prose(pm, BODY_KINDS + ("abstract",)):
        refs = span_list(b, citations=False)
        for m in _SUPP.finditer(b.text):
            if inside(m.start(), refs) and not m.group("supp"):
                continue
            if _FOREIGN_AFTER.match(b.text[m.end():m.end() + 60]):
                continue
            if m.group("supp"):
                num = m.group("supp_num")
                if supp_in_paper and num and num not in objs["appendix"]:
                    missing.append((b, m, f"{m.group('supp')} {num}"))
                elif not supp_in_paper:
                    unresolved.append((b, m, m.group(0)))
            elif m.group("snum"):
                kind = _KIND_OF.get(m.group("skind").lower().rstrip("s") if m.group("skind").lower() not in _KIND_OF
                                    else m.group("skind").lower(), "table")
                num = m.group("snum")
                present = num in objs.get(kind, set())
                if present:
                    continue
                (missing if supp_in_paper else unresolved).append((b, m, f"{m.group('skind')} {num}"))
            elif m.group("anum"):
                kind = "table" if m.group("akind").lower().startswith("table") else "figure"
                num = m.group("anum").replace(".", "")
                if num in objs[kind]:
                    continue
                if objs["has_appendix"] and any(t.number and re.fullmatch(r"[A-Z]\d+", str(t.number))
                                                for t in (pm.tables if kind == "table" else pm.figures)):
                    missing.append((b, m, m.group(0)))
                elif not objs["has_appendix"]:
                    unresolved.append((b, m, m.group(0)))
            elif m.group("app"):
                if inside(m.start("app"), refs):
                    continue
                if not objs["has_appendix"]:
                    unresolved.append((b, m, m.group(0)))
    steps = ["Listed mentions of online or supplementary appendices, S-numbered tables and figures, and lettered "
             "appendix tables, and looked each up among the paper's headings, tables and figures."]
    for b, m, what in missing:
        quote = quote_at(b, m.start(), m.end(), 3, 4)
        yield ctx.finding(
            "FMT-16", "Supplementary reference points to nothing", "major",
            f"The text refers to {what}, but the supplementary material in this file has no such item.",
            block=b, quote=quote, status="likely", confidence="medium",
            evidence=[Evidence(type="quote", text=quote, block=b.id),
                      Evidence(type="checked_absence", text=what, data={"scope": "headings, tables and figures of the "
                                                                                 "supplement in this file",
                                                                        "terms": {what: 0}})],
            trajectory=steps + [f"{what} at {b.anchor.label()}: not found."],
            fix=Fix(action="investigate", detail="Correct the reference or add the missing item to the supplement.",
                    resolved_when=f"{what} exists in the supplement."),
            script=SCRIPT, extra={"item": what})
    if unresolved:
        b, m, what = unresolved[0]
        quote = quote_at(b, m.start(), m.end(), 3, 4)
        items = sorted({w for _, _, w in unresolved})
        yield ctx.finding(
            "FMT-16", "Supplementary material not included in the check", "minor",
            f"The paper refers to material that is not in the files checked: {', '.join(items[:12])}. Make sure the "
            "supplement you submit contains each of them under the same number.",
            block=b, quote=quote, status="needs_human", confidence="medium",
            related=[related(b2, quote_at(b2, m2.start(), m2.end(), 3, 4)) for b2, m2, _ in unresolved[1:8]],
            evidence=[Evidence(type="checked_absence", text=", ".join(items),
                               data={"scope": "the files given to the check", "terms": {i: 0 for i in items[:20]}})],
            trajectory=steps + ["The input has no online or supplementary appendix to compare with."],
            fix=Fix(action="investigate", detail="Check each item against the supplementary file, or give that file "
                                                 "to the check as well.",
                    resolved_when="Every supplementary item the paper mentions exists in the submitted supplement."),
            script=SCRIPT, extra={"items": items})


# =============================================================== FMT-18 hidden text and instructions to AI
_INJECTION = re.compile(
    r"\bignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier|preceding) (?:instructions|prompts?|directions)\b"
    r"|\bdisregard (?:all |any )?(?:the )?(?:previous|prior|above) (?:instructions|prompts?)\b"
    r"|\bgive (?:this|the) (?:paper|manuscript|submission|article|study) an? (?:positive|favou?rable|good|high|strong|"
    r"glowing) (?:review|rating|score|evaluation|assessment)\b"
    r"|\b(?:recommend|suggest) (?:accepting|acceptance of|to accept) (?:this|the) (?:paper|manuscript|submission)\b"
    r"|\bas an? (?:AI |LLM |language model )?reviewer,? you (?:must|should|will|are)\b"
    r"|\b(?:if|when) you are an? (?:AI|LLM|large language model|language model|AI assistant|automated reviewer)\b"
    r"|\b(?:for|to) (?:the )?(?:AI|LLM|language model)s? (?:reviewers?|readers?)\b"
    r"|\bdo not (?:mention|highlight|point out|report) (?:any )?(?:weaknesses|negatives|limitations|flaws)\b"
    r"|\brate this (?:paper|manuscript|submission) (?:highly|as excellent|10|ten|5|five)\b", re.I)


@register("FMT-18")
def hidden_instructions(pm, ctx):
    steps = ["Read the hidden-text notes and hidden blocks recorded by the reader (white text, hidden runs), and "
             "searched all text for instructions addressed to AI reviewers."]
    reported = set()
    hidden_notes = [n for n in pm.notes if "hidden" in n.kind.lower() or "white" in (n.detail or "").lower()
                    or "vanish" in n.kind.lower()]
    hidden_blocks = [b for b in pm.blocks if is_hidden(b)]
    items = []
    for b in hidden_blocks:
        note = next((n for n in hidden_notes if n.text and (find_quote(n.text[:200], b.text)
                                                            or find_quote(b.text[:200], n.text))), None)
        items.append((b, note))
    for n in hidden_notes:
        if not any(note is n for _, note in items):
            blk = next((b for b in pm.blocks if n.text and find_quote(n.text[:200], b.text)), None)
            items.append((blk, n))
    for b, n in items:
        text = (n.text if n is not None else b.text) or ""
        words = re.findall(r"[A-Za-z]{2,}", text)
        if len(words) < 3:
            continue  # white padding such as a hidden minus sign used to align a column
        injection = _INJECTION.search(text)
        how = (n.detail if n is not None and n.detail else (b.attrs.get("hidden") if b is not None else "hidden"))
        how = re.split(r"[:;]", str(how))[0].strip() or "hidden text"
        quote = None
        if b is not None:
            span = find_quote(text[:300], b.text) if text else None
            quote = b.text[span[0]:span[1]] if span else block_quote(b, 40)
        key = (b.id if b is not None else None, normalize(text)[:80])
        if key in reported:
            continue
        reported.add(key)
        problem = (f"The paper contains {how} that readers cannot see but text extraction and AI tools read: "
                   f"\"{' '.join(text.split())[:200]}\". "
                   + ("It is addressed to AI reviewers and asks for a favorable assessment, which journals treat as "
                      "manipulation of peer review." if injection else
                      "Hidden text in a submission looks like an attempt to influence automated screening."))
        f = ctx.finding(
            "FMT-18", "Hidden instruction to AI reviewers" if injection else "Hidden text", "critical" if injection else "major",
            problem, block=b, quote=quote, status="confirmed",
            evidence=([Evidence(type="quote", text=quote, block=b.id)] if quote else [])
            + ([Evidence(type="note", text=n.text[:500], data={"location": n.anchor.label(), "kind": n.kind,
                                                                "detail": n.detail})] if n is not None else []),
            trajectory=steps + [f"Hidden text at {(n.anchor if n is not None else b.anchor).label()} ({how})."]
            + ([f"Matched the instruction pattern \"{injection.group(0)}\"."] if injection else []),
            fix=Fix(action="delete", original=quote,
                    detail="Delete the hidden text from the source; the manuscript must contain only what readers see.",
                    resolved_when="The paper has no white, hidden or microscopic text, and nothing addressed to AI tools."),
            script=SCRIPT, extra={"hidden": how, "injection": bool(injection)})
        if b is None and n is not None:
            add_location(f, n.anchor)
        yield f
    # visible text addressed to AI reviewers
    for b in pm.blocks:
        if is_hidden(b) or b.kind in ("reference",) or not b.text:
            continue
        for m in _INJECTION.finditer(b.text):
            key = (b.id, normalize(b.text)[:80])
            if key in reported:
                continue
            reported.add(key)
            quote = quote_at(b, m.start(), m.end(), 4, 10)
            quoted = bool(re.search(r"[\"“'‘]\s*$", b.text[max(0, m.start() - 3):m.start()]))
            materials = any(_MATERIALS.search(s) for s in b.section or [])
            yield ctx.finding(
                "FMT-18", "Instruction addressed to AI reviewers", "minor" if materials else "critical",
                f"\"{m.group(0)}\" addresses AI tools or reviewers directly. Text that tries to steer an automated "
                "review is treated as manipulation of peer review."
                + (" It is inside quotation marks, so it may be an example under discussion; check." if quoted else "")
                + (" It sits in the study materials, so it may be a bot check shown to participants; check." if materials
                   else ""),
                block=b, quote=quote, status="needs_human" if quoted or materials else "confirmed",
                evidence=[Evidence(type="quote", text=quote, block=b.id)],
                trajectory=steps + [f"Matched \"{m.group(0)}\" at {b.anchor.label()}."],
                fix=Fix(action="delete", original=quote, detail="Remove the instruction.",
                        resolved_when="Nothing in the paper addresses AI reviewers."),
                script=SCRIPT, extra={"injection": True})
    # LaTeX tricks the reader does not mark: \phantom text and microscopic fonts
    if input_format(pm) == "latex":
        for b in pm.blocks:
            raw = b.raw or ""
            for m in re.finditer(r"\\phantom\s*\{([^{}]{12,})\}|\\fontsize\s*\{\s*0?\.\d+\s*(?:pt)?\s*\}", raw):
                inner = m.group(1) or raw[m.end():m.end() + 200]
                words = re.findall(r"[A-Za-z]{2,}", inner)
                if len(words) < 3:
                    continue
                yield ctx.finding(
                    "FMT-18", "Invisible text in the LaTeX source", "critical" if _INJECTION.search(inner) else "major",
                    f"The source hides text with {m.group(0)[:30]}...: \"{' '.join(inner.split())[:160]}\".",
                    block=b, quote=None, status="likely", confidence="medium",
                    evidence=[Evidence(type="script_output", text=raw[m.start():m.start() + 300],
                                       data={"script": SCRIPT, "location": b.anchor.label()})],
                    trajectory=steps + [f"Found invisible-text markup at {b.anchor.label()}."],
                    fix=Fix(action="delete", detail="Remove the invisible text.",
                            resolved_when="The source has no \\phantom text or microscopic fonts carrying words."),
                    script=SCRIPT)
