"""Word reader: a .docx (or .docm) file into a PaperMap.

The reader works on the raw WordprocessingML with zipfile and lxml, so that it
sees what python-docx does not model: tracked changes, hidden and white text,
field codes, footnotes, endnotes, content controls and text boxes. It reads a
macro-enabled .docm and a package with broken relationships the same way.

Steps:
  1. Walk the main document in order. Every w:p becomes a paragraph record with
     its text (the current version: insertions kept, deletions dropped, field
     instructions dropped, field results kept), run formatting, footnote and
     comment marks, bookmarks, fields and images. Footnotes, endnotes, comments,
     text boxes, headers and footers are walked the same way as separate stories.
  2. Classify the paragraphs: title, authors, abstract, headings (heading styles,
     outline levels, or bold numbered lines such as "1 Introduction"), captions,
     equations, list items, table notes, the reference list and acknowledgments.
  3. Emit blocks in body order, each footnote right after the paragraph that
     references it, plus tables, figures, references, labels and notes.
  4. Resolve citations: reference-manager field codes (Zotero, Mendeley, EndNote,
     Word's own sources) give exact reference data; plain author-year citations
     are matched by family name and year. Cross-references ("Table 1", Word REF
     fields) are resolved against the tables, figures, sections and equations.

Paragraph numbers. `anchor.paragraph` counts every w:p of the main document in
document order, from 1, including empty paragraphs and the paragraphs inside
table cells and content controls, but not those in text boxes, notes, comments,
headers or footers. A table is anchored at its first cell paragraph. A footnote,
and a comment, tracked change or hidden text found inside one, is anchored at
the body paragraph that holds its reference mark; a text box at the paragraph
that holds the drawing.

Conventions that checks can rely on:
  - Notes: "comment" (detail: the commented passage; threads and resolved state
    in metadata["comments"]), "tracked_insertion" and "tracked_deletion" (detail
    "moved text", "table row" or "paragraph mark" where it applies),
    "tracked_format_change" (w:pPrChange, w:rPrChange) and "hidden_text" (detail
    "hidden text" for w:vanish, "white text", or "tiny text" for 2 pt or less).
    Hidden text stays in the block text; the block gets attrs["hidden"].
  - Reference keys are the first author's family name plus the printed year
    ("laibson1998"); a citation that matches no entry gets the same kind of key.
    Citation commands: "zotero", "mendeley", "endnote", "word" (field codes),
    "narrative", "parenthetical", "numeric" (plain text).
  - Labels: "table:1", "figure:2", "section:3", "appendix:A", "equation:1".
    Cross-reference commands: "REF" and "NOTEREF" (fields) and "text".
  - Metadata: document_properties, page (and sections when they differ), fonts,
    line_spacing, language, comments, fields, reference_manager,
    reference_manager_items, track_revisions, stale_fields, images,
    headers_footers, cited_keys_missing_from_bib, cited_items_missing_from_list,
    uncited_references, paragraph_count.
"""

from __future__ import annotations

import base64
import json
import posixpath
import re
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from typing import Optional

from lxml import etree

from ..model import Anchor, Block, Citation, CrossRef, Figure, Label, Note, PaperMap, Reference, Table

# ---------------------------------------------------------------- namespaces
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "v": "urn:schemas-microsoft-com:vml",
    "o": "urn:schemas-microsoft-com:office:office",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "cup": "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties",
    "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
    "b": "http://schemas.openxmlformats.org/officeDocument/2006/bibliography",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
# ISO 29500 Strict documents use other namespace names for the same vocabulary.
_STRICT = {
    b"http://purl.oclc.org/ooxml/wordprocessingml/main": NS["w"].encode(),
    b"http://purl.oclc.org/ooxml/officeDocument/relationships": NS["r"].encode(),
    b"http://purl.oclc.org/ooxml/officeDocument/math": NS["m"].encode(),
    b"http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing": NS["wp"].encode(),
    b"http://purl.oclc.org/ooxml/drawingml/main": NS["a"].encode(),
    b"http://purl.oclc.org/ooxml/drawingml/chart": NS["c"].encode(),
    b"http://purl.oclc.org/ooxml/officeDocument/extendedProperties": NS["ep"].encode(),
    b"http://purl.oclc.org/ooxml/officeDocument/customProperties": NS["cup"].encode(),
    b"http://purl.oclc.org/ooxml/officeDocument/docPropsVTypes": NS["vt"].encode(),
    b"http://purl.oclc.org/ooxml/officeDocument/bibliography": NS["b"].encode(),
}


def q(tag: str) -> str:
    prefix, local = tag.split(":")
    return f"{{{NS[prefix]}}}{local}"


W_P, W_R, W_T, W_TBL, W_TR, W_TC, W_SDT = q("w:p"), q("w:r"), q("w:t"), q("w:tbl"), q("w:tr"), q("w:tc"), q("w:sdt")
W_SDTCONTENT, W_SDTPR, W_PPR, W_RPR, W_VAL = q("w:sdtContent"), q("w:sdtPr"), q("w:pPr"), q("w:rPr"), q("w:val")
W_INS, W_DEL, W_MOVETO, W_MOVEFROM = q("w:ins"), q("w:del"), q("w:moveTo"), q("w:moveFrom")
W_ID, W_AUTHOR, W_DATE, W_NAME = q("w:id"), q("w:author"), q("w:date"), q("w:name")
MC_ALT, MC_CHOICE, MC_FALLBACK = q("mc:AlternateContent"), q("mc:Choice"), q("mc:Fallback")
W_TXBX = q("w:txbxContent")
_RUN_WRAPPERS = {q("w:smartTag"), q("w:customXml"), q("w:dir"), q("w:bdo")}
_IGNORE_INLINE = {W_PPR, q("w:proofErr"), q("w:permStart"), q("w:permEnd"), q("w:smartTagPr"), q("w:customXmlPr"),
                  q("w:moveFromRangeStart"), q("w:moveFromRangeEnd"), q("w:moveToRangeStart"), q("w:moveToRangeEnd")}
_SKIP_RUN = {W_RPR, q("w:footnoteRef"), q("w:endnoteRef"), q("w:annotationRef"), q("w:separator"),
             q("w:continuationSeparator"), q("w:dayShort"), q("w:monthShort"), q("w:yearShort"),
             q("w:dayLong"), q("w:monthLong"), q("w:yearLong"), q("w:pgNum")}

PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, remove_comments=True,
                         remove_pis=True)
MAX_PART = 200 * 1024 * 1024
WS = re.compile(r"\s")


def _val(el, name: str = "w:val") -> Optional[str]:
    return None if el is None else el.get(q(name))


def _on(el) -> bool:
    """A toggle property element is on unless its value says off."""
    if el is None:
        return False
    v = el.get(W_VAL)
    return v is None or v.lower() not in ("0", "false", "off", "none")


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


# ---------------------------------------------------------------- package
class _Package:
    """The zip package: parts as lxml trees, found through relationships."""

    def __init__(self, path: Path, warnings: list):
        self.warnings = warnings
        try:
            self.zip = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            raise SystemExit(f"{path} is not a Word file (not a zip package: {exc}).")
        self.infos = {i.filename: i for i in self.zip.infolist()}
        self.strict = False
        root = self.rels("")
        self.main = next((t for t, typ, ext in root.values() if typ.endswith("/officeDocument") and not ext),
                         "word/document.xml")
        self.root_rels = root
        self.main_rels = self.rels(self.main)

    def has(self, name: str) -> bool:
        return name in self.infos

    def read(self, name: str) -> Optional[bytes]:
        info = self.infos.get(name)
        if info is None:
            return None
        if info.file_size > MAX_PART:
            self.warnings.append(f"Skipped {name}: {info.file_size} bytes uncompressed.")
            return None
        data = self.zip.read(info)
        if b"purl.oclc.org/ooxml" in data:
            self.strict = True
            for k, v in _STRICT.items():
                data = data.replace(k, v)
        return data

    def xml(self, name: Optional[str]):
        if not name:
            return None
        data = self.read(name)
        if data is None:
            return None
        try:
            return etree.fromstring(data, PARSER)
        except etree.XMLSyntaxError as exc:
            self.warnings.append(f"Could not parse {name}: {exc}")
            return None

    def rels(self, part: str) -> dict:
        """rId -> (target part name or URL, relationship type, is_external) for a part."""
        folder, base = posixpath.split(part)
        rels_name = posixpath.join(folder, "_rels", base + ".rels") if part else "_rels/.rels"
        root = self.xml(rels_name)
        out = {}
        if root is None:
            return out
        for rel in root:
            if _local(rel.tag) != "Relationship":
                continue
            target, typ = rel.get("Target") or "", rel.get("Type") or ""
            external = (rel.get("TargetMode") or "").lower() == "external"
            if not external:
                target = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
            out[rel.get("Id")] = (target, typ, external)
        return out

    def related(self, suffix: str, rels: Optional[dict] = None) -> list:
        rels = self.main_rels if rels is None else rels
        return [t for t, typ, ext in rels.values() if typ.endswith(suffix) and not ext]


# ---------------------------------------------------------------- styles
class _Styles:
    def __init__(self, root, theme_fonts: dict):
        self.by_id: dict = {}
        self.default_para = None
        self.default_char = None
        self.doc_rpr = None
        self.doc_ppr = None
        self.theme_fonts = theme_fonts
        self._cache: dict = {}
        if root is None:
            return
        dd = root.find(q("w:docDefaults"))
        if dd is not None:
            self.doc_rpr = dd.find(f"{q('w:rPrDefault')}/{W_RPR}")
            self.doc_ppr = dd.find(f"{q('w:pPrDefault')}/{W_PPR}")
        for st in root.iter(q("w:style")):
            sid = st.get(q("w:styleId"))
            if sid is None:
                continue
            info = {"id": sid, "type": st.get(q("w:type")) or "paragraph", "name": _val(st.find(W_NAME)) or sid,
                    "based": _val(st.find(q("w:basedOn"))), "pPr": st.find(W_PPR), "rPr": st.find(W_RPR),
                    "link": _val(st.find(q("w:link")))}
            self.by_id[sid] = info
            if (st.get(q("w:default")) or "").lower() in ("1", "true", "on"):
                if info["type"] == "paragraph":
                    self.default_para = sid
                elif info["type"] == "character":
                    self.default_char = sid

    def chain(self, sid: Optional[str]) -> list:
        out, seen = [], set()
        while sid and sid in self.by_id and sid not in seen:
            seen.add(sid)
            out.append(self.by_id[sid])
            sid = self.by_id[sid]["based"]
        return out

    def name(self, sid: Optional[str]) -> str:
        """The style name as Word shows it ("heading 1" is stored, "Heading 1" is shown)."""
        sid = sid or self.default_para
        name = self.by_id[sid]["name"] if sid in self.by_id else (sid or "")
        if name and name == name.lower():
            name = re.sub(r"^Toc\b", "TOC", name.title())
        return name

    def names(self, sid: Optional[str]) -> list:
        return [s["name"].lower() for s in self.chain(sid or self.default_para)]

    def ppr(self, sid: Optional[str], tag: str):
        for st in self.chain(sid or self.default_para):
            if st["pPr"] is not None:
                el = st["pPr"].find(q(tag))
                if el is not None:
                    return el
        return None

    def rpr(self, rstyle: Optional[str], pstyle: Optional[str], tag: str):
        key = (rstyle, pstyle, tag)
        if key in self._cache:
            return self._cache[key]
        found = None
        for st in self.chain(rstyle) + self.chain(pstyle or self.default_para):
            if st["rPr"] is not None:
                el = st["rPr"].find(q(tag))
                if el is not None:
                    found = el
                    break
        if found is None and self.doc_rpr is not None:
            found = self.doc_rpr.find(q(tag))
        self._cache[key] = found
        return found

    def heading_level(self, sid: Optional[str]) -> Optional[int]:
        for st in self.chain(sid):
            m = re.fullmatch(r"heading\s*(\d)", st["name"].strip().lower())
            if m:
                return int(m.group(1))
        lvl = self.ppr(sid, "w:outlineLvl") if sid else None
        if lvl is not None and (_val(lvl) or "").isdigit() and int(_val(lvl)) < 9:
            return int(_val(lvl)) + 1
        return None

    def font_of(self, rfonts) -> Optional[str]:
        if rfonts is None:
            return None
        name = rfonts.get(q("w:ascii")) or rfonts.get(q("w:hAnsi"))
        if name:
            return name
        theme = rfonts.get(q("w:asciiTheme")) or rfonts.get(q("w:hAnsiTheme"))
        if theme:
            return self.theme_fonts.get("major" if theme.startswith("major") else "minor")
        return None


