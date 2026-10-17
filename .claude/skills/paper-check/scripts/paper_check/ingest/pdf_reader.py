"""PDF reader: a .pdf file into a PaperMap.

Every block's text is built from the characters of the PDF's text layer, in
reading order, so quotes can be checked against the PDF. Structure is inferred
with heuristics:

  1. Characters with positions, fonts, sizes and colours come from pdfplumber.
     Document information, fonts, links and comments come from pypdf.
  2. Characters are grouped into tokens and lines. Superscripts stay on their
     line and are marked, so that footnote markers can be matched to their
     footnotes and left out of the text. White or near-white characters, and
     characters under 2 points, are hidden text.
  3. Lines in the top and bottom margins whose text repeats across pages, with
     digits ignored, are running heads. Lone numbers there are page numbers.
     Both are dropped.
  4. Each page is checked for a column gutter. On a two-column page, lines that
     cross the gutter split the page into bands, and within a band the left
     column is read before the right one.
  5. Small text at the bottom of a page or column, below a short rule or opening
     with a marker, is footnotes.
  6. Blocks: the front matter of page 1 (title, authors, date, abstract, JEL and
     keyword lines), headings (size, weight and numbering), captions, tables
     (cells found by word alignment, not by ruling lines), equations,
     paragraphs (vertical gaps and indentation; a paragraph may continue into
     the next column or page), footnotes, and the reference list after a
     "References" heading.
  7. Author-year citations, matched to references by family name and year, and
     cross-references such as "Table 1", "Appendix A" or "Table ??", become
     spans.

Anchors are {"page", "page_line", "bbox"}. page_line counts the visible lines
of the page in reading order, leaving out running heads and page numbers; a
line made only of hidden text shares the number of the next visible line.
bbox is [x0, top, x1, bottom] in points from the page's top-left corner, and
covers the block's lines on its first page. attrs["lines"] lists
[offset in text, page, page_line] for every source line of a block.

PDFs have no citation keys or labels, so the reader makes them: a reference's
key is the first author's family name plus the year ("laibson1998"), which is
also the key of a citation that matches it or, when none does, of the
unresolved citation; labels are "table:1", "figure:2", "section:3",
"appendix:A" and "equation:1".
"""

from __future__ import annotations

import bisect
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..model import Anchor, Block, Citation, CrossRef, Figure, Label, Note, PaperMap, Reference, Table
from ..textutil import dehyphenate

# ---------------------------------------------------------------- constants
LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
             "\ufb05": "st", "\ufb06": "st"}
ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}
CID = re.compile(r"\(cid:\d+\)")
BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi|cmbx|sfbx|medi(?!um)", re.I)
ITALIC_FONT = re.compile(r"ital|oblique|cmti|cmmi|cmsl|sfti|sfsl|slant", re.I)
MARKER_TEXT = re.compile(r"[\d*\u2020\u2021\u00a7\u00b6\u2016#\u2217\u22c6]{1,3}")
GREEK = set("\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6\u03b7\u03b8\u03b9\u03ba\u03bb\u03bc\u03bd\u03be\u03c0\u03c1"
            "\u03c3\u03c4\u03c5\u03c6\u03c7\u03c8\u03c9\u0393\u0394\u0398\u039b\u039e\u03a0\u03a3\u03a6\u03a8"
            "\u03a9\u03d1\u03d5\u03f5")
MATH_CHARS = set("=+\u2212\u00d7\u00f7\u00b1\u2213\u2264\u2265\u2248\u2260\u223c\u2243\u2261\u221d\u221e\u2211"
                 "\u220f\u222b\u2202\u2207\u221a\u2208\u2209\u2282\u2286\u222a\u2229\u2200\u2203\u2192\u2190"
                 "\u2194\u21d2\u21d4\u22c5\u2032") | GREEK
NEAR_WHITE = 0.94       # colour components at or above this read as white
TINY = 2.0              # text under this size, in points, is hidden
PAGE_SIZES = {"Letter": (612.0, 792.0), "A4": (595.3, 841.9), "Legal": (612.0, 1008.0),
              "A5": (419.5, 595.3), "B5": (498.9, 708.7), "Executive": (522.0, 756.0)}
MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
          "Jan\\.?|Feb\\.?|Mar\\.?|Apr\\.?|Jun\\.?|Jul\\.?|Aug\\.?|Sept?\\.?|Oct\\.?|Nov\\.?|Dec\\.?")
DATE_LINE = re.compile(rf"^(?:(?:this|first|current)\s+(?:version|draft)[:,]?\s*|draft[:,]?\s*|version[:,]?\s*)?"
                       rf"(?:\d{{1,2}}\s+)?(?:{MONTHS})\s+(?:\d{{1,2}},?\s+)?\d{{4}}$", re.I)
SECTION_NAMES = re.compile(
    r"^(?:abstract|introduction|background|literature(?:\s+review)?|related\s+(?:work|literature)|data|"
    r"data\s+and\s+methods?|methods?|methodology|model|theory|theoretical\s+framework|(?:experimental\s+)?design|"
    r"results?|empirical\s+results|main\s+results|discussion|robustness(?:\s+checks)?|mechanisms?|"
    r"conclusions?|concluding\s+remarks|summary|references(?:\s+and\s+notes)?|bibliography|works\s+cited|literature\s+cited|"
    r"appendix|appendices|online\s+appendix|supplementary\s+(?:material|appendix|information)|"
    r"acknowledge?ments?|data\s+availability(?:\s+statement)?|funding|declarations?|"
    r"conflicts?\s+of\s+interest|ethics(?:\s+statement)?)$", re.I)
REFERENCE_HEADING = re.compile(r"^(?:(?:\d{1,2}|[A-Z]|[IVX]{1,4})\.?\s+)?(?:references(?:\s+and\s+notes)?|notes\s+and\s+references|"
                               r"bibliography|works\s+cited|literature(?:\s+cited)?|cited\s+literature|reference\s+list)$", re.I)
CAPTION = re.compile(r"^(?P<kind>Table|TABLE|Figure|FIGURE|Fig\.|FIG\.|Exhibit|EXHIBIT|Chart|CHART)\s+"
                     r"(?P<num>[A-Z]?\d+(?:\.\d+)*[a-z]?|[IVXLC]+)\s*(?:(?P<sep>[:.|\u2014\u2013-])\s*|$|(?=[A-Z(]))")
NUMBERED_HEADING = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3}|[A-Z](?:\.\d{1,2}){0,3}|[IVX]{1,5})\.?\s+(?P<title>\S.*)$")
APPENDIX_HEADING = re.compile(r"^(?:Online\s+)?(?:Appendix|APPENDIX)(?:\s+(?P<num>[A-Z]|\d{1,2}))?\b\s*[.:\u2014\u2013-]?\s*(?P<title>.*)$")
PAGE_NUMBER = re.compile(r"(?:page\s+)?(?:\d{1,4}|[ivxlc]{1,6})(?:\s*(?:of|/)\s*\d{1,4})?|[-\u2013\u2014]\s*\d{1,4}\s*[-\u2013\u2014]", re.I)
NOTES_START = re.compile(r"^(?:notes?|sources?|standard errors|robust standard errors|\*|significance)\b", re.I)
LIST_START = re.compile(r"^(?:[\u2022\u25cf\u25aa\u2013\u2014-]\s|\(?(?:[ivx]{1,4}|[a-h]|\d{1,2})\)\s)")
URL_TAIL = re.compile(r"(?:https?://|www\.|doi\.org/|doi:|\b10\.\d{4,9}/)\S*$", re.I)

# Line breaks after the hyphen of these words are kept as compounds.
COMPOUND_HEADS = {"self", "non", "cross", "long", "short", "well", "high", "low", "two", "three", "four", "five",
                  "six", "ten", "first", "second", "third", "within", "between", "half", "multi", "quasi", "semi",
                  "risk", "loss", "time", "present"}
COMPOUND_TAILS = {"based", "level", "specific", "related", "wide", "free", "like", "run", "term", "scale", "up",
                  "off", "averse", "neutral", "seeking", "taking", "making", "sectional", "dependent", "invariant",
                  "year", "class", "group", "biased", "control", "reported", "selection", "sample"}
PARTICLES = {"van", "von", "de", "der", "den", "del", "della", "di", "da", "du", "dos", "das", "la", "le", "ten",
             "ter", "bin", "ibn", "al", "el", "st", "st."}


# ---------------------------------------------------------------- small helpers
def _rnd(v: float) -> float:
    return round(float(v), 1)


def _bbox(items) -> list:
    boxes = [getattr(i, "box", None) or (i.x0, i.top, i.x1, i.bottom) for i in items]
    return [_rnd(min(b[0] for b in boxes)), _rnd(min(b[1] for b in boxes)),
            _rnd(max(b[2] for b in boxes)), _rnd(max(b[3] for b in boxes))]


def _pdf_date(value: str) -> str:
    """"D:20261017194139+02'00'" as "2026-10-17T19:41:39+02:00"; other text unchanged."""
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?\s*([Zz]|[+-]\d{2}'?\d{2}'?)?", value.strip())
    if not m or not m.group(1) or m.group(1) == "0000":
        return value
    y, mo, d, h, mi, sec = (m.group(k) for k in range(1, 7))
    out = f"{y}-{mo or '01'}-{d or '01'}"
    if h:
        out += f"T{h}:{mi or '00'}:{sec or '00'}"
        tz = m.group(7)
        if tz:
            out += "Z" if tz in "Zz" else f"{tz[:3]}:{re.sub(r'[^0-9]', '', tz)[2:4] or '00'}"
    return out


