"""Number and statistics checks: NUM-01 to NUM-09, and the script part of BEH-09.

NUM-01  Headline numbers in the abstract and conclusion against the body and tables.
NUM-02  Arithmetic: "from A to B, an increase of C", "k of n (x%)", parts that must
        add up to 100% or to a total row.
NUM-03  Regression tables: stars against coefficient and standard error with
        rounding intervals, confidence intervals against b +/- 1.96 SE, impossible
        statistics. Text: t, F, chi-square, z, r and Mann-Whitney reports, and
        "coefficient (standard error) ... significant at the X% level".
NUM-04  GRIM, DEBIT, standard-deviation bounds, and GRIMMER as a cautious flag.
NUM-05  Sample sizes in the text against each other and against "Observations"
        rows; participant-flow arithmetic.
NUM-06  Numbers in sentences that cite "Table k" against Table k; claimed best values.
NUM-07  False precision, impossible shares, proportions reported as percentage points,
        unit conversions.
NUM-08  "Significant" claims against p-values, intervals and table estimates.
NUM-09  Percent versus percentage points; log-outcome coefficients read as percentages.
BEH-09  Table notes state the type of standard errors and the clustering, and the
        clustering is not finer than the unit of assignment.

False-positive policy, which every check follows:
  - Every printed number stands for its rounding interval, and every bound is
    closed. A check fails only when no value that rounds to the printed numbers
    makes the printed claim true.
  - Years, section, table, column and equation numbers, numbers inside
    citations and cross-references, and column headers such as (1) are never
    results. Sentences with citations are not treated as the paper's own results.
  - When an assumption decides the verdict (default star thresholds, what the
    parentheses hold, degrees of freedom, items in a scale), the check either
    tries every common alternative or lowers the status, and says so.
  - Status is confirmed only when the arithmetic is unambiguous.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from . import register
from . import stats as st
from ..model import Block, Evidence, Fix
from ..textutil import find_quote, split_sentences

SCRIPT = "checks/numbers.py"
TEXT_KINDS = {"abstract", "paragraph", "list_item", "footnote", "caption", "other"}
MASK = "\u25ca"

# ================================================================ shared patterns
_NUM = r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
_UNIT = r"(?:\s?%|\s?percentage\s+points?\b|\s?percent\b|\s?per\s+cent\b|\s?pp\b|\s?p\.p\.)"
_QUAL = (r"(?:about|approximately|around|roughly|nearly|almost|over|more\s+than|less\s+than|fewer\s+than|"
         r"at\s+least|at\s+most|up\s+to|some|close\s+to|under|below|above)")
_PEOPLE = (r"participants?|subjects?|respondents?|employees?|workers?|individuals?|students?|households?|people|"
           r"persons?|customers?|users?|players?|patients?|children|adults?|consumers?|clients?|farmers?|teachers?|"
           r"volunteers?|members?|investors?|voters?|donors?|applicants?|borrowers?|savers?|couples?|families|"
           r"pupils?|women|men|mothers?|fathers?|traders?|managers?|entrepreneurs?")
_COUNT_NOUNS = (_PEOPLE + r"|firms?|villages?|schools?|classes|classrooms?|sessions?|groups?|teams?|observations?|"
                r"cases?|trials?|decisions?|choices?|rounds?|periods?|items?|questions?|countries|states|cities|"
                r"districts?|days?|weeks?|months?|years?|hours?|minutes?|seconds?|points?|tokens?|games?|tasks?|"
                r"pairs?|dyads?|clusters?|markets?|stores?|branches|banks?|loans?|accounts?|contracts?|offers?")
_PERSON_GROUP = {
    "employee": "employees", "worker": "employees", "participant": "participants", "subject": "participants",
    "respondent": "participants", "individual": "participants", "volunteer": "participants",
    "people": "participants", "person": "participants", "student": "students", "pupil": "students",
    "household": "households", "customer": "customers", "client": "customers", "user": "users",
    "player": "participants", "patient": "patients", "farmer": "farmers", "teacher": "teachers",
}
_LABEL_WORDS = (r"[Tt]ables?|[Ff]igures?|[Ff]igs?\.|[Ss]ections?|[Ss]ecs?\.|[Aa]ppendix|[Aa]ppendices|[Cc]olumns?|"
                r"[Cc]ols?\.|[Pp]anels?|[Ee]quations?|[Ee]qs?\.|[Ss]pecifications?|[Hh]ypothes[ie]s|[Pp]ropositions?|"
                r"[Ll]emmas?|[Tt]heorems?|[Cc]orollar(?:y|ies)|[Aa]ssumptions?|[Dd]efinitions?|[Ff]ootnotes?|"
                r"[Cc]hapters?|[Pp]ages?|pp?\.|[Nn]os?\.|TABLES?|FIGURES?|"
                # ambiguous words count as labels only when capitalized: "Study 2", not "we study 400"
                r"Stud(?:y|ies)|Experiments?|Waves?|Rounds?|Periods?|Models?|Treatments?|Arms?|Conditions?|"
                r"Sessions?|Blocks?|Games?|Tasks?|Phases?|Versions?|Regressions?|Rows?|Lines?|Days?|Weeks?|Months?|"
                r"Grades?|Types?|Cohorts?|Batch(?:es)?|Trials?|Parts?|Steps?|Stages?|Items?|Questions?|Q|Stata|"
                r"Python|R|oTree|z-Tree|zTree")
_LABEL_BEFORE = re.compile(rf"\b(?:{_LABEL_WORDS})\s*\(?\s*(?:[A-Z]?\d+(?:\.\d+)*[a-z]?\)?\s*(?:,|and|or|to|-|&)\s*\(?\s*)*$")
_TABLE_REF = re.compile(r"\bTables?\s+(?P<n>[A-Z]?\d+(?:\.\d+)?)(?P<more>(?:\s*(?:,|and|&|-|to)\s*[A-Z]?\d+(?:\.\d+)?)*)")
_AUTHOR_YEAR = re.compile(r"\b[A-Z][A-Za-z'\u2019-]+(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][A-Za-z'\u2019-]+)?,?\s*\(?(?:19|20)\d{2}[a-z]?\)")

_STOP = set("""a an the of in on at by for with to from and or that this these those is are was were be been being
as it its their our we us who which whose than then there here into over under per via also only not no more most
less least very can could may might will would should shall do does did done has have had about after before
between both each either few many much other same such some any all relative compared versus while when where
group groups percent percentage points point""".split())
_SYN = {"nothing": "zero", "none": "zero", "zeros": "zero", "savings": "saving", "saved": "saving", "save": "saving"}


def _stems(text: str) -> set:
    out = set()
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if w in _STOP or len(w) < 3:
            continue
        out.add(_SYN.get(w, w)[:6])
    return out


def _similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _canon_unit(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.strip().lower()
    if not u:
        return None
    if "point" in u or u in ("pp", "p.p."):
        return "pp"
    return "%"


# ================================================================ text normalization
_NORM_PATTERNS = [
    ("sci", r"(?<=\d)\s*(?:\\times|\u00d7)\s*10\s*\^\s*\{?\s*(?P<exp>[-\u2212]?\d+)\s*\}?"),
    ("chi", r"\\chi\s*\^\s*\{?\s*2\s*\}?|\\chi_?\{?2\}?|\u03c7\s*\^?\s*\{?\s*2\s*\}?|\u03c7\u00b2"),
    ("le", r"\\leq?(?![a-zA-Z])|\\leqslant|\u2264|&lt;="),
    ("ge", r"\\geq?(?![a-zA-Z])|\\geqslant|\u2265|&gt;="),
    ("lt", r"\\lt(?![a-zA-Z])|&lt;"),
    ("gt", r"\\gt(?![a-zA-Z])|&gt;"),
    ("approx", r"\\approx(?![a-zA-Z])|\u2248|\u223c"),
    ("pct", r"\\%"),
    ("beta", r"\\hat\{\\beta\}|\\hat\\beta|\\beta(?![a-zA-Z])"),
    ("txt", r"\\(?:text|mathrm|mathit|textit|textrm|mbox|textnormal|operatorname|textbf|mathbf|emph|textsc)\s*\{"),
    ("thin", r"\\[,;:! ]"),
    ("cur", r"\\\$"),
    ("cmd", r"\\[a-zA-Z]+"),
    ("thou", r"\{,\}"),
    ("drop", r"[{}$^]"),
    ("dash", r"[\u2212\u2013\u2014\u2012\ufe63\uff0d]"),
    ("space", r"[\u00a0\u2009\u202f\u2007]"),
]
_NORM_RE = re.compile("|".join(f"(?P<{n}>{p})" for n, p in _NORM_PATTERNS))
# In Word and PDF text "$" is a currency sign, not a LaTeX math delimiter, so it is kept.
_NORM_RE_PLAIN = re.compile("|".join(f"(?P<{n}>{p if n != 'drop' else r'[{}^]'})" for n, p in _NORM_PATTERNS))
_NORM_REPL = {"chi": "\u03c72", "le": "\u2264", "ge": "\u2265", "lt": "<", "gt": ">", "approx": "\u2248", "pct": "%",
              "beta": "\u03b2", "txt": "", "thin": " ", "cur": "$", "cmd": " ", "thou": ",", "drop": "", "dash": "-",
              "space": " "}
_NORM_NAMES = [n for n, _ in _NORM_PATTERNS]


def normalize_math(text: str, latex: bool = True) -> tuple:
    """Plain analysis text, plus maps from each output character to the source span.

    LaTeX math is reduced (``$t(28) = 2.20$`` becomes ``t(28) = 2.20``) so that
    patterns can match; the maps turn a match back into verbatim source text. For
    Word and PDF input (latex=False) a "$" is a currency sign and stays."""
    out, starts, ends = [], [], []
    pos = 0
    for m in (_NORM_RE if latex else _NORM_RE_PLAIN).finditer(text):
        for k in range(pos, m.start()):
            out.append(text[k])
            starts.append(k)
            ends.append(k + 1)
        name = next(n for n in _NORM_NAMES if m.group(n) is not None)
        rep = "e" + m.group("exp").replace("\u2212", "-") if name == "sci" else _NORM_REPL[name]
        for ch in rep:
            out.append(ch)
            starts.append(m.start())
            ends.append(m.end())
        pos = m.end()
    for k in range(pos, len(text)):
        out.append(text[k])
        starts.append(k)
        ends.append(k + 1)
    return "".join(out), starts, ends


# ================================================================ sentences and number tokens
@dataclass
class Tok:
    s: int
    e: int
    raw: str
    rep: st.Reported
    unit: Optional[str]
    kind: str = "result"
    cur: Optional[str] = None

    @property
    def value(self) -> float:
        return self.rep.value

    def text(self) -> str:
        return self.raw + ("%" if self.unit == "%" else " pp" if self.unit == "pp" else "")


@dataclass
class Sent:
    block: Block
    start: int
    end: int
    norm: str
    starts: list
    ends: list
    role: str
    has_citation: bool
    sid: str
    table_refs: list = field(default_factory=list)
    tokens: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.block.text[self.start:self.end]

    def span(self, s: int, e: int) -> tuple:
        s = max(0, min(s, len(self.starts) - 1))
        e = max(s + 1, min(e, len(self.ends)))
        return self.start + self.starts[s], self.start + self.ends[e - 1]

    def quote(self, s: Optional[int] = None, e: Optional[int] = None) -> str:
        """Verbatim text of norm[s:e] (the whole sentence by default), extended to close a
        parenthesis it opens, such as "0.12 (SE 0.08; p < 0.05)"."""
        if s is None:
            return self.block.text[self.start:self.end].strip()
        seg = self.norm[s:e]
        while e < len(self.norm) and seg.count("(") > seg.count(")"):
            nxt = self.norm.find(")", e)
            if nxt < 0 or nxt - e > 40:
                break
            e = nxt + 1
            seg = self.norm[s:e]
        a, b = self.span(s, e)
        return self.block.text[a:b].strip()

    def clause(self, s: int, e: int) -> str:
        """Verbatim clause around norm[s:e], between ", " or "; " boundaries, so that several
        findings in one sentence get different quotes (the report merges identical ones)."""
        left = max(self.norm.rfind(", ", 0, s), self.norm.rfind("; ", 0, s), self.norm.rfind(": ", 0, s))
        left = left + 2 if left >= 0 else 0
        rights = [x for x in (self.norm.find(", ", e), self.norm.find("; ", e), self.norm.find(": ", e)) if x >= 0]
        right = min(rights) if rights else len(self.norm)
        return self.quote(left, right).rstrip(".")

    def where(self) -> str:
        if self.role == "abstract":
            return "the abstract"
        sec = self.block.section[-1] if self.block.section else ""
        return f"section {sec}" if sec else self.block.anchor.label()


_TOKEN = re.compile(r"(?<![\w.,\u25ca])(?P<cur>[$\u20ac\u00a3]\s?)?(?P<num>[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+))"
                    rf"(?![\d])(?P<unit>{_UNIT})?")
_COUNT_AFTER = re.compile(rf"^\s+(?:[A-Za-z][\w-]*\s+){{0,3}}?(?:{_COUNT_NOUNS})\b", re.I)
_P_BEFORE = re.compile(r"(?<![\w.])p\s*(?:[-\s]?values?)?\s*(?:[<>=\u2264\u2265]|of|is|was|equals)\s*$", re.I)
_STAT_BEFORE = re.compile(r"(?<![\w.])(?:t|z|F|\u03c72|chi2|r|U|W|R2)\s*(?:\([^)]*\))?\s*[<>=\u2264\u2265]\s*$")
_DF_BEFORE = re.compile(r"(?<![\w.])(?:t|F|\u03c72|chi2|chi-squared?|r)\s*\(\s*(?:\d+(?:\.\d+)?\s*,\s*)?$", re.I)
_N_BEFORE = re.compile(r"\b[Nn]\s*=\s*$")
_LEVEL_AFTER = re.compile(r"^\s*(?:-?\s*(?:significance\s+)?level|(?:confidence|credible)\b|CI\b|significance\b)", re.I)


def _classify(norm: str, m: re.Match, unit: Optional[str], rep: st.Reported) -> str:
    before = norm[max(0, m.start() - 60):m.start()]
    after = norm[m.end():m.end() + 60]
    integer = rep.decimals == 0 and rep.exponent == 0
    if m.group("cur"):
        return "money"
    if _P_BEFORE.search(before):
        return "p"
    if _DF_BEFORE.search(before):
        return "df"
    if _STAT_BEFORE.search(before):
        return "stat"
    if unit == "%" and _LEVEL_AFTER.match(after):
        return "level"
    if re.match(r"^\s*(?:significance\s+)?level\b", after) or re.search(r"(?:\u03b1|alpha)\s*=\s*$", before):
        return "level"
    if re.search(r"\bat\s+(?:the\s+)?$", before) and unit == "%" and re.match(r"^\s*(?:-?\s*level|or\s+(?:better|lower))", after):
        return "level"
    if unit is None and _LABEL_BEFORE.search(before):
        return "label"
    if integer and unit is None and re.search(r"\(\s*$", before) and re.match(r"^\s*\)", after):
        return "label"
    if re.match(r"^(?:\([a-z]\)|[A-Za-z])", after) and unit is None:
        return "other"  # 401(k), 2SLS, 1st, 3rd
    if unit is None and re.match(r"^-[A-Za-z]", after):
        return "descriptor"  # 5-point, 18-year-old
    if integer and unit is None and 1800 <= rep.value <= 2100 and not _COUNT_AFTER.match(after):
        return "year"
    if _N_BEFORE.search(before):
        return "count"
    if integer and unit is None and _COUNT_AFTER.match(after):
        return "count"
    return "result"


def _tokens(norm: str) -> list:
    out = []
    for m in _TOKEN.finditer(norm):
        rep = st.reported(m.group("num"))
        if rep is None:
            continue
        unit = _canon_unit(m.group("unit"))
        kind = _classify(norm, m, unit, rep)
        out.append(Tok(m.start(), m.end(), m.group("num"), rep, unit, kind, (m.group("cur") or "").strip() or None))
    return out


def _role(block: Block) -> str:
    """abstract, intro, conclusion or body. A PDF or Word reader may give the abstract as a
    paragraph under an "Abstract" heading; "Summary statistics" is not a conclusion."""
    heading = (block.section[0] if block.section else "").strip().lower()
    heading = re.sub(r"^(?:[a-z]|[ivx]+|\d+(?:\.\d+)*)[.)]?\s+", "", heading)
    if block.kind == "abstract" or heading in ("abstract", "summary", "executive summary"):
        return "abstract"
    if re.match(r"introduction\b", heading):
        return "intro"
    if re.match(r"(?:conclu\w*|final\s+remarks|closing\s+remarks|summary\s+and\s+conclu\w*|discussion\s+and\s+conclu\w*)",
                heading):
        return "conclusion"
    return "body"


def _sentences(pm, table_by_label: dict, table_numbers: set) -> list:
    out = []
    latex = str((pm.source or {}).get("format") or "latex") == "latex"
    for b in pm.blocks:
        if b.kind not in TEXT_KINDS or b.attrs.get("hidden"):
            continue
        spans = [(s.start, s.end, s.id) for s in b.sentences]
        if not spans:
            spans = [(s, e, f"{b.id}.s{i}") for i, (s, e) in enumerate(split_sentences(b.text), 1)]
        role = _role(b)
        for s, e, sid in spans:
            chars = list(b.text[s:e])
            has_cit = False
            refs: list = []
            for c in b.citations:
                if c.end > s and c.start < e:
                    has_cit = True
                    for i in range(max(c.start, s), min(c.end, e)):
                        chars[i - s] = MASK
            for r in b.crossrefs:
                if r.end > s and r.start < e:
                    for lab in r.labels:
                        if lab in table_by_label:
                            refs.append(table_by_label[lab])
                    for i in range(max(r.start, s), min(r.end, e)):
                        chars[i - s] = MASK
            norm, starts, ends = normalize_math("".join(chars), latex=latex)
            for m in _TABLE_REF.finditer(norm):
                for n in [m.group("n")] + re.findall(r"[A-Z]?\d+(?:\.\d+)?", m.group("more") or ""):
                    if n in table_numbers and n not in refs:
                        refs.append(n)
            if _AUTHOR_YEAR.search(norm):
                has_cit = True
            sent = Sent(b, s, e, norm, starts, ends, role, has_cit, sid, refs)
            sent.tokens = _tokens(norm)
            out.append(sent)
    return out


# ================================================================ tables
_C_NUM = r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
_C_STARS = r"\*{1,4}|\u2020|\u2021|\u00a7|\+|#"
_CELL_PLAIN = re.compile(rf"^(?P<num>{_C_NUM})\s*(?P<pct>%)?\s*(?P<stars>{_C_STARS})?$")
_CELL_BRACK = re.compile(rf"^(?P<open>[(\[])\s*(?P<num>{_C_NUM})\s*(?P<pct>%)?\s*[)\]]\s*(?P<stars>{_C_STARS})?$")
_CELL_PAIR = re.compile(rf"^(?P<open>[(\[])\s*(?P<lo>{_C_NUM})\s*(?:,|;|\bto\b)\s*(?P<hi>{_C_NUM})\s*[)\]]$")
_CELL_COMBO = re.compile(rf"^(?P<num>{_C_NUM})\s*(?P<pct>%)?\s*(?P<stars>{_C_STARS})?\s*(?P<open>[(\[])\s*(?P<se>{_C_NUM})\s*[)\]]$")
_EMPTYISH = {"", "-", "--", "\u2014", "\u2013", "n/a", "na", ".", "\u00b7"}


@dataclass
class Cell:
    raw: str
    kind: str  # empty, num, brack, pair, combo, text
    num: Optional[st.Reported] = None
    stars: str = ""
    pct: bool = False
    bracket: str = ""
    second: Optional[st.Reported] = None


def parse_cell(raw: str) -> Cell:
    """One table cell: a number with stars, a bracketed number, an interval, both, or text."""
    t = (raw or "").translate(st._DASHES)
    t = re.sub(r"[${}\\^]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if t.lower() in _EMPTYISH:
        return Cell(raw, "empty")
    m = _CELL_PLAIN.match(t)
    if m:
        return Cell(raw, "num", st.reported(m.group("num")), m.group("stars") or "", bool(m.group("pct")))
    m = _CELL_BRACK.match(t)
    if m:
        return Cell(raw, "brack", st.reported(m.group("num")), m.group("stars") or "", bool(m.group("pct")), m.group("open"))
    m = _CELL_PAIR.match(t)
    if m:
        return Cell(raw, "pair", st.reported(m.group("lo")), "", False, m.group("open"), st.reported(m.group("hi")))
    m = _CELL_COMBO.match(t)
    if m:
        return Cell(raw, "combo", st.reported(m.group("num")), m.group("stars") or "", bool(m.group("pct")),
                    m.group("open"), st.reported(m.group("se")))
    return Cell(raw, "text")


_STAT_LABELS = [
    ("observations", r"(?:observations|obs\.?|no\.?\s+of\s+obs(?:ervations)?\.?|number\s+of\s+observations|n|"
                     r"n\.?\s*obs\.?|sample\s+size|#\s*obs\.?|num\.?\s+obs\.?)"),
    ("clusters", r"(?:(?:no\.?|number|#|num\.?)\s+of\s+clusters|clusters|n\.?\s*clusters|#\s*clusters|"
                 r"number\s+of\s+(?:sessions|groups|schools|villages|classes)(?:\s*\(clusters\))?)"),
    ("r2", r"(?:adj(?:usted)?\.?\s*|pseudo[\s-]*|within\s+|overall\s+|between\s+)?r\s*-?\s*(?:squared|sq\.?|2|\u00b2)"),
    ("control_mean", r"(?:control\s+(?:group\s+)?(?:mean|average)|mean\s+(?:in|of|for)\s+(?:the\s+)?control(?:\s+group)?|"
                     r"control\s+mean\s+of\s+(?:the\s+)?dep(?:endent)?\.?\s*var(?:iable)?\.?|"
                     r"mean\s+of\s+(?:the\s+)?dep(?:endent)?\.?\s*var(?:iable)?\.?(?:\s*\(control(?:\s+group)?\))?|"
                     r"dep(?:endent)?\.?\s*var(?:iable)?\.?\s+mean|mean\s+dep\.?\s*var\.?|baseline\s+mean|"
                     r"outcome\s+mean|mean\s+of\s+(?:the\s+)?outcome|y\s+mean|control\s+mean\s+\(.*\))"),
    ("other", r"(?:f[\s-]*stat(?:istic)?.*|f[\s-]*test.*|p[\s-]*values?.*|controls?.*|.*fixed\s+effects?.*|.*\bfe\b.*|"
              r"log[\s-]*likelihood|aic|bic|rmse|mean|sd|s\.d\.|std\.?\s*dev\.?|wald.*|hansen.*|kleibergen.*|"
              r"first[\s-]*stage.*|sample|estimator|method|.*cluster.*|.*\bmean\b.*|.*\bmedian\b.*|weights?)"),
]
_STAT_RES = [(k, re.compile(rf"^{p}$", re.I)) for k, p in _STAT_LABELS]
_TREATMENT_LABEL = re.compile(r"treat|nudge|default|intervention|program|offer|incentive|reminder|information|"
                              r"enrol|assigned|arm\b|condition", re.I)
_TOTAL_LABEL = re.compile(r"^(?:total|all|sum|overall|full\s+sample|n\s+total)$", re.I)


def _stat_kind(label: str) -> Optional[str]:
    lab = re.sub(r"\s+", " ", (label or "").strip().strip(":")).lower()
    for kind, rx in _STAT_RES:
        if rx.match(lab):
            return kind
    return None


@dataclass
class Estimate:
    row: int
    se_row: int
    col: int
    label: str
    column: str
    coef: Cell
    se: Cell
    third: Optional[Cell] = None
    panel: str = ""


@dataclass
class ParsedTable:
    table: object
    block: Optional[Block]
    number: str
    cells: list
    row_kinds: list
    columns: dict
    estimates: list
    stats: dict  # kind -> {col: Cell}
    notes: str
    thresholds: Optional[dict]
    paren: str
    paren_source: str
    bracket: str
    se_types: list
    cluster_unit: Optional[str]
    n_clusters: Optional[int]
    adjusted: list
    one_sided: bool
    ci_level: float
    has_stars: bool
    problems: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"Table {self.number}" if self.number else "a table"

    def row_quote(self, i: int, upto: Optional[int] = None) -> Optional[str]:
        """Verbatim text of row i from the table block; with upto, only through data column upto,
        so that findings on different cells of one row have different quotes."""
        if self.block is None:
            return None
        row = self.table.rows[i] if upto is None else self.table.rows[i][:upto + 2]
        for cand in (" | ".join(row).strip(), " | ".join(c for c in row if c.strip())):
            span = find_quote(cand, self.block.text) if cand else None
            if span:
                return self.block.text[span[0]:span[1]]
        for c in row:
            if c.strip():
                span = find_quote(c, self.block.text)
                if span:
                    return self.block.text[span[0]:span[1]]
        return None

    def notes_quote(self, focus: Optional[str] = None) -> Optional[str]:
        if self.block is None or not self.notes:
            return None
        text = self.notes
        if focus:
            m = re.search(focus, text, re.I)
            if m:
                start = max(text.rfind(". ", 0, m.start()) + 2, 0) if text.rfind(". ", 0, m.start()) >= 0 else 0
                end = text.find(". ", m.end())
                text = text[start:end + 1 if end >= 0 else len(text)]
        span = find_quote(text.strip(), self.block.text)
        if span:
            return self.block.text[span[0]:span[1]]
        span = find_quote(self.notes, self.block.text)
        return self.block.text[span[0]:span[1]] if span else None

    def column_values(self, kind: str, col: int) -> Optional[Cell]:
        return self.stats.get(kind, {}).get(col)


_CONTENT_WORDS = [
    ("se", r"standard\s+errors?|std\.?\s*errors?|s\.\s?e\.|\bses?\b"),
    ("t", r"\bt[\s-]*(?:stat(?:istic)?s?|values?|ratios?)\b"),
    ("z", r"\bz[\s-]*(?:stat(?:istic)?s?|values?|scores?)\b"),
    ("p", r"\bp[\s-]*values?\b"),
    ("sd", r"standard\s+deviations?|std\.?\s*dev(?:iation)?s?\.?|\bs\.\s?d\.|\bsds?\b"),
    ("ci", r"confidence\s+intervals?|\bcis?\b"),
]
_SE_TYPES = [
    ("wild bootstrap", r"wild\s+(?:cluster\s+)?(?:\w+\s+)?bootstrap"),
    ("randomization inference", r"randomi[sz]ation\s+inference|permutation\s+(?:tests?|inference|p)"),
    ("bootstrap", r"bootstrap"),
    ("clustered", r"cluster"),
    ("robust", r"\brobust\b|heteros[ck]edasticity|huber|eicker|\bwhite\b|\bhc[0-3]\b|sandwich"),
    ("HAC", r"newey|\bhac\b|autocorrelation"),
    ("spatial", r"conley|spatial(?:ly)?\s+(?:correlated|robust)"),
    ("Driscoll-Kraay", r"driscoll"),
    ("small-sample correction", r"\bcr2\b|bell[\s-]+mccaffrey|small[\s-]+sample\s+correction"),
    ("conventional", r"(?:conventional|classical|homos[ck]edastic|\bols\b|unadjusted)\s+standard\s+errors?"),
]
_ADJUSTED = re.compile(r"randomi[sz]ation\s+inference|permutation|wild\s+(?:cluster\s+)?bootstrap|bootstrap(?:ped)?\s+p|"
                       r"bonferroni|holm|romano|westfall|sharpened|q[\s-]values?|false\s+discovery|\bfdr\b|"
                       r"family[\s-]*wise|\bfwer\b|multiple\s+(?:hypothes[ie]s|testing|comparisons?)|adjusted\s+p|"
                       r"list[\s,]+shaikh", re.I)
_ONE_SIDED = re.compile(r"one[\s-]+(?:sided|tailed)|directional\s+(?:test|hypothes)", re.I)
_UNITS_RANK = [
    (1, r"individuals?|subjects?|participants?|persons?|respondents?|employees?|workers?|students?|players?|"
        r"children|patients?|customers?|users?|people|person|id|pupils?|farmers?|teachers?|investors?|borrowers?"),
    (2, r"pairs?|dyads?|couples?"),
    (3, r"(?:matching\s+)?groups?|teams?|households?|famil(?:y|ies)|markets?\s+groups?"),
    (4, r"class(?:es)?|classrooms?"),
    (5, r"(?:lab(?:oratory)?\s+)?sessions?|days?|dates?|waves?"),
    (6, r"schools?|villages?|firms?|branch(?:es)?|stores?|clinics?|establishments?|plants?|departments?|"
        r"companies|company|banks?|offices?|neighbou?rhoods?|communit(?:y|ies)"),
    (7, r"districts?|count(?:y|ies)|municipalit(?:y|ies)|regions?|states?|countr(?:y|ies)|markets?|cities|city|"
        r"provinces?|zip\s+codes?"),
]


def _unit_rank(text: str) -> Optional[tuple]:
    t = (text or "").strip().lower()
    for rank, pat in _UNITS_RANK:
        m = re.search(rf"\b(?:{pat})\b", t)
        if m:
            return rank, m.group(0)
    return None


def _content_of(notes: str, where: str) -> tuple:
    """What the parentheses (or brackets) hold, read from the note: se, t, z, p, sd, ci or None."""
    n = notes.lower()
    hits = []
    for m in re.finditer(where, n):
        clause_start = max(n.rfind(". ", 0, m.start()), n.rfind(";", 0, m.start()), -1) + 1
        clause_end = min([x for x in (n.find(". ", m.end()), n.find(";", m.end())) if x >= 0] or [len(n)])
        before = n[clause_start:m.start()]
        after = n[m.end():clause_end]
        best = None
        for kind, pat in _CONTENT_WORDS:
            for mm in re.finditer(pat, before):
                pos = mm.start()
                if best is None or pos > best[0]:
                    best = (pos, kind)
        if best is None:
            for kind, pat in _CONTENT_WORDS:
                mm = re.search(pat, after)
                if mm and (best is None or mm.start() < best[0]):
                    best = (mm.start(), kind)
        if best:
            hits.append(best[1])
    return (hits[0], "table note") if hits else (None, "")


def _parse_notes(notes: str) -> dict:
    n = st.clean_note(notes)
    low = n.lower()
    paren, src = _content_of(n, r"parenthes[ie]s|\(\s*in\s+parenthes")
    bracket, _ = _content_of(n, r"(?:square\s+)?brackets")
    if paren is None and "parenthes" not in low:
        if re.search(_CONTENT_WORDS[0][1], low):
            paren, src = "se", "assumed: the note mentions standard errors but not where they are"
    if paren is None:
        paren, src = "se", "assumed: the economics convention, since the note does not say what the parentheses hold"
    types = [name for name, pat in _SE_TYPES if re.search(pat, low)]
    unit = None
    m = re.search(r"cluster(?:ed|ing)?(?:[\s-]+robust)?(?:\s+(?:standard\s+errors?|ses?))?(?:\s+are)?\s+(?:at|by|on|over|within)\s+"
                  r"(?:the\s+)?(?P<u>[a-z][a-z\s-]{1,40}?)(?:[\s-]+level|\s+and\b|[.,;)]|$)", low)
    if m is None:
        m = re.search(r"(?P<u>[a-z][a-z-]*(?:\s+[a-z-]+)?)[\s-]+level\s+(?:clustered|cluster)", low)
    if m is None:
        m = re.search(r"clustered\s+(?:standard\s+errors?\s+)?\(?(?:by\s+)?(?P<u>[a-z]+)\)?", low) if "cluster" in low else None
    if m is not None:
        unit = m.group("u").strip()
    g = None
    mg = re.search(r"(?P<g>\d[\d,]*)\s+clusters|clusters?\s*(?:=|:|is|of)\s*(?P<g2>\d[\d,]*)", low)
    if mg:
        g = int((mg.group("g") or mg.group("g2")).replace(",", ""))
    level = 0.95
    ml = re.search(r"(?P<l>9\d(?:\.\d+)?)\s*%?\s*(?:percent\s+)?confidence", low)
    if ml:
        level = float(ml.group("l")) / 100
    return {"thresholds": st.parse_star_thresholds(notes), "paren": paren, "paren_source": src,
            "bracket": bracket, "se_types": types, "cluster_unit": unit, "n_clusters": g,
            "adjusted": sorted({mm.group(0) for mm in _ADJUSTED.finditer(n)}), "one_sided": bool(_ONE_SIDED.search(n)),
            "ci_level": level}


def _consecutive(nums: list) -> bool:
    return len(nums) >= 2 and all(b == a + 1 for a, b in zip(nums, nums[1:]))


def parse_table(table, block: Optional[Block]) -> ParsedTable:
    """Parse a table into estimates (coefficient row followed by a bracketed row), summary rows
    (observations, clusters, R squared, control mean), column labels and what the note says."""
    rows = [list(r) for r in (table.rows or [])]
    notes = table.notes or ""
    cells = [[parse_cell(c) for c in r[1:]] for r in rows]
    kinds = []
    seen_values = False
    for i, r in enumerate(rows):
        label = (r[0] if r else "").strip()
        data = cells[i]
        nonempty = [c for c in data if c.kind != "empty"]
        stat = _stat_kind(label) if label else None
        if not nonempty and re.match(r"^(?:notes?|sources?)\b", label, re.I):
            kinds.append("notes")  # a note that a PDF or Word reader left inside the rows
            if label not in notes:
                notes = (notes + " " + label).strip()
            continue
        if not nonempty:
            kinds.append("label" if label else "empty")
            continue
        if stat:
            kinds.append("stat:" + stat)
            seen_values = True
            continue
        if all(c.kind == "text" for c in nonempty):
            kinds.append("text" if seen_values else "header")
            continue
        ints = [int(c.num.value) for c in nonempty if c.kind == "brack" and c.num and c.num.decimals == 0]
        header_area = not seen_values
        if (len(ints) == len(nonempty) and not label and (_consecutive(ints) or (header_area and len(ints) == 1))
                and (header_area or (i > 0 and kinds[-1] not in ("values",)))):
            kinds.append("colnums")
            continue
        if all(c.kind in ("brack", "pair") for c in nonempty):
            kinds.append("brackets")
            continue
        if all(c.kind in ("num", "combo", "text") for c in nonempty) and any(c.kind in ("num", "combo") for c in nonempty):
            kinds.append("values")
            seen_values = True
            continue
        kinds.append("mixed")
        seen_values = True
    first_data = next((i for i, k in enumerate(kinds) if k in ("values", "brackets", "mixed") or k.startswith("stat:")), len(rows))
    ncols = max((len(r) for r in rows), default=0)
    columns = {}
    for j in range(1, ncols):
        parts = []
        for i in range(first_data):
            if kinds[i] in ("header", "colnums", "text", "label") and j < len(rows[i]):
                cell = rows[i][j].strip()
                if not cell and kinds[i] in ("header", "text"):
                    k = j - 1  # a spanning header sits in the first spanned column
                    while k >= 1 and k < len(rows[i]) and not rows[i][k].strip():
                        k -= 1
                    if k >= 1 and sum(1 for c in rows[i][1:] if c.strip()) < ncols - 1:
                        cell = rows[i][k].strip()
                if cell and cell not in parts:
                    parts.append(cell)
        columns[j - 1] = " ".join(parts)
    estimates = []
    stats_rows: dict = {}
    panel = ""
    i = 0
    while i < len(rows):
        kind = kinds[i]
        label = (rows[i][0] if rows[i] else "").strip()
        if kind == "label" and label:
            panel = label
        if kind.startswith("stat:"):
            stats_rows.setdefault(kind[5:], {})
            for j, c in enumerate(cells[i]):
                if c.kind != "empty":
                    stats_rows[kind[5:]].setdefault(j, c)
        if kind == "values" and i + 1 < len(rows) and kinds[i + 1] == "brackets" and not (rows[i + 1][0] or "").strip():
            third = i + 2 if i + 2 < len(rows) and kinds[i + 2] == "brackets" and not (rows[i + 2][0] or "").strip() else None
            for j, c in enumerate(cells[i]):
                if c.kind != "num" or j >= len(cells[i + 1]):
                    continue
                se = cells[i + 1][j]
                if se.kind not in ("brack", "pair"):
                    continue
                t3 = cells[third][j] if third is not None and j < len(cells[third]) else None
                if se.stars and not c.stars:
                    c.stars = se.stars
                estimates.append(Estimate(i, i + 1, j, label, columns.get(j, ""), c, se, t3, panel))
            i = (third or i + 1) + 1
            continue
        if kind == "values":
            for j, c in enumerate(cells[i]):
                if c.kind == "combo":
                    se = Cell(c.raw, "brack", c.second, "", False, "(")
                    estimates.append(Estimate(i, i, j, label, columns.get(j, ""), c, se, None, panel))
        i += 1
    info = _parse_notes(notes)
    has_stars = any(c.stars for r in cells for c in r if c.kind in ("num", "combo", "brack")) or any(
        re.search(r"\d\s*(?:\^\{?)?(?:\*{1,4}|\\dagger)", c) for r in rows for c in r[1:])
    number = str(table.number or "")
    return ParsedTable(table, block, number, cells, kinds, columns, estimates, stats_rows, notes,
                       info["thresholds"], info["paren"], info["paren_source"], info["bracket"], info["se_types"],
                       info["cluster_unit"], info["n_clusters"], info["adjusted"], info["one_sided"], info["ci_level"],
                       has_stars)


# ================================================================ statements found in the text
@dataclass
class Change:
    sent: Sent
    a: Tok
    b: Tok
    a_ctx: str
    b_ctx: str
    direction: Optional[str]
    span: tuple
    c: Optional[Tok] = None
    c_dir: Optional[str] = None
    c_qual: Optional[str] = None
    c_span: Optional[tuple] = None
    multiplier: Optional[float] = None


_DIRS = [("up", r"increas|ris|rose|grew|grow|gain|jump|boost|improv|rais|higher|more|climb|doubl|tripl|quadrupl|expand"),
         ("down", r"declin|decreas|drop|fell|fall|reduc|cut|lower|less|fewer|shrank|shrink|halv|dip|slid|contract")]


def _direction(word: Optional[str]) -> Optional[str]:
    w = (word or "").lower()
    for d, pat in _DIRS:
        if re.match(pat, w):
            return d
    return None


_FROM_TO = re.compile(rf"\bfrom\s+(?:{_QUAL}\s+)?(?P<a>(?:[$\u20ac\u00a3]\s?)?{_NUM})(?P<au>{_UNIT})?(?P<actx>[^\d;:]{{0,80}}?)"
                      rf"\bto\s+(?:{_QUAL}\s+)?(?P<b>(?:[$\u20ac\u00a3]\s?)?{_NUM})(?P<bu>{_UNIT})?", re.I)
_PRE_VERB = re.compile(r"\b(?P<v>increas\w*|ris\w*|rose|grew|grow\w*|gain\w*|jump\w*|boost\w*|improv\w*|rais\w*|climb\w*|"
                       r"declin\w*|decreas\w*|drop\w*|fell|fall\w*|reduc\w*|cut\w*|lower\w*|shrank|shrink\w*|went|"
                       r"moved?|chang\w*|shift\w*|doubl\w*|tripl\w*|halv\w*)\b[^.;]*$", re.I)
_RANGE_BEFORE = re.compile(r"\b(?:rang\w*|var(?:y|ies|ied|ying)|scale\w*|scored?|between|span\w*|ages?|aged)\b[^.;]{0,25}$", re.I)
_CHANGE_NOUN = re.compile(rf"\b(?P<dir>increase|rise|gain|growth|jump|boost|improvement|decrease|decline|drop|fall|"
                          rf"reduction|cut|change|difference|shift)s?\s+(?:of|by)\s+(?:(?P<q>{_QUAL})\s+)?"
                          rf"(?P<c>{_NUM})(?P<cu>{_UNIT})?", re.I)
_CHANGE_VERB = re.compile(rf"\b(?P<dir>increas|ris|rose|grew|grow|gain|jump|boost|improv|declin|decreas|drop|fell|fall|"
                          rf"reduc|cut|lower|rais|shrank|shrink)\w*\s+(?:[\w-]+\s+){{0,8}}?by\s+(?:(?P<q>{_QUAL})\s+)?"
                          rf"(?P<c>{_NUM})(?P<cu>{_UNIT})?", re.I)
_CHANGE_ADJ = re.compile(rf"(?:(?P<q>{_QUAL})\s+)?(?P<c>{_NUM})(?P<cu>{_UNIT})?\s+(?P<dir>higher|lower|more|less|fewer|"
                         rf"increase|decrease|reduction|rise|drop|decline|gain)\b", re.I)
_MULT = re.compile(r"\b(?P<m>doubl|tripl|quadrupl|halv)\w*\b|(?P<c>\d+(?:\.\d+)?)[-\s]?fold\b", re.I)
_GROUP_PAIR = re.compile(rf"(?P<a>{_NUM})(?P<au>{_UNIT})?\s+(?:in|for|among|of)\s+(?:the\s+)?(?P<ga>control|treatment|treated|"
                         rf"comparison)\b(?:\s+(?:group|arm|condition))?[^.;\d]{{0,60}}?(?P<b>{_NUM})(?P<bu>{_UNIT})?\s+"
                         rf"(?:in|for|among|of)\s+(?:the\s+)?(?P<gb>control|treatment|treated|comparison)\b", re.I)


def _tok_at(sent: Sent, s: int) -> Optional[Tok]:
    for t in sent.tokens:
        if t.s <= s < t.e or (t.s >= s and t.s - s <= 2):
            return t
    return None


def _find_changes(sents: list) -> list:
    out = []
    for sent in sents:
        norm = sent.norm
        for m in _FROM_TO.finditer(norm):
            a = _tok_at(sent, m.start("a"))
            b = _tok_at(sent, m.start("b"))
            if a is None or b is None or a is b:
                continue
            if {a.kind, b.kind} & {"year", "label", "descriptor", "other", "p", "stat", "df"}:
                continue
            before = norm[max(0, m.start() - 80):m.start()]
            if _RANGE_BEFORE.search(before[-40:]):
                continue
            pv = _PRE_VERB.search(before)
            direction = _direction(pv.group("v")) if pv else None
            ch = Change(sent, a, b, m.group("actx") or "", "", direction, (m.start(), m.end()))
            after_start = m.end()
            nxt = norm.find("from ", after_start)
            window_end = nxt if nxt > 0 else len(norm)
            ch.b_ctx = re.split(r"[,;]", norm[after_start:window_end], maxsplit=1)[0]
            best = None
            for rx in (_CHANGE_NOUN, _CHANGE_VERB, _CHANGE_ADJ):
                for cm in rx.finditer(norm):
                    if cm.start("c") in (m.start("a"), m.start("b")) or (m.start() <= cm.start("c") < m.end()):
                        continue
                    if not (cm.start() >= m.end() and cm.start() <= window_end) and not (cm.end() <= m.start() and m.start() - cm.end() <= 40):
                        continue
                    c = _tok_at(sent, cm.start("c"))
                    if c is None or c.kind in ("year", "label", "p", "stat", "df", "level"):
                        continue
                    dist = cm.start() - m.end() if cm.start() >= m.end() else m.start() - cm.end()
                    if best is None or dist < best[0]:
                        best = (dist, cm, c)
            if best:
                _, cm, c = best
                ch.c, ch.c_dir, ch.c_qual = c, _direction(cm.group("dir")), (cm.group("q") or None)
                start = cm.start()
                for art in ("an ", "a "):
                    if norm[max(0, start - len(art)):start].lower() == art:
                        start -= len(art)
                        break
                ch.c_span = (start, cm.end())
            else:
                mm = _MULT.search(norm[m.end():window_end]) or _MULT.search(before[-40:])
                if mm:
                    word = (mm.group("m") or "").lower()
                    ch.multiplier = {"doubl": 2.0, "tripl": 3.0, "quadrupl": 4.0, "halv": 0.5}.get(word) or (
                        float(mm.group("c")) if mm.group("c") else None)
            if ch.direction is None and ch.c is None and ch.multiplier is None:
                continue
            out.append(ch)
    return out


@dataclass
class TextStat:
    sent: Sent
    kind: str  # t, F, chi2, z, r, U, b_se
    span: tuple
    stat: st.Reported
    se: Optional[st.Reported] = None
    df1: Optional[float] = None
    df2: Optional[float] = None
    n: Optional[int] = None
    n1: Optional[int] = None
    n2: Optional[int] = None
    p: Optional[st.PReport] = None
    p_span: Optional[tuple] = None
    claim: Optional[dict] = None
    stat_text: str = ""
    linked: Optional[tuple] = None  # (table, estimate) for a p-value quoted next to a table coefficient


_SNUM = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
_PNUM = r"(?:\d?\.\d+(?:e-?\d+)?|[01](?:\.0+)?|\d(?:\.\d+)?e-\d+)"
_CMP = {"\u2264": "<=", "\u2265": ">=", "<=": "<=", ">=": ">=", "<": "<", ">": ">", "=": "="}
_P_RE = re.compile(rf"(?<![\w.])p\s*(?:[-\s]?values?)?\s*(?P<cmp><=|>=|\u2264|\u2265|<|>|=)\s*(?P<val>{_PNUM})(?![\d])|"
                   rf"(?<![\w.])p[-\s]values?\s+(?:of|is|was|equals)\s+(?P<val2>{_PNUM})(?![\d])", re.I)
_STAT_RES_TEXT = [
    ("t", re.compile(rf"(?<![\w.])t\s*\(\s*(?P<df>\d+(?:\.\d+)?)\s*\)\s*(?P<cmp>=|<|>|\u2264|\u2265)\s*(?P<val>{_SNUM})")),
    ("F", re.compile(rf"(?<![\w.])F\s*\(\s*(?P<df>\d+(?:\.\d+)?)\s*,\s*(?P<df2>\d+(?:\.\d+)?)\s*\)\s*(?P<cmp>=|<|>)\s*(?P<val>{_SNUM})")),
    ("chi2", re.compile(rf"(?:\u03c72|chi2|chi[-\s]?squared?)\s*\(\s*(?P<df>\d+)\s*(?:,\s*[Nn]\s*=\s*(?P<n>\d[\d,]*))?\s*\)\s*"
                        rf"(?P<cmp>=|<|>)\s*(?P<val>{_SNUM})", re.I)),
    ("r", re.compile(rf"(?<![\w.])r\s*\(\s*(?P<df>\d+)\s*\)\s*(?P<cmp>=)\s*(?P<val>{_SNUM})")),
    ("z", re.compile(rf"(?<![\w.])[zZ](?:[-\s](?:stat(?:istic)?|score|value))?\s*(?P<cmp>=)\s*(?P<val>{_SNUM})")),
    ("t0", re.compile(rf"(?<![\w.])t(?:[-\s]stat(?:istic)?s?|[-\s]values?)?\s*(?P<cmp>=)\s*(?P<val>{_SNUM})")),
    ("U", re.compile(r"(?<![\w.])U\s*(?P<cmp>=)\s*(?P<val>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")),
]
_BSE = [
    re.compile(rf"(?P<b>{_NUM})\s*(?:%|percentage\s+points?|percent|pp|p\.p\.)?\s*\(\s*(?:standard\s+error|std\.?\s*err(?:or)?\.?|"
               rf"s\.\s?e\.|SE|se)\s*(?:=|:|of|is)?\s*(?P<se>{_NUM})\s*(?:\)|[;,])"),
    re.compile(rf"(?:coefficient|estimate|effect|\u03b2|beta|\bb)\s*(?:of|is|was|=|:|equals)\s*(?P<b>{_NUM})[^.;()]{{0,60}}?"
               rf"(?:standard\s+error|s\.\s?e\.|\bSE\b)\s*(?:of|is|was|=|:)?\s*(?P<se>{_NUM})", re.I),
]
_SIG_RE = re.compile(
    r"(?P<neg>\bnot\s+(?:\w+\s+)?|\bno\s+|\bnon-?|\bin)?(?P<adv>(?:statistically|highly|marginally|weakly|strongly)\s+)?"
    r"significan(?:t|tly)\b"
    r"(?:[^.;]{0,40}?\bat\s+(?:the\s+)?(?:(?P<lvl>\d+(?:\.\d+)?)\s*(?:%|percent|per\s+cent)|(?P<lvl2>0?\.\d+)\b|"
    r"(?P<conv>conventional|standard|usual|all\s+conventional)\b)(?:\s+(?:significance\s+)?levels?\b)?)?", re.I)
_NOT_STAT_SIG = re.compile(r"(?:economically|practically|clinically|substantively|quantitatively)\s+(?:and\s+\w+\s+)?$", re.I)
_CI_RE = re.compile(rf"(?:(?P<lvl>\d+(?:\.\d+)?)\s*%\s*)?(?:confidence\s+interval|\bCI\b)\s*(?:[:=,]|is|of|was)?\s*[\[(]?\s*"
                    rf"(?P<lo>{_NUM})\s*(?:,|;|\bto\b|\s-\s)\s*(?P<hi>{_NUM})\s*[\])]?", re.I)
_CLAUSE_BREAK = re.compile(r"\d|;|\bwhile\b|\bwhereas\b|\bbut\b|\bhowever\b|\bin\s+contrast\b|\balthough\b|"
                           r"\band\s+(?:the|that|its|for|in)\b", re.I)
_CORRECTION = re.compile(r"bonferroni|holm|sidak|\u0161id\u00e1k|greenhouse|huynh|corrected|adjusted|false\s+discovery|"
                         r"\bfdr\b|benjamini|romano|westfall|q[\s-]values?|sharpened|family[\s-]*wise", re.I)


def _p_reports(sent: Sent) -> list:
    out = []
    for m in _P_RE.finditer(sent.norm):
        val = m.group("val") or m.group("val2")
        rep = st.reported(val)
        if rep is None or rep.value > 1:
            continue
        cmp = _CMP.get(m.group("cmp") or "=", "=")
        out.append((m.start(), m.end(), st.PReport(cmp, rep)))
    return out


def _claims(sent: Sent) -> list:
    out = []
    for m in _SIG_RE.finditer(sent.norm):
        if _NOT_STAT_SIG.search(sent.norm[max(0, m.start() - 40):m.start()]):
            continue
        neg = bool(m.group("neg"))
        adv = (m.group("adv") or "").strip().lower()
        level = None
        if m.group("lvl"):
            level = float(m.group("lvl")) / 100
        elif m.group("lvl2"):
            level = float(m.group("lvl2"))
        elif m.group("conv"):
            level = 0.10
        explicit = level is not None and not m.group("conv")
        if level is None:
            level = 0.05 if (neg or adv == "highly") else 0.10
        if adv in ("marginally", "weakly") and not neg:
            level = 0.10
        if not (0 < level < 0.5):
            continue
        out.append({"start": m.start(), "end": m.end(), "negative": neg, "level": level, "explicit": explicit,
                    "adverb": adv})
    return out


def _find_text_stats(sents: list) -> list:
    out = []
    for sent in sents:
        norm = sent.norm
        ps = _p_reports(sent)
        found = []
        taken = []
        for kind, rx in _STAT_RES_TEXT:
            for m in rx.finditer(norm):
                if any(a <= m.start() < b for a, b in taken):
                    continue
                if kind == "U" and not re.search(r"mann|whitney|wilcoxon|rank[\s-]sum", norm, re.I):
                    continue
                val = st.reported(m.group("val"))
                if val is None:
                    continue
                k = "t" if kind == "t0" else kind
                ts = TextStat(sent, k, (m.start(), m.end()), val, stat_text=norm[m.start():m.end()])
                gd = m.groupdict()
                if gd.get("df"):
                    ts.df1 = float(gd["df"])
                if gd.get("df2"):
                    ts.df2 = float(gd["df2"])
                if gd.get("n"):
                    ts.n = int(gd["n"].replace(",", ""))
                found.append(ts)
                taken.append((m.start(), m.end()))
        for rx in _BSE:
            for m in rx.finditer(norm):
                if any(a <= m.start("b") < b for a, b in taken):
                    continue
                b, se = st.reported(m.group("b")), st.reported(m.group("se"))
                if b is None or se is None or se.value <= 0:
                    continue
                found.append(TextStat(sent, "b_se", (m.start("b"), m.end()), b, se, stat_text=norm[m.start("b"):m.end()]))
                taken.append((m.start("b"), m.end()))
        claims = _claims(sent)
        found.sort(key=lambda t: t.span[0])
        for idx, ts in enumerate(found):
            nxt = found[idx + 1].span[0] if idx + 1 < len(found) else len(norm)
            for s, e, rep in ps:
                if ts.span[1] <= s <= ts.span[1] + 45 and s < nxt:
                    ts.p, ts.p_span = rep, (s, e)
                    break
            if ts.kind in ("z", "t") and ts.df1 is None and ts.p is None:
                ts.kind = "drop"
                continue
            if ts.kind == "U":
                m1 = re.search(r"\bn_?1\s*=\s*(\d+)", norm)
                m2 = re.search(r"\bn_?2\s*=\s*(\d+)", norm)
                mn = re.search(r"\b[Nn]\s*=\s*(\d[\d,]*)", norm)
                if m1 and m2:
                    ts.n1, ts.n2 = int(m1.group(1)), int(m2.group(1))
                elif mn:
                    ts.n = int(mn.group(1).replace(",", ""))
            if ts.kind == "b_se":
                for c in claims:
                    gap = norm[ts.span[1]:c["start"]]
                    if c["start"] >= ts.span[1] and len(gap) <= 100 and c["start"] < nxt and not _CLAUSE_BREAK.search(gap):
                        ts.claim = c
                        break
        out.extend(t for t in found if t.kind != "drop")
    return out


def _table_linked_stats(paper) -> list:
    """A p-value quoted right after a coefficient that matches exactly one table estimate,
    as in "the coefficient (0.120, p < 0.01)": checked against that estimate's standard error."""
    out = []
    regs = paper.reg_tables()
    for sent in paper.sents:
        tables = [pt for pt in paper.tables_for(sent) if pt.estimates] or (regs if len(regs) == 1 else [])
        if not tables:
            continue
        taken = [ts.span for ts in paper.text_stats if ts.sent is sent]
        for s0, e0, rep in _p_reports(sent):
            toks = [t for t in sent.tokens if t.kind == "result" and t.rep.decimals >= 2 and t.e <= s0
                    and s0 - t.e <= 30 and not any(a <= t.s < b for a, b in taken)]
            if not toks:
                continue
            tok = toks[-1]
            if re.search(r"\d", sent.norm[tok.e:s0]):
                continue
            hits = [(pt, e) for pt in tables for e in pt.estimates if e.coef.num is not None and e.se.num is not None
                    and e.se.kind == "brack" and pt.paren == "se" and abs(e.coef.num.exact) == abs(tok.rep.exact)]
            if len(hits) != 1:
                continue
            pt, est = hits[0]
            out.append(TextStat(sent, "b_se", (tok.s, tok.e), est.coef.num, est.se.num, p=rep, p_span=(s0, e0),
                                stat_text=f"{tok.raw} (with standard error {est.se.num.raw} in {pt.name})",
                                linked=(pt, est)))
    return out


