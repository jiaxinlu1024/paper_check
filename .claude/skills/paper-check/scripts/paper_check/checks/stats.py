"""Pure arithmetic and statistics helpers for the number checks in `numbers.py`.

Nothing here knows about the paper map. Reported numbers are passed as strings
so that trailing zeros survive: "0.120" was rounded to three decimals and stands
for any value in [0.1195, 0.1205]. Every comparison uses these rounding
intervals and closed bounds, so a check only fails when no value that rounds to
the printed numbers could make the printed claim true.

Methods, each reimplemented from its published description. No code, regular
expressions or test cases were copied from any implementation:

- Star check for regression tables with rounding intervals: Puetz and Bruns
  (2021), "The (non-)significance of reporting errors in economics", Journal of
  Economic Surveys 35(1), and the DORIS method of Bruns, Herwartz, Ioannidis,
  Islam and Raters (doi:10.31222/osf.io/mbx62).
- Recomputing p from a reported test statistic and its degrees of freedom: the
  idea behind statcheck (Nuijten et al. 2016, Behavior Research Methods 48).
  statcheck is GPL-3, so this is a fresh implementation from the paper.
- GRIM: Brown and Heathers (2017), Social Psychological and Personality Science 8(4).
- DEBIT: Heathers and Brown (2019), https://osf.io/5vb3u/.
- GRIMMER: Anaya (2016), PeerJ Preprints, with the parity argument that a sum
  of squares of integers has the parity of their sum. Cautious flag only.
- Bounds on the standard deviation of bounded data: Bhatia and Davis (2000),
  American Mathematical Monthly 107(4), and the extreme-point construction for
  integer data.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Iterable, Optional

from scipy import stats as _sp

EPS = 1e-9
ALPHA = 0.05

# Economics convention, used when a table note gives no thresholds.
DEFAULT_THRESHOLDS = {"*": 0.10, "**": 0.05, "***": 0.01}
# Stata esttab's default, the other common convention. A defaulted check must fail under both.
ESTTAB_THRESHOLDS = {"*": 0.05, "**": 0.01, "***": 0.001}

_DASHES = dict.fromkeys(map(ord, "\u2212\u2013\u2014\u2012\ufe63\uff0d"), "-")
_NUMBER = re.compile(r"^(?P<sign>[-+])?(?P<int>\d{1,3}(?:,\d{3})+|\d+)?(?:\.(?P<frac>\d+))?(?:[eE](?P<exp>[-+]?\d+))?$")


# ================================================================ reported numbers
@dataclass(frozen=True)
class Reported:
    """A number as printed, with the interval it stands for after rounding."""

    raw: str
    exact: Fraction
    decimals: int
    exponent: int = 0

    @property
    def value(self) -> float:
        return float(self.exact)

    @property
    def half_unit(self) -> Fraction:
        return Fraction(1, 2) * Fraction(10) ** (self.exponent - self.decimals)

    @property
    def lo_exact(self) -> Fraction:
        return self.exact - self.half_unit

    @property
    def hi_exact(self) -> Fraction:
        return self.exact + self.half_unit

    @property
    def lo(self) -> float:
        return float(self.lo_exact)

    @property
    def hi(self) -> float:
        return float(self.hi_exact)

    @property
    def interval(self) -> tuple:
        return (self.lo, self.hi)

    @property
    def abs_interval(self) -> tuple:
        """Interval of |x|; it starts at 0 when the rounding interval straddles 0."""
        lo, hi = self.lo, self.hi
        if lo >= 0:
            return (lo, hi)
        if hi <= 0:
            return (-hi, -lo)
        return (0.0, max(-lo, hi))

    @property
    def places(self) -> int:
        """Decimal places of the rounding unit: 3 for "0.120", 2 for "1.2e-1"."""
        return self.decimals - self.exponent

    def scaled(self, power: int) -> "Reported":
        """The same report times 10**power; a percentage as a share is scaled(-2)."""
        return Reported(self.raw, self.exact * Fraction(10) ** power, self.decimals, self.exponent + power)

    def __str__(self) -> str:
        return self.raw


def reported(raw) -> Optional[Reported]:
    """Parse a printed number: "0.120", "-0.018", "1,150", ".05", "1.2e-3", "\u22120.031", "23%".

    Returns None for anything else, including a decimal comma such as "0,120",
    which is ambiguous with a thousands separator."""
    if raw is None:
        return None
    if isinstance(raw, Reported):
        return raw
    text = str(raw).strip()
    s = text.translate(_DASHES)
    s = re.sub(r"[\s\u00a0\u2009\u202f$\u20ac\u00a3]", "", s)
    s = s[:-1] if s.endswith("%") else s
    m = _NUMBER.match(s)
    if not m or not (m.group("int") or m.group("frac")):
        return None
    int_part = m.group("int") or "0"
    if "," in int_part and int_part.startswith("0,"):
        return None
    int_part = int_part.replace(",", "")
    frac = m.group("frac") or ""
    exp = int(m.group("exp") or 0)
    exact = Fraction(int(int_part + frac), 10 ** len(frac)) * Fraction(10) ** exp
    if m.group("sign") == "-":
        exact = -exact
    return Reported(text, exact, len(frac), exp)


def overlaps(a: tuple, b: tuple, eps: float = EPS) -> bool:
    """Closed intervals a and b share at least one point."""
    return a[0] <= b[1] + eps and b[0] <= a[1] + eps


def magnitude(rng: tuple) -> tuple:
    """Range of |x| for x in the closed interval rng."""
    lo, hi = rng
    if lo >= 0:
        return (lo, hi)
    if hi <= 0:
        return (-hi, -lo)
    return (0.0, max(-lo, hi))


def fmt(x: float, places: int = 3) -> str:
    """Readable number for evidence: fixed places, scientific for tiny values."""
    if x is None:
        return "n/a"
    if math.isinf(x):
        return "inf"
    if x != 0 and abs(x) < 10 ** (-places):
        return f"{x:.1e}"
    return f"{x:.{places}f}"


def fmt_p(p: float) -> str:
    return f"{p:.1e}" if 0 < p < 0.001 else f"{p:.3f}"


def fmt_range(rng: tuple, places: int = 3, p: bool = False) -> str:
    f = fmt_p if p else (lambda v: fmt(v, places))
    return f"{f(rng[0])} to {f(rng[1])}"


def round_half_up(value: Fraction, places: int) -> str:
    """value rounded half up to `places` decimals (to a whole number when places <= 0)."""
    q = Decimal(1).scaleb(-places) if places > 0 else Decimal(1)
    d = Decimal(value.numerator) / Decimal(value.denominator)
    return str(d.quantize(q, rounding=ROUND_HALF_UP))


# ================================================================ distributions
def p_from_z(z: float, tails: int = 2) -> float:
    return min(1.0, tails * float(_sp.norm.sf(abs(z))))


def p_from_t(t: float, df: Optional[float] = None, tails: int = 2) -> float:
    """p of a t statistic; df None means the normal limit, the smallest p for any df."""
    if math.isinf(t):
        return 0.0
    if df is None or math.isinf(df):
        return p_from_z(t, tails)
    return min(1.0, tails * float(_sp.t.sf(abs(t), df)))


def p_from_f(F: float, df1: float, df2: float) -> float:
    return float(_sp.f.sf(F, df1, df2))


def p_from_chi2(x: float, df: float) -> float:
    return float(_sp.chi2.sf(x, df))


def t_from_r(r: float, df: float) -> float:
    if abs(r) >= 1:
        return math.inf
    return r * math.sqrt(df / (1 - r * r))


def p_from_r(r: float, df: float, tails: int = 2) -> float:
    return p_from_t(t_from_r(r, df), df, tails)


def z_from_u(U: float, n1: int, n2: int) -> float:
    """Normal approximation for the Mann-Whitney U statistic, without tie or continuity correction."""
    mu = n1 * n2 / 2
    sd = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    return (U - mu) / sd


def critical_value(level: float = 0.95, df: Optional[float] = None) -> float:
    q = 1 - (1 - level) / 2
    return float(_sp.norm.ppf(q)) if df is None else float(_sp.t.ppf(q, df))


# ================================================================ statistic ranges
def t_range(coef: Reported, se: Reported) -> tuple:
    """Range of |t| = |b| / SE over the rounding intervals of b and SE."""
    b_lo, b_hi = coef.abs_interval
    se_lo, se_hi = max(se.lo, 0.0), se.hi
    t_min = b_lo / se_hi if se_hi > 0 else math.inf
    t_max = math.inf if se_lo <= 0 else b_hi / se_lo
    return (t_min, t_max)


def p_range_from_t(t_rng: tuple, df: Optional[float] = None, tails: int = 2) -> tuple:
    """p is decreasing in |t|, so the range ends come from the ends of the t range."""
    return (p_from_t(t_rng[1], df, tails), p_from_t(t_rng[0], df, tails))


def p_range_stat(kind: str, stat: Reported, df1: Optional[float] = None, df2: Optional[float] = None,
                 tails: int = 2) -> tuple:
    """p range for a reported t, z, F, chi2 or r statistic, using its rounding interval."""
    lo, hi = stat.abs_interval
    if kind == "t":
        return (p_from_t(hi, df1, tails), p_from_t(lo, df1, tails))
    if kind == "z":
        return (p_from_z(hi, tails), p_from_z(lo, tails))
    if kind == "F":
        return (p_from_f(hi, df1, df2), p_from_f(lo, df1, df2))
    if kind == "chi2":
        return (p_from_chi2(hi, df1), p_from_chi2(lo, df1))
    if kind == "r":
        hi = min(hi, 1.0)
        return (p_from_r(hi, df1, tails), p_from_r(lo, df1, tails))
    raise ValueError(f"unknown statistic {kind}")


def p_range_u(U: Reported, n1: int, n2: int, tails: int = 2) -> tuple:
    """p range for a Mann-Whitney U under the normal approximation."""
    mu = n1 * n2 / 2
    dev = magnitude((U.lo - mu, U.hi - mu))
    sd = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    return (p_from_z(dev[1] / sd, tails), p_from_z(dev[0] / sd, tails))


def p_range_u_total(U: Reported, n: int, tails: int = 2) -> Optional[tuple]:
    """p range for U when only the total N is known: the union over every split n1 + n2 = N
    that can produce the reported U."""
    lo = hi = None
    for n1 in range(1, n):
        n2 = n - n1
        if n1 * n2 < U.lo:
            continue
        p_lo, p_hi = p_range_u(U, n1, n2, tails)
        lo = p_lo if lo is None else min(lo, p_lo)
        hi = p_hi if hi is None else max(hi, p_hi)
    return None if lo is None else (lo, hi)


# ================================================================ reported p-values
@dataclass(frozen=True)
class PReport:
    comparator: str  # "=", "<", "<=", ">", ">="
    value: Reported

    @property
    def interval(self) -> tuple:
        if self.comparator == "=":
            return (max(0.0, self.value.lo), min(1.0, self.value.hi))
        if self.comparator in ("<", "<="):
            return (0.0, self.value.value)
        return (self.value.value, 1.0)

    def __str__(self) -> str:
        return f"p {self.comparator} {self.value.raw}"


def p_consistent(computed: tuple, rep: PReport) -> bool:
    return overlaps(computed, rep.interval)


def reported_significant(rep: PReport, alpha: float = ALPHA) -> Optional[bool]:
    """What the reported p says about significance at alpha; None when it says nothing.
    Like statcheck's default, p = .05 counts as significant at .05."""
    v = rep.value.value
    if rep.comparator in ("<", "<="):
        return True if v <= alpha + EPS else None
    if rep.comparator in (">", ">="):
        return False if v >= alpha - EPS else None
    return v <= alpha + EPS


