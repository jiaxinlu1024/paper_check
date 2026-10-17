"""NUM-10: sample sizes across tables and models are consistent, or the paper explains the differences.

Reads every "Observations", "N" or "Sample size" row of every table, column by
column. When a table or a model uses fewer or more observations than the paper's
main sample, it looks for an explanation in the table's caption and notes and in
the paragraphs that mention the table: a subsample, a restriction, missing data,
attrition, a balanced panel and so on. A difference with no explanation nearby is
reported as likely; the numbers agent reads the paper for explanations phrased in
other words.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from ..model import Evidence, Fix
from . import register

_N_ROW = re.compile(r"^\s*(observations|obs\.?|n|no\.? of obs(?:ervations)?|number of (?:observations|obs\.?|"
                    r"households|individuals|respondents|participants|firms|employees|borrowers|users|consumers)|"
                    r"sample size|n\.? obs\.?)\s*$", re.I)
_EXPLAIN = re.compile(r"sub-?samples?|restrict|exclud|drop(?:s|ped|ping)?\b|missing|non-?missing|attrition|"
                      r"balanced panel|unbalanced|non-?response|available for|only (?:the |those |households|"
                      r"respondents|participants|individuals|firms)|conditional on|limited to|smaller sample|"
                      r"sample (?:is|are|was|were) (?:reduced|limited|smaller)|fewer observations|"
                      r"those who|among (?:the )?(?:households|respondents|participants|borrowers)|"
                      r"singleton|lagged|first[- ]difference|we lose|lost|winsori[sz]|trim|except|estimated on|"
                      r"(?:respondents|households|individuals|participants|borrowers|firms|users) (?:who|that|with)|"
                      r"subset|sample of|subgroup|split by|by (?:income|treatment|gender|quartile|group)", re.I)


def _int(cell: str) -> Optional[int]:
    text = (cell or "").strip().replace(",", "").replace(" ", "").replace(" ", "")
    m = re.fullmatch(r"\(?(\d{2,9})\)?", text)
    return int(m.group(1)) if m else None


def _table_ns(table) -> list:
    """[(row label, column index, column header, N)] for every observation-count row."""
    out = []
    rows = table.rows or []
    header = None
    for r in rows:
        if r and not _int(r[0]) and any(c.strip() for c in r[1:]) and header is None and not _N_ROW.match(r[0] or ""):
            header = r
        if r and _N_ROW.match(r[0] or ""):
            for j, cell in enumerate(r[1:], 1):
                n = _int(cell)
                if n is not None:
                    col = header[j].strip() if header and j < len(header) else f"column {j}"
                    out.append((r[0].strip(), j, col or f"column {j}", n))
    return out


def _mentions(pm, table) -> list:
    """Paragraphs that cite the table by its number."""
    if not table.number:
        return []
    pat = re.compile(rf"\bTables?\s+(?:[A-Z]?\d+\s*(?:,|and|&|-|–|to)\s*)*{re.escape(str(table.number))}\b")
    return [b for b in pm.blocks if b.kind in ("paragraph", "list_item", "footnote") and pat.search(b.text)]


_N_NOTE = re.compile(r"\b[Nn]\s*=\s*(\d{1,3}(?:,\d{3})+|\d{2,9})\b")


def _note_ns(table) -> list:
    """N stated in a table's caption or notes, such as "N = 1,234"."""
    out = []
    for where, text in (("caption", table.caption or ""), ("notes", table.notes or "")):
        for m in _N_NOTE.finditer(text):
            out.append((f"N in the {where}", 0, f"stated in the {where}", int(m.group(1).replace(",", ""))))
    return out


def _partitions(ns: list) -> set:
    """Values that are parts of a split: two or three values that add up to another value of the same table."""
    vals = sorted({n for *_, n in ns})
    parts = set()
    for total in vals:
        others = [v for v in vals if v < total]
        for i, a in enumerate(others):
            for b in others[i + 1:] + [a]:
                if abs(a + b - total) <= max(2, total * 0.002):
                    parts.update({a, b})
                for c in others:
                    if abs(a + b + c - total) <= max(2, total * 0.002) and len({a, b, c}) >= 2:
                        parts.update({a, b, c})
    return parts


def _number_pattern(n: int) -> re.Pattern:
    """A sample size as the text may print it: 1,858 or 1858 or 1 858."""
    body = r"[,\u2009\u202f ]?".join(f"{n:,}".split(",")) if n >= 1000 else str(n)
    return re.compile(rf"(?<![\d.]){body}(?!\d|,\d)")


def _mentioned(pm, n: int) -> Optional[str]:
    """The id of a text block that states this sample size."""
    pat = _number_pattern(n)
    for b in pm.blocks:
        if b.kind in ("paragraph", "list_item", "footnote", "abstract", "caption") and pat.search(b.text):
            return b.id
    return None