# ================================================================ the paper, analysed once
class _Paper:
    def __init__(self, pm):
        self.pm = pm
        self.table_by_label = {t.label: str(t.number) for t in pm.tables if t.label and t.number}
        self.table_numbers = {str(t.number) for t in pm.tables if t.number}
        blocks = {}
        for b in pm.blocks:
            if b.kind == "table":
                tid = b.attrs.get("table_id") or b.attrs.get("float_id")
                if tid:
                    blocks[tid] = b
        self.tables = []
        used = set()
        for t in pm.tables:
            block = blocks.get(t.id)
            if block is None:
                block = next((b for b in pm.blocks if b.kind == "table" and t.caption_block and b.parent == t.caption_block), None)
            if block is None:  # a reader that does not link tables to blocks: find the block by its rows
                rows = [" | ".join(r).strip() for r in (t.rows or []) if any(c.strip() for c in r)][:3]
                block = next((b for b in pm.blocks if b.kind == "table" and b.id not in used and rows
                              and all(find_quote(r, b.text) for r in rows)), None)
            if block is not None:
                used.add(block.id)
            self.tables.append(parse_table(t, block))
        self.table_by_number = {pt.number: pt for pt in self.tables if pt.number}
        self.sents = _sentences(pm, self.table_by_label, self.table_numbers)
        self.changes = _find_changes(self.sents)
        self.text_stats = _find_text_stats(self.sents)
        self.text_stats += _table_linked_stats(self)
        self.body_text = " ".join(s.norm for s in self.sents)

    def reg_tables(self) -> list:
        return [pt for pt in self.tables if pt.estimates]

    def tables_for(self, sent: Sent) -> list:
        return [self.table_by_number[n] for n in sent.table_refs if n in self.table_by_number]


