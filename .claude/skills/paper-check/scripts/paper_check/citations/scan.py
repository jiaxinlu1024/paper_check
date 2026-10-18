"""Exhaustive term scan of a cited work, plus BM25-ranked passages: the absence record.

`scan(text, terms)` looks for every term in the cached text of a cited work and reports, per term,
the hit count, the pages and the surface forms found. It then ranks the passages around the hits
with BM25 so a judge reads the most relevant ones first. When no term occurs at all, it ranks the
whole text instead and returns the closest passages, which an absence verdict must show.

Matching, for each term independently:
  - case-insensitive; quote marks, dashes and ligatures are unified first
  - the words of a term may be separated by spaces, hyphens, line breaks or nothing, so
    "self control" matches "self-control", "self- control" and "selfcontrol"
  - a word hyphenated across a line break ("procras-" / "tination") still matches
  - whole words only, with an optional plural: "gym" matches "gyms" but not "gymnasium";
    "study" matches "studies"
  - "*" ends a word with any letters: "procrastinat*" matches "procrastination" and "procrastinate"
  - a term with no whole-word hit is also counted as the start of longer words, reported under
    "inside_longer_words" with a warning, so a stem written without its "*" is never recorded as absent
  - a term starting with "re:" is a regular expression on the folded (lowercased) text,
    for example "re:β\\s*[<=]\\s*0?\\.\\d+"
  - text inside the page markers themselves is never matched

Pages come from the [[page N]] markers that fulltext.py writes (PDF page index, from 1). Text after
[[abstract]] is labelled "abstract", and after [[text]] "text" (a source without page numbers).

BM25 (Robertson and Zaragoza's formula, k1 = 1.2, b = 0.75) is computed over chunks of about 100
words, which give the document frequencies. A passage scores the BM25 of the terms as phrases plus
0.3 times the BM25 of their individual words, so a passage with the exact phrase ranks above one
that only shares a word. Written from the published formula; no code was copied.

Hits inside the work's own reference list (found from its "References" heading) are counted
separately per term, and their passages rank after every passage of the text itself: a cited
title such as "Self-Control and Saving" shows what the work cites, not what it discusses.
"""

from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Optional

K1, B, WORD_WEIGHT = 1.2, 0.75, 0.3
CHUNK_WORDS = 100
MARKER = re.compile(r"^\[\[(?:page (\d+)|abstract|text)\]\][ \t]*$", re.M)
_FOLD = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "`": "'", "“": '"', "”": '"', "„": '"', "‟": '"',
         "″": '"', "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-", " ": " ",
         " ": " ", " ": " ", " ": " ", "­": "", "​": "", "﻿": ""}
_STOP = set("""a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has have having he
her here hers him his how i if in into is it its itself just me more most my no nor not now of off on once only or
other our ours out over own same she should so some such than that the their theirs them then there these they this
those through to too under until up very was we were what when where which while who whom why will with would you
your yours et al""".split())
_FOLD_CACHE: dict = {}


# ================================================================ folding
def _fold_char(ch: str) -> str:
    piece = _FOLD_CACHE.get(ch)
    if piece is None:
        piece = _FOLD.get(ch)
        if piece is None:
            piece = unicodedata.normalize("NFKC", ch)
            piece = "".join(_FOLD.get(c, c) for c in piece)
        piece = piece.lower()
        _FOLD_CACHE[ch] = piece
    return piece


def fold(text: str) -> tuple:
    """Lowercased text with typographic variants unified and line-break hyphenation removed.

    Returns (folded, index) where index[k] is the position in `text` of folded character k.
    Marker lines are blanked so that no term can match inside them."""
    chars, index = [], []
    blank = set()
    for m in MARKER.finditer(text):
        blank.update(range(m.start(), m.end()))
    for i, ch in enumerate(text):
        if i in blank:
            chars.append(" ")
            index.append(i)
            continue
        for c in _fold_char(ch):
            chars.append(c)
            index.append(i)
    # drop "-" + line break between two letters: "procras-\ntination" -> "procrastination"
    out, out_index, k, n = [], [], 0, len(chars)
    while k < n:
        c = chars[k]
        if c == "-" and out and out[-1].isalpha():
            j = k + 1
            while j < n and chars[j] in " \t":
                j += 1
            if j < n and chars[j] == "\n":
                j += 1
                while j < n and chars[j] in " \t":
                    j += 1
                if j < n and chars[j].isalpha():
                    k = j
                    continue
        out.append(c)
        out_index.append(index[k])
        k += 1
    return "".join(out), out_index