def computed_significant(p_rng: tuple, alpha: float = ALPHA) -> Optional[bool]:
    """True when the whole p range is below alpha, False when none of it is, else None."""
    if p_rng[1] < alpha - EPS:
        return True
    if p_rng[0] >= alpha - EPS:
        return False
    return None


# ================================================================ star thresholds
_SYMBOL = r"(?:\*{1,4}|\u2020|\u2021|\u00a7|\+|#)"
_SYMBOLS = re.compile(_SYMBOL)
_VAL = r"(?P<val>\d*\.?\d+)\s*(?P<pct>%|percent\b|per\s+cent\b)?"
_SEP = r"\s*(?:,\s*(?:and|or|&)?|;|/|and|&|or)\s*"
_LIST = re.compile(
    rf"(?P<syms>{_SYMBOL}(?:{_SEP}{_SYMBOL})+)\s*,?\s*"
    r"(?:(?:denote|indicate|represent|mark|show|signify|correspond\s+to|refer\s+to|stand\s+for)s?\s+)?"
    r"(?:(?:statistical(?:ly)?\s+)?(?:significance|significant(?:ly)?(?:\s+different\s+from\s+(?:zero|0))?)\s+)?"
    r"(?:(?:at|levels?\s+of)\s+)?(?:the\s+)?(?:p\s*<=?\s*)?"
    rf"(?P<vals>\d*\.?\d+\s*%?(?:{_SEP}(?:p\s*<=?\s*)?\d*\.?\d+\s*%?)+)"
    r"\s*(?P<pct>%|percent\b|per\s+cent\b)?", re.I)