_CACHE: dict = {}


def _paper(pm) -> _Paper:
    hit = _CACHE.get(id(pm))
    if hit is not None and hit[0] is pm:
        return hit[1]
    _CACHE.clear()
    paper = _Paper(pm)
    _CACHE[id(pm)] = (pm, paper)
    return paper


# ================================================================ finding helpers
def _cr(formula: str, inputs: dict, output, tolerance: str, **more) -> Evidence:
    data = {"formula": formula, "inputs": inputs, "output": output, "tolerance": tolerance}
    data.update(more)
    return Evidence(type="computed_result", data=data)


def _rel(block: Optional[Block], quote: Optional[str]) -> Optional[dict]:
    if block is None or not quote:
        return None
    return {"quote": quote, "block": block.id}


def _emit(ctx, cid: str, title: str, severity: str, problem: str, *, block: Block, quote: str, evidence: list,
          trajectory: list, fix: Fix, status: str, confidence: str, related=None, extra=None):
    related = [r for r in (related or []) if r]
    return ctx.finding(cid, title, severity, problem, block=block, quote=quote, related=related, evidence=evidence,
                       trajectory=trajectory, fix=fix, confidence=confidence, status=status, extra=extra, script=SCRIPT)


def _verbatim(block: Block, text: str) -> Optional[str]:
    span = find_quote(text, block.text) if text else None
    return block.text[span[0]:span[1]] if span else None


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _same_number(x: st.Reported, y: st.Reported) -> bool:
    """x and y are the same printed number, or the coarser one is the finer one rounded.
    A coarse number with one significant digit (such as 1) never stands for a finer one
    two or more decimals away (such as 0.82)."""
    if x.places == y.places:
        return st.overlaps(x.abs_interval, y.abs_interval)
    fine, coarse = (x, y) if x.places > y.places else (y, x)
    if coarse.places < fine.places - 1 and _sig_digits(coarse) < 2:
        return False
    lo, hi = coarse.abs_interval
    return lo - st.EPS <= abs(fine.value) <= hi + st.EPS


def _number_matches(x: st.Reported, unit: Optional[str], y: st.Reported, y_pct: bool = False) -> bool:
    """x (from the text) and y (elsewhere) are the same number up to rounding, sign and the
    percent/share scale."""
    if _same_number(x, y):
        return True
    if unit in ("%", "pp") and not y_pct and abs(y.value) <= 1.5 and _same_number(x.scaled(-2), y):
        return True
    if unit is None and y_pct and abs(x.value) <= 1.5 and _same_number(x.scaled(2), y):
        return True
    return False


def _all_numbers(paper: _Paper, exclude_roles=(), exclude_sent=None) -> list:
    """(Reported, unit, where, block, quote-hint) for every number in text and tables."""
    out = []
    for s in paper.sents:
        if s.role in exclude_roles or s is exclude_sent:
            continue
        for t in s.tokens:
            if t.kind in ("year", "label", "other", "descriptor", "df"):
                continue
            out.append((t.rep, t.unit, s.where(), s.block, s))
    for pt in paper.tables:
        for i, row in enumerate(pt.cells):
            for c in row:
                for r in (c.num, c.second):
                    if r is not None and pt.row_kinds[i] not in ("colnums", "header"):
                        out.append((r, "%" if c.pct else None, pt.name, pt.block, pt))
    return out


def _coverage(ctx, cid: str, evaluated: int, candidates: int, what: str, na_reason: str, notes: list) -> None:
    if candidates == 0:
        ctx.not_applicable(cid, na_reason)
    elif evaluated == 0:
        ctx.skip(cid, "; ".join(notes) if notes else f"found {candidates} {what} but could not evaluate any")
    else:
        text = f"checked {evaluated} {what}"
        if notes:
            text += "; " + "; ".join(sorted(set(notes)))
        ctx.note(cid, text)


# ================================================================ NUM-03: regression tables
def _df_low(pt: ParsedTable, est: Estimate) -> tuple:
    """Lowest plausible degrees of freedom for this estimate, with a description."""
    clustered = "clustered" in pt.se_types
    g = None
    cl = pt.column_values("clusters", est.col)
    if cl is not None and cl.num is not None:
        g = int(cl.num.value)
    elif pt.n_clusters:
        g = pt.n_clusters
    if clustered:
        if g and g > 1:
            return float(g - 1), f"t({g - 1}): {g} clusters"
        return None, "clustered standard errors with an unstated number of clusters"
    obs = pt.column_values("observations", est.col)
    if obs is not None and obs.num is not None:
        k = sum(1 for e in pt.estimates if e.col == est.col) + 1
        df = int(obs.num.value) - k
        if df > 0:
            return float(df), f"t({df}): {int(obs.num.value)} observations less {k} parameters"
    return None, "no degrees of freedom stated"


_PAREN_NAMES = {"se": "standard errors", "t": "t statistics", "z": "z statistics", "p": "p-values"}


def _correct_symbol(p_rng: tuple, thresholds: dict) -> Optional[str]:
    fits = []
    for sym in [""] + sorted(thresholds, key=lambda s: -thresholds[s]):
        implied = st.implied_interval(sym, thresholds)
        if implied and st.star_verdict(p_rng, implied) == "consistent":
            fits.append(sym)
    return fits[0] if len(fits) == 1 else None


_RATIO_TABLE = re.compile(r"odds\s+ratios?|hazard\s+ratios?|incidence[\s-]+rate\s+ratios?|relative\s+risk|risk\s+ratios?|"
                          r"\birrs?\b|exponentiated|\bexp\s*\(\s*b|\bodds\b", re.I)
_STARS_OTHER_TEST = re.compile(r"(?:stars?|asterisks?|\*)[^.]{0,60}?(?:denote|indicate|show|mark|refer)[^.]{0,80}?"
                               r"(?:difference|equality|equal\s+to|relative\s+to|compared\s+(?:to|with)|"
                               r"different\s+from\s+(?!zero|0\b))", re.I)
_CONSTANT = re.compile(r"^(?:constant|intercept|_cons|const\.?)$", re.I)


def _table_star_findings(pt: ParsedTable, ctx, counts: dict, notes: list, text_clustered: bool = False):
    if not pt.has_stars:
        notes.append(f"{pt.name}: no significance marks, so stars were not checked")
        return
    if pt.paren in ("sd", "ci"):
        notes.append(f"{pt.name}: the note says the parentheses hold {pt.paren}; stars not checked")
        return
    context = " ".join([pt.table.caption or "", pt.notes or ""] + list(pt.columns.values()))
    if _RATIO_TABLE.search(context):
        notes.append(f"{pt.name}: reports ratios, which are tested against 1; stars not checked")
        return
    if _STARS_OTHER_TEST.search(pt.notes or ""):
        notes.append(f"{pt.name}: the stars mark a test other than b = 0; stars not checked")
        return
    if pt.thresholds:
        options = [(pt.thresholds, "table note")]
    else:
        options = [(st.DEFAULT_THRESHOLDS, "default 10/5/1, since the note gives no thresholds"),
                   (st.ESTTAB_THRESHOLDS, "the other common default, 5/1/0.1")]
    paren_kind = pt.paren if pt.paren in ("se", "t", "z", "p") else "se"
    # When the note does not say what the parentheses hold, a flag must hold under both readings.
    paren_kinds = [paren_kind, "t"] if pt.paren_source.startswith("assumed") and paren_kind == "se" else [paren_kind]
    starred_cols = {e.col for e in pt.estimates if e.coef.stars}
    for est in pt.estimates:
        if est.se.kind != "brack" or est.coef.num is None or est.se.num is None:
            continue
        if est.col not in starred_cols:
            continue  # a column without any marks does not use them
        df_low, df_desc = _df_low(pt, est)
        results = []
        for kind in paren_kinds:
            for th, src in options:
                res = st.check_stars(est.coef.num, est.se.num, est.coef.stars, th, kind, df_low)
                results.append((res, th, src + ("" if kind == paren_kind else f"; parentheses read as {kind}")))
        if any(r is None for r, _, _ in results):
            notes.append(f"{pt.name}: mark {est.coef.stars!r} is not defined in the note")
            continue
        counts["estimates"] += 1
        verdicts = {r.verdict for r, _, _ in results}
        if "consistent" in verdicts or len(verdicts) != 1:
            continue
        res, th, src = results[0]
        verdict = res.verdict
        row_starred = any(x.coef.stars for x in pt.estimates if x.row == est.row)
        if verdict == "understated" and (_CONSTANT.match(est.label or "") or not row_starred):
            continue  # constants and rows never marked are often left without stars on purpose
        strong = all(r.strong for r, _, _ in results)
        assumed = []
        if not pt.thresholds:
            assumed.append("star thresholds")
        if pt.paren_source.startswith("assumed"):
            assumed.append("that the parentheses hold standard errors")
        df_decides = False
        if verdict == "understated":
            if df_low is not None:
                df_decides = res.df_sensitive
            elif ("clustered" in pt.se_types or not pt.column_values("observations", est.col)
                  or (text_clustered and not pt.se_types)):
                df_decides = True  # with few clusters, t(G - 1) can make these stars right
        if pt.adjusted or pt.one_sided or df_decides or (verdict == "understated" and paren_kind == "p"):
            status, confidence = "needs_human", "medium"
        elif assumed:
            status, confidence = "likely", "medium"
        else:
            status, confidence = "confirmed", "high"
        severity = "major" if strong else "minor"
        quote = pt.row_quote(est.row, est.col)
        if not quote:
            notes.append(f"{pt.name}: row {est.label!r} could not be quoted")
            continue
        se_quote = pt.row_quote(est.se_row) if est.se_row != est.row else None
        cell = est.coef.raw.strip()
        col = f'column "{est.column}"' if est.column else f"column {est.col + 1}"
        claimed = f"p < {res.implied[1]:g}" if est.coef.stars else f"p of at least {res.implied[0]:g}"
        if paren_kind == "se":
            t_point = est.coef.num.value / est.se.num.value if est.se.num.value else math.inf
            stat_text = f"t = {st.fmt(abs(t_point), 2)} ({st.fmt_range(res.t_range, 3)} after rounding)"
        elif paren_kind in ("t", "z"):
            stat_text = f"{paren_kind} = {est.se.num.raw} ({st.fmt_range(res.t_range, 3)} after rounding)"
        else:
            stat_text = f"reported p = {est.se.num.raw}"
        what = "overstate" if verdict == "overstated" else "understate"
        problem = (f"{pt.name}, row \"{est.label or '(unlabelled)'}\", {col}: {est.coef.num.raw} with "
                   f"{_PAREN_NAMES.get(paren_kind, paren_kind)[:-1]} {est.se.num.raw} gives {stat_text} and "
                   f"two-sided p = {st.fmt_range(res.p_range, p=True)}, but the mark {est.coef.stars or '(none)'} "
                   f"means {claimed}. The stars {what} the evidence.")
        if strong:
            problem += (" The 5% conclusion flips: the estimate is "
                        + (("not significant even at 10%." if res.p_range[0] >= 0.10 else "not significant at 5%.")
                           if verdict == "overstated" else "significant at 5%."))
        if df_decides:
            problem += f" The degrees of freedom decide this ({df_desc}), so a person should check."
        if pt.adjusted:
            problem += f" The note mentions {', '.join(pt.adjusted)}, so the stars may use adjusted p-values."
        correct = _correct_symbol(res.p_range, th) if len(options) == 1 and not df_decides else None
        replacement = None
        if correct is not None and est.coef.num is not None:
            replacement = cell.replace(est.coef.stars, "") + correct if est.coef.stars else cell + correct
            replacement = replacement.strip()
        fix = (Fix("replace", original=cell, replacement=replacement,
                   detail="Or correct the coefficient or standard error if one of them is the typo.",
                   resolved_when=f"The marks on {est.coef.num.raw} match the p-value implied by the coefficient and "
                                 f"standard error under the thresholds in the table note.")
               if replacement is not None and replacement != cell and _verbatim(pt.block, cell) else
               Fix("investigate", detail="Recompute the p-value and set the marks from it, or correct the "
                                         "coefficient or standard error.",
                   resolved_when=f"The marks on {est.coef.num.raw} match the p-value implied by the reported numbers."))
        evidence = [_cr(
            "|t| = |b| / SE with b and SE each widened by half a unit in their last printed decimal; "
            "p = 2 (1 - Phi(|t|))" if paren_kind == "se" else
            "|t| widened by half a unit in its last decimal; p = 2 (1 - Phi(|t|))" if paren_kind in ("t", "z") else
            "reported p widened by half a unit in its last decimal",
            {"coefficient": est.coef.num.raw, "parenthesis": est.se.num.raw,
             "parenthesis holds": _PAREN_NAMES.get(paren_kind, paren_kind),
             "parenthesis source": pt.paren_source, "mark": est.coef.stars or "none",
             "thresholds": st.describe_thresholds(th), "thresholds source": src},
            {"t range": st.fmt_range(res.t_range, 3) if res.t_range else None,
             "p range (normal)": st.fmt_range(res.p_range, p=True),
             "p range (lowest plausible df)": st.fmt_range(res.p_range_low_df, p=True) if res.p_range_low_df else None,
             "df assumption": df_desc, "mark implies": claimed, "verdict": verdict,
             "strong (5% conclusion flips)": strong},
            "rounding intervals of the printed numbers; the normal distribution gives the smallest p for any "
            "degrees of freedom, so an overstated mark stays overstated under every t distribution",
            tool="scipy.stats.norm and scipy.stats.t")]
        for other, oth, osrc in results[1:]:
            evidence.append(_cr("the same check under another reading of the table",
                                {"thresholds": st.describe_thresholds(oth), "reading": osrc},
                                {"p range": st.fmt_range(other.p_range, p=True), "verdict": other.verdict},
                                "as above"))
        trajectory = [
            f"Parsed {pt.name} ({pt.table.anchor.label()}): {len(pt.estimates)} coefficient and bracketed pairs.",
            f"Thresholds: {st.describe_thresholds(th)} ({src}).",
            f"Parentheses hold {_PAREN_NAMES.get(paren_kind, paren_kind)} ({pt.paren_source}).",
            f"Widened {est.coef.num.raw} and {est.se.num.raw} by half a unit in their last decimal and computed "
            f"the range of p: {st.fmt_range(res.p_range, p=True)}.",
            f"Compared with {claimed} for the mark {est.coef.stars or '(none)'}: {verdict}"
            + ("; the 5% conclusion flips." if strong else "."),
            f"Degrees of freedom: {df_desc}." + (" They decide the verdict." if df_decides else
                                                  " They cannot change an overstated verdict." if verdict == "overstated" else ""),
        ]
        related = [_rel(pt.block, se_quote), _rel(pt.block, pt.notes_quote(r"\*|p\s*<|signific"))]
        yield _emit(ctx, "NUM-03", f"Significance stars {what} the evidence in {pt.name}", severity, problem,
                    block=pt.block, quote=quote, evidence=evidence, trajectory=trajectory, fix=fix, status=status,
                    confidence=confidence, related=related,
                    extra={"table": pt.table.label, "table_number": pt.number, "row": est.label, "column": col,
                           "cell": cell, "parenthesis": est.se.raw.strip(), "verdict": verdict, "strong": strong,
                           "assumptions": assumed, "df": df_desc})


def _table_ci_findings(pt: ParsedTable, ctx, counts: dict, notes: list):
    for est in pt.estimates:
        ci = est.se if est.se.kind == "pair" else (est.third if est.third is not None and est.third.kind == "pair" else None)
        if ci is None or est.coef.num is None or ci.num is None or ci.second is None:
            continue
        se = est.se.num if est.se.kind == "brack" and pt.paren == "se" else None
        df_low, df_desc = _df_low(pt, est)
        res = st.check_ci(est.coef.num, ci.num, ci.second, se, pt.ci_level, df_low)
        counts["intervals"] += 1
        if re.search(r"bootstrap|percentile|bias[\s-]+corrected|profile|exact", pt.notes or "", re.I):
            res.width_verdict = None  # such intervals need not equal b +/- c * SE
        problems = []
        status, severity = "likely", "minor"
        if not res.contains_estimate:
            problems.append(f"the interval [{ci.num.raw}, {ci.second.raw}] does not contain the estimate {est.coef.num.raw}")
            status, severity = "confirmed", "major"
        if res.width_verdict == "narrow":
            problems.append(f"its half-width is {st.fmt_range(res.crit_range, 2)} standard errors, less than the "
                            f"{st.fmt(res.expected_crit[0], 2)} a {int(pt.ci_level * 100)}% interval needs")
        elif res.width_verdict == "wide":
            problems.append(f"its half-width is {st.fmt_range(res.crit_range, 2)} standard errors, more than "
                            f"{st.fmt(res.expected_crit[1], 2)} ({df_desc})")
            status = "needs_human" if status != "confirmed" else status
        if pt.thresholds or not pt.has_stars:
            th = pt.thresholds or st.DEFAULT_THRESHOLDS
            implied = st.implied_interval(est.coef.stars, th) if pt.has_stars else None
            alpha = round(1 - pt.ci_level, 4)
            if implied is not None and res.excludes_zero is not None:
                claimed = st.implied_significant(implied, alpha)
                if claimed is not None and claimed != res.excludes_zero:
                    problems.append("the interval " + ("excludes" if res.excludes_zero else "contains")
                                    + f" zero, but the mark {est.coef.stars or '(none)'} says the estimate is "
                                    + ("not " if not claimed else "") + f"significant at {alpha:g}")
                    severity = "major"
        if not problems:
            continue
        quote = pt.row_quote(est.row, est.col)
        if not quote:
            continue
        yield _emit(
            ctx, "NUM-03", f"Confidence interval inconsistent with the estimate in {pt.name}", severity,
            f"{pt.name}, row \"{est.label}\", {est.column or 'column ' + str(est.col + 1)}: " + "; ".join(problems) + ".",
            block=pt.block, quote=quote,
            evidence=[_cr("b within [lo, hi]; half-width (hi - lo) / 2 against c * SE with c = 1.96 for a 95% interval",
                          {"b": est.coef.num.raw, "interval": ci.raw.strip(), "SE": se.raw if se else None,
                           "level": pt.ci_level},
                          {"contains b": res.contains_estimate, "half-width / SE": st.fmt_range(res.crit_range, 2)
                           if res.crit_range else None, "excludes zero": res.excludes_zero},
                          "rounding intervals of every printed number; critical value from 1.96 up to "
                          f"{st.fmt(res.expected_crit[1], 2)} to allow for t distributions")],
            trajectory=[f"Parsed {pt.name}: interval {ci.raw.strip()} under {est.coef.raw.strip()}.",
                        "Checked that the interval contains the estimate and matches b +/- c * SE.",
                        "Compared the interval with the significance mark."],
            fix=Fix("investigate", detail="Recompute the interval from the estimate and its standard error.",
                    resolved_when="The interval contains the estimate, equals b +/- c * SE for the stated level, and "
                                  "agrees with the significance marks."),
            status=status, confidence="medium" if status != "confirmed" else "high",
            related=[_rel(pt.block, pt.row_quote(est.se_row))],
            extra={"table": pt.table.label, "table_number": pt.number, "row": est.label, "cell": est.coef.raw.strip()})


def _table_impossible(pt: ParsedTable, ctx):
    if "r2" in pt.stats:
        for i, r in enumerate(pt.table.rows):
            if pt.row_kinds[i] != "stat:r2":
                continue
            label = r[0].strip()
            adjusted = bool(re.match(r"adj", label, re.I))
            for c in pt.cells[i]:
                if c.num is None:
                    continue
                bad = c.num.lo > 1 + st.EPS or (not adjusted and c.num.hi < -st.EPS)
                if not bad:
                    continue
                quote = pt.row_quote(i)
                if not quote:
                    continue
                yield _emit(ctx, "NUM-03", f"Impossible R squared in {pt.name}", "minor",
                            f"{pt.name}, row \"{label}\": {c.num.raw} is outside the possible range "
                            f"({'at most 1' if adjusted else '0 to 1'}).",
                            block=pt.block, quote=quote,
                            evidence=[_cr("R squared must lie in [0, 1] (adjusted R squared at most 1)",
                                          {"value": c.num.raw, "row": label}, "outside the range", "exact")],
                            trajectory=[f"Read the R squared row of {pt.name}.", "Checked each value against [0, 1]."],
                            fix=Fix("investigate", detail="Correct the R squared value.",
                                    resolved_when="Every R squared lies between 0 and 1."),
                            status="confirmed", confidence="high",
                            extra={"table": pt.table.label, "row": label, "cell": c.raw})
    if pt.paren == "se" and not pt.paren_source.startswith("assumed"):
        for est in pt.estimates:
            if est.se.kind == "brack" and est.se.num is not None and est.se.num.hi < 0:
                quote = pt.row_quote(est.se_row)
                if quote:
                    yield _emit(ctx, "NUM-03", f"Negative standard error in {pt.name}", "minor",
                                f"{pt.name}, row \"{est.label}\": the standard error {est.se.raw.strip()} is negative.",
                                block=pt.block, quote=quote,
                                evidence=[_cr("a standard error is positive", {"SE": est.se.raw.strip()}, "negative", "exact")],
                                trajectory=[f"Read the standard errors of {pt.name}.", "Found a negative value."],
                                fix=Fix("investigate", detail="Report the standard error without a sign.",
                                        resolved_when="Every standard error is positive."),
                                status="confirmed", confidence="high",
                                extra={"table": pt.table.label, "row": est.label, "cell": est.se.raw})