# ================================================================ terms
_ASCII_ALNUM = re.compile(r"[a-z0-9]")


def compile_term(term: str) -> re.Pattern:
    """Regular expression for one term on folded text. See the module docstring for the rules."""
    term = term.strip()
    if term.lower().startswith("re:"):
        return re.compile(term[3:], re.I | re.M)
    folded = "".join(_fold_char(c) for c in term)
    tokens = [t for t in re.split(r"[\s\-]+", folded) if t]
    if not tokens:
        raise ValueError(f"empty term: {term!r}")
    parts = []
    for i, token in enumerate(tokens):
        wildcard = token.endswith("*") and len(token) > 1
        core = token.rstrip("*") if wildcard else token
        piece = re.escape(core)
        if wildcard:
            piece += r"[^\W_]*"
        elif i == len(tokens) - 1 and core[-1:].isalpha() and core[-1:].isascii():
            if core.endswith("y") and len(core) > 2:
                piece = re.escape(core[:-1]) + r"(?:y|ies)"
            else:
                piece += r"(?:e?s)?"
        parts.append(piece)
    body = r"[\s\-]*".join(parts)
    head = r"(?<![a-z0-9])" if _ASCII_ALNUM.match(tokens[0][:1]) else ""
    last = tokens[-1].rstrip("*")
    tail = r"(?![a-z0-9])" if _ASCII_ALNUM.match(last[-1:]) and not tokens[-1].endswith("*") else ""
    return re.compile(head + body + tail)


def _longer_words(term: str, folded: str, index: list, text: str, pages: list) -> Optional[dict]:
    """For a term with no whole-word hit: the words that start with it, so that a stem written
    without its "*" ("procrastinat") is not reported as absent. None if there are none."""
    t = term.strip()
    if t.lower().startswith("re:") or t.endswith("*"):
        return None
    folded_term = "".join(_fold_char(c) for c in t)
    tokens = [x for x in re.split(r"[\s\-]+", folded_term) if x]
    if not tokens or not tokens[-1][-1:].isalpha():
        return None
    try:
        regex = compile_term(t + "*")
    except (re.error, ValueError):
        return None
    forms, hit_pages, hits = Counter(), [], 0
    for m in regex.finditer(folded):
        if m.end() <= m.start():
            continue
        start, end = index[m.start()], index[m.end() - 1] + 1
        hits += 1
        forms[_clean(text[start:end]).replace("- ", "-")] += 1
        label = page_at(pages, start)
        if label not in hit_pages:
            hit_pages.append(label)
    if not hits:
        return None
    return {"hits": hits, "pages": hit_pages, "forms": dict(forms.most_common())}


# ================================================================ pages
def page_index(text: str) -> list:
    """[(offset where the page's text starts, label)] in order. Label: int, "abstract" or "text"."""
    out = []
    for m in MARKER.finditer(text):
        label = int(m.group(1)) if m.group(1) else m.group(0).strip().strip("[]")
        out.append((m.end(), label))
    return out


def page_at(index: list, pos: int):
    """Label of the page containing text offset `pos`, or None before any marker."""
    starts = [s for s, _ in index]
    k = bisect.bisect_right(starts, pos) - 1
    return index[k][1] if k >= 0 else None


def page_spans(text: str) -> list:
    """[(start, end, label)] of every page's text, without the marker lines."""
    index = page_index(text)
    if not index:
        return [(0, len(text), None)]
    spans = []
    marker_starts = [m.start() for m in MARKER.finditer(text)]
    for k, (start, label) in enumerate(index):
        end = marker_starts[k + 1] if k + 1 < len(marker_starts) else len(text)
        spans.append((start, end, label))
    return spans


def strip_markers(text: str) -> str:
    """The text without page markers, for matching quotes that run across a page break."""
    return MARKER.sub(" ", text)


_REF_HEADING = re.compile(r"^[ \t]*(?:\d+\.?\s+)?(?:references|bibliography|works cited|literature cited|"
                          r"literatur|literaturverzeichnis)[ \t]*$", re.I | re.M)
_AFTER_REFS = re.compile(r"^[ \t]*(?:appendix\b|online appendix|tables?[ \t]+[A-Z]?\d|figures?[ \t]+[A-Z]?\d)", re.I | re.M)