# ---------------------------------------------------------------- numbering
def _roman(n: int) -> str:
    vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
            (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def _letters(n: int) -> str:
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(ord("a") + r) + out
    return out


def format_number(n: int, fmt: str) -> str:
    fmt = (fmt or "decimal").lower()
    if fmt == "lowerroman":
        return _roman(n)
    if fmt == "upperroman":
        return _roman(n).upper()
    if fmt == "lowerletter":
        return _letters(n)
    if fmt == "upperletter":
        return _letters(n).upper()
    if fmt == "decimalzero":
        return f"{n:02d}"
    if fmt == "ordinal":
        return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
    if fmt in ("chicago",):
        return "*†‡§"[(n - 1) % 4] * ((n - 1) // 4 + 1)
    return str(n)


class _Numbering:
    """List and heading numbers from numbering.xml, counted in document order."""

    def __init__(self, root):
        self.abstract: dict = {}
        self.nums: dict = {}
        self.counters: dict = {}
        self.started: set = set()
        if root is None:
            return
        for an in root.iter(q("w:abstractNum")):
            self.abstract[an.get(q("w:abstractNumId"))] = {
                int(l.get(q("w:ilvl")) or 0): self._level(l) for l in an.findall(q("w:lvl"))}
        for num in root.iter(q("w:num")):
            overrides = {}
            for ov in num.findall(q("w:lvlOverride")):
                start = _val(ov.find(q("w:startOverride")))
                lvl = ov.find(q("w:lvl"))
                overrides[int(ov.get(q("w:ilvl")) or 0)] = {
                    "start": int(start) if start and start.lstrip("-").isdigit() else None,
                    "level": self._level(lvl) if lvl is not None else None}
            self.nums[num.get(q("w:numId"))] = {"abstract": _val(num.find(q("w:abstractNumId"))), "overrides": overrides}

    @staticmethod
    def _level(lvl) -> dict:
        start = _val(lvl.find(q("w:start")))
        return {"start": int(start) if start and start.lstrip("-").isdigit() else 1,
                "fmt": _val(lvl.find(q("w:numFmt"))) or "decimal", "text": _val(lvl.find(q("w:lvlText"))) or "",
                "pstyle": _val(lvl.find(q("w:pStyle"))), "legal": lvl.find(q("w:isLgl")) is not None}

    def levels(self, num_id: str) -> dict:
        num = self.nums.get(num_id) or {}
        levels = dict(self.abstract.get(num.get("abstract"), {}))
        for ilvl, ov in (num.get("overrides") or {}).items():
            if ov.get("level"):
                levels[ilvl] = ov["level"]
        return levels

    def level_for_style(self, num_id: str, style_id: Optional[str]) -> int:
        for ilvl, lvl in self.levels(num_id).items():
            if style_id and lvl.get("pstyle") == style_id:
                return ilvl
        return 0

    def next_label(self, num_id: str, ilvl: int) -> Optional[str]:
        num = self.nums.get(num_id)
        if num is None:
            return None
        levels = self.levels(num_id)
        lvl = levels.get(ilvl)
        if lvl is None:
            return None
        counts = self.counters.setdefault(num.get("abstract") or num_id, {})
        if num_id not in self.started:
            self.started.add(num_id)
            for o_lvl, ov in (num.get("overrides") or {}).items():
                if ov.get("start") is not None:
                    counts[o_lvl] = ov["start"] - 1
        counts[ilvl] = counts.get(ilvl, lvl["start"] - 1) + 1
        for deeper in [k for k in counts if k > ilvl]:
            del counts[deeper]
        if lvl["fmt"] == "bullet":
            return "•"
        if lvl["fmt"] == "none":
            return ""

        def rep(m):
            k = int(m.group(1)) - 1
            lv = levels.get(k) or {"fmt": "decimal", "start": 1}
            return format_number(counts.get(k, lv["start"]), "decimal" if lvl["legal"] else lv["fmt"])
        return re.sub(r"%(\d)", rep, lvl["text"])


# ---------------------------------------------------------------- math and symbols
_SYMBOL_FONT = {
    **dict(zip("ABCDEFGHIKLMNOPQRSTUWXYZ", "ΑΒΧΔΕΦΓΗΙΚΛΜΝΟΠΘΡΣΤΥΩΞΨΖ")),
    **dict(zip("abcdefghijklmnopqrstuvwxyz", "αβχδεφγηιϕκλμνοπθρστυϖωξψζ")),
    "J": "ϑ", "V": "ς", "-": "−", "\xa3": "≤", "\xb3": "≥", "\xb1": "±", "\xb4": "×", "\xb8": "÷", "\xb9": "≠",
    "\xba": "≡", "\xbb": "≈", "\xa5": "∞", "\xb6": "∂", "\xd6": "√", "\xe5": "∑", "\xf2": "∫", "\xae": "→",
    "\xac": "←", "\xde": "⇒", "\xdb": "⇔", "\xce": "∈", "\xcf": "∉", "\xc7": "∩", "\xc8": "∪", "\xcc": "⊂",
    "\xcd": "⊆", "\xb7": "•", "\xd7": "⋅", "\xa2": "′", "\xb2": "″", "\xbc": "…", "\xc5": "⊕", "\xd1": "∇",
}


def _sym_char(el) -> str:
    code = el.get(q("w:char")) or ""
    try:
        n = int(code, 16)
    except ValueError:
        return ""
    if n >= 0xF000:
        n -= 0xF000
    ch = chr(n)
    if (el.get(q("w:font")) or "").lower().startswith("symbol"):
        return _SYMBOL_FONT.get(ch, ch)
    return ch if ch.isprintable() and n >= 0x20 else ""


def _math_text(el) -> str:
    """A readable linear form of an OMML equation."""
    tag = _local(el.tag)

    def kids(name=None):
        return [c for c in el if isinstance(c.tag, str) and (name is None or _local(c.tag) == name)]

    def part(name):
        found = [c for c in el if _local(c.tag) == name]
        return "".join(_math_text(c) for c in found)

    def group(s):
        return "{" + s + "}"
    if tag == "t":
        return el.text or ""
    if tag in ("rPr", "ctrlPr", "fPr", "naryPr", "sSubPr", "sSupPr", "sSubSupPr", "dPr", "radPr", "funcPr", "accPr",
               "barPr", "eqArrPr", "mPr", "limLowPr", "limUppPr", "groupChrPr", "boxPr", "borderBoxPr", "oMathParaPr",
               "sPrePr", "phantPr", "argPr"):
        return ""
    if tag == "f":
        return f"({part('num')})/({part('den')})"
    if tag == "sSub":
        return part("e") + "_" + group(part("sub"))
    if tag == "sSup":
        return part("e") + "^" + group(part("sup"))
    if tag == "sSubSup":
        return part("e") + "_" + group(part("sub")) + "^" + group(part("sup"))
    if tag == "sPre":
        return "_" + group(part("sub")) + "^" + group(part("sup")) + part("e")
    if tag == "nary":
        pr = el.find(q("m:naryPr"))
        chr_el = pr.find(q("m:chr")) if pr is not None else None
        sym = _val(chr_el, "m:val") if chr_el is not None else "∫"
        sub, sup = part("sub"), part("sup")
        return sym + ("_" + group(sub) if sub else "") + ("^" + group(sup) if sup else "") + " " + part("e")
    if tag == "d":
        pr = el.find(q("m:dPr"))
        beg = _val(pr.find(q("m:begChr")), "m:val") if pr is not None and pr.find(q("m:begChr")) is not None else "("
        end = _val(pr.find(q("m:endChr")), "m:val") if pr is not None and pr.find(q("m:endChr")) is not None else ")"
        sep = _val(pr.find(q("m:sepChr")), "m:val") if pr is not None and pr.find(q("m:sepChr")) is not None else ","
        return (beg or "") + sep.join(_math_text(c) for c in kids("e")) + (end or "")
    if tag == "rad":
        deg = part("deg")
        return ("√" if not deg else f"root{group(deg)}") + "(" + part("e") + ")"
    if tag == "eqArr":
        return "; ".join(_math_text(c) for c in kids("e"))
    if tag == "m":
        return "[" + "; ".join(", ".join(_math_text(e) for e in r if _local(e.tag) == "e") for r in kids("mr")) + "]"
    if tag == "func":
        return part("fName") + " " + part("e")
    if tag in ("limLow", "limUpp"):
        return part("e") + ("_" if tag == "limLow" else "^") + group(part("lim"))
    if tag == "acc":
        pr = el.find(q("m:accPr"))
        c = pr.find(q("m:chr")) if pr is not None else None
        return part("e") + (_val(c, "m:val") if c is not None else "̂")
    return "".join(_math_text(c) for c in el if isinstance(c.tag, str))


# ---------------------------------------------------------------- paragraph records
class _Para:
    """One w:p of any story, with its text and the marks found in it."""

    def __init__(self, el, story: str, number: Optional[int]):
        self.el = el
        self.story = story
        self.number = number
        self.anchor_number = number
        self.pieces: list = []
        self.len = 0
        self.fmt: list = []          # [start, end, (italic, bold, hidden, highlight)]
        self.style = None
        self.num = None
        self.num_label = None
        self.align = None
        self.outline = None
        self.note_refs: list = []    # (raw offset, kind, note id, custom mark)
        self.links: list = []        # (raw start, raw end, target)
        self.changes: list = []      # dicts: kind, start, end, text, author, date, detail
        self.images: list = []
        self.textboxes: list = []
        self.math = 0
        self.math_spans: list = []
        self.ole_equation = False
        self.field_kinds: set = set()
        self.sdt_kinds: set = set()
        self.in_table = False
        self.cell_bg = None
        self.shading = None
        self.fonts: Counter = Counter()
        self.text = ""
        self.map: list = [0]
        self.role = None
        self.heading = None
        self.block = None
        self.block_offset = 0
        self.seq = 0
        self.prefix_cut = 0

    def pos(self, raw: int) -> int:
        raw = max(0, min(raw, len(self.map) - 1))
        return self.map[raw]

    def finish(self) -> None:
        raw = "".join(self.pieces)
        out, mapping, prev_space = [], [0] * (len(raw) + 1), True
        for i, ch in enumerate(raw):
            mapping[i] = len(out)
            if ch.isspace() or ch in "​﻿":
                if ch in "​﻿" or prev_space:
                    continue
                out.append(" ")
                prev_space = True
            else:
                out.append(ch)
                prev_space = False
        mapping[len(raw)] = len(out)
        if out and out[-1] == " ":
            out.pop()
            mapping = [min(m, len(out)) for m in mapping]
        self.text, self.map = "".join(out), mapping

    @property
    def plain(self) -> list:
        """(start, end) spans of the tidied text outside equations."""
        out, pos = [], 0
        for s, e in sorted((self.pos(a), self.pos(b)) for a, b in self.math_spans):
            if s > pos:
                out.append((pos, s))
            pos = max(pos, e)
        if pos < len(self.text):
            out.append((pos, len(self.text)))
        return out

    def segments(self):
        """(start, end, flags) in the tidied text."""
        for s, e, flags in self.fmt:
            a, b = self.pos(s), self.pos(e)
            if b > a:
                yield a, b, flags

    def all_flag(self, idx: int) -> bool:
        seen = False
        for s, e, flags in self.segments():
            if self.text[s:e].strip():
                seen = True
                if not flags[idx]:
                    return False
        return seen


class _Cell:
    def __init__(self):
        self.paras: list = []
        self.span = 1
        self.vmerge_continue = False


class _TableItem:
    def __init__(self, el):
        self.el = el
        self.rows: list = []         # list of (cells, deleted, change)
        self.first_number = None
        self.role = "table"
        self.caption = []            # caption paragraphs
        self.notes = []              # notes paragraphs after the table
        self.number = None
        self.table_id = None
        self.equation = False

    def paras(self):
        for cells, _deleted, _chg in self.rows:
            for c in cells:
                yield from c.paras


# ---------------------------------------------------------------- patterns
REF_HEADINGS = {"references", "bibliography", "works cited", "literature cited", "reference list", "literature",
                "cited literature", "references cited", "list of references"}
ACK_HEADINGS = {"acknowledgments", "acknowledgements", "acknowledgment", "acknowledgement"}
KNOWN_HEADINGS = REF_HEADINGS | ACK_HEADINGS | {
    "abstract", "introduction", "conclusion", "conclusions", "discussion", "related literature", "literature review",
    "background", "data", "data and methods", "methods", "methodology", "results", "model", "theory",
    "theoretical framework", "experimental design", "design", "empirical strategy", "robustness", "robustness checks",
    "appendix", "appendices", "online appendix", "supplementary appendix", "data availability",
    "data availability statement", "ethics", "ethics statement", "declarations", "conflict of interest",
    "conflicts of interest", "competing interests", "funding", "author contributions", "supplementary material",
    "limitations", "concluding remarks", "summary", "hypotheses", "procedures", "framework", "notes", "endnotes",
    "tables", "figures", "tables and figures", "figures and tables"}
_NUM_HEAD = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3}|[A-Z](?:\.\d{1,2}){0,3}|[IVX]{1,5}(?=\.))(?P<dot>\.?)\s+"
                       r"(?P<title>[A-ZÀ-ɏ\"“‘(].*)$")
_APPX_HEAD = re.compile(r"^(?:Online\s+|Supplementary\s+|Supplemental\s+)?(?:Appendix|Appendices)"
                        r"(?:\s+(?P<num>[A-Z]|\d{1,2}|[IVX]{1,4})(?![\w]))?\s*(?:[.:—–-]\s*)?(?P<title>.*)$", re.I)
_CAPTION = re.compile(r"^(?P<kind>Table|Figure|Fig\.|Exhibit|Chart)\s+(?P<num>[A-Z]{0,2}\d+[a-z]?|[IVX]{1,6}|[A-Z])"
                      r"(?P<rest>\s*[:.—–-]\s*.*|\s*$|\s+.*)$", re.S)
_ABSTRACT_START = re.compile(r"^abstract\s*(?:[:.—–-]\s*|\s+(?=[A-ZÀ-ɏ]))", re.I)
_JEL_KW = re.compile(r"^(?:jel\b|jel codes?|jel classification|keywords?\s*[:.—-]|key words\s*[:.—-])", re.I)
_ACK_START = re.compile(r"^(?:acknowledg(?:e)?ments?\b|we (?:are (?:very )?grateful|thank|gratefully acknowledge|"
                        r"acknowledge)|i (?:am grateful|thank)|the authors? (?:thanks?|(?:are|is) grateful|gratefully)|"
                        r"thanks (?:to|go)|funding\s*:)", re.I)
_NOTES_START = re.compile(r"^(?:notes?|sources?|source and notes?|notes? and sources?)\s*[:.—–-]", re.I)
_NOT_NAME = {"university", "department", "school", "institute", "college", "center", "centre", "faculty",
             "laboratory", "lab", "economics", "research", "version", "draft", "preliminary", "working", "paper",
             "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
             "november", "december", "abstract", "keywords", "jel", "email", "e-mail", "corresponding", "author",
             "authors", "address", "street", "road", "avenue", "the", "of", "for", "on", "in", "at", "this",
             "comments", "welcome", "please", "do", "not", "cite", "circulate", "bank", "fund", "foundation",
             "business", "management", "studies", "policy", "group", "society", "association", "inc", "ltd",
             "from", "a", "an", "with", "to", "by", "under", "over", "into", "evidence", "experiment", "experiments",
             "theory", "study", "analysis", "approach", "model", "effect", "effects", "impact", "role",
             "using", "how", "why", "what", "when", "does", "is", "are", "and", "or", "behavioral",
             "behavioural", "economic", "bias", "present", "default", "defaults", "saving", "savings", "retirement",
             "choice", "choices", "decision", "decisions", "market", "markets", "survey", "data", "test", "paper"}
_PARTICLES = {"van", "von", "de", "der", "den", "del", "della", "di", "da", "du", "le", "la", "dos", "das", "ten",
              "ter", "bin", "al", "el", "st.", "mac", "y"}
_YEAR = r"(?:1[5-9]\d\d|20\d\d)"


def _norm_heading(text: str) -> str:
    t = re.sub(r"^(?:\d+(?:\.\d+)*|[A-Z]|[IVX]+)\.?\s+(?=[A-Za-z])", "", text.strip())
    return re.sub(r"[\s:.]+$", "", t).strip().lower()


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def norm_name(s: str) -> str:
    """Family names compared without case, accents, spaces, hyphens or apostrophes."""
    return re.sub(r"[^a-z]", "", _ascii(s or "").lower())


# ---------------------------------------------------------------- reference parsing
_DOI = re.compile(r"(?:https?://(?:dx\.)?doi\.org/|\bdoi:\s*|\bDOI:?\s*)?(10\.\d{4,9}/[^\s\"<>]+)", re.I)
_URL = re.compile(r"https?://[^\s<>\"]+")
_REF_YEAR = re.compile(r"(?:^|[\s(,.\[])\(?(?P<year>" + _YEAR + r")(?P<suffix>[a-z])?\)?(?=[\s.,:;)\]]|$)"
                       r"|\((?P<nd>n\.\s?d\.|forthcoming|in press|undated)\)|(?<=[\s.,])(?P<nd2>n\.\s?d\.|forthcoming|in press)(?=[\s.,:;]|$)",
                       re.I)
_VOL = re.compile(r"(?:\b[Vv]ol(?:ume)?\.?\s*)?(?P<vol>\d+[A-Z]?)\s*(?:\(\s*(?P<iss>[^)]{1,20}?)\s*\)|,?\s*[Nn]o\.?\s*(?P<iss2>[\w/-]+))?"
                  r"\s*[:,]?\s*(?:pp?\.?\s*)?(?P<pages>[A-Za-z]?\d+[A-Za-z]?\s*[-–—]+\s*[A-Za-z]?\d+[A-Za-z]?"
                  r"|(?<=:)\s*[A-Za-z]?\d+[A-Za-z]?|[A-Za-z]?\d+[A-Za-z]?(?=\s*\.?\s*$))?")
_PAGES = re.compile(r"\bpp?\.?\s*(?P<pages>[A-Za-z]?\d+[A-Za-z]?\s*[-–—]+\s*[A-Za-z]?\d+[A-Za-z]?)")
_REPORT = re.compile(r"(?P<series>(?:NBER|CEPR|IZA|CESifo|SSRN|IMF|World Bank|Federal Reserve)?[A-Za-z .&-]*?"
                     r"(?:Working|Discussion|Policy Research|Research)\s+Papers?(?:\s+Series)?)\s*(?:No\.?|Number|#)?\s*(?P<number>[\w./-]+)?",
                     re.I)
_QUOTES = {"“": "”", '"': '"', "‘": "’", "«": "»", "„": "“"}