# ================================================================ NUM-03: statistics in the text
LOWEST_DF = 2  # when no df is given, a t statistic could have as few as this


def _text_stat_p(ts: TextStat, tails: int = 2, df: Optional[float] = None, normal_only: bool = False) -> Optional[tuple]:
    """p range for a statistic in the text. Without stated df, the range runs from the normal
    limit (the smallest p for any df) up to t(df) or t(LOWEST_DF), so that only a p that no
    df could produce is called inconsistent. normal_only gives the normal range."""
    if ts.kind == "b_se":
        t_rng = st.t_range(ts.stat, ts.se)
        lo = st.p_range_from_t(t_rng, None, tails)
        if normal_only:
            return lo
        return (lo[0], st.p_range_from_t(t_rng, df or LOWEST_DF, tails)[1])
    if ts.kind == "t":
        if ts.df1 is None:
            lo = st.p_range_stat("t", ts.stat, None, None, tails)
            if normal_only:
                return lo
            return (lo[0], st.p_range_stat("t", ts.stat, LOWEST_DF, None, tails)[1])
        return st.p_range_stat("t", ts.stat, ts.df1, None, tails)
    if ts.kind == "z":
        return st.p_range_stat("z", ts.stat, None, None, tails)
    if ts.kind == "r":
        return st.p_range_stat("r", ts.stat, ts.df1, None, tails)
    if ts.kind == "F" and ts.df1 and ts.df2:
        return st.p_range_stat("F", ts.stat, ts.df1, ts.df2)
    if ts.kind == "chi2" and ts.df1:
        return st.p_range_stat("chi2", ts.stat, ts.df1)
    if ts.kind == "U":
        if ts.n1 and ts.n2:
            return st.p_range_u(ts.stat, ts.n1, ts.n2, tails)
        if ts.n:
            return st.p_range_u_total(ts.stat, ts.n, tails)
    return None


def _text_stat_findings(paper: _Paper, ctx, counts: dict, covered: set):
    for ts in paper.text_stats:
        match = _matching_estimate(paper, ts)
        df_known = None
        if match is not None:
            df_known = _df_low(*match)[0]
        p2 = _text_stat_p(ts, df=df_known)
        if p2 is None:
            continue
        p2_normal = _text_stat_p(ts, normal_only=True)
        counts["text"] += 1
        sent = ts.sent
        context = sent.norm + " " + sent.block.text
        one_sided = bool(_ONE_SIDED.search(context))
        corrected = bool(_CORRECTION.search(sent.norm))
        p1 = _text_stat_p(ts, tails=1, df=df_known) if ts.kind in ("t", "z", "b_se", "r", "U") else None
        p1_normal = _text_stat_p(ts, tails=1, normal_only=True) if p1 is not None else None
        stat_desc = ts.stat_text.strip()
        problems, strong = [], False
        kind_of_issue = None
        claim_span = None
        if ts.p is not None:
            ok = st.p_consistent(p2, ts.p) or (one_sided and p1 is not None and st.p_consistent(p1, ts.p))
            if not ok:
                rep_sig = st.reported_significant(ts.p)
                comp_sig = st.computed_significant(p2)
                strong = rep_sig is not None and comp_sig is not None and rep_sig != comp_sig
                if one_sided and p1 is not None:
                    comp1 = st.computed_significant(p1)
                    strong = strong and comp1 is not None and comp1 != rep_sig
                problems.append(f"{stat_desc} gives two-sided p = {st.fmt_range(p2, p=True)}, but the text reports "
                                f"{ts.p}")
                kind_of_issue = "p"
        if ts.claim is not None and ts.kind == "b_se":
            c = ts.claim
            covered.add((sent.sid, c["start"]))
            alpha = c["level"]
            if c["negative"]:
                bad = p2[1] < alpha - st.EPS
                if bad:
                    problems.append(f"{stat_desc} gives two-sided p = {st.fmt_range(p2, p=True)}, yet the text says "
                                    f"the estimate is not significant" + (f" at {alpha:g}" if c["explicit"] else ""))
                    strong = st.computed_significant(p2) is True
            else:
                pn, pn1 = p2_normal, p1_normal
                bad = pn[0] > alpha + st.EPS and not (one_sided and pn1 and pn1[0] <= alpha + st.EPS)
                if bad:
                    level_txt = f"at the {alpha * 100:g}% level" if c["explicit"] else "significant"
                    problems.append(f"{stat_desc} gives t = {st.fmt(ts.stat.value / ts.se.value, 2)} and two-sided "
                                    f"p = {st.fmt_range(pn, p=True)}, so it is not significant "
                                    + (level_txt if c["explicit"] else f"even at {alpha:g}"))
                    strong = alpha <= 0.05 + st.EPS and st.computed_significant(pn) is False
                    p2 = pn
            if problems and kind_of_issue is None:
                kind_of_issue = "claim"
                claim_span = (c["start"], c["end"])
        if not problems:
            continue
        if ts.kind == "U":
            status, confidence = "needs_human", "medium"
        elif corrected or (one_sided and kind_of_issue == "p") or sent.has_citation:
            status, confidence = "likely", "medium"
        elif kind_of_issue == "claim" and ts.claim and ts.claim["negative"]:
            status, confidence = "likely", "medium"
        elif ts.kind in ("t", "F", "chi2", "r") and ts.df1 is None:
            status, confidence = "likely", "medium"
        else:
            status, confidence = "confirmed", "high"
        severity = "major" if strong else "minor"
        end = max([ts.span[1]] + ([ts.p_span[1]] if ts.p_span and kind_of_issue == "p" else []) +
                  ([claim_span[1]] if claim_span else []))
        quote = sent.quote(ts.span[0], end)
        related, extra_ev = [], []
        if match is not None:
            pt, est = match
            related.append(_rel(pt.block, pt.row_quote(est.row)))
            problems.append(f"{pt.name} reports the same estimate as {est.coef.raw.strip()} "
                            f"with {est.se.raw.strip()}")
        problem = "; ".join(problems) + "."
        if strong:
            problem += " The 5% conclusion flips."
        if ts.kind == "U":
            problem += " (Normal approximation without tie correction; an exact test can differ in small samples.)"
        if claim_span is not None:
            original = sent.quote(*claim_span)
            new_level = _correct_symbol_text(p2)
            fix = Fix("replace", original=original, replacement=new_level,
                      detail="Or correct the estimate or standard error if one of them is the typo.",
                      resolved_when="The significance claim matches the p-value implied by the estimate and its "
                                    "standard error.")
        else:
            fix = Fix("investigate", detail=f"Recompute p from {stat_desc} and report it, or correct the statistic.",
                      resolved_when="The reported p-value equals the p-value recomputed from the test statistic and "
                                    "its degrees of freedom, within rounding.")
        formula = {"b_se": "t = b / SE over the rounding intervals; p = 2 (1 - Phi(|t|))",
                   "t": "p = 2 P(T_df > |t|)", "z": "p = 2 (1 - Phi(|z|))", "F": "p = P(F_df1,df2 > F)",
                   "chi2": "p = P(chi2_df > x)", "r": "t = r sqrt(df / (1 - r^2)); p = 2 P(T_df > |t|)",
                   "U": "z = (U - n1 n2 / 2) / sqrt(n1 n2 (n1 + n2 + 1) / 12); p = 2 (1 - Phi(|z|))"}[ts.kind]
        inputs = {"statistic": stat_desc, "df": [x for x in (ts.df1, ts.df2) if x] or None,
                  "reported p": str(ts.p) if ts.p else None,
                  "claim": sent.quote(*claim_span) if claim_span else None, "n1, n2 or N": [ts.n1, ts.n2] if ts.n1 else ts.n}
        output = {"p range (two-sided)": st.fmt_range(p2, p=True)}
        if p2_normal is not None and p2_normal != p2:
            output["p range (two-sided, normal)"] = st.fmt_range(p2_normal, p=True)
        if p1 is not None:
            output["p range (one-sided)"] = st.fmt_range(p1, p=True)
        if (ts.kind == "t" and ts.df1 is None) or (ts.kind == "b_se" and kind_of_issue != "claim"):
            output["df assumption"] = (f"t({df_known:g}) from the matching table" if df_known else
                                       f"any df from {LOWEST_DF} up, since none is stated")
        evidence = [_cr(formula, {k: v for k, v in inputs.items() if v is not None}, output,
                        "half a unit in the last printed decimal of every number; the normal distribution where no "
                        "df is given, which gives the smallest p", tool="scipy.stats")] + extra_ev
        trajectory = [f"Found \"{stat_desc}\" in {sent.where()} ({sent.block.anchor.label()}).",
                      f"Recomputed the p range over the rounding intervals: {st.fmt_range(p2, p=True)}.",
                      ("Compared with " + (str(ts.p) if kind_of_issue == "p" else "the significance claim") + ": inconsistent"
                       + ("; the 5% conclusion flips." if strong else "."))]
        if one_sided:
            trajectory.append("The passage mentions a one-sided test, so one-sided p was also accepted.")
        if match is not None:
            trajectory.append(f"Matched the estimate to {match[0].name}, row \"{match[1].label}\".")
        yield _emit(ctx, "NUM-03", "Reported significance does not match the statistic" if kind_of_issue == "claim"
                    else "Reported p-value does not match the test statistic", severity, problem,
                    block=sent.block, quote=quote, evidence=evidence, trajectory=trajectory, fix=fix, status=status,
                    confidence=confidence, related=related,
                    extra={"statistic": ts.kind, "also_checks": ["NUM-08"] if kind_of_issue == "claim" else [],
                           "strong": strong})


def _correct_symbol_text(p_rng: tuple) -> str:
    lo = p_rng[0]
    if lo >= 0.10:
        return f"not statistically significant at conventional levels (p = {sum(p_rng) / 2:.2f})"
    if lo >= 0.05:
        return "significant only at the 10% level"
    if lo >= 0.01:
        return "statistically significant at the 5% level"
    return "statistically significant at the 1% level"


def _matching_estimate(paper: _Paper, ts: TextStat) -> Optional[tuple]:
    if ts.linked:
        return ts.linked
    if ts.kind != "b_se":
        return None
    hits = []
    for pt in paper.reg_tables():
        for est in pt.estimates:
            if (est.coef.num is not None and est.se.num is not None and est.coef.num.exact == ts.stat.exact
                    and est.se.num.exact == ts.se.exact):
                hits.append((pt, est))
    return hits[0] if len(hits) == 1 else None


@register("NUM-03")
def statistics_consistency(pm, ctx):
    """NUM-03. Regression tables: significance stars against coefficient and standard error with
    rounding intervals (DORIS / Puetz-Bruns), confidence intervals, impossible R squared and
    negative standard errors. Text: t, F, chi-square, z, r and Mann-Whitney reports with p, and
    "coefficient (standard error) ... significant at the X% level".

    Misses: tables where coefficient and standard error sit in separate columns, stars on
    estimates whose standard error is in another table, p-values corrected for multiple testing
    (flagged for a person instead), and test reports in non-standard wording."""
    paper = _paper(pm)
    counts = {"estimates": 0, "intervals": 0, "text": 0}
    notes: list = []
    covered: set = set()
    candidates = 0
    # The text says standard errors are clustered, even where the table notes do not.
    text_clustered = any(re.search(r"cluster", sent.norm, re.I) and _TEXT_SE.search(sent.norm)
                         for sent in paper.sents if not sent.has_citation)
    for pt in paper.tables:
        if pt.block is None:
            notes.append(f"{pt.name}: no table block to quote")
            continue
        if not pt.table.rows:
            notes.append(f"{pt.name}: no rows could be read")
            candidates += 1
            continue
        if not pt.estimates:
            if pt.has_stars:
                notes.append(f"{pt.name}: has significance marks but no coefficient and bracketed rows could be paired")
                candidates += 1
            continue
        candidates += 1
        yield from _table_star_findings(pt, ctx, counts, notes, text_clustered)
        yield from _table_ci_findings(pt, ctx, counts, notes)
        yield from _table_impossible(pt, ctx)
    candidates += len(paper.text_stats)
    yield from _text_stat_findings(paper, ctx, counts, covered)
    evaluated = counts["estimates"] + counts["intervals"] + counts["text"]
    what = (f"items ({counts['estimates']} table estimates, {counts['intervals']} intervals, "
            f"{counts['text']} statistics in the text)")
    _coverage(ctx, "NUM-03", evaluated, candidates, what,
              "no regression tables and no test statistics in the text" if pm.tables else
              "the paper has no tables and no test statistics in the text", notes)


# ================================================================ NUM-08: significance claims
@register("NUM-08")
def significance_claims(pm, ctx):
    """NUM-08. "Significant", "not significant" and "marginally significant" against a p-value in
    the same sentence, a confidence interval, or the table estimate the sentence quotes. Claims
    next to a coefficient and its standard error are checked under NUM-03.

    Misses: claims that point to an estimate only in words ("the treatment effect is significant"),
    and whether an effect within the uncertainty is described as an effect, which needs reading."""
    paper = _paper(pm)
    covered = {(ts.sent.sid, ts.claim["start"]) for ts in paper.text_stats if ts.kind == "b_se" and ts.claim}
    claims_total = evaluated = 0
    for sent in paper.sents:
        claims = _claims(sent)
        if not claims:
            continue
        ps = _p_reports(sent)
        cis = list(_CI_RE.finditer(sent.norm))
        for c in claims:
            claims_total += 1
            if (sent.sid, c["start"]) in covered:
                evaluated += 1
                continue
            alpha = c["level"]
            evidence_desc = None
            p_rng = None
            source = None
            others = [x for x in claims if x is not c]
            after = [(p[0] - c["end"], p) for p in ps if p[0] >= c["end"] and p[0] - c["end"] <= 40
                     and not any(c["end"] <= x["start"] < p[0] for x in others)]
            before = [(c["start"] - p[1], p) for p in ps if p[1] <= c["start"] and c["start"] - p[1] <= 25
                      and not any(p[1] <= x["start"] < c["start"] for x in others)]
            near = [min(after)[1]] if after else ([min(before)[1]] if before else [])
            q_span = (c["start"], c["end"])
            if near:
                rep = near[0][2]
                q_span = (min(c["start"], near[0][0]), max(c["end"], near[0][1]))
                p_rng = rep.interval
                evidence_desc = f"the reported {rep}"
                source = ("p", rep)
            elif cis:
                m = cis[0]
                lo, hi = st.reported(m.group("lo")), st.reported(m.group("hi"))
                if lo is not None and hi is not None:
                    excl = lo.lo > 0 or hi.hi < 0
                    incl = lo.hi < 0 < hi.lo
                    lvl = float(m.group("lvl")) / 100 if m.group("lvl") else 0.95
                    if abs((1 - lvl) - alpha) < 1e-9 and (excl or incl):
                        p_rng = (0.0, alpha * 0.999) if excl else (alpha, 1.0)
                        evidence_desc = f"the {int(lvl * 100)}% confidence interval [{lo.raw}, {hi.raw}]"
                        source = ("ci", (lo, hi))
            else:
                est = _quoted_estimate(paper, sent, c)
                if est is not None:
                    pt, e = est
                    if pt.paren == "se" and e.se.kind == "brack":
                        t_rng = st.t_range(e.coef.num, e.se.num)
                        p_rng = st.p_range_from_t(t_rng)
                        if c["negative"]:  # a small df could make the estimate insignificant
                            p_rng = (p_rng[0], st.p_range_from_t(t_rng, _df_low(pt, e)[0] or LOWEST_DF)[1])
                        evidence_desc = (f"{pt.name}, row \"{e.label}\": {e.coef.raw.strip()} with standard error "
                                         f"{e.se.raw.strip()}")
                        source = ("table", est)
            if p_rng is None:
                continue
            evaluated += 1
            if c["negative"]:
                bad = p_rng[1] < alpha - st.EPS and (source[0] != "p" or source[1].comparator != ">")
                verdict = f"says not significant, but {evidence_desc} gives p below {alpha:g}"
            else:
                bad = p_rng[0] > alpha + st.EPS
                verdict = (f"says significant{' at ' + format(alpha * 100, 'g') + '%' if c['explicit'] else ''}, "
                           f"but {evidence_desc} gives p above {alpha:g}")
            if not bad:
                continue
            strong = (not c["negative"] and alpha <= 0.05 + st.EPS and p_rng[0] >= 0.05) or (
                c["negative"] and p_rng[1] < 0.05)
            claim_text = sent.quote(c["start"], c["end"])
            status = "confirmed" if (c["explicit"] and source[0] in ("p", "table")) else "likely"
            if c["adverb"] in ("marginally", "weakly"):
                status = "likely"
            related = []
            if source[0] == "table":
                related.append(_rel(source[1][0].block, source[1][0].row_quote(source[1][1].row)))
            yield _emit(
                ctx, "NUM-08", "Significance claim contradicts the reported statistics",
                "major" if strong else "minor",
                f"The sentence {verdict} (p range {st.fmt_range(p_rng, p=True)}).",
                block=sent.block, quote=sent.clause(*q_span),
                evidence=[_cr("claim of significance at alpha against the p range of the cited statistic",
                              {"claim": claim_text, "alpha": alpha, "statistic": evidence_desc},
                              {"p range": st.fmt_range(p_rng, p=True), "consistent": False},
                              "rounding interval of the printed numbers; an unstated level is read as 10% for a "
                              "claim of significance and 5% for a claim of no significance")],
                trajectory=[f"Found the claim \"{claim_text}\" in {sent.where()}.",
                            f"Linked it to {evidence_desc}.",
                            f"Compared the p range {st.fmt_range(p_rng, p=True)} with {alpha:g}: inconsistent."],
                fix=Fix("investigate", detail="State significance only as far as the reported statistics support it.",
                        resolved_when="The words about significance agree with the p-value, interval or table "
                                      "estimate they describe."),
                status=status, confidence="high" if status == "confirmed" else "medium", related=related,
                extra={"claim": claim_text, "level": alpha, "strong": strong})
    if claims_total == 0:
        ctx.not_applicable("NUM-08", "no claims of statistical significance in the text")
    else:
        ctx.note("NUM-08", f"{claims_total} significance claims found; {evaluated} could be linked to a statistic "
                           f"(claims next to an estimate and standard error are checked under NUM-03)")


def _quoted_estimate(paper: _Paper, sent: Sent, claim: dict) -> Optional[tuple]:
    tables = paper.tables_for(sent) or (paper.reg_tables() if len(paper.reg_tables()) == 1 else [])
    hits = []
    for tok in sent.tokens:
        if tok.kind != "result" or tok.rep.decimals < 2 or not (claim["start"] - 150 <= tok.s <= claim["end"] + 40):
            continue
        for pt in tables:
            for est in pt.estimates:
                if est.coef.num is not None and abs(est.coef.num.exact) == abs(tok.rep.exact):
                    hits.append((pt, est))
    uniq = {(id(h[0]), h[1].row, h[1].col): h for h in hits}
    return next(iter(uniq.values())) if len(uniq) == 1 else None


# ================================================================ NUM-01: headline numbers
@dataclass
class Candidate:
    source: str  # text, table
    block: Optional[Block]
    quote: str
    desc: str
    rel: Optional[tuple]  # relative change, as a fraction
    diff: tuple  # absolute change, in percentage points when pct
    pct: bool
    words: set
    direction: Optional[str]
    a_desc: str = ""
    b_desc: str = ""
    inputs: dict = field(default_factory=dict)
    formula: str = ""
    rows: list = field(default_factory=list)
    where: str = ""


_CLAIM_VERB = re.compile(rf"\b(?P<verb>reduc|lower|decreas|cut|increas|rais|boost|improv|ris|rose|fell|declin|drop|"
                         rf"shrink|shrank|grow|grew|halv|doubl)\w*\s+(?P<outcome>(?:(?!\bby\b)[^\d;:]){{3,120}}?)\s*\bby\s+"
                         rf"(?:(?P<q>{_QUAL})\s+)?(?P<c>{_NUM})(?P<cu>{_UNIT})?", re.I)
_CLAIM_ADJ = re.compile(rf"(?:(?P<q>{_QUAL})\s+)?(?P<c>{_NUM})(?P<cu>{_UNIT})?\s+(?P<dir>higher|lower|increase|decrease|"
                        rf"reduction|rise|drop|decline|gain|fall)\b(?:\s+in\s+(?P<outcome>[^\d;:,.]{{3,80}}))?", re.I)


def _candidates(paper: _Paper) -> list:
    out = []
    for ch in paper.changes:
        if ch.sent.role in ("abstract", "conclusion") or ch.sent.has_citation:
            continue
        a, b = ch.a.rep, ch.b.rep
        rel = st.rel_range(a, b)
        pct = "%" in (ch.a.unit, ch.b.unit) or "pp" in (ch.a.unit, ch.b.unit)
        direction = "down" if b.hi < a.lo else "up" if b.lo > a.hi else ch.direction
        out.append(Candidate("text", ch.sent.block, ch.sent.quote(),
                             f"{ch.sent.where()} reports a change from {ch.a.text()} to {ch.b.text()}",
                             rel, st.diff_range(a, b), pct, _stems(ch.sent.norm), direction,
                             ch.a.text(), ch.b.text(), {"from": ch.a.text(), "to": ch.b.text()}, "(B - A) / A",
                             where=ch.sent.where()))
    for sent in paper.sents:
        if sent.role in ("abstract", "conclusion") or sent.has_citation:
            continue
        for m in _GROUP_PAIR.finditer(sent.norm):
            ta, tb = _tok_at(sent, m.start("a")), _tok_at(sent, m.start("b"))
            if ta is None or tb is None:
                continue
            ga = m.group("ga").lower()
            ctrl, trt = (ta, tb) if ga in ("control", "comparison") else (tb, ta)
            a, b = ctrl.rep, trt.rep
            if any(c.source == "text" and c.block is sent.block and c.a_desc == ctrl.text() and c.b_desc == trt.text()
                   for c in out):
                continue
            pct = "%" in (ctrl.unit, trt.unit)
            out.append(Candidate("text", sent.block, sent.quote(),
                                 f"{sent.where()} reports {ctrl.text()} in the control group and {trt.text()} in the "
                                 f"treatment group",
                                 st.rel_range(a, b), st.diff_range(a, b), pct, _stems(sent.norm),
                                 "down" if b.hi < a.lo else "up" if b.lo > a.hi else None, ctrl.text(), trt.text(),
                                 {"control": ctrl.text(), "treatment": trt.text()}, "(treatment - control) / control",
                                 where=sent.where()))
    for pt in paper.reg_tables():
        cms = pt.stats.get("control_mean", {})
        for col, cm_cell in cms.items():
            cm = cm_cell.num
            if cm is None or cm.lo <= 0 <= cm.hi:
                continue
            ests = [e for e in pt.estimates if e.col == col and e.coef.num is not None]
            if not ests:
                continue
            treat = [e for e in ests if _TREATMENT_LABEL.search(e.label or "")] or ests[:1]
            e = treat[0]
            b = e.coef.num
            rel = st.quotient_range(b, cm)
            share = 0 < cm.value < 1 and abs(b.value) < 1
            diff = (100 * b.lo, 100 * b.hi) if share else b.interval
            words = _stems(" ".join([pt.table.caption or "", pt.columns.get(col, ""), e.label, "control treatment"]))
            row_q = pt.row_quote(e.row)
            cm_row = next((i for i, k in enumerate(pt.row_kinds) if k == "stat:control_mean"), None)
            out.append(Candidate("table", pt.block, row_q or "",
                                 f"{pt.name}, column {pt.columns.get(col) or col + 1}, reports a coefficient of {b.raw} "
                                 f"on a control mean of {cm.raw}", rel, diff, share, words,
                                 "down" if b.hi < 0 else "up" if b.lo > 0 else None, cm.raw, b.raw,
                                 {"coefficient": b.raw, "control mean": cm.raw}, "coefficient / control mean",
                                 [row_q, pt.row_quote(cm_row) if cm_row is not None else None], where=pt.name))
    return out


def _headline_claims(paper: _Paper) -> list:
    out = []
    for sent in paper.sents:
        if sent.role not in ("abstract", "conclusion") or sent.has_citation:
            continue
        for rx in (_CLAIM_VERB, _CLAIM_ADJ):
            for m in rx.finditer(sent.norm):
                tok = _tok_at(sent, m.start("c"))
                if tok is None or tok.kind not in ("result",):
                    continue
                if any(c["tok"] is tok for c in out):
                    continue
                gd = m.groupdict()
                direction = _direction(gd.get("verb") or gd.get("dir"))
                out.append({"sent": sent, "tok": tok, "q": gd.get("q"), "direction": direction,
                            "outcome": gd.get("outcome") or "", "span": (m.start(), m.end()),
                            "c_span": (m.start("c"), m.end("cu") if m.group("cu") else m.end("c"))})
    return out


def _claim_value_ranges(cand: Candidate) -> dict:
    out = {}
    if cand.rel is not None:
        out["relative"] = st.magnitude((100 * cand.rel[0], 100 * cand.rel[1]))
    out["absolute"] = st.magnitude(cand.diff)
    return out