_LIST_REV = re.compile(
    rf"(?P<vals>\d*\.?\d+\s*%?(?:{_SEP}\d*\.?\d+\s*%?)+)\s*(?P<pct>%|percent\b|per\s+cent\b)?"
    rf"[^.*\u2020\u2021]{{0,60}}?(?P<syms>{_SYMBOL}(?:{_SEP}{_SYMBOL})+)", re.I)
_PER = re.compile(
    rf"(?<![*\u2020\u2021\u00a7+#\w])(?P<sym>{_SYMBOL})(?![*\u2020\u2021\u00a7+#])\s*[:=]?\s*"
    r"(?:(?:denotes?|indicates?|represents?|means?|marks?)\s+)?"
    r"(?:(?:statistical(?:ly)?\s+)?significan(?:t|ce)(?:ly)?\s+(?:different\s+from\s+(?:zero|0)\s+)?)?"
    r"(?:at\s+)?(?:the\s+)?"
    r"(?:(?:p|p-values?|p\s+values?)\s*(?:<=|<|=)\s*)?" + _VAL + rf"(?!{_SEP}\d)", re.I)
_REV = re.compile(rf"\bp\s*(?:-?\s*values?)?\s*(?:<=|<)\s*{_VAL}\s*[:(\[=]?\s*(?P<sym>{_SYMBOL})", re.I)
_REV2 = re.compile(rf"{_VAL}\s*(?:levels?\s*)?\(\s*(?P<sym>{_SYMBOL})\s*\)", re.I)


