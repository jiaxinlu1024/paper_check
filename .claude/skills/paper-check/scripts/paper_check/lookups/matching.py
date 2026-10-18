"""String similarity for references: titles, author names, venues, years and pages.

Pure functions that return scores; the thresholds that turn scores into decisions live
in policy.THRESHOLDS. rapidfuzz (MIT) does the edit-distance work.

Text is folded before comparison: HTML entities and LaTeX commands removed, symbols such
as "TM" dropped, letters that Unicode does not decompose transliterated (ß→ss, ø→o, ł→l),
accents stripped, case folded, punctuation turned into spaces. Author names are compared
on their family names with spaces removed as well, so "DellaVigna" matches Crossref's
"Della Vigna", "O'Donoghue" matches "O’Donoghue", and "Kőszegi" matches "Koszegi".
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Iterable, Optional

from rapidfuzz import fuzz

_TRANSLIT = str.maketrans({
    "ß": "ss", "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    "đ": "d", "Đ": "D", "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th", "ı": "i", "ħ": "h", "Ħ": "H",
})
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\*?|\\[^a-zA-Z\s]")
_SPLIT_SUBTITLE = re.compile(r"\s*(?::|\?|!|\s[-–—]\s|\.\s)\s*")
# Databases prefix retracted works' titles, as Crossref does with "RETRACTED: Signing at the beginning ...".
_MARKER = re.compile(r"^\s*(?:retracted|withdrawn)(?:\s+(?:article|paper))?\s*[:.\-–—]\s*", re.I)


def strip_marker(title: Optional[str]) -> str:
    return _MARKER.sub("", str(title or ""))
STOPWORDS = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "at", "de", "la", "le", "der", "die", "das"}
NOT_AUTHORS = {"others", "etal", "al", "andothers", "et"}
# Economics journal abbreviations that neither initials nor prefixes recover.
JOURNAL_ALIASES = {
    "restud": "review of economic studies", "res": "review of economic studies",
    "restat": "review of economics and statistics", "rest": "review of economics and statistics",
    "ecta": "econometrica", "jeea": "journal of the european economic association",
    "jebo": "journal of economic behavior and organization", "jpube": "journal of public economics",
    "jpubec": "journal of public economics", "jhr": "journal of human resources", "mnsc": "management science",
    "ms": "management science", "geb": "games and economic behavior", "jru": "journal of risk and uncertainty",
    "jbee": "journal of behavioral and experimental economics", "joep": "journal of economic psychology",
    "jesa": "journal of the economic science association", "expecon": "experimental economics",
    "bpp": "behavioural public policy", "aeri": "american economic review insights",
    "aejapplied": "american economic journal applied economics", "aejpolicy": "american economic journal economic policy",
    "aejmicro": "american economic journal microeconomics", "aejmacro": "american economic journal macroeconomics",
    "pnas": "proceedings of the national academy of sciences", "jfe": "journal of financial economics",
    "jf": "journal of finance", "rfs": "review of financial studies", "jole": "journal of labor economics",
    "jde": "journal of development economics", "jhe": "journal of health economics",
}


def fold(text: Optional[str]) -> str:
    """Lowercase ASCII words separated by single spaces."""
    if not text:
        return ""
    text = html.unescape(str(text)).replace("&", " and ")
    text = _LATEX_CMD.sub(" ", text).replace("{", "").replace("}", "")
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("So", "Sk", "Sm", "Cf"))
    text = text.translate(_TRANSLIT)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def squeeze(text: Optional[str]) -> str:
    return fold(text).replace(" ", "")


_FUNCTION_WORDS = STOPWORDS | {"or", "from", "with", "by", "as", "is", "are", "its", "their", "into", "over", "under",
                               "between", "about", "after", "before", "than", "vs", "versus", "how", "what", "why",
                               "when", "does", "do", "new", "this", "that", "these", "those", "we", "our"}


def content_words(text: Optional[str]) -> set:
    """The folded content words of a title, plurals reduced to their singular."""
    out = set()
    for w in fold(text).split():
        if len(w) <= 2 or w in _FUNCTION_WORDS:
            continue
        out.add(w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 4 else w)
    return out


def title_word_overlap(a: Optional[str], b: Optional[str]) -> float:
    """Share of the shorter title's content words that the other title has (0 to 1). Edit-distance
    ratios give unrelated titles of similar length about 0.5; shared words do not."""
    wa, wb = content_words(a), content_words(b)
    if not wa or not wb:
        return 0.0
    return round(len(wa & wb) / min(len(wa), len(wb)), 3)


def main_title(text: Optional[str]) -> str:
    """The folded part of a title before its subtitle, or '' when it has none."""
    if not text:
        return ""
    parts = _SPLIT_SUBTITLE.split(strip_marker(text).strip(), maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return fold(parts[0])
    return ""


def word_count(text: Optional[str]) -> int:
    return len(fold(text).split())


def is_short_title(text: Optional[str]) -> bool:
    """Short titles match too many works by accident (after Hallucinator's rule)."""
    folded = fold(text)
    return len(folded.split()) < 4 or len(folded) < 25


def title_similarity(a: Optional[str], b: Optional[str]) -> float:
    """0 to 1. Edit-distance ratio on folded titles, order-insensitive ratio, and a dropped
    subtitle counted as 0.9 when one title equals the other's main title. A leading
    "RETRACTED:" or "WITHDRAWN:" marker is ignored."""
    a, b = strip_marker(a), strip_marker(b)
    fa, fb = fold(a), fold(b)
    if not fa or not fb:
        return 0.0
    if fa == fb:
        return 1.0
    score = max(fuzz.ratio(fa, fb), fuzz.token_sort_ratio(fa, fb)) / 100.0
    ma, mb = main_title(a), main_title(b)
    if (ma and not mb and ma == fb) or (mb and not ma and mb == fa):
        shorter = fb if ma else fa
        if len(shorter) >= 12 and len(shorter.split()) >= 2:
            score = max(score, 0.9)
    return round(score, 3)


# ---------------------------------------------------------------- authors
def family_key(person) -> str:
    """Squeezed family name of a cited author ({family, given} or a plain name)."""
    if isinstance(person, dict):
        fam = person.get("family")
        if fam:
            return squeeze(fam)
        name = str(person.get("name") or "")
    else:
        name = str(person or "")
    if "," in name:
        return squeeze(name.split(",")[0])
    words = fold(name).split()
    return words[-1] if words else ""


def is_not_author(person) -> bool:
    return family_key(person) in NOT_AUTHORS


def _record_keys(person: dict) -> tuple:
    """(exact keys, full-name keys, family key, last word) for one record author."""
    fam = squeeze(person.get("family")) if person.get("family") else ""
    given = squeeze(person.get("given")) if person.get("given") else ""
    names = [squeeze(person.get(k)) for k in ("name", "raw") if person.get(k)]
    if fam:
        names.append(given + fam)
    exact = {k for k in [fam] + names if k}
    # Swapped fields, such as family "D." and given "Laibson".
    if fam and len(fam) <= 2 and given:
        exact.add(given)
    last = ""
    for k in ("name", "raw"):
        if person.get(k):
            raw = str(person[k])
            if "," in raw:
                last = squeeze(raw.split(",")[0])
            else:
                words = fold(raw).split()
                last = words[-1] if words else ""
            break
    return exact, [n for n in names if n], fam, last


def author_matches(fam: str, person: dict) -> bool:
    if not fam or not isinstance(person, dict):
        return False
    exact, names, rec_fam, last = _record_keys(person)
    if fam in exact:
        return True
    if len(fam) >= 3 and any(n.endswith(fam) for n in names):
        return True  # "stefanodellavigna" ends with "dellavigna"
    if rec_fam and len(rec_fam) >= 4 and fam.endswith(rec_fam):
        return True  # cited "vandenberg", record family "berg"
    for other in (rec_fam, last):
        if other and len(other) >= 4 and len(fam) >= 4 and fuzz.ratio(fam, other) >= 85:
            return True  # "mueller" and "muller"
    return False


def compare_authors(cited: Iterable, found: Iterable) -> dict:
    """Overlap of cited family names with a record's authors.

    fraction: share of cited names found in the record; jaccard: matched over the larger
    list, for comparing author sets; first_author: the first cited author is the record's
    first author; same_order: matched names appear in the same order."""
    cited = [c for c in (cited or [])]
    truncated = any(is_not_author(c) for c in cited)
    cited = [c for c in cited if not is_not_author(c)]
    found = [f for f in (found or []) if isinstance(f, dict)]
    # Some records list every author twice (a DataCite record merged from two sources): keep the first.
    seen, unique = set(), []
    for person in found:
        ident = (str(person.get("family") or person.get("name") or "").strip().lower(),
                 str(person.get("given") or "").strip().lower()[:1])
        if ident in seen and ident != ("", ""):
            continue
        seen.add(ident)
        unique.append(person)
    found = unique
    fams = [family_key(c) for c in cited]
    used, pairs = set(), []
    for i, fam in enumerate(fams):
        for j, person in enumerate(found):
            if j not in used and author_matches(fam, person):
                used.add(j)
                pairs.append((i, j))
                break
    n_cited, n_found = len(fams), len(found)
    matched_i = {i for i, _ in pairs}
    fraction = len(pairs) / n_cited if n_cited else None
    denom = max(n_cited, n_found)
    js = [j for _, j in pairs]
    return {
        "fraction": round(fraction, 3) if fraction is not None else None,
        "jaccard": round(len(pairs) / denom, 3) if denom and n_cited and n_found else None,
        "matched": len(pairs), "cited_count": n_cited, "record_count": n_found,
        "cited_not_in_record": [_name(cited[i]) for i in range(n_cited) if i not in matched_i],
        "record_not_cited": [_name(found[j]) for j in range(n_found) if j not in used],
        "first_author": bool(pairs) and pairs[0] == (0, 0),
        "same_order": js == sorted(js),
        "truncated": truncated,
    }


def _name(person) -> str:
    if isinstance(person, dict):
        if person.get("family"):
            return f"{person['family']}, {person['given']}" if person.get("given") else str(person["family"])
        return str(person.get("name") or "")
    return str(person)


# ---------------------------------------------------------------- years, venues, pages
def parse_year(value) -> Optional[int]:
    if isinstance(value, int):
        return value
    m = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", str(value or ""))
    return int(m.group(1)) if m else None


def year_difference(cited, years: Iterable) -> Optional[int]:
    """Signed difference from the cited year to the closest record year (record minus cited)."""
    cy = parse_year(cited)
    ys = [y for y in years if isinstance(y, int)]
    if cy is None or not ys:
        return None
    best = min(ys, key=lambda y: (abs(y - cy), y))
    return best - cy


def _venue(text: Optional[str]) -> str:
    v = fold(text)
    return v[4:] if v.startswith("the ") else v


def _significant(words: list) -> list:
    return [w for w in words if w not in STOPWORDS]


def abbreviation_of(short: str, long: str) -> bool:
    """`short` abbreviates `long`: initials ("qje"), token prefixes ("j polit econ"),
    or a known alias ("restud")."""
    s_words, l_words = short.split(), _significant(long.split())
    if not s_words or not l_words:
        return False
    joined = "".join(s_words)
    if JOURNAL_ALIASES.get(joined) and _significant(JOURNAL_ALIASES[joined].split()) == l_words:
        return True
    if len(s_words) == 1 and len(joined) >= 2 and joined == "".join(w[0] for w in l_words):
        return True
    s_sig = _significant(s_words)
    return len(s_sig) == len(l_words) and all(l.startswith(s) for s, l in zip(s_sig, l_words))


def container_similarity(cited: Optional[str], names: Iterable) -> Optional[float]:
    """0 to 1, or None when either side has no venue."""
    c = _venue(cited)
    names = [_venue(n) for n in names if n]
    if not c or not names:
        return None
    best = 0.0
    for n in names:
        if c == n or abbreviation_of(c, n) or abbreviation_of(n, c):
            return 1.0
        best = max(best, fuzz.token_set_ratio(c, n) / 100.0, fuzz.ratio(c, n) / 100.0)
    return round(best, 3)


def looks_abbreviated(venue: Optional[str]) -> bool:
    v = (venue or "").strip()
    return bool(v) and (len(v) <= 8 or "." in v or v.isupper())


def _page_parts(pages: Optional[str]) -> tuple:
    if not pages:
        return "", ""
    text = re.sub(r"[‐‑‒–—―−]+|--+", "-", str(pages))
    bits = [re.sub(r"[^0-9A-Za-z]", "", b) for b in text.split("-")]
    bits = [b for b in bits if b]
    if not bits:
        return "", ""
    first, last = bits[0].lower(), (bits[1].lower() if len(bits) > 1 else "")
    if last and first.isdigit() and last.isdigit() and len(last) < len(first):
        last = first[: len(first) - len(last)] + last  # 1149-87 means 1149-1187
    return first, last


def compare_pages(cited: Optional[str], found: Optional[str]) -> Optional[bool]:
    """True when the pages agree, False when they differ, None when not comparable.
    A record that gives only a first page, or a range that ends where it starts, is
    compared on the first page only."""
    cf, cl = _page_parts(cited)
    ff, fl = _page_parts(found)
    if not cf or not ff:
        return None
    if cf != ff:
        return False
    if cl and fl and fl != ff:
        return cl == fl
    return True


def compare_simple(cited, found, numeric_only: bool = False) -> Optional[bool]:
    """Volumes and issues: equal after folding. "112(2)" counts as volume 112."""
    def lead(v):
        v = re.sub(r"\(.*?\)", " ", str(v)) if v is not None else ""
        return squeeze(v)
    a, b = lead(cited), lead(found)
    if not a or not b:
        return None
    if a == b:
        return True
    if numeric_only and not (a.isdigit() and b.isdigit()):
        return None
    return False
