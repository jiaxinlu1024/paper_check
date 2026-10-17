"""Post-processing shared by the LaTeX, Word and PDF readers.

Every reader builds blocks, references, tables and figures, then calls
`finish(pm, work)`, which adds sentences, numbers, abbreviations and the
definitions slice, detects keyword and JEL lines, and writes:

    paper_map.json     the full map
    paper_text.md      every block with its id, kind, section and location; agents quote from this
    definitions.md     the definitions and notation slice given to every reading agent
"""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path

from ..model import Block, Definition, NumberMention, PaperMap, Sentence
from ..textutil import extract_numbers, split_sentences

SENTENCE_KINDS = {"abstract", "paragraph", "list_item", "footnote", "caption", "acknowledgment", "front_matter"}
_ABBR_DEF = re.compile(r"\b((?:[A-Z]?[a-z]+[\s-]+){0,6}[A-Z]?[a-z]+)\s*\(([A-Z][A-Za-z]*[A-Z]s?)\)")
_ABBR_USE = re.compile(r"\b([A-Z][A-Za-z]*[A-Z]s?)\b")
_NOT_ABBR = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "OK", "US", "UK", "EU", "USA",
             "JEL", "PDF", "URL", "DOI", "ID", "AM", "PM", "IT", "TV", "AI", "TODO", "FIXME", "TBD", "XXX", "NB",
             "PS", "OLS", "SE", "SD", "CI", "NA", "N/A"}
_DEF_CUES = re.compile(
    r"\b(denotes?|denoted by|is defined as|are defined as|we define|define[sd]?\b|refers? to|we call|"
    r"stands? for|is the (?:parameter|share|fraction|probability|rate|number|level|discount)|"
    r"captures?|measures?|where \$?\\?[a-zA-Z]+|let \$)", re.I)
_SYMBOL = re.compile(r"\$[^$]{1,40}\$|\\[a-zA-Z]+|[Ͱ-Ͽ]")


def assign_sentences(block: Block) -> None:
    if block.kind not in SENTENCE_KINDS or block.sentences:
        return
    for i, (s, e) in enumerate(split_sentences(block.text), 1):
        block.sentences.append(Sentence(id=f"{block.id}.s{i}", start=s, end=e))


def _sentence_of(block: Block, pos: int):
    for s in block.sentences:
        if s.start <= pos < s.end:
            return s.id
    return None


def extract_block_numbers(pm: PaperMap) -> None:
    pm.numbers = []
    for block in pm.blocks:
        if block.kind in ("reference", "equation", "heading"):
            continue
        skip = [(c.start, c.end) for c in block.citations] + [(r.start, r.end) for r in block.crossrefs]
        for n in extract_numbers(block.text, skip):
            pm.numbers.append(NumberMention(block=block.id, start=n["start"], end=n["end"], raw=n["raw"],
                                            value=n["value"], unit=n["unit"], decimals=n["decimals"],
                                            sentence=_sentence_of(block, n["start"])))


def find_abbreviations(pm: PaperMap) -> None:
    """Record each abbreviation's definitions and first use, with block ids and offsets.

    Entries: {abbr, expansion, defined_at: [{block, start}], first_use: {block, start}}.
    A use counts only outside the parenthesis that defines it."""
    defined: "OrderedDict[str, dict]" = OrderedDict()
    first_use: dict = {}
    order = pm.block_order()
    for block in pm.blocks:
        if block.kind in ("reference", "equation", "table"):
            continue
        def_spans = []
        for m in _ABBR_DEF.finditer(block.text):
            abbr, phrase = m.group(2), m.group(1)
            core = abbr.rstrip("s").upper()
            words = [w for w in re.split(r"[\s-]+", phrase) if w]
            initials = "".join(w[0] for w in words).upper()
            if abbr in _NOT_ABBR or not core or core[0] not in initials:
                continue
            expansion = " ".join(words[-len(core):]) if len(words) >= len(core) else phrase
            entry = defined.setdefault(abbr, {"abbr": abbr, "expansion": expansion, "defined_at": []})
            entry["defined_at"].append({"block": block.id, "start": m.start(2)})
            def_spans.append((m.start(2), m.end(2)))
        for m in _ABBR_USE.finditer(block.text):
            abbr = m.group(1)
            if abbr in _NOT_ABBR or len(abbr.rstrip("s")) < 2 or any(s0 <= m.start() < e0 for s0, e0 in def_spans):
                continue
            first_use.setdefault(abbr, {"block": block.id, "start": m.start()})
    pm.abbreviations = []
    def sort_key(a):
        u = first_use.get(a) or (defined.get(a, {}).get("defined_at") or [{}])[0]
        return (order.get(u.get("block"), 10**9), u.get("start", 0))
    for abbr in sorted(set(defined) | set(first_use), key=sort_key):
        entry = defined.get(abbr, {"abbr": abbr, "expansion": None, "defined_at": []})
        entry["first_use"] = first_use.get(abbr)
        pm.abbreviations.append(entry)