def clean_note(note: str) -> str:
    """Table-note text with LaTeX math reduced to plain symbols."""
    s = note or ""
    s = re.sub(r"\\(?:dagger|textdagger)(?![a-zA-Z])", "\u2020", s)
    s = re.sub(r"\\(?:ddagger|textdaggerdbl)(?![a-zA-Z])", "\u2021", s)
    s = re.sub(r"\\(?:ast|textasteriskcentered)(?![a-zA-Z])", "*", s)
    s = re.sub(r"\\(?:leq?|leqslant)(?![a-zA-Z])|\u2264|&lt;=", "<=", s)
    s = re.sub(r"\\lt(?![a-zA-Z])|&lt;", "<", s)
    s = s.replace("\\%", "%")
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    s = re.sub(r"[\\${}^]", " ", s)
    s = s.translate(_DASHES)
    return re.sub(r"\s+", " ", s).strip()


def _to_p(val: str, pct: Optional[str]) -> Optional[float]:
    try:
        v = float(val)
    except ValueError:
        return None
    if pct or v > 0.5:
        v /= 100
    return v if 0 < v <= 0.5 else None


def _valid(found: dict) -> bool:
    stars = sorted((len(k), v) for k, v in found.items() if set(k) == {"*"})
    return all(a[1] > b[1] for a, b in zip(stars, stars[1:]))


def parse_star_thresholds(note: str) -> Optional[dict]:
    """Read significance thresholds from a table note.

    Returns a mapping such as {"*": 0.10, "**": 0.05, "***": 0.01}, or None when
    the note defines none, or defines them inconsistently (more stars must mean
    a smaller p). Understands, among others: "* p<0.10, ** p<0.05, *** p<0.01",
    "*** 1%, ** 5%, * 10%", "*, ** and *** denote significance at the 10%, 5% and
    1% levels", "*/**/*** significant at 10/5/1 percent", "p < 0.01 (***)",
    "1% (***)" and daggers."""
    text = clean_note(note)
    if not _SYMBOLS.search(text):
        return None
    found: dict = {}
    rest = text
    for m in _LIST.finditer(text):
        syms = _SYMBOLS.findall(m.group("syms"))
        vals = re.findall(r"(\d*\.?\d+)\s*(%)?", m.group("vals"))
        if len(syms) != len(vals):
            continue
        for sym, (v, pct) in zip(syms, vals):
            p = _to_p(v, pct or m.group("pct"))
            if p is not None:
                found.setdefault(sym, p)
        rest = rest.replace(m.group(0), " ")
    for m in _PER.finditer(rest):
        p = _to_p(m.group("val"), m.group("pct"))
        if p is not None:
            found.setdefault(m.group("sym"), p)
    if not found:
        for pattern in (_REV, _REV2):
            for m in pattern.finditer(text):
                p = _to_p(m.group("val"), m.group("pct"))
                if p is not None:
                    found.setdefault(m.group("sym"), p)
    if not found:
        for m in _LIST_REV.finditer(text):
            syms = _SYMBOLS.findall(m.group("syms"))
            vals = re.findall(r"(\d*\.?\d+)\s*(%)?", m.group("vals"))
            if len(syms) == len(vals):
                for sym, (v, pct) in zip(syms, vals):
                    p = _to_p(v, pct or m.group("pct"))
                    if p is not None:
                        found.setdefault(sym, p)
    if not found or not _valid(found):
        return None
    return found


