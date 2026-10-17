"""Language checks with a script part (LANG).

LANG-01  US and UK spellings mixed, from a small built-in list of variant pairs
LANG-02  sentences over 45 words
LANG-04  vague or loaded words; "significant(ly)" only when no test is nearby
LANG-07  a small list of non-inclusive terms
LANG-08  filler phrases

Word lists are written for economics papers: "significantly" is a technical term
in economics, so it is flagged only without a statistical test in its sentence or
the sentences around it. Text inside quotation marks, citations, math, the
reference list and appendices of experimental instructions is not checked, since
it quotes others or what participants saw.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..model import Evidence, Fix
from ..textutil import word_count
from . import register
from .format import (PROSE_KINDS, inside, math_spans, note_coverage, prose, quote_at, related,
                     sentence_bounds, sentence_quote, setting, span_list, venue_other)

SCRIPT = "checks/language.py"
_INSTRUCTIONS = re.compile(r"\binstructions?\b|\bquestionnaires?\b|\bsurvey (?:items|questions|instruments?)\b|"
                           r"\bscreens?\b|\bscreenshots?\b|\bconsent forms?\b|\bscripts?\b", re.I)


def _texts(pm, kinds=PROSE_KINDS):
    """Blocks to check, without experimental instructions, with spans to skip."""
    out = []
    for b in prose(pm, kinds):
        if any(_INSTRUCTIONS.search(s) for s in b.section or []):
            continue
        out.append((b, span_list(b) + math_spans(b.text) + _quoted_spans(b.text)))
    return out


def _quoted_spans(text: str) -> list:
    spans = [(m.start(), m.end()) for m in re.finditer(r"“[^”]{1,400}”|\"[^\"]{1,400}\"|``.{1,400}?''", text)]
    return spans


def _proper(text: str, start: int) -> bool:
    """True for a capitalized word that is likely part of a name: in mid-sentence, or
    followed by another capitalized word ('Behavioural Public Policy')."""
    if not text[start:start + 1].isupper():
        return False
    before = text[:start].rstrip()
    if bool(before) and before[-1] not in ".!?:\"“(" and not re.search(r"(?:^|\n)\s*$", text[:start]):
        return True
    return bool(re.match(r"[A-Za-z'’-]+\s+(?:of\s+|and\s+|for\s+)?[A-Z][a-z]", text[start:start + 60]))


# =============================================================== LANG-01 US and UK spelling
_IZE_ROOTS = ("random|organ|real|recogn|util|optim|maxim|minim|standard|special|categor|general|summar|emphas|priorit|"
              "normal|central|final|capital|harmon|critic|monet|subsid|stabil|mobil|visual|formal|internal|character|"
              "memor|penal|legal|apolog|theor|hypothes|incentiv|individual|operational|conceptual|parameter|custom|"
              "familiar|local|neutral|rational|social|symbol|sympath|synthes|author|liberal|privat|modern|global|"
              "industrial|commercial|polar|vapor|equal")
# Group A: pairs where British and American English differ outright.
_PAIRS = [
    (r"behavior(?:s|al|ally|ist|ism)?", r"behaviour(?:s|al|ally|ist|ism)?"),
    (r"labor(?:s|ed|er|ers|ing)?", r"labour(?:s|ed|er|ers|ing)?"),
    (r"favor(?:s|ed|ing|able|ably|ite|ites)?", r"favour(?:s|ed|ing|able|ably|ite|ites)?"),
    (r"color(?:s|ed|ful|ing)?", r"colour(?:s|ed|ful|ing)?"),
    (r"honor(?:s|ed|ing|able)?", r"honour(?:s|ed|ing|able)?"),
    (r"neighbor(?:s|hood|hoods|ing)?", r"neighbour(?:s|hood|hoods|ing)?"),
    (r"endeavor(?:s|ed|ing)?", r"endeavour(?:s|ed|ing)?"),
    (r"cent(?:er|ers|ered|ering)", r"cent(?:re|res|red|ring)"),
    (r"defense", r"defence"),
    (r"offense", r"offence"),
    (r"analyz(?:e|ed|es|ing)", r"analys(?:e|ed|ing)"),  # 'analyses' is also the plural of 'analysis' in both
    (r"model(?:ing|ed|er|ers)", r"model(?:ling|led|ler|lers)"),
    (r"travel(?:ing|ed|er|ers)", r"travel(?:ling|led|ler|lers)"),
    (r"label(?:ing|ed)", r"label(?:ling|led)"),
    (r"signal(?:ing|ed)", r"signal(?:ling|led)"),
    (r"cancel(?:ing|ed)", r"cancel(?:ling|led)"),
    (r"enroll(?:ment|ments)", r"enrol(?:ment|ments)"),
    (r"fulfill(?:s|ment)?", r"fulfil(?:s|ment)?"),
    (r"skeptic(?:al|ally|ism|s)?", r"sceptic(?:al|ally|ism|s)?"),
    (r"gray", r"grey"),
    (r"aging", r"ageing"),
]
# -ize is American and also British (Oxford spelling); -ise is British only.
_IZE = (rf"(?:{_IZE_ROOTS})iz(?:e|es|ed|ing|ation|ations|er|ers)", rf"(?:{_IZE_ROOTS})is(?:e|es|ed|ing|ation|ations|er|ers)")
# British writers use both 'per cent' and 'percent', so only a mix of the two is reported.
_PCT = (r"percent", r"per cent")
_GROUPS = {
    "A": ([re.compile(rf"\b{us}\b", re.I) for us, _ in _PAIRS], [re.compile(rf"\b{uk}\b", re.I) for _, uk in _PAIRS]),
    "IZE": ([re.compile(rf"\b{_IZE[0]}\b", re.I)], [re.compile(rf"\b{_IZE[1]}\b", re.I)]),
    "PCT": ([re.compile(rf"\b{_PCT[0]}\b", re.I)], [re.compile(rf"\b{_PCT[1]}\b", re.I)]),
}


def _variant_hits(pm) -> dict:
    hits = {g: ([], []) for g in _GROUPS}
    for b, skip in _texts(pm, PROSE_KINDS + ("heading",)):
        for g, sides in _GROUPS.items():
            for side, pats in enumerate(sides):
                for pat in pats:
                    for m in pat.finditer(b.text):
                        if inside(m.start(), skip) or _proper(b.text, m.start()):
                            continue
                        hits[g][side].append((b, m.start(), m.end(), m.group(0)))
    return hits


@register("LANG-01")
def spelling_variant(pm, ctx):
    hits = _variant_hits(pm)
    us, uk = (len(x) for x in hits["A"])
    ize, ise = (len(x) for x in hits["IZE"])
    pct, per_cent = (len(x) for x in hits["PCT"])
    target = str(setting(ctx, "language_variant") or "").upper().replace("ENGLISH", "").strip() or None
    if target not in ("US", "UK"):
        target = None
    steps = [f"Counted US and UK forms of {len(_PAIRS)} spelling pairs (behavior/behaviour, center/centre, "
             f"enrollment/enrolment, modeling/modelling and others) outside quotations, citations and names: {us} US, "
             f"{uk} UK. Counted -ize and -ise endings separately ({ize} and {ise}), since British English allows "
             f"both, and 'percent' against 'per cent' ({pct} and {per_cent})."]
    wrong, reasons, status = [], [], "likely"
    if target:
        status = "confirmed"
        reasons.append(f"the settings ask for {target} English")
        wrong += hits["A"][1 if target == "US" else 0]
    elif us and uk:
        target = "US" if us > uk else "UK" if uk > us else None
        if target:
            reasons.append(f"most variant spellings are {target} ({max(us, uk)} of {us + uk})")
            wrong += hits["A"][1 if target == "US" else 0]
        else:
            status = "needs_human"
            reasons.append(f"US and UK forms are equally common ({us} each)")
            wrong += hits["A"][1]
    else:
        target = "US" if us else "UK" if uk else None  # one variant throughout
    if target == "US" and ise:
        reasons.append(f"US English spells -ize words with a z, but {ise} use -ise")
        wrong += hits["IZE"][1]
    elif ize and ise:
        reasons.append(f"both -ize ({ize}) and -ise ({ise}) endings are used; British English allows either, but "
                       "not both")
        wrong += hits["IZE"][1 if ize >= ise else 0]
    if pct and per_cent:
        reasons.append(f"both 'percent' ({pct}) and 'per cent' ({per_cent}) are used")
        side = 1 if target == "US" else 0 if target == "UK" else (1 if pct >= per_cent else 0)
        wrong += hits["PCT"][side]
    if not wrong:
        venue_rule = venue_other(ctx, "language_variant")
        if venue_rule and re.search(r"\bUK\b|British", str(venue_rule.get("value")), re.I) and us >= 3 and not uk:
            b, s, e, word = hits["A"][0][0]
            quote = quote_at(b, s, e, 4, 4)
            yield ctx.finding(
                "LANG-01", "Journal uses UK spelling", "suggestion",
                f"The paper uses US spelling throughout ({us} forms such as \"{word}\"), and the venue profile records "
                f"UK English ({venue_rule.get('value')}).",
                block=b, quote=quote, status="likely", confidence="medium",
                evidence=[Evidence(type="script_output", text=", ".join(sorted({w for *_, w in hits['A'][0]}))[:300],
                                   data={"script": SCRIPT, "us": us, "uk": uk})],
                trajectory=steps,
                fix=Fix(action="investigate", detail="Switch to UK spelling if the journal requires it at this stage.",
                        resolved_when="The spelling matches the journal's variant."),
                script=SCRIPT)
        note_coverage(ctx, "LANG-01", f"{us} US and {uk} UK forms, {ize} -ize and {ise} -ise; only variant pairs on the "
                                      "built-in list are checked, not spelling or grammar in general")
        return
    order = {blk.id: i for i, blk in enumerate(pm.blocks)}
    wrong.sort(key=lambda h: (order.get(h[0].id, 0), h[1]))
    b, s, e, word = wrong[0]
    quote = quote_at(b, s, e, 4, 4)
    forms = sorted({w.lower() for *_, w in wrong})
    why = "; ".join(reasons)
    yield ctx.finding(
        "LANG-01", "US and UK spelling mixed", "minor",
        f"{why[0].upper() + why[1:]}. {len(wrong)} form{'s' if len(wrong) != 1 else ''} to change: "
        f"{', '.join(forms[:10])}{' and others' if len(forms) > 10 else ''}. Use one variant throughout.",
        block=b, quote=quote, status=status, confidence="high" if status == "confirmed" else "medium",
        related=[related(b2, quote_at(b2, s2, e2, 4, 4)) for b2, s2, e2, _ in wrong[1:7]],
        evidence=[Evidence(type="script_output",
                           text=f"US forms: {us}; UK forms: {uk}; -ize: {ize}; -ise: {ise}; percent: {pct}; "
                                f"per cent: {per_cent}; forms to change: {', '.join(forms)}"[:600],
                           data={"script": SCRIPT, "us": us, "uk": uk, "ize": ize, "ise": ise})],
        trajectory=steps + [f"Listed the {len(wrong)} forms that differ from the main variant."],
        fix=Fix(action="investigate", detail=f"Change {', '.join(forms[:6])} to the {target or 'chosen'} spelling.",
                resolved_when="All variant spellings follow one variant."),
        script=SCRIPT, extra={"us": us, "uk": uk, "ize": ize, "ise": ise, "target": target})
    note_coverage(ctx, "LANG-01", f"{us} US and {uk} UK forms, {ize} -ize and {ise} -ise; only variant pairs on the "
                                  "built-in list are checked")


# =============================================================== LANG-02 long sentences
MAX_WORDS = 45


@register("LANG-02")
def long_sentences(pm, ctx):
    n_checked = 0
    for b, skip in _texts(pm, ("abstract", "paragraph", "list_item", "footnote")):
        cites = span_list(b, crossrefs=False)
        for sent in b.sentences or []:
            n_checked += 1
            text = b.text[sent.start:sent.end]
            # citations do not count; a math expression counts as one word
            pieces, pos = [], sent.start
            for cs, ce in sorted(cites + math_spans(b.text)):
                if ce <= sent.start or cs >= sent.end:
                    continue
                pieces.append(b.text[pos:max(pos, cs)])
                if b.text[cs:cs + 1] == "$":
                    pieces.append(" x ")
                pos = max(pos, ce)
            pieces.append(b.text[pos:sent.end])
            n = word_count(" ".join(pieces))
            if n <= MAX_WORDS:
                continue
            quote = sentence_quote(b, sent.start, 30)
            yield ctx.finding(
                "LANG-02", "Overlong sentence", "minor",
                f"This sentence has {n} words, not counting citations. Sentences over {MAX_WORDS} words are hard to "
                "follow; consider splitting it.",
                block=b, quote=quote, status="confirmed", confidence="high",
                evidence=[Evidence(type="computed_result", text="sentence length",
                                   data={"formula": "words in the sentence, citations excluded, math as one word",
                                         "inputs": {"sentence": sent.id}, "output": n, "threshold": MAX_WORDS})],
                trajectory=[f"Counted the words of each sentence in {b.anchor.label()}: {n} in sentence {sent.id}."],
                fix=Fix(action="investigate", detail="Split the sentence at a natural break, such as before 'which', "
                                                     "'and' or a semicolon.",
                        resolved_when=f"No sentence in the passage is longer than {MAX_WORDS} words."),
                script=SCRIPT, extra={"words": n})
    note_coverage(ctx, "LANG-02", f"{n_checked} sentences measured; ambiguous 'this' or 'it', dangling modifiers and "
                                  "nesting are left to the reading agents")


# =============================================================== LANG-04 vague and loaded words
# 'trivially' is left out: "the constraint is trivially satisfied" is ordinary mathematical usage.
_LOADED = ["clearly", "obviously", "of course", "needless to say", "it is well known", "it is well-known",
           "it is easy to see", "undoubtedly", "unquestionably", "groundbreaking", "ground-breaking",
           "unprecedented", "revolutionary", "game-changing", "game changer", "paradigm shift"]
_HYPE = ["incredibly", "hugely", "huge", "tremendous", "tremendously", "massive", "massively", "dramatic",
         "dramatically"]
# Common words that are a problem only when overused: reported from MIN_WEAK uses on.
_WEAK = ["very", "really", "extremely", "remarkably", "basically", "actually", "totally", "interestingly"]
_INTENSIFIERS = _HYPE + _WEAK
MIN_WEAK = 3
_SIGNPOST = {"interestingly", "basically", "actually", "really", "totally"}
_VERY_ADJ = re.compile(r"\b(?:the|this|that|its|their|his|her|our)\s+$", re.I)  # "the very first": not an intensifier
_SIGNIF = re.compile(r"\b(?:significantly|significant|insignificant(?:ly)?)\b", re.I)
_STAT_CONTEXT = re.compile(
    r"\bp\s*[<=>≤≥]\s*0?\.\d|\bp-?values?\b|\bt\s*[=(]|\bz\s*=|\bF\s*\(|χ|chi-?squared?|\bstatistical(?:ly)?\b|"
    r"\bat (?:the )?\d+(?:\.\d+)?\s*(?:%|percent|per cent) (?:level|significance)|\b\d+(?:\.\d+)?\s*(?:%|percent) level|"
    r"\bstandard errors?\b|\bconfidence intervals?\b|\*{1,3}|\bWilcoxon|\bMann-Whitney|\brank-?sum|\bt-?tests?\b|"
    r"\bregression|\bcoefficients?\b|\bestimates?\b|\bcolumns? \(?\d|\btest(?:s|ed)?\b|\bq-values?\b|"
    r"\bsignificance\b|\bnull\b", re.I)


def _stat_nearby(b, s0: int, e0: int) -> bool:
    spans = [(s.start, s.end) for s in b.sentences] or [(s0, e0)]
    idx = next((i for i, (s, e) in enumerate(spans) if s <= s0 < e), 0)
    lo = spans[max(0, idx - 1)][0]
    hi = spans[min(len(spans) - 1, idx + 1)][1]
    window_text = b.text[lo:hi]
    if _STAT_CONTEXT.search(window_text):
        return True
    for r in b.crossrefs:
        if lo <= r.start < hi:
            return True
    return bool(re.search(r"\b(?:Table|Figure|Panel)\s+[A-Z]?\d", window_text))


@register("LANG-04")
def vague_words(pm, ctx):
    texts = _texts(pm, ("abstract", "paragraph", "list_item", "footnote"))
    groups = defaultdict(list)
    for b, skip in texts:
        for word in _LOADED + _INTENSIFIERS:
            for m in re.finditer(rf"\b{re.escape(word)}\b", b.text, re.I):
                if inside(m.start(), skip) or _proper(b.text, m.start()) and word not in ("clearly", "obviously"):
                    continue
                if word == "very" and _VERY_ADJ.search(b.text[max(0, m.start() - 12):m.start()]):
                    continue
                groups[word.lower()].append((b, m.start(), m.end()))
    for word, hits in groups.items():
        loaded = word in _LOADED
        if word in _WEAK and len(hits) < MIN_WEAK:
            continue
        b, s, e = hits[0]
        quote = quote_at(b, s, e, 5, 5)
        yield ctx.finding(
            "LANG-04", f"{'Loaded' if loaded else 'Vague'} word: \"{word}\"", "minor" if loaded else "suggestion",
            (f"\"{word}\" asserts rather than shows" if loaded else f"\"{word}\" adds emphasis without information")
            + f" ({len(hits)} use{'s' if len(hits) != 1 else ''}). "
            + ("Let the evidence make the point, or say what makes it clear." if loaded else
               "Drop the word; the sentence says the same without it." if word in _SIGNPOST else
               "Give the magnitude instead, or drop the word."),
            block=b, quote=quote, status="likely", confidence="medium",
            related=[related(b2, quote_at(b2, s2, e2, 5, 5)) for b2, s2, e2 in hits[1:6]],
            evidence=[Evidence(type="script_output", text=f"\"{word}\": {len(hits)}", data={"script": SCRIPT})],
            trajectory=["Searched the text, outside quotations, for a list of vague and loaded words; common "
                        f"intensifiers such as 'very' are reported only from {MIN_WEAK} uses on.",
                        f"\"{word}\" occurs {len(hits)} time(s); the first is at {b.anchor.label()}."],
            fix=Fix(action="investigate", detail=f"Rewrite without \"{word}\", stating the size or the evidence.",
                    resolved_when=f"\"{word}\" is gone, or each use is backed by the evidence it refers to."),
            script=SCRIPT, extra={"word": word, "count": len(hits)})
    for b, skip in texts:
        if b.kind == "abstract":
            continue  # abstracts summarize results tested in the body
        for m in _SIGNIF.finditer(b.text):
            if inside(m.start(), skip):
                continue
            s0, e0 = sentence_bounds(b, m.start())
            if _stat_nearby(b, s0, e0):
                continue
            quote = sentence_quote(b, m.start(), 35)
            yield ctx.finding(
                "LANG-04", f"\"{m.group(0)}\" without a statistical test", "minor",
                f"\"{m.group(0)}\" has no test statistic, p-value, standard error or table reference in its sentence or "
                "the sentences around it. In economics it reads as statistical significance; if that is meant, give "
                "the test, and if not, use a word such as \"substantial\" and give the size.",
                block=b, quote=quote, status="likely", confidence="medium",
                evidence=[Evidence(type="quote", text=quote, block=b.id),
                          Evidence(type="checked_absence", text="statistical context",
                                   data={"scope": "the sentence and its neighbours",
                                         "terms": {"p-value|test statistic|standard error|stars|table": 0}})],
                trajectory=["Found 'significant(ly)' and searched the sentence before, the sentence itself and the "
                            "sentence after for a test, p-value, standard error, star or table reference: none."],
                fix=Fix(action="investigate", detail="Report the test, or replace the word.",
                        resolved_when="Every 'significant' either refers to a reported test or is replaced."),
                script=SCRIPT, extra={"word": m.group(0)})


# =============================================================== LANG-07 inclusive language
_INCLUSIVE = [
    (r"mankind", "humankind or humanity"),
    (r"man-?made", "artificial or human-made"),
    (r"manpower", "workforce or staff"),
    (r"chairm[ae]n", "chair or chairperson"),
    (r"businessm[ae]n", "businesspeople or executives"),
    (r"policem[ae]n", "police officers"),
    (r"firem[ae]n", "firefighters"),
    (r"salesm[ae]n", "salespeople"),
    (r"congressm[ae]n", "members of Congress"),
    (r"forefathers", "ancestors or predecessors"),
    (r"the elderly", "older adults"),
    (r"(?:the )?handicapped", "people with disabilities"),
    (r"wheelchair-bound|confined to a wheelchair", "wheelchair users"),
    (r"illegal (?:aliens?|immigrants?)", "undocumented immigrants"),
    (r"third[- ]world(?: countries| nations)?", "low- and middle-income countries"),
    (r"(?:mentally )?retarded", "people with intellectual disabilities"),
    (r"blacklist(?:s|ed|ing)?", "blocklist"),
    (r"whitelist(?:s|ed|ing)?", "allowlist"),
]


@register("LANG-07")
def inclusive_language(pm, ctx):
    for pattern, better in _INCLUSIVE:
        pat = re.compile(rf"\b(?:{pattern})\b", re.I)
        hits = [(b, m) for b, skip in _texts(pm) for m in pat.finditer(b.text)
                if not inside(m.start(), skip) and not _proper(b.text, m.start())]
        if not hits:
            continue
        b, m = hits[0]
        quote = quote_at(b, m.start(), m.end(), 5, 5)
        yield ctx.finding(
            "LANG-07", f"Non-inclusive term: \"{m.group(0)}\"", "minor",
            f"\"{m.group(0)}\" ({len(hits)} use{'s' if len(hits) != 1 else ''}) is considered non-inclusive by most "
            f"style guides; consider \"{better}\". Keep it where it is a quotation or an official name.",
            block=b, quote=quote, status="likely", confidence="medium",
            related=[related(b2, quote_at(b2, m2.start(), m2.end(), 5, 5)) for b2, m2 in hits[1:6]],
            evidence=[Evidence(type="script_output", text=f"{m.group(0)}: {len(hits)}", data={"script": SCRIPT})],
            trajectory=["Searched the text, outside quotations and names, for a short list of non-inclusive terms."],
            fix=Fix(action="replace", original=m.group(0), replacement=better.split(" or ")[0],
                    resolved_when=f"\"{m.group(0)}\" is replaced or justified as a quotation or name."),
            script=SCRIPT, extra={"term": m.group(0).lower(), "count": len(hits)})


# =============================================================== LANG-08 filler
_FILLERS = [
    (r"in order to", "to"),
    (r"due to the fact that", "because"),
    (r"owing to the fact that", "because"),
    (r"in view of the fact that", "because"),
    (r"in spite of the fact that|despite the fact that", "although"),
    (r"it is (?:important|worth|interesting) to (?:note|mention|point out|emphasi[sz]e|stress) that", ""),
    (r"it should be (?:noted|mentioned|pointed out|emphasi[sz]ed|stressed) that", ""),
    (r"it is worth (?:noting|mentioning|pointing out) that", ""),
    (r"at this point in time|at the present time", "now"),
    (r"for the purpose of", "for"),
    (r"in the event that", "if"),
    (r"has the ability to|have the ability to", "can"),
    (r"a (?:large|great) number of", "many"),
    (r"the (?:vast )?majority of", "most"),
    (r"first and foremost", "first"),
    (r"each and every", "each"),
    (r"take into consideration", "consider"),
    (r"with the exception of", "except"),
    (r"in close proximity to", "near"),
    (r"on an? (daily|weekly|monthly|yearly|annual|regular) basis",
     lambda m: {"regular": "regularly", "annual": "annually"}.get(m.group(1).lower(), m.group(1).lower())),
]


@register("LANG-08")
def filler(pm, ctx):
    texts = _texts(pm)
    for pattern, better in _FILLERS:
        pat = re.compile(rf"\b(?:{pattern})\b", re.I)
        hits = [(b, m) for b, skip in texts for m in pat.finditer(b.text) if not inside(m.start(), skip)]
        if not hits:
            continue
        b, m = hits[0]
        quote = quote_at(b, m.start(), m.end(), 3, 6)
        phrase = m.group(0)
        if callable(better):
            better = better(m)
        if better:
            replacement = better[0].upper() + better[1:] if phrase[:1].isupper() else better
            fix = Fix(action="replace", original=phrase, replacement=replacement,
                      resolved_when=f"\"{phrase.lower()}\" no longer appears.")
            advice = f"\"{better}\" says the same"
        else:
            fix = Fix(action="delete", original=phrase, detail="Delete the phrase and start with the point itself.",
                      resolved_when=f"\"{phrase.lower()}\" no longer appears.")
            advice = "the sentence reads better without it"
        yield ctx.finding(
            "LANG-08", f"Filler: \"{phrase.lower()}\"", "suggestion",
            f"\"{phrase}\" ({len(hits)} use{'s' if len(hits) != 1 else ''}) is wordy; {advice}.",
            block=b, quote=quote, status="confirmed", confidence="high",
            related=[related(b2, quote_at(b2, m2.start(), m2.end(), 3, 6)) for b2, m2 in hits[1:6]],
            evidence=[Evidence(type="script_output", text=f"{phrase.lower()}: {len(hits)}", data={"script": SCRIPT})],
            trajectory=["Searched the text for a list of filler phrases."],
            fix=fix, script=SCRIPT, extra={"phrase": phrase.lower(), "count": len(hits)})