def _graphics_regions(page, limit: int = 20000) -> list:
    """Areas drawn with curves, diagonal lines or several filled shapes: plots and diagrams.
    Areas made only of horizontal and vertical rules (ruled tables) do not count."""
    width, height = float(page.width), float(page.height)
    shapes = []
    for c in list(page.curves)[:limit]:
        shapes.append(((c["x0"], c["top"], c["x1"], c["bottom"]), "curve", len(c.get("pts") or [])))
    for r in list(page.rects)[:limit]:
        w, h = r["x1"] - r["x0"], r["bottom"] - r["top"]
        if w > 1.5 and h > 1.5 and not (w > 0.9 * width and h > 0.9 * height):
            shapes.append(((r["x0"], r["top"], r["x1"], r["bottom"]), "rect", 4))
    for l in list(page.lines)[:limit]:
        if abs(l["x1"] - l["x0"]) > 1 and abs(l["bottom"] - l["top"]) > 1:
            shapes.append(((l["x0"], l["top"], l["x1"], l["bottom"]), "diagonal", 2))
    if not shapes:
        return []
    parent = list(range(len(shapes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    tol, cell = 12.0, 60.0
    grid = defaultdict(list)
    for i, ((x0, top, x1, bottom), _, _) in enumerate(shapes):
        for gx in range(int((x0 - tol) // cell), int((x1 + tol) // cell) + 1):
            for gy in range(int((top - tol) // cell), int((bottom + tol) // cell) + 1):
                for j in grid[(gx, gy)]:
                    a, b = shapes[j][0], shapes[i][0]
                    if a[0] - tol <= b[2] and b[0] - tol <= a[2] and a[1] - tol <= b[3] and b[1] - tol <= a[3]:
                        parent[find(i)] = find(j)
                grid[(gx, gy)].append(i)
    groups = defaultdict(list)
    for i in range(len(shapes)):
        groups[find(i)].append(shapes[i])
    regions = []
    for members in groups.values():
        x0 = min(m[0][0] for m in members)
        top = min(m[0][1] for m in members)
        x1 = max(m[0][2] for m in members)
        bottom = max(m[0][3] for m in members)
        if x1 - x0 < 50 or bottom - top < 35 or (x1 - x0 > 0.95 * width and bottom - top > 0.9 * height):
            continue
        curves = sum(1 for m in members if m[1] == "curve" and m[2] >= 4)
        diagonals = sum(1 for m in members if m[1] == "diagonal")
        rects = sum(1 for m in members if m[1] == "rect")
        if curves or diagonals >= 3 or rects >= 4:
            regions.append((x0, top, x1, bottom, rects >= 4 and not curves and diagonals < 3))
    return regions


def _is_white(color) -> bool:
    if color is None or isinstance(color, str):
        return False
    if isinstance(color, (int, float)):
        color = (color,)
    try:
        vals = [float(v) for v in color]
    except (TypeError, ValueError):
        return False
    if len(vals) == 1:
        return vals[0] >= NEAR_WHITE
    if len(vals) == 3:
        return min(vals) >= NEAR_WHITE
    if len(vals) == 4:
        return max(vals) <= 1 - NEAR_WHITE
    return False


def _fold(name: str) -> str:
    """Lowercase ASCII letters of a name: "O'Donoghue" -> "odonoghue"."""
    text = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in text if ch.isascii() and ch.isalpha()).lower()


def _percentile(values, q: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    k = (len(values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


# ---------------------------------------------------------------- tokens and lines
@dataclass(eq=False)
class Tok:
    """Characters of one style without a word space inside."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    font: str = ""
    space: bool = False        # a word space comes before this token
    hidden: str = ""           # "white", "tiny" or "white tiny"
    bold: bool = False
    italic: bool = False
    script: str = ""           # "super" or "sub", relative to the token's line
    marker: bool = False       # a footnote marker matched to its footnote; left out of the text
    color: object = None


@dataclass(eq=False)
class Line:
    page: int
    toks: list
    col: int = 0               # 0 left or only column, 1 right column, -1 crosses the gutter
    role: str = "body"         # body, footnote or removed
    no: int = 0                # page_line
    size: float = 0.0
    bold: float = 0.0          # share of characters in a bold font
    italic: float = 0.0
    used: bool = False         # already part of a block
    tag: str = ""              # caption, heading, equation or table, from classification
    block: object = None
    box: Optional[tuple] = None  # bbox on the page, for rotated text
    _cache: Optional[tuple] = None

    def __post_init__(self):
        self.refresh()

    def refresh(self) -> None:
        self.toks.sort(key=lambda t: (t.x0, t.top))
        self.x0 = min(t.x0 for t in self.toks)
        self.x1 = max(t.x1 for t in self.toks)
        self.top = min(t.top for t in self.toks)
        self.bottom = max(t.bottom for t in self.toks)
        visible = [t for t in self.toks if not t.hidden] or self.toks
        weights = Counter()
        for t in visible:
            weights[round(t.size, 1)] += len(t.text)
        self.size = weights.most_common(1)[0][0] if weights else 0.0
        n = sum(len(t.text) for t in visible) or 1
        self.bold = sum(len(t.text) for t in visible if t.bold) / n
        self.italic = sum(len(t.text) for t in visible if t.italic) / n
        main = [t for t in visible if abs(t.size - self.size) <= 0.15 * self.size] or visible
        base = statistics.median(t.bottom for t in main)
        for t in self.toks:
            t.script = ""
            if t.size <= 0.82 * self.size and not t.hidden:
                if t.bottom < base - 0.18 * self.size:
                    t.script = "super"
                elif t.bottom > base + 0.08 * self.size:
                    t.script = "sub"
        self._cache = None

    def render(self) -> tuple:
        """(text, token of each character or None for spaces, [(token, start, end)])."""
        if self._cache is None:
            out, owners, spans, pos = [], [], [], 0
            for t in self.toks:
                if t.marker:
                    spans.append((t, pos, pos))
                    continue
                if t.space and out:
                    out.append(" ")
                    owners.append(None)
                    pos += 1
                out.append(t.text)
                owners.extend([t] * len(t.text))
                spans.append((t, pos, pos + len(t.text)))
                pos += len(t.text)
            self._cache = ("".join(out), owners, spans)
        return self._cache

    @property
    def text(self) -> str:
        return self.render()[0]

    @property
    def hidden_only(self) -> bool:
        return all(t.hidden for t in self.toks)

    @property
    def center(self) -> float:
        return (self.top + self.bottom) / 2


def _extract_chars(page) -> tuple:
    """Characters of a page as small dicts, plus word-space positions, rotated characters, unmapped glyphs."""
    chars, spaces, rotated, cids = [], [], [], 0
    for c in page.chars:
        text = c.get("text") or ""
        if not text or text in ZERO_WIDTH:
            continue
        if CID.fullmatch(text):
            text, cids = "\ufffd", cids + 1
        d = {"text": LIGATURES.get(text, text), "x0": float(c["x0"]), "x1": float(c["x1"]),
             "top": float(c["top"]), "bottom": float(c["bottom"]),
             "size": float(c.get("size") or (c["bottom"] - c["top"]) or 1.0),
             "font": c.get("fontname") or "", "color": c.get("non_stroking_color")}
        if not c.get("upright", True):
            a, b = (c.get("matrix") or (1, 0, 0, 1, 0, 0))[:2]
            d["dir"] = "up" if b > abs(a) else "down" if -b > abs(a) else "flip"
            d["space"] = text.isspace() or text == "\xa0"
            rotated.append(d)
        elif text.isspace() or text == "\xa0":
            spaces.append(d)
        else:
            chars.append(d)
    return _dedupe(chars), spaces, rotated, cids


def _dedupe(chars: list) -> list:
    """Drop characters printed twice at almost the same spot (fake bold). The tolerance
    scales with the font size, so 1-point text keeps its double letters."""
    chars.sort(key=lambda c: (c["text"], round(c["top"], 1), c["x0"]))
    out = []
    for c in chars:
        p = out[-1] if out else None
        tol = 0.12 * c["size"]
        if (p is not None and p["text"] == c["text"] and abs(p["size"] - c["size"]) < 0.05
                and abs(p["x0"] - c["x0"]) < tol and abs(p["top"] - c["top"]) < tol):
            continue
        out.append(c)
    return out


def _band_fit(c: dict, b: dict) -> float:
    """How well character c sits on band b: 0 for not at all."""
    small, big = sorted((c["size"], b["size"]))
    if big <= 0 or small / big < 0.4:
        return 0.0  # tiny hidden text never joins a line of normal text
    h, bh = max(c["bottom"] - c["top"], 0.1), max(b["bottom"] - b["top"], 0.1)
    ov = min(c["bottom"], b["bottom"]) - max(c["top"], b["top"])
    if ov <= 0:
        return 0.0
    if small / big >= 0.8:
        r = ov / min(h, bh)
        return r if r >= 0.7 else 0.0
    sh = h if c["size"] < b["size"] else bh
    r = ov / sh
    return 0.6 * r if r >= 0.35 else 0.0  # a superscript or subscript of the band's text


def _bands(chars: list) -> list:
    """Group characters into rough rows. A row may hold several columns' lines."""
    chars = sorted(chars, key=lambda c: ((c["top"] + c["bottom"]) / 2, c["x0"]))
    bands, active = [], []
    for c in chars:
        active = [b for b in active if b["bottom"] + 2 * b["size"] > c["top"]]
        best, score = None, 0.0
        for b in active:
            s = _band_fit(c, b)
            if s > score:
                best, score = b, s
        if best is None:
            best = {"top": c["top"], "bottom": c["bottom"], "size": c["size"], "chars": []}
            bands.append(best)
            active.append(best)
        elif c["size"] > best["size"] * 1.2:
            best.update(top=c["top"], bottom=c["bottom"], size=c["size"])
        best["chars"].append(c)
    return bands


def _tokens(chars: list, spaces: list) -> list:
    chars = sorted(chars, key=lambda c: (c["x0"], c["top"]))
    top = min(c["top"] for c in chars)
    bottom = max(c["bottom"] for c in chars)
    size = statistics.median(c["size"] for c in chars)
    gaps = sorted((s["x0"] + s["x1"]) / 2 for s in spaces
                  if top <= (s["top"] + s["bottom"]) / 2 <= bottom and 0.5 <= s["size"] / size <= 2.0)
    toks, cur, cur_chars = [], None, []

    def close():
        if cur is not None:
            fonts = Counter(ch["font"] for ch in cur_chars).most_common(1)[0][0]
            cur.font = fonts
            cur.bold = bool(BOLD_FONT.search(fonts.split("+")[-1]))
            cur.italic = bool(ITALIC_FONT.search(fonts.split("+")[-1]))
            toks.append(cur)

    for c in chars:
        if cur is not None:
            gap = c["x0"] - cur.x1
            ref = min(c["size"], cur.size)
            i = bisect.bisect_left(gaps, cur.x1 - 0.3 * ref)
            explicit = i < len(gaps) and gaps[i] <= c["x0"] + 0.3 * ref
            # When the PDF writes its word spaces, trust them: in tiny or tightly set
            # text, gaps between letters can be as wide as a space.
            spaced = explicit or gap > (0.45 if gaps else 0.18) * ref
            same = (c["hidden"] == cur.hidden and 0.85 <= c["size"] / max(cur.size, 0.01) <= 1.18)
            if not spaced and same and gap > -0.6 * ref:
                cur.text += c["text"]
                cur.x1 = max(cur.x1, c["x1"])
                cur.top, cur.bottom = min(cur.top, c["top"]), max(cur.bottom, c["bottom"])
                cur_chars.append(c)
                continue
            close()
            cur = Tok(c["text"], c["x0"], c["x1"], c["top"], c["bottom"], c["size"], space=spaced,
                      hidden=c["hidden"], color=c["color"])
            cur_chars = [c]
        else:
            cur = Tok(c["text"], c["x0"], c["x1"], c["top"], c["bottom"], c["size"], hidden=c["hidden"],
                      color=c["color"])
            cur_chars = [c]
    close()
    return toks


def _horizontal_rules(page) -> list:
    """Thin horizontal lines and rectangles, collinear pieces merged: [(x0, x1, y)]."""
    segs = []
    for obj in page.lines:
        if abs(obj["top"] - obj["bottom"]) < 1.0 and obj["x1"] - obj["x0"] > 3:
            segs.append([float(obj["x0"]), float(obj["x1"]), (obj["top"] + obj["bottom"]) / 2])
    for obj in page.rects:
        if obj["bottom"] - obj["top"] <= 1.6 and obj["x1"] - obj["x0"] > 3:
            segs.append([float(obj["x0"]), float(obj["x1"]), (obj["top"] + obj["bottom"]) / 2])
    segs.sort(key=lambda s: (round(s[2]), s[0]))
    merged = []
    for s in segs:
        if merged and abs(merged[-1][2] - s[2]) < 0.8 and s[0] <= merged[-1][1] + 2:
            merged[-1][1] = max(merged[-1][1], s[1])
        else:
            merged.append(list(s))
    return [tuple(m) for m in merged]


def _dark_boxes(page, images) -> list:
    """Filled areas that are not white: white text on them is visible."""
    boxes = [tuple(b) for b in images]
    for obj in list(page.rects) + list(page.curves):
        if obj.get("fill") and not _is_white(obj.get("non_stroking_color")):
            boxes.append((obj["x0"], obj["top"], obj["x1"], obj["bottom"]))
    return boxes


@dataclass(eq=False)
class PageInfo:
    number: int
    width: float
    height: float
    bands: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    images: list = field(default_factory=list)
    rotated: list = field(default_factory=list)
    gutter: Optional[tuple] = None
    confident: bool = False
    graphics: list = field(default_factory=list)
    fonts: set = field(default_factory=set)


# ---------------------------------------------------------------- citations and cross-references
_NAME = (r"(?<![\w'\u2019\-])(?:(?:van|von|de|der|den|del|della|di|da|du|dos|das|la|le|ten|ter)\s+)*"
         r"[A-Z\u00c0-\u00de][\w\u00c0-\u024f'\u2019\-]*[\w\u00c0-\u024f]")
_AUTHORS = rf"{_NAME}(?:\s+et\s+al\.?|(?:\s*,\s*{_NAME})*\s*,?\s+(?:and|&)\s+{_NAME})?"
_YEAR = r"(?:1[6-9]\d\d|20\d\d)[a-z]?|forthcoming|in\s+press|n\.\s?d\."
_YEARS = rf"(?:{_YEAR})(?:\s*,\s*(?:{_YEAR}|[a-z]\b))*"
_LOC = r"(?:\s*,\s*(?:p|pp|ch|chap|sec|fn|footnote|table|figure|eq)\.?\s*[\w\-\u2013]+)?"
NARRATIVE = re.compile(rf"(?P<authors>{_AUTHORS})(?:\u2019s|'s)?\s*\((?P<years>{_YEARS}){_LOC}\)")
PAREN_SEGMENT = re.compile(
    rf"^\s*(?P<pre>(?i:e\.g\.|i\.e\.|see(?:\s+also)?|cf\.|for\s+example|for\s+instance|as\s+in|following|"
    rf"reviewed\s+in|surveyed\s+in)[,:]?\s+)?(?P<authors>{_AUTHORS})(?:\u2019s|'s)?\s*,?\s+(?P<years>{_YEARS})"
    rf"{_LOC}\s*(?P<post>,?\s*(?i:among\s+others|for\s+a\s+review|and\s+references\s+therein))?\s*$")
NOT_AUTHORS = {"Table", "Tables", "Figure", "Figures", "Section", "Sections", "Appendix", "Equation", "Panel",
               "Column", "Columns", "Model", "Models", "Wave", "Round", "Study", "Experiment", "Treatment",
               "Hypothesis", "Proposition", "Spring", "Summer", "Fall", "Autumn", "Winter", "Since", "Until",
               "In", "From", "Before", "After", "During", "The", "This", "We", "Our", "Census", "Survey",
               "Protocol", "Version", "Draft", "Page", "Note", "Notes", "Source", "Sources"} | set(MONTHS.replace("\\.?", "").split("|"))
XREF = re.compile(
    r"\b(?P<kind>Tables?|TABLES?|Figures?|FIGURES?|Figs?\.|Sections?|Sects?\.|Secs?\.|\u00a7|Appendix|Appendices|"
    r"Equations?|Eqs?\.)(?:~|\s)*"
    r"(?P<nums>\(?(?:[A-Z]?\d+(?:\.\d+)*[a-z]?|[A-Z](?:\.\d+)*\b|\?\?)\)?"
    r"(?:\s*(?:,|and|&|\u2013|-|to)\s*\(?(?:[A-Z]?\d+(?:\.\d+)*[a-z]?|[A-Z](?:\.\d+)*\b|\?\?)\)?)*)")
XREF_KIND = {"table": "table", "figure": "figure", "fig": "figure", "section": "section", "sect": "section",
             "sec": "section", "\u00a7": "section", "appendix": "appendix", "appendice": "appendix",
             "equation": "equation", "eq": "equation"}


def find_citations(text: str) -> list:
    """Author-year citations in text: [{start, end, kind, items: [(names, et_al, year)]}].

    kind is "citep" for a parenthesis of citations, such as "(Laibson, 1998; O'Donoghue
    and Rabin, 1999)", and "citet" for a narrative one, such as "Madrian and Shea (2001)".
    natbib's "(?)" and "[?]" for undefined citations come back with no items."""
    found = []
    for m in re.finditer(r"\(([^()]*)\)", text):
        inner = m.group(1)
        if inner.strip() == "?":
            found.append({"start": m.start(), "end": m.end(), "kind": "citep", "items": []})
            continue
        items = []
        for seg in inner.split(";"):
            sm = PAREN_SEGMENT.match(seg)
            if sm:
                items.extend(_cite_items(sm.group("authors"), sm.group("years")))
        if items:
            found.append({"start": m.start(), "end": m.end(), "kind": "citep", "items": items})
    for m in re.finditer(r"\[\?\]", text):
        found.append({"start": m.start(), "end": m.end(), "kind": "cite", "items": []})
    taken = [(f["start"], f["end"]) for f in found]
    for m in NARRATIVE.finditer(text):
        if any(s <= m.start() < e or s < m.end() <= e for s, e in taken):
            continue
        items = _cite_items(m.group("authors"), m.group("years"))
        if items:
            starts = [n.start() for n in re.finditer(_NAME, text[:m.end("authors")]) if n.start() >= m.start()]
            found.append({"start": m.start(), "end": m.end(), "kind": "citet", "items": items, "name_starts": starts})
    for m in re.finditer(r"\[(\d{1,3}(?:\s*[-\u2013,;]\s*\d{1,3})*)\]", text):
        if not any(s <= m.start() < e for s, e in taken):
            nums = []
            for part in re.split(r"\s*[,;]\s*", m.group(1)):
                rng = re.fullmatch(r"(\d+)\s*[-\u2013]\s*(\d+)", part)
                if rng and int(rng.group(1)) < int(rng.group(2)) <= int(rng.group(1)) + 50:
                    nums.extend(str(n) for n in range(int(rng.group(1)), int(rng.group(2)) + 1))
                elif part.isdigit():
                    nums.append(part)
            found.append({"start": m.start(), "end": m.end(), "kind": "cite", "items": [], "numbers": nums})
    return sorted(found, key=lambda f: f["start"])


def _cite_items(authors: str, years: str) -> list:
    et_al = bool(re.search(r"\bet\s+al\b", authors))
    names = [n.strip() for n in re.split(r"\s*,\s*(?:and\s+|&\s+)?|\s+and\s+|\s*&\s*",
                                         re.sub(r"\s+et\s+al\.?", "", authors)) if n.strip()]
    names = [re.sub(r"(?:\u2019|')s$", "", n) for n in names]
    if not names or names[0].split()[-1] in NOT_AUTHORS or names[0] in NOT_AUTHORS:
        return []
    out, last_year = [], None
    for y in re.split(r"\s*,\s*", years):
        y = re.sub(r"\s+", " ", y.strip())
        if re.fullmatch(r"[a-z]", y) and last_year:
            y = last_year[:4] + y  # "2019a, b"
        last_year = y
        out.append((names, et_al, y))
    return out


def find_crossrefs(text: str) -> list:
    """Cross-references in text: [{start, end, labels, resolved}]. "??" is unresolved."""
    found = []
    for m in XREF.finditer(text):
        kind_word = m.group("kind").lower().rstrip(".s") if m.group("kind") != "\u00a7" else "\u00a7"
        kind = XREF_KIND.get(kind_word, XREF_KIND.get(kind_word.rstrip("e"), "other"))
        nums = re.findall(r"\?\?|[A-Z]?\d+(?:\.\d+)*[a-z]?|\b[A-Z](?:\.\d+)*\b", m.group("nums"))
        if not nums:
            continue
        labels = [f"{kind}:{n}" for n in nums]
        found.append({"start": m.start(), "end": m.end(), "labels": labels, "resolved": "??" not in nums,
                      "raw": m.group(0)})
    for m in re.finditer(r"(?<![\w?])\?\?(?![\w?])", text):
        if not any(f["start"] <= m.start() < f["end"] for f in found):
            found.append({"start": m.start(), "end": m.end(), "labels": ["??"], "resolved": False, "raw": "??"})
    return sorted(found, key=lambda f: f["start"])


# ---------------------------------------------------------------- reference parsing
DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
URL = re.compile(r"(?:https?://|www\.)[^\s<>\"]+", re.I)
REF_YEAR = re.compile(r"(?<![\d.])\(?(?P<year>1[5-9]\d\d|20\d\d)(?P<suffix>[a-z])?\)?(?![\d])|\b(?P<word>forthcoming|in press|n\.\s?d\.)", re.I)


_INITIAL = re.compile(r"[A-Z\u00c0-\u00de]\.?(?:-[A-Z]\.?)?|[A-Z]{1,3}")
_WORD = re.compile(r"[A-Z\u00c0-\u00de][a-z\u00df-\u024f'\u2019\-]+")


def _is_given(part: str) -> bool:
    """Given names after an inverted family name: "Thomas", "Brigitte C.", "B. C.", "D.-F."."""
    tokens = part.replace(".", ". ").split()
    if not tokens or len(tokens) > 4:
        return False
    if len(tokens) == 1:
        return bool(_WORD.fullmatch(tokens[0]) or _INITIAL.fullmatch(tokens[0]))
    if not all(_WORD.fullmatch(t) or _INITIAL.fullmatch(t) for t in tokens):
        return False
    return bool(_INITIAL.fullmatch(tokens[-1]))  # "Dennis F. Shea" is a whole name, "Richard H." is not


def _is_family(part: str) -> bool:
    core = [w for w in part.split() if w.lower() not in PARTICLES]
    return len(core) == 1 and bool(re.fullmatch(r"[A-Z\u00c0-\u00de][\w\u00c0-\u024f'\u2019\-]*", core[0]))


def parse_names(text: str) -> tuple:
    """Authors of a reference: ([{family, given}], et_al)."""
    s = re.sub(r"\s*&\s*", " and ", text.strip().rstrip(",;:( "))
    if s.endswith(".") and len(s.split()[-1].rstrip(".")) > 2:
        s = s[:-1]  # the full stop after a name, but not the one after an initial
    et_al = bool(re.search(r"\bet\s+al\b", s))
    s = re.sub(r",?\s*\bet\s+al\b\.?", "", s)
    parts = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+|;\s*", s) if p.strip()]
    names, i = [], 0
    while i < len(parts):
        p = parts[i]
        nxt = parts[i + 1] if i + 1 < len(parts) else None
        words = p.split()
        if nxt is not None and _is_family(p) and _is_given(nxt):
            names.append({"family": p, "given": nxt})
            i += 2
            continue
        if len(words) >= 3 and any(w in ("of", "for", "the", "on", "and", "de", "des", "du") for w in words[1:-1]) \
                and not any(_INITIAL.fullmatch(w) for w in words):
            names.append({"family": p, "given": ""})  # an organisation: "Bureau of Labor Statistics"
        elif len(words) >= 2 and re.fullmatch(r"[A-Z]{1,3}", words[-1]):  # Vancouver: "Smith JA"
            names.append({"family": " ".join(words[:-1]), "given": words[-1]})
        elif len(words) >= 2:
            k = len(words) - 1
            while k > 0 and words[k - 1].lower() in PARTICLES:
                k -= 1
            names.append({"family": " ".join(words[k:]), "given": " ".join(words[:k])})
        else:
            names.append({"family": p, "given": ""})
        i += 1
    return names, et_al


def _quoted(rest: str) -> Optional[tuple]:
    """(title, end) when `rest` opens with a quoted title."""
    closing = {"\u201c": "\u201d", '"': '"', "\u2018": "\u2019", "'": "'"}.get(rest[:1])
    if closing is None:
        return None
    i = 1
    while True:
        j = rest.find(closing, i)
        if j < 0:
            return None
        if closing in ("\u2019", "'") and j + 1 < len(rest) and rest[j + 1].isalpha():
            i = j + 1  # an apostrophe inside the title
            continue
        return rest[1:j].strip().rstrip(",."), j + 1


def _year_ok(text: str, m, excluded: list) -> bool:
    """A year candidate that is not part of a DOI, URL, page range or page number."""
    s, e = m.start(), m.end()
    if any(a <= s < b for a, b in excluded):
        return False
    if text[max(0, s - 1):s] in ("-", "\u2013", "\u2014", ":", "/") or re.match(r"\s*[-\u2013\u2014]\s*\d", text[e:e + 4]):
        return False
    return True


def _name_prefix(prefix: str) -> bool:
    """Does the text before a year look like a list of authors?"""
    p = prefix.strip()
    if not p or len(p) > 400 or len(p.split()) > 45:
        return False
    if not re.fullmatch(r"(?:[^\W\d_]|[\s,.;&'\u2019\-])*(?:\bet\s+al\.?)?[\s,(\[]*", p):
        return False
    # a period, then a capitalised word and lowercase words: a title, not names
    return not re.search(r"[a-z\u00df-\u024f]{3,}\.\s+[A-Z\u00c0-\u00de][a-z\u00df-\u024f]+\s+[a-z\u00df-\u024f]{2,}", p)


SAME_AUTHORS = re.compile(r"^\s*(?:[\u2014\u2013_-]{2,}\s*[.,]?\s*)?\(?\s*(?:1[5-9]\d\d|20\d\d)[a-z]?\s*\)?[.,:]?(?:\s|$)")


def parse_reference(text: str, italic: Optional[list] = None) -> dict:
    """Heuristic fields of a printed reference.

    Handles the author-year order of the AEA, Chicago, APA, Econometrica and Harvard
    styles ("Laibson, David. 1998. Title. Journal ...") and the year-last order of
    natbib's plainnat ("David Laibson. Title. Journal, 112(2):443-477, 1997.").
    `italic` gives (start, end) spans of italic text, which usually mark the journal
    or book title. An entry that opens with its year, as when a style replaces a
    repeated author list with a rule, comes back without authors."""
    fields: dict = {}
    excluded = []
    m = DOI.search(text)
    if m:
        fields["doi"] = m.group(1).rstrip(".,;)]}\u201d\u2019")
        excluded.append((m.start(), m.end()))
    for u in URL.finditer(text):
        excluded.append((u.start(), u.end()))
        if "doi.org" not in u.group(0).lower() and "url" not in fields:
            fields["url"] = u.group(0).rstrip(".,;)]}\u201d\u2019")
    years = [y for y in REF_YEAR.finditer(text) if _year_ok(text, y, excluded)]
    ym, authors_text, rest_start = None, None, 0
    if years and SAME_AUTHORS.match(text) and years[0].start() < 12:
        ym, authors_text = years[0], ""
    elif years and _name_prefix(text[:years[0].start()]):
        ym, authors_text = years[0], text[:years[0].start()]
    if ym is not None:
        rest_start = ym.end()
        while rest_start < len(text) and text[rest_start] in " .,):;":
            rest_start += 1
    else:
        am = re.match(r"(.+?(?:[A-Za-z\u00c0-\u024f][a-z\u00df-\u024f]|\bet\s+al|\b[A-Z]{2,}))\.\s+(?=\S)", text)
        if am and _name_prefix(am.group(1)):
            authors_text, rest_start = am.group(1), am.end()
        else:
            authors_text, rest_start = "", 0
        later = [y for y in years if y.start() >= rest_start]
        ym = later[-1] if later else (years[-1] if years else None)
    if ym is not None:
        year = ym.group("year") or ym.group("word")
        fields["year"] = year.lower() if ym.group("word") else year
        if ym.group("suffix"):
            fields["year_suffix"] = ym.group("suffix")
    if authors_text:
        authors, et_al = parse_names(authors_text)
        fields["authors"] = authors
        if et_al:
            fields["et_al"] = True
    rest = text[rest_start:]
    title, after_off = None, rest_start
    quoted = _quoted(rest)
    if quoted:
        title, after_off = quoted[0], rest_start + quoted[1]
    else:
        tm = re.match(r"(.+?[\w\)\?!])[.?!](?=\s+[A-Z\u00c0-\u00de(\[]|\s+In\b|\s*$)", rest)
        if tm:
            title, after_off = tm.group(1).strip(), rest_start + tm.end()
    if title and not re.match(r"(?i)(?:https?:|doi:|www\.)", title):
        fields["title"] = title.rstrip(".,")
    after = text[after_off:].lstrip(" .,:;")
    after_start = len(text) - len(after)
    container = None
    for s, e in italic or []:
        if s >= after_start - 1 and e - s > 2:
            container = text[s:e].strip(" .,:;")
            break
    if container is None and after:
        cm = re.match(r"(?:In:?\s+)?((?:[^,(\d.]|\.(?=\s*[A-Z][\w.]*\s))+)", after)
        if cm and not re.match(r"(?i)(?:https?|doi|www)", cm.group(1)):
            container = cm.group(1).strip(" .,:;")
    if container:
        fields["container"] = container
    pages_re = r"[A-Za-z]?\d+(?:\s*[-\u2013\u2014]+\s*[A-Za-z]?\d+)?"
    vm = re.search(rf"\b(\d+)\s*\(([^)]{{1,12}})\)\s*[:,]\s*(?:pp?\.\s*)?({pages_re})", after)
    if vm:
        fields.update(volume=vm.group(1), issue=vm.group(2), pages=vm.group(3))
    else:
        vm = (re.search(rf"\b(\d+)\s*:\s*({pages_re})", after)
              or re.search(rf"\b[Vv]ol(?:ume)?\.?\s*(\d+)(?:,?\s*[Nn]o\.?\s*(\w+))?,?\s*(?:pp?\.\s*)?({pages_re})?", after)
              or re.search(rf",\s*(\d+)\s*,\s*(?:pp?\.\s*)?({pages_re})", after)
              or re.search(r"\b(\d{1,4})\s*,\s*(?:pp?\.\s*)?([A-Za-z]?\d+\s*[-\u2013\u2014]+\s*[A-Za-z]?\d+)", after))
        if vm:
            groups = [g for g in vm.groups()]
            fields["volume"] = groups[0]
            if len(groups) == 3:
                if groups[1]:
                    fields["issue"] = groups[1]
                if groups[2]:
                    fields["pages"] = groups[2]
            elif len(groups) == 2 and groups[1]:
                fields["pages"] = groups[1]
        else:
            pm_ = re.search(rf"\bpp?\.\s*({pages_re})", after)
            if pm_:
                fields["pages"] = pm_.group(1)
    if fields.get("pages"):
        fields["pages"] = re.sub(r"\s+", "", fields["pages"])
    low = text.lower()
    report = re.search(r"(working paper|discussion paper|technical report|research paper|policy research|mimeo|"
                       r"nber|ssrn|unpublished|manuscript)", low)
    if report:
        fields["type"] = "report"
        nm = re.search(r"(?:no\.|number|paper)\s*([A-Za-z]?\d[\w\-]*)", text, re.I)
        if nm:
            fields["number"] = nm.group(1)
    elif fields.get("container") and (fields.get("volume") or fields.get("pages")):
        fields["type"] = "article"
    elif re.search(r"\b(?:eds?\.|edited by)", low) and re.search(r"\bin\b", low):
        fields["type"] = "chapter"
    pub = re.search(r"([A-Z][\w.&\- ]*(?:Press|Publishing|Publishers|Books|Verlag|Wiley|Elsevier|Springer|Routledge))", text)
    if pub:
        fields["publisher"] = pub.group(1).strip()
        fields.setdefault("type", "book")
        if fields.get("container") and fields["publisher"] in fields["container"] and not fields.get("volume"):
            fields.pop("container")  # "New Haven: Yale University Press" is the publisher
    return {k: v for k, v in fields.items() if v not in (None, "", [])}


def reference_key(family: str, year: str) -> str:
    return f"{_fold(family) or 'anon'}{(year or 'nd').replace(' ', '').lower()}"


# ---------------------------------------------------------------- the reader
class PdfReader:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.pm = PaperMap(source={"path": str(self.path)})
        self.pages: list = []
        self.cid_count = 0
        self.body_size = 10.0
        self.blocks: list = []
        self.n_block = 0
        self.section_path: list = []
        self.appendix = False
        self.footnotes: list = []
        self.tables: dict = {}       # caption line -> table info
        self.figures: dict = {}      # caption line -> figure info
        self.gap: dict = {}
        self.edges: dict = {}
        self.vocab: set = set()
        self.hyphen_words: set = set()
        self.hyphen_heads: set = set()
        self.indent_style = True
        self.level1_size: Optional[float] = None
        self.annotations: list = []

    # -- main ------------------------------------------------------------
    def read(self) -> PaperMap:
        import pdfplumber

        self._read_pypdf()
        with pdfplumber.open(str(self.path)) as pdf:
            for page in pdf.pages:
                self.pages.append(self._read_page(page))
        self.pm.metadata["page_count"] = len(self.pages)
        self._text_layer()
        if not any(p.bands for p in self.pages):
            self._finish_metadata()
            return self.pm
        self._body_size()
        self._remove_running_heads()
        self._columns()
        self._make_lines()
        self._footnote_regions()
        self._number_lines()
        self._layout_stats()
        self._vocabulary()
        self._group_footnotes()
        self._figure_text()
        self._classify()
        self._find_tables()
        self._find_figures()
        self._build_blocks()
        self._place_footnotes()
        self._finalize_ids()
        self._spans()
        self._hidden_notes()
        self._annotation_notes()
        self._finish_metadata()
        return self.pm

    # -- pages -----------------------------------------------------------
    def _read_page(self, page) -> PageInfo:
        info = PageInfo(number=page.page_number, width=float(page.width), height=float(page.height))
        chars, spaces, rotated, cids = _extract_chars(page)
        self.cid_count += cids
        info.images = [(float(i["x0"]), float(i["top"]), float(i["x1"]), float(i["bottom"])) for i in page.images]
        info.rules = _horizontal_rules(page)
        info.fonts = {c.get("fontname") or "" for c in page.chars}
        try:
            info.graphics = _graphics_regions(page)
        except Exception:
            info.graphics = []
        dark = None
        for c in chars:
            hidden = "tiny" if c["size"] < TINY else ""
            if _is_white(c["color"]):
                if dark is None:
                    dark = _dark_boxes(page, info.images)
                cx, cy = (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2
                if not any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in dark):
                    hidden = "white tiny" if hidden else "white"
            c["hidden"] = hidden
        for band in _bands(chars):
            toks = _tokens(band["chars"], spaces)
            if toks:
                info.bands.append(Line(page=info.number, toks=toks))
        info.bands.sort(key=lambda b: (b.top, b.x0))
        if rotated:
            info.rotated = rotated
        return info

    def _text_layer(self) -> None:
        with_text = [p.number for p in self.pages if p.bands]
        without = [p.number for p in self.pages if not p.bands]
        self.pm.metadata["text_layer"] = bool(with_text)
        if without:
            self.pm.metadata["pages_without_text"] = without
        if not with_text:
            self.pm.warnings.append("This PDF has no text layer: it is probably scanned. Text checks cannot run; "
                                    "run OCR on it or supply the LaTeX or Word source.")
        elif without:
            imaged = [p.number for p in self.pages if not p.bands and p.images]
            if imaged:
                self.pm.warnings.append(f"Pages {', '.join(map(str, imaged))} have images but no text layer "
                                        f"(scanned pages?); their text is missing from the paper map.")
        if self.cid_count:
            self.pm.warnings.append(f"{self.cid_count} characters have no Unicode mapping in the PDF's fonts and "
                                    f"appear as \ufffd.")
        rotated = sum(len(p.rotated) for p in self.pages)
        if rotated:
            self.pm.warnings.append(f"{rotated} rotated characters (for example a sideways table or a margin stamp) "
                                    f"are kept as blocks of kind 'other'; their layout is not analysed.")

    def _body_size(self) -> None:
        weights = Counter()
        for p in self.pages:
            for b in p.bands:
                for t in b.toks:
                    if not t.hidden:
                        weights[round(t.size * 2) / 2] += len(t.text)
        if weights:
            self.body_size = weights.most_common(1)[0][0]
        self.pm.metadata["body_font_size"] = self.body_size

    # -- running heads and page numbers ------------------------------------
    def _remove_running_heads(self) -> None:
        n = len(self.pages)
        cands = []
        for p in self.pages:
            vis = [b for b in p.bands if not b.hidden_only]
            tops = [b for b in vis[:2] if b.top < 0.12 * p.height]
            bottoms = [b for b in vis[-2:] if b.bottom > 0.88 * p.height]
            for zone, group in (("top", tops), ("bottom", bottoms)):
                outer = group[0] if zone == "top" and group else (group[-1] if group else None)
                for b in group:
                    cands.append((p, zone, b, re.sub(r"\s+", " ", re.sub(r"\d+", "#", b.text.lower())).strip(),
                                  b is outer))
        pages_per_key = defaultdict(set)
        for p, zone, b, key, _ in cands:
            pages_per_key[(zone, key)].add(p.number)
        need = max(2, math.ceil(0.25 * n))
        heads: dict = {}
        numbers = {}
        for p, zone, b, key, outer in cands:
            text = b.text.strip()
            if outer and PAGE_NUMBER.fullmatch(text):
                b.role = "removed"
                numbers[p.number] = text
            elif (len(pages_per_key[(zone, key)]) >= need and b.size <= self.body_size * 1.15
                  and re.search(r"[A-Za-z]", key)):
                b.role = "removed"
                heads.setdefault(key, {"text": text, "zone": zone, "pages": []})["pages"].append(p.number)
                num = re.search(r"^(\d{1,4})\b|\b(\d{1,4})$", text)
                if num:
                    numbers[p.number] = num.group(1) or num.group(2)
        if heads:
            self.pm.metadata["running_heads"] = list(heads.values())
        if numbers:
            self.pm.metadata["printed_page_numbers"] = {str(k): v for k, v in sorted(numbers.items())}

    # -- columns -----------------------------------------------------------
    @staticmethod
    def _cover(b: Line) -> list:
        ivs = []
        for t in b.toks:
            if t.hidden:
                continue
            if ivs and t.x0 - ivs[-1][1] <= 0.8 * b.size:
                ivs[-1][1] = max(ivs[-1][1], t.x1)
            else:
                ivs.append([t.x0, t.x1])
        return ivs

    def _find_gutter(self, p: PageInfo):
        areas = list(p.images) + [g[:4] for g in p.graphics]
        rows = [b for b in p.bands if b.role != "removed" and not b.hidden_only
                and not any(a[0] - 8 <= b.x0 and b.x1 <= a[2] + 8 and a[1] - 8 <= b.top and b.bottom <= a[3] + 8
                            for a in areas)]
        if len(rows) < 6:
            return None
        covers = [(b, self._cover(b)) for b in rows]
        x_lo, x_hi = min(b.x0 for b in rows), max(b.x1 for b in rows)
        width = x_hi - x_lo
        if width < 150:
            return None
        counts = []
        x = x_lo + 0.3 * width
        while x <= x_lo + 0.7 * width:
            counts.append((x, sum(1 for _, ivs in covers if any(a < x < e for a, e in ivs))))
            x += 1.0
        low = min(c for _, c in counts)
        runs, start, prev = [], None, None
        for x, c in counts:
            if c <= low:
                start = x if start is None else start
                prev = x
            elif start is not None:
                runs.append((start, prev))
                start = None
        if start is not None:
            runs.append((start, prev))
        g0, g1 = max(runs, key=lambda r: r[1] - r[0])
        mid = (g0 + g1) / 2
        crossing = [b for b, ivs in covers if any(a < mid < e for a, e in ivs)]
        sides = [(b, ivs) for b, ivs in covers if b not in crossing]
        lefts = [[iv for iv in ivs if iv[1] <= mid] for _, ivs in sides]
        rights = [[iv for iv in ivs if iv[0] >= mid] for _, ivs in sides]
        left_w = [l[-1][1] - l[0][0] for l in lefts if l]
        right_w = [r[-1][1] - r[0][0] for r in rights if r]
        edge0 = max((l[-1][1] for l in lefts if l), default=g0)
        edge1 = min((r[0][0] for r in rights if r), default=g1)
        confident = (len(crossing) <= 0.4 * len(rows) and len(left_w) >= 3 and len(right_w) >= 3
                     and statistics.median(left_w) >= 0.25 * width and statistics.median(right_w) >= 0.25 * width
                     and edge1 - edge0 >= 4)
        return (edge0, edge1) if confident else None

    def _columns(self) -> None:
        found = {}
        for p in self.pages:
            g = self._find_gutter(p)
            if g:
                p.gutter, p.confident = g, True
                found[p.number] = g
        if found:
            g0 = statistics.median(g[0] for g in found.values())
            g1 = statistics.median(g[1] for g in found.values())
            for p in self.pages:
                if p.gutter:
                    continue
                rows = [b for b in p.bands if b.role != "removed" and not b.hidden_only]
                if not rows:
                    continue
                mid = (g0 + g1) / 2
                crossing = [b for b in rows if any(a < mid < e for a, e in self._cover(b))]
                if len(crossing) <= max(1, 0.3 * len(rows)) and any(b.x1 <= g0 + 2 or b.x0 >= g1 - 2 for b in rows):
                    p.gutter = (g0, g1)
        self.pm.metadata["columns"] = [2 if p.gutter else 1 for p in self.pages]

    def _split_band(self, b: Line, gutter: tuple) -> list:
        g0, g1 = gutter
        mid = (g0 + g1) / 2
        left = [t for t in b.toks if (t.x0 + t.x1) / 2 < mid]
        right = [t for t in b.toks if (t.x0 + t.x1) / 2 >= mid]
        straddle = any(t.x0 < mid - 1 and t.x1 > mid + 1 for t in b.toks if not t.hidden)
        if not straddle and left and right:
            gap = min(t.x0 for t in right) - max(t.x1 for t in left)
            straddle = gap < 0.6 * (g1 - g0)
        if straddle:
            b.col = -1
            return [b]
        out = []
        for col, toks in ((0, left), (1, right)):
            if toks:
                line = Line(page=b.page, toks=list(toks), col=col, role=b.role)
                if toks[0] is not b.toks[0] and toks is right:
                    toks[0].space = False
                out.append(line)
        return out

    def _make_lines(self) -> None:
        for p in self.pages:
            lines = []
            for b in p.bands:
                if b.role == "removed":
                    continue
                lines.extend(self._split_band(b, p.gutter) if p.gutter else [b])
            for line in lines:
                if line.toks:
                    line.toks[0].space = False
            lines = self._merge_tiny(lines)
            p.lines = self._reading_order(p, lines)
            for line in self._rotated_lines(p):
                p.lines.append(line)

    @staticmethod
    def _merge_tiny(lines: list) -> list:
        """Put tiny hidden text that sits inside a line of normal text back into that line."""
        normal = [l for l in lines if not l.hidden_only]
        out = []
        for l in lines:
            if l.hidden_only and l.size < TINY:
                host = next((n for n in normal if n.col == l.col and n.top <= l.center <= n.bottom
                             and n.x0 - 2 <= l.x0 and l.x1 <= n.x1 + 2), None)
                if host is not None:
                    l.toks[0].space = True
                    host.toks.extend(l.toks)
                    host.refresh()
                    continue
            out.append(l)
        return out

    @staticmethod
    def _reading_order(p: PageInfo, lines: list) -> list:
        if not p.gutter:
            return sorted(lines, key=lambda l: (round(l.top, 0), l.x0))
        spanning = sorted((l for l in lines if l.col == -1), key=lambda l: l.top)
        cols = [l for l in lines if l.col != -1]
        out, prev = [], -math.inf
        for s in spanning + [None]:
            limit = s.center if s is not None else math.inf
            band = [l for l in cols if prev <= l.center < limit]
            out += sorted((l for l in band if l.col == 0), key=lambda l: l.top)
            out += sorted((l for l in band if l.col == 1), key=lambda l: l.top)
            if s is not None:
                out.append(s)
                prev = s.center
        return out

    def _rotated_lines(self, p: PageInfo) -> list:
        """Rotated text (margin stamps, sideways tables), turned upright and read in its own
        direction. The lines keep their bounding box on the page in `box`."""
        if not p.rotated:
            return []
        W, H = p.width, p.height

        def turn(c, direction):
            x0, x1, top, bottom = c["x0"], c["x1"], c["top"], c["bottom"]
            if direction == "up":
                box = (H - bottom, x0, H - top, x1)
            elif direction == "down":
                box = (top, W - x1, bottom, W - x0)
            else:
                box = (W - x1, H - bottom, W - x0, H - top)
            d = dict(c, x0=box[0], top=box[1], x1=box[2], bottom=box[3])
            d["size"] = max(box[3] - box[1], 0.1)
            hidden = "tiny" if d["size"] < TINY else ""
            if _is_white(c["color"]):
                hidden = "white tiny" if hidden else "white"
            d["hidden"] = hidden
            return d

        def unturn(line, direction):
            X0, T, X1, B = line.x0, line.top, line.x1, line.bottom
            if direction == "up":
                return (T, H - X1, B, H - X0)
            if direction == "down":
                return (W - B, X0, W - T, X1)
            return (W - X1, H - B, W - X0, H - T)

        out = []
        for direction in ("up", "down", "flip"):
            chars = [turn(c, direction) for c in p.rotated if c.get("dir") == direction and not c.get("space")]
            if not chars:
                continue
            spaces = [turn(c, direction) for c in p.rotated if c.get("dir") == direction and c.get("space")]
            lines = []
            for band in _bands(chars):
                toks = _tokens(band["chars"], spaces)
                if toks:
                    toks[0].space = False
                    line = Line(page=p.number, toks=toks, col=-1, tag="rotated")
                    line.box = unturn(line, direction)
                    lines.append(line)
            out.extend(sorted(lines, key=lambda l: (l.top, l.x0)))
        return out

    # -- footnotes ---------------------------------------------------------
    def _footnote_regions(self) -> None:
        for p in self.pages:
            body = [l for l in p.lines if l.tag != "rotated"]
            if not body:
                continue
            marked = set()
            for x0, x1, y in sorted(p.rules, key=lambda r: r[2]):
                if y < 0.4 * p.height or not (15 <= x1 - x0):
                    continue
                region_w = self._region_width(p, x0)
                if x1 - x0 > 0.6 * region_w:
                    continue
                if any(l.top - 1 <= y <= l.bottom + 1 and 0 <= l.x0 - x1 < 3 * l.size for l in body):
                    continue  # a rule with text right after it, as for a repeated author in a reference list
                below = [l for l in body if l.top >= y - 1 and x0 - 4 <= l.x0 <= x0 + 0.5 * region_w]
                if not below or not any(self._marker_of(l, lenient=True) is not None for l in below):
                    continue
                first = min(below, key=lambda l: l.top)
                if first.top - y > 3 * max(first.size, 6) or first.size > self.body_size * 0.95:
                    continue
                if any(l.size > self.body_size * 0.95 and not l.hidden_only for l in below):
                    below = [l for l in below if l.top < min(b.top for b in below if b.size > self.body_size * 0.95)]
                for l in below:
                    marked.add(id(l))
                    l.role = "footnote"
            if not marked:
                self._footnotes_without_rule(p, body)

    def _region_width(self, p: PageInfo, x0: float) -> float:
        if p.gutter:
            g0, g1 = p.gutter
            xs = [l.x1 for l in p.lines] or [p.width]
            return g0 - x0 if x0 < g0 else max(xs) - g1
        xs0 = [l.x0 for l in p.lines] or [0]
        xs1 = [l.x1 for l in p.lines] or [p.width]
        return max(xs1) - min(xs0)

    def _footnotes_without_rule(self, p: PageInfo, body: list) -> None:
        for col in sorted({l.col for l in body}):
            lines = sorted((l for l in body if l.col == col or l.col == -1), key=lambda l: l.top)
            tail = []
            for l in reversed(lines):
                if l.size <= self.body_size * 0.92 and not l.hidden_only and l.top > 0.5 * p.height:
                    tail.insert(0, l)
                else:
                    break
            if not tail or len(tail) == len(lines):
                continue
            if self._marker_of(tail[0], lenient=True) is None:
                continue
            above = lines[len(lines) - len(tail) - 1]
            if tail[0].top - above.bottom < 0.3 * tail[0].size or above.size < self.body_size * 0.95:
                continue
            for l in tail:
                l.role = "footnote"

    @staticmethod
    def _marker_of(line: Line, expected: Optional[int] = None, lenient: bool = False) -> Optional[str]:
        """The marker that opens a line of the footnote area: a superscript, a number or
        symbol followed by a space, or one glued to the first word ("1Payments").

        A number that is neither raised nor the expected next footnote number is not a
        marker: footnote text can wrap onto a line that starts with a number."""
        toks = [t for t in line.toks if not t.hidden]
        if not toks:
            return None
        t = toks[0]
        if t.script == "super" and MARKER_TEXT.fullmatch(t.text) and len(toks) > 1:
            return t.text
        m = re.fullmatch(r"(\d{1,3}|[*\u2020\u2021\u00a7\u00b6\u2016#\u2217]{1,3})[.)]?", t.text)
        marker = m.group(1) if m and len(toks) > 1 and toks[1].space else None
        if marker is None:
            g = re.match(r"[*\u2020\u2021\u00a7\u00b6\u2016#\u2217]{1,3}(?=\S)|\d{1,3}(?=[A-Z\u00c0-\u00de\u201c\"(])", t.text)
            marker = g.group(0) if g else None
        if marker is not None and marker.isdigit() and not lenient:
            value = int(marker)
            if expected is None and value > 5 or expected is not None and value not in (expected, expected + 1):
                return None
        return marker

    @staticmethod
    def _cut_marker(line: Line, marker: str) -> Tok:
        """Mark the opening marker of a footnote line, splitting it off a glued word."""
        i = next(k for k, t in enumerate(line.toks) if not t.hidden)
        t = line.toks[i]
        if t.text == marker or t.text.rstrip(".)") == marker:
            t.marker = True
            line._cache = None
            return t
        cut = t.x0 + (t.x1 - t.x0) * len(marker) / max(len(t.text), 1)
        head = Tok(marker, t.x0, cut, t.top, t.bottom, t.size, font=t.font, hidden=t.hidden, bold=t.bold,
                   italic=t.italic, marker=True, color=t.color)
        t.text, t.x0, t.space = t.text[len(marker):], cut, False
        line.toks.insert(i, head)
        line._cache = None
        return head

    def _group_footnotes(self) -> None:
        last, expected = None, None
        for p in self.pages:
            lines = [l for l in p.lines if l.role == "footnote"]
            for l in lines:
                marker = self._marker_of(l, expected, lenient=l is lines[0])
                if marker is not None and marker.isdigit():
                    expected = int(marker) + 1
                if marker is not None:
                    self._cut_marker(l, marker)
                    last = {"marker": marker, "lines": [l], "page": p.number, "anchor": None}
                    self.footnotes.append(last)
                elif last is not None and (last["page"] == p.number or l is lines[0]):
                    last["lines"].append(l)
                else:
                    last = {"marker": None, "lines": [l], "page": p.number, "anchor": None}
                    self.footnotes.append(last)
        by_page = defaultdict(list)
        for p in self.pages:
            for l in p.lines:
                if l.role == "body":
                    by_page[p.number].append(l)
        for fn in self.footnotes:
            m = fn["marker"]
            if m is None:
                continue
            for page in (fn["page"], fn["page"] - 1, fn["page"] + 1):
                hit = None
                for l in by_page.get(page, []):
                    for t in l.toks:
                        if t.script == "super" and not t.marker and t.text == m:
                            hit = (l, t)
                            break
                    if hit:
                        break
                if hit:
                    hit[1].marker = True
                    hit[0]._cache = None
                    fn["anchor"] = hit[0]
                    fn["anchor_tok"] = hit[1]
                    break

    # -- line numbers and statistics -------------------------------------------
    def _number_lines(self) -> None:
        for p in self.pages:
            n = 0
            pending = []
            for l in p.lines:
                if l.hidden_only:
                    pending.append(l)
                    continue
                n += 1
                l.no = n
                for h in pending:
                    h.no = n
                pending = []
            for h in pending:
                h.no = n + 1

    def _layout_stats(self) -> None:
        gaps = defaultdict(list)
        lefts, rights = defaultdict(list), defaultdict(list)
        for p in self.pages:
            layout = 2 if p.gutter else 1
            for col in (0, 1, -1):
                lines = [l for l in p.lines if l.col == col and l.role == "body" and not l.hidden_only
                         and l.tag != "rotated"]
                lines.sort(key=lambda l: l.top)
                for a, b in zip(lines, lines[1:]):
                    if abs(a.size - b.size) < 0.3:
                        g = b.top - a.bottom
                        if -1 < g < 2.5 * a.size:
                            gaps[round(a.size * 2) / 2].append(g)
                normal = [l for l in lines if abs(l.size - self.body_size) <= 1.0]
                lefts[(layout, col)].extend(l.x0 for l in normal)
                rights[(layout, col)].extend(l.x1 for l in normal)
                self.edges[(p.number, col)] = normal
        self.gap = {s: statistics.median(v) for s, v in gaps.items() if v}
        self.doc_edges = {k: (_percentile(lefts[k], 0.1), _percentile(rights[k], 0.9)) for k in lefts if lefts[k]}
        page_edges = {}
        for (page, col), normal in self.edges.items():
            p = self.pages[page - 1]
            if len(normal) >= 6:
                page_edges[(page, col)] = (_percentile([l.x0 for l in normal], 0.1),
                                           _percentile([l.x1 for l in normal], 0.9))
            else:
                key = (2 if p.gutter else 1, col)
                if key in self.doc_edges:
                    page_edges[(page, col)] = self.doc_edges[key]
                elif normal:
                    page_edges[(page, col)] = (min(l.x0 for l in normal), max(l.x1 for l in normal))
        self.edges = page_edges
        starts = 0
        for p in self.pages:
            for col in (0, 1, -1):
                lines = [l for l in p.lines if l.col == col and l.role == "body" and abs(l.size - self.body_size) <= 0.6]
                for a, b in zip(lines, lines[1:]):
                    left = self.col_left(b)
                    if 0.7 * b.size <= b.x0 - left <= 4 * b.size and a.x0 - left < 0.5 * a.size:
                        starts += 1
        self.indent_style = starts >= 2

    def col_left(self, l: Line) -> float:
        e = self.edges.get((l.page, l.col))
        return e[0] if e else l.x0

    def col_right(self, l: Line) -> float:
        e = self.edges.get((l.page, l.col))
        return e[1] if e else l.x1

    def typical_gap(self, size: float) -> float:
        if not self.gap:
            return 0.3 * size
        key = min(self.gap, key=lambda s: abs(s - size))
        return self.gap[key] if abs(key - size) <= 1.5 else 0.3 * size

    def _vocabulary(self) -> None:
        for p in self.pages:
            for l in p.lines:
                words = l.text.split()
                for i, w in enumerate(words):
                    w = w.strip(".,;:!?()[]\u201c\u201d\"'\u2018\u2019").lower()
                    if not w:
                        continue
                    if re.fullmatch(r"[a-z\u00df-\u024f]+(?:-[a-z\u00df-\u024f]+)+", w) and i < len(words) - 1:
                        self.hyphen_words.add(w)
                        self.hyphen_heads.add(w.split("-")[0])
                    if re.fullmatch(r"[a-z\u00df-\u024f]+", w) and i < len(words) - 1:
                        self.vocab.add(w)

    # -- classification ----------------------------------------------------
    def _flow(self) -> list:
        return [l for p in self.pages for l in p.lines if l.role == "body"]

    def _classify(self) -> None:
        flow = self._flow()
        for i, l in enumerate(flow):
            prev = flow[i - 1] if i > 0 else None
            nxt = flow[i + 1] if i + 1 < len(flow) else None
            if l.tag in ("rotated", "figure_text"):
                continue
            if self._is_caption(l, prev):
                l.tag = "caption"
            elif self._heading_info(l, prev, nxt) is not None:
                l.tag = "heading"
            elif self._is_equation(l):
                l.tag = "equation"
        sizes = []
        for l in flow:
            info = self._heading_info(l, None, None, loose=True) if l.tag == "heading" else None
            if info and info["number"] and "." not in info["number"]:
                sizes.append(l.size)
        self.level1_size = Counter(sizes).most_common(1)[0][0] if sizes else None

    def _starts_block(self, l: Line, prev: Optional[Line]) -> bool:
        if prev is None or prev.page != l.page or prev.col != l.col:
            return True
        if abs(prev.size - l.size) > 0.6 or abs(prev.bold - l.bold) > 0.5:
            return True
        if l.top - prev.bottom > self.typical_gap(prev.size) + 0.3 * prev.size:
            return True
        left, right = self.col_left(l), self.col_right(l)
        if l.x0 - left > 1.0 * l.size and abs((l.x0 + l.x1) / 2 - (left + right) / 2) < 2 * l.size:
            return True  # centred
        if prev.x1 < right - 2 * prev.size and re.search(r"[.!?:]['\")\u201d]?$", prev.text):
            return True
        return False

    def _is_caption(self, l: Line, prev: Optional[Line]) -> bool:
        m = CAPTION.match(l.text)
        if not m:
            return False
        if not self._starts_block(l, prev):
            return False
        rest = l.text[m.end():]
        if not m.group("sep") and rest[:1].islower():
            return False
        return True

    def _heading_info(self, l: Line, prev: Optional[Line], nxt: Optional[Line], loose: bool = False) -> Optional[dict]:
        text = l.text.strip()
        if not text or len(text) > 120 or len(text.split()) > 16 or l.hidden_only:
            return None
        if text.endswith((",", ";")) or re.search(r"[.:]\s*$", text) and not re.match(r"^[\dA-Z.]+\.?\s", text):
            if not SECTION_NAMES.match(text.rstrip(".:")):
                return None
        larger = l.size >= self.body_size + 1.0
        bold = l.bold >= 0.85
        caps = text.isupper() and len(re.sub(r"[^A-Z]", "", text)) >= 4
        if not (larger or bold or caps):
            return None
        if l.size < self.body_size * 0.85:
            return None
        if not loose:
            if prev is not None and prev.page == l.page and prev.col == l.col and prev.tag != "heading":
                if l.top - prev.bottom < 0.5 * self.typical_gap(prev.size) and prev.size == l.size and prev.bold == l.bold:
                    return None
            if nxt is not None and nxt.page == l.page and nxt.col == l.col:
                if abs(nxt.size - l.size) < 0.3 and abs(nxt.bold - l.bold) < 0.2 and abs(nxt.italic - l.italic) < 0.2:
                    if len(nxt.text) > 60 and not NUMBERED_HEADING.match(nxt.text):
                        return None  # a paragraph in the same style
        number, title, appendix = None, text, False
        am = APPENDIX_HEADING.match(text)
        nm = NUMBERED_HEADING.match(text)
        if am and (am.group("num") or not am.group("title")):
            number, title, appendix = am.group("num"), text, True
        elif nm:
            num = nm.group("num")
            if re.fullmatch(r"[A-Z](?:\.\d+)*", num):
                if not nm.group("title")[:1].isupper():
                    return None
                appendix = True
            elif re.fullmatch(r"[IVX]+", num) and not re.match(r"^[IVX]+\.\s", text):
                return None
            number = num
        elif not (SECTION_NAMES.match(text.rstrip(".:")) or larger or caps or bold):
            return None
        if number is None and not SECTION_NAMES.match(text.rstrip(".:")) and not larger and not caps:
            # an unnumbered bold line: a heading only if short and alone
            if len(text.split()) > 8:
                return None
        if number and "." in number:
            level = number.count(".") + 1
        elif number:
            level = 1
        elif self.level1_size and l.size < self.level1_size - 0.5:
            level = 2
        else:
            level = 1
        return {"number": number, "text": text, "level": level, "appendix": appendix}

    def _is_equation(self, l: Line) -> bool:
        text = l.text
        if len(text) > 160 or l.hidden_only:
            return False
        toks = [t for t in l.toks if not t.marker]
        if not toks:
            return False
        last = toks[-1]
        numbered = bool(re.fullmatch(r"\(\s*[A-Z]?\d+[a-z]?(?:\.\d+)?\s*\)", last.text)) and len(toks) > 1 \
            and last.x0 - toks[-2].x1 > 2 * l.size
        chars = [ch for ch in text if not ch.isspace()]
        if not chars:
            return False
        mathy = sum(1 for ch in chars if ch in MATH_CHARS) + sum(1 for t in toks if t.italic and len(t.text) == 1)
        mathy += sum(1 for t in toks if t.script == "sub")
        ratio = mathy / max(len(toks), 1)
        words = re.findall(r"[A-Za-z]{4,}", text)
        left = self.col_left(l)
        indented = l.x0 - left > 2 * l.size
        if numbered and (ratio >= 0.15 or "=" in text):
            return True
        return indented and ratio >= 0.35 and len(words) <= 3

    # -- tables and figures ------------------------------------------------
    def _cells(self, toks: list, size: float) -> list:
        """Split tokens into cells at gaps wider than about one em."""
        cells = []
        for t in sorted((t for t in toks if not t.marker), key=lambda t: t.x0):
            if cells and t.x0 - cells[-1]["x1"] < max(0.9 * size, 6.0):
                c = cells[-1]
                c["text"] += (" " if t.space or t.x0 - c["x1"] > 0.18 * size else "") + t.text
                c["x1"] = max(c["x1"], t.x1)
            else:
                cells.append({"text": t.text, "x0": t.x0, "x1": t.x1})
        return cells

    @staticmethod
    def _numeric(text: str) -> bool:
        core = re.sub(r"[\s*\u2020\u2021,.%$()\[\]\u2212\u2013\-+<>=]", "", text)
        return bool(core) and (core.isdigit() or bool(re.fullmatch(r"[\d]+[A-Za-z]?", core)))

    def _table_like(self, l: Line, region_w: float) -> bool:
        cells = self._cells(l.toks, l.size)
        if len(cells) >= 2:
            return True
        text = l.text
        tokens = text.split()
        if tokens and sum(1 for t in tokens if self._numeric(t)) >= 0.5 * len(tokens):
            return True
        return False

    def _find_tables(self) -> None:
        flow = self._flow()
        index = {id(l): i for i, l in enumerate(flow)}
        for l in flow:
            if l.tag != "caption":
                continue
            m = CAPTION.match(l.text)
            if not m.group("kind").lower().startswith("tab"):
                continue
            p = self.pages[l.page - 1]
            region = self._region(p, l)
            same = [x for x in flow if x.page == l.page and region[0] - 2 <= x.x0 and x.x1 <= region[1] + 2
                    and x is not l]
            i = index[id(l)]
            cap_lines = [l]
            j = i + 1
            while j < len(flow) and flow[j].page == l.page and flow[j].tag == "" and flow[j] in same and \
                    abs(flow[j].size - l.size) < 0.3 and not self._table_like(flow[j], region[1] - region[0]) and \
                    flow[j].top - flow[j - 1].bottom < self.typical_gap(l.size) + 0.3 * l.size and \
                    len(cap_lines) < 4:
                cap_lines.append(flow[j])
                j += 1
            below = [x for x in same if x.top >= cap_lines[-1].bottom - 1 and x.tag not in ("heading", "caption")]
            below.sort(key=lambda x: x.top)
            rows = self._table_rows_from(below, p, region, l)
            if not rows["lines"]:
                above = [x for x in same if x.bottom <= l.top + 1 and x.tag not in ("heading", "caption")]
                above.sort(key=lambda x: -x.top)
                rows = self._table_rows_from(above, p, region, l, upward=True)
            if not rows["lines"]:
                continue
            for x in cap_lines:
                x.used = x is not l
            for x in rows["lines"] + rows["notes"]:
                x.used = True
                x.tag = "table"
            self.tables[id(l)] = {"caption_lines": cap_lines, "number": m.group("num"), **rows}

    def _region(self, p: PageInfo, l: Line) -> tuple:
        if p.gutter and l.col != -1:
            e = self.edges.get((p.number, l.col))
            if e:
                return (min(e[0], l.x0), max(e[1], l.x1))
            g0, g1 = p.gutter
            return (min(x.x0 for x in p.lines), g0) if l.col == 0 else (g1, max(x.x1 for x in p.lines))
        xs = [x for x in p.lines if x.tag != "rotated"]
        return (min(x.x0 for x in xs), max(x.x1 for x in xs))

    def _table_rows_from(self, cand: list, p: PageInfo, region: tuple, cap: Line, upward: bool = False) -> dict:
        width = region[1] - region[0]
        rules = [r for r in p.rules if r[1] - r[0] >= 0.25 * width and region[0] - 5 <= r[0] and r[1] <= region[1] + 5]
        lines, notes = [], []
        prev = cap
        for x in cand:
            gap = (x.top - prev.bottom) if not upward else (prev.top - x.bottom)
            if gap > 4 * max(x.size, prev.size) and lines:
                break
            if not upward and lines and NOTES_START.match(x.text):
                break
            if self._table_like(x, width) or (not upward and not lines and gap < 3 * x.size and len(x.text) < 0.5 * width / max(x.size * 0.5, 1)
                                                 and self._between_rules(x, cap, rules)):
                lines.append(x)
                prev = x
                continue
            if lines and self._between_rules(x, lines[0] if not upward else cap, rules, upto=lines[-1]):
                lines.append(x)
                prev = x
                continue
            break
        if len(lines) < 2:
            return {"lines": [], "notes": [], "rules": rules}
        if upward:
            lines.reverse()
        else:
            last = lines[-1]
            after = [x for x in cand if x.top > last.bottom - 1 and x not in lines]
            for x in after:
                gap = x.top - (notes[-1].bottom if notes else last.bottom)
                if not notes:
                    if not (NOTES_START.match(x.text) or (x.size < self.body_size - 0.4 and gap < 2.5 * x.size)):
                        break
                    if gap > 3 * x.size:
                        break
                else:
                    if abs(x.size - notes[0].size) > 0.4 or gap > self.typical_gap(x.size) + 0.5 * x.size:
                        break
                    if x.x0 - notes[0].x0 > 1.5 * x.size and x.size >= self.body_size - 0.4:
                        break
                notes.append(x)
        return {"lines": lines, "notes": notes, "rules": rules}

    @staticmethod
    def _between_rules(x: Line, start: Line, rules: list, upto: Optional[Line] = None) -> bool:
        ys = sorted(r[2] for r in rules if r[2] >= start.top - 2)
        if len(ys) < 2:
            return False
        return ys[0] - 2 <= x.center <= ys[-1] + 2

    def _table_cells(self, info: dict) -> list:
        """Rows of cell text, columns aligned across rows."""
        rows = []
        for l in info["lines"]:
            cells = self._cells(l.toks, l.size)
            if cells:
                rows.append(cells)
        if not rows:
            return []
        n = Counter(len(r) for r in rows if len(r) > 1)
        width = max(len(r) for r in rows)
        template = [r for r in rows if len(r) == width]
        cols = [[min(r[k]["x0"] for r in template), max(r[k]["x1"] for r in template)] for k in range(width)]
        out = []
        for r in rows:
            row = [""] * width
            for c in r:
                best, score = None, -math.inf
                for k, (a, b) in enumerate(cols):
                    ov = min(b, c["x1"]) - max(a, c["x0"])
                    s = ov if ov > 0 else -min(abs(c["x0"] - b), abs(a - c["x1"]))
                    if s > score:
                        best, score = k, s
                text = c["text"].replace("\u2212", "-").strip()
                row[best] = f"{row[best]} {text}".strip() if row[best] else text
            out.append(row)
        return out

    def _figure_text(self) -> None:
        """Tag text drawn inside plots and diagrams (axis labels, legends) as figure text."""
        for p in self.pages:
            if not p.graphics:
                continue
            pad = 1.5 * self.body_size
            for l in p.lines:
                if l.role != "body" or l.tag == "rotated":
                    continue
                cx, cy = (l.x0 + l.x1) / 2, l.center
                for x0, top, x1, bottom, bars_only in p.graphics:
                    inside = x0 <= cx <= x1 and top <= cy <= bottom
                    near = x0 - pad <= cx <= x1 + pad and top - pad <= cy <= bottom + pad
                    short = (l.x1 - l.x0) < 0.6 * (x1 - x0 + 2 * pad) or l.size < self.body_size - 0.5
                    if (inside or near) and short and not CAPTION.match(l.text):
                        if bars_only and inside and len(l.text) > 40:
                            continue  # long text over shaded boxes is a table, not a chart
                        l.tag = "figure_text"
                        break

    def _find_figures(self) -> None:
        flow = self._flow()
        claimed = set()
        for l in flow:
            if l.tag != "caption" or id(l) in self.tables:
                continue
            m = CAPTION.match(l.text)
            if not m.group("kind").lower().startswith(("fig", "chart", "exh")):
                continue
            p = self.pages[l.page - 1]
            region = self._region(p, l)
            best, dist = None, math.inf
            for k, im in enumerate(p.images):
                if (p.number, k) in claimed or im[2] < region[0] - 5 or im[0] > region[1] + 5:
                    continue
                d = l.top - im[3] if im[3] <= l.top + 2 else (im[1] - l.bottom if im[1] >= l.bottom - 2 else math.inf)
                if 0 <= d < dist and d < 0.5 * p.height:
                    best, dist = k, d
            info = {"number": m.group("num"), "image": None}
            if best is None:
                near = []
                for g in p.graphics:
                    if g[2] < region[0] - 5 or g[0] > region[1] + 5:
                        continue
                    d = l.top - g[3] if g[3] <= l.top + 2 else (g[1] - l.bottom if g[1] >= l.bottom - 2 else math.inf)
                    if 0 <= d < 0.4 * p.height:
                        near.append((d, g))
                if near:
                    info["image"] = tuple(min(near)[1][:4])
            if best is not None:
                claimed.add((p.number, best))
                im = p.images[best]
                info["image"] = im
                for x in p.lines:
                    if x is not l and x.role == "body" and im[0] - 2 <= x.x0 and x.x1 <= im[2] + 2 \
                            and im[1] - 2 <= x.top and x.bottom <= im[3] + 2:
                        x.tag = "figure_text"
            self.figures[id(l)] = info
        self._uncaptioned = []
        for p in self.pages:
            for k, im in enumerate(p.images):
                if (p.number, k) in claimed:
                    continue
                if im[2] - im[0] >= 0.2 * p.width and im[3] - im[1] >= 0.1 * p.height:
                    self._uncaptioned.append((p.number, im))
        if self._uncaptioned:
            self.pm.metadata["images_without_caption"] = [{"page": page, "bbox": [_rnd(v) for v in im]}
                                                          for page, im in self._uncaptioned]

    # -- blocks --------------------------------------------------------------
    def _new_block(self, kind: str, text: str, lines: list, *, level=None, parent=None, attrs=None,
                   bbox_items=None, offsets=None) -> Block:
        self.n_block += 1
        first = lines[0]
        on_first = [l for l in lines if l.page == first.page]
        bbox = _bbox(bbox_items) if bbox_items else _bbox(on_first)
        block = Block(id=f"tmp{self.n_block}", kind=kind, text=text,
                      anchor=Anchor(page=first.page, page_line=first.no, bbox=bbox),
                      section=list(self.section_path), level=level, parent=parent, attrs=dict(attrs or {}))
        if offsets is not None and len(lines) > 1:
            block.attrs["lines"] = [[o, l.page, l.no] for o, l in zip(offsets, lines)]
        for l in lines:
            l.used = True
            if l.block is None:
                l.block = block
        self.blocks.append(block)
        return block

    def _keep_hyphen(self, head: str, tail: str) -> bool:
        h = re.sub(r"^.*[^A-Za-z\u00c0-\u024f]", "", head).lower()
        t = re.sub(r"[^A-Za-z\u00c0-\u024f].*$", "", tail).lower()
        if not h or not t:
            return False
        if f"{h}-{t}" in self.hyphen_words:
            return True
        if f"{h}{t}" in self.vocab:
            return False
        return h in self.hyphen_heads or h in COMPOUND_HEADS or t in COMPOUND_TAILS

    def join(self, texts: list) -> tuple:
        """Join line texts into one string; return it and each line's start offset.

        Hyphenated line breaks are joined with textutil.dehyphenate, except that a
        compound seen elsewhere in the paper ("present-biased") keeps its hyphen, and
        URLs, DOIs and ranges broken after a dash are joined without a space."""
        out, starts = "", []
        for raw in texts:
            line = raw.strip()
            if not line:
                starts.append(len(out))
                continue
            if not out:
                out = line
                starts.append(0)
                continue
            last = out.split(" ")[-1]
            if URL_TAIL.search(last) and re.search(r"[/._\-]$", last) or re.search(r"\w[\u2013\u2014]$", out):
                starts.append(len(out))
                out += line
            elif out.endswith("-") and len(out) > 1 and out[-2].isalpha() and line[:1].islower() \
                    and self._keep_hyphen(last[:-1], line.split(" ")[0]):
                starts.append(len(out))
                out += line
            else:
                out = dehyphenate([out, line])
                starts.append(len(out) - len(line))
        return out, starts

    def _render_lines(self, lines: list) -> tuple:
        """Text, start offsets, and for each character its token (None for spaces)."""
        texts = [l.render() for l in lines]
        text, starts = self.join([t[0] for t in texts])
        owners = [None] * len(text)
        for (ltext, lowners, _), s in zip(texts, starts):
            stripped = ltext.strip()
            lead = len(ltext) - len(ltext.lstrip())
            for k in range(len(stripped)):
                if s + k < len(owners):
                    owners[s + k] = lowners[lead + k]
        return text, starts, owners

    def _text_block(self, kind: str, lines: list, **kw) -> Optional[Block]:
        text, starts, owners = self._render_lines(lines)
        if not text.strip():
            for l in lines:
                l.used = True
            return None
        block = self._new_block(kind, text, lines, offsets=starts, **kw)
        block._owners = owners
        return block

    # -- front matter ---------------------------------------------------------
    def _front_end(self, flow: list) -> int:
        """Index of the first line after the front matter of the first pages."""
        for i, l in enumerate(flow):
            if l.page > 2:
                return i
            if l.tag == "heading":
                info = self._heading_info(l, flow[i - 1] if i else None, flow[i + 1] if i + 1 < len(flow) else None)
                if info and (info["number"] or (SECTION_NAMES.match(info["text"].rstrip(".:"))
                                                 and not info["text"].lower().startswith("abstract"))):
                    return i
        return 0

    @staticmethod
    def _prominence(l: Line) -> float:
        return l.size + (2.0 if l.bold >= 0.6 else 0.0) + (0.5 if l.text.isupper() else 0.0)

    def _front_matter(self, lines: list) -> None:
        rotated = [l for l in lines if l.tag == "rotated"]
        lines = [l for l in lines if l.tag != "rotated"]
        if not lines:
            for l in rotated:
                self._text_block("other", [l], attrs={"rotated": True})
            return
        label = re.compile(rf"(?i)^(?:abstract|keywords?|key words|jel\b)|{DATE_LINE.pattern[1:]}")
        first_page = [l for l in lines if l.page == lines[0].page and not l.hidden_only and not label.match(l.text.strip())
                      and not SECTION_NAMES.match(l.text.strip().rstrip(".:"))]
        title_lines = []
        i = 0
        if first_page:
            top = max(self._prominence(l) for l in first_page)
            if top >= self.body_size + 1.0:
                first = next(l for l in first_page if self._prominence(l) >= top - 0.6)
                i = lines.index(first)
                for l in lines[:i]:
                    self._text_block("front_matter", [l])
                while i < len(lines) and lines[i].page == first.page and self._prominence(lines[i]) >= top - 0.6 \
                        and not label.match(lines[i].text.strip()) and len(title_lines) < 5:
                    title_lines.append(lines[i])
                    i += 1
        if title_lines:
            block = self._text_block("title", title_lines)
            if block:
                self.pm.title = block.text
        rest = lines[i:]
        k = 0
        state = "authors"
        while k < len(rest):
            l = rest[k]
            text = l.text.strip()
            low = text.lower()
            if l.hidden_only:
                self._text_block("paragraph", [l])
                k += 1
                continue
            if re.fullmatch(r"abstract[.:]?", low):
                l.used = True
                l.block = None
                state = "abstract"
                k += 1
                group = self._collect_paragraph(rest, k)
                while group:
                    first_text = group[0].text.strip().lower()
                    if re.match(r"(jel\b|keywords?|key words)", first_text):
                        break
                    self._text_block("abstract", group, attrs={"label": text.rstrip(".:")})
                    k += len(group)
                    group = self._collect_paragraph(rest, k) if k < len(rest) else []
                continue
            if re.match(r"(jel\b|jel codes?|jel classification)", low) or re.match(r"(keywords?|key words)\s*[:.\u2014-]", low):
                kind = "jel" if low.startswith("jel") else "keywords"
                group = [l]
                while k + len(group) < len(rest):
                    nxt = rest[k + len(group)]
                    if nxt.used or abs(nxt.size - l.size) > 0.3 or nxt.top - group[-1].bottom > self.typical_gap(l.size) + 0.3 * l.size \
                            or re.match(r"(?i)(jel\b|keywords?|key words)", nxt.text.strip()) or nxt.page != l.page:
                        break
                    group.append(nxt)
                self._text_block(kind, group)
                k += len(group)
                continue
            abstract_inline = re.match(r"(?i)abstract\s*[.:\u2014-]\s*", text)
            if abstract_inline:
                group = self._collect_paragraph(rest, k)
                self._text_block("abstract", group, attrs={"label": "Abstract"})
                k += len(group)
                state = "abstract"
                continue
            if DATE_LINE.match(text) or re.match(r"(?i)(this|first|current) (version|draft)|(preliminary|draft|work(ing)? paper)\b", text):
                self._text_block("front_matter", [l], attrs={"role": "date" if DATE_LINE.match(text) else "note"})
                k += 1
                continue
            if state == "authors" and self._author_line(l):
                self._author_blocks(l)
                k += 1
                continue
            if state == "authors" and (re.search(r"@|\b(?:university|universit\u00e4t|universidad|institute|school|department|"
                                                 r"college|centre|center|bank|nber|cepr|iza|cesifo)\b", low)):
                self._text_block("front_matter", [l], attrs={"role": "affiliation"})
                k += 1
                continue
            if l.toks and l.toks[0].script == "super" and state == "authors":
                self._text_block("front_matter", [l], attrs={"role": "affiliation"})
                k += 1
                continue
            group = self._collect_paragraph(rest, k)
            narrow = group and (self.col_right(group[0]) - self.col_left(group[0])) - (max(g.x1 for g in group) - min(g.x0 for g in group)) > 3 * group[0].size
            smaller = group and group[0].size < self.body_size - 0.4
            if state != "done" and not any(b.kind == "abstract" for b in self.blocks) and len(group) >= 2 and (narrow or smaller):
                self._text_block("abstract", group)
                state = "abstract"
            else:
                self._text_block("paragraph", group)
                state = "done"
            k += len(group)
        for l in rotated:
            self._text_block("other", [l], attrs={"rotated": True})
        self.pm.authors = [b.text for b in self.blocks if b.kind == "author"]

    def _author_line(self, l: Line) -> bool:
        """A line of author names: short, capitalised words, no digits or addresses.
        Superscript affiliation and footnote marks are ignored."""
        words = [t.text for t in l.toks if t.script != "super" and not t.marker and not t.hidden]
        text = " ".join(words)
        if not words or len(words) > 16 or re.search(r"\d|@|https?:", text):
            return False
        if re.search(r"(?i)\b(university|universit\u00e4t|institute|school|department|college|center|centre|bank|"
                     r"abstract|introduction|working|paper|draft|version)\b", text):
            return False
        names = [w for w in re.split(r"[\s,;\u00b7|\u2022]+", text) if w and w.lower() not in ("and", "&")]
        caps = sum(1 for w in names if w[:1].isupper())
        return bool(names) and caps >= 0.8 * len(names) and l.size >= self.body_size - 0.6

    def _author_blocks(self, l: Line) -> None:
        """One author block per name. Names are split at wide gaps, commas, "and" and "&";
        superscript affiliation marks are left out of the names."""
        groups, cur = [], []
        for t in l.toks:
            if cur and t.x0 - cur[-1].x1 > 2.0 * l.size:
                groups.append(cur)
                cur = []
            cur.append(t)
        if cur:
            groups.append(cur)
        for group in groups:
            names, name, marks = [], [], []
            for t in group:
                if t.marker:
                    (marks if name else (names[-1][1] if names else marks)).append(t)
                    continue
                if t.script == "super" or t.hidden:
                    continue
                if t.text.lower() in ("and", "&", "\u00b7", "|", "\u2022"):
                    if name:
                        names.append((name, marks))
                    name, marks = [], []
                    continue
                name.append(t)
                if t.text.endswith((",", ";")):
                    names.append((name, marks))
                    name, marks = [], []
            if name:
                names.append((name, marks))
            for toks, marks in names:
                text = "".join((" " if k and t.space else "") + t.text for k, t in enumerate(toks)).strip().rstrip(",;")
                if not text:
                    continue
                block = self._new_block("author", text, [l], bbox_items=toks)
                block._marker_positions = list(marks)
        l.used = True

    # -- body -------------------------------------------------------------------
    def _same_paragraph(self, prev: Line, cur: Line) -> bool:
        if cur.tag or cur.used:
            return False
        if abs(cur.size - prev.size) > max(0.6, 0.06 * prev.size) or abs(cur.bold - prev.bold) > 0.5:
            return False
        if cur.hidden_only != prev.hidden_only:
            return False
        em = prev.size
        if cur.page != prev.page or cur.col != prev.col:
            return self._continues(prev, cur)
        gap = cur.top - prev.bottom
        if gap > self.typical_gap(prev.size) + max(0.45 * prev.size, 2.5) or gap < -0.5 * prev.size:
            return False
        left = self.col_left(cur)
        if 0.7 * em <= cur.x0 - left <= 6 * em and prev.x0 - left < 0.5 * em:
            return False  # first-line indent
        if LIST_START.match(cur.text) and not LIST_START.match(prev.text) and cur.x0 <= prev.x0 + 2:
            return False
        if LIST_START.match(cur.text) and LIST_START.match(prev.text):
            return False
        if not self.indent_style and prev.x1 < self.col_right(prev) - 3 * em and re.search(r"[.!?:]['\")\u201d]?$", prev.text) \
                and cur.text[:1].isupper():
            return False
        return True

    def _continues(self, prev: Line, cur: Line) -> bool:
        """Does a paragraph go on from the end of one column or page into the next?"""
        em = prev.size
        if cur.x0 - self.col_left(cur) >= 0.7 * em:
            return False
        text = prev.text.rstrip()
        if text.endswith("-"):
            return True
        if prev.x1 < self.col_right(prev) - 1.5 * em:
            return False
        if not self.indent_style and re.search(r"[.!?]['\")\u201d]?$", text) and cur.text[:1].isupper():
            return False
        return True

    def _collect_paragraph(self, flow: list, i: int) -> list:
        group = [flow[i]]
        j = i + 1
        while j < len(flow):
            cur = flow[j]
            prev = group[-1]
            if cur.used and (cur.page != prev.page or cur.col != prev.col) and cur.tag in ("table", "figure_text"):
                j += 1  # a float at the top of the next column: the paragraph may resume after it
                continue
            if cur.tag == "caption" and (cur.page != prev.page or cur.col != prev.col) and self._float_ahead(flow, j):
                j += 1
                continue
            if cur.tag == "figure_text" and (cur.page != prev.page or cur.col != prev.col):
                j += 1
                continue
            if not self._same_paragraph(prev, cur):
                break
            group.append(cur)
            j += 1
        return group

    def _float_ahead(self, flow: list, j: int) -> bool:
        """A caption at the top of a column whose float lines follow it."""
        cap = flow[j]
        return id(cap) in self.tables or id(cap) in self.figures

    def _build_blocks(self) -> None:
        flow = self._flow()
        end = self._front_end(flow)
        if end:
            self._front_matter(flow[:end])
        refs_mode = False
        i = end
        while i < len(flow):
            l = flow[i]
            if l.used:
                i += 1
                continue
            if l.tag == "rotated":
                group = [l]
                while i + len(group) < len(flow) and flow[i + len(group)].tag == "rotated" and flow[i + len(group)].page == l.page:
                    group.append(flow[i + len(group)])
                self._text_block("other", group, attrs={"rotated": True})
                i += len(group)
                continue
            if l.tag == "heading":
                group = [l]
                info = self._heading_info(l, flow[i - 1] if i else None, flow[i + 1] if i + 1 < len(flow) else None) \
                    or self._heading_info(l, None, None, loose=True)
                while i + len(group) < len(flow):
                    nxt = flow[i + len(group)]
                    if nxt.page == l.page and nxt.col == l.col and abs(nxt.size - l.size) < 0.3 and abs(nxt.bold - l.bold) < 0.2 \
                            and nxt.top - group[-1].bottom < self.typical_gap(l.size) + 0.3 * l.size and not nxt.used \
                            and nxt.tag in ("heading", "") and not NUMBERED_HEADING.match(nxt.text) and len(group) < 3 \
                            and not SECTION_NAMES.match(nxt.text.strip().rstrip(".:")):
                        group.append(nxt)
                    else:
                        break
                refs_mode = self._heading(group, info)
                i += len(group)
                continue
            if refs_mode:
                group = []
                j = i
                while j < len(flow) and flow[j].tag != "heading":
                    if not flow[j].used:
                        group.append(flow[j])
                    j += 1
                self._references(group)
                i = j
                continue
            if l.tag == "caption":
                self._caption(l, flow, i)
                i += 1
                continue
            if l.tag == "equation":
                group = [l]
                while i + len(group) < len(flow) and flow[i + len(group)].tag == "equation" \
                        and flow[i + len(group)].page == l.page and not flow[i + len(group)].used \
                        and flow[i + len(group)].top - group[-1].bottom < 2 * l.size:
                    group.append(flow[i + len(group)])
                num = re.search(r"\(\s*([A-Z]?\d+[a-z]?(?:\.\d+)?)\s*\)\s*$", group[-1].text)
                attrs = {"number": num.group(1), "label": f"equation:{num.group(1)}"} if num else {}
                block = self._text_block("equation", group, attrs=attrs)
                if block is not None and num:
                    self.pm.labels.append(Label(name=f"equation:{num.group(1)}", kind="equation", number=num.group(1),
                                                anchor=block.anchor, block=block.id))
                i += len(group)
                continue
            if l.tag == "figure_text":
                group = [l]
                while i + len(group) < len(flow) and flow[i + len(group)].tag == "figure_text" and flow[i + len(group)].page == l.page:
                    group.append(flow[i + len(group)])
                self._text_block("other", group, attrs={"role": "figure_text"})
                i += len(group)
                continue
            group = self._collect_paragraph(flow, i)
            kind = "list_item" if LIST_START.match(l.text) else "paragraph"
            self._text_block(kind, group)
            i += 1

    def _heading(self, lines: list, info: Optional[dict]) -> bool:
        info = info or {"number": None, "level": 1, "appendix": False}
        text, starts, owners = self._render_lines(lines)
        number = info.get("number")
        level = info.get("level", 1)
        if info.get("appendix") or (number and re.fullmatch(r"[A-Z](?:\.\d+)*", number)):
            self.appendix = True
        if re.match(r"(?i)^(online\s+)?appendi(x|ces)\b", text):
            self.appendix = True
        depth = max(level, 1)
        self.section_path = self.section_path[:depth - 1] + [text]
        attrs = {"number": number, "appendix": bool(self.appendix and (info.get("appendix") or (number and number[:1].isalpha())))}
        block = self._new_block("heading", text, lines, level=level, attrs=attrs, offsets=starts)
        block._owners = owners
        if number:
            kind = "appendix" if (number[:1].isalpha() and level == 1) or re.match(r"(?i)appendix", text) else "section"
            self.pm.labels.append(Label(name=f"{kind}:{number}", kind=kind, number=number, anchor=block.anchor,
                                        block=block.id))
            block._labels = [f"{kind}:{number}"]
        return bool(REFERENCE_HEADING.match(text.strip().rstrip(".:")))

    def _caption(self, l: Line, flow: list, i: int) -> None:
        m = CAPTION.match(l.text)
        kind_word = m.group("kind").lower()
        float_kind = "table" if kind_word.startswith("tab") else "figure"
        number = m.group("num")
        table = self.tables.get(id(l))
        cap_lines = table["caption_lines"] if table else [l]
        if not table:
            j = i + 1
            while j < len(flow) and len(cap_lines) < 6:
                nxt = flow[j]
                if nxt.used or nxt.tag or nxt.page != l.page or nxt.col != l.col or abs(nxt.size - l.size) > 0.3 \
                        or nxt.top - cap_lines[-1].bottom > self.typical_gap(l.size) + 0.3 * l.size:
                    break
                if 0.7 * nxt.size <= nxt.x0 - self.col_left(nxt) <= 6 * nxt.size and abs(nxt.x0 - l.x0) > 2:
                    break
                cap_lines.append(nxt)
                j += 1
        float_id = f"{'t' if float_kind == 'table' else 'f'}{sum(1 for b in self.blocks if b.kind == 'caption' and b.attrs.get('float') == float_kind) + 1}"
        label = f"{float_kind}:{number}"
        cap = self._text_block("caption", cap_lines, attrs={"float": float_kind, "number": number, "label": label,
                                                            "float_id": float_id, "prefix": m.group(0).strip()})
        caption_text = cap.text[m.end():].strip() if cap else ""
        self.pm.labels.append(Label(name=label, kind=float_kind, number=number, anchor=cap.anchor, block=cap.id))
        cap._labels = [label]
        if float_kind == "table" and table:
            rows = self._table_cells(table)
            notes_text = self._render_lines(table["notes"])[0] if table["notes"] else ""
            text_rows = [" | ".join(r) for r in rows]
            prefix = "" if re.match(r"\s*notes?\b", notes_text, re.I) or not notes_text else "Notes: "
            table_text = "\n".join(text_rows) + (f"\n{prefix}{notes_text}" if notes_text else "")
            all_lines = table["lines"] + table["notes"]
            block = self._new_block("table", table_text, all_lines, parent=cap.id,
                                    attrs={"number": number, "label": label, "float_id": float_id, "table_id": float_id},
                                    bbox_items=[x for x in all_lines if x.page == all_lines[0].page])
            block._owners = None
            self.pm.tables.append(Table(id=float_id, anchor=Anchor(page=block.anchor.page, page_line=block.anchor.page_line,
                                                                   bbox=list(block.anchor.bbox)),
                                        caption=caption_text, label=label, number=number, caption_block=cap.id,
                                        rows=rows, notes=notes_text))
        elif float_kind == "figure":
            info = self.figures.get(id(l), {})
            im = info.get("image")
            anchor = Anchor(page=l.page, page_line=l.no, bbox=[_rnd(v) for v in im] if im else cap.anchor.bbox)
            self.pm.figures.append(Figure(id=float_id, anchor=anchor, caption=caption_text, label=label, number=number,
                                          caption_block=cap.id))

    # -- references ----------------------------------------------------------------
    def _references(self, lines: list) -> None:
        lines = [l for l in lines if not l.used and l.tag != "rotated"]
        if not lines:
            return
        lefts = {}
        for l in lines:
            key = (l.page, l.col)
            lefts[key] = min(lefts.get(key, l.x0), l.x0)
        indents = [l.x0 - lefts[(l.page, l.col)] for l in lines]
        hanging = sum(1 for d, l in zip(indents, lines) if 0.5 * l.size <= d <= 5 * l.size) >= 0.15 * len(lines)
        number_re = re.compile(r"^\s*(?:\[(\d+)\]|(\d{1,3})\.)\s")
        numbered_list = bool(number_re.match(lines[0].text))
        entries = []
        for l, d in zip(lines, indents):
            new = not entries
            if not new:
                prev = entries[-1][-1]
                numbered = numbered_list and number_re.match(l.text) and d < 0.5 * l.size
                if numbered:
                    new = True
                elif SAME_AUTHORS.match(l.text) and re.search(r"[.)]\s*$", prev.text):
                    new = True  # "(1982) ..." or "---. 1982." for another work by the same authors
                elif hanging:
                    new = d < 0.5 * l.size
                else:
                    same_col = prev.page == l.page and prev.col == l.col
                    gap = l.top - prev.bottom if same_col else 0
                    new = (same_col and gap > self.typical_gap(l.size) + 0.3 * l.size) or (
                        re.search(r"\.\s*$", prev.text) and re.match(r"^[A-Z\u00c0-\u00de][\w'\u2019\-]+,\s", l.text) is not None)
            if new:
                entries.append([l])
            else:
                entries[-1].append(l)
        for group in entries:
            text, starts, owners = self._render_lines(group)
            if not text.strip():
                continue
            italic = []
            for k, t in enumerate(owners):
                flag = bool(t is not None and t.italic)
                if flag and italic and italic[-1][1] >= k - 1:
                    italic[-1][1] = k + 1
                elif flag:
                    italic.append([k, k + 1])
                elif t is None and italic and italic[-1][1] == k and k + 1 < len(owners) and owners[k + 1] is not None and owners[k + 1].italic:
                    italic[-1][1] = k + 1
            fields = parse_reference(text, [tuple(s) for s in italic])
            if not fields.get("authors") and SAME_AUTHORS.match(text) and self.pm.references:
                previous = self.pm.references[-1].fields
                if previous.get("authors"):
                    fields["authors"] = [dict(a) for a in previous["authors"]]
                    fields["authors_from_previous_entry"] = True
            nm = number_re.match(text) if numbered_list else None
            if nm:
                fields["label"] = nm.group(1) or nm.group(2)
            idx = len(self.pm.references) + 1
            ref = Reference(id=f"r{idx:03d}", raw=text, anchor=None, source="pdf", fields=fields)
            block = self._new_block("reference", text, group, offsets=starts, attrs={"ref": ref.id})
            block._owners = owners
            ref.anchor = Anchor(page=block.anchor.page, page_line=block.anchor.page_line, bbox=list(block.anchor.bbox))
            self.pm.references.append(ref)
        self._reference_keys()

    def _reference_keys(self) -> None:
        seen = Counter()
        for ref in self.pm.references:
            authors = ref.fields.get("authors") or []
            fam = authors[0]["family"] if authors else (ref.fields.get("title") or "anon").split()[0]
            year = ref.fields.get("year", "nd")
            base = reference_key(fam, year) + ref.fields.get("year_suffix", "")
            seen[base] += 1
            ref.key = base if seen[base] == 1 else f"{base}{'abcdefghij'[seen[base] - 1]}"
            ref.fields["key_generated"] = True
        for b in self.blocks:
            if b.kind == "reference":
                ref = next((r for r in self.pm.references if r.id == b.attrs.get("ref")), None)
                if ref:
                    b.attrs["key"] = ref.key

    # -- footnote blocks -----------------------------------------------------------
    def _place_footnotes(self) -> None:
        inserts = defaultdict(list)
        page_last = {}
        for b in self.blocks:
            page_last[b.anchor.page] = b
        for fn in self.footnotes:
            lines = fn["lines"]
            text, starts, owners = self._render_lines(lines)
            if not text.strip():
                continue
            parent = None
            kind = "footnote"
            if fn.get("anchor") is not None:
                anchor_line = fn["anchor"]
                parent = anchor_line.block
                for b in self.blocks:
                    if b.kind == "author" and fn.get("anchor_tok") in getattr(b, "_marker_positions", []):
                        parent = b
                if parent is not None and parent.kind in ("title", "author"):
                    kind = "acknowledgment"
            attrs = {"marker": fn["marker"]} if fn["marker"] else {}
            if fn["marker"] and fn["marker"].isdigit():
                attrs["number"] = fn["marker"]
            self.n_block += 1
            first = lines[0]
            on_first = [l for l in lines if l.page == first.page]
            block = Block(id=f"tmp{self.n_block}", kind=kind, text=text,
                          anchor=Anchor(page=first.page, page_line=first.no, bbox=_bbox(on_first)),
                          section=list(parent.section) if parent is not None else [],
                          parent=parent.id if parent is not None else None, attrs=attrs)
            if len(lines) > 1:
                block.attrs["lines"] = [[o, l.page, l.no] for o, l in zip(starts, lines)]
            block._owners = owners
            for l in lines:
                l.block = block
                l.used = True
            host = parent if parent is not None else page_last.get(first.page) or (self.blocks[-1] if self.blocks else None)
            if host is None:
                self.blocks.append(block)
            else:
                inserts[host.id].append(block)
        if not inserts:
            return
        out = []
        for b in self.blocks:
            out.append(b)
            out.extend(inserts.get(b.id, []))
        self.blocks = out

    def _finalize_ids(self) -> None:
        mapping = {}
        for k, b in enumerate(self.blocks, 1):
            mapping[b.id] = f"b{k:04d}"
        for b in self.blocks:
            b.id = mapping[b.id]
            if b.parent:
                b.parent = mapping.get(b.parent, b.parent)
        for t in self.pm.tables:
            t.caption_block = mapping.get(t.caption_block, t.caption_block)
        for f in self.pm.figures:
            f.caption_block = mapping.get(f.caption_block, f.caption_block)
        for lab in self.pm.labels:
            lab.block = mapping.get(lab.block, lab.block)
        self.pm.blocks = self.blocks
        title = next((b for b in self.blocks if b.kind == "title"), None)
        if title:
            self.pm.title = title.text
        elif self.pm.metadata.get("document_info", {}).get("title"):
            self.pm.title = self.pm.metadata["document_info"]["title"]
        self.pm.authors = [b.text for b in self.blocks if b.kind == "author"]

    # -- citations and cross-references -----------------------------------------
    def _spans(self) -> None:
        refs = self.pm.references
        index = defaultdict(list)
        for r in refs:
            authors = r.fields.get("authors") or []
            if authors:
                index[(_fold(authors[0]["family"]), str(r.fields.get("year", "")).lower())].append(r)
        cited, missing = set(), []
        numbered = {r.fields["label"]: r for r in refs if r.fields.get("label")}
        targets = {lab.name for lab in self.pm.labels}
        dangling = []
        for b in self.blocks:
            if b.kind in ("reference", "heading", "title", "author", "equation", "other", "jel", "keywords"):
                continue
            skip = []
            if b.kind == "caption":
                m = CAPTION.match(b.text)
                if m:
                    skip.append((0, m.end()))
            for c in find_citations(b.text):
                if any(s <= c["start"] < e for s, e in skip):
                    continue
                keys, ok = [], True
                if "numbers" in c:
                    if not numbered:
                        continue  # "[3]" means nothing without a numbered reference list
                    for n in c["numbers"]:
                        ref = numbered.get(n)
                        keys.append(ref.key if ref else f"[{n}]")
                        ok = ok and ref is not None
                        if ref:
                            cited.add(ref.id)
                    b.citations.append(Citation(keys=keys, start=c["start"], end=c["end"], command="cite",
                                                raw=b.text[c["start"]:c["end"]], resolved=ok))
                    continue
                if c["kind"] == "citet":
                    c = self._trim_narrative(c, index)
                if not c["items"]:
                    keys, ok = ["?"], False
                for names, et_al, year in c["items"]:
                    ref = self._match_reference(index, names, et_al, year)
                    if ref is None:
                        ok = False
                        key = reference_key(names[0].split()[-1], year)
                        keys.append(key)
                        if key not in missing:
                            missing.append(key)
                    else:
                        keys.append(ref.key)
                        cited.add(ref.id)
                b.citations.append(Citation(keys=keys, start=c["start"], end=c["end"], command=c["kind"],
                                            raw=b.text[c["start"]:c["end"]], resolved=ok))
            for x in find_crossrefs(b.text):
                if any(s <= x["start"] < e for s, e in skip):
                    continue
                if any(c.start <= x["start"] < c.end for c in b.citations):
                    continue
                b.crossrefs.append(CrossRef(labels=x["labels"], start=x["start"], end=x["end"], command="text",
                                            raw=x["raw"], resolved=x["resolved"]))
                for lab in x["labels"]:
                    if x["resolved"] and lab not in targets and not self._target_exists(lab, targets) and lab not in dangling:
                        dangling.append(lab)
        if missing:
            self.pm.metadata["cited_keys_missing_from_bib"] = sorted(missing)
        if refs:
            self.pm.metadata["uncited_references"] = [r.id for r in refs if r.id not in cited]
        if dangling:
            self.pm.metadata["crossref_targets_not_found"] = dangling

    def _trim_narrative(self, c: dict, index: dict) -> dict:
        """Drop words caught in front of a narrative citation's names, as in "Relatedly,
        Ershov and Lyons (2025)": keep the shortest tail of the name list that matches a
        reference, or else drop leading words that the paper also uses in lowercase."""
        items, starts = c["items"], c.get("name_starts") or []
        names = items[0][0]
        if len(names) < 2 or len(starts) != len(names):
            return c
        if all(self._match_reference(index, n, e, y) for n, e, y in items):
            return c
        for k in range(1, len(names)):
            trimmed = [(n[k:], e, y) for n, e, y in items]
            if all(self._match_reference(index, n, e, y) for n, e, y in trimmed):
                return {**c, "items": trimmed, "start": starts[k]}
        k = 0
        while k < len(names) - 1 and names[k].lower() in self.vocab:
            k += 1
        if k:
            return {**c, "items": [(n[k:], e, y) for n, e, y in items], "start": starts[k]}
        return c

    @staticmethod
    def _target_exists(label: str, targets: set) -> bool:
        kind, _, num = label.partition(":")
        if kind in ("section", "appendix"):
            return f"section:{num}" in targets or f"appendix:{num}" in targets
        return False

    @staticmethod
    def _match_reference(index: dict, names: list, et_al: bool, year: str) -> Optional[Reference]:
        fam = _fold(names[0].split()[-1] if " " in names[0] and names[0].split()[0].lower() not in PARTICLES else names[0])
        y = year.lower()
        cands = index.get((fam, y[:4] if y[:4].isdigit() else y), [])
        if not cands and " " in names[0]:
            cands = index.get((_fold(names[0]), y[:4] if y[:4].isdigit() else y), [])
        if len(cands) > 1 and len(y) == 5 and y[:4].isdigit():
            cands = [r for r in cands if r.fields.get("year_suffix") == y[4]] or cands
        if len(cands) > 1 and len(names) > 1:
            second = _fold(names[1].split()[-1])
            cands = [r for r in cands if len(r.fields.get("authors", [])) > 1
                     and _fold(r.fields["authors"][1]["family"]) == second] or cands
        return cands[0] if cands else None

    # -- hidden text ------------------------------------------------------------
    def _hidden_notes(self) -> None:
        for b in self.blocks:
            owners = getattr(b, "_owners", None)
            if not owners:
                continue
            hidden_kinds = Counter()
            visible = 0
            runs, cur = [], None
            for k, t in enumerate(owners):
                if t is None:
                    if cur is not None:
                        cur["end"] = k
                    continue
                if t.hidden:
                    hidden_kinds[t.hidden] += 1
                    if cur is None or cur["end"] < k - 1:
                        cur = {"start": k, "end": k + 1, "toks": [t]}
                        runs.append(cur)
                    else:
                        cur["end"] = k + 1
                        if t is not cur["toks"][-1]:
                            cur["toks"].append(t)
                else:
                    visible += 1
                    cur = None
            if not hidden_kinds:
                continue
            reason = hidden_kinds.most_common(1)[0][0]
            label = {"white": "white text", "tiny": "tiny text", "white tiny": "white tiny text"}[reason]
            b.attrs["hidden"] = label if not visible else f"partly {label}"
            for run in runs:
                text = b.text[run["start"]:run["end"]].strip()
                if not text:
                    continue
                toks = run["toks"]
                size = statistics.median(t.size for t in toks)
                colors = {str(tuple(round(float(v), 2) for v in t.color)) if isinstance(t.color, (tuple, list)) else str(t.color)
                          for t in toks}
                line_no = b.anchor.page_line
                for o, page, no in b.attrs.get("lines", []):
                    if o <= run["start"]:
                        line_no = no
                self.pm.notes.append(Note(kind="hidden_text", text=text,
                                          anchor=Anchor(page=b.anchor.page, page_line=line_no, bbox=_bbox(toks)),
                                          detail=f"{label}: {size:.1f} pt, colour {', '.join(sorted(colors))}; block {b.id}"))

    # -- pypdf: metadata, fonts, annotations ----------------------------------------
    def _read_pypdf(self) -> None:
        try:
            from pypdf import PdfReader as PypdfReader
        except ImportError:
            self.pm.warnings.append("pypdf is not installed: document properties and fonts were not read.")
            return
        try:
            reader = PypdfReader(str(self.path))
            if reader.is_encrypted:
                self.pm.metadata["encrypted"] = True
                try:
                    reader.decrypt("")
                except Exception:
                    self.pm.warnings.append("The PDF is encrypted; document properties could not be read.")
                    return
        except Exception as exc:
            self.pm.warnings.append(f"pypdf could not open the PDF ({type(exc).__name__}: {exc}).")
            return
        info = {}
        try:
            meta = reader.metadata or {}
            for key, name in (("/Author", "author"), ("/Creator", "creator"), ("/Producer", "producer"),
                              ("/Title", "title"), ("/Subject", "subject"), ("/Keywords", "keywords"),
                              ("/CreationDate", "creation_date"), ("/ModDate", "mod_date")):
                value = meta.get(key)
                if value is not None and str(value).strip():
                    info[name] = str(value).strip()
            for name in ("creation_date", "mod_date"):
                if name in info:
                    info[name] = _pdf_date(info[name])
        except Exception as exc:
            self.pm.warnings.append(f"Could not read the document information ({type(exc).__name__}).")
        self.pm.metadata["document_info"] = info
        try:
            xmp = reader.xmp_metadata
            if xmp is not None:
                xinfo = {"creator": list(xmp.dc_creator or []), "title": dict(xmp.dc_title or {}),
                         "creator_tool": xmp.xmp_creator_tool, "producer": xmp.pdf_producer}
                xinfo = {k: v for k, v in xinfo.items() if v}
                if xinfo:
                    self.pm.metadata["xmp"] = xinfo
        except Exception:
            pass
        try:
            self.pm.metadata["pdf_version"] = reader.pdf_header.replace("%PDF-", "")
        except Exception:
            pass
        self.pm.metadata["file_size"] = self.path.stat().st_size
        sizes = []
        fonts: dict = {}
        links = []
        for number, page in enumerate(reader.pages, 1):
            try:
                box = page.cropbox
                w, h = float(box.width), float(box.height)
                if int(page.get("/Rotate", 0) or 0) % 180 == 90:
                    w, h = h, w
                sizes.append([round(w, 1), round(h, 1)])
            except Exception:
                sizes.append(None)
            try:
                self._collect_fonts(page.get("/Resources"), number, fonts, set())
            except Exception:
                pass
            try:
                height = float(page.mediabox.height)
                for a in page.get("/Annots") or []:
                    a = a.get_object()
                    sub = str(a.get("/Subtype", ""))
                    rect = [float(v) for v in a.get("/Rect", [])] if a.get("/Rect") is not None else None
                    bbox = [_rnd(rect[0]), _rnd(height - rect[3]), _rnd(rect[2]), _rnd(height - rect[1])] if rect else None
                    if sub == "/Link":
                        action = a.get("/A")
                        action = action.get_object() if action is not None else None
                        uri = action.get("/URI") if action is not None else None
                        if uri:
                            links.append({"page": number, "uri": str(uri), "bbox": bbox})
                    elif sub in ("/Popup", "/Widget"):
                        continue
                    else:
                        self.annotations.append({"page": number, "subtype": sub.lstrip("/"), "bbox": bbox,
                                                 "contents": str(a.get("/Contents") or "").strip(),
                                                 "author": str(a.get("/T") or "").strip(),
                                                 "date": str(a.get("/M") or a.get("/CreationDate") or "").strip(),
                                                 "quads": [float(v) for v in a.get("/QuadPoints", [])] or None,
                                                 "height": height})
            except Exception:
                pass
        if sizes:
            self.pm.metadata["page_sizes"] = sizes
            common = Counter(tuple(s) for s in sizes if s).most_common(1)
            if common:
                w, h = common[0][0]
                name = next((n for n, (pw, ph) in PAGE_SIZES.items()
                             if abs(pw - min(w, h)) < 2 and abs(ph - max(w, h)) < 2), None)
                self.pm.metadata["page_size"] = {"width": w, "height": h, "name": name,
                                                 "orientation": "landscape" if w > h else "portrait"}
        if fonts:
            out = sorted(fonts.values(), key=lambda f: f["name"])
            self.pm.metadata["fonts"] = out
            not_embedded = sorted({f["name"] for f in out if not f["embedded"]})
            type3 = sorted({f["name"] for f in out if f["type3"]})
            if not_embedded:
                self.pm.metadata["fonts_not_embedded"] = not_embedded
            if type3:
                self.pm.metadata["type3_fonts"] = type3
        if links:
            self.pm.metadata["links"] = links

    def _collect_fonts(self, resources, page: int, fonts: dict, seen: set) -> None:
        if resources is None:
            return
        resources = resources.get_object()
        font_dict = resources.get("/Font")
        if font_dict is not None:
            for _, ref in font_dict.get_object().items():
                f = ref.get_object()
                base = str(f.get("/BaseFont", "") or "").lstrip("/") or "(unnamed)"
                subtype = str(f.get("/Subtype", "")).lstrip("/")
                descriptor = f.get("/FontDescriptor")
                if subtype == "Type0":
                    desc = f.get("/DescendantFonts")
                    if desc is not None:
                        d0 = desc.get_object()[0].get_object()
                        descriptor = d0.get("/FontDescriptor")
                descriptor = descriptor.get_object() if descriptor is not None else None
                embedded = subtype == "Type3" or bool(descriptor is not None and any(
                    k in descriptor for k in ("/FontFile", "/FontFile2", "/FontFile3")))
                key = base + "|" + subtype
                entry = fonts.setdefault(key, {
                    "name": re.sub(r"^[A-Z]{6}\+", "", base), "base_font": base, "subtype": subtype,
                    "embedded": embedded, "subset": bool(re.match(r"^[A-Z]{6}\+", base)),
                    "type3": subtype == "Type3", "pages": []})
                entry["embedded"] = entry["embedded"] and embedded
                if page not in entry["pages"]:
                    entry["pages"].append(page)
                if subtype == "Type3":
                    self._collect_fonts(f.get("/Resources"), page, fonts, seen)
        xobjects = resources.get("/XObject")
        if xobjects is not None:
            for _, ref in xobjects.get_object().items():
                idnum = getattr(ref, "idnum", None)
                if idnum is not None and idnum in seen:
                    continue
                if idnum is not None:
                    seen.add(idnum)
                x = ref.get_object()
                if str(x.get("/Subtype", "")) == "/Form":
                    self._collect_fonts(x.get("/Resources"), page, fonts, seen)

    def _annotation_notes(self) -> None:
        for a in self.annotations:
            page = self.pages[a["page"] - 1] if 0 < a["page"] <= len(self.pages) else None
            line_no = None
            if page is not None and a["bbox"]:
                x0, top, x1, bottom = a["bbox"]
                cy = (top + bottom) / 2
                visible = [l for l in page.lines if not l.hidden_only]
                near = [l for l in visible if l.top - 2 <= cy <= l.bottom + 2 and l.x0 - 20 <= x0 <= l.x1 + 20] or visible
                if near:
                    line_no = min(near, key=lambda l: abs(l.center - cy)).no
            text = a["contents"]
            detail = a["subtype"]
            if a["quads"] and page is not None:
                marked = self._quad_text(page, a["quads"], a["height"])
                if marked:
                    detail += f": {marked}"
            author, date = a["author"] or None, a["date"] or None
            m = re.match(r"^(.*?),\s*(\d{1,2}/\d{1,2}/\d{2,4}),?\s*$", a["author"] or "")
            if m:
                author, date = m.group(1).strip(), date if date and not set(date) <= set("D:0Z'") else m.group(2)
            if date and set(date) <= set("D:0Z'"):
                date = None
            self.pm.notes.append(Note(kind="pdf_comment", text=text or detail,
                                      anchor=Anchor(page=a["page"], page_line=line_no, bbox=a["bbox"]),
                                      author=author, date=date, detail=f"{detail} annotation"))

    @staticmethod
    def _quad_text(page: PageInfo, quads: list, height: float) -> str:
        boxes = []
        for k in range(0, len(quads) - 7, 8):
            xs = quads[k:k + 8:2]
            ys = quads[k + 1:k + 8:2]
            boxes.append((min(xs), height - max(ys), max(xs), height - min(ys)))
        words = []
        for l in page.lines:
            for t in l.toks:
                cx, cy = (t.x0 + t.x1) / 2, (t.top + t.bottom) / 2
                if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes):
                    words.append(t.text)
        return " ".join(words)

    def _finish_metadata(self) -> None:
        self.pm.source["pages"] = len(self.pages)
        fonts = self.pm.metadata.get("fonts")
        if fonts and self.pages:
            used = set().union(*(p.fonts for p in self.pages))
            for f in fonts:
                f["used"] = f["base_font"] in used or f["name"] in used or f["type3"] and bool(used)
            not_embedded = sorted({f["name"] for f in fonts if f["used"] and not f["embedded"]})
            type3 = sorted({f["name"] for f in fonts if f["used"] and f["type3"]})
            for key, value in (("fonts_not_embedded", not_embedded), ("type3_fonts", type3)):
                if value:
                    self.pm.metadata[key] = value
                else:
                    self.pm.metadata.pop(key, None)
        if not self.pm.title and self.pm.metadata.get("document_info", {}).get("title"):
            self.pm.title = self.pm.metadata["document_info"]["title"]
        for page, im in getattr(self, "_uncaptioned", []):
            fid = f"f{len(self.pm.figures) + 1}"
            self.pm.figures.append(Figure(id=fid, anchor=Anchor(page=page, bbox=[_rnd(v) for v in im])))


def read_pdf(path: Path) -> PaperMap:
    return PdfReader(Path(path)).read()