def describe_thresholds(th: dict) -> str:
    return ", ".join(f"{s} p<{v:g}" for s, v in sorted(th.items(), key=lambda kv: -kv[1]))


def implied_interval(symbol: str, thresholds: dict) -> Optional[tuple]:
    """The p interval a significance mark stands for: [next stricter threshold, its own threshold].
    No mark means p is at least the loosest threshold. None for an undefined mark."""
    levels = sorted(set(thresholds.values()))
    if not levels:
        return None
    if not symbol:
        return (max(levels), 1.0)
    if symbol not in thresholds:
        return None
    hi = thresholds[symbol]
    stricter = [v for v in levels if v < hi - EPS]
    return (max(stricter) if stricter else 0.0, hi)


def implied_significant(implied: tuple, alpha: float = ALPHA) -> Optional[bool]:
    if implied[1] <= alpha + EPS:
        return True
    if implied[0] >= alpha - EPS:
        return False
    return None


def star_verdict(p_rng: tuple, implied: tuple) -> str:
    """overstated: every admissible p is above the interval the mark claims;
    understated: every admissible p is below it; otherwise consistent."""
    if p_rng[0] > implied[1] + EPS:
        return "overstated"
    if p_rng[1] < implied[0] - EPS:
        return "understated"
    return "consistent"


@dataclass
class StarCheck:
    symbol: str
    implied: tuple
    t_range: Optional[tuple]
    p_range: tuple
    verdict: str
    strong: bool
    df_low: Optional[float] = None
    p_range_low_df: Optional[tuple] = None
    verdict_low_df: Optional[str] = None

    @property
    def df_sensitive(self) -> bool:
        return self.verdict_low_df is not None and self.verdict_low_df != self.verdict


def _strong(verdict: str, implied: tuple, p_rng: tuple, alpha: float = ALPHA) -> bool:
    if verdict == "consistent":
        return False
    claimed = implied_significant(implied, alpha)
    computed = computed_significant(p_rng, alpha)
    return claimed is not None and computed is not None and claimed != computed


def check_stars(coef: Reported, paren: Reported, symbol: str, thresholds: dict, paren_kind: str = "se",
                df_low: Optional[float] = None, tails: int = 2) -> Optional[StarCheck]:
    """Star check of one estimate. paren_kind says what the number under the
    coefficient is: "se" (standard error), "t" or "z" (statistic) or "p" (p-value).

    The verdict uses the normal distribution, which gives the smallest p for any
    df, so an overstated verdict holds for every df. With df_low, the verdict is
    recomputed under t(df_low) to see whether the df assumption decides it."""
    implied = implied_interval(symbol, thresholds)
    if implied is None:
        return None
    if paren_kind == "se":
        t_rng = t_range(coef, paren)
    elif paren_kind in ("t", "z"):
        t_rng = paren.abs_interval
    elif paren_kind == "p":
        p_rng = PReport("=", paren).interval
        verdict = star_verdict(p_rng, implied)
        return StarCheck(symbol, implied, None, p_rng, verdict, _strong(verdict, implied, p_rng))
    else:
        raise ValueError(paren_kind)
    p_rng = p_range_from_t(t_rng, None, tails)
    verdict = star_verdict(p_rng, implied)
    out = StarCheck(symbol, implied, t_rng, p_rng, verdict, _strong(verdict, implied, p_rng))
    if df_low and paren_kind != "z":
        out.df_low = df_low
        out.p_range_low_df = p_range_from_t(t_rng, df_low, tails)
        out.verdict_low_df = star_verdict(out.p_range_low_df, implied)
    return out