def find_definitions(pm: PaperMap) -> None:
    pm.definitions = []
    for block in pm.blocks:
        if block.kind not in ("paragraph", "footnote", "list_item", "abstract", "equation", "caption"):
            continue
        for s in block.sentences or [Sentence(id=f"{block.id}.s1", start=0, end=len(block.text))]:
            text = block.text[s.start:s.end]
            if not _DEF_CUES.search(text):
                continue
            symbols = _SYMBOL.findall(text)
            kind = "symbol" if symbols else "term"
            term = symbols[0] if symbols else ""
            pm.definitions.append(Definition(term=term, kind=kind, definition=text.strip(), block=block.id,
                                             anchor=block.anchor))


def detect_front_matter_lines(pm: PaperMap) -> None:
    """Mark paragraphs that are really keyword or JEL lines."""
    for block in pm.blocks[:80]:
        if block.kind != "paragraph":
            continue
        head = block.text.strip()[:40].lower()
        if re.match(r"(jel\b|jel codes?|jel classification)", head):
            block.kind = "jel"
        elif re.match(r"(keywords?|key words)\s*[:.—-]", head):
            block.kind = "keywords"


def write_text_dump(pm: PaperMap, path: Path) -> None:
    lines = [f"# Paper text: {pm.title}", "",
             "Each block starts with [id · kind · section · location]. Quote text exactly as it appears here.", ""]
    for b in pm.blocks:
        section = " > ".join(b.section[-2:]) if b.section else "front matter"
        lines.append(f"[{b.id} · {b.kind} · {section} · {b.anchor.label()}]")
        lines.append(b.text)
        lines.append("")
    if pm.references:
        lines += ["# Reference list", ""]
        for r in pm.references:
            lines.append(f"[{r.id}{' · ' + r.key if r.key else ''} · {r.anchor.label()}] {r.raw}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_definitions(pm: PaperMap, path: Path) -> None:
    lines = [f"# Definitions and notation: {pm.title}", "",
             "Sentences that define terms or symbols, and the abbreviations in the paper. "
             "Read this before judging any passage, so that terms are understood as the paper defines them.", ""]
    for d in pm.definitions:
        lines.append(f"- [{d.block}] {d.definition}")
    if pm.abbreviations:
        lines += ["", "## Abbreviations", ""]
        for a in pm.abbreviations:
            where = ", ".join(d["block"] for d in a.get("defined_at", [])) or "never defined"
            use = (a.get("first_use") or {}).get("block", "never used outside its definition")
            lines.append(f"- {a['abbr']}: {a.get('expansion') or '?'} (defined in {where}; first used in {use})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def finish(pm: PaperMap, work: Path) -> PaperMap:
    detect_front_matter_lines(pm)
    for block in pm.blocks:
        assign_sentences(block)
    extract_block_numbers(pm)
    find_abbreviations(pm)
    find_definitions(pm)
    work.mkdir(parents=True, exist_ok=True)
    pm.save(work / "paper_map.json")
    write_text_dump(pm, work / "paper_text.md")
    write_definitions(pm, work / "definitions.md")
    return pm