def _assess_claims(paper: _Paper) -> list:
    """Compare every headline change claim with every value pair in the body and tables.

    verdict: "match" (some pair gives the claimed value), "mismatch" (none does, and the
    closest-worded pair gives another value), "other_measure" (the claim matches the
    percentage-point change where it says percent, or the reverse), or "unmatched"."""
    cached = getattr(paper, "_assessed", None)
    if cached is not None:
        return cached
    claims = _headline_claims(paper)
    cands = _candidates(paper)
    out = []
    for cl in claims:
        sent, tok = cl["sent"], cl["tok"]
        claim_rng = st.claim_range(tok.rep, cl["q"])
        primary = "absolute" if tok.unit in ("pp", None) else "relative"
        secondary = "relative" if primary == "absolute" else "absolute"
        words = _stems(sent.norm)
        scored = []
        for cand in cands:
            if cl["direction"] and cand.direction and cl["direction"] != cand.direction:
                continue
            ranges = _claim_value_ranges(cand)
            p_ok = primary in ranges and st.overlaps(claim_rng, ranges[primary]) and not (
                tok.unit == "pp" and not cand.pct)
            s_ok = secondary in ranges and st.overlaps(claim_rng, ranges[secondary]) and (
                secondary == "relative" or cand.pct)
            scored.append({"sim": _similarity(words, cand.words), "shared": len(words & cand.words), "cand": cand,
                           "ranges": ranges, "p_ok": p_ok, "s_ok": s_ok})
        scored.sort(key=lambda x: (-x["sim"], x["cand"].source != "text"))
        res = {"claim": cl, "primary": primary, "secondary": secondary, "candidates": len(cands), "scored": scored,
               "verdict": "unmatched", "best": None}
        if any(x["p_ok"] for x in scored):
            res["verdict"] = "match"
        elif scored and scored[0]["sim"] >= 0.2 and scored[0]["shared"] >= 2:
            best = scored[0]
            res["best"] = best
            if best["s_ok"] and best["cand"].pct:
                res["verdict"] = "other_measure"
            elif any(x["s_ok"] for x in scored):
                res["verdict"] = "match"  # some pair fits the other measure: ambiguous, so no flag
            else:
                res["verdict"] = "mismatch"
                res["corroborating"] = [x for x in scored[1:] if primary in x["ranges"]
                                        and st.overlaps(x["ranges"][primary], best["ranges"][primary])]
        out.append(res)
    paper._assessed = out
    return out


def _claim_original(sent: Sent, cl: dict) -> tuple:
    """Span of the claimed number with its "by", such as "by 23%", for the fix."""
    s0, e0 = cl["c_span"]
    by = sent.norm.rfind("by ", cl["span"][0], s0)
    if by >= 0 and s0 - by <= 20:
        s0 = by
    return s0, e0


@register("NUM-01")
def headline_numbers(pm, ctx):
    """NUM-01. Headline numbers in the abstract and conclusion against the body and tables.
    A relative change ("reduces X by 23%") is recomputed from every pair of values the body
    reports for an outcome (from A to B, control and treatment values, a table coefficient over
    its control mean). It is flagged only when no pair in the paper gives the claimed value and
    the closest-worded pair gives a different one. Other headline estimates are searched for in
    the body and the tables, allowing for rounding and the percent/share scale.

    Misses: headline numbers that summarise several results, outcomes worded with no shared
    words, and numbers that appear only in figures (figures are not read)."""
    paper = _paper(pm)
    assessed = _assess_claims(paper)
    headline_sents = [s for s in paper.sents if s.role in ("abstract", "conclusion") and not s.has_citation]
    evaluated = len(assessed)
    for res in assessed:
        if res["verdict"] != "mismatch":
            continue
        cl, best = res["claim"], res["best"]
        sent, tok, primary = cl["sent"], cl["tok"], res["primary"]
        cand = best["cand"]
        corroborating = res.get("corroborating", [])
        elsewhere = [n for n in _all_numbers(paper, exclude_sent=sent)
                     if _number_matches(tok.rep, tok.unit, n[0], n[1] == "%")]
        sources = {cand.source} | {c["cand"].source for c in corroborating}
        confirmed = len(sources) >= 2 and not elsewhere and not cl["q"]
        status, confidence = ("confirmed", "high") if confirmed else ("likely", "medium")
        computed = best["ranges"][primary]
        mid = (computed[0] + computed[1]) / 2
        noun = {"down": "reduction", "up": "increase"}.get(cl["direction"], "change")
        kind_txt = f"relative {noun}" if primary == "relative" else noun
        unit_txt = "%" if primary == "relative" else (" percentage points" if cand.pct else "")
        head = "The abstract" if sent.role == "abstract" else "The conclusion"
        problem = (f"{head} states a {kind_txt} of {tok.text()}. {_cap(cand.desc)}: a {kind_txt} of "
                   f"{mid:.1f}{unit_txt} ({computed[0]:.1f} to {computed[1]:.1f} allowing for rounding).")
        for c in corroborating[:2]:
            r2 = c["ranges"][primary]
            problem += f" {_cap(c['cand'].desc)}, which gives the same {(r2[0] + r2[1]) / 2:.1f}{unit_txt}."
        if not elsewhere:
            problem += f" No other number in the paper is {tok.text()}."
        places = max(tok.rep.places, 0)
        new_value = f"{mid:.{places}f}" + ("%" if tok.unit == "%" else " percentage points" if tok.unit == "pp" else "")
        o_span = _claim_original(sent, cl)
        orig = sent.quote(*o_span)
        replacement = orig[:orig.find(tok.raw)] + new_value if tok.raw in orig else new_value
        evidence = [_cr(cand.formula, cand.inputs, f"{mid:.1f}{unit_txt} (range {computed[0]:.1f} to {computed[1]:.1f})",
                        "half a unit in the last printed digit of each input and of the claim")]
        for c in corroborating[:2]:
            r2 = c["ranges"][primary]
            evidence.append(_cr(c["cand"].formula, c["cand"].inputs,
                                f"{(r2[0] + r2[1]) / 2:.1f}{unit_txt} (range {r2[0]:.1f} to {r2[1]:.1f})",
                                "half a unit in the last printed digit"))
        evidence.append(Evidence(type="checked_absence", data={
            "scope": "every sentence and table cell outside this sentence, allowing for rounding and the share scale",
            "terms": {tok.text(): len(elsewhere)}, "version": "paper map"}))
        related = [_rel(cand.block, cand.quote)] + [_rel(cand.block, q) for q in cand.rows[1:]]
        for c in corroborating[:2]:
            related += [_rel(c["cand"].block, q) for q in ([c["cand"].quote] + c["cand"].rows[1:])]
        seen, uniq = set(), []
        for r in related:
            if r and (r["block"], r["quote"]) not in seen:
                seen.add((r["block"], r["quote"]))
                uniq.append(r)
        trajectory = [f"Extracted the claim \"{sent.quote(*cl['span'])}\" from {sent.where()} "
                      f"({sent.block.anchor.label()}).",
                      f"Collected {res['candidates']} value pairs from the body and tables; none gives {tok.text()}.",
                      f"Closest-worded pair: {cand.desc} (word overlap {best['sim']:.2f}).",
                      f"Recomputed the {kind_txt} over the rounding intervals: {mid:.1f}{unit_txt}."]
        if corroborating:
            trajectory.append(f"{len(corroborating)} other source(s) give the same value.")
        trajectory.append(f"Searched the rest of the paper for {tok.text()}: {len(elsewhere)} matches.")
        fix = (Fix("replace", original=orig, replacement=replacement,
                   detail="Or update the body and tables if they hold the stale numbers.",
                   resolved_when=f"{head} and {cand.where} imply the same {kind_txt}, within rounding.")
               if _verbatim(sent.block, orig) else
               Fix("investigate", detail=f"Make {head.lower()} and {cand.where} agree.",
                   resolved_when=f"{head} and {cand.where} imply the same {kind_txt}, within rounding."))
        yield _emit(ctx, "NUM-01", "Headline number disagrees with the body", "major", problem,
                    block=sent.block, quote=sent.quote(), evidence=evidence, trajectory=trajectory, fix=fix,
                    status=status, confidence=confidence, related=uniq,
                    extra={"claimed": tok.text(), "computed": round(mid, 3), "sources": sorted(sources)})
    claims = [r["claim"] for r in assessed]
    support = [n for n in _all_numbers(paper, exclude_roles=("abstract",))]
    for sent in headline_sents:
        spans = [c["span"] for c in claims if c["sent"] is sent]
        spans += [ch.span for ch in paper.changes if ch.sent is sent] + [ch.c_span for ch in paper.changes
                                                                         if ch.sent is sent and ch.c_span]
        for tok in sent.tokens:
            if tok.kind != "result" or any(a <= tok.s < b for a, b in spans if a is not None):
                continue
            if tok.rep.decimals == 0 and tok.unit is None:
                continue
            evaluated += 1
            pool = support if sent.role == "abstract" else [n for n in support if not (
                isinstance(n[4], Sent) and n[4].role == "conclusion")]
            if any(_number_matches(tok.rep, tok.unit, n[0], n[1] == "%") for n in pool):
                continue
            ctx_start = max(0, tok.s - 40)
            space = sent.norm.find(" ", ctx_start, tok.s)
            ctx_start = space + 1 if ctx_start > 0 and space >= 0 else ctx_start
            phrase = sent.quote(ctx_start, tok.e)
            shown = sent.norm[ctx_start:tok.e].strip() + ("%" if tok.unit == "%" else "")
            yield _emit(ctx, "NUM-01", "Headline number not found in the body or tables", "minor",
                        f"{'The abstract' if sent.role == 'abstract' else 'The conclusion'} reports \"{shown}\", "
                        f"but no sentence or table cell elsewhere reports this number, even allowing for rounding. "
                        f"Figures were not searched.",
                        block=sent.block, quote=sent.clause(tok.s, tok.e),
                        evidence=[_cr("search for the same value in every other sentence and table cell",
                                      {"value": tok.text(), "context": phrase},
                                      "no match", "half a unit in the last printed digit; percent and share scales"),
                                  Evidence(type="checked_absence", data={
                                      "scope": "body text, footnotes, captions and tables; not figures",
                                      "terms": {tok.text(): 0}, "version": "paper map"})],
                        trajectory=[f"Listed the result numbers in {sent.where()}.",
                                    f"Searched {len(pool)} numbers elsewhere in the paper for {tok.text()}: none match."],
                        fix=Fix("investigate", detail=f"Report where {tok.text()} comes from in the body or a table, "
                                                      "or correct the headline.",
                                resolved_when=f"The body or a table reports {tok.text()}, or the headline number is "
                                              "changed to one the body reports."),
                        status="needs_human", confidence="medium", extra={"value": tok.text()})
    candidates = len(claims) + sum(1 for s in headline_sents for t in s.tokens if t.kind == "result")
    _coverage(ctx, "NUM-01", evaluated, candidates, "headline numbers",
              "no numbers in the abstract or conclusion" if headline_sents else "no abstract or conclusion found", [])


# ================================================================ NUM-02 and NUM-09: changes
def _eval_change(ch: Change) -> Optional[dict]:
    a, b = ch.a.rep, ch.b.rep
    pct_ab = ch.a.unit in ("%", "pp") or ch.b.unit in ("%", "pp")
    diff = st.magnitude(st.diff_range(a, b))
    if not pct_ab and ch.c is not None and ch.c.unit in ("%", "pp") and max(a.decimals, b.decimals) > 0 and (
            0 <= a.value <= 1 and 0 <= b.value <= 1):
        pct_ab = True  # shares written as proportions: a change of 0.05 is 5 percentage points
        diff = (100 * diff[0], 100 * diff[1])
    rel = st.rel_range(a, b)
    rel_pct = st.magnitude((100 * rel[0], 100 * rel[1])) if rel else None
    out = {"diff": diff, "rel": rel_pct, "pct_ab": pct_ab}
    direction = ch.c_dir or ch.direction
    if direction == "up" and b.hi < a.lo:
        out["direction"] = "the values fall although the text says they rise"
    elif direction == "down" and b.lo > a.hi:
        out["direction"] = "the values rise although the text says they fall"
    if ch.c is None:
        if ch.multiplier:
            ratio = st.ratio_range(a, b)
            if ratio:
                ok = st.overlaps(ratio, (0.9 * ch.multiplier, 1.1 * ch.multiplier))
                out.update(kind="ratio", ok=ok, expected=ratio, claim=(ch.multiplier, ch.multiplier))
                return out
        return out if "direction" in out else None
    c = ch.c.rep
    claim = st.claim_range(c, ch.c_qual)
    cu = ch.c.unit
    out["claim"] = claim
    if cu == "pp":
        ok = pct_ab and st.overlaps(claim, diff)
        alt = rel_pct is not None and st.overlaps(claim, rel_pct)
        out.update(kind="pp", ok=ok, alt=alt, expected=diff)
    elif cu == "%":
        ok = rel_pct is not None and st.overlaps(claim, rel_pct)
        alt = pct_ab and st.overlaps(claim, diff)
        out.update(kind="relative", ok=ok, alt=alt, expected=rel_pct)
    else:
        ok = st.overlaps(claim, diff) or (rel_pct is not None and st.overlaps(claim, rel_pct))
        out.update(kind="absolute", ok=ok, alt=False, expected=diff)
    return out


def _change_findings(paper: _Paper, ctx, which: str):
    evaluated = 0
    for ch in paper.changes:
        res = _eval_change(ch)
        if res is None:
            continue
        evaluated += 1
        sent = ch.sent
        if sent.has_citation:
            continue
        a_t, b_t = ch.a.text(), ch.b.text()
        quote = sent.quote()
        if "direction" in res and which == "NUM-02":
            yield _emit(ctx, "NUM-02", "Stated direction of change contradicts the numbers", "major",
                        f"From {a_t} to {b_t}: {res['direction']}.", block=sent.block, quote=quote,
                        evidence=[_cr("sign of B - A", {"A": a_t, "B": b_t}, st.fmt_range(st.diff_range(ch.a.rep, ch.b.rep), 3),
                                      "half a unit in the last printed digit")],
                        trajectory=[f"Parsed \"from {a_t} to {b_t}\" in {sent.where()}.", "Compared the direction word with B - A."],
                        fix=Fix("investigate", detail="Correct the direction word or the values.",
                                resolved_when="The direction word matches the sign of B - A."),
                        status="likely", confidence="medium", extra={"from": a_t, "to": b_t})
            continue
        if "ok" not in res or res["ok"]:
            continue
        c_t = ch.c.text() if ch.c else f"{ch.multiplier:g} times"
        orig = sent.quote(*ch.c_span) if ch.c_span else c_t
        diff_mid = float(ch.b.rep.exact - ch.a.rep.exact)
        if not ({ch.a.unit, ch.b.unit} & {"%", "pp"}) and res.get("pct_ab"):
            diff_mid *= 100  # proportions
        rel_mid = float((ch.b.rep.exact - ch.a.rep.exact) / ch.a.rep.exact) * 100 if ch.a.rep.exact else None
        places = max(ch.c.rep.places, 0) if ch.c else 1
        diff_txt = f"{abs(diff_mid):.{places}f}"
        rel_txt = f"{abs(rel_mid):.{places}f}%" if rel_mid is not None else "n/a"
        exact_ok = ch.c_qual is None
        if res.get("kind") == "pp" and res.get("alt"):
            cid, title = "NUM-09", "Relative change reported in percentage points"
            problem = (f"From {a_t} to {b_t} is a change of {diff_txt} percentage points, or {rel_txt} in relative "
                       f"terms. The text says \"{orig}\", which is the relative change labelled as percentage points.")
            replacement = re.sub(re.escape(ch.c.raw) + r"\s*(?:percentage\s+points?|pp|p\.p\.)",
                                 f"{diff_txt} percentage points ({rel_txt} in relative terms)", orig, count=1)
        elif res.get("kind") == "relative" and res.get("alt"):
            cid, title = "NUM-09", "Percentage-point change reported as percent"
            problem = (f"From {a_t} to {b_t} is a change of {diff_txt} percentage points, or {rel_txt} in relative "
                       f"terms. The text says \"{orig}\", which is the percentage-point change labelled as percent.")
            replacement = re.sub(re.escape(ch.c.raw) + r"\s*(?:%|percent|per\s+cent)",
                                 f"{diff_txt} percentage points ({rel_txt} in relative terms)", orig, count=1)
        else:
            cid, title = "NUM-02", "Stated change does not match the values"
            exp = res["expected"]
            what = {"pp": "percentage-point change", "relative": "relative change", "absolute": "difference",
                    "ratio": "ratio"}[res["kind"]]
            problem = (f"From {a_t} to {b_t}, the {what} is {st.fmt(exp[0], 2)} to {st.fmt(exp[1], 2)} allowing for "
                       f"rounding, but the text says {c_t}.")
            new = (f"{diff_txt} percentage points" if res["kind"] == "pp" else rel_txt if res["kind"] == "relative"
                   else diff_txt)
            replacement = orig.replace(ch.c.raw, new.split(" ")[0].rstrip("%"), 1) if ch.c and res["kind"] != "ratio" else None
        if cid != which:
            continue
        exp_desc = {"change in points": f"{st.fmt(res['diff'][0], 2)} to {st.fmt(res['diff'][1], 2)}",
                    "relative change (%)": f"{st.fmt(res['rel'][0], 2)} to {st.fmt(res['rel'][1], 2)}"
                    if res.get("rel") else None}
        evidence = [_cr("B - A in percentage points; (B - A) / A x 100 in percent",
                        {k: v for k, v in {"A": a_t, "B": b_t, "stated": orig, "qualifier": ch.c_qual}.items() if v},
                        {k: v for k, v in exp_desc.items() if v}, "half a unit in the last printed digit of A, B and "
                        "the stated change; words such as 'about' widen the stated value by 10%")]
        fix = (Fix("replace", original=orig, replacement=replacement,
                   resolved_when="The stated change equals B - A in percentage points, or (B - A) / A in percent, "
                                 "within rounding.")
               if replacement and replacement != orig and _verbatim(sent.block, orig) else
               Fix("investigate", detail="Recompute the change from the two values.",
                   resolved_when="The stated change equals the change computed from the two values, within rounding."))
        yield _emit(ctx, cid, title, "major", problem, block=sent.block, quote=quote, evidence=evidence,
                    trajectory=[f"Parsed \"from {a_t} to {b_t}\" and the stated change \"{orig}\" in {sent.where()} "
                                f"({sent.block.anchor.label()}).",
                                f"Computed B - A = {diff_txt} and (B - A) / A = {rel_txt} over the rounding intervals.",
                                ("The stated change matches the other measure, not the one its unit names."
                                 if cid == "NUM-09" else "The stated change matches neither measure.")],
                    fix=fix, status="confirmed" if exact_ok else "likely", confidence="high" if exact_ok else "medium",
                    extra={"from": a_t, "to": b_t, "stated": c_t})
    return evaluated


_K_OF_N = [
    re.compile(r"(?P<k>\d[\d,]*)\s+(?:of|out\s+of)\s+(?:the\s+)?(?P<n>\d[\d,]*)(?:\s+[A-Za-z-]+){0,3}?\s*\(\s*(?P<p>\d+(?:\.\d+)?)\s*%\s*\)", re.I),
    re.compile(r"(?P<p>\d+(?:\.\d+)?)\s*%\s*\(\s*(?P<k>\d[\d,]*)\s*(?:/|of|out\s+of)\s*(?P<n>\d[\d,]*)\s*\)", re.I),
    re.compile(r"(?P<p>\d+(?:\.\d+)?)\s*%\s*\(\s*n\s*=\s*(?P<k>\d[\d,]*)\s*(?:/|of|out\s+of)\s*(?P<n>\d[\d,]*)\s*\)", re.I),
]
_REMAINING = re.compile(r"\b(?:the\s+)?(?:remaining|rest|other)\b", re.I)


def _replace_span(sent: Sent, m: re.Match, group: str, new: str) -> str:
    """The verbatim text of match m with one group replaced."""
    a, b = sent.span(m.start(), m.end())
    ga, gb = sent.span(m.start(group), m.end(group))
    text = sent.block.text
    return (text[a:ga] + new + text[gb:b]).strip()


@register("NUM-02")
def arithmetic(pm, ctx):
    """NUM-02. Recomputes "from A to B, an increase of C" (difference, percent change, ratio,
    direction), "k of n (x%)" and "x% (k/n)", lists of shares that end in "the remaining x%",
    and table columns or rows labelled Total. A percent/percentage-point mix-up goes to NUM-09.

    Misses: arithmetic spread over several sentences, totals of rounded percentages that are
    not labelled, and differences in balance tables that may be regression-adjusted."""
    paper = _paper(pm)
    evaluated = 0
    n_changes = sum(1 for ch in paper.changes if ch.c is not None or ch.multiplier or ch.direction)
    gen = _change_findings(paper, ctx, "NUM-02")
    while True:
        try:
            yield next(gen)
        except StopIteration as stop:
            evaluated += stop.value or 0
            break
    candidates = n_changes
    for sent in paper.sents:
        if sent.has_citation:
            continue
        for rx in _K_OF_N:
            for m in rx.finditer(sent.norm):
                k, n, p = int(m.group("k").replace(",", "")), int(m.group("n").replace(",", "")), st.reported(m.group("p"))
                if n <= 0 or k > n or p is None:
                    continue
                candidates += 1
                evaluated += 1
                res = st.share_check(p, k, n)
                if res["consistent"]:
                    continue
                places = max(p.places, 0)
                yield _emit(ctx, "NUM-02", "Percentage does not match the count", "major",
                            f"{k} of {n} is {res['computed']:.{max(places, 1)}f}%, not {p.raw}%.",
                            block=sent.block, quote=sent.quote(m.start(), m.end()),
                            evidence=[_cr("100 k / n", {"k": k, "n": n, "stated": p.raw + "%"},
                                          f"{res['computed']:.3f}%", "half a unit in the last printed digit of the percentage")],
                            trajectory=[f"Found \"{sent.quote(m.start(), m.end())}\" in {sent.where()}.",
                                        "Recomputed the percentage from the count."],
                            fix=Fix("replace", original=sent.quote(m.start(), m.end()),
                                    replacement=_replace_span(sent, m, "p", f"{res['computed']:.{places}f}"),
                                    resolved_when="The percentage equals 100 k / n after rounding.")
                            if sent.block.text.count(sent.quote(m.start(), m.end())) == 1 else
                            Fix("investigate", resolved_when="The percentage equals 100 k / n after rounding."),
                            status="confirmed", confidence="high", extra={"k": k, "n": n, "stated": p.raw})
        m_rem = _REMAINING.search(sent.norm)
        if m_rem:
            pcts = [t for t in sent.tokens if t.unit == "%" and t.kind == "result"]
            after_rem = [t for t in pcts if t.s > m_rem.start()]
            pcts = [t for t in pcts if t.s <= m_rem.start()] + after_rem[:1]
            if (len(pcts) >= 2 and after_rem and after_rem[0].s - m_rem.end() <= 12
                    and not re.search(r"\b(?:of\s+(?:the\s+)?remaining|each)\b", sent.norm)):
                candidates += 1
                evaluated += 1
                total = st.reported("100")
                res = st.sum_check([t.rep for t in pcts], total)
                if not res["consistent"]:
                    yield _emit(ctx, "NUM-02", "Shares do not add up to 100%", "major",
                                f"The shares {', '.join(t.text() for t in pcts)} add up to {res['sum']:g}%, not 100%.",
                                block=sent.block, quote=sent.quote(pcts[0].s, pcts[-1].e),
                                evidence=[_cr("sum of the shares", {"shares": [t.text() for t in pcts]},
                                              f"{res['sum']:g}%", f"sum of half-units, {res['tolerance']:g} points")],
                                trajectory=[f"Found shares ending in \"the remaining\" in {sent.where()}.",
                                            "Added them up."],
                                fix=Fix("investigate", detail="Correct the shares so the parts cover the whole.",
                                        resolved_when="The shares add up to 100% within rounding."),
                                status="likely", confidence="medium", extra={"shares": [t.text() for t in pcts]})
    for pt in paper.tables:
        res = _table_totals(pt, ctx)
        for f in res["findings"]:
            yield f
        candidates += res["candidates"]
        evaluated += res["evaluated"]
    _coverage(ctx, "NUM-02", evaluated, candidates, "statements and totals",
              "no stated changes, percentages of counts, share lists or total rows", [])


def _table_totals(pt: ParsedTable, ctx) -> dict:
    out = {"findings": [], "candidates": 0, "evaluated": 0}
    if pt.block is None or pt.estimates:
        return out
    rows = pt.table.rows
    total_rows = [i for i, r in enumerate(rows) if r and _TOTAL_LABEL.match(r[0].strip())]
    checks = []
    for ti in total_rows:
        start = max([i for i in range(ti) if pt.row_kinds[i] in ("label", "header", "colnums")] or [-1]) + 1
        body = [i for i in range(start, ti) if pt.row_kinds[i] == "values"]
        if len(body) < 2:
            continue
        for j, tc in enumerate(pt.cells[ti]):
            if tc.kind != "num" or tc.num is None:
                continue
            parts = [pt.cells[i][j] for i in body if j < len(pt.cells[i])]
            if any(p.kind != "num" or p.num is None for p in parts):
                continue
            nums = [p.num for p in parts]
            if tc.num.value <= max(n.value for n in nums) or any(n.value < 0 for n in nums):
                continue
            checks.append((ti, j, nums, tc))
    if not checks:
        return out
    out["candidates"] = len(checks)
    out["evaluated"] = len(checks)
    results = [(c, st.sum_check(c[2], c[3].num)) for c in checks]
    if not any(r["consistent"] for _, r in results):
        return out  # no column adds up, so "Total" may not be a sum here
    for (ti, j, nums, tc), r in results:
        if r["consistent"]:
            continue
        quote = pt.row_quote(ti)
        if not quote:
            continue
        out["findings"].append(_emit(
            ctx, "NUM-02", f"Total row does not add up in {pt.name}", "major",
            f"{pt.name}, {pt.columns.get(j) or 'column ' + str(j + 2)}: the rows above add up to {r['sum']:g}, "
            f"but the total row says {tc.num.raw}. Other columns of the same table do add up.",
            block=pt.block, quote=quote,
            evidence=[_cr("sum of the rows above the total", {"rows": [n.raw for n in nums], "total": tc.num.raw},
                          f"{r['sum']:g}", f"sum of half-units, {r['tolerance']:g}")],
            trajectory=[f"Found a total row in {pt.name}.", "Added the rows above it in each column.",
                        "At least one other column adds up, so the row is a sum."],
            fix=Fix("investigate", detail="Correct the total or the rows above it.",
                    resolved_when="Each total equals the sum of the rows above it, within rounding."),
            status="likely", confidence="medium", extra={"table": pt.table.label, "column": pt.columns.get(j)}))
    return out