# ================================================================ confidence intervals
@dataclass
class CICheck:
    contains_estimate: bool
    excludes_zero: Optional[bool]  # True: whole interval on one side of 0; False: surely contains 0
    crit_range: Optional[tuple]  # half-width / SE over the rounding intervals
    expected_crit: tuple
    width_verdict: Optional[str]  # "ok", "narrow", "wide"


def check_ci(coef: Reported, lo: Reported, hi: Reported, se: Optional[Reported] = None, level: float = 0.95,
             df_low: Optional[float] = None) -> CICheck:
    """Check a confidence interval [lo, hi] against b and, when given, b +/- c * SE."""
    if lo.value > hi.value:
        lo, hi = hi, lo
    contains = coef.hi >= lo.lo - EPS and coef.lo <= hi.hi + EPS
    if lo.lo > 0 or hi.hi < 0:
        excludes = True
    elif lo.hi < 0 < hi.lo:
        excludes = False
    else:
        excludes = None
    z = critical_value(level)
    upper = critical_value(level, df_low) if df_low else z * 1.33  # about t with 6 df when df is unknown
    expected = (z, upper)
    crit, verdict = None, None
    if se is not None and se.hi > 0:
        hw_lo = max(0.0, (hi.lo - lo.hi) / 2)
        hw_hi = (hi.hi - lo.lo) / 2
        se_lo = max(se.lo, 0.0)
        crit = (hw_lo / se.hi, math.inf if se_lo <= 0 else hw_hi / se_lo)
        if crit[1] < z * 0.98:
            verdict = "narrow"
        elif crit[0] > upper * 1.02:
            verdict = "wide"
        else:
            verdict = "ok"
    return CICheck(contains, excludes, crit, expected, verdict)


# ================================================================ changes and sums
def diff_range(a: Reported, b: Reported) -> tuple:
    """Range of b - a."""
    return (b.lo - a.hi, b.hi - a.lo)


def rel_range(a: Reported, b: Reported) -> Optional[tuple]:
    """Range of (b - a) / a; None when a's interval contains 0."""
    if a.lo <= 0 <= a.hi:
        return None
    corners = [b.lo / a.lo, b.lo / a.hi, b.hi / a.lo, b.hi / a.hi]
    return (min(corners) - 1, max(corners) - 1)


def ratio_range(a: Reported, b: Reported) -> Optional[tuple]:
    r = rel_range(a, b)
    return None if r is None else (r[0] + 1, r[1] + 1)


def quotient_range(num: Reported, den: Reported) -> Optional[tuple]:
    """Range of num / den; None when den's interval contains 0."""
    if den.lo <= 0 <= den.hi:
        return None
    corners = [num.lo / den.lo, num.lo / den.hi, num.hi / den.lo, num.hi / den.hi]
    return (min(corners), max(corners))


APPROX_WORDS = {"about", "approximately", "around", "roughly", "some", "approx.", "~", "\u2248", "close to"}
LOWER_WORDS = {"over", "more than", "above", "at least", "exceeding", "upwards of"}
UPPER_WORDS = {"less than", "under", "below", "up to", "at most", "fewer than"}
NEAR_WORDS = {"nearly", "almost"}


def claim_range(c: Reported, qualifier: Optional[str] = None) -> tuple:
    """Interval of magnitudes a stated quantity allows, widened for words like "about".
    "About" allows 10% either way, "nearly" up to 15% below, "over" anything above."""
    lo, hi = c.abs_interval
    q = (qualifier or "").strip().lower()
    v = abs(c.value)
    if q in APPROX_WORDS:
        return (min(lo, 0.9 * v), max(hi, 1.1 * v))
    if q in NEAR_WORDS:
        return (min(lo, 0.85 * v), hi)
    if q in LOWER_WORDS:
        return (lo, math.inf)
    if q in UPPER_WORDS:
        return (0.0, hi)
    return (lo, hi)


def sum_check(parts: Iterable[Reported], total: Reported) -> dict:
    """Do the parts add up to the total within the sum of their rounding errors?"""
    parts = list(parts)
    s = sum((p.exact for p in parts), Fraction(0))
    tol = sum((p.half_unit for p in parts), Fraction(0)) + total.half_unit
    return {"sum": float(s), "total": float(total.exact), "tolerance": float(tol),
            "consistent": abs(s - total.exact) <= tol}


