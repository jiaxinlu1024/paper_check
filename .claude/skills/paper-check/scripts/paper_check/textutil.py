"""Text helpers shared by ingestion, checks and verification.

The quote matcher is the basis of the skill's main guardrail: a finding may only
quote text that this module can find in the paper map or in a cached source.
Matching ignores case, whitespace, and the usual typographic variants of quote
marks, dashes, ligatures and soft hyphens. A quote may use "..." to skip text.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterator, Optional

_CHAR_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "`": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "''": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", "​": "", "­": "", "﻿": "",
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "…": "...",
}
_ELLIPSIS = re.compile(r"\.\.\.|…|\[\.\.\.\]|\[…\]")


def normalize(text: str) -> str:
    """Readable normalization: typographic variants unified, whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text)
    for k, v in _CHAR_MAP.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text).strip()


def _squeeze_with_map(text: str) -> tuple[str, list]:
    """Lowercased, whitespace-free text plus, for each output char, its index in `text`.

    A hyphen between two letters is dropped too, so "self-control", "self- control"
    and a PDF's "behav-ioral" all match their unhyphenated forms. Minus signs before
    digits are kept, because they change meaning."""
    chars = []
    for i, ch in enumerate(text):
        piece = unicodedata.normalize("NFKC", ch)
        piece = _CHAR_MAP.get(piece, piece)
        for c in piece.lower():
            if not c.isspace():
                chars.append((c, i))
    out, index = [], []
    for k, (c, i) in enumerate(chars):
        if c == "-" and 0 < k < len(chars) - 1 and chars[k - 1][0].isalpha() and chars[k + 1][0].isalpha():
            continue
        out.append(c)
        index.append(i)
    return "".join(out), index


def find_quote(quote: str, text: str) -> Optional[tuple[int, int]]:
    """Return (start, end) offsets of `quote` in `text`, or None.

    Whitespace, case and typographic variants are ignored. Parts separated by
    "..." must appear in order; the span runs from the first part to the last."""
    parts = [p for p in _ELLIPSIS.split(quote) if p.strip()]
    if not parts:
        return None
    hay, index = _squeeze_with_map(text)
    pos, start, end = 0, None, None
    for part in parts:
        needle, _ = _squeeze_with_map(part)
        if not needle:
            continue
        found = hay.find(needle, pos)
        if found < 0:
            return None
        if start is None:
            start = index[found]
        last = found + len(needle) - 1
        end = index[last] + 1
        pos = found + len(needle)
    return (start, end) if start is not None else None


# ---------------------------------------------------------------- sentences
_ABBREVIATIONS = {
    "e.g", "i.e", "et al", "al", "etc", "cf", "fig", "figs", "eq", "eqs", "sec", "secs", "no", "nos",
    "vs", "approx", "dr", "mr", "mrs", "ms", "prof", "jr", "sr", "inc", "ltd", "co", "corp", "u.s",
    "u.k", "e.u", "st", "vol", "pp", "p", "ch", "ed", "eds", "resp", "viz", "ca", "jan", "feb", "mar",
    "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "tab", "app", "est", "std", "dept",
}
_BOUNDARY = re.compile(r"([.!?])(['\")\]]*)(\s+)(?=[\"'(\[]?[A-Z0-9])")


_LABEL_WORDS = {"appendix", "table", "figure", "section", "panel", "column", "model", "treatment", "group",
                "study", "experiment", "part", "wave", "phase", "option", "condition", "arm", "type", "category",
                "class", "grade", "plan", "sample", "stage", "round", "game", "lottery", "item", "question",
                "scenario", "version", "variant", "list", "box", "exhibit", "chapter", "step", "case"}


def _is_initial(before: str) -> bool:
    """A lone capital before ". " is an initial when it follows a name or another initial, as in
    "Richard H. Thaler" or "J. Smith", not a label or a lowercase word, as in "Appendix A." or "chose C."."""
    m = re.search(r"(?:^|[\s(\[])(?P<prev>[^\s]*)\s+[A-Z]$", before)
    if not m:
        return bool(re.fullmatch(r"\s*[A-Z]", before))  # an initial at the very start
    prev = m.group("prev").strip("(),;[")
    if not prev:
        return True
    if re.fullmatch(r"[A-Z]\.", prev) or prev.lower() in ("and", "&", "von", "van", "de", "der", "di", "da", "le"):
        return True
    return prev[:1].isupper() and prev.lower().rstrip(".,") not in _LABEL_WORDS


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Split text into sentence spans, avoiding common abbreviations and initials."""
    spans, start = [], 0
    for m in _BOUNDARY.finditer(text):
        before = text[start:m.start(1)]
        token = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
        if m.group(1) == ".":
            if token:
                word = token.group(1).lower().rstrip(".")
                if word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha() and _is_initial(before)):
                    continue
            if re.search(r"\d$", before) and re.match(r"\s*\d", text[m.end(3):]):
                continue  # decimal number split across a space is not a boundary
        end = m.end(2)
        if text[start:end].strip():
            spans.append((start, end))
        start = m.end(3)
    if text[start:].strip():
        spans.append((start, len(text.rstrip())))
    return spans


# ---------------------------------------------------------------- numbers
_NUMBER = re.compile(
    r"(?<![\w.])(?P<sign>[-−+])?(?P<cur>[$€£])?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
    r"(?P<unit>\s?%|\s?percentage points?|\s?pp\b|\s?percent\b|\s?per cent\b|\s?bps?\b|"
    r"\s?(?:million|billion|thousand)\b)?"
)


def extract_numbers(text: str, skip_spans: Optional[list] = None) -> Iterator[dict]:
    """Yield numbers with value, unit, decimals and offsets, skipping given spans."""
    skip_spans = skip_spans or []
    for m in _NUMBER.finditer(text):
        if any(s <= m.start() < e for s, e in skip_spans):
            continue
        raw_num = m.group("num").replace(",", "")
        try:
            value = float(raw_num)
        except ValueError:
            continue
        if m.group("sign") in ("-", "−"):
            value = -value
        unit = (m.group("unit") or "").strip().lower() or None
        if unit in ("percent", "per cent"):
            unit = "%"
        elif unit and unit.startswith("percentage point"):
            unit = "pp"
        if m.group("cur"):
            unit = m.group("cur") + (f" {unit}" if unit else "")
        decimals = len(raw_num.split(".")[1]) if "." in raw_num else 0
        yield {"start": m.start(), "end": m.end(), "raw": m.group(0), "value": value,
               "unit": unit, "decimals": decimals}


# ---------------------------------------------------------------- misc
def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9À-ɏ]+(?:['’-][A-Za-z0-9]+)*", text))


def dehyphenate(lines: list[str]) -> str:
    """Join PDF lines, removing end-of-line hyphenation like "behav-" + "ioral"."""
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out.endswith("-") and len(out) > 1 and out[-2].isalpha() and line[:1].isalpha():
            # Lowercase continuation: a word broken across lines. Otherwise a real hyphen.
            out = (out[:-1] if line[:1].islower() else out) + line
        elif out:
            out += " " + line
        else:
            out = line
    return out


# The month, day or season after the year in an APA entry, "(2020, December 2)": part of the date.
APA_DATE = re.compile(r"\s*,\s*(?P<date>(?:January|February|March|April|May|June|July|August|September|October|"
                      r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec|Spring|Summer|Fall|Autumn|"
                      r"Winter)\.?(?:\s+\d{1,2}(?:\s*[–-]\s*\d{1,2})?)?)\s*\)")