def reference_region(text: str) -> Optional[tuple]:
    """(start, end) of the work's own reference list, so that a hit in a cited title is not
    mistaken for the work discussing the topic. The last such heading in the latter part of the
    text opens it; an appendix, table or figure heading after it closes it."""
    heads = [m for m in _REF_HEADING.finditer(text) if m.start() > 0.3 * len(text)]
    if not heads:
        return None
    start = heads[-1].start()
    after = _AFTER_REFS.search(text, heads[-1].end())
    return start, (after.start() if after else len(text))


# ================================================================ BM25
def stem(word: str) -> str:
    """Light suffix stripping, enough to pair 'procrastination' with 'procrastinate'."""
    w = word
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 4 and w.endswith("es") and w[:-2].endswith(("s", "x", "z", "ch", "sh")):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "as")):
        w = w[:-1]
    for suffix in ("ational", "ations", "ation", "ating", "ated", "ates", "ate", "ingly", "ing", "edly", "ed",
                   "ities", "ity", "ments", "ment", "ness", "ions", "ion", "ly"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)]
    return w


def words(folded: str) -> list:
    return [stem(w) for w in re.findall(r"[^\W_]+", folded) if w not in _STOP and (len(w) > 1 or not w.isascii())]


def _bm25(tf: float, df: int, dl: int, n_docs: int, avgdl: float) -> float:
    if tf <= 0:
        return 0.0
    idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
    return idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / max(avgdl, 1.0)))


def _chunks(text: str, spans: list) -> list:
    """About 100-word pieces of each page, as (start, end, label)."""
    out = []
    for start, end, label in spans:
        pos, count, chunk_start = start, 0, start
        for line in text[start:end].splitlines(keepends=True):
            pos += len(line)
            count += len(line.split())
            if count >= CHUNK_WORDS:
                out.append((chunk_start, pos, label))
                chunk_start, count = pos, 0
        if text[chunk_start:end].strip():
            out.append((chunk_start, end, label))
    return out


def _snap(text: str, start: int, end: int, lo: int, hi: int) -> tuple:
    """Widen a window to whole words, inside [lo, hi)."""
    while start > lo and not text[start - 1].isspace():
        start -= 1
    while end < hi and not text[end].isspace():
        end += 1
    return start, end


def _clean(snippet: str) -> str:
    return " ".join(snippet.split())