def _given_like(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 40 or any(ch.isdigit() for ch in s):
        return False
    toks = s.replace(".", ". ").split()
    return all(re.fullmatch(r"[A-ZÀ-ɏ][a-zß-ɏ'’-]*\.?|[A-Z]\.(?:-?[A-Z]\.)*|[A-Z]{1,3}|Jr\.?|Sr\.?|"
                            r"II|III|IV|(?:van|von|de|der|den|del|della|di|da|du|le|la)", t) for t in toks)


def _initials(s: str) -> bool:
    return bool(re.fullmatch(r"(?:[A-ZÀ-ɏ]\.?\s*-?\s*){1,4}", s.strip()))


def _natural(name: str) -> dict:
    """'Dennis F. Shea' -> family Shea, given Dennis F."""
    toks = name.split()
    suffix = ""
    if len(toks) > 2 and re.fullmatch(r"Jr\.?|Sr\.?|II|III|IV", toks[-1]):
        suffix = " " + toks.pop()
    if len(toks) == 1:
        return {"family": toks[0], "given": ""}
    k = len(toks) - 1
    while k > 1 and toks[k - 1].lower() in _PARTICLES:
        k -= 1
    return {"family": " ".join(toks[k:]), "given": (" ".join(toks[:k]) + suffix).strip()}


def parse_names(text: str) -> tuple:
    """Author string of a reference entry -> ([{family, given}], et_al)."""
    s = re.sub(r"(?<![A-Z])\.$", "", text.strip().strip(",; "))
    et_al = bool(re.search(r"\bet\.?\s*al\b\.?", s))
    s = re.sub(r",?\s*\bet\.?\s*al\b\.?", "", s)
    s = re.sub(r"\s*\((?:eds?|Hrsg|coord)\.?\)\s*$|,\s*eds?\.?$", "", s, flags=re.I)
    s = re.sub(r"\s*(?:,\s*)?(?:&|\band\b|\bund\b|\bet\b|\by\b)\s+", " ; ", s)
    chunks = [c.strip() for c in s.split(";") if c.strip()]
    names: list = []
    for chunk in chunks:
        pieces = [p.strip() for p in chunk.split(",") if p.strip()]
        i = 0
        while i < len(pieces):
            p = pieces[i]
            nxt = pieces[i + 1] if i + 1 < len(pieces) else None
            if _initials(p) and names and not names[-1]["given"]:
                names[-1]["given"] = p
                i += 1
                continue
            if re.fullmatch(r"Jr\.?|Sr\.?|II|III|IV", p) and names:
                names[-1]["given"] = (names[-1]["given"] + " " + p).strip()
                i += 1
                continue
            first = not names
            words = p.split()
            multi = len(words) > 1 and not _initials(p)
            if not first and multi and words[0].lower() not in _PARTICLES and not (nxt and _initials(nxt)):
                names.append(_natural(p))
                i += 1
            elif nxt is not None and _given_like(nxt) and not (len(nxt.split()) > 1 and not _initials(nxt)
                                                                and not first and len(pieces) - i > 2):
                names.append({"family": p, "given": nxt})
                i += 2
            elif multi and not first:
                names.append(_natural(p))
                i += 1
            elif re.fullmatch(r"(?:[A-Z]\.?\s?){1,3}\s+\S.*", p):
                # Vancouver order: "Madrian BC" is unusual in economics; "B. C. Madrian" is natural order.
                names.append(_natural(p))
                i += 1
            else:
                vanc = re.fullmatch(r"(?P<fam>[\w'’ -]+?)\s+(?P<ini>[A-Z]{1,3})", p)
                if vanc and not first or (vanc and nxt is None and len(chunks) == 1 and len(pieces) == 1 and
                                          re.fullmatch(r".+\s[A-Z]{1,3}", p)):
                    names.append({"family": vanc.group("fam"), "given": vanc.group("ini")})
                else:
                    names.append({"family": p, "given": ""})
                i += 1
    return [n for n in names if n["family"]], et_al


def _italic_after(italics: list, pos: int, limit: int = 4) -> Optional[tuple]:
    for s, e in italics:
        if s >= pos - 1 and s <= pos + limit:
            return s, e
    return None


def parse_reference(text: str, italics: Optional[list] = None) -> dict:
    """Heuristic parse of one author-year reference entry into CSL-like fields.

    `italics` are (start, end) spans of italic text in `text`; in Word the journal
    or book title is usually italic, which locates the container."""
    italics = sorted(italics or [])
    t = text.strip()
    fields: dict = {}
    lead = re.match(r"^\s*(?:\[\d+\]|\d+\.(?=\s))\s*", t)
    offset = lead.end() if lead else 0
    if lead:
        fields["label"] = t[:lead.end()].strip()
    doi = _DOI.search(t)
    if doi:
        d = doi.group(1).rstrip(".,;")
        if d.count(")") > d.count("("):
            d = d.rstrip(")")
        fields["doi"] = d
    for m in _URL.finditer(t):
        url = m.group(0).rstrip(".,;")
        if "doi.org/" not in url:
            fields["url"] = url
            break
    ym = None
    for m in _REF_YEAR.finditer(t, offset):
        before = t[offset:m.start()]
        if re.search(r"[A-Za-zÀ-ɏ]", before) and len(before) < 400:
            ym = m
            break
    if ym is None:
        names, et_al = parse_names(re.split(r"\.\s+(?=[A-Z“\"])", t[offset:], maxsplit=1)[0])
        fields.update({"authors": names, "type": "other"})
        return {k: v for k, v in fields.items() if v not in (None, "", [])}
    if ym.group("year"):
        fields["year"] = ym.group("year")
        if ym.group("suffix"):
            fields["year_suffix"] = ym.group("suffix")
    else:
        fields["year_note"] = (ym.group("nd") or ym.group("nd2")).lower()
    author_text = t[offset:ym.start()].strip().rstrip("(").strip()
    author_text = re.sub(r"(?:,|(?<![A-Z])\.)$", "", author_text).strip()
    names, et_al = parse_names(author_text)
    fields["authors"] = names
    if et_al:
        fields["et_al"] = True
    rest_start = ym.end()
    rest = t[rest_start:]
    lstrip = len(rest) - len(rest.lstrip(" ).,:;"))
    rest_start += lstrip
    rest = t[rest_start:]
    title, after_pos = None, rest_start
    if rest[:1] in _QUOTES:
        close = rest.find(_QUOTES[rest[0]], 1)
        if close > 0:
            title = rest[1:close].strip().rstrip(".,").strip()
            after_pos = rest_start + close + 1
    if title is None:
        ital = _italic_after(italics, rest_start, 2)
        if ital and ital[1] - ital[0] > 3:
            title = t[ital[0]:ital[1]].strip().rstrip(".,")
            fields["type"] = "book"
            after_pos = ital[1]
        else:
            m = re.search(r"(?<![A-Z])(?<!\b[A-Z][a-z])[.?!](?=\s+[A-ZÀ-ɏ(“\"\[]|\s*$)", rest)
            end = m.start() + (1 if m and rest[m.start()] in "?!" else 0) if m else len(rest)
            title = rest[:end].strip().rstrip(".,").strip()
            after_pos = rest_start + (m.end() if m else len(rest))
    fields["title"] = title or None
    tail = t[after_pos:]
    tail_start = after_pos + len(tail) - len(tail.lstrip(" .,:;"))
    tail = t[tail_start:]
    container, vol_text, ital_container = None, tail, False
    if fields.get("type") != "book":
        ital = _italic_after(italics, tail_start, 6)
        if ital:
            container = t[ital[0]:ital[1]].strip().rstrip(".,:;")
            vol_text = t[ital[1]:]
            ital_container = True
        else:
            # the container runs up to the volume number; abbreviated names such as "Q. J. Econ." keep their periods
            m = re.match(r"(?:In:?\s+)?(?P<c>[^\d\"“”]+?)[,.]?\s+(?=(?:[Vv]ol(?:ume)?\.?\s*)?\d+[A-Z]?\s*(?:\(|,|:|$|\.\s|\.$))",
                         tail)
            if not m:
                m = re.match(r"(?:In:?\s+)?(?P<c>[^,\d(]*?[A-Za-z][^,\d(]*?)\s*(?=,|\s\d|\(|\.\s|$)", tail)
            if m:
                container = m.group("c").strip().rstrip(".,:;")
                vol_text = tail[m.end():]
    if container and re.match(r"^in\b", container, re.I):
        fields["type"] = "chapter"
        container = re.sub(r"^in:?\s+", "", container, flags=re.I)
    rep = _REPORT.search(t[tail_start:])
    if rep and fields.get("type") != "book":
        fields["type"] = "report"
        fields["container"] = rep.group("series").strip()
        if rep.group("number"):
            fields["number"] = rep.group("number").rstrip(".,")
    elif container:
        fields["container"] = container
    vt = re.sub(r"https?://\S+|\bdoi:\s*\S+", " ", vol_text)
    vm = _VOL.search(vt) if fields.get("type") not in ("book", "report") else None
    if vm and vm.group("vol") and not re.fullmatch(_YEAR, vm.group("vol")):
        fields["volume"] = vm.group("vol")
        iss = vm.group("iss") or vm.group("iss2")
        if iss:
            fields["issue"] = iss.strip()
        if vm.group("pages"):
            fields["pages"] = re.sub(r"\s+", "", vm.group("pages"))
    if "pages" not in fields:
        pm_ = _PAGES.search(vt)
        if pm_:
            fields["pages"] = re.sub(r"\s+", "", pm_.group("pages"))
    if fields.get("type") in ("book", "report", None) and "publisher" not in fields:
        pub = re.search(r"(?:^|[.,]\s+)(?:(?P<place>[A-Z][\w .]+?(?:,\s*[A-Z]{2})?):\s*)?(?P<pub>[A-Z][\w&.,' -]*?(?:Press|Publishing|Publishers|"
                        r"Books|Verlag|Wiley|Springer|Elsevier|Routledge|Norton|Penguin|Basic Books|Bureau|Office|Bank|"
                        r"Fund|Institute|Foundation|University))(?=[.,]|$)", t[tail_start:])
        if pub:
            fields["publisher"] = pub.group("pub").strip()
            if pub.group("place"):
                fields["publisher_place"] = pub.group("place").strip()
    if fields.get("publisher") and not fields.get("volume") and fields.get("type") not in ("report", "chapter"):
        fields["type"] = "book"
        if not ital_container:
            fields.pop("container", None)
    if "type" not in fields:
        fields["type"] = "article-journal" if fields.get("volume") else "other"
    return {k: v for k, v in fields.items() if v not in (None, "", [])}


def ref_key(fields: dict, taken: set) -> str:
    authors = fields.get("authors") or []
    base = norm_name(authors[0]["family"]) if authors else norm_name((fields.get("title") or "anon").split()[0])
    base = (base or "anon")[:30] + (fields.get("year") or "nd") + (fields.get("year_suffix") or "")
    key, n = base, 0
    while key in taken:
        n += 1
        key = base + _letters(n)
    taken.add(key)
    return key


# ---------------------------------------------------------------- reference-manager data
def csl_fields(item: dict) -> dict:
    """CSL-JSON itemData -> paper-map reference fields."""
    def names(lst):
        out = []
        for a in lst or []:
            if not isinstance(a, dict):
                continue
            family = a.get("family") or a.get("literal") or ""
            given = a.get("given") or ""
            particle = a.get("non-dropping-particle") or ""
            out.append({"family": f"{particle} {family}".strip(), "given": given})
        return out
    year = None
    issued = item.get("issued")
    if isinstance(issued, dict):
        parts = issued.get("date-parts")
        if parts and parts[0] and parts[0][0] not in (None, ""):
            year = str(parts[0][0])
        else:
            m = re.search(_YEAR, str(issued.get("raw") or issued.get("literal") or ""))
            year = m.group(0) if m else None
    elif issued:
        m = re.search(_YEAR, str(issued))
        year = m.group(0) if m else None
    authors = names(item.get("author")) or names(item.get("editor"))
    fields = {
        "type": item.get("type"), "title": item.get("title"), "authors": authors, "year": year,
        "container": item.get("container-title") or item.get("collection-title"),
        "volume": item.get("volume"), "issue": item.get("issue"), "pages": item.get("page"),
        "doi": item.get("DOI") or item.get("doi"), "url": item.get("URL"), "publisher": item.get("publisher"),
        "number": item.get("number"), "note": item.get("note"),
    }
    return {k: (str(v) if isinstance(v, (int, float)) else v) for k, v in fields.items() if v not in (None, "", [])}


def _endnote_fields(cite) -> tuple:
    """One <Cite> of EndNote field data -> (fields, record number)."""
    rec = cite.find("record")

    def txt(path, base=None):
        el = (rec if base is None and rec is not None else cite).find(path)
        return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else None
    fields: dict = {}
    if rec is not None:
        authors = []
        for a in rec.findall("contributors/authors/author"):
            name = re.sub(r"\s+", " ", "".join(a.itertext())).strip()
            if "," in name:
                fam, giv = name.split(",", 1)
                authors.append({"family": fam.strip(), "given": giv.strip()})
            elif name:
                authors.append(_natural(name))
        ref_type = rec.find("ref-type")
        fields = {
            "authors": authors, "title": txt("titles/title"),
            "container": txt("titles/secondary-title") or txt("periodical/full-title"),
            "year": txt("dates/year"), "volume": txt("volume"), "issue": txt("number"), "pages": txt("pages"),
            "doi": txt("electronic-resource-num"), "url": txt("urls/related-urls/url"),
            "publisher": txt("publisher"), "type": (ref_type.get("name") if ref_type is not None else None),
        }
        fields = {k: v for k, v in fields.items() if v not in (None, "", [])}
    if not fields.get("authors") and txt("Author", cite):
        fields["authors"] = [{"family": txt("Author", cite), "given": ""}]
    if not fields.get("year") and txt("Year", cite):
        fields["year"] = txt("Year", cite)
    return fields, txt("RecNum", cite) or txt("rec-number")


def _word_source_fields(src) -> dict:
    """A Word bibliography source (customXml b:Source) -> reference fields."""
    def txt(tag):
        el = src.find(q("b:" + tag))
        return (el.text or "").strip() if el is not None and el.text else None
    authors = []
    for person in src.iterfind(f".//{q('b:Author')}/{q('b:Author')}/{q('b:NameList')}/{q('b:Person')}"):
        last = person.find(q("b:Last"))
        first = [p.text for p in (person.find(q("b:First")), person.find(q("b:Middle"))) if p is not None and p.text]
        authors.append({"family": (last.text if last is not None else "") or "", "given": " ".join(first)})
    corp = src.find(f".//{q('b:Author')}/{q('b:Author')}/{q('b:Corporate')}")
    if not authors and corp is not None and corp.text:
        authors.append({"family": corp.text, "given": ""})
    fields = {"authors": authors, "title": txt("Title"), "year": txt("Year"),
              "container": txt("JournalName") or txt("BookTitle") or txt("ConferenceName"),
              "volume": txt("Volume"), "issue": txt("Issue"), "pages": txt("Pages"), "doi": txt("DOI"),
              "url": txt("URL"), "publisher": txt("Publisher"), "type": txt("SourceType")}
    return {k: v for k, v in fields.items() if v not in (None, "", [])}


# ---------------------------------------------------------------- in-text citations and cross-references
_SURNAME = (r"(?:(?:[vV]an|[vV]on|[dD]e|[dD]er|[dD]en|[dD]el|[dD]ella|[dD]i|[dD]a|[dD]u|[lL]e|[lL]a|[dD]os|[tT]en|"
            r"[tT]er)\s+)*[A-ZÀ-Þ][A-Za-zÀ-ɏ'’\-]*[a-zß-ɏ][A-Za-zÀ-ɏ'’\-]*")
_AUTHORS = (rf"{_SURNAME}(?:\s*,\s*{_SURNAME})*(?:,?\s+(?:and|&)\s+{_SURNAME})?(?:\s+et\s+al\.?)?")
_CYEAR = rf"(?:{_YEAR}[a-z]?|forthcoming|in press|n\.\s?d\.)"
_CYEARS = rf"{_CYEAR}(?:\s*,\s*(?:{_CYEAR}|[a-z]\b))*"
_LOCATOR = r"(?:\s*,\s*(?:p|pp|ch|chap|sec|section|table|fig|figure|eq|appendix)\.?\s*[\w–.-]+)?"
NARRATIVE = re.compile(rf"(?<![\w’'])(?P<authors>{_AUTHORS})(?:['’]s?)?\s*\(\s*(?P<years>{_CYEARS}){_LOCATOR}\s*\)")
PAREN = re.compile(r"\((?P<inner>[^()]*?(?:" + _YEAR + r"|forthcoming|in press|n\.\s?d\.)[^()]*)\)")
PART = re.compile(rf"(?P<authors>{_AUTHORS}),?\s+(?P<years>{_CYEARS})(?P<post>(?:\s*,\s*[^;]*)?)\s*$")
_LEADIN = re.compile(r"(?:^|[\s,;(])(?:e\.\s?g\.|i\.\s?e\.|see(?:\s+also)?|cf\.|for\s+example|for\s+instance|"
                     r"for\s+(?:a\s+)?(?:review|survey|discussion|overview)s?(?:,?\s+see)?|as\s+in|following|"
                     r"surveyed\s+(?:in|by)|reviewed\s+(?:in|by)|and|also|but\s+see|compare|including|like|"
                     r"among\s+others|as\s+(?:shown|argued|noted|reported|discussed)\s+(?:by|in))[\s,:]*$", re.I)
_NOT_SURNAME = {"table", "tables", "figure", "figures", "section", "sections", "appendix", "equation", "panel", "column",
                "model", "study", "survey", "wave", "round", "experiment", "treatment", "control", "group", "sample",
                "census", "bureau", "act", "law", "policy", "program", "programme", "report", "commission", "committee",
                "council", "agency", "department", "ministry", "university", "institute", "association", "society",
                "office", "board", "january", "february", "march", "april", "may", "june", "july", "august",
                "september", "october", "november", "december", "spring", "summer", "fall", "autumn", "winter",
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "since", "until",
                "after", "before", "during", "in", "from", "through", "between", "the", "this", "that", "our", "we",
                "version", "edition", "data", "online", "wave", "phase", "year", "years", "also", "see", "and"}
CROSSREF = re.compile(
    r"(?<![\w-])(?P<kind>Tables?|Figures?|Figs?\.|Sections?|Secs?\.|§§?|(?:Online\s+|Supplementary\s+)?Appendi(?:x|ces)"
    r"(?:\s+(?:Table|Figure)s?)?|Equations?|Eqs?\.)\s*(?P<labels>(?:\(\d+[a-z]?\)|[A-Z]{0,2}\d+(?:\.\d+)*[a-z]?|[A-Z](?![\w’'])|"
    r"[IVX]{1,5}(?![\w]))(?:(?:\s*,\s*(?:and\s+)?|\s+(?:and|&|to|through)\s+|\s*[–—-]\s*)"
    r"(?:\(\d+[a-z]?\)|[A-Z]{0,2}\d+(?:\.\d+)*[a-z]?|[A-Z](?![\w’'])|[IVX]{1,5}(?![\w])))*)")
_LABEL_TOKEN = re.compile(r"\(\d+[a-z]?\)|[A-Z]{0,2}\d+(?:\.\d+)*[a-z]?|[A-Z](?![\w’'])|[IVX]{1,5}(?![\w])")
CITE_KINDS = ("paragraph", "abstract", "footnote", "caption", "list_item", "acknowledgment", "front_matter", "table",
              "other")
_ERROR_FIELD = re.compile(r"\bError[!:]\s|Fehler!|Erreur\s?!|¡Error!|Errore!|Reference source not found|Bookmark not defined", re.I)


def _xref_kind(word: str) -> str:
    w = word.lower().replace(".", "")
    if w.startswith(("online appendix", "supplementary appendix")):
        return "online_appendix"
    if w.startswith("append"):
        return "appendix_" + ("table" if "table" in w else "figure") if ("table" in w or "figure" in w) else "appendix"
    if w.startswith(("table",)):
        return "table"
    if w.startswith(("fig",)):
        return "figure"
    if w.startswith(("sec", "§")):
        return "section"
    return "equation"


def _expand_labels(text: str) -> list:
    toks = [(m.group(0), m.start(), m.end()) for m in _LABEL_TOKEN.finditer(text)]
    out = []
    for i, (tok, s, e) in enumerate(toks):
        out.append(tok.strip("()"))
        if i + 1 < len(toks):
            between = text[e:toks[i + 1][1]]
            a, b = tok.strip("()"), toks[i + 1][0].strip("()")
            if re.search(r"[–—-]|\bto\b|\bthrough\b", between) and a.isdigit() and b.isdigit() and 0 < int(b) - int(a) <= 20:
                out.extend(str(n) for n in range(int(a) + 1, int(b)))
    return out


def _within(spans: list, s: int, e: int) -> bool:
    return any(a < e and s < b for a, b in spans)


# ---------------------------------------------------------------- reader
class DocxReader:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.pm = PaperMap(source={"path": str(path), "main": self.path.name, "files": [self.path.name]})
        self.pkg = _Package(self.path, self.pm.warnings)
        self.pm.source["main_part"] = self.pkg.main
        self.n_par = 0
        self.fstack: list = []
        self.chg: list = []
        self.sdt_stack: list = []
        self.fields: list = []
        self.bookmarks: dict = {}
        self.comment_marks: dict = {}
        self.items: list = []
        self.all_paras: list = []
        self.sect_prs: list = []
        self.notes_paras = {"footnote": {}, "endnote": {}}
        self.comments: dict = {}
        self.n_block = 0
        self.headings: list = []
        self.block_paras: dict = {}
        self.field_counts: Counter = Counter()
        self.stale_fields: list = []
        self.label_index: dict = {}
        self.pending_marks: list = []
        self.section_path: list = []
        self.rels: dict = {}

    # -- setup -----------------------------------------------------------
    def _load_parts(self) -> None:
        pkg = self.pkg
        theme = pkg.xml(next(iter(pkg.related("/theme")), None))
        fonts = {}
        if theme is not None:
            for kind in ("major", "minor"):
                latin = theme.find(f".//{q('a:' + kind + 'Font')}/{q('a:latin')}")
                if latin is not None:
                    fonts[kind] = latin.get("typeface")
        self.styles = _Styles(pkg.xml(next(iter(pkg.related("/styles")), None)), fonts)
        self.numbering = _Numbering(pkg.xml(next(iter(pkg.related("/numbering")), None)))
        self.settings = pkg.xml(next(iter(pkg.related("/settings")), None))
        self.doc = pkg.xml(pkg.main)
        if self.doc is None:
            raise SystemExit(f"{self.path} has no readable main document part ({pkg.main}).")
        if pkg.strict:
            self.pm.warnings.append("The document uses ISO 29500 Strict namespaces; they were mapped to the usual ones.")

    def _new_id(self) -> str:
        self.n_block += 1
        return f"b{self.n_block:04d}"

    # -- run formatting --------------------------------------------------
    def _flags(self, run, para: _Para) -> tuple:
        """(italic, bold, hidden kind, highlight, font, size in points) of a run, through its styles."""
        rpr = run.find(W_RPR) if run is not None else None
        rstyle = _val(rpr.find(q("w:rStyle"))) if rpr is not None else None
        st = self.styles

        def prop(tag):
            if rpr is not None:
                el = rpr.find(q(tag))
                if el is not None:
                    return el
            return st.rpr(rstyle, para.style, tag)
        italic, bold = _on(prop("w:i")), _on(prop("w:b"))
        hidden = None
        if _on(prop("w:vanish")) and not _on(prop("w:specVanish")):
            hidden = "hidden text"
        else:
            color = prop("w:color")
            if color is not None and self._is_white(color) and not self._dark_background(rpr, para):
                hidden = "white text"
            else:
                sz = _val(prop("w:sz"))
                if sz and sz.isdigit() and int(sz) <= 4:
                    hidden = "tiny text"
        hl = _val(prop("w:highlight"))
        highlight = hl if hl and hl.lower() not in ("none", "white") else None
        font = st.font_of(prop("w:rFonts"))
        sz = _val(prop("w:sz"))
        return italic, bold, hidden, highlight, font, int(sz) / 2 if sz and sz.isdigit() else None

    @staticmethod
    def _is_white(color) -> bool:
        val = (color.get(W_VAL) or "").strip()
        theme = (color.get(q("w:themeColor")) or "").lower()
        if theme in ("background1", "light1") and not color.get(q("w:themeShade")):
            return True
        if re.fullmatch(r"[0-9A-Fa-f]{6}", val):
            r, g, b = int(val[:2], 16), int(val[2:4], 16), int(val[4:], 16)
            return min(r, g, b) >= 0xF0
        return False

    @staticmethod
    def _dark(fill: Optional[str]) -> bool:
        if not fill or fill.lower() == "auto" or not re.fullmatch(r"[0-9A-Fa-f]{6}", fill):
            return False
        r, g, b = int(fill[:2], 16), int(fill[2:4], 16), int(fill[4:], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) < 160

    def _dark_background(self, rpr, para: _Para) -> bool:
        if rpr is not None:
            shd = rpr.find(q("w:shd"))
            if shd is not None and self._dark(shd.get(q("w:fill"))):
                return True
            hl = rpr.find(q("w:highlight"))
            if hl is not None and (_val(hl) or "").lower() in ("black", "darkblue", "darkred", "darkgreen", "darkgray",
                                                                "darkmagenta", "darkcyan", "blue", "red", "green"):
                return True
        return self._dark(para.shading) or self._dark(para.cell_bg)

    # -- text emission ---------------------------------------------------
    def _in_instr(self) -> bool:
        return any(f["phase"] == "instr" for f in self.fstack)

    def _deleting(self) -> Optional[dict]:
        for c in reversed(self.chg):
            if c["kind"] == "tracked_deletion":
                return c
        return None

    def _emit(self, para: _Para, text: str, run) -> None:
        if not text or self._in_instr():
            return
        deletion = self._deleting()
        if deletion is not None:
            deletion["parts"].append(text)
            return
        flags = self._flags(run, para)
        start = para.len
        para.pieces.append(text)
        para.len += len(text)
        f4 = flags[:4]
        if para.fmt and para.fmt[-1][1] == start and para.fmt[-1][2] == f4:
            para.fmt[-1][1] = para.len
        else:
            para.fmt.append([start, para.len, f4])
        if flags[4] or flags[5]:
            n = sum(1 for ch in text if not ch.isspace())
            if n:
                para.fonts[(flags[4], flags[5])] += n
        for c in self.chg:
            if c["kind"] == "tracked_insertion":
                c["parts"].append(text)

    # -- walking ---------------------------------------------------------
    def _paragraph(self, p, story: str, *, in_table: bool = False, cell_bg=None, numbered: bool = True) -> _Para:
        number = None
        if story == "body" and numbered:
            self.n_par += 1
            number = self.n_par
        para = _Para(p, story, number)
        para.in_table, para.cell_bg = in_table, cell_bg
        para.sdt_kinds = set(self.sdt_stack)
        para.field_kinds = {f["kind"] for f in self.fstack if f["phase"] == "result" and f.get("kind")}
        ppr = p.find(W_PPR)
        if ppr is not None:
            para.style = _val(ppr.find(q("w:pStyle")))
            para.align = _val(ppr.find(q("w:jc")))
            ol = _val(ppr.find(q("w:outlineLvl")))
            para.outline = int(ol) + 1 if ol and ol.isdigit() and int(ol) < 9 else None
            shd = ppr.find(q("w:shd"))
            para.shading = shd.get(q("w:fill")) if shd is not None else None
            numpr = ppr.find(q("w:numPr"))
            if numpr is not None:
                nid = _val(numpr.find(q("w:numId")))
                ilvl = _val(numpr.find(q("w:ilvl")))
                para.num = (nid, int(ilvl) if ilvl and ilvl.isdigit() else None)
            chg = ppr.find(q("w:pPrChange"))
            if chg is not None:
                para.changes.append({"kind": "tracked_format_change", "start": 0, "end": 0, "text": None,
                                     "author": chg.get(W_AUTHOR), "date": chg.get(W_DATE), "detail": "paragraph properties"})
            mark = ppr.find(W_RPR)
            if mark is not None:
                for tag, kind in ((W_INS, "tracked_insertion"), (W_DEL, "tracked_deletion")):
                    el = mark.find(tag)
                    if el is not None:
                        para.changes.append({"kind": kind, "start": None, "end": None, "text": None, "mark": True,
                                             "author": el.get(W_AUTHOR), "date": el.get(W_DATE),
                                             "detail": "paragraph mark"})
            if ppr.find(q("w:sectPr")) is not None:
                self.sect_prs.append(ppr.find(q("w:sectPr")))
        if para.num is None and para.style:
            st_num = self.styles.ppr(para.style, "w:numPr")
            if st_num is not None:
                nid = _val(st_num.find(q("w:numId")))
                ilvl = _val(st_num.find(q("w:ilvl")))
                para.num = (nid, int(ilvl) if ilvl and ilvl.isdigit() else None)
        if para.num is not None:
            nid, ilvl = para.num
            if nid and nid != "0" and story == "body":
                if ilvl is None:
                    ilvl = self.numbering.level_for_style(nid, para.style)
                para.num = (nid, ilvl)
                para.num_label = self.numbering.next_label(nid, ilvl)
            else:
                para.num = None
        if self.pending_marks:
            marks, self.pending_marks = self.pending_marks, []
            self._inline(marks, para)
        self._inline(p, para)
        if any(f["phase"] == "instr" for f in self.fstack):
            # a field instruction never spans paragraphs in practice; a broken one must not swallow the document
            broken = [f for f in self.fstack if f["phase"] == "instr"]
            self.fstack = [f for f in self.fstack if f["phase"] != "instr"]
            self.pm.warnings.append(f"Paragraph {para.anchor_number or '?'} ({story}): a field instruction "
                                    f"({''.join(broken[0]['instr_parts']).strip()[:40]!r}) has no end; it was ignored.")
        para.finish()
        para.seq = len(self.all_paras)
        self.all_paras.append(para)
        return para

    def _inline(self, el, para: _Para) -> None:
        for child in el:
            tag = child.tag
            if not isinstance(tag, str) or tag in _IGNORE_INLINE:
                continue
            if tag == W_R:
                self._run(child, para)
            elif tag in (W_INS, W_MOVETO, W_DEL, W_MOVEFROM):
                kind = "tracked_insertion" if tag in (W_INS, W_MOVETO) else "tracked_deletion"
                ctx = {"kind": kind, "author": child.get(W_AUTHOR), "date": child.get(W_DATE), "parts": [],
                       "start": para.len, "move": tag in (W_MOVETO, W_MOVEFROM)}
                self.chg.append(ctx)
                self._inline(child, para)
                self.chg.pop()
                text = "".join(ctx["parts"])
                if text.strip():
                    para.changes.append({"kind": kind, "start": ctx["start"], "end": para.len, "text": text,
                                         "author": ctx["author"], "date": ctx["date"],
                                         "detail": "moved text" if ctx["move"] else None})
            elif tag == q("w:hyperlink"):
                start = para.len
                self._inline(child, para)
                rid, anchor = child.get(q("r:id")), child.get(q("w:anchor"))
                target = None
                if rid and rid in self.rels:
                    target = self.rels[rid][0]
                elif anchor:
                    target = "#" + anchor
                if target and para.len > start:
                    para.links.append((start, para.len, target))
            elif tag == q("w:fldSimple"):
                instr = child.get(q("w:instr")) or ""
                f = {"instr_parts": [instr], "instr": instr, "phase": "result", "start": (para, para.len), "data": [],
                     "deleted": self._deleting() is not None, "kind": _field_kind(instr)}
                para.field_kinds.add(f["kind"])
                self.fstack.append(f)
                self._inline(child, para)
                self.fstack.remove(f)
                f["end"] = (para, para.len)
                self._field_done(f)
            elif tag in _RUN_WRAPPERS:
                self._inline(child, para)
            elif tag == W_SDT:
                self._inline_sdt(child, para)
            elif tag == q("w:bookmarkStart"):
                self.bookmarks[child.get(W_ID)] = {"name": child.get(W_NAME) or "", "start": (para, para.len)}
            elif tag == q("w:bookmarkEnd"):
                bm = self.bookmarks.get(child.get(W_ID))
                if bm is not None and "end" not in bm:
                    bm["end"] = (para, para.len)
            elif tag == q("w:commentRangeStart"):
                self.comment_marks.setdefault(child.get(W_ID), {})["start"] = (para, para.len)
            elif tag == q("w:commentRangeEnd"):
                self.comment_marks.setdefault(child.get(W_ID), {})["end"] = (para, para.len)
            elif tag in (q("m:oMathPara"), q("m:oMath")):
                if not self._in_instr() and self._deleting() is None:
                    text = re.sub(r"\s+", " ", _math_text(child)).strip()
                    if text:
                        sep = " " if para.len and not "".join(para.pieces)[-1:].isspace() else ""
                        start = para.len + len(sep)
                        self._emit(para, sep + text, None)
                        para.math += len(text)
                        para.math_spans.append((start, para.len))
            elif tag == MC_ALT:  # read the first choice only; the fallback repeats the same content
                holder = child.find(MC_CHOICE)
                holder = holder if holder is not None else child.find(MC_FALLBACK)
                if holder is not None:
                    self._inline(holder, para)

    def _inline_sdt(self, sdt, para: _Para) -> None:
        pr = sdt.find(W_SDTPR)
        tag = _val(pr.find(q("w:tag"))) if pr is not None else None
        content = sdt.find(W_SDTCONTENT)
        start = (para, para.len)
        if content is not None:
            self._inline(content, para)
        if tag and tag.startswith("MENDELEY_CITATION_v3_"):
            self._field_done({"kind": "mendeley_v3", "instr": tag, "start": start, "end": (para, para.len), "data": [],
                              "deleted": False, "sdt": True})
        elif pr is not None and pr.find(q("w:citation")) is not None:
            self.field_counts["citation content control"] += 1

    def _run(self, r, para: _Para) -> None:
        for child in r:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            if tag == W_RPR:
                chg = child.find(q("w:rPrChange"))
                if chg is not None and not self._in_instr():
                    text = "".join(t.text or "" for t in r.iter(W_T))
                    para.changes.append({"kind": "tracked_format_change", "start": para.len, "end": para.len + len(text),
                                         "text": text, "author": chg.get(W_AUTHOR), "date": chg.get(W_DATE),
                                         "detail": "run properties"})
                continue
            if tag in _SKIP_RUN:
                continue
            if tag == W_T:
                self._emit(para, child.text or "", r)
            elif tag == q("w:delText"):
                deletion = self._deleting()
                if deletion is not None and not self._in_instr():
                    deletion["parts"].append(child.text or "")
            elif tag in (q("w:instrText"), q("w:delInstrText")):
                if self.fstack and self.fstack[-1]["phase"] == "instr":
                    self.fstack[-1]["instr_parts"].append(child.text or "")
            elif tag == q("w:fldChar"):
                self._fldchar(child, para)
            elif tag in (q("w:tab"), q("w:ptab")):
                self._emit(para, "\t", r)
            elif tag in (q("w:br"), q("w:cr")):
                self._emit(para, "\n", r)
            elif tag == q("w:noBreakHyphen"):
                self._emit(para, "-", r)
            elif tag == q("w:softHyphen"):
                continue
            elif tag == q("w:sym"):
                self._emit(para, _sym_char(child), r)
            elif tag in (q("w:footnoteReference"), q("w:endnoteReference")):
                if not self._in_instr() and self._deleting() is None:
                    kind = "footnote" if tag == q("w:footnoteReference") else "endnote"
                    para.note_refs.append((para.len, kind, child.get(W_ID), _on(child.find(q("w:customMarkFollows")))
                                           or (child.get(q("w:customMarkFollows")) or "").lower() in ("1", "true", "on")))
            elif tag == q("w:commentReference"):
                self.comment_marks.setdefault(child.get(W_ID), {})["ref"] = (para, para.len)
            elif tag == q("w:drawing"):
                self._drawing(child, para)
            elif tag == q("w:pict"):
                self._pict(child, para)
            elif tag == q("w:object"):
                self._object(child, para)
            elif tag == MC_ALT:
                choice = child.find(MC_CHOICE)
                holder = choice if choice is not None else child.find(MC_FALLBACK)
                if holder is not None:
                    self._run(holder, para)

    def _fldchar(self, el, para: _Para) -> None:
        typ = el.get(q("w:fldCharType"))
        if typ == "begin":
            data = el.find(q("w:fldData"))
            self.fstack.append({"instr_parts": [], "phase": "instr", "start": None, "kind": None,
                                "data": [data.text] if data is not None and data.text else [],
                                "deleted": self._deleting() is not None, "begin": (para, para.len)})
        elif typ == "separate" and self.fstack:
            f = self.fstack[-1]
            if f["phase"] == "instr":
                f["phase"] = "result"
                f["start"] = (para, para.len)
                f["instr"] = "".join(f["instr_parts"])
                f["kind"] = _field_kind(f["instr"])
                para.field_kinds.add(f["kind"])
        elif typ == "end" and self.fstack:
            f = self.fstack.pop()
            if f["start"] is None:
                f["start"] = (para, para.len)
                f["instr"] = "".join(f["instr_parts"])
                f["kind"] = _field_kind(f["instr"])
            f["end"] = (para, para.len)
            if self.fstack and self.fstack[-1]["phase"] == "instr":
                self.fstack[-1]["data"].extend(f["data"])
                self.fstack[-1].setdefault("nested", []).append(f)
            self._field_done(f)

    def _field_done(self, f: dict) -> None:
        if f.get("deleted"):
            return
        self.fields.append(f)
        self.field_counts[f["kind"]] += 1

    def _drawing(self, el, para: _Para) -> None:
        doc_pr = el.find(f".//{q('wp:docPr')}")
        files = []
        for blip in el.iter(q("a:blip")):
            rid = blip.get(q("r:embed")) or blip.get(q("r:link"))
            if rid and rid in self.rels:
                files.append(self.rels[rid][0])
        kind = "picture" if files else "shape"
        for chart in el.iter(q("c:chart")):
            rid = chart.get(q("r:id"))
            if rid and rid in self.rels:
                files.append(self.rels[rid][0])
                kind = "chart"
        if any(_local(g.get("uri") or "").endswith("diagram") or "diagram" in (g.get("uri") or "")
               for g in el.iter(q("a:graphicData"))):
            kind = "diagram"
        boxes = [tb for tb in el.iter(W_TXBX)]
        para.textboxes.extend(boxes)
        if files or kind == "diagram" or not boxes:
            para.images.append({"files": files, "kind": kind, "alt": (doc_pr.get("descr") if doc_pr is not None else None),
                                "title": doc_pr.get("title") if doc_pr is not None else None,
                                "name": doc_pr.get("name") if doc_pr is not None else None,
                                "floating": el.find(q("wp:anchor")) is not None})

    def _pict(self, el, para: _Para) -> None:
        files = []
        for img in el.iter(q("v:imagedata")):
            rid = img.get(q("r:id"))
            if rid and rid in self.rels:
                files.append(self.rels[rid][0])
        boxes = list(el.iter(W_TXBX))
        para.textboxes.extend(boxes)
        if files:
            para.images.append({"files": files, "kind": "picture", "alt": None, "title": None, "name": None,
                                "floating": False})

    def _object(self, el, para: _Para) -> None:
        ole = el.find(f".//{q('o:OLEObject')}")
        prog = (ole.get("ProgID") if ole is not None else "") or ""
        if prog.lower().startswith("equation") or "mathtype" in prog.lower() or "dsmt" in prog.lower():
            para.ole_equation = True
            return
        files = [self.rels[i.get(q("r:id"))][0] for i in el.iter(q("v:imagedata")) if i.get(q("r:id")) in self.rels]
        para.images.append({"files": files, "kind": "object", "alt": None, "title": prog or None, "name": None,
                            "floating": False})

    def _block_content(self, parent, story: str, out: list, *, in_table=False, cell_bg=None) -> None:
        """Walk block-level content (body, cell, note, comment, text box) into `out`."""
        for child in parent:
            tag = child.tag
            if tag == W_P:
                out.append(self._paragraph(child, story, in_table=in_table, cell_bg=cell_bg))
            elif tag == W_TBL:
                if story == "body" and not in_table:
                    out.append(self._table(child))
                else:  # nested table, or a table in a note: flatten its paragraphs in order
                    nested = self._table(child, story=story)
                    out.extend(nested.paras())
            elif tag == W_SDT:
                pr = child.find(W_SDTPR)
                kind = self._sdt_kind(pr)
                content = child.find(W_SDTCONTENT)
                if content is not None:
                    self.sdt_stack.append(kind)
                    self._block_content(content, story, out, in_table=in_table, cell_bg=cell_bg)
                    self.sdt_stack.pop()
            elif tag == q("w:customXml"):
                self._block_content(child, story, out, in_table=in_table, cell_bg=cell_bg)
            elif tag == q("w:sectPr"):
                self.sect_prs.append(child)
            elif tag in (q("w:bookmarkStart"), q("w:commentRangeStart")):
                self.pending_marks.append(child)  # placed at the start of the next paragraph
            elif tag in (q("w:bookmarkEnd"), q("w:commentRangeEnd")):
                if self.all_paras:
                    self._inline([child], self.all_paras[-1])
                else:
                    self.pending_marks.append(child)
            elif tag == MC_ALT:
                choice = child.find(MC_CHOICE)
                if choice is not None:
                    self._block_content(choice, story, out, in_table=in_table, cell_bg=cell_bg)

    @staticmethod
    def _sdt_kind(pr) -> str:
        if pr is None:
            return "sdt"
        gallery = _val(pr.find(f".//{q('w:docPartGallery')}")) or ""
        tag = _val(pr.find(q("w:tag"))) or ""
        if "contents" in gallery.lower():
            return "toc"
        if "bibliograph" in gallery.lower() or tag.upper().startswith(("MENDELEY_BIBLIOGRAPHY", "CITAVI_BIBLIOGRAPHY")):
            return "bibliography"
        return "sdt"

    def _table(self, tbl, story: str = "body") -> _TableItem:
        item = _TableItem(tbl)
        item.first_number = self.n_par + 1 if story == "body" else None
        for tr in _children(tbl, W_TR):
            trpr = tr.find(q("w:trPr"))
            deleted = trpr is not None and trpr.find(W_DEL) is not None
            inserted = trpr.find(W_INS) if trpr is not None else None
            cells = []
            for tc in _children(tr, W_TC):
                cell = _Cell()
                tcpr = tc.find(q("w:tcPr"))
                if tcpr is not None:
                    span = _val(tcpr.find(q("w:gridSpan")))
                    cell.span = int(span) if span and span.isdigit() else 1
                    vm = tcpr.find(q("w:vMerge"))
                    cell.vmerge_continue = vm is not None and (vm.get(W_VAL) or "continue") == "continue"
                    shd = tcpr.find(q("w:shd"))
                    bg = shd.get(q("w:fill")) if shd is not None else None
                else:
                    bg = None
                self._block_content(tc, story, cell.paras, in_table=True, cell_bg=bg)
                cells.append(cell)
            if deleted:
                # one note for the deleted row instead of one per cell and paragraph mark
                texts = []
                for c in cells:
                    parts = []
                    for cp in c.paras:
                        removed = [ch for ch in cp.changes if ch["kind"] == "tracked_deletion"]
                        cp.changes = [ch for ch in cp.changes if ch["kind"] != "tracked_deletion"]
                        parts += [ch["text"] for ch in removed if ch.get("text")] or ([cp.text] if cp.text else [])
                    texts.append(" ".join(x.strip() for x in parts if x.strip()))
                first = next((cp for c in cells for cp in c.paras), None)
                row_del = trpr.find(W_DEL)
                if first is not None and any(texts):
                    first.changes.append({"kind": "tracked_deletion", "start": 0, "end": 0, "text": " | ".join(texts),
                                          "author": row_del.get(W_AUTHOR), "date": row_del.get(W_DATE),
                                          "detail": "table row"})
            if inserted is not None and cells and cells[0].paras:
                cells[0].paras[0].changes.append({
                    "kind": "tracked_insertion", "start": 0, "end": 0,
                    "text": " | ".join(" ".join(p.text for p in c.paras).strip() for c in cells),
                    "author": inserted.get(W_AUTHOR), "date": inserted.get(W_DATE), "detail": "table row"})
            item.rows.append((cells, deleted, None))
        return item

    def _walk_story(self, root, story: str) -> list:
        saved = (self.fstack, self.chg, self.sdt_stack)
        self.fstack, self.chg, self.sdt_stack = [], [], []
        out: list = []
        self._block_content(root, story, out)
        self.fstack, self.chg, self.sdt_stack = saved
        return [p for p in out if isinstance(p, _Para)]

    def _walk(self) -> None:
        self.rels = self.pkg.main_rels
        body = self.doc.find(q("w:body"))
        if body is None:
            raise SystemExit(f"{self.path}: the main document has no body.")
        self._block_content(body, "body", self.items)
        if self.fstack:
            self.pm.warnings.append(f"{len(self.fstack)} field(s) were not closed at the end of the document.")
            self.fstack = []
        # text boxes: a separate story anchored at the paragraph holding the drawing
        self.textbox_paras: dict = {}
        for para in list(self.all_paras):
            for tb in para.textboxes:
                inner = self._walk_story(tb, "textbox")
                for ip in inner:
                    ip.anchor_number = para.anchor_number
                self.textbox_paras.setdefault(id(para), []).extend(inner)
        for kind in ("footnote", "endnote"):
            for name in self.pkg.related(f"/{kind}s"):
                self.rels = self.pkg.rels(name)
                root = self.pkg.xml(name)
                if root is None:
                    continue
                for note in root.iter(q(f"w:{kind}")):
                    if (note.get(q("w:type")) or "normal") != "normal":
                        continue
                    self.notes_paras[kind][note.get(W_ID)] = self._walk_story(note, kind)
        for name in self.pkg.related("/comments"):
            self.rels = self.pkg.rels(name)
            root = self.pkg.xml(name)
            if root is None:
                continue
            for c in root.iter(q("w:comment")):
                paras = self._walk_story(c, "comment")
                self.comments[c.get(W_ID)] = {
                    "author": c.get(W_AUTHOR), "date": c.get(W_DATE), "initials": c.get(q("w:initials")),
                    "text": " ".join(p.text for p in paras if p.text).strip(), "paras": paras,
                    "para_ids": [p.el.get(q("w14:paraId")) for p in paras if p.el is not None and p.el.get(q("w14:paraId"))]}
        self.headers_footers = []
        for kind in ("header", "footer"):
            for name in self.pkg.related(f"/{kind}"):
                self.rels = self.pkg.rels(name)
                root = self.pkg.xml(name)
                if root is None:
                    continue
                paras = self._walk_story(root, kind)
                self.headers_footers.append({"kind": kind, "part": name, "paras": paras})
        self.rels = self.pkg.main_rels

    # -- classification --------------------------------------------------
    def _heading_info(self, p: _Para) -> Optional[dict]:
        """Level, number and display text when the paragraph is a heading."""
        text = p.text.strip()
        if not text or p.in_table or p.story != "body" or "toc" in p.sdt_kinds or "toc" in p.field_kinds:
            return None
        names = self.styles.names(p.style)
        if names and (names[0].startswith("toc") or names[0] in ("title", "subtitle", "caption")):
            return None
        level = self.styles.heading_level(p.style) if p.style else None
        level = level or p.outline
        source = "style" if level else None
        words = len(text.split())
        short = len(text) <= 160 and words <= 16
        name = _norm_heading(text)
        if level is None and short:
            bold = p.all_flag(1)
            ends_ok = not re.search(r"[,;:]$", text) and not (text.endswith(".") and words > 8)
            am = _APPX_HEAD.match(text)
            if bold and ends_ok and am and (am.group("num") or name in ("appendix", "appendices", "online appendix")):
                level, source = 1, "bold numbered"
            elif bold and ends_ok and _NUM_HEAD.match(text) and not _CAPTION.match(text):
                num = _NUM_HEAD.match(text).group("num")
                level, source = min(num.count(".") + 1, 6), "bold numbered"
            elif bold and ends_ok and name in KNOWN_HEADINGS:
                level, source = 1, "bold name"
            elif name in REF_HEADINGS | ACK_HEADINGS | {"abstract"} and words <= 3:
                level, source = 1, "name"
        if level is None:
            return None
        label = p.num_label if source == "style" and p.num_label else None
        display = f"{label} {text}" if label and label != "•" else text
        number = None
        am = _APPX_HEAD.match(display)
        if am and am.group("num"):
            number = am.group("num")
        else:
            m = re.match(r"^(\d{1,2}(?:\.\d{1,2}){0,3}|[A-Z](?:\.\d{1,2}){0,3}|[IVX]{1,5}(?=\.))\.?\s", display)
            if m:
                number = m.group(1)
        # "4.2" is a second-level heading whatever its style says; drafts often mix heading styles.
        if number and source == "style" and re.fullmatch(r"(?:\d{1,2}|[A-Z])(?:\.\d{1,2})*", number):
            by_number = number.count(".") + 1
            if by_number != level:
                level, source = by_number, "style, level from numbering"
        return {"level": level, "number": number, "text": display, "source": source, "name": _norm_heading(display),
                "appendix": bool(am), "label": label}

    @staticmethod
    def _looks_like_names(text: str) -> bool:
        if "@" in text or len(text) > 200:
            return False
        t = re.sub(r"[*†‡§¶#]|\(\d+\)|(?<=[A-Za-z])\d+\b|\b\d+\b", " ", text)
        parts = [x.strip() for x in re.split(r"\s*(?:,|;|\band\b|&)\s*", t) if x.strip()]
        if not parts or len(parts) > 15:
            return False
        for part in parts:
            toks = part.split()
            if not 2 <= len(toks) <= 5:
                return False
            if any(tok.lower().strip(".") in _NOT_NAME for tok in toks):
                return False
            if not all(re.fullmatch(r"[A-ZÀ-Þ][\w'’.-]*|[A-Z]\.(?:-?[A-Z]\.)*", tok) or tok in _PARTICLES
                       for tok in toks):
                return False
            if toks[-1] in _PARTICLES:
                return False
        return True

    def _adjacent_float(self, idx: int) -> Optional[str]:
        for step in (1, -1):
            j = idx + step
            while 0 <= j < len(self.items):
                it = self.items[j]
                if isinstance(it, _TableItem):
                    return "table"
                if it.text.strip() or it.images:
                    if it.images and len(it.text.strip()) < 10:
                        return "figure"
                    break
                j += step
        return None

    def _caption_kind(self, p: _Para, idx: int) -> Optional[str]:
        """'table' or 'figure' (or 'caption') when the paragraph is a caption."""
        text = p.text.strip()
        names = self.styles.names(p.style)
        m = _CAPTION.match(text)
        styled = any(n == "caption" or n.startswith("caption") or n in ("table caption", "figure caption",
                                                                         "table title", "figure title")
                     for n in names[:2])
        kind = None
        if m:
            kind = "table" if m.group("kind").lower() == "table" else "figure"
        if styled:
            return kind or self._adjacent_float(idx) or "caption"
        if not m:
            return None
        rest = m.group("rest")
        if re.match(r"\s*[:.—–-]|\s*$", rest):
            return kind
        if len(text.split()) <= 25 and not text.rstrip().endswith(".") and self._adjacent_float(idx):
            return kind
        return None

    def _classify(self) -> None:
        items = self.items
        for it in items:
            if isinstance(it, _Para):
                it.heading = self._heading_info(it)
        state, front, in_abstract = "front", "start", False
        in_refs = in_ack = None
        bib_open = False  # inside a reference manager's bibliography field without a References heading
        abstract_seen = False
        for idx, it in enumerate(items):
            if isinstance(it, _TableItem):
                self._classify_table(it)
                if state == "front" and front != "start":
                    state = "body"
                if in_refs is not None or bib_open:
                    in_refs = None
                    bib_open = False
                    it.after_refs = True
                continue
            p = it
            text = p.text.strip()
            names = self.styles.names(p.style)
            if "toc" in p.sdt_kinds or "toc" in p.field_kinds or (names and names[0].startswith("toc ")):
                p.role = "toc" if text else "empty"
                continue
            if not text:
                p.role = "figure_image" if any(i["kind"] != "shape" for i in p.images) else "empty"
                continue
            if "bibliography" in p.field_kinds or "bibliography" in p.sdt_kinds or (names and names[0] == "bibliography"):
                p.role = "reference"
                bib_open = in_refs is None
                continue
            if bib_open and not p.heading:
                cap = self._caption_kind(p, idx)
                if cap in ("table", "figure"):
                    bib_open = False
                    p.after_refs = True
                    p.role, p.caption_kind = "caption", cap
                    continue
            h = p.heading
            if h:
                bib_open = False
                if h["name"] == "abstract":
                    p.role = "abstract_label"
                    in_abstract = abstract_seen = True
                    continue
                p.role = "heading"
                state = "body"
                in_abstract = False
                if in_refs is not None and h["level"] <= in_refs:
                    in_refs = None
                if in_ack is not None and h["level"] <= in_ack:
                    in_ack = None
                if h["name"] in REF_HEADINGS:
                    in_refs = h["level"]
                elif h["name"] in ACK_HEADINGS:
                    in_ack = h["level"]
                continue
            if names and names[0] == "title":
                p.role = "title"
                front = "title"
                continue
            if in_refs is not None:
                cap = self._caption_kind(p, idx)
                if cap in ("table", "figure"):
                    in_refs = None
                    p.after_refs = True
                    p.role, p.caption_kind = "caption", cap
                    continue
                p.role = "reference"
                continue
            if in_ack is not None:
                p.role = "acknowledgment"
                continue
            cap = self._caption_kind(p, idx)
            if cap:
                p.role, p.caption_kind = "caption", cap
                continue
            # a display equation: OMML or an equation object, with at most a number such as "(1)" beside it
            if (p.math or p.ole_equation) and re.fullmatch(r"[^A-Za-z]{0,12}?(?:\(\s*[A-Z]?\d+[a-z]?\s*\))?[\s.,;]*",
                                                           self._nonmath(p).strip()):
                p.role = "equation"
                continue
            if state == "front":
                role = self._front_role(p, text, front, in_abstract, abstract_seen, idx)
                p.role = role
                if role == "title":
                    front = "title"
                elif role == "abstract":
                    abstract_seen = True
                    if p.prefix_cut:
                        in_abstract = False
                elif role in ("paragraph",) and not _JEL_KW.match(text):
                    state = "body"
                    in_abstract = False
                elif _JEL_KW.match(text):
                    in_abstract = False
                if front == "start" and role != "front_matter":
                    front = "title"
                continue
            if p.num_label is not None:
                p.role = "list_item"
                continue
            p.role = "paragraph"

    @staticmethod
    def _nonmath(p: _Para) -> str:
        """Text of the paragraph outside its equations."""
        return "".join(p.text[s:e] for s, e in p.plain) if p.math else p.text

    def _front_role(self, p: _Para, text: str, front: str, in_abstract: bool, abstract_seen: bool, idx: int) -> str:
        words = len(text.split())
        if _ABSTRACT_START.match(text) and words > 3:
            p.prefix_cut = len(_ABSTRACT_START.match(text).group(0)) + (len(p.text) - len(p.text.lstrip()))
            return "abstract"
        if in_abstract:
            return "paragraph" if _JEL_KW.match(text) else "abstract"
        if _JEL_KW.match(text):
            return "paragraph"
        if _ACK_START.match(text):
            return "acknowledgment"
        if front == "start":
            if re.search(r"\b(?:draft|do not (?:cite|circulate|distribute)|working paper|preliminary|this version|"
                         r"version\b|comments welcome|job market paper)", text, re.I) and words <= 15:
                return "front_matter"
            if words <= 35 and not text.endswith(".") or (words <= 35 and (p.all_flag(1) or p.align == "center")):
                return "title"
        if self._looks_like_names(text):
            return "author"
        if words <= 20 and not abstract_seen:
            return "front_matter"
        if words <= 12:
            return "front_matter"
        if not abstract_seen and words >= 40 and self._abstract_follows(idx):
            return "abstract"
        return "paragraph"

    def _abstract_follows(self, idx: int) -> bool:
        """An unlabeled abstract: a long front paragraph followed by keywords, JEL codes or the first heading."""
        for it in self.items[idx + 1: idx + 4]:
            if isinstance(it, _TableItem):
                return False
            t = it.text.strip()
            if not t:
                continue
            return bool(_JEL_KW.match(t) or it.heading)
        return False

    def _classify_table(self, item: _TableItem) -> None:
        math = any(p.math for p in item.paras())
        if math and len(item.rows) == 1 and all(
                p.math or re.fullmatch(r"\(\s*[A-Z]?\d+[a-z]?\s*\)", p.text.strip()) or not p.text.strip()
                for p in item.paras()):
            item.equation = True

    def _link_floats(self) -> None:
        """Attach captions and notes to tables and figures, then number every float in document order."""
        items = self.items
        used: set = set()

        def next_item(j, step):
            while 0 <= j < len(items) and isinstance(items[j], _Para) and items[j].role == "empty":
                j += step
            return items[j] if 0 <= j < len(items) else None

        for idx, it in enumerate(items):
            if isinstance(it, _TableItem):
                if it.equation:
                    continue
                caps = []
                j = idx - 1
                while j >= 0 and isinstance(items[j], _Para) and items[j].role in ("caption", "empty"):
                    if items[j].role == "caption":
                        if id(items[j]) in used or items[j].caption_kind == "figure":
                            break
                        caps.insert(0, items[j])
                    j -= 1
                    if caps and items[j + 1].role == "empty":
                        break
                if not caps:
                    below = next_item(idx + 1, 1)
                    if isinstance(below, _Para) and below.role == "caption" and id(below) not in used \
                            and below.caption_kind in ("table", "caption"):
                        caps = [below]
                it.caption = caps
                for c in caps:
                    used.add(id(c))
                    c.caption_of = it
                if caps:
                    m = _CAPTION.match(caps[0].text.strip())
                    it.number = m.group("num") if m and m.group("kind").lower() == "table" else None
                    for c in caps[1:]:
                        c.role = "caption_cont"
                # notes: paragraphs right after the table (after a caption placed below it)
                j = idx + 1
                while j < len(items) and isinstance(items[j], _Para) and (items[j].role == "empty" or id(items[j]) in used):
                    j += 1
                while j < len(items) and isinstance(items[j], _Para) and items[j].role in ("paragraph", "list_item", "caption") \
                        and id(items[j]) not in used and self._is_table_note(items[j]):
                    items[j].role = "table_notes"
                    it.notes.append(items[j])
                    j += 1
            elif isinstance(it, _Para) and it.role == "figure_image":
                it.number, it.caption_para = None, None
                for step in (1, -1):
                    cap = next_item(idx + step, step)
                    if not (isinstance(cap, _Para) and cap.role == "caption" and id(cap) not in used):
                        continue
                    if cap.caption_kind == "table":
                        # a table pasted as a picture, unless the caption belongs to a real table beyond it
                        if isinstance(next_item(items.index(cap) + step, step), _TableItem):
                            continue
                        it.as_table = True
                    used.add(id(cap))
                    cap.caption_of, it.caption_para = it, cap
                    m = _CAPTION.match(cap.text.strip())
                    it.number = m.group("num") if m else None
                    break
        for it in items:
            if isinstance(it, _Para) and it.role == "caption" and id(it) not in used:
                m = _CAPTION.match(it.text.strip())
                it.caption_of = None
                it.orphan_kind = ("table" if m.group("kind").lower() == "table" else "figure") if m else None
                it.orphan_number = m.group("num") if m else None
        n_table = n_fig = 0
        for it in items:
            if isinstance(it, _TableItem):
                if not it.equation:
                    n_table += 1
                    it.table_id = f"t{n_table}"
            elif it.role == "figure_image":
                if getattr(it, "as_table", False):
                    n_table += 1
                    it.figure_id = f"t{n_table}"
                else:
                    n_fig += 1
                    it.figure_id = f"f{n_fig}"
            elif it.role == "caption" and getattr(it, "orphan_kind", None) and it.orphan_number:
                if it.orphan_kind == "table":
                    n_table += 1
                    it.orphan_id = f"t{n_table}"
                else:
                    n_fig += 1
                    it.orphan_id = f"f{n_fig}"

    def _is_table_note(self, p: _Para) -> bool:
        text = p.text.strip()
        names = self.styles.names(p.style)
        if _NOTES_START.match(text):
            return True
        return bool(names) and "note" in names[0] and "foot" not in names[0] and "end" not in names[0]

    # -- blocks ------------------------------------------------------------
    def _make_block(self, kind: str, paras: list, *, level=None, attrs=None, parent=None, sep: str = " ",
                    anchor_number=None) -> Block:
        bid = self._new_id()
        parts, pos = [], 0
        members = [p for p in paras if p.text] or paras[:1]
        for k, p in enumerate(members):
            if k and sep:
                parts.append(sep)
                pos += len(sep)
            ptxt = p.text[p.prefix_cut:]
            p.block, p.block_offset = bid, pos - p.prefix_cut
            parts.append(ptxt)
            pos += len(ptxt)
        number = anchor_number if anchor_number is not None else next(
            (p.anchor_number for p in paras if p.anchor_number), None)
        block = Block(id=bid, kind=kind, text="".join(parts), anchor=Anchor(paragraph=number),
                      section=list(self.section_path), level=level, parent=parent, attrs=dict(attrs or {}))
        self.pm.blocks.append(block)
        self.block_paras[bid] = members
        return block

    def _build(self) -> None:
        self.note_counter = Counter()
        appendix = False
        last_block = None
        for idx, it in enumerate(self.items):
            if getattr(it, "after_refs", False):
                self.section_path = ["Tables and figures"]
            if isinstance(it, _TableItem):
                if it.equation:
                    paras = [p for p in it.paras() if p.text]
                    if paras:
                        m = re.search(r"\(\s*([A-Z]?\d+[a-z]?)\s*\)\s*$", " ".join(p.text for p in paras))
                        last_block = self._make_block("equation", paras, attrs={"number": m.group(1) if m else None,
                                                                                 "layout_table": True})
                        self._equation_label(last_block)
                else:
                    last_block = self._table_block(it)
                for p in it.paras():
                    self._note_blocks(p, last_block)
                    self._textbox_blocks(p, last_block)
                continue
            p = it
            role = p.role
            block = None
            if role == "heading":
                h = p.heading
                if h["appendix"] or (h["level"] == 1 and h["name"] in ("appendix", "appendices", "online appendix")):
                    appendix = True
                elif appendix and h["level"] == 1 and h["name"] not in REF_HEADINGS | ACK_HEADINGS \
                        and not (h["number"] and re.fullmatch(r"[A-Z](?:\.\d+)*", h["number"])):
                    appendix = h["name"] not in KNOWN_HEADINGS  # e.g. "Proofs" stays in the appendix, "Conclusion" does not
                depth = max(h["level"], 1)
                self.section_path = self.section_path[:depth - 1] + [h["text"]]
                attrs = {"number": h["number"], "style": self.styles.name(p.style) if p.style else None,
                         "detected": h["source"], "appendix": appendix or h["appendix"]}
                if h["label"]:
                    attrs["numbering"] = h["label"]
                block = self._make_block("heading", [p], level=h["level"], attrs={k: v for k, v in attrs.items() if v})
                if h["label"] and h["text"] != p.text:
                    block.text = h["text"]
                    p.block_offset = len(block.text) - len(p.text)
                self.headings.append((block, h, appendix or h["appendix"]))
            elif role == "abstract_label":
                self.section_path = [p.text.strip()]
                block = self._make_block("heading", [p], level=(p.heading or {}).get("level") or 1,
                                         attrs={"detected": (p.heading or {}).get("source"), "abstract_label": True})
            elif role in ("empty", "table_notes", "caption_cont"):
                block = None
            elif role == "figure_image":
                if p.caption_para is None:
                    self._figure(p, None)
                if p.text.strip():
                    block = self._make_block("other", [p], attrs={"figure": p.figure_id})
            elif role == "caption":
                block = self._caption_block(p, idx)
            elif role == "reference":
                if not self.section_path or _norm_heading(self.section_path[-1]) not in REF_HEADINGS:
                    self.section_path = ["References"]  # a bibliography field with no heading of its own
                block = self._reference_block(p)
            elif role == "equation":
                m = re.search(r"\(\s*([A-Z]?\d+[a-z]?)\s*\)[\s.,;]*$", self._nonmath(p))
                block = self._make_block("equation", [p], attrs={"number": m.group(1) if m else None})
                self._equation_label(block)
            else:
                kind = {"title": "title", "author": "author", "front_matter": "front_matter", "abstract": "abstract",
                        "paragraph": "paragraph", "list_item": "list_item", "acknowledgment": "acknowledgment",
                        "toc": "other"}.get(role, "paragraph")
                attrs = {}
                if role == "list_item":
                    attrs = {"label": p.num_label or None, "level": (p.num[1] if p.num else None)}
                elif role == "toc":
                    attrs = {"toc": True}
                elif role == "abstract" and p.prefix_cut:
                    attrs = {"label": p.text[:p.prefix_cut].strip()}
                block = self._make_block(kind, [p], attrs={k: v for k, v in attrs.items() if v is not None})
            if block is not None:
                last_block = block
            self._note_blocks(p, last_block)
            self._textbox_blocks(p, last_block)

    def _equation_label(self, block: Block) -> None:
        num = block.attrs.get("number")
        if num:
            self._add_label(f"equation:{num}", "equation", num, block)

    def _add_label(self, name: str, kind: str, number, block: Optional[Block]) -> None:
        if name in self.label_index:
            return
        lab = Label(name=name, kind=kind, number=number, anchor=Anchor(paragraph=block.anchor.paragraph) if block else Anchor(),
                    block=block.id if block else None)
        self.label_index[name] = lab
        self.pm.labels.append(lab)

    def _caption_block(self, p: _Para, idx: int) -> Block:
        target = getattr(p, "caption_of", None)
        paras = [p]
        if isinstance(target, _TableItem) and len(target.caption) > 1:
            paras = target.caption
        if isinstance(target, _TableItem):
            kind, fid, number = "table", target.table_id, target.number
        elif target is not None:
            as_table = getattr(target, "as_table", False)
            kind, fid, number = ("table" if as_table else "figure"), target.figure_id, target.number
        else:
            kind, fid, number = getattr(p, "orphan_kind", None), None, getattr(p, "orphan_number", None)
        attrs = {"float": kind, "number": number, "label": f"{kind}:{number}" if kind and number else None,
                 "float_id": fid, "style": self.styles.name(p.style) if p.style else None}
        block = self._make_block("caption", paras, attrs={k: v for k, v in attrs.items() if v})
        p.caption_block = block
        if isinstance(target, _TableItem) and getattr(target, "table_obj", None) is not None:
            # the caption sits below its table, whose block is already out
            target.table_obj.caption = self._strip_caption_label(block.text)
            target.table_obj.caption_block = block.id
            target.block.parent = target.block.parent or block.id
        if target is None and kind in ("table", "figure") and number:
            # a caption with no table or picture beside it: the content is an object the reader cannot see, or missing
            fid = getattr(p, "orphan_id", None)
            caption = self._strip_caption_label(block.text)
            if kind == "figure":
                self.pm.figures.append(Figure(id=fid, anchor=Anchor(paragraph=p.anchor_number), caption=caption,
                                              label=f"figure:{number}", number=number, caption_block=block.id))
            else:
                self.pm.tables.append(Table(id=fid, anchor=Anchor(paragraph=p.anchor_number), caption=caption,
                                            label=f"table:{number}", number=number, caption_block=block.id))
                self.pm.metadata.setdefault("tables_without_content", []).append(fid)
            block.attrs["float_id"] = fid
            self._add_label(f"{kind}:{number}", kind, number, block)
        elif target is not None and not isinstance(target, _TableItem):
            self._figure(target, block)
        return block

    @staticmethod
    def _strip_caption_label(text: str) -> str:
        return re.sub(r"^(?:Table|Figure|Fig\.|Exhibit|Chart)\s+(?:[A-Z]{0,2}\d+[a-z]?|[IVX]{1,6}|[A-Z])\s*[:.—–-]?\s*",
                      "", text).strip()

    def _figure(self, img_para: _Para, caption_block: Optional[Block]) -> None:
        number = getattr(img_para, "number", None)
        files = [f for i in img_para.images for f in i["files"]]
        caption = self._strip_caption_label(caption_block.text) if caption_block else ""
        if getattr(img_para, "as_table", False):
            tid = img_para.figure_id
            self.pm.tables.append(Table(id=tid, anchor=Anchor(paragraph=img_para.anchor_number), caption=caption,
                                        label=f"table:{number}" if number else None, number=number,
                                        caption_block=caption_block.id if caption_block else None,
                                        raw=f"image: {', '.join(files)}" if files else None))
            self.pm.metadata.setdefault("tables_as_images", []).append(tid)
            if number:
                self._add_label(f"table:{number}", "table", number, caption_block)
            return
        self.pm.figures.append(Figure(id=img_para.figure_id, anchor=Anchor(paragraph=img_para.anchor_number),
                                      caption=caption, label=f"figure:{number}" if number else None, number=number,
                                      caption_block=caption_block.id if caption_block else None, files=files))
        img_para.figure_done = True
        if number:
            self._add_label(f"figure:{number}", "figure", number, caption_block)

    def _table_block(self, item: _TableItem) -> Block:
        lines, rows, line_paras = [], [], []
        for cells, deleted, _chg in item.rows:
            if deleted:
                continue
            row, row_paras = [], []
            for c in cells:
                ptexts, offs, pos = [], [], 0
                if not c.vmerge_continue:
                    for p in c.paras:
                        if p.text:
                            if ptexts:
                                pos += 1
                            offs.append((p, pos))
                            ptexts.append(p.text)
                            pos += len(p.text)
                row.append(" ".join(ptexts))
                row_paras.append(offs)
                for _ in range(c.span - 1):
                    row.append("")
                    row_paras.append([])
            rows.append(row)
            line_paras.append(row_paras)
        notes_paras = []
        if len(rows) > 1:
            nonempty = [k for k, x in enumerate(rows[-1]) if x]
            if len(nonempty) == 1 and _NOTES_START.match(rows[-1][nonempty[0]]):
                notes_paras = [p for p, _ in line_paras[-1][nonempty[0]]]
                rows.pop()
                line_paras.pop()
        keep = [k for k, r in enumerate(rows) if any(r)]
        rows = [rows[k] for k in keep]
        line_paras = [line_paras[k] for k in keep]
        text_parts, pos = [], 0
        bid = f"b{self.n_block + 1:04d}"
        for r_i, (row, rparas) in enumerate(zip(rows, line_paras)):
            line, where = _collapse_spaces(" | ".join(row))
            if r_i:
                text_parts.append("\n")
                pos += 1
            cell_start = 0
            for cell_text, offs in zip(row, rparas):
                for p, off in offs:
                    p.block, p.block_offset = bid, pos + where(cell_start + off)
                cell_start += len(cell_text) + 3
            text_parts.append(line)
            pos += len(line)
            lines.append(line)
        note_texts = [p.text for p in notes_paras + item.notes if p.text]
        notes = " ".join(note_texts)
        if notes:
            prefix = "" if re.match(r"\s*notes?\b", notes, re.I) else "Notes: "
            text_parts.append("\n" + prefix)
            pos += 1 + len(prefix)
            for p in notes_paras + item.notes:
                if p.text:
                    p.block, p.block_offset = bid, pos
                    pos += len(p.text) + 1
            text_parts.append(notes)
        caption_block = getattr(item.caption[0], "caption_block", None) if item.caption else None
        number = item.number
        label = f"table:{number}" if number else None
        members = [p for p in item.paras() if p.block == bid] + [p for p in notes_paras + item.notes if p.text]
        block = Block(id=self._new_id(), kind="table", text="".join(text_parts),
                      anchor=Anchor(paragraph=item.first_number), section=list(self.section_path),
                      parent=caption_block.id if caption_block else None,
                      attrs={k: v for k, v in {"number": number, "label": label, "table_id": item.table_id}.items() if v})
        assert block.id == bid
        self.pm.blocks.append(block)
        self.block_paras[block.id] = members
        caption_text = self._strip_caption_label(caption_block.text) if caption_block else ""
        table = Table(id=item.table_id, anchor=Anchor(paragraph=item.first_number), caption=caption_text,
                      label=label, number=number, caption_block=caption_block.id if caption_block else None,
                      rows=rows, notes=(prefix + notes) if notes else "")
        self.pm.tables.append(table)
        item.table_obj, item.block = table, block
        if number:
            self._add_label(label, "table", number, caption_block or block)
        return block

    def _note_blocks(self, p: _Para, parent: Optional[Block]) -> None:
        for raw_off, kind, nid, custom in p.note_refs:
            paras = self.notes_paras[kind].get(nid)
            if paras is None:
                self.pm.warnings.append(f"The {kind} with id {nid} referenced in paragraph {p.anchor_number} is missing.")
                continue
            if custom:
                tail = "".join(p.pieces)[raw_off:raw_off + 3]
                number = tail.split()[0] if tail.split() else "*"
            else:
                self.note_counter[kind] += 1
                number = format_number(self.note_counter[kind] + self.note_start[kind] - 1, self.note_fmt[kind])
            for np_ in paras:
                np_.anchor_number = p.anchor_number
            text = " ".join(np_.text for np_ in paras if np_.text)
            front = parent is not None and parent.kind in ("title", "author")
            block_kind = "acknowledgment" if front or _ACK_START.match(text) else "footnote"
            if not text:
                continue
            self._make_block(block_kind, paras, parent=parent.id if parent else None, anchor_number=p.anchor_number,
                             attrs={"number": number, "note_id": nid, "note_type": kind})
            for np_ in paras:
                self._note_blocks(np_, parent)

    def _textbox_blocks(self, p: _Para, parent: Optional[Block]) -> None:
        for tp in self.textbox_paras.get(id(p), []):
            if tp.text:
                self._make_block("other", [tp], parent=parent.id if parent else None, anchor_number=p.anchor_number,
                                 attrs={"textbox": True})
                self._note_blocks(tp, parent)

    def _reference_block(self, p: _Para) -> Block:
        text = p.text
        italics = [(s, e) for s, e, fl in p.segments() if fl[0]]
        fields = parse_reference(text, italics)
        if p.num_label and p.num_label != "•" and "label" not in fields:
            fields["label"] = p.num_label  # "[1]" from Word's list numbering, not typed
        idx = len(self.pm.references) + 1
        key = ref_key(fields, self.ref_keys)
        ref = Reference(id=f"r{idx:03d}", raw=text, anchor=Anchor(paragraph=p.anchor_number), source="reference_list",
                        key=key, fields=fields)
        self.pm.references.append(ref)
        self.ref_printed[ref.id] = dict(fields)
        block = self._make_block("reference", [p], attrs={"ref": ref.id, "key": key})
        return block

    # -- positions ----------------------------------------------------------
    def _block_pos(self, mark) -> Optional[tuple]:
        para, raw = mark
        if para.block is None:
            return None
        block = self.pm.block(para.block)
        if block is None:
            return None
        return block, max(0, min(len(block.text), para.block_offset + para.pos(raw)))

    def _span(self, start, end) -> Optional[tuple]:
        a = self._block_pos(start)
        if a is None:
            return None
        b = self._block_pos(end) if end else None
        e = b[1] if b is not None and b[0].id == a[0].id else len(a[0].text)
        return a[0], a[1], max(a[1], e)

    def _text_between(self, start, end, limit: int = 400) -> str:
        if not start:
            return ""
        (pa, ra) = start
        (pb, rb) = end or start
        if pa is pb:
            return pa.text[pa.pos(ra):pa.pos(rb)].strip()
        if pa.seq > pb.seq:
            return ""
        out = [pa.text[pa.pos(ra):]]
        for p in self.all_paras[pa.seq + 1:pb.seq]:
            out.append(p.text)
            if sum(len(x) for x in out) > limit:
                break
        out.append(pb.text[:pb.pos(rb)])
        return " ".join(x for x in out if x).strip()[:limit]

    # -- reference-manager citations ----------------------------------------
    def _field_items(self, f: dict) -> tuple:
        """Parse a citation field into (items, manager); each item has fields and an id."""
        kind, instr = f["kind"], f.get("instr") or ""
        items = []
        if kind in ("zotero", "mendeley"):
            i, j = instr.find("{"), instr.rfind("}")
            data = None
            if i >= 0 and j > i:
                try:
                    data = json.loads(instr[i:j + 1])
                except json.JSONDecodeError as exc:
                    self.pm.warnings.append(f"Could not read the {kind} citation data ({exc}).")
            if isinstance(data, dict):
                for ci in data.get("citationItems") or []:
                    item = ci.get("itemData") or {}
                    uris = ci.get("uris") or ci.get("uri") or []
                    items.append({"fields": csl_fields(item), "id": str(ci.get("id") or item.get("id") or ""),
                                  "uris": uris if isinstance(uris, list) else [uris],
                                  "locator": ci.get("locator"), "data": item})
                f["display"] = ((data.get("properties") or {}).get("plainCitation")
                                or (data.get("mendeley") or {}).get("plainTextFormattedCitation"))
                f["edited"] = bool((data.get("properties") or {}).get("dontUpdate")
                                   or (data.get("mendeley") or {}).get("manualFormatting"))
        elif kind == "mendeley_v3":
            payload = instr[len("MENDELEY_CITATION_v3_"):]
            try:
                data = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8"))
            except Exception as exc:
                data = None
                self.pm.warnings.append(f"Could not read a Mendeley Cite citation ({type(exc).__name__}).")
            if isinstance(data, dict):
                for ci in data.get("citationItems") or []:
                    item = ci.get("itemData") or {}
                    items.append({"fields": csl_fields(item), "id": str(ci.get("id") or item.get("id") or ""),
                                  "uris": [], "data": item})
            kind = "mendeley"
        elif kind == "endnote":
            xml = None
            m = re.search(r"<EndNote>.*</EndNote>", instr, re.S)
            if m:
                xml = m.group(0)
            else:
                for blob in f.get("data") or []:
                    try:
                        raw = base64.b64decode(re.sub(r"\s+", "", blob))
                    except Exception:
                        continue
                    for enc in ("utf-8", "utf-16"):
                        try:
                            s = raw.decode(enc)
                        except UnicodeDecodeError:
                            continue
                        m = re.search(r"<EndNote>.*</EndNote>", s, re.S)
                        if m:
                            xml = m.group(0)
                            break
                    if xml:
                        break
            if xml:
                try:
                    root = etree.fromstring(xml.encode("utf-8"), PARSER)
                    for cite in root.iter("Cite"):
                        fields, rec = _endnote_fields(cite)
                        items.append({"fields": fields, "id": rec or "", "uris": [], "data": None})
                except etree.XMLSyntaxError as exc:
                    self.pm.warnings.append(f"Could not read EndNote citation data ({exc}).")
        elif kind == "word_citation":
            toks = instr.split()
            tags = [toks[1]] if len(toks) > 1 else []
            tags += [toks[k + 1] for k, t in enumerate(toks[:-1]) if t.lower() == "\\m"]
            for tag in tags:
                src = self.word_sources.get(tag)
                if src is not None:
                    items.append({"fields": src, "id": tag, "uris": [], "data": None})
                else:
                    items.append({"fields": {}, "id": tag, "uris": [], "data": None, "missing": True})
            kind = "word"
        return items, kind

    def _load_word_sources(self) -> None:
        self.word_sources = {}
        for name in sorted(n for n in self.pkg.infos if re.fullmatch(r"customXml/item\d+\.xml", n)):
            root = self.pkg.xml(name)
            if root is None or root.tag != q("b:Sources"):
                continue
            for src in root.iter(q("b:Source")):
                tag = src.find(q("b:Tag"))
                if tag is not None and tag.text:
                    self.word_sources[tag.text.strip()] = _word_source_fields(src)

    def _title_ratio(self, a: Optional[str], b: Optional[str]) -> float:
        if not a or not b:
            return 0.0
        a, b = _ascii(a).lower(), _ascii(b).lower()
        try:
            from rapidfuzz import fuzz
            return fuzz.token_sort_ratio(a, b)
        except ImportError:  # pragma: no cover - rapidfuzz is a core dependency
            import difflib
            return 100 * difflib.SequenceMatcher(None, a, b).ratio()

    def _match_fields(self, fields: dict) -> Optional[Reference]:
        """The printed reference that a reference manager's item describes."""
        authors = fields.get("authors") or []
        fam = norm_name(authors[0]["family"]) if authors else ""
        year = fields.get("year")
        title = fields.get("title")
        doi = (fields.get("doi") or "").lower()
        scored = []
        for r in self.pm.references:
            pf = self.ref_printed.get(r.id, r.fields)
            pa = pf.get("authors") or []
            rfam = norm_name(pa[0]["family"]) if pa else ""
            score = 0
            if doi and (pf.get("doi") or "").lower() == doi:
                score += 2
            if fam and rfam == fam:
                score += 2
            if year and pf.get("year") == year:
                score += 1
            ratio = self._title_ratio(title, pf.get("title"))
            if ratio >= 90:
                score += 3
            elif ratio >= 75:
                score += 1
            if (fam and rfam == fam and year and pf.get("year") == year) or ratio >= 90 and (rfam == fam or not fam):
                scored.append((score, ratio, r))
        if not scored:
            return None
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return scored[0][2]

    def _field_citations(self) -> None:
        self.manager_items: dict = {}
        unmatched: list = []
        cites = []
        for f in self.fields:
            if f["kind"] not in ("zotero", "mendeley", "endnote", "word_citation", "mendeley_v3"):
                continue
            items, manager = self._field_items(f)
            cites.append((f, items, manager))
        has_list = bool(self.pm.references)
        if not has_list and any(items for _, items, _ in cites):
            self._references_from_fields(cites)
        for f, items, manager in cites:
            keys, ok = [], True
            for item in items:
                ref = self._match_fields(item["fields"]) if item["fields"] else None
                if ref is None:
                    ok = False
                    key = ref_key(item["fields"], set()) if item["fields"] else f"?{item.get('id')}"
                    keys.append(key)
                    unmatched.append((key, item, manager))
                    continue
                keys.append(ref.id)
                self._merge_manager_data(ref, item, manager)
            if not items:
                continue
            span = self._span(f["start"], f["end"])
            if span is None:
                continue
            block, s, e = span
            display = block.text[s:e]
            if f.get("display") and re.sub(r"\W", "", f["display"]) != re.sub(r"\W", "", display):
                self.stale_fields.append({"field": manager, "paragraph": block.anchor.paragraph, "shown": display,
                                          "expected": f["display"], "block": block.id,
                                          "reason": "edited by hand" if f.get("edited") else "differs from the stored citation"})
            raw = (f.get("instr") or "").strip()
            block.citations.append(Citation(keys=keys, start=s, end=e, command=manager, raw=raw[:20000],
                                            resolved=ok))
        self.unmatched_manager_items = unmatched

    def _merge_manager_data(self, ref: Reference, item: dict, manager: str) -> None:
        printed = self.ref_printed.get(ref.id, {})
        exact = item["fields"]
        if ref.id not in self.manager_items:
            for k, label in (("year", "year"), ("title", "title")):
                a, b = printed.get(k), exact.get(k)
                if a and b and (a != b if k == "year" else self._title_ratio(a, b) < 90):
                    self.pm.warnings.append(f"Reference {ref.id}: the printed entry and the {manager} data differ in "
                                            f"{label} ({a!r} printed, {b!r} in {manager}).")
            merged = dict(printed)
            merged.update({k: v for k, v in exact.items() if v not in (None, "", [])})
            ref.fields = merged
            ref.source = manager
        self.manager_items.setdefault(ref.id, {"manager": manager, "ids": [], "uris": []})
        entry = self.manager_items[ref.id]
        if item.get("id") and item["id"] not in entry["ids"]:
            entry["ids"].append(item["id"])
        for u in item.get("uris") or []:
            if u not in entry["uris"]:
                entry["uris"].append(u)

    def _references_from_fields(self, cites: list) -> None:
        """No printed reference list: build one from the reference manager's data, as BibTeX would."""
        seen, unique = set(), []
        for _f, items, manager in cites:
            for item in items:
                fields = item["fields"]
                if not fields:
                    continue
                ident = (fields.get("doi") or "").lower() or norm_name(fields.get("title") or "") or item.get("id")
                if ident in seen:
                    continue
                seen.add(ident)
                unique.append((fields, manager))
        if not unique:
            return
        unique.sort(key=lambda x: (norm_name((x[0].get("authors") or [{"family": ""}])[0]["family"]), x[0].get("year") or ""))
        self.pm.warnings.append("No reference list was found in the document; the references were taken from the "
                                "reference manager's field codes.")
        self.pm.metadata["reference_list"] = "generated from field codes"
        heading = Block(id=self._new_id(), kind="heading", text="References", anchor=Anchor(), section=["References"],
                        level=1, attrs={"generated": True})
        self.pm.blocks.append(heading)
        for fields, manager in unique:
            idx = len(self.pm.references) + 1
            names = "; ".join(f"{a['family']}, {a.get('given', '')}".strip(", ") for a in fields.get("authors") or [])
            bits = [names, f"({fields.get('year', 'n.d.')})", fields.get("title"), fields.get("container"),
                    fields.get("volume"), fields.get("pages"), fields.get("doi") and f"doi:{fields['doi']}"]
            raw = ". ".join(str(b).rstrip(".") for b in bits if b)
            key = ref_key(fields, self.ref_keys)
            ref = Reference(id=f"r{idx:03d}", raw=raw, anchor=Anchor(), source=manager, key=key, fields=dict(fields))
            self.pm.references.append(ref)
            self.ref_printed[ref.id] = dict(fields)
            self.pm.blocks.append(Block(id=self._new_id(), kind="reference", text=raw, anchor=Anchor(),
                                        section=["References"], attrs={"ref": ref.id, "key": key, "generated": True}))

    # -- plain-text citations -------------------------------------------------
    @staticmethod
    def _families(authors: str) -> tuple:
        et_al = bool(re.search(r"\bet\s+al\b", authors))
        a = re.sub(r"\s+et\s+al\.?", "", authors)
        fams = [x.strip() for x in re.split(r"\s*,\s*|\s+(?:and|&)\s+", a) if x.strip()]
        return fams, et_al

    @staticmethod
    def _years(text: str) -> list:
        out, prev = [], None
        for tok in re.split(r"\s*,\s*", text.strip()):
            tok = tok.strip()
            if re.fullmatch(r"[a-z]", tok) and prev:
                out.append(prev[:4] + tok)
            elif tok:
                out.append(tok)
                prev = tok
        return out

    def _author_index(self) -> dict:
        """References by normalized first-author family name, printed and reference-manager versions."""
        index: dict = {}
        for r in self.pm.references:
            for f in (self.ref_printed.get(r.id) or {}, r.fields):
                authors = f.get("authors") or []
                if authors:
                    index.setdefault(norm_name(authors[0]["family"]), []).append((r, f))
        return index

    def _match_text(self, fams: list, et_al: bool, year: str) -> Optional[str]:
        """The reference id that an author-year citation names: first author and year must match;
        coauthors, "et al." and the year suffix break ties."""
        key = (tuple(fams), et_al, year)
        if key in self.match_cache:
            return self.match_cache[key]
        y = year[:4] if year[:4].isdigit() else None
        suffix = year[4:] if y else ""
        note = None if y else re.sub(r"\W", "", year.lower())
        cands, seen = [], set()
        for r, f in self.author_index.get(norm_name(fams[0]), []):
            if r.id in seen or (y and f.get("year") != y):
                continue
            if note and re.sub(r"\W", "", (f.get("year_note") or "")) != note:
                continue
            if suffix and f.get("year_suffix") and f.get("year_suffix") != suffix:
                continue
            cands.append((r, f))
            seen.add(r.id)
        if not cands:
            self.match_cache[key] = None
            return None

        def score(rf):
            r, f = rf
            authors = f.get("authors") or []
            s = 0
            if et_al:
                s += 2 if len(authors) >= 3 else (1 if len(authors) == 2 else 0)
            else:
                if len(authors) == len(fams):
                    s += 2
                    if all(norm_name(a["family"]) == norm_name(b) for a, b in zip(authors, fams)):
                        s += 3
            if suffix and f.get("year_suffix") == suffix:
                s += 4
            return s
        cands.sort(key=score, reverse=True)
        self.match_cache[key] = cands[0][0].id
        return cands[0][0].id

    def _text_citations(self) -> None:
        self.author_index, self.match_cache = self._author_index(), {}
        numbered = sum(1 for r in self.pm.references if re.fullmatch(r"\[\d+\]|\d+\.", r.fields.get("label") or ""))
        by_label = {re.sub(r"\D", "", r.fields.get("label") or ""): r for r in self.pm.references}
        for block in self.pm.blocks:
            if block.kind not in CITE_KINDS or block.attrs.get("toc"):
                continue
            taken = [(c.start, c.end) for c in block.citations]
            found = []
            for m in PAREN.finditer(block.text):
                if _within(taken, m.start(), m.end()):
                    continue
                keys, ok, parts = [], True, 0
                inner_start = m.start("inner")
                for pm_ in re.finditer(r"[^;]+", m.group("inner")):
                    part = pm_.group(0)
                    pmatch = PART.search(part)
                    if not pmatch:
                        continue
                    fams, et_al = self._families(pmatch.group("authors"))
                    prefix = part[:pmatch.start()]
                    years = self._years(pmatch.group("years"))
                    ids = [self._match_text(fams, et_al, y) for y in years]
                    plausible = not prefix.strip() or _LEADIN.search(prefix) is not None
                    if not any(ids) and (not plausible or fams[0].lower() in _NOT_SURNAME):
                        continue
                    parts += 1
                    for y, rid in zip(years, ids):
                        if rid:
                            keys.append(rid)
                        else:
                            ok = False
                            keys.append(norm_name(fams[0]) + (y if y[:4].isdigit() else re.sub(r"\W", "", y)))
                if parts:
                    found.append(Citation(keys=keys, start=m.start(), end=m.end(), command="parenthetical",
                                          raw=m.group(0), resolved=ok))
                    taken.append((m.start(), m.end()))
            for m in NARRATIVE.finditer(block.text):
                if _within(taken, m.start(), m.end()):
                    continue
                fams, et_al = self._families(m.group("authors"))
                if any(f.lower() in _NOT_SURNAME for f in fams[:1]):
                    years = self._years(m.group("years"))
                    if not all(self._match_text(fams, et_al, y) for y in years):
                        continue
                years = self._years(m.group("years"))
                ids = [self._match_text(fams, et_al, y) for y in years]
                before = block.text[max(0, m.start() - 30):m.start()]
                if not any(ids) and re.search(r"[A-Z][a-z]+\s+$", before) and not re.search(
                        r"(?:^|[.!?]\s+|\b(?:In|As|See|Following|Like|Unlike|While|Whereas|And|But|Both|Also|Then|"
                        r"Recently|However|Thus|Hence|Indeed|Similarly|Building on|Contrary to)\s+)$", before):
                    continue
                keys = [rid or norm_name(fams[0]) + (y if y[:4].isdigit() else re.sub(r"\W", "", y))
                        for y, rid in zip(years, ids)]
                found.append(Citation(keys=keys, start=m.start(), end=m.end(), command="narrative", raw=m.group(0),
                                      resolved=all(ids)))
                taken.append((m.start(), m.end()))
            if numbered >= max(2, len(self.pm.references) // 2):
                for m in re.finditer(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]", block.text):
                    if _within(taken, m.start(), m.end()):
                        continue
                    nums = _expand_labels(m.group(1))
                    keys = [by_label[n].id if n in by_label else f"[{n}]" for n in nums]
                    found.append(Citation(keys=keys, start=m.start(), end=m.end(), command="numeric", raw=m.group(0),
                                          resolved=all(n in by_label for n in nums)))
            block.citations.extend(found)
            block.citations.sort(key=lambda c: c.start)

    # -- cross-references -------------------------------------------------------
    def _register_labels(self) -> None:
        for block, h, appendix in self.headings:
            num = h["number"]
            if not num:
                continue
            if appendix or h["appendix"]:
                self._add_label(f"appendix:{num}", "appendix", num, block)
            self._add_label(f"section:{num}", "section", num, block)

    def _resolve_xref(self, kind: str, label: str) -> tuple:
        if kind in ("appendix_table", "appendix_figure"):
            kind = kind.split("_")[1]
        if kind == "online_appendix":
            name = f"appendix:{label}"
            return name, name in self.label_index
        name = f"{kind}:{label}"
        if kind == "section" and name not in self.label_index and f"appendix:{label}" in self.label_index:
            return f"appendix:{label}", True
        return name, name in self.label_index

    def _bookmark_target(self, name: str) -> tuple:
        """(canonical label or None, number or None, current text) of a bookmark."""
        bm = self.bm_by_name.get(name)
        if bm is None:
            return None, None, None
        para = bm["start"][0]
        text = self._text_between(bm["start"], bm.get("end"), 200)
        if para.role == "caption" or getattr(para, "caption_block", None):
            blk = getattr(para, "caption_block", None)
            if blk is not None and blk.attrs.get("label"):
                return blk.attrs["label"], blk.attrs.get("number"), text
        if para.role == "heading" and para.heading:
            num = para.heading.get("number")
            if num:
                lab = f"appendix:{num}" if f"appendix:{num}" in self.label_index else f"section:{num}"
                return lab, num, text
        if para.role == "equation" and para.block:
            blk = self.pm.block(para.block)
            if blk is not None and blk.attrs.get("number"):
                return f"equation:{blk.attrs['number']}", blk.attrs["number"], text
        if para.note_refs:
            return None, None, text
        return None, None, text

    def _crossrefs(self) -> None:
        self.bm_by_name = {}
        for bm in self.bookmarks.values():
            if bm.get("name") and bm["name"] not in self.bm_by_name:
                self.bm_by_name[bm["name"]] = bm
        for f in self.fields:
            if f["kind"] not in ("ref", "noteref"):
                continue
            toks = (f.get("instr") or "").split()
            name = toks[1].strip('"') if len(toks) > 1 else ""
            switches = {t.lower() for t in toks[2:] if t.startswith("\\")}
            span = self._span(f["start"], f["end"])
            if span is None:
                continue
            block, s, e = span
            shown = block.text[s:e]
            label, number, target_text = self._bookmark_target(name)
            exists = name in self.bm_by_name
            resolved = exists and not _ERROR_FIELD.search(shown)
            if exists and f["kind"] == "noteref":
                label = None
            stale = None
            if _ERROR_FIELD.search(shown):
                stale = "shows an error"
            elif not exists:
                stale = "bookmark missing"
            elif switches & {"\\r", "\\n", "\\w"} and number and re.sub(r"\W", "", shown) != re.sub(r"\W", "", number):
                stale = "number out of date"
            elif not switches & {"\\r", "\\n", "\\w", "\\p"} and target_text is not None and f["kind"] == "ref" \
                    and re.sub(r"\s+", " ", target_text).strip() != re.sub(r"\s+", " ", shown).strip():
                stale = "text out of date"
            if stale:
                self.stale_fields.append({"field": "REF" if f["kind"] == "ref" else "NOTEREF", "bookmark": name,
                                          "paragraph": block.anchor.paragraph, "block": block.id, "shown": shown,
                                          "expected": target_text, "reason": stale})
            block.crossrefs.append(CrossRef(labels=[label or name], start=s, end=e, command=f["kind"].upper(),
                                            raw=(f.get("instr") or "").strip(), resolved=bool(resolved)))
        for block in self.pm.blocks:
            if block.kind in ("heading", "reference", "equation") or block.attrs.get("toc"):
                continue
            taken = [(c.start, c.end) for c in block.citations] + [(r.start, r.end) for r in block.crossrefs]
            for m in CROSSREF.finditer(block.text):
                if _within(taken, m.start(), m.end()):
                    continue
                if block.kind == "caption" and m.start() == 0:
                    continue
                kind = _xref_kind(m.group("kind"))
                labels, ok = [], True
                for lab in _expand_labels(m.group("labels")):
                    name, resolved = self._resolve_xref(kind, lab)
                    labels.append(name)
                    ok = ok and resolved
                if not labels:
                    continue
                block.crossrefs.append(CrossRef(labels=labels, start=m.start(), end=m.end(), command="text",
                                                raw=m.group(0), resolved=ok))
                taken.append((m.start(), m.end()))
            block.crossrefs.sort(key=lambda r: r.start)

    # -- notes ------------------------------------------------------------------
    def _notes(self) -> None:
        notes = self.pm.notes
        extended = {}
        for name in self.pkg.related("/commentsExtended"):
            root = self.pkg.xml(name)
            if root is None:
                continue
            for ex in root.iter(q("w15:commentEx")):
                extended[ex.get(q("w15:paraId"))] = {"parent": ex.get(q("w15:paraIdParent")),
                                                     "done": (ex.get(q("w15:done")) or "0") in ("1", "true")}
        para_to_comment = {}
        for cid, info in self.comments.items():
            for pid in info["para_ids"]:
                para_to_comment[pid] = cid
        threads = []
        for cid, info in sorted(self.comments.items(), key=lambda kv: int(kv[0]) if (kv[0] or "").lstrip("-").isdigit() else 0):
            marks = self.comment_marks.get(cid, {})
            start = marks.get("start") or marks.get("ref")
            end = marks.get("end") or marks.get("ref")
            anchor_no = start[0].anchor_number if start else None
            passage = self._text_between(start, end, 300) if start else ""
            ex = extended.get(info["para_ids"][-1]) if info["para_ids"] else None
            parent = para_to_comment.get(ex["parent"]) if ex and ex.get("parent") else None
            notes.append(Note(kind="comment", text=info["text"], anchor=Anchor(paragraph=anchor_no),
                              author=info["author"], date=info["date"], detail=passage or None))
            threads.append({k: v for k, v in {"id": cid, "author": info["author"], "initials": info["initials"],
                                              "date": info["date"], "paragraph": anchor_no, "passage": passage or None,
                                              "reply_to": parent, "resolved": bool(ex and ex["done"]),
                                              "text": info["text"]}.items() if v not in (None, "")})
        if threads:
            self.pm.metadata["comments"] = threads
        order = {"body": 0, "textbox": 1, "footnote": 2, "endnote": 2}
        stories = sorted((p for p in self.all_paras if p.story in order),
                         key=lambda p: (p.anchor_number or 0, order[p.story], p.seq))
        for p in stories:
            self._change_notes(p)
        for p in stories:
            self._hidden_notes(p, Anchor(paragraph=p.anchor_number), None)
        for hf in self.headers_footers:
            for p in hf["paras"]:
                self._hidden_notes(p, Anchor(), hf["kind"])
                self._change_notes(p, where=hf["kind"])

    def _change_notes(self, p: _Para, where: Optional[str] = None) -> None:
        merged: list = []
        for c in p.changes:
            if c.get("mark") and any(o["kind"] == c["kind"] and not o.get("mark") for o in p.changes):
                continue
            prev = merged[-1] if merged else None
            if prev and prev["kind"] == c["kind"] and prev["author"] == c["author"] and prev["date"] == c["date"] \
                    and prev.get("detail") == c.get("detail") and c["kind"] != "tracked_format_change" \
                    and prev.get("end") is not None and c.get("start") is not None \
                    and (prev["end"] == c["start"] or (c["kind"] == "tracked_deletion" and prev["start"] == c["start"])):
                prev["text"] = (prev["text"] or "") + (c["text"] or "")
                prev["end"] = c["end"]
                continue
            if prev and c["kind"] == "tracked_format_change" and prev["kind"] == c["kind"] \
                    and prev.get("detail") == c.get("detail") == "run properties" and prev["author"] == c["author"]:
                prev["text"] = (prev["text"] or "") + (c["text"] or "")
                continue
            merged.append(dict(c))
        for c in merged:
            text = c["text"]
            if text is None:
                text = p.text[:200]
            detail = c.get("detail")
            if where:
                detail = f"{detail}; in the {where}" if detail else f"in the {where}"
            self.pm.notes.append(Note(kind=c["kind"], text=text, anchor=Anchor(paragraph=p.anchor_number),
                                      author=c.get("author"), date=c.get("date"), detail=detail))

    def _hidden_notes(self, p: _Para, anchor: Anchor, where: Optional[str]) -> None:
        run = None
        segs = []
        for s, e, flags in p.segments():
            kind = flags[2]
            if run and kind == run[2] and s <= run[1] + 1:
                run[1] = e
            else:
                if run:
                    segs.append(run)
                run = [s, e, kind]
        if run:
            segs.append(run)
        for s, e, kind in segs:
            text = p.text[s:e].strip()
            if kind and text:
                self.pm.notes.append(Note(kind="hidden_text", text=text, anchor=anchor,
                                          detail=f"{kind} in the {where}" if where else kind))

    def _block_attrs(self) -> None:
        for block in self.pm.blocks:
            paras = self.block_paras.get(block.id) or []
            total = hidden = 0
            kinds: Counter = Counter()
            highlights, links = [], []
            for p in paras:
                if p.block != block.id:
                    continue
                for s, e, flags in p.segments():
                    if s < p.prefix_cut:
                        s = p.prefix_cut
                    if e <= s:
                        continue
                    n = sum(1 for ch in p.text[s:e] if not ch.isspace())
                    total += n
                    if flags[2]:
                        hidden += n
                        kinds[flags[2]] += n
                    if flags[3]:
                        a, b = p.block_offset + s, p.block_offset + e
                        if highlights and highlights[-1]["end"] >= a - 1 and highlights[-1]["color"] == flags[3]:
                            highlights[-1]["end"] = b
                        else:
                            highlights.append({"start": a, "end": b, "color": flags[3]})
                for s, e, target in p.links:
                    a, b = p.block_offset + p.pos(s), p.block_offset + p.pos(e)
                    if b > a:
                        links.append({"start": a, "end": b, "url": target})
            if hidden:
                kind = kinds.most_common(1)[0][0]
                block.attrs["hidden"] = kind if hidden >= total else f"partly {kind}"
            if highlights:
                block.attrs["highlights"] = highlights
            if links:
                block.attrs["links"] = links
        # hyperlinks written as HYPERLINK fields
        for f in self.fields:
            if f["kind"] != "hyperlink":
                continue
            m = re.search(r'HYPERLINK\s+(?:\\l\s+)?"([^"]+)"', f.get("instr") or "", re.I)
            span = self._span(f["start"], f["end"])
            if m and span and span[2] > span[1]:
                block, s, e = span
                target = m.group(1) if not re.search(r"\\l", f["instr"]) else "#" + m.group(1)
                block.attrs.setdefault("links", []).append({"start": s, "end": e, "url": target})

    # -- metadata ---------------------------------------------------------------
    def _properties(self) -> dict:
        out: dict = {}
        core_name = next((t for t, typ, ext in self.pkg.root_rels.values() if typ.endswith("/core-properties")),
                         "docProps/core.xml")
        core = self.pkg.xml(core_name if self.pkg.has(core_name) else None)
        if core is not None:
            for tag, key in (("dc:title", "title"), ("dc:subject", "subject"), ("dc:creator", "author"),
                             ("cp:keywords", "keywords"), ("dc:description", "description"),
                             ("cp:lastModifiedBy", "last_modified_by"), ("cp:revision", "revision"),
                             ("cp:lastPrinted", "last_printed"), ("dcterms:created", "created"),
                             ("dcterms:modified", "modified"), ("cp:category", "category"),
                             ("cp:contentStatus", "content_status"), ("dc:language", "language"),
                             ("dc:identifier", "identifier")):
                el = core.find(q(tag))
                if el is not None and (el.text or "").strip():
                    out[key] = el.text.strip()
        app_name = next((t for t, typ, ext in self.pkg.root_rels.values() if typ.endswith("/extended-properties")), None)
        app = self.pkg.xml(app_name if app_name and self.pkg.has(app_name) else None)
        if app is not None:
            for tag, key in (("Company", "company"), ("Manager", "manager"), ("Application", "application"),
                             ("AppVersion", "app_version"), ("Template", "template"),
                             ("TotalTime", "total_editing_minutes"), ("Pages", "pages"), ("Words", "words"),
                             ("Characters", "characters"), ("HyperlinkBase", "hyperlink_base")):
                el = app.find(q("ep:" + tag))
                if el is not None and (el.text or "").strip():
                    v = el.text.strip()
                    out[key] = int(v) if v.isdigit() and key in ("total_editing_minutes", "pages", "words", "characters") else v
        custom_name = next((t for t, typ, ext in self.pkg.root_rels.values() if typ.endswith("/custom-properties")), None)
        custom = self.pkg.xml(custom_name if custom_name and self.pkg.has(custom_name) else None)
        if custom is not None:
            props = {}
            for prop in custom:
                name = prop.get("name")
                value = next((c.text for c in prop if c.text), None)
                if name and value is not None:
                    props[name] = value.strip()
            if props:
                out["custom"] = props
        return out

    @staticmethod
    def _section_info(sect) -> dict:
        def tw(el, attr):
            v = el.get(q("w:" + attr)) if el is not None else None
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return None
        sz, mar = sect.find(q("w:pgSz")), sect.find(q("w:pgMar"))
        info: dict = {}
        w, h = tw(sz, "w"), tw(sz, "h")
        if w and h:
            info.update({"width_in": round(w / 1440, 3), "height_in": round(h / 1440, 3),
                         "width_pt": round(w / 20, 1), "height_pt": round(h / 20, 1),
                         "orientation": (sz.get(q("w:orient")) or ("landscape" if w > h else "portrait"))})
            short, long_ = sorted((w, h))
            for name, (a, b) in (("Letter", (12240, 15840)), ("A4", (11906, 16838)), ("Legal", (12240, 20160)),
                                 ("A5", (8391, 11906)), ("B5", (9979, 14175))):
                if abs(short - a) <= 30 and abs(long_ - b) <= 30:
                    info["paper"] = name
        if mar is not None:
            margins = {k: round(tw(mar, k) / 1440, 3) for k in ("top", "bottom", "left", "right", "header", "footer", "gutter")
                       if tw(mar, k) is not None}
            info["margins_in"] = margins
        cols = sect.find(q("w:cols"))
        if cols is not None and (cols.get(q("w:num")) or "1").isdigit() and int(cols.get(q("w:num")) or "1") > 1:
            info["columns"] = int(cols.get(q("w:num")))
        lines = sect.find(q("w:lnNumType"))
        if lines is not None:
            info["line_numbers"] = True
        return info

    def _metadata(self) -> None:
        md = self.pm.metadata
        md["document_properties"] = self._properties()
        sections = [self._section_info(s) for s in self.sect_prs]
        sections = [s for s in sections if s]
        if sections:
            md["page"] = sections[0]
            if len(sections) > 1 and any(s != sections[0] for s in sections[1:]):
                md["sections"] = sections
        st = self.styles
        body_font = st.font_of(st.rpr(None, None, "w:rFonts"))
        body_size = _val(st.rpr(None, None, "w:sz"))
        fonts: dict = {"body": {k: v for k, v in {"name": body_font, "size_pt": int(body_size) / 2 if body_size and
                                                  body_size.isdigit() else None}.items() if v}}
        used: Counter = Counter()
        for p in self.all_paras:
            if p.story == "body":
                used.update(p.fonts)
        if used:
            fonts["used"] = [{"name": name, "size_pt": size, "chars": n} for (name, size), n in used.most_common(15)]
        md["fonts"] = fonts
        spacing = st.ppr(None, "w:spacing")
        if spacing is None and st.doc_ppr is not None:
            spacing = st.doc_ppr.find(q("w:spacing"))
        if spacing is not None and spacing.get(q("w:line")):
            rule = spacing.get(q("w:lineRule")) or "auto"
            line = int(spacing.get(q("w:line")))
            md["line_spacing"] = round(line / 240, 2) if rule == "auto" else {"rule": rule, "points": line / 20}
        lang = st.doc_rpr.find(q("w:lang")) if st.doc_rpr is not None else None
        if lang is not None and lang.get(W_VAL):
            md["language"] = lang.get(W_VAL)
        md["paragraph_count"] = self.n_par
        md["paragraph_numbering"] = ("anchor.paragraph counts every w:p of the main document in order from 1, "
                                     "including empty paragraphs and table cells; notes, comments, text boxes, "
                                     "headers and footers are not counted")
        if self.field_counts:
            md["fields"] = dict(sorted(self.field_counts.items()))
        managers = Counter(c.command for b in self.pm.blocks for c in b.citations
                           if c.command in ("zotero", "mendeley", "endnote", "word"))
        if managers:
            md["reference_manager"] = dict(managers)
        if self.manager_items:
            md["reference_manager_items"] = self.manager_items
        missing, seen = [], set()
        for key, item, manager in self.unmatched_manager_items:
            if key not in seen and item.get("fields"):
                seen.add(key)
                missing.append({"key": key, "manager": manager, "fields": item["fields"]})
        if missing:
            md["cited_items_missing_from_list"] = missing
        if self.settings is not None:
            md["track_revisions"] = self.settings.find(q("w:trackRevisions")) is not None
        if self.stale_fields:
            md["stale_fields"] = self.stale_fields
        images = []
        for p in self.all_paras:
            for img in p.images:
                images.append({k: v for k, v in {"paragraph": p.anchor_number, "files": img["files"], "kind": img["kind"],
                                                 "alt_text": img["alt"], "title": img["title"], "name": img["name"],
                                                 "floating": img["floating"] or None,
                                                 "figure": getattr(p, "figure_id", None)}.items() if v not in (None, [], "")})
        if images:
            md["images"] = images
        hf = []
        for item in self.headers_footers:
            text = " / ".join(p.text for p in item["paras"] if p.text)
            if text:
                hf.append({"kind": item["kind"], "part": item["part"], "text": text})
        if hf:
            md["headers_footers"] = hf
        if any(n.endswith("vbaProject.bin") for n in self.pkg.infos):
            md["has_macros"] = True
        unresolved = sorted({k for b in self.pm.blocks for c in b.citations if not c.resolved for k in c.keys
                             if self.pm.reference(k) is None})
        md["cited_keys_missing_from_bib"] = unresolved
        cited = {k for b in self.pm.blocks for c in b.citations for k in c.keys}
        md["uncited_references"] = [r.id for r in self.pm.references if r.id not in cited]

    # -- main -------------------------------------------------------------------
    def read(self) -> PaperMap:
        self._load_parts()
        self.note_fmt = {"footnote": "decimal", "endnote": "lowerRoman"}
        self.note_start = {"footnote": 1, "endnote": 1}
        if self.settings is not None:
            for kind in ("footnote", "endnote"):
                pr = self.settings.find(q(f"w:{kind}Pr"))
                if pr is not None:
                    self.note_fmt[kind] = _val(pr.find(q("w:numFmt"))) or self.note_fmt[kind]
                    start = _val(pr.find(q("w:numStart")))
                    if start and start.isdigit():
                        self.note_start[kind] = int(start)
        self._load_word_sources()
        self.ref_keys: set = set()
        self.ref_printed: dict = {}
        self._walk()
        self._classify()
        self._link_floats()
        self._build()
        self._field_citations()
        self._register_labels()
        self._text_citations()
        self._crossrefs()
        self._notes()
        self._block_attrs()
        title = next((b for b in self.pm.blocks if b.kind == "title"), None)
        props = self._properties()
        self.pm.title = title.text if title else props.get("title", "")
        authors = []
        for b in self.pm.blocks:
            if b.kind == "author":
                text = re.sub(r"[*†‡§¶]|(?<=[A-Za-z])\d+\b", "", b.text)
                authors += [a.strip() for a in re.split(r"\s*(?:,|;|\band\b|&)\s*", text) if a.strip()]
        self.pm.authors = authors
        self._metadata()
        return self.pm


def _collapse_spaces(line: str) -> tuple:
    """Collapse runs of spaces and strip, as the LaTeX reader's table text does; returns the text and an offset map."""
    out, where, prev = [], [], False
    for ch in line:
        where.append(len(out))
        if ch == " " and prev:
            continue
        out.append(ch)
        prev = ch == " "
    where.append(len(out))
    text = "".join(out)
    lead = len(text) - len(text.lstrip())
    text = text.strip()
    return text, lambda i: max(0, min(len(text), where[min(i, len(where) - 1)] - lead))


def _children(el, tag):
    """Direct children with `tag`, looking through content controls and custom XML wrappers."""
    for child in el:
        if child.tag == tag:
            yield child
        elif child.tag in (W_SDT, q("w:customXml")):
            holder = child.find(W_SDTCONTENT) if child.tag == W_SDT else child
            if holder is not None:
                yield from _children(holder, tag)


def _field_kind(instr: str) -> str:
    s = (instr or "").strip()
    up = s.upper()
    if up.startswith("ADDIN"):
        rest = up[5:].strip()
        for prefix, kind in (("ZOTERO_ITEM", "zotero"), ("ZOTERO_BIBL", "bibliography"), ("CSL_CITATION", "mendeley"),
                             ("MENDELEY BIBLIOGRAPHY", "bibliography"), ("EN.CITE.DATA", "endnote_data"),
                             ("EN.CITE", "endnote"), ("EN.REFLIST", "bibliography"), ("CITAVI", "citavi"),
                             ("PAPERS2_CITATIONS", "papers"), ("RW.CITE", "refworks"), ("RW.BIB", "bibliography")):
            if rest.startswith(prefix):
                return kind
        if "CSL_BIBLIOGRAPHY" in rest:
            return "bibliography"
        return "addin"
    first = up.split()[0] if up.split() else ""
    return {"REF": "ref", "NOTEREF": "noteref", "PAGEREF": "pageref", "SEQ": "seq", "TOC": "toc",
            "HYPERLINK": "hyperlink", "CITATION": "word_citation", "BIBLIOGRAPHY": "bibliography"}.get(
        first, first.lower() or "empty")


def read_docx(path: Path) -> PaperMap:
    return DocxReader(path).read()