@register("NUM-09")
def percent_points_and_logs(pm, ctx):
    """NUM-09. "From A% to B%, an increase of C percentage points" where C is the relative
    change (or "C%" where C is the point change); a percent claim about a share outcome that
    matches 100 times the coefficient rather than the relative change; and coefficients on log
    outcomes quoted as percentages when exp(b) - 1 differs materially from b.

    Misses: log outcomes not labelled "log" or "ln" in the table or sentence, and point/percent
    mix-ups in sentences without both levels or a matching table estimate."""
    paper = _paper(pm)
    candidates = sum(1 for ch in paper.changes if ch.c is not None and ch.c.unit in ("%", "pp"))
    evaluated = candidates
    gen = _change_findings(paper, ctx, "NUM-09")
    while True:
        try:
            yield next(gen)
        except StopIteration:
            break
    for f in list(_log_findings(paper, ctx)) + list(_share_percent_findings(paper, ctx)) + list(
            _headline_unit_findings(paper, ctx)):
        if f is None:
            candidates += 1
            evaluated += 1
        else:
            yield f
    _coverage(ctx, "NUM-09", evaluated, candidates, "percent and log statements",
              "no percent or percentage-point changes and no log outcomes", [])


_LOG_COL = re.compile(r"\blog\b|\bln\b|log\s*\(|ln\s*\(|\blogs\b|logged|\blog-", re.I)


def _headline_unit_findings(paper: _Paper, ctx):
    """A headline change in percent that equals the body's percentage-point change (or the reverse)
    while the measure its unit names gives a different number."""
    for res in _assess_claims(paper):
        cl = res["claim"]
        yield None
        if res["verdict"] != "other_measure":
            continue
        sent, tok, best = cl["sent"], cl["tok"], res["best"]
        cand = best["cand"]
        rel = best["ranges"].get("relative")
        ab = best["ranges"]["absolute"]
        rel_txt = f"{(rel[0] + rel[1]) / 2:.1f}%" if rel else "n/a"
        ab_txt = f"{(ab[0] + ab[1]) / 2:.1f} percentage points"
        if tok.unit == "%":
            title = "Percentage-point change reported as percent"
            problem = (f"{'The abstract' if sent.role == 'abstract' else 'The conclusion'} states a change of "
                       f"{tok.text()}. {_cap(cand.desc)}: {ab_txt}, or {rel_txt} in relative terms. The headline "
                       f"matches the percentage-point change but calls it percent.")
        else:
            title = "Relative change reported in percentage points"
            problem = (f"{'The abstract' if sent.role == 'abstract' else 'The conclusion'} states a change of "
                       f"{tok.text()}. {_cap(cand.desc)}: {ab_txt}, or {rel_txt} in relative terms. The headline "
                       f"matches the relative change but calls it percentage points.")
        yield _emit(ctx, "NUM-09", title, "major", problem, block=sent.block, quote=sent.quote(),
                    evidence=[_cr(cand.formula + "; and B - A in points", cand.inputs,
                                  {"relative": rel_txt, "points": ab_txt},
                                  "half a unit in the last printed digit of each input and of the claim")],
                    trajectory=[f"Extracted the claim \"{sent.quote(*cl['span'])}\" from {sent.where()}.",
                                f"Matched it to {cand.desc} (word overlap {best['sim']:.2f}).",
                                "The claimed value equals the other measure, not the one its unit names."],
                    fix=Fix("investigate", detail=f"Say {ab_txt}, or {rel_txt} relative to the base.",
                            resolved_when="The headline names the measure that its number equals."),
                    status="likely", confidence="medium", related=[_rel(cand.block, cand.quote)],
                    extra={"claimed": tok.text(), "points": ab_txt, "relative": rel_txt})


def _log_findings(paper: _Paper, ctx):
    """A percent change quoted for a coefficient on a log outcome. The sentence must link to
    the coefficient: it names the table, says "log", or names the outcome of the log column."""
    log_words = {"log", "logs", "logged", "ln", "natural"}
    for sent in paper.sents:
        if sent.has_citation:
            continue
        pct_toks = [t for t in sent.tokens if t.unit == "%" and t.kind == "result"]
        if not pct_toks:
            continue
        in_sentence_log = bool(_LOG_COL.search(sent.norm))
        refs = paper.tables_for(sent)
        words = _stems(sent.norm)
        for tok in pct_toks:
            matches = []
            if in_sentence_log:
                for t2 in sent.tokens:
                    if t2 is not tok and t2.unit is None and t2.kind == "result" and t2.rep.decimals >= 2 and abs(t2.value) < 3:
                        matches.append((t2.rep, None, None))
            for pt in paper.reg_tables():
                for est in pt.estimates:
                    col_label = pt.columns.get(est.col, "")
                    if est.coef.num is None or not _LOG_COL.search(col_label + " " + (pt.table.caption or "")):
                        continue
                    outcome = {w for w in _stems(re.sub(r"\([^)]*\)", " ", col_label)) if w not in log_words}
                    linked = pt in refs or in_sentence_log or (outcome and outcome <= words)
                    if linked:
                        matches.append((est.coef.num, pt, est))
            for b, pt, est in matches:
                if not st.overlaps(tok.rep.abs_interval, (100 * b.abs_interval[0], 100 * b.abs_interval[1])):
                    continue
                yield None
                exact = st.magnitude(st.log_points_to_percent(b))
                if st.overlaps(st.claim_range(tok.rep), exact):
                    continue
                gap = abs((exact[0] + exact[1]) / 2 - abs(tok.value))
                if gap < 1.0 or gap < 0.1 * abs(tok.value):
                    continue
                exact_mid = (exact[0] + exact[1]) / 2
                related = [_rel(pt.block, pt.row_quote(est.row))] if pt else []
                where = f"{pt.name}, column \"{pt.columns.get(est.col, '')}\"" if pt else "this sentence"
                yield _emit(ctx, "NUM-09", "Log-point coefficient read as a percent change", "major" if gap >= 5 else "minor",
                            f"A coefficient of {b.raw} on a log outcome ({where}) implies a change of "
                            f"100 (exp({b.raw}) - 1) = {exact_mid:.1f}%, not {tok.text()}.",
                            block=sent.block, quote=sent.quote(),
                            evidence=[_cr("100 (exp(b) - 1)", {"b": b.raw, "stated": tok.text()},
                                          f"{exact_mid:.2f}% (range {exact[0]:.2f} to {exact[1]:.2f})",
                                          "rounding interval of b; flagged only when the gap is at least 1 point and 10%")],
                            trajectory=[f"Found {tok.text()} next to a log-outcome coefficient {b.raw} in {sent.where()}.",
                                        "Computed the exact percent change exp(b) - 1."],
                            fix=Fix("investigate", detail=f"Report {exact_mid:.1f}% or say that {tok.text()} is "
                                                          "an approximation in log points.",
                                    resolved_when="The percent change quoted for a log outcome equals 100 (exp(b) - 1), "
                                                  "or the text says it reports log points."),
                            status="likely", confidence="medium", related=related, extra={"b": b.raw, "stated": tok.text()})
                break


def _share_percent_findings(paper: _Paper, ctx):
    """A percent effect quoted for a share outcome that equals 100 x the coefficient (points),
    while the relative change from the control mean is different."""
    for sent in paper.sents:
        if sent.has_citation or sent.role in ("abstract", "conclusion"):
            continue
        tables = paper.tables_for(sent)
        if not tables:
            continue
        for tok in sent.tokens:
            if tok.unit != "%" or tok.kind != "result":
                continue
            before = sent.norm[max(0, tok.s - 60):tok.s]
            if not re.search(r"\bby\s+(?:about\s+|approximately\s+)?$", before):
                continue
            for pt in tables:
                for est in pt.estimates:
                    cm = pt.column_values("control_mean", est.col)
                    b = est.coef.num
                    if cm is None or cm.num is None or b is None or not (0 < cm.num.value < 1) or abs(b.value) >= 1:
                        continue
                    if not st.overlaps(tok.rep.abs_interval, (100 * b.abs_interval[0], 100 * b.abs_interval[1])):
                        continue
                    rel = st.quotient_range(b, cm.num)
                    yield None
                    if rel is None or st.overlaps(tok.rep.abs_interval, st.magnitude((100 * rel[0], 100 * rel[1]))):
                        continue
                    rel_mid = 100 * (rel[0] + rel[1]) / 2
                    yield _emit(ctx, "NUM-09", "Percentage-point effect reported as percent", "major",
                                f"{pt.name}, row \"{est.label}\": the coefficient {b.raw} on a share with control mean "
                                f"{cm.num.raw} is {100 * b.value:g} percentage points, or {abs(rel_mid):.1f}% of the "
                                f"control mean. The text says {tok.text()}.",
                                block=sent.block, quote=sent.quote(),
                                evidence=[_cr("points = 100 b; percent = b / control mean", {"b": b.raw, "control mean": cm.num.raw},
                                              {"points": f"{100 * b.value:g}", "percent": f"{abs(rel_mid):.1f}%"},
                                              "rounding intervals of b and the control mean")],
                                trajectory=[f"Matched {tok.text()} in {sent.where()} to {pt.name}, row \"{est.label}\".",
                                            "Compared it with the point and percent readings of the coefficient."],
                                fix=Fix("investigate", detail=f"Say {100 * abs(b.value):g} percentage points, or "
                                                              f"{abs(rel_mid):.0f}% relative to the control mean.",
                                        resolved_when="Effects on shares are stated in percentage points, or as percent "
                                                      "of a named base."),
                                status="likely", confidence="medium",
                                related=[_rel(pt.block, pt.row_quote(est.row))],
                                extra={"table": pt.table.label, "row": est.label})


# ================================================================ NUM-04: GRIM, DEBIT, bounds
_NUMWORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11}
_SCALE_K = re.compile(r"\b(?P<k>\d{1,2}|two|three|four|five|six|seven|eight|nine|ten|eleven)[-\s]point\s+(?:likert[-\s])?"
                      r"(?:rating\s+)?(?:scale|item|likert)", re.I)
_SCALE_AB = re.compile(r"\b(?:scale\s+(?:from|of|ranging\s+from)\s+|from\s+|on\s+a\s+)?(?P<a>-?\d{1,2})\s*(?:-|to)\s*(?P<b>\d{1,3})"
                       r"\s*(?:\(|point\s+)?\s*(?:likert[-\s])?scale", re.I)
_SCALE_AB2 = re.compile(r"\bscale\s+(?:from|of|ranging\s+from)\s+(?P<a>-?\d{1,2})\s*(?:\([^)]*\)\s*)?(?:-|to)\s*(?P<b>\d{1,3})", re.I)
_MEAN = re.compile(rf"\b(?:mean|average|avg\.?)\b(?:\s+[\w-]+){{0,8}}?\s+(?:was|is|of|equals|=|:|at)\s+(?P<m>{_SNUM})|"
                   rf"\b(?:averag(?:ed|es)|scor(?:ed|es)\s+on\s+average|rated\s+[\w\s-]{{0,40}}?\s+(?:at\s+)?an\s+average\s+of)\s+(?P<m2>{_SNUM})|"
                   rf"(?<![\w.])M\s*=\s*(?P<m3>{_SNUM})", re.I)
_SD = re.compile(rf"(?:\bSD\b|\bs\.d\.|standard\s+deviation|std\.?\s*dev\.?)\s*(?:=|of|:|is|was)?\s*(?P<sd>\d*\.?\d+)", re.I)
_N_ANY = re.compile(rf"\b[Nn]\s*=\s*(?P<n>\d[\d,]*)(?![\d.])|(?P<n2>\d[\d,]*)(?![\d.,%])\s+(?:[A-Za-z-]+\s+){{0,2}}?(?:{_PEOPLE})\b", re.I)
_MULTI_ITEM = re.compile(r"\b(?:index|composite|items|item\s+scale|average\s+of|mean\s+of\s+(?:the\s+)?\w+\s+items|sum\s+score|"
                         r"subscale|factor\s+score|aggregate)\b", re.I)
_ITEMS_K = re.compile(r"\b(?P<k>\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)[-\s]item\b|\b(?:of|across)\s+"
                      r"(?P<k2>\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)\s+items\b", re.I)
_SHARE_N = re.compile(rf"(?P<p>\d+(?:\.\d+)?)\s*%\s+of\s+(?:the\s+|our\s+|all\s+)?(?P<n>\d[\d,]*)\s+(?:[A-Za-z-]+\s+){{0,2}}?(?:{_PEOPLE})\b", re.I)


_NOT_A_MEAN = re.compile(r"effect|difference|change|gap|increase|decrease|gain|impact|treatment|marginal|growth", re.I)