def _units(n: int, main_n: int) -> Optional[int]:
    """k when the main N is about k times this N: units such as households observed k times each."""
    if n <= 0 or main_n <= n:
        return None
    k = round(main_n / n)
    return k if 2 <= k <= 60 and abs(main_n - k * n) <= max(2, 0.01 * main_n) else None


@register("NUM-10")
def sample_sizes(pm, ctx):
    tables = [t for t in pm.tables]
    found = [(t, _table_ns(t) + _note_ns(t)) for t in tables]
    found = [(t, ns) for t, ns in found if ns]
    if not found:
        ctx.not_applicable("NUM-10", "no table reports its number of observations")
        return
    all_ns = Counter(n for _, ns in found for *_, n in ns)
    main_n, _ = all_ns.most_common(1)[0]
    if len(all_ns) == 1:
        ctx.note("NUM-10", f"{len(found)} tables report observations; all use N = {main_n:,}")
        return
    unexplained: dict = {}   # N -> list of (table, column label)
    explained = Counter()
    for table, ns in found:
        parts = _partitions(ns + [("main", 0, "main", main_n)])
        texts = [table.caption or "", table.notes or ""] + [b.text for b in _mentions(pm, table)]
        cue = next((m for t in texts for m in [_EXPLAIN.search(t)] if m), None)
        for lab, j, col, n in ns:
            if n == main_n:
                continue
            if cue or n in parts or _mentioned(pm, n):
                explained[n] += 1
                continue
            unexplained.setdefault(n, []).append((table, col))
    for n, uses in sorted(unexplained.items(), key=lambda x: -x[0]):
        first = uses[0][0]
        block = next((b for b in pm.blocks if b.kind == "table" and
                      ((b.attrs or {}).get("table_id") == first.id or (b.attrs or {}).get("number") == first.number)), None)
        quote = None
        if block is not None:
            pat = _number_pattern(n)
            for line in block.text.split("\n"):
                if _N_ROW.match(line.split("|")[0]) and pat.search(line):
                    quote = line.strip()
                    break
                m = pat.search(line)
                if m and _N_NOTE.search(line):
                    # the clause of the note that holds this N, not the whole note
                    start = max(line.rfind(". ", 0, m.start()) + 2, line.rfind("; ", 0, m.start()) + 2, 0)
                    end_candidates = [i for i in (line.find(". ", m.end()), line.find("; ", m.end())) if i != -1]
                    end = min(end_candidates) if end_candidates else len(line)
                    quote = line[start:end].strip()
                    break
        where = "; ".join(f"Table {t.number or '?'} ({col})" for t, col in uses[:8])
        share = n / main_n
        k = _units(n, main_n)
        if k:
            severity = "minor"
            problem = (f"N = {n:,} in {where}, while most tables use N = {main_n:,}, about {k} times as many. N = {n:,} "
                       f"is probably the number of units (such as households or people) and {main_n:,} the number of "
                       f"unit-period observations, but the text never states {n:,} or says how the two relate.")
        else:
            severity = "major" if abs(1 - share) >= 0.05 else "minor"
            problem = (f"N = {n:,} in {where}, while the paper's main sample is N = {main_n:,}. The text never states "
                       f"{n:,}, the table notes and the paragraphs that discuss {'these tables' if len(uses) > 1 else 'the table'} "
                       "do not explain the change, and the columns do not add up as a split of the sample.")
        yield ctx.finding(
            "NUM-10", "Sample size changes without an explanation", severity,
            problem=problem,
            block=block, quote=quote,
            evidence=[Evidence("computed_result", data={
                "formula": "observation counts per table column against the most common N, with splits and text mentions",
                "inputs": {"N": n, "most common N": main_n, "tables": [f"Table {t.number}" for t, _ in uses]},
                "output": f"{n / main_n:.1%} of the main sample"}),
                Evidence("checked_absence", data={
                    "scope": "every paragraph, footnote and caption, plus the notes of the tables involved",
                    "terms": {f"{n:,}": 0, "subsample, restrict, exclude, missing, attrition, balanced panel and similar": 0}})],
            trajectory=[f"Read the observation counts of {len(found)} tables: N values {', '.join(f'{v:,}' for v in sorted(all_ns))}.",
                        f"The most common N is {main_n:,}; N = {n:,} appears in {where}.",
                        "Checked whether the columns split the sample, whether the text states this N, and whether the "
                        "notes or citing paragraphs explain the change: none of these."],
            fix=Fix("investigate", detail=f"Explain where N = {n:,} comes from, in the data section or the table notes: "
                                          "which observations are dropped and why (missing values, a subsample, "
                                          "attrition, lags), with the count lost at each step.",
                    resolved_when="Every sample size used in a table or model is stated and explained in the paper."),
            confidence="medium", status="likely", script="checks.samples",
            extra={"n": n, "main_n": main_n, "tables": [t.number for t, _ in uses]})
    ctx.note("NUM-10", f"compared observation counts in {len(found)} tables; most common N = {main_n:,}; "
                       f"{sum(explained.values())} differing counts are splits, stated in the text or explained nearby")