# ================================================================ scan
def scan(text: str, terms: list, context: int = 300, top: int = 8) -> dict:
    """Count every term in `text`, with pages, and rank the passages around the hits by BM25."""
    folded, index = fold(text)
    to_folded = lambda pos: bisect.bisect_left(index, pos)  # noqa: E731
    pages = page_index(text)
    spans = page_spans(text)
    chunks = _chunks(text, spans)
    chunk_starts = [c[0] for c in chunks]
    chunk_words = [Counter(words(folded[to_folded(s):to_folded(e)])) for s, e, _ in chunks]
    n_docs = max(len(chunks), 1)
    avgdl = sum(sum(c.values()) for c in chunk_words) / n_docs if chunks else 1.0
    refs = reference_region(text)
    in_refs = lambda pos: refs is not None and refs[0] <= pos < refs[1]  # noqa: E731

    def mostly_refs(start: int, end: int) -> bool:
        return refs is not None and min(end, refs[1]) - max(start, refs[0]) > 0.5 * max(end - start, 1)

    results, all_hits = [], []
    for term in terms:
        entry = {"term": term, "hits": 0, "hits_in_reference_list": 0, "pages": [], "forms": {}, "examples": []}
        try:
            regex = compile_term(term)
        except (re.error, ValueError) as exc:
            entry["error"] = f"invalid term: {exc}"
            results.append(entry)
            continue
        forms, hit_pages = Counter(), []
        for m in regex.finditer(folded):
            if m.end() <= m.start():
                continue
            start, end = index[m.start()], index[m.end() - 1] + 1
            label = page_at(pages, start)
            all_hits.append((start, end, term, label))
            entry["hits"] += 1
            entry["hits_in_reference_list"] += in_refs(start)
            forms[_clean(text[start:end]).replace("- ", "-")] += 1
            if label not in hit_pages:
                hit_pages.append(label)
            if len(entry["examples"]) < 5:
                p_lo, p_hi = next(((s, e) for s, e, _ in spans if s <= start < e), (0, len(text)))
                lo, hi = _snap(text, max(p_lo, start - 80), min(p_hi, end + 80), p_lo, p_hi)
                example = {"page": label, "text": _clean(text[lo:hi])}
                if in_refs(start):
                    example["in_reference_list"] = True
                entry["examples"].append(example)
        entry["pages"] = hit_pages
        entry["forms"] = dict(forms.most_common())
        if not entry["hits"]:
            longer = _longer_words(term, folded, index, text, pages)
            if longer:
                entry["inside_longer_words"] = longer
                shown = ", ".join(f"{w} ({n})" for w, n in list(longer["forms"].items())[:4])
                entry["warning"] = (f"No whole-word match, but {longer['hits']} words start with it: {shown}. "
                                    f"Scan \"{term.strip()}*\" to count those, and don't call the term absent "
                                    "without reading them.")
        results.append(entry)

    # document frequency of each term, over chunks
    term_df = Counter()
    for term in {h[2] for h in all_hits}:
        seen = {bisect.bisect_right(chunk_starts, h[0]) - 1 for h in all_hits if h[2] == term}
        term_df[term] = len(seen)
    plain_terms = [t for t in terms if not t.lower().startswith("re:")]
    query_words = Counter(words(" ".join("".join(_fold_char(c) for c in t.replace("*", " ")) for t in plain_terms)))
    word_df = Counter()
    for counts in chunk_words:
        for w in query_words:
            if counts.get(w):
                word_df[w] += 1

    def word_score(counts: Counter, dl: int) -> float:
        return sum(_bm25(counts.get(w, 0), word_df[w], dl, n_docs, avgdl) for w in query_words)

    passages = []
    if all_hits:
        windows = []
        for start, end, term, label in sorted(all_hits):
            lo, hi = next(((s, e) for s, e, lab in spans if s <= start < e), (0, len(text)))
            ws, we = _snap(text, max(lo, start - context), min(hi, end + context), lo, hi)
            if windows and windows[-1][3] == (lo, hi) and ws <= windows[-1][1] + 20:
                windows[-1][1] = max(windows[-1][1], we)
                windows[-1][2].append((start, term))
            else:
                windows.append([ws, we, [(start, term)], (lo, hi), label])
        for ws, we, hits, _, label in windows:
            counts = Counter(words(folded[to_folded(ws):to_folded(we)]))
            dl = sum(counts.values())
            per_term = Counter(term for _, term in hits)
            phrase = sum(_bm25(n, term_df[t], dl, n_docs, avgdl) for t, n in per_term.items())
            score = phrase + WORD_WEIGHT * word_score(counts, dl)
            passages.append({"page": label, "score": round(score, 3), "terms": dict(per_term),
                             "text": _clean(text[ws:we]), "_start": ws, "_refs": all(in_refs(h) for h, _ in hits)})
        basis = "windows around the term hits, ranked by BM25"
    else:
        for (s, e, label), counts in zip(chunks, chunk_words):
            score = word_score(counts, sum(counts.values()))
            if score > 0:
                passages.append({"page": label, "score": round(score, 3), "terms": {},
                                 "text": _clean(text[s:e]), "_start": s, "_refs": mostly_refs(s, e)})
        basis = ("no term occurs in the text; these are the closest passages by BM25 over the words of the terms"
                 if passages else "no term and none of their words occur in the text")
    passages.sort(key=lambda p: (p["_refs"], -p["score"], -len(p["terms"]), p["_start"]))
    passages = passages[:max(0, top)]
    for rank, p in enumerate(passages, 1):
        p["rank"] = rank
        p.pop("_start")
        if p.pop("_refs"):
            p["in_reference_list"] = True
    labels = [label for _, _, label in spans if label is not None]
    ref_pages = ([p for p in dict.fromkeys((page_at(pages, refs[0]), page_at(pages, max(refs[0], refs[1] - 1))))
                  if p is not None] if refs else [])
    return {
        "terms": results,
        "total_hits": len(all_hits),
        "terms_with_hits": sum(1 for r in results if r["hits"]),
        "terms_without_hits": [r["term"] for r in results
                               if not r["hits"] and "error" not in r and "inside_longer_words" not in r],
        "terms_only_inside_longer_words": [r["term"] for r in results if "inside_longer_words" in r],
        "passages": passages,
        "passage_basis": basis,
        "pages_scanned": {"count": sum(1 for x in labels if isinstance(x, int)), "labels": labels[:1] + labels[-1:]},
        "reference_list": {"pages": ref_pages, "note": "hits there are titles of works it cites, not discussion"}
                          if refs else None,
        "chars": len(text),
        "settings": {
            "context": context, "top": top,
            "matching": "case-insensitive; spaces, hyphens and line breaks between words ignored; line-break "
                        "hyphenation joined; whole words with optional plural; * ends a word with any letters; "
                        "re: prefix for a regular expression; a term with no whole-word hit is also counted "
                        "as the start of longer words (inside_longer_words)",
            "ranking": f"BM25 (k1={K1}, b={B}) over the terms as phrases plus {WORD_WEIGHT} x BM25 over their "
                       f"words; document frequencies from {len(chunks)} chunks of about {CHUNK_WORDS} words; "
                       "passages in the work's reference list come last",
            "pages": "PDF page index from the [[page N]] markers, starting at 1",
        },
    }