def share_check(pct: Reported, k: int, n: int) -> dict:
    """Is the printed percentage what k out of n rounds to?"""
    exact = Fraction(100 * k, n)
    ok = pct.lo_exact <= exact <= pct.hi_exact
    return {"computed": float(exact), "consistent": ok}


def log_points_to_percent(b: Reported) -> tuple:
    """Percent change implied by a coefficient on a log outcome: 100 (exp(b) - 1)."""
    return (100 * math.expm1(b.lo), 100 * math.expm1(b.hi))


# ================================================================ GRIM, DEBIT, GRIMMER, SD bounds
@dataclass
class GrimResult:
    testable: bool
    consistent: Optional[bool] = None
    n: int = 0
    places: int = 0
    interval: Optional[tuple] = None
    sum_interval: Optional[tuple] = None
    nearest: list = field(default_factory=list)
    share_inconsistent: float = 0.0
    reason: str = ""


def _mean_report(mean_raw, percent: bool) -> Optional[Reported]:
    r = reported(mean_raw)
    if r is None:
        return None
    return r.scaled(-2) if percent else r


def grim(mean_raw, n: int, items: int = 1, percent: bool = False) -> GrimResult:
    """GRIM: can n responses on an integer scale (each the average of `items` integer items)
    have a mean that rounds to the printed value? A percentage is checked as a share of n.
    Rounding is taken as a closed interval, so ties rounded either way are accepted."""
    r = _mean_report(mean_raw, percent)
    if r is None:
        return GrimResult(False, reason="not a number")
    big_n = int(n) * int(items)
    places = r.places
    if big_n <= 0:
        return GrimResult(False, reason="no sample size")
    if places <= 0 or big_n >= 10 ** places:
        return GrimResult(False, n=big_n, places=places,
                          reason=f"with N = {big_n}, every value with {max(places, 0)} decimals is possible")
    lo, hi = r.lo_exact, r.hi_exact
    s_lo, s_hi = math.ceil(lo * big_n), math.floor(hi * big_n)
    consistent = s_lo <= s_hi
    near = sorted({math.floor(r.exact * big_n), math.ceil(r.exact * big_n)} | ({s_lo} if consistent else set()))
    shown = []
    for k in near:
        value = Fraction(k, big_n)
        shown.append(round_half_up(value * 100, places - 2) + "%" if percent else round_half_up(value, places))
    return GrimResult(True, consistent, big_n, places, (float(lo), float(hi)), (float(lo * big_n), float(hi * big_n)),
                      shown, max(0.0, 1 - big_n / 10 ** places))


@dataclass
class DebitResult:
    testable: bool
    consistent: Optional[bool] = None
    grim_consistent: Optional[bool] = None
    candidates: list = field(default_factory=list)  # (k, sample SD, population SD)
    reason: str = ""


def debit(mean_raw, sd_raw, n: int, percent: bool = False) -> DebitResult:
    """DEBIT: for a binary variable with k ones among n, mean = k/n and SD is fixed by k.
    Accepts either the sample (n-1) or the population (n) formula."""
    m = _mean_report(mean_raw, percent)
    s = _mean_report(sd_raw, percent)
    if m is None or s is None or n < 2:
        return DebitResult(False, reason="missing mean, SD or N")
    if not (-EPS <= m.value <= 1 + EPS):
        return DebitResult(False, reason="mean is not a share")
    ks = [k for k in range(max(0, math.ceil(m.lo_exact * n)), min(n, math.floor(m.hi_exact * n)) + 1)]
    if not ks:
        return DebitResult(True, False, False, reason="no count of ones gives this mean (GRIM)")
    cands = []
    ok = False
    for k in ks:
        sd_sample = math.sqrt(k * (n - k) / (n * (n - 1)))
        sd_pop = math.sqrt(k * (n - k)) / n
        cands.append((k, sd_sample, sd_pop))
        if any(s.lo - EPS <= v <= s.hi + EPS for v in (sd_sample, sd_pop)):
            ok = True
    return DebitResult(True, ok, True, cands)


def _q_min(total: int, n: int) -> int:
    """Smallest sum of squares of n integers that add up to total: spread them evenly."""
    q, r = divmod(total, n)
    return (n - r) * q * q + r * (q + 1) * (q + 1)


def _q_max(total: int, n: int, a: int, b: int) -> Optional[int]:
    """Largest sum of squares of n integers in [a, b] that add up to total: push them to the bounds."""
    if b < a or not (n * a <= total <= n * b):
        return None
    if b == a:
        return n * a * a
    k, rem = divmod(total - n * a, b - a)
    if k >= n:
        return n * b * b
    return k * b * b + (a + rem) ** 2 + (n - k - 1) * a * a


