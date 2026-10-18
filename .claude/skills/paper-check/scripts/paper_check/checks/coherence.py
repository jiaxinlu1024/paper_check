"""Coherence checks with a script part (COH).

COH-05  spelling variants of one term (hyphenated, closed or open compounds)
COH-06  symbols used before the definitions slice defines them
COH-07  abbreviations: used before their definition, defined twice, defined but unused
COH-09  passages repeated word for word in different places

These are kept light and conservative: each flags only what a script can show, and
the reading agents judge meaning (COH-05 synonyms, COH-06 overloading).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from ..model import Evidence, Fix
from . import register
from .format import (BODY_KINDS, PROSE_KINDS, inside, math_spans, note_coverage, prose, quote_at, related,
                     sentence_bounds, sentence_quote, span_list)

SCRIPT = "checks/coherence.py"


# =============================================================== COH-05 term variants
# Pairs whose hyphenated and closed forms are different words.
_NOT_VARIANTS = {"re-sign", "re-cover", "re-form", "re-press", "re-creation", "re-sort", "re-treat", "re-collect",
                 "re-present", "re-lease", "re-mark", "co-op", "un-ionized", "multi-ply", "re-count", "re-solve",
                 "re-serve", "re-search", "re-act", "pro-test", "de-light", "in-valid", "re-fuse", "re-signed",
                 "re-formed", "re-treated", "re-covered", "re-pressed", "re-sorted", "re-marked", "re-leased"}
# Open (two-word) forms checked against their closed or hyphenated forms; only pairs that
# are spellings of one noun, not verb-noun pairs such as "set up" and "setup".
_OPEN_FORMS = ["data set", "work force", "policy maker", "policy makers", "decision maker", "decision makers",
               "well being", "co worker", "co workers", "sub sample", "sub samples", "sub group", "sub groups",
               "co author", "co authors", "pre registration", "pre registered", "time frame", "wage earner",
               "wage earners", "web site", "e mail", "on line", "non profit", "life time"]
_WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")


_CAMEL = re.compile(r"[A-Z][a-z]+(?:[A-Z][a-z0-9]*)+")


def _forms(pm):
    counts, first, occurrences = Counter(), {}, defaultdict(list)
    for b in prose(pm, PROSE_KINDS):
        skip = span_list(b) + math_spans(b.text)
        for m in _WORD.finditer(b.text):
            if inside(m.start(), skip):
                continue
            # A variable name is not a spelling of a term: "PostRetirement_{it}", "IncomeQuartile".
            if b.text[m.end():m.end() + 1] in ("_", "^", "{") or _CAMEL.fullmatch(m.group(0)):
                continue
            w = m.group(0).lower()
            counts[w] += 1
            occurrences[w].append((b, m.start(), m.end()))
            first.setdefault(w, (b, m.start(), m.end()))
    return counts, occurrences


@register("COH-05")
def term_variants(pm, ctx):
    counts, occ = _forms(pm)
    groups = []
    seen = set()
    for w in sorted(counts):
        if w.count("-") != 1 or w in _NOT_VARIANTS:
            continue
        a, b = w.split("-")
        if len(a) < 2 or len(b) < 2:
            continue
        closed = a + b
        forms = {w: counts[w]}
        if counts.get(closed):
            forms[closed] = counts[closed]
        if len(forms) > 1 and closed not in seen:
            seen.add(closed)
            groups.append(forms)
    texts = [(b, b.text) for b in prose(pm, PROSE_KINDS)]
    for open_form in _OPEN_FORMS:
        a, b = open_form.split(" ")
        closed, hyph = a + b, f"{a}-{b}"
        pat = re.compile(rf"\b{a}\s+{b}\b", re.I)
        hits = [(blk, m.start(), m.end()) for blk, t in texts for m in pat.finditer(t)
                if not inside(m.start(), span_list(blk) + math_spans(t))]
        if not hits:
            continue
        forms = {open_form: len(hits)}
        occ[open_form] = hits
        for alt in (closed, hyph):
            if counts.get(alt):
                forms[alt] = counts[alt]
        if len(forms) > 1 and closed not in seen:
            seen.add(closed)
            groups.append(forms)
    for forms in groups:
        ranked = sorted(forms.items(), key=lambda kv: (-kv[1], kv[0]))
        major, n_major = ranked[0]
        minor_form, n_minor = ranked[-1]
        b, s, e = occ[minor_form][0]
        mb, ms, me = occ[major][0]
        quote = quote_at(b, s, e, 4, 4)
        original = b.text[s:e]
        replacement = major if not original[:1].isupper() else major[:1].upper() + major[1:]
        listing = ", ".join(f"\"{f}\" {n}x" for f, n in ranked)
        yield ctx.finding(
            "COH-05", "One term spelled more than one way", "minor",
            f"The paper writes the same term in {len(ranked)} ways: {listing}. Pick one spelling.",
            block=b, quote=quote, status="likely", confidence="medium",
            related=[related(mb, quote_at(mb, ms, me, 4, 4))],
            evidence=[Evidence(type="script_output", text=listing, data={"script": SCRIPT, "forms": forms})],
            trajectory=["Counted every word form in the text, outside citations and math.",
                        f"Matched hyphenated, closed and open spellings of the same compound: {listing}."],
            fix=Fix(action="replace", original=original, replacement=replacement,
                    detail=f"Use \"{major}\" throughout.",
                    resolved_when=f"Only one spelling of \"{major}\" remains."),
            script=SCRIPT, extra={"forms": forms})


# =============================================================== COH-06 symbols before definition
_GREEK = ("alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|iota|kappa|lambda|mu|nu|xi|pi|varpi|"
          "rho|varrho|sigma|varsigma|tau|upsilon|phi|varphi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|"
          "Upsilon|Phi|Psi|Omega")
_SYM = re.compile(rf"\\({_GREEK})(?![A-Za-z])|(?<![\\A-Za-z])([A-Za-z])(?![A-Za-z])")
_UNI_GREEK = dict(zip("αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΥΦΨΩ",
                      ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda",
                       "mu", "nu", "xi", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega", "Gamma",
                       "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega"]))
_APPOSITIVE = re.compile(r"(?:parameter|factor|coefficient|rate|share|probability|elasticity|index|variable|level|measure|"
                         r"degree|weight|cost|price|value|number|fraction|discount|utility|threshold|endowment|payoff|"
                         r"wage|income|function|vector|matrix|denoted|called)\s*(?:of\s*)?$", re.I)
_DEF_CUE = re.compile(r"\b(?:denotes?|denoted|is defined|are defined|we define|define|refers? to|we call|stands? for|"
                      r"is the|are the|be the|where|let)\b", re.I)
_AFTER_DEF = re.compile(r"\s*(?:,|\(|--|—|–)\s*(?:the|a|an|our|its|i\.e\.,?|which is|that is)\b", re.I)


def _symbols(text: str) -> list:
    """(name, start, end) for symbols inside $...$ math, plus Unicode Greek letters outside it."""
    out = []
    for ms, me in math_spans(text):
        inner = text[ms + 1:me - 1]
        for m in _SYM.finditer(inner):
            name = m.group(1) or m.group(2)
            out.append((name, ms, me))
    for i, ch in enumerate(text):
        if ch in _UNI_GREEK and not inside(i, math_spans(text)):
            out.append((_UNI_GREEK[ch], i, i + 1))
    return out


@register("COH-06")
def symbols_before_definition(pm, ctx):
    order = pm.block_order()
    defs = {}
    for d in pm.definitions:
        if d.kind != "symbol":
            continue
        b = pm.block(d.block)
        if b is None:
            continue
        for name, _, _ in _symbols(d.definition):
            if len(name) == 1 and name in "itnjkxyNTp":
                continue  # generic indices and variables are too common to judge by script
            defs.setdefault(name, (b, d))
    if not defs:
        note_coverage(ctx, "COH-06", "the definitions slice defines no symbols")
        return
    note_coverage(ctx, "COH-06", "symbols defined: " + ", ".join(sorted(defs)))
    reported = set()
    for b in prose(pm, BODY_KINDS):
        for name, ms, me in _symbols(b.text):
            if name not in defs or name in reported:
                continue
            db, d = defs[name]
            if order.get(b.id, 0) >= order.get(db.id, 0):
                continue
            s0, e0 = sentence_bounds(b, ms)
            if (_DEF_CUE.search(b.text[s0:e0]) or _APPOSITIVE.search(b.text[max(s0, ms - 40):ms])
                    or _AFTER_DEF.match(b.text[me:me + 30])):
                continue  # defined in passing where it is used
            reported.add(name)
            quote = sentence_quote(b, ms, 35)
            sym = b.text[ms:me]
            def_quote = d.definition if len(d.definition.split()) <= 40 else sentence_quote(db, 0, 35)
            yield ctx.finding(
                "COH-06", "Symbol used before it is defined", "minor",
                f"{sym} is used here, but the paper defines it only later ({db.anchor.label()}): "
                f"\"{d.definition[:160]}\".",
                block=b, quote=quote, status="likely", confidence="medium",
                related=[related(db, def_quote)],
                evidence=[Evidence(type="quote", text=quote, block=b.id), Evidence(type="quote", text=def_quote, block=db.id)],
                trajectory=["Read the symbols that the definitions slice defines.",
                            f"Found {sym} in {b.anchor.label()}, before its definition in {db.anchor.label()}, with no "
                            "definition in the same sentence."],
                fix=Fix(action="investigate", detail=f"Define {sym} at its first use, or move the use after the "
                                                     "definition.",
                        resolved_when=f"{sym} is defined at or before its first use in the body."),
                script=SCRIPT, extra={"symbol": name})


# =============================================================== COH-07 abbreviations
def _abbr_uses(pm, abbr: str, defs: list) -> list:
    """Uses in running text (abstract, paragraphs, lists, footnotes, captions), outside its definitions.

    Titles, headings and keyword lines often use abbreviations before the text defines
    them, so they do not count as a first use."""
    pat = re.compile(rf"\b{re.escape(abbr)}s?\b")
    def_pos = {(d["block"], d["start"]) for d in defs}
    out = []
    for b in pm.blocks:
        if b.kind not in PROSE_KINDS or not b.text:
            continue
        skip = span_list(b, crossrefs=False)
        for m in pat.finditer(b.text):
            if (b.id, m.start()) in def_pos or inside(m.start(), skip):
                continue
            out.append((b, m.start(), m.end()))
    return out


def _article_fix(block, start: int, abbr: str, expansion: str) -> tuple:
    """(original, replacement) that spell out an abbreviation at its first use, fixing a/an."""
    original = block.text[start:start + len(abbr)]
    new = f"{expansion} ({abbr})"
    m = re.search(r"\b(an|a|An|A)\s+$", block.text[max(0, start - 4):start])
    if m:
        art_start = start - len(block.text[max(0, start - 4):start]) + m.start()
        original = block.text[art_start:start + len(abbr)]
        art = "an" if expansion[:1].lower() in "aeiou" else "a"
        new = f"{art.capitalize() if m.group(1)[0].isupper() else art} {expansion} ({abbr})"
    return original, new


@register("COH-07")
def abbreviations(pm, ctx):
    order = pm.block_order()
    abstract = {b.id for b in pm.blocks if b.kind == "abstract"}
    steps = ["Read the abbreviations with the offsets of their definitions and uses from the paper map.",
             "Treated the abstract and the body separately: each should define an abbreviation at its first use."]

    def pos(block_id, start):
        return (order.get(block_id, 10**9), start)

    for a in pm.abbreviations:
        abbr, defs = a["abbr"], a.get("defined_at") or []
        if not defs:
            continue  # never defined: standard abbreviations need none, so the reading agents judge these
        expansion = a.get("expansion") or abbr
        uses = [(pos(b.id, s), b, s) for b, s, _ in _abbr_uses(pm, abbr, defs)]
        body_defs = sorted((pos(d["block"], d["start"]), d) for d in defs if d["block"] not in abstract)
        abs_defs = sorted((pos(d["block"], d["start"]), d) for d in defs if d["block"] in abstract)
        body_uses = sorted((u for u in uses if u[1].id not in abstract), key=lambda u: u[0])
        abs_uses = sorted((u for u in uses if u[1].id in abstract), key=lambda u: u[0])

        if body_defs:
            d0pos, d0 = body_defs[0]
            def_block = pm.block(d0["block"])
            def_quote = sentence_quote(def_block, d0["start"], 35)
            before = [u for u in body_uses if u[0] < d0pos]
            after = [u for u in body_uses if u[0] > d0pos]
            if before:
                _, b, s = before[0]
                quote = sentence_quote(b, s, 35)
                original, replacement = _article_fix(b, s, abbr, expansion)
                yield ctx.finding(
                    "COH-07", "Abbreviation used before it is defined", "minor",
                    f"{abbr} is used here before the paper spells it out as \"{expansion}\" ({def_block.anchor.label()})."
                    + ("" if after else " It is not used again after the definition, so the definition sits in the "
                                        "wrong place."),
                    block=b, quote=quote, status="confirmed", related=[related(def_block, def_quote)],
                    evidence=[Evidence(type="quote", text=quote, block=b.id),
                              Evidence(type="quote", text=def_quote, block=def_block.id),
                              Evidence(type="computed_result", text="first use precedes the definition",
                                       data={"formula": "compare (block order, character offset)",
                                             "inputs": {"first_use": {"block": b.id, "start": s},
                                                        "definition": {"block": d0["block"], "start": d0["start"]}},
                                             "output": "use before definition"})],
                    trajectory=steps + [f"{abbr}: first body use at {b.anchor.label()} (offset {s}); first definition at "
                                        f"{def_block.anchor.label()} (offset {d0['start']})."],
                    fix=Fix(action="replace", original=original, replacement=replacement,
                            detail=f"Spell out {abbr} at its first use and drop the later \"({abbr})\".",
                            resolved_when=f"{abbr} is defined at its first use in the body."),
                    script=SCRIPT, extra={"abbr": abbr})
            elif not after:
                yield ctx.finding(
                    "COH-07", "Abbreviation defined but never used", "suggestion",
                    f"{abbr} is defined as \"{expansion}\" but never used afterwards, so the abbreviation adds nothing.",
                    block=def_block, quote=def_quote, status="confirmed",
                    evidence=[Evidence(type="checked_absence", text=abbr,
                                       data={"scope": "all text after the definition", "terms": {abbr: 0}})],
                    trajectory=steps + [f"Searched the text after the definition of {abbr}: no use."],
                    fix=Fix(action="investigate", detail=f"Drop \"({abbr})\", or use {abbr} where the term recurs.",
                            resolved_when=f"{abbr} is used after its definition, or not introduced."),
                    script=SCRIPT, extra={"abbr": abbr})
            if len(body_defs) >= 2:
                _, d1 = body_defs[1]
                b2 = pm.block(d1["block"])
                quote = sentence_quote(b2, d1["start"], 35)
                yield ctx.finding(
                    "COH-07", "Abbreviation defined twice", "minor",
                    f"{abbr} is defined again here, after its first definition ({def_block.anchor.label()}).",
                    block=b2, quote=quote, status="confirmed", related=[related(def_block, def_quote)],
                    evidence=[Evidence(type="quote", text=quote, block=b2.id),
                              Evidence(type="quote", text=def_quote, block=def_block.id)],
                    trajectory=steps + [f"{abbr} has {len(body_defs)} definitions in the body."],
                    fix=Fix(action="investigate", detail=f"Keep the first definition and write {abbr} here.",
                            resolved_when=f"{abbr} is defined once in the body."),
                    script=SCRIPT, extra={"abbr": abbr})
        elif body_uses and abs_defs:
            _, b, s = body_uses[0]
            quote = sentence_quote(b, s, 35)
            yield ctx.finding(
                "COH-07", "Abbreviation defined only in the abstract", "minor",
                f"{abbr} is spelled out in the abstract but not again at its first use in the body.",
                block=b, quote=quote, status="confirmed",
                evidence=[Evidence(type="quote", text=quote, block=b.id)],
                trajectory=steps + [f"{abbr} has a definition in the abstract and none in the body."],
                fix=Fix(action="replace", original=b.text[s:s + len(abbr)], replacement=f"{expansion} ({abbr})",
                        resolved_when=f"The body defines {abbr} at its first use."),
                script=SCRIPT, extra={"abbr": abbr})
        if abs_uses:
            _, b, s = abs_uses[0]
            quote = sentence_quote(b, s, 35)
            if not abs_defs:
                yield ctx.finding(
                    "COH-07", "Abbreviation not defined in the abstract", "minor",
                    f"The abstract uses {abbr} without spelling it out. Abstracts are read on their own, so define it "
                    f"there (\"{expansion} ({abbr})\") as well as in the body.",
                    block=b, quote=quote, status="likely", confidence="medium",
                    evidence=[Evidence(type="quote", text=quote, block=b.id)],
                    trajectory=steps + [f"{abbr} appears in the abstract with no definition there."],
                    fix=Fix(action="replace", original=b.text[s:s + len(abbr)], replacement=f"{expansion} ({abbr})",
                            resolved_when=f"The abstract defines {abbr} or does not use it."),
                    script=SCRIPT, extra={"abbr": abbr})
            elif abs_uses[0][0] < abs_defs[0][0]:
                yield ctx.finding(
                    "COH-07", "Abbreviation used before it is defined", "minor",
                    f"In the abstract, {abbr} is used before it is spelled out.",
                    block=b, quote=quote, status="confirmed",
                    evidence=[Evidence(type="quote", text=quote, block=b.id)],
                    trajectory=steps + [f"{abbr}: the first use in the abstract precedes the abstract's definition."],
                    fix=Fix(action="investigate", detail=f"Move the definition of {abbr} to its first use.",
                            resolved_when=f"The abstract defines {abbr} at its first use."),
                    script=SCRIPT, extra={"abbr": abbr})


# =============================================================== COH-09 repeated passages
K = 8               # words per shingle
MIN_RUN = 15        # words repeated across sections
MIN_RUN_SAME = 20   # words repeated within one section
_TOKEN = re.compile(r"\w+(?:[-']\w+)*")
_SKIP_SECTION = re.compile(r"\binstructions?\b|\bquestionnaires?\b|\bsurvey (?:items|questions|instruments?|text)\b|"
                           r"\bscreens?\b|\bscreenshots?\b|\bscripts?\b|\bprotocols?\b|"
                           r"\bmaterials?\b(?! and methods)|\bconsent\b", re.I)


@register("COH-09")
def repeated_passages(pm, ctx):
    blocks = [b for b in prose(pm, ("paragraph", "list_item", "footnote"))
              if not any(_SKIP_SECTION.search(s) for s in b.section or [])]
    # Citations do not count: two passages that share only a list of citations are not repeated text.
    toks = [[(m.group(0).lower(), m.start(), m.end()) for m in _TOKEN.finditer(b.text)
             if not any(c.start <= m.start() < c.end for c in b.citations)] for b in blocks]
    index = defaultdict(list)
    found = []
    for j, tj in enumerate(toks):
        covered = 0
        for p in range(len(tj) - K + 1):
            if p < covered:
                continue
            key = tuple(t[0] for t in tj[p:p + K])
            best = None
            for i, q in index.get(key, []):
                n = K
                while p + n < len(tj) and q + n < len(toks[i]) and tj[p + n][0] == toks[i][q + n][0]:
                    n += 1
                if not best or n > best[2]:
                    best = (i, q, n)
            if best:
                i, q, n = best
                same = blocks[i].section[:1] == blocks[j].section[:1]
                if n >= (MIN_RUN_SAME if same else MIN_RUN):
                    found.append((i, q, j, p, n))
                    covered = p + n
        for p in range(len(tj) - K + 1):
            index[tuple(t[0] for t in tj[p:p + K])].append((j, p))
    for i, q, j, p, n in found:
        b1, b2 = blocks[i], blocks[j]
        s2, e2 = toks[j][p][1], toks[j][p + n - 1][2]
        s1, e1 = toks[i][q][1], toks[i][q + n - 1][2]
        def clip(b, s, e, toklist, start_tok):
            if n <= 40:
                return b.text[s:e]
            head_end = toklist[start_tok + 24][2]
            tail_start = toklist[start_tok + n - 10][1]
            return f"{b.text[s:head_end]} ... {b.text[tail_start:e]}"
        quote = clip(b2, s2, e2, toks[j], p)
        other = clip(b1, s1, e1, toks[i], q)
        yield ctx.finding(
            "COH-09", "Passage repeated word for word", "minor",
            f"{n} consecutive words here repeat a passage at {b1.anchor.label()}"
            + (f" (section \"{b1.section[0]}\")" if b1.section else "") + ".",
            block=b2, quote=quote, status="confirmed", related=[related(b1, other)],
            evidence=[Evidence(type="quote", text=quote, block=b2.id), Evidence(type="quote", text=other, block=b1.id),
                      Evidence(type="computed_result", text="repeated run",
                               data={"formula": f"longest common run of words, from {K}-word shingles",
                                     "output": n, "threshold": MIN_RUN})],
            trajectory=[f"Indexed {K}-word shingles of every paragraph, list item and footnote, skipping sections of "
                        "experimental instructions or questionnaires.",
                        f"Found a {n}-word run shared by {b1.anchor.label()} and {b2.anchor.label()}."],
            fix=Fix(action="investigate", detail="Keep the passage in one place and refer to it, or rephrase one of the "
                                                 "two.",
                    resolved_when="No passage of 15 or more words appears twice."),
            script=SCRIPT, extra={"words": n})