def _int_word(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    s = s.lower()
    return _NUMWORDS.get(s) or (int(s) if s.isdigit() else None)


@register("NUM-04")
def grim_debit_bounds(pm, ctx):
    """NUM-04. GRIM for means of integer ratings and for percentages of a stated N; DEBIT for
    means and SDs of binary variables; standard-deviation bounds and means outside the scale;
    GRIMMER as a cautious, needs-human flag. Inputs must sit in one sentence (mean, scale, N) or
    in a summary table with Mean, SD and N columns.

    Misses: multi-item scales without a stated number of items (skipped, since GRIM would
    over-flag), N stated in another sentence, and means of non-integer data."""
    paper = _paper(pm)
    candidates = evaluated = 0
    notes: list = []
    for sent in paper.sents:
        norm = sent.norm
        if sent.has_citation:
            continue
        mm = next((m for m in _MEAN.finditer(norm) if not _NOT_A_MEAN.search(m.group(0))), None)
        sk = _SCALE_K.search(norm)
        sab = _SCALE_AB.search(norm) or _SCALE_AB2.search(norm)
        scale = sk or sab
        shares = list(_SHARE_N.finditer(norm))
        if mm and scale and abs(scale.start() - mm.end()) > 100 and abs(mm.start() - scale.end()) > 100:
            scale = sk = sab = None  # the scale belongs to another part of the sentence
        if mm and (sk or sab):
            candidates += 1
            mean_raw = mm.group("m") or mm.group("m2") or mm.group("m3")
            ns = [int((m.group("n") or m.group("n2")).replace(",", "")) for m in _N_ANY.finditer(norm)]
            ns = sorted(set(ns))
            if len(ns) != 1:
                notes.append(f"{sent.block.anchor.label()}: a mean on a rating scale without a single N in its sentence")
                continue
            n = ns[0]
            if sk:
                k = _int_word(sk.group("k"))
                bounds = [(1, k), (0, k - 1)] if k else None
            else:
                bounds = [(int(sab.group("a")), int(sab.group("b")))]
            items = 1
            ik = _ITEMS_K.search(norm)
            if ik:
                items = _int_word(ik.group("k") or ik.group("k2")) or 0
            elif _MULTI_ITEM.search(norm):
                notes.append(f"{sent.block.anchor.label()}: a multi-item scale without a stated number of items, "
                             "so GRIM was not applied")
                continue
            if not items:
                continue
            evaluated += 1
            sdm = _SD.search(norm[mm.end():]) or _SD.search(norm)
            yield from _grim_sentence(ctx, sent, mean_raw, n, items, bounds, sdm.group("sd") if sdm else None,
                                      bool(ik), (mm.start(), mm.end()))
        for m in shares:
            candidates += 1
            p = st.reported(m.group("p"))
            n = int(m.group("n").replace(",", ""))
            if p is None or n <= 0:
                continue
            evaluated += 1
            res = st.grim(m.group("p"), n, percent=True)
            if not res.testable or res.consistent:
                continue
            yield _emit(ctx, "NUM-04", f"Percentage impossible for {n} people (GRIM)", "major",
                        f"{p.raw}% of {n} is {p.value * n / 100:.2f} people. No whole number of people out of {n} "
                        f"gives a share that rounds to {p.raw}%; the nearest possible shares are {', '.join(res.nearest)}.",
                        block=sent.block, quote=sent.clause(m.start(), m.end()),
                        evidence=[_cr("an integer count k with 100 k / N within [p - half unit, p + half unit]",
                                      {"share": p.raw + "%", "N": n},
                                      f"N x interval = {st.fmt_range(res.sum_interval, 3)}: no integer",
                                      "half a unit in the last printed digit; ties rounded either way")],
                        trajectory=[f"Found \"{sent.quote(m.start(), m.end())}\" in {sent.where()}.",
                                    "Checked whether a whole number of people gives this share (GRIM for percentages)."],
                        fix=Fix("investigate", detail="Recompute the share from the count, or state the N it is based on.",
                                resolved_when=f"The share times N is a whole number within rounding."),
                        status="likely", confidence="high", extra={"share": p.raw, "n": n})
    for pt in paper.tables:
        for f in _table_summary_checks(pt, ctx):
            if f is None:
                candidates += 1
                evaluated += 1
            else:
                yield f
    _coverage(ctx, "NUM-04", evaluated, candidates, "means and shares with a stated N",
              "no means or shares of integer or binary data with a stated N", notes)


def _grim_sentence(ctx, sent: Sent, mean_raw: str, n: int, items: int, bounds, sd_raw, items_stated: bool, mspan):
    quote = sent.quote()
    res = st.grim(mean_raw, n, items)
    item_txt = f"{items} items" if items > 1 else "one integer rating"
    if res.testable and not res.consistent:
        unit = 1 / (n * items)
        yield _emit(ctx, "NUM-04", f"Mean impossible for {n} integer ratings (GRIM)", "major",
                    f"A mean of {n} responses on an integer scale ({item_txt} each) must be a multiple of 1/{n * items} "
                    f"= {unit:.4g}. No integer total gives a mean that rounds to {mean_raw}: {mean_raw} x {n * items} = "
                    f"{float(st.reported(mean_raw).exact) * n * items:.2f}, and the nearest possible means are "
                    f"{' and '.join(res.nearest)}.",
                    block=sent.block, quote=quote,
                    evidence=[_cr("an integer total T with T / (N x items) within [M - half unit, M + half unit]",
                                  {"mean": mean_raw, "N": n, "items": items, "decimals": res.places},
                                  f"N x [{res.interval[0]:g}, {res.interval[1]:g}] = [{res.sum_interval[0]:g}, "
                                  f"{res.sum_interval[1]:g}] contains no integer; nearest possible means "
                                  f"{', '.join(res.nearest)}",
                                  "half a unit in the last printed decimal; ties rounded either way",
                                  share_of_values_impossible=round(res.share_inconsistent, 3))],
                    trajectory=[f"Found the mean {mean_raw}, an integer rating scale and N = {n} in {sent.where()} "
                                f"({sent.block.anchor.label()}).",
                                f"Assumed {item_txt} per respondent" + (" (stated)." if items_stated else
                                                                        ", since no items are mentioned."),
                                f"GRIM: N x mean interval = [{res.sum_interval[0]:g}, {res.sum_interval[1]:g}], no integer."],
                    fix=Fix("investigate", detail=f"Recompute the mean from the {n} ratings. If fewer people answered "
                                                  "this item, report that N.",
                            resolved_when="The reported mean times the N that answered the item is a whole number, "
                                          "within rounding."),
                    status="likely", confidence="high" if not items_stated or items == 1 else "medium",
                    extra={"mean": mean_raw, "n": n, "items": items, "test": "GRIM"})
        return
    if bounds:
        m = st.reported(mean_raw)
        inside = [b for b in bounds if m.hi >= b[0] - st.EPS and m.lo <= b[1] + st.EPS]
        if not inside:
            yield _emit(ctx, "NUM-04", "Mean outside the scale", "major",
                        f"The mean {mean_raw} lies outside the scale "
                        f"({' or '.join(f'{a} to {b}' for a, b in bounds)}).",
                        block=sent.block, quote=quote,
                        evidence=[_cr("scale minimum <= mean <= scale maximum", {"mean": mean_raw, "scale": bounds},
                                      "outside", "half a unit in the last printed decimal")],
                        trajectory=[f"Found the mean {mean_raw} and its scale in {sent.where()}.",
                                    "Compared the mean with the scale bounds."],
                        fix=Fix("investigate", detail="Correct the mean or the description of the scale.",
                                resolved_when="The mean lies within the scale."),
                        status="confirmed", confidence="high",
                        extra={"mean": mean_raw, "test": "bounds"})
            return
        if sd_raw and items == 1:
            results = [st.sd_bounds(mean_raw, sd_raw, n, a, b, integer=True) for a, b in inside]
            if all(r.testable and r.consistent is False for r in results):
                feas = results[0].feasible
                yield _emit(ctx, "NUM-04", "Standard deviation impossible for the scale", "major",
                            f"With {n} integer ratings from {inside[0][0]} to {inside[0][1]} and mean {mean_raw}, the "
                            f"SD must lie between {feas[0]:.2f} and {feas[1]:.2f}; the text reports {sd_raw}.",
                            block=sent.block, quote=quote,
                            evidence=[_cr("extremes of the sum of squares for integer data with the given sum and bounds",
                                          {"mean": mean_raw, "SD": sd_raw, "N": n, "scale": inside},
                                          {"feasible SD": st.fmt_range(feas, 3)},
                                          "rounding intervals of mean and SD; sample SD")],
                            trajectory=[f"Found mean {mean_raw}, SD {sd_raw}, N = {n} and the scale in {sent.where()}.",
                                        "Computed the smallest and largest SD possible for integer data."],
                            fix=Fix("investigate", detail="Recompute the SD from the data.",
                                    resolved_when="The SD lies within the range possible for the scale, mean and N."),
                            status="likely", confidence="medium", extra={"mean": mean_raw, "sd": sd_raw, "test": "SD bounds"})
                return
            gm = [st.grimmer(mean_raw, sd_raw, n, b) for b in inside]
            if all(g.testable and g.consistent is False and g.grim_consistent for g in gm):
                yield _emit(ctx, "NUM-04", "Standard deviation may be impossible (GRIMMER)", "minor",
                            f"No set of {n} integer ratings with mean {mean_raw} gives an SD that rounds to {sd_raw}: "
                            f"the implied sum of squares is never a whole number of the right parity.",
                            block=sent.block, quote=quote,
                            evidence=[_cr("sum of squares Q = (N - 1) SD^2 + T^2 / N must be an integer with the parity "
                                          "of the total T", {"mean": mean_raw, "SD": sd_raw, "N": n, "scale": inside},
                                          "no admissible Q", "rounding intervals of mean and SD; sample SD")],
                            trajectory=[f"Found mean {mean_raw}, SD {sd_raw} and N = {n} in {sent.where()}.",
                                        "Ran GRIMMER for single-item integer data. Kept as a cautious flag."],
                            fix=Fix("investigate", detail="Check the SD against the raw data.",
                                    resolved_when="A person has confirmed the SD from the data."),
                            status="needs_human", confidence="low", extra={"mean": mean_raw, "sd": sd_raw, "test": "GRIMMER"})


_HEADER_MEAN = re.compile(r"^(?:mean|average|avg\.?|share|proportion)$", re.I)
_HEADER_SD = re.compile(r"^(?:sd|s\.d\.|std\.?\s*dev\.?|standard\s+deviation|std\.?)$", re.I)
_HEADER_N = re.compile(r"^(?:n|obs\.?|observations|count)$", re.I)
# A 0/1 variable. A plain "share" is not one: an income share is continuous, a share of respondents is binary.
_BINARY_LABEL = re.compile(r"\(\s*=\s*1\b|\bdummy\b|\bindicator\b|\bbinary\b|\b0/1\b|"
                           r"\b(?:share|fraction|proportion|percent(?:age)?)\s+(?:of\s+)?(?:the\s+|all\s+)?(?:respondents|"
                           r"households|individuals|people|persons|participants|subjects|workers|women|men|borrowers|"
                           r"families|firms|sample)\b|"
                           r"^(?:female|male|married|employed|unemployed|white|black|college|treated|yes)\b", re.I)
# A variable between 0 and 1 that may be continuous: only the bound SD <= sqrt(m (1 - m)) applies to it.
_SHARE_LABEL = re.compile(r"\b(?:share|fraction|proportion)\b", re.I)


def _share_sd_excess(mean, sd, n: int) -> Optional[float]:
    """The largest SD any variable between 0 and 1 with this mean can have (Bhatia and Davis 2000), when the
    reported SD exceeds it beyond rounding; otherwise None."""
    half_m = 0.5 * 10 ** -(mean.decimals or 0)
    half_s = 0.5 * 10 ** -(sd.decimals or 0)
    lo, hi = max(0.0, mean.value - half_m), min(1.0, mean.value + half_m)
    m = 0.5 if lo <= 0.5 <= hi else (hi if hi < 0.5 else lo)
    bound = math.sqrt(m * (1 - m) * (n / (n - 1) if n > 1 else 1.0))
    return bound if sd.value - half_s > bound + 1e-12 else None


def _share_bound_finding(ctx, pt: ParsedTable, row: int, label: str, mean, sd, n: int, bound: float, layout: str):
    quote = pt.row_quote(row)
    if not quote:
        return None
    return _emit(ctx, "NUM-04", f"SD larger than any share with this mean can have in {pt.name}", "major",
                 f"{pt.name}, row \"{label}\": a variable between 0 and 1 with mean {mean.raw} has an SD of at most "
                 f"{bound:.3f} (N = {n}), so the reported SD {sd.raw} is impossible: the mean, the SD or the scale is "
                 "wrong.",
                 block=pt.block, quote=quote,
                 evidence=[_cr("for any variable in [0, 1]: SD <= sqrt(m (1 - m)), times sqrt(N / (N - 1)) for a "
                               "sample SD (Bhatia and Davis, 2000)",
                               {"mean": mean.raw, "SD": sd.raw, "N": n, "layout": layout},
                               {"largest possible SD": round(bound, 4)}, "rounding intervals of the mean and SD")],
                 trajectory=[f"Read {layout} in {pt.name}.", f"Row \"{label}\" is a share, so it lies between 0 and 1.",
                             "Compared its SD with the largest SD a variable in [0, 1] with that mean can have."],
                 fix=Fix("investigate", detail="Recompute the SD, or state the scale if the variable is not a share.",
                         resolved_when="The SD is at most sqrt(m (1 - m)) for the reported mean."),
                 status="likely", confidence="medium", extra={"table": pt.table.label, "row": label, "test": "share bound"})


def _debit_finding(ctx, pt: ParsedTable, row: int, label: str, mean: st.Reported, sd: st.Reported, n: int, res,
                   layout: str):
    quote = pt.row_quote(row)
    if not quote:
        return None
    sds = ", ".join(f"{c[1]:.3f}" for c in res.candidates[:3])
    return _emit(ctx, "NUM-04", f"Mean and SD inconsistent for a binary variable in {pt.name} (DEBIT)", "major",
                 f"{pt.name}, row \"{label}\": a 0/1 variable with mean {mean.raw} and N = {n} "
                 + (f"has SD {sds}, not {sd.raw}." if res.grim_consistent else "cannot have this mean: no count of "
                                                                                "ones gives it."),
                 block=pt.block, quote=quote,
                 evidence=[_cr("SD = sqrt(k (N - k) / (N (N - 1))) for k ones among N (or the population formula)",
                               {"mean": mean.raw, "SD": sd.raw, "N": n, "layout": layout},
                               {"admissible SDs": sds or "none"}, "rounding intervals of the mean and SD")],
                 trajectory=[f"Read {layout} in {pt.name}.", f"Row \"{label}\" is a binary variable.", "Ran DEBIT."],
                 fix=Fix("investigate", detail="Recompute the mean and SD of the binary variable.",
                         resolved_when="The SD equals sqrt(m (1 - m) N / (N - 1)) for the reported mean, within rounding."),
                 status="likely", confidence="medium", extra={"table": pt.table.label, "row": label, "test": "DEBIT"})


def _table_summary_checks(pt: ParsedTable, ctx):
    """DEBIT for binary rows of a summary table: Mean, SD and N columns, or a mean with its SD
    in parentheses below (when the note says so) and N in an Observations row."""
    if pt.block is None:
        return
    if pt.estimates and pt.paren == "sd":
        for est in pt.estimates:
            label = est.label
            n_cell = pt.column_values("observations", est.col)
            if (est.se.kind != "brack" or n_cell is None or n_cell.num is None or n_cell.num.decimals
                    or est.coef.num is None or est.se.num is None or not (0 <= est.coef.num.value <= 1)):
                continue
            n = int(n_cell.num.value)
            if not _BINARY_LABEL.search(label or ""):
                if _SHARE_LABEL.search(label or ""):
                    bound = _share_sd_excess(est.coef.num, est.se.num, n)
                    yield None
                    if bound is not None:
                        f = _share_bound_finding(ctx, pt, est.row, label, est.coef.num, est.se.num, n, bound,
                                                 "means with standard deviations in parentheses")
                        if f is not None:
                            yield f
                continue
            res = st.debit(est.coef.num.raw, est.se.num.raw, n)
            if not res.testable:
                continue
            yield None
            if not res.consistent:
                f = _debit_finding(ctx, pt, est.row, label, est.coef.num, est.se.num, n, res,
                                   "means with standard deviations in parentheses")
                if f is not None:
                    yield f
        return
    if pt.estimates:
        return
    header_rows = [i for i, k in enumerate(pt.row_kinds) if k in ("header", "colnums")]
    cols = {}
    for i in header_rows:
        for j, cell in enumerate(pt.table.rows[i][1:]):
            c = cell.strip()
            if _HEADER_MEAN.match(c):
                cols.setdefault("mean", j)
            elif _HEADER_SD.match(c):
                cols.setdefault("sd", j)
            elif _HEADER_N.match(c):
                cols.setdefault("n", j)
    if not {"mean", "sd", "n"} <= set(cols):
        return
    for i, kind in enumerate(pt.row_kinds):
        if kind != "values":
            continue
        label = pt.table.rows[i][0].strip()
        binary = bool(_BINARY_LABEL.search(label))
        if not binary and not _SHARE_LABEL.search(label):
            continue
        row = pt.cells[i]
        try:
            mean, sd, n = row[cols["mean"]], row[cols["sd"]], row[cols["n"]]
        except IndexError:
            continue
        if mean.num is None or sd.num is None or n.num is None or n.num.decimals or not (0 <= mean.num.value <= 1):
            continue
        if not binary:
            bound = _share_sd_excess(mean.num, sd.num, int(n.num.value))
            yield None
            if bound is not None:
                f = _share_bound_finding(ctx, pt, i, label, mean.num, sd.num, int(n.num.value), bound,
                                         "Mean, SD and N columns")
                if f is not None:
                    yield f
            continue
        res = st.debit(mean.num.raw, sd.num.raw, int(n.num.value))
        if not res.testable:
            continue
        yield None
        if not res.consistent:
            f = _debit_finding(ctx, pt, i, label, mean.num, sd.num, int(n.num.value), res, "Mean, SD and N columns")
            if f is not None:
                yield f


# ================================================================ NUM-05: sample sizes and flow
_N_MENTION = re.compile(rf"(?<![\d.,])(?P<n>\d{{1,3}}(?:,\d{{3}})+|\d+)(?![\d.,%])\s+(?P<mods>(?:[A-Za-z][\w-]*\s+){{0,3}}?)(?P<noun>{_PEOPLE})\b", re.I)
# Words between a number and a noun that show the number does not count those people: "2.48 visits per
# employee" is a rate, "week 8 if the participant" an index followed by a clause.
_NOT_COUNT_MODS = re.compile(r"\b(?:per|if|the|a|an|and|or|to|of|for|in|at|on|by|with|when|than|that|as|from|is|are|"
                             r"was|were|be|been|each|every)\b", re.I)
_INDEX_BEFORE = re.compile(r"\b(?:week|day|month|year|wave|round|session|column|table|panel|section|figure|model|"
                           r"specification|step|stage|phase|part|grade|level|item|question|line|page|footnote|appendix|"
                           r"arm|group|cohort|block|period|quarter|semester)s?\s+$", re.I)
_TOGETHER_BEFORE = re.compile(r"\b(?:together|between\s+them|combined|jointly|in\s+all)\s+(?:have|had|has|hold|held|"
                              r"contain\w*|account\s+for|make\s+up|number)\s+$", re.I)
_SUBSET_AFTER = re.compile(r"^\s*(?:who|that|whom|of\s+whom|of\s+which|in\s+the\s+(?:treatment|control|pilot|first|second|"
                           r"comparison)|in\s+each|per\b|each\b|assigned\s+to|in\s+(?:our\s+)?(?:pilot|treatment|control)|"
                           r"from\s+the|with(?:out)?\s+(?:a|an|no|missing|complete|zero)|did\b|were\s+(?:excluded|dropped|"
                           r"removed|assigned)|(?:are|were)\s+in)", re.I)
_SUBSET_MODS = re.compile(r"\b(?:pilot|treated|treatment|control|remaining|excluded|additional|female|male|other|eligible|"
                          r"new|first|second|third|last|final|inattentive|attentive|active|inactive|selected|randomly)\b", re.I)
_STAGE = re.compile(r"\b(?:recruit\w*|invit\w*|contact\w*|eligib\w*|enrolled|complet\w*|finish\w*|remain\w*|retain\w*|"
                    r"exclud\w*|drop\w*|attrit\w*|respond\w*|start\w*|screen\w*|approach\w*|lost|left|failed)\b", re.I)
_APPROX_BEFORE = re.compile(rf"\b(?:{_QUAL}|nearly|over|almost|more\s+than|roughly)\s+$", re.I)
_OF_BEFORE = re.compile(r"\b(?:of|among|out\s+of)\s+(?:the|these|those|them|our)?\s*$", re.I)


_STUDY_LABEL = re.compile(r"\b(?:Study|Experiment|Wave|Sample|Survey|Phase|Part)\s+(?:\d+|[A-Z]|I{1,3}|IV)\b")


def _sample_mentions(paper: _Paper) -> list:
    out = []
    for sent in paper.sents:
        if sent.has_citation:
            continue
        norm = sent.norm
        for m in _N_MENTION.finditer(norm):
            tok = _tok_at(sent, m.start("n"))
            if tok is None or tok.kind not in ("count", "result") or tok.unit or tok.cur:
                continue  # "94 percent of households" and "$2,000 ... for a household" are not head counts
            if "." in (tok.raw or "") or tok.rep.value != int(tok.rep.value):
                continue  # a decimal such as 2.48 is never a head count
            if re.match(r"\s*(?:percent|per\s+cent|percentage|pct)\b", m.group("mods") or "", re.I):
                continue
            if _NOT_COUNT_MODS.search(m.group("mods") or ""):
                continue
            if _INDEX_BEFORE.search(norm[max(0, m.start() - 20):m.start()]):
                continue  # "week 8", "column 3": an index, not a number of people
            noun = m.group("noun").lower()
            key = noun.rstrip("s") if noun not in ("people", "children", "women", "men", "families") else noun
            group = _PERSON_GROUP.get(key)
            if group is None:
                continue
            before = norm[max(0, m.start() - 40):m.start()]
            after = norm[m.end():m.end() + 50]
            clause = re.split(r"[,;:]", norm[max(0, m.start() - 60):m.start()])[-1] + norm[m.start():m.end() + 40]
            kind = "total"
            depth = norm[:m.start()].count("(") - norm[:m.start()].count(")")
            if depth > 0:
                kind = "statistic"  # "(N = 25 participants)": the N of one statistic
            elif (_SUBSET_AFTER.match(after) or _SUBSET_MODS.search(m.group("mods") or "") or _OF_BEFORE.search(before)
                  or _TOGETHER_BEFORE.search(before)):
                kind = "subset"
            elif _STAGE.search(clause):
                kind = "stage"
            elif _APPROX_BEFORE.search(before):
                kind = "approximate"
            lab = _STUDY_LABEL.search(norm) or _STUDY_LABEL.search(" ".join(sent.block.section))
            out.append({"sent": sent, "value": int(tok.rep.value), "raw": tok.raw, "group": group, "kind": kind,
                        "span": (m.start(), m.end()), "study": lab.group(0) if lab else ""})
    return out


@register("NUM-05")
def sample_sizes(pm, ctx):
    """NUM-05. Totals of the same kind of unit (employees, participants, students, ...) stated in
    the text, with "Observations" rows as supporting evidence; a mention is flagged when it
    disagrees with a value stated more often elsewhere. Also "N split into A and B" and
    "N ... excluded X ... leaving Y" arithmetic.

    Misses: totals spread over several sentences, subsamples not marked as such, and panel data
    where observations exceed people (never compared directly with a head count)."""
    paper = _paper(pm)
    mentions = _sample_mentions(paper)
    obs = []
    for pt in paper.tables:
        for col, c in pt.stats.get("observations", {}).items():
            if c.num is not None and c.num.decimals == 0:
                row = next((i for i, k in enumerate(pt.row_kinds) if k == "stat:observations"), None)
                obs.append({"value": int(c.num.value), "pt": pt, "row": row, "col": col})
    candidates = evaluated = len(mentions) + len(obs)  # every count is examined, even if none is comparable
    by_group: dict = {}
    multi_study = any(m["study"] for m in mentions)
    for mnt in mentions:
        if mnt["kind"] == "total" and (mnt["study"] or not multi_study):
            by_group.setdefault((mnt["group"], mnt["study"]), []).append(mnt)
    for (group, _study), ms in by_group.items():
        values = sorted({m["value"] for m in ms})
        if len(values) < 2:
            continue
        support = {v: sum(1 for m in ms if m["value"] == v) + (1 if any(o["value"] == v for o in obs) else 0)
                   for v in values}
        best = max(values, key=lambda v: support[v])
        if sum(1 for v in values if support[v] == support[best]) > 1:
            status = "needs_human"
        else:
            status = "likely"
        for m in ms:
            if m["value"] == best:
                continue
            others = [x for x in ms if x["value"] == best]
            ob = [o for o in obs if o["value"] == best]
            if status == "likely" and m["sent"].role not in ("abstract", "intro", "conclusion") and support[best] < 2:
                continue
            sent = m["sent"]
            related = [_rel(x["sent"].block, x["sent"].quote()) for x in others[:2]]
            if ob:
                related.append(_rel(ob[0]["pt"].block, ob[0]["pt"].row_quote(ob[0]["row"])))
            where_best = [x["sent"].where() for x in others] + [o["pt"].name + " (Observations)" for o in ob[:1]]
            orig = sent.quote(*m["span"])
            yield _emit(ctx, "NUM-05", f"Sample size of {group} disagrees across the paper", "major",
                        f"{_cap(sent.where())} gives {m['raw']} {group}, but {' and '.join(where_best)} "
                        f"give{'s' if len(where_best) == 1 else ''} {best:,}.",
                        block=sent.block, quote=sent.clause(*m["span"]),
                        evidence=[_cr("total sample sizes of the same unit stated in the paper",
                                      {"this mention": m["raw"], "elsewhere": {w: f"{best:,}" for w in where_best}},
                                      f"{m['raw']} differs from {best:,}, which has more support", "exact (counts)")],
                        trajectory=[f"Collected {len(mentions)} head counts and {len(obs)} Observations entries.",
                                    f"Kept totals of {group}, leaving out subsamples, flow stages and approximations.",
                                    f"Values found: {', '.join(f'{v:,} ({support[v]}x)' for v in values)}."],
                        fix=Fix("replace", original=orig, replacement=orig.replace(m["raw"], f"{best:,}", 1),
                                detail="If the numbers count different stages (recruited, randomized, analysed), say so.",
                                resolved_when="Every statement of the full sample size gives the same number, or the "
                                              "text explains the difference.")
                        if _verbatim(sent.block, orig) else
                        Fix("investigate", resolved_when="Every statement of the full sample size gives the same number."),
                        status=status, confidence="medium", related=related,
                        extra={"group": group, "stated": m["value"], "elsewhere": best})
    for f in _flow_findings(paper, ctx):
        if f is None:
            candidates += 1
            evaluated += 1
        else:
            yield f
    totals = sum(len(ms) for ms in by_group.values())
    _coverage(ctx, "NUM-05", evaluated, candidates, f"head counts and Observations entries ({totals} totals compared)",
              "no head counts or Observations rows", [])


_SPLIT_CUE = re.compile(r"\b(?:randomi[sz]\w*|assign\w*|allocat\w*|split|divid\w*)\b", re.I)
_ARM = re.compile(rf"(?P<n>\d[\d,]*)(?![\d.,%])\s+(?:(?:{_PEOPLE})\s+)?(?:(?:were\s+)?(?:assigned\s+)?(?:to|in|into)\s+)?(?:the\s+|a\s+|each\s+)?"
                  r"(?P<arm>control|treatment|treated|comparison|placebo|baseline|[A-Z][\w-]*)\s*(?:group|arm|condition)?\b", re.I)
_LEAVING = re.compile(r"\b(?:leaving|leaves|resulting\s+in|for\s+a\s+final\s+sample\s+of|final\s+sample\s+of|left\s+with)\s+"
                      r"(?:a\s+(?:final\s+)?(?:sample|total)\s+of\s+)?(?P<n>\d[\d,]*)", re.I)
_EXCLUDED = re.compile(rf"(?P<n>\d[\d,]*)(?![\d.,%])\s+(?:(?:{_PEOPLE}|observations?)\s+)?(?:\w+\s+){{0,2}}?"
                       r"(?:were\s+|was\s+|are\s+)?(?:excluded|dropped|removed|failed|did\s+not|were\s+lost|attrited|left)", re.I)


def _flow_findings(paper: _Paper, ctx):
    for sent in paper.sents:
        norm = sent.norm
        if sent.has_citation:
            continue
        totals = [m for m in _N_MENTION.finditer(norm)]
        lv = _LEAVING.search(norm)
        if lv and totals:
            excl = [m for m in _EXCLUDED.finditer(norm) if m.start() < lv.start()]
            total = totals[0]
            t_val = int(total.group("n").replace(",", ""))
            ex_vals = [int(m.group("n").replace(",", "")) for m in excl if m.start() != total.start()]
            left = int(lv.group("n").replace(",", ""))
            if ex_vals and total.start() < lv.start():
                yield None
                if t_val - sum(ex_vals) != left:
                    yield _emit(ctx, "NUM-05", "Participant flow does not add up", "major",
                                f"{t_val:,} minus {' and '.join(f'{v:,}' for v in ex_vals)} excluded is "
                                f"{t_val - sum(ex_vals):,}, not the {left:,} the text says remain.",
                                block=sent.block, quote=sent.quote(),
                                evidence=[_cr("total - exclusions = remaining", {"total": t_val, "exclusions": ex_vals,
                                                                                 "remaining": left},
                                              t_val - sum(ex_vals), "exact (counts)")],
                                trajectory=[f"Parsed the flow in {sent.where()}.", "Subtracted the exclusions."],
                                fix=Fix("investigate", detail="Correct the counts in the participant flow.",
                                        resolved_when="Total minus exclusions equals the remaining sample."),
                                status="likely", confidence="medium", extra={"total": t_val, "excluded": ex_vals, "left": left})
                continue
        if _SPLIT_CUE.search(norm) and totals:
            total = totals[0]
            t_val = int(total.group("n").replace(",", ""))
            arms = [m for m in _ARM.finditer(norm[total.end():])
                    if re.match(r"control|treatment|treated|comparison|placebo|baseline", m.group("arm"), re.I)]
            vals = [int(m.group("n").replace(",", "")) for m in arms]
            if len(vals) >= 2 and t_val > max(vals):
                yield None
                if sum(vals) != t_val:
                    yield _emit(ctx, "NUM-05", "Arms do not add up to the sample", "major",
                                f"The arms ({', '.join(f'{v:,}' for v in vals)}) add up to {sum(vals):,}, not {t_val:,}.",
                                block=sent.block, quote=sent.quote(),
                                evidence=[_cr("sum of arm sizes = total", {"total": t_val, "arms": vals}, sum(vals),
                                              "exact (counts)")],
                                trajectory=[f"Parsed the split in {sent.where()}.", "Added the arm sizes."],
                                fix=Fix("investigate", detail="Correct the arm sizes or the total.",
                                        resolved_when="The arm sizes add up to the total."),
                                status="likely", confidence="medium", extra={"total": t_val, "arms": vals})


# ================================================================ NUM-06: text against tables
_SUPERLATIVE = re.compile(r"\b(?:largest|highest|biggest|strongest|greatest|smallest|lowest|weakest|best|worst|maximum|minimum)\b", re.I)
# "two further estimates, not reported in Table 2, are ...": the sentence itself says the numbers are elsewhere.
# A table named by a cross-reference field is masked in the sentence text, so the pattern takes either form.
_NOT_IN_TABLE = re.compile(r"\b(?:(?:not|never)\s+(?:shown|reported|included|presented|listed|displayed|tabulated)\s+"
                           r"(?:in|on)|(?:omitted|excluded|absent)\s+from)\s+(?:the\s+)?(?:Tables?\b|" + MASK + ")", re.I)
_NOTE_NUMBER = re.compile(r"(?<![\w.])[-\u2212\u2013]?\d+\.\d+(?![\w.]*\d)")
# A sentence that says it derives its number from the table's cells ("the average of the effects ... in
# Table 2", "the pooled effect") need not find that number in a cell; the reading agent checks the arithmetic.
_DERIVED = re.compile(r"\b(?:average|mean|sum|difference|ratio|combination)\s+of\s+(?:the\s+)?(?:two\s+|three\s+|"
                      r"first\s+|second\s+)?(?:effects?|coefficients?|estimates?|columns?|values?|rows?)\b|\bpooled\b|"
                      r"\bderived\s+from\b|\bimplied\s+by\b", re.I)


def _in_notes(tok: Tok, pt: ParsedTable) -> bool:
    """The number is printed in the table's notes, such as a break-even value the note derives from the rows."""
    for m in _NOTE_NUMBER.finditer(pt.notes or ""):
        text = m.group(0).replace("\u2212", "-").replace("\u2013", "-")
        half = 0.5 * 10 ** -len(text.split(".")[1])
        v = abs(float(text))
        if st.overlaps(tok.rep.abs_interval, (v - half, v + half)):
            return True
    return False


def _table_numbers(pt: ParsedTable) -> list:
    out = []
    for i, row in enumerate(pt.cells):
        if pt.row_kinds[i] in ("colnums", "header"):
            continue
        for c in row:
            for r in (c.num, c.second):
                if r is not None:
                    out.append((r, c.pct))
    return out


def _derived(pt: ParsedTable, percent: bool) -> list:
    """Numbers a sentence may quote that are computed from cells. Without a unit: t = b/SE,
    b +/- 1.96 SE, b / control mean and control mean + b. In percent or points: the same
    shares times 100, and 100 (exp(b) - 1) for log outcomes. A t statistic never stands
    for a percentage."""
    out = []
    for e in pt.estimates:
        b, se = e.coef.num, e.se.num
        if b is None or se is None:
            continue
        cm = pt.column_values("control_mean", e.col)
        share = cm is not None and cm.num is not None and 0 < cm.num.value < 1
        if e.se.kind == "brack" and pt.paren == "se":
            ci = [(b.lo - 1.96 * se.hi, b.hi - 1.96 * se.lo), (b.lo + 1.96 * se.lo, b.hi + 1.96 * se.hi)]
            if percent:
                out += [(100 * lo, 100 * hi) for lo, hi in ci] if share else []
            else:
                out += [st.t_range(b, se)] + ci
        if percent and _LOG_COL.search(pt.columns.get(e.col, "") + " " + (pt.table.caption or "")):
            out.append(st.log_points_to_percent(b))
        if cm is not None and cm.num is not None:
            q = st.quotient_range(b, cm.num)
            level = (cm.num.lo + b.lo, cm.num.hi + b.hi)
            if percent:
                out += ([(100 * q[0], 100 * q[1])] if q else []) + ([(100 * level[0], 100 * level[1])] if share else [])
            else:
                out += ([q] if q else []) + [level]
    return out


def _in_cells(tok: Tok, pt: ParsedTable) -> bool:
    for r, pct in _table_numbers(pt):
        if _number_matches(tok.rep, tok.unit, r, pct):
            return True
        if tok.unit in ("%", "pp") and abs(r.value) < 1.5 and st.overlaps(tok.rep.abs_interval,
                                                                            (100 * r.abs_interval[0], 100 * r.abs_interval[1])):
            return True
    return False


def _in_table(tok: Tok, pt: ParsedTable) -> bool:
    if _in_cells(tok, pt):
        return True
    for rng in _derived(pt, percent=tok.unit in ("%", "pp")):
        if st.overlaps(tok.rep.abs_interval, st.magnitude(rng)):
            return True
    return False


@register("NUM-06")
def text_against_tables(pm, ctx):
    """NUM-06. Every number quoted in a sentence that cites "Table k" must appear in Table k,
    allowing for rounding, sign, the percent/share scale and simple derived values (t = b/SE,
    b / control mean, control mean + b, b +/- 1.96 SE). Superlatives ("the largest effect")
    and bold cells are checked against the other values in their row or column.

    Misses: numbers in sentences that do not name the table, numbers from figures, and values
    computed from several cells in other ways."""
    paper = _paper(pm)
    if not pm.tables:
        ctx.not_applicable("NUM-06", "the paper has no tables")
        return
    candidates = evaluated = 0
    for sent in paper.sents:
        tables = paper.tables_for(sent)
        if not tables or sent.has_citation:
            continue
        if re.search(r"\bFig(?:ure|\.)?s?\b", sent.norm) or _NOT_IN_TABLE.search(sent.norm) \
                or _DERIVED.search(sent.norm):
            continue
        toks = [t for t in sent.tokens if t.kind == "result" and t.rep.decimals > 0]
        for tok in toks:
            candidates += 1
            evaluated += 1
            if any(_in_table(tok, pt) or _in_notes(tok, pt) for pt in tables):
                continue
            others = [pt for pt in paper.tables if pt not in tables and _in_cells(tok, pt)]
            names = " and ".join(pt.name for pt in tables)
            near = _near_miss(tok, tables)
            problem = f"The sentence cites {names} and quotes {tok.text()}, but {names} has no such number"
            problem += (f"; {', '.join(pt.name for pt in others)} does." if others else
                        ", even allowing for rounding, sign, percent scale and simple derived values.")
            if near:
                problem += f" {near[1].name} has {near[0].raw}, which differs by {near[2]}."
            minor = bool(near) and near[2] == "one unit in the last digit"
            status = "likely" if (others or (near and not minor)) else "needs_human"
            yield _emit(ctx, "NUM-06", f"Number quoted from {names} not found there", "minor" if minor else "major",
                        problem,
                        block=sent.block, quote=sent.clause(tok.s, tok.e),
                        evidence=[_cr("search of every cell and derived value of the cited table",
                                      {"value": tok.text(), "tables": [pt.name for pt in tables]},
                                      {"found in cited table": False, "found in": [pt.name for pt in others]},
                                      "half a unit in the last printed digit; sign; percent and share scales"),
                                  Evidence(type="checked_absence", data={"scope": names, "terms": {tok.text(): 0},
                                                                         "version": "paper map"})],
                        trajectory=[f"Found a reference to {names} in {sent.where()}.",
                                    f"Searched {names} for {tok.text()} and values derived from its cells: not found."],
                        fix=Fix("investigate", detail=f"Update {tok.text()} to the value in {names}, or cite the "
                                                      "right table.",
                                resolved_when=f"Every number in the sentence appears in {names}, within rounding."),
                        status=status, confidence="medium",
                        related=[_rel(pt.block, pt.notes_quote() or pt.row_quote(0)) for pt in tables[:1]],
                        extra={"value": tok.text(), "tables": [pt.number for pt in tables]})
        if _SUPERLATIVE.search(sent.norm):
            for f in _best_value(sent, tables, ctx):
                if f is None:
                    candidates += 1
                    evaluated += 1
                else:
                    yield f
    for pt in paper.tables:
        for f in _bold_best(pt, ctx):
            if f is None:
                candidates += 1
                evaluated += 1
            else:
                yield f
    _coverage(ctx, "NUM-06", evaluated, candidates, "numbers quoted with a table reference",
              "no sentence quotes a number together with a table reference", [])


def _near_miss(tok: Tok, tables: list) -> Optional[tuple]:
    """A cell that looks like a typo of the quoted number: two adjacent digits swapped, or one
    unit apart in the last digit. Returns (Reported, table, how) or None."""
    x = tok.rep
    xd = re.sub(r"\D", "", x.raw)
    for pt in tables:
        for r, _pct in _table_numbers(pt):
            if r.decimals != x.decimals:
                continue  # the sign is ignored: text often drops it ("reduces by 0.18")
            rd = re.sub(r"\D", "", r.raw)
            if len(rd) != len(xd) or rd == xd:
                continue
            diffs = [i for i in range(len(xd)) if xd[i] != rd[i]]
            if len(diffs) == 2 and diffs[1] == diffs[0] + 1 and xd[diffs[0]] == rd[diffs[1]] and xd[diffs[1]] == rd[diffs[0]]:
                return r, pt, "two swapped digits"
            if diffs == [len(xd) - 1] and abs(abs(r.exact) - abs(x.exact)) == 2 * x.half_unit:
                return r, pt, "one unit in the last digit"
    return None


def _best_value(sent: Sent, tables: list, ctx):
    sup = _SUPERLATIVE.search(sent.norm)
    word = sup.group(0).lower()
    want_max = word in ("largest", "highest", "biggest", "strongest", "greatest", "best", "maximum")
    for tok in sent.tokens:
        if tok.kind != "result" or tok.rep.decimals == 0:
            continue
        for pt in tables:
            for e in pt.estimates:
                if e.coef.num is None or e.coef.num.exact != tok.rep.exact and abs(e.coef.num.exact) != abs(tok.rep.exact):
                    continue
                row = [x for x in pt.estimates if x.row == e.row and x.coef.num is not None]
                if len(row) < 2:
                    continue
                vals = [abs(x.coef.num.value) for x in row]
                extreme = max(vals) if want_max else min(vals)
                yield None
                if abs(abs(e.coef.num.value) - extreme) < 1e-12:
                    continue
                quote = pt.row_quote(e.row)
                yield _emit(ctx, "NUM-06", f"Value called the {word} is not the {word} in {pt.name}", "minor",
                            f"The sentence calls {tok.text()} the {word}, but row \"{e.label}\" of {pt.name} has "
                            f"{', '.join(x.coef.raw.strip() for x in row)}.",
                            block=sent.block, quote=sent.quote(),
                            evidence=[_cr(f"{'max' if want_max else 'min'} of |b| across the row",
                                          {"row": [x.coef.raw.strip() for x in row], "quoted": tok.text()},
                                          f"{extreme:g}", "exact comparison of printed values")],
                            trajectory=[f"Found \"{word}\" with {tok.text()} in {sent.where()}.",
                                        f"Compared with the other columns of row \"{e.label}\" in {pt.name}."],
                            fix=Fix("investigate", detail="Check which value is the extreme one, and in which sense.",
                                    resolved_when="The value called the extreme one is the extreme value in its row."),
                            status="needs_human", confidence="low", related=[_rel(pt.block, quote)],
                            extra={"table": pt.table.label, "row": e.label})
                return


def _bold_best(pt: ParsedTable, ctx):
    raw = pt.table.raw or ""
    if "\\textbf" not in raw or pt.block is None:
        return
    lines = [r for r in re.split(r"\\\\", raw) if "&" in r]
    for line in lines:
        cells = re.split(r"(?<!\\)&", line)
        bold = [j for j, c in enumerate(cells[1:]) if "\\textbf" in c]
        if len(bold) != 1:
            continue
        vals = []
        for c in cells[1:]:
            m = re.search(r"-?\d*\.?\d+", re.sub(r"\\textbf\{|\}", "", c))
            vals.append(float(m.group(0)) if m else None)
        nums = [v for v in vals if v is not None]
        j = bold[0]
        if vals[j] is None or len(nums) < 3:
            continue
        yield None
        if vals[j] in (max(nums), min(nums)):
            continue
        label = cells[0].strip()
        quote = None
        for i, row in enumerate(pt.table.rows):
            if row and row[0].strip() == re.sub(r"\\[a-zA-Z]+|[{}$]", "", label).strip():
                quote = pt.row_quote(i)
                break
        if not quote:
            continue
        yield _emit(ctx, "NUM-06", f"Bold value is not the best in its row in {pt.name}", "minor",
                    f"{pt.name}, row \"{label}\": the bold value {vals[j]:g} is neither the largest nor the smallest of "
                    f"{', '.join(f'{v:g}' for v in nums)}.",
                    block=pt.block, quote=quote,
                    evidence=[_cr("bold cell against max and min of its row", {"row": nums, "bold": vals[j]},
                                  {"max": max(nums), "min": min(nums)}, "exact")],
                    trajectory=[f"Read bold cells from the LaTeX source of {pt.name}.", "Compared the bold value with its row."],
                    fix=Fix("investigate", detail="Bold the best value, or say in the note what bold marks.",
                            resolved_when="The bold cell is the best value in its row, or the note explains the marking."),
                    status="needs_human", confidence="low", extra={"table": pt.table.label, "row": label})


# ================================================================ NUM-07: precision and units
_COMPARATIVE = (r"(?!\s*(?:%|percent)?\s*(?:times|fold|higher|lower|more|less|larger|smaller|greater|above|below|"
                r"bigger|of\s+the|of\s+its|relative|compared|points?|percentage))")
_SHARE_LEVEL = re.compile(rf"\b(?:share|fraction|proportion|percentage)\s+of\s+[^.;\d]{{0,60}}?\b(?:is|was|are|were|equals|of|=|"
                          rf"reached|stood\s+at)\s+(?P<v>{_NUM})\s*(?:%|percent){_COMPARATIVE}", re.I)
_PROB_LEVEL = re.compile(rf"\bprobability\s+(?:of\s+[^.;\d]{{0,60}}?\s+)?(?:is|was|of|=|equals)\s+(?P<v>{_NUM})(?!\s*%)"
                         rf"{_COMPARATIVE}", re.I)
_TIME_CONV = re.compile(rf"(?P<a>{_NUM})\s*(?P<ua>minutes?|hours?|days?|weeks?|months?|years?)\s*\(\s*(?:about\s+|approximately\s+|"
                        rf"i\.e\.,?\s+|or\s+|roughly\s+)?(?P<b>{_NUM})\s*(?P<ub>minutes?|hours?|days?|weeks?|months?|years?)\s*\)", re.I)
_TIME_UNITS = {"minute": 1, "hour": 60, "day": 1440, "week": 10080, "month": 43830, "year": 525960}


def _sig_digits(rep: st.Reported) -> int:
    digits = re.sub(r"[^\d]", "", rep.raw.split("e")[0].split("E")[0])
    return len(digits.lstrip("0")) or 1


@register("NUM-07")
def precision_and_units(pm, ctx):
    """NUM-07. False precision (a percentage with five or more significant digits, other
    results with six or more), "p = 0.000", shares above 100% and probabilities above 1, time
    conversions in parentheses, and effects on share outcomes quoted in percentage points that
    match the raw coefficient rather than 100 times it.

    Misses: units that are missing altogether, currency conversions (they need exchange rates),
    and implausible magnitudes that are still possible."""
    paper = _paper(pm)
    candidates = evaluated = 0
    for sent in paper.sents:
        if sent.has_citation:
            continue
        for tok in sent.tokens:
            if tok.kind == "result" and tok.cur is None:
                candidates += 1
                evaluated += 1
                sig = _sig_digits(tok.rep)
                if (tok.unit == "%" and sig >= 5 and tok.rep.decimals >= 2) or (tok.unit is None and sig >= 6 and tok.rep.decimals >= 4):
                    places = 1 if tok.unit == "%" else 3
                    rounded = st.round_half_up(tok.rep.exact, places)
                    yield _emit(ctx, "NUM-07", "False precision", "minor",
                                f"{tok.text()} reports {sig} significant digits, more than the data can support.",
                                block=sent.block, quote=sent.clause(tok.s, tok.e),
                                evidence=[_cr("count of significant digits", {"value": tok.text()}, sig,
                                              "flag at 5 or more for percentages, 6 or more otherwise")],
                                trajectory=[f"Listed the result numbers in {sent.where()}.", "Counted significant digits."],
                                fix=Fix("replace", original=tok.raw, replacement=rounded,
                                        resolved_when="The number is reported with the precision the data support.")
                                if _verbatim(sent.block, tok.raw) and sent.block.text.count(tok.raw) == 1 else
                                Fix("investigate", detail=f"Round to {rounded}.",
                                    resolved_when="The number is reported with the precision the data support."),
                                status="likely", confidence="medium", extra={"value": tok.text()})
        for s, e, rep in _p_reports(sent):
            candidates += 1
            evaluated += 1
            if rep.comparator == "=" and rep.value.exact == 0:
                yield _emit(ctx, "NUM-07", "p-value reported as zero", "minor",
                            f"\"{sent.quote(s, e)}\" cannot be exact: a p-value is never zero. Report p < 0.001.",
                            block=sent.block, quote=sent.quote(s, e),
                            evidence=[_cr("p > 0 for any finite test statistic", {"reported": str(rep)},
                                          "p printed as zero", "exact")],
                            trajectory=[f"Found {rep} in {sent.where()}."],
                            fix=Fix("replace", original=sent.quote(s, e), replacement=f"p < {10 ** -max(rep.value.places, 3):g}",
                                    resolved_when="Small p-values are reported as an upper bound such as p < 0.001.")
                            if _verbatim(sent.block, sent.quote(s, e)) else
                            Fix("investigate", resolved_when="Small p-values are reported as p < 0.001."),
                            status="confirmed", confidence="high", extra={"reported": str(rep)})
        for rx, limit, what in ((_SHARE_LEVEL, 100.0, "share"), (_PROB_LEVEL, 1.0, "probability")):
            for m in rx.finditer(sent.norm):
                v = st.reported(m.group("v"))
                if v is None:
                    continue
                candidates += 1
                evaluated += 1
                if v.lo > limit + st.EPS:
                    yield _emit(ctx, "NUM-07", f"Impossible {what}", "major",
                                f"A {what} of {v.raw}{'%' if what == 'share' else ''} is above the maximum of "
                                f"{limit:g}{'%' if what == 'share' else ''}.",
                                block=sent.block, quote=sent.clause(m.start(), m.end()),
                                evidence=[_cr(f"{what} <= {limit:g}", {"value": v.raw}, "above the maximum", "exact")],
                                trajectory=[f"Found a {what} level in {sent.where()}.", "Compared it with its maximum."],
                                fix=Fix("investigate", detail="Correct the value or say what it is a share of.",
                                        resolved_when=f"The {what} is at most {limit:g}."),
                                status="likely", confidence="medium", extra={"value": v.raw})
        for m in _TIME_CONV.finditer(sent.norm):
            a, b = st.reported(m.group("a")), st.reported(m.group("b"))
            ua, ub = m.group("ua").lower().rstrip("s"), m.group("ub").lower().rstrip("s")
            if a is None or b is None or ua == ub:
                continue
            candidates += 1
            evaluated += 1
            conv = (a.lo * _TIME_UNITS[ua] / _TIME_UNITS[ub], a.hi * _TIME_UNITS[ua] / _TIME_UNITS[ub])
            if st.overlaps(conv, st.claim_range(b, "about")):
                continue
            yield _emit(ctx, "NUM-07", "Unit conversion is wrong", "minor",
                        f"{a.raw} {m.group('ua')} is {conv[0]:.3g} to {conv[1]:.3g} {m.group('ub')}, not {b.raw}.",
                        block=sent.block, quote=sent.clause(m.start(), m.end()),
                        evidence=[_cr("value x unit factor", {"value": f"{a.raw} {m.group('ua')}", "stated": f"{b.raw} {m.group('ub')}"},
                                      f"{conv[0]:.4g} to {conv[1]:.4g}", "rounding interval, plus 10% for loose conversions")],
                        trajectory=[f"Found a conversion in {sent.where()}.", "Recomputed it."],
                        fix=Fix("investigate", detail="Correct the converted value.",
                                resolved_when="Both values describe the same duration."),
                        status="likely", confidence="medium", extra={"from": a.raw, "to": b.raw})
    for f in _unit_scale_findings(paper, ctx):
        if f is None:
            candidates += 1
            evaluated += 1
        else:
            yield f
    _coverage(ctx, "NUM-07", evaluated, candidates, "numbers", "no result numbers in the text", [])


def _unit_scale_findings(paper: _Paper, ctx):
    """'0.018 percentage points' when the table coefficient 0.018 is on a share outcome (0-1)."""
    regs = paper.reg_tables()
    for sent in paper.sents:
        if sent.has_citation:
            continue
        tables = paper.tables_for(sent) or regs
        for tok in sent.tokens:
            if tok.unit != "pp" or tok.kind != "result" or tok.rep.decimals < 2:
                continue
            hits = []
            for pt in tables:
                for est in pt.estimates:
                    b = est.coef.num
                    cm = pt.column_values("control_mean", est.col)
                    if b is None or cm is None or cm.num is None:
                        continue
                    if abs(b.exact) == abs(tok.rep.exact):
                        hits.append((pt, est, cm.num))
            if len(hits) != 1:
                continue
            yield None
            pt, est, cm = hits[0]
            if not (0 < cm.value < 1):
                continue
            yield _emit(ctx, "NUM-07", "Share coefficient reported in the wrong unit", "major",
                        f"{pt.name}, row \"{est.label}\": the outcome is a share (control mean {cm.raw}), so the "
                        f"coefficient {est.coef.num.raw} is {100 * abs(est.coef.num.value):g} percentage points, "
                        f"not {tok.text()}.",
                        block=sent.block, quote=sent.quote(),
                        evidence=[_cr("points = 100 x coefficient on a 0-1 outcome",
                                      {"coefficient": est.coef.num.raw, "control mean": cm.raw, "stated": tok.text()},
                                      f"{100 * abs(est.coef.num.value):g} percentage points", "exact digits")],
                        trajectory=[f"Matched {tok.text()} in {sent.where()} to {pt.name}, row \"{est.label}\".",
                                    "The control mean shows a 0-1 outcome."],
                        fix=Fix("investigate", detail=f"Say {100 * abs(est.coef.num.value):g} percentage points.",
                                resolved_when="Effects on 0-1 outcomes are quoted as 100 x the coefficient in points."),
                        status="likely", confidence="medium", related=[_rel(pt.block, pt.row_quote(est.row))],
                        extra={"table": pt.table.label, "row": est.label})


# ================================================================ BEH-09: standard errors and clustering
_RANDOMIZED_AT = [
    re.compile(r"randomi[sz](?:e|es|ed|ation)\s+(?:was\s+(?:done|conducted|carried\s+out)\s+)?at\s+the\s+"
               r"(?P<u>[a-z][a-z\s-]{1,30}?)[\s-]+level", re.I),
    re.compile(r"(?P<u>[a-z]+)[\s-]+level\s+randomi[sz]ation", re.I),
    re.compile(rf"randomly\s+assign(?:ed|s)?\s+(?:\d[\d,]*\s+)?(?:\w+\s+){{0,2}}?(?P<u>sessions|groups|classes|classrooms|schools|"
               rf"villages|households|firms|teams|days|branches|stores|{_PEOPLE})\b", re.I),
    re.compile(rf"randomi[sz]ed\s+(?:\d[\d,]*\s+)?(?:\w+\s+){{0,2}}?(?P<u>sessions|groups|classes|classrooms|schools|villages|"
               rf"households|firms|teams|days|branches|stores|{_PEOPLE})\s+(?:in)?to\b", re.I),
    re.compile(r"\beach\s+(?P<u>session|group|class|classroom|school|village|firm|day)\s+(?:was\s+)?(?:randomly\s+)?assigned", re.I),
    re.compile(r"treatments?\s+(?:were|was)\s+(?:varied|assigned|randomi[sz]ed)\s+(?:at\s+the\s+|across\s+|between\s+|by\s+)"
               r"(?P<u>[a-z]+)", re.I),
    re.compile(r"\bbetween[\s-]+(?P<u>session|group|subject)s?\s+design", re.I),
]
# The text says how standard errors are computed: "standard errors adjust for district-level clustering",
# "we cluster by session", "heteroskedasticity-robust standard errors", "delta-method standard errors".
_TEXT_SE = re.compile(
    r"standard\s+errors?\b[^.;]{0,80}?\b(?:cluster|robust|heterosk|heterosc|bootstrap|huber|eicker|sandwich|newey|"
    r"conley|delta[\s-]+method|jackknife)"
    r"|(?:robust|clustered|bootstrapped|delta[\s-]+method|heterosk\w*[\s-]+(?:robust|consistent))\s+standard\s+errors?"
    r"|\bcluster(?:ed|ing|s)?\b[^.;]{0,40}?\b(?:at|by)\s+(?:the\s+)?[a-z-]+(?:\s+[a-z-]+)?[\s-]+level"
    r"|\b[a-z]+[\s-]+level\s+clustering|\bwe\s+cluster\b|\bclustered\s+(?:at|by)\b", re.I)
_FEW_FIX = re.compile(r"wild\s+(?:cluster\s+)?(?:\w+\s+)?bootstrap|randomi[sz]ation\s+inference|permutation|\bcr2\b|"
                      r"bell[\s-]+mccaffrey|few\s+clusters|small[\s-]+sample\s+correction", re.I)


def _count_of_unit(paper: _Paper, unit: str) -> Optional[int]:
    """The number of clusters when the text says how many there are, such as "We ran 12 sessions"."""
    base = re.sub(r"(?:es|s)$", "", unit.strip().lower().split()[-1])
    if not base:
        return None
    values = set()
    for sent in paper.sents:
        for m in re.finditer(rf"\b(?P<n>\d{{1,4}})\s+(?:[a-z-]+\s+){{0,2}}?{re.escape(base)}(?:e?s)?\b", sent.norm, re.I):
            values.add(int(m.group("n")))
    return max(values) if values else None


def _assignment_unit(paper: _Paper) -> Optional[tuple]:
    for sent in paper.sents:
        if sent.has_citation:
            continue
        for rx in _RANDOMIZED_AT:
            m = rx.search(sent.norm)
            if m:
                ur = _unit_rank(m.group("u"))
                if ur:
                    if rx.pattern.startswith(r"\bbetween") and ur[0] == 1:
                        continue
                    return ur[0], ur[1], sent
    return None


_SE_HEADER = re.compile(r"^\(?(?:s\.?\s?e\.?|std\.?\s*err(?:or)?s?\.?|standard\s+errors?|robust\s+s\.?e\.?)\)?$", re.I)


def _has_se_column(pt: ParsedTable) -> bool:
    """A column headed "SE" or "Std. err." in the rows above the first value row, as in SEM tables."""
    for i, kind in enumerate(pt.row_kinds):
        if kind in ("values", "brackets", "mixed") or kind.startswith("stat:"):
            break
        if any(_SE_HEADER.match((cell or "").strip()) for cell in pt.table.rows[i][1:]):
            return True
    return False


@register("BEH-09")
def standard_error_notes(pm, ctx):
    """BEH-09 (script part). Every regression table's note states the type of standard errors;
    clustering is not finer than the unit of treatment assignment; tables with few clusters say
    how inference allows for it (wild bootstrap, randomization inference, CR2). Whether the
    clustering level is right for the design is left to the reading agent.

    Misses: the unit of assignment when the text does not say "randomized at the X level" or
    similar, and statements about standard errors made only in the text far from the table."""
    paper = _paper(pm)
    # Regression tables: estimates with a value in parentheses below or beside them. A table of means whose
    # difference column carries stars (a balance or descriptive table) has no standard errors to describe.
    regs = [pt for pt in paper.tables if pt.block is not None and pt.paren not in ("sd", "ci")
            and (pt.estimates or _has_se_column(pt))
            and (pt.has_stars or re.search(r"standard\s+errors?|std\.?\s*err", pt.notes or "", re.I))]
    if not pm.tables:
        ctx.not_applicable("BEH-09", "the paper has no tables")
        return
    if not regs:
        ctx.not_applicable("BEH-09", "no regression tables with standard errors")
        return
    assign = _assignment_unit(paper)
    text_se = None
    for sent in paper.sents:
        if not sent.has_citation and _TEXT_SE.search(sent.norm):
            text_se = sent
            break
    text_fix = bool(_FEW_FIX.search(paper.body_text))
    missing = []
    for pt in regs:
        notes_quote = pt.notes_quote()
        anchor_quote = notes_quote or pt.row_quote(0)
        if not pt.se_types:
            missing.append((pt, anchor_quote))
            continue
        if assign is None:
            continue
        rank, unit, a_sent = assign
        clustered = "clustered" in pt.se_types
        cl = _unit_rank(pt.cluster_unit) if pt.cluster_unit else None
        if rank > 1 and not clustered and not {"randomization inference", "wild bootstrap"} & set(pt.se_types):
            yield _emit(ctx, "BEH-09", f"Standard errors in {pt.name} are not clustered at the level of assignment", "major",
                        f"Treatment is assigned by {unit}, but the note of {pt.name} describes "
                        f"{', '.join(pt.se_types)} standard errors without clustering.",
                        block=pt.block, quote=anchor_quote,
                        evidence=[_cr("cluster level must be at least the assignment level",
                                      {"assignment unit": unit, "standard errors": pt.se_types},
                                      "not clustered", "keyword reading of the text and the note")],
                        trajectory=[f"Found the unit of assignment ({unit}) in {a_sent.where()}.",
                                    f"Read the note of {pt.name}: {', '.join(pt.se_types)}."],
                        fix=Fix("investigate", detail=f"Cluster standard errors by {unit}, or explain why not.",
                                resolved_when=f"The note of {pt.name} reports standard errors clustered at the level "
                                              "of assignment, or justifies another choice."),
                        status="likely", confidence="medium", related=[_rel(a_sent.block, a_sent.quote())],
                        extra={"table": pt.table.label, "assignment": unit})
        elif clustered and cl and cl[0] < rank:
            yield _emit(ctx, "BEH-09", f"Clustering in {pt.name} is finer than the level of assignment", "major",
                        f"Treatment is assigned by {unit}, but {pt.name} clusters by {pt.cluster_unit}.",
                        block=pt.block, quote=anchor_quote,
                        evidence=[_cr("cluster level must be at least the assignment level",
                                      {"assignment unit": unit, "cluster unit": pt.cluster_unit}, "finer", "unit ranking")],
                        trajectory=[f"Found the unit of assignment ({unit}) in {a_sent.where()}.",
                                    f"Read the cluster level of {pt.name}: {pt.cluster_unit}."],
                        fix=Fix("investigate", detail=f"Cluster at the {unit} level.",
                                resolved_when="Standard errors are clustered at the level of assignment or coarser."),
                        status="likely", confidence="medium", related=[_rel(a_sent.block, a_sent.quote())],
                        extra={"table": pt.table.label, "assignment": unit, "cluster": pt.cluster_unit})
        if clustered:
            g = pt.n_clusters
            g_source = "the table note"
            for c in pt.stats.get("clusters", {}).values():
                if c.num is not None:
                    g, g_source = min(g or 10 ** 9, int(c.num.value)), "the Clusters row"
            if g is None and cl:
                g = _count_of_unit(paper, cl[1])
                g_source = f"the number of {cl[1]}s stated in the text"
            if g and g < 30 and not (_FEW_FIX.search(pt.notes or "") or text_fix):
                yield _emit(ctx, "BEH-09", f"Few clusters in {pt.name} without a small-sample correction", "major",
                            f"{pt.name} clusters standard errors with {g} clusters (from {g_source}), and neither the "
                            f"note nor the text "
                            f"mentions a wild bootstrap, randomization inference or another few-cluster correction.",
                            block=pt.block, quote=anchor_quote,
                            evidence=[_cr("cluster-robust inference is unreliable below about 30 to 50 clusters",
                                          {"clusters": g}, "few clusters, no correction stated", "rule of thumb")],
                            trajectory=[f"Read the number of clusters in {pt.name}: {g}.",
                                        "Searched the note and the text for a few-cluster correction: none."],
                            fix=Fix("investigate", detail="Report wild cluster bootstrap or randomization-inference p-values.",
                                    resolved_when="Inference with few clusters uses a correction suited to it."),
                            status="needs_human", confidence="medium", extra={"table": pt.table.label, "clusters": g})
    if missing:
        # One finding for all the tables whose notes leave the type out: the fix is the same for each.
        names = [pt.name for pt, _ in missing]
        first, first_quote = missing[0]
        no_note = [pt.name for pt, _ in missing if not (pt.notes or "").strip()]
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        subject = f"{names[0]} does not" if len(names) == 1 else f"{len(names)} regression tables do not"
        problem = ((f"The note of {listed} does not say" if len(names) == 1 else f"The notes of {listed} do not say")
                   + " whether standard errors are robust, clustered (and at which level) or bootstrapped.")
        if text_se is not None:
            problem += (f" The text says it at {text_se.where()}, but a table note should be self-contained, "
                        "since tables are often read on their own.")
        if no_note:
            problem += (f" {', '.join(no_note)} {'has' if len(no_note) == 1 else 'have'} no note at all, which may "
                        "also mean a note was lost when the file was read.")
        rel = [_rel(pt.block, q) for pt, q in missing[1:12] if pt.block is not None and q]
        if text_se is not None:
            rel.append(_rel(text_se.block, text_se.quote()))
        yield _emit(ctx, "BEH-09", f"{subject} state the type of standard errors",
                    "minor" if text_se is not None else "major", problem,
                    block=first.block, quote=first_quote, related=rel,
                    evidence=[Evidence(type="checked_absence", data={
                        "scope": "notes of " + ", ".join(names),
                        "terms": {"robust": 0, "cluster": 0, "heteroskedasticity": 0, "bootstrap": 0},
                        "version": "paper map"}),
                        _cr("presence of a standard-error type in each table note",
                            {pt.name: pt.notes or "(none)" for pt, _ in missing[:12]},
                            "no type stated", "exact keyword search")],
                    trajectory=[f"Read the notes of {len(regs)} regression table(s).",
                                "Searched each for the type of standard errors: none in " + listed + ".",
                                (f"Searched the text: the type is stated at {text_se.where()}." if text_se is not None
                                 else "Searched the text: the type of standard errors is not stated anywhere.")],
                    fix=Fix("insert", detail="Add the type of standard errors and the clustering level to each note, "
                                             "for example \"Standard errors clustered at the county level in "
                                             "parentheses.\"",
                            resolved_when="Every regression table's note names the type of standard errors and any "
                                          "clustering."),
                    status="likely" if len(no_note) == len(names) else "confirmed",
                    confidence="medium" if len(no_note) == len(names) else "high",
                    extra={"tables": [pt.table.label for pt, _ in missing]})
    ctx.note("BEH-09", f"read the notes of {len(regs)} regression table(s)"
             + (f"; unit of assignment: {assign[1]}" if assign else "; unit of assignment not stated in the text"))