# ================================================================ command
def _caveats(meta: dict, text: str) -> list:
    out = []
    if meta.get("abstract_only") or text.lstrip().startswith("[[abstract]]"):
        out.append("Abstract only: zero hits here cannot show that a topic is absent. With only the abstract, "
                   "a negative verdict becomes cannot verify.")
    version = meta.get("version")
    if version == "submitted":
        out.append("Working-paper or preprint version: the published article may differ.")
    elif version in (None, "unknown"):
        out.append("The version read is not known.")
    pages, with_text = meta.get("pages"), meta.get("pages_with_text")
    if isinstance(pages, int) and isinstance(with_text, int) and with_text < pages:
        out.append(f"{pages - with_text} of {pages} pages have little or no extractable text (figures, tables or "
                   "scans); terms on those pages may be missed.")
    if meta.get("truncated"):
        out.append("Only part of the document was extracted.")
    if text.lstrip().startswith("[[text]]"):
        out.append("This source has no page numbers.")
    ident = meta.get("identity") or {}
    if ident.get("basis") and not str(ident["basis"]).startswith("DOI and title"):
        out.append(f"Identity check of the document: {ident['basis']}.")
    out.append("PDF extraction can garble equations and symbols: search for parameter names (beta) as well as "
               "symbols (β), and check tables and appendices.")
    return out


def _opening(text: str) -> str:
    spans = page_spans(text)
    if not spans:
        return ""
    start, end, _ = spans[0]
    return _clean(text[start:min(end, start + 900)])


def scan_command(work: Path, ref: str, terms: list, context: int = 300, top: int = 8) -> int:
    """`pc.py scan WORK --ref R --terms ...`: print the absence record and append it to scans/<ref>.jsonl."""
    work = Path(work)
    citations = work / "citations"
    rid, raw, key = ref, None, None
    if (work / "paper_map.json").exists():
        from ..model import PaperMap

        reference = PaperMap.load(work / "paper_map.json").reference(ref)
        if reference is not None:
            rid, raw, key = reference.id, reference.raw, reference.key
    meta_path, text_path = citations / "sources" / f"{rid}.json", citations / "sources" / f"{rid}.txt"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    record = {"ref": rid, "key": key or meta.get("key"), "reference": raw, "scanned_at": now}
    if not text_path.exists():
        record.update({"status": "no_text", "terms_requested": list(terms),
                       "note": meta.get("note") or "cannot verify: no full text (run pc.py cite-prepare first)",
                       "tried": [f"{a.get('step')}: {a.get('outcome')}" for a in meta.get("attempts", [])]})
        code = 1
    else:
        text = text_path.read_text(encoding="utf-8", errors="replace")
        result = scan(text, list(terms), context=context, top=top)
        abstract_only = bool(meta.get("abstract_only")) or text.lstrip().startswith("[[abstract]]")
        n = result["pages_scanned"]["count"]
        record.update({
            "status": "ok",
            "version_read": {k: meta.get(k) for k in ("status", "source", "version", "url", "landing_page", "pages",
                                                      "pages_with_text", "abstract_only", "fetched") if k in meta},
            "scope": "abstract only" if abstract_only else (f"full text, PDF pages 1-{n}" if n else "full text without page numbers"),
            "text_file": f"citations/sources/{rid}.txt",
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            **result,
            "opening": _opening(text),
            "caveats": _caveats(meta, text),
        })
        if meta.get("abstract") and not abstract_only:
            record["abstract"] = meta["abstract"][:1500]
        code = 0
    print(json.dumps(record, ensure_ascii=False, indent=1))
    scans = citations / "scans"
    scans.mkdir(parents=True, exist_ok=True)
    with (scans / f"{rid}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return code