@dataclass
class GrimmerResult:
    testable: bool
    consistent: Optional[bool] = None
    grim_consistent: Optional[bool] = None
    reason: str = ""
    sums: list = field(default_factory=list)


def grimmer(mean_raw, sd_raw, n: int, bounds: Optional[tuple] = None) -> GrimmerResult:
    """GRIMMER for single-item integer data: some integer sum T (GRIM) and integer sum of
    squares Q with Q = T (mod 2), within the feasible range, must give the printed SD
    (sample formula) after rounding. A cautious check: report failures for a person to judge."""
    m = reported(mean_raw)
    s = reported(sd_raw)
    if m is None or s is None or n < 2:
        return GrimmerResult(False, reason="missing mean, SD or N")
    t_lo, t_hi = math.ceil(m.lo_exact * n), math.floor(m.hi_exact * n)
    if bounds:
        t_lo, t_hi = max(t_lo, n * bounds[0]), min(t_hi, n * bounds[1])
    if t_lo > t_hi:
        return GrimmerResult(True, False, False, reason="no integer sum gives this mean (GRIM)")
    s_lo = max(s.lo_exact, Fraction(0))
    s_hi = s.hi_exact
    for total in range(t_lo, t_hi + 1):
        base = Fraction(total * total, n)
        q_lo = math.ceil((n - 1) * s_lo * s_lo + base)
        q_hi = math.floor((n - 1) * s_hi * s_hi + base)
        q_lo = max(q_lo, _q_min(total, n))
        if bounds:
            qm = _q_max(total, n, bounds[0], bounds[1])
            if qm is None:
                continue
            q_hi = min(q_hi, qm)
        first = q_lo + ((total - q_lo) % 2)
        if first <= q_hi:
            return GrimmerResult(True, True, True, sums=[total])
    return GrimmerResult(True, False, True, reason="no integer sum of squares gives this SD",
                         sums=list(range(t_lo, t_hi + 1))[:10])


@dataclass
class SdBounds:
    testable: bool
    consistent: Optional[bool] = None
    feasible: Optional[tuple] = None  # (min SD, max SD) over the admissible means
    mean_in_bounds: Optional[bool] = None
    reason: str = ""


def sd_bounds(mean_raw, sd_raw, n: int, lo: float, hi: float, integer: bool = True) -> SdBounds:
    """Is the printed SD possible for n values in [lo, hi] with the printed mean?
    Integer data: exact extremes of the sum of squares for each admissible sum.
    Other bounded data: the Bhatia-Davis bound, var <= (M - lo)(hi - M), as a sample SD."""
    m = reported(mean_raw)
    s = reported(sd_raw)
    if m is None or n < 2:
        return SdBounds(False, reason="missing mean or N")
    if m.hi < lo - EPS or m.lo > hi + EPS:
        return SdBounds(True, False, None, False, reason="mean outside the scale")
    if s is None:
        return SdBounds(False, mean_in_bounds=True, reason="no SD")
    if integer and float(lo).is_integer() and float(hi).is_integer():
        a, b = int(lo), int(hi)
        t_lo, t_hi = max(math.ceil(m.lo_exact * n), n * a), min(math.floor(m.hi_exact * n), n * b)
        if t_lo > t_hi:
            return SdBounds(True, None, None, True, reason="no integer sum gives this mean (GRIM)")
        sd_min, sd_max = math.inf, 0.0
        for total in range(t_lo, t_hi + 1):
            qmin, qmax = _q_min(total, n), _q_max(total, n, a, b)
            if qmax is None:
                continue
            base = total * total / n
            sd_min = min(sd_min, math.sqrt(max(0.0, (qmin - base) / (n - 1))))
            sd_max = max(sd_max, math.sqrt(max(0.0, (qmax - base) / (n - 1))))
        feasible = (sd_min, sd_max)
    else:
        mid = (lo + hi) / 2
        m_best = min(max(mid, m.lo), m.hi)
        var_max = max(0.0, (m_best - lo) * (hi - m_best)) * n / (n - 1)
        feasible = (0.0, math.sqrt(var_max))
    ok = overlaps(feasible, (max(0.0, s.lo), s.hi))
    return SdBounds(True, ok, feasible, True)
