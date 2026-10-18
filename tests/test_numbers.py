"""Number and statistics checks: the helpers in checks/stats.py and the checks in checks/numbers.py."""

import itertools
import json
import math
import random
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

import pytest
import yaml
from scipy import stats as sp

import paper_check.checks as checks
from paper_check.checks import Context
from paper_check.checks import numbers as num
from paper_check.checks import stats as st
from paper_check.model import Anchor, Block, Citation, FindingSet, PaperMap, Table
from paper_check.textutil import find_quote, normalize
from paper_check.verify import load_findings_file, verify_finding

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NUM_IDS = {f"NUM-0{i}" for i in range(1, 10)} | {"BEH-09"}
R = st.reported


# ================================================================ helpers
@pytest.fixture()
def run(monkeypatch, tmp_path):
    """Run only this module's checks through the real registry runner."""
    monkeypatch.setattr(checks, "load_modules", lambda names=None: [])
    monkeypatch.setattr(checks, "_REGISTRY", [e for e in checks._REGISTRY if e[1].__module__ == num.__name__])

    def _run(pm, work=None):
        ctx = Context(work=work or tmp_path)
        result = checks.run_checks(pm, ctx, only=NUM_IDS)
        return result.findings, {c.check_id: c for c in result.coverage}
    return _run


def make_map(paragraphs=(), tables=()):
    """A paper map from (kind, section, text[, citation texts]) paragraphs and
    (rows, notes, number[, caption]) tables. Sentences are split by the checks themselves."""
    pm = PaperMap(source={"path": "synthetic", "format": "latex"})
    for i, para in enumerate(paragraphs, 1):
        kind, section, text = para[:3]
        b = Block(id=f"b{i:04d}", kind=kind, text=text, anchor=Anchor(file="paper.tex", line=i),
                  section=[section] if section else [])
        for c in (para[3] if len(para) > 3 else []):
            s = text.index(c)
            b.citations.append(Citation(keys=["k"], start=s, end=s + len(c), command="citep", raw=c))
        pm.blocks.append(b)
    for j, t in enumerate(tables, 1):
        rows, notes, number = t[:3]
        caption = t[3] if len(t) > 3 else ""
        raw = t[4] if len(t) > 4 else None
        text = "\n".join(" | ".join(r).strip() for r in rows) + (f"\nNotes: {notes}" if notes else "")
        tid = f"t{j}"
        pm.blocks.append(Block(id=f"bt{j:03d}", kind="table", text=text, anchor=Anchor(file="tables.tex", line=j),
                               section=["3 Results"], attrs={"table_id": tid, "number": number}))
        pm.tables.append(Table(id=tid, anchor=Anchor(file="tables.tex", line=j), caption=caption,
                               label=f"tab:{number}", number=number, rows=rows, notes=notes, raw=raw))
    return pm


def by_check(findings, cid):
    return [f for f in findings if f.check_id == cid]


def assert_well_formed(pm, findings, work):
    """Every finding quotes verbatim block text, carries computed evidence, a trajectory and a fix,
    and no two findings share check, block and quote (the report would merge them)."""
    keys = [(f.check_id, f.locations[0].block, normalize(f.quote).lower()) for f in findings]
    assert len(keys) == len(set(keys)), keys
    for f in findings:
        block = pm.block(f.locations[0].block)
        assert find_quote(f.quote, block.text), (f.check_id, f.quote)
        report = verify_finding(pm, work, f, {})
        assert not report["failed"], (f.check_id, report["failed"])
        cr = [e for e in f.evidence if e.type == "computed_result"]
        assert cr, f.title
        for e in cr:
            assert {"formula", "inputs", "output", "tolerance"} <= set(e.data), f.title
        assert f.trajectory and all(isinstance(t, str) and t for t in f.trajectory)
        assert f.fix is not None and f.fix.resolved_when
        if f.fix.action == "replace":
            assert f.fix.original and f.fix.replacement and find_quote(f.fix.original, block.text)
        assert f.status in ("confirmed", "likely", "needs_human")
        assert f.severity in ("critical", "major", "minor", "suggestion")
        assert f.confidence in ("high", "medium", "low")
        json.dumps(f.to_dict())


def rounded(x, places, mode=ROUND_HALF_UP):
    d = Decimal(repr(x)) if isinstance(x, float) else Decimal(x.numerator) / Decimal(x.denominator)
    return str(d.quantize(Decimal(1).scaleb(-places), rounding=mode))


# ================================================================ rounding intervals
def test_reported_keeps_trailing_zeros_and_rounding_interval():
    r = R("0.120")
    assert r.decimals == 3 and r.interval == pytest.approx((0.1195, 0.1205))
    assert R("-0.018").abs_interval == pytest.approx((0.0175, 0.0185))
    assert R("−0.031").value == pytest.approx(-0.031)
    assert R("1,150").value == 1150 and R("1,150").decimals == 0 and R("1,150").interval == (1149.5, 1150.5)
    assert R(".05").interval == pytest.approx((0.045, 0.055))
    assert R("1.2e-3").interval == pytest.approx((0.00115, 0.00125))
    assert R("23%").value == 23
    assert R("0,120") is None and R("abc") is None and R("") is None
    assert R("0.000").abs_interval == pytest.approx((0.0, 0.0005))  # straddles zero
    assert R("12.5").scaled(-2).interval == pytest.approx((0.1245, 0.1255))


def test_change_and_quotient_ranges():
    rel = st.rel_range(R("9.9"), R("8.1"))
    assert rel[0] < -0.1818 < rel[1]
    assert rel == pytest.approx((8.05 / 9.95 - 1, 8.15 / 9.85 - 1))
    assert st.diff_range(R("20"), R("25")) == pytest.approx((4.0, 6.0))
    assert st.rel_range(R("0.0"), R("1.0")) is None
    q = st.quotient_range(R("-0.018"), R("0.099"))
    assert q == pytest.approx((-0.0185 / 0.0985, -0.0175 / 0.0995))
    assert st.claim_range(R("25"), "about") == pytest.approx((22.5, 27.5))
    assert st.claim_range(R("25"), "more than")[1] == math.inf
    assert st.overlaps((1, 2), (2, 3)) and not st.overlaps((1, 2), (2.1, 3))


# ================================================================ distributions
def test_t_to_p_conversions_match_scipy():
    assert st.p_from_t(2.2, 28) == pytest.approx(2 * sp.t.sf(2.2, 28))
    assert st.p_from_t(2.2) == pytest.approx(2 * sp.norm.sf(2.2))
    assert st.p_from_t(-2.2, 28) == pytest.approx(st.p_from_t(2.2, 28))
    assert st.p_from_t(2.2, 28, tails=1) == pytest.approx(sp.t.sf(2.2, 28))
    assert st.p_from_t(math.inf) == 0.0
    for df in (2, 5, 30, 1000):  # the normal limit is the smallest p for any df
        assert st.p_from_t(2.0) < st.p_from_t(2.0, df)
    assert st.p_from_f(3.10, 2, 57) == pytest.approx(sp.f.sf(3.10, 2, 57))
    assert st.p_from_chi2(4.5, 1) == pytest.approx(sp.chi2.sf(4.5, 1))
    t = 0.25 * math.sqrt(98 / (1 - 0.25 ** 2))
    assert st.p_from_r(0.25, 98) == pytest.approx(2 * sp.t.sf(t, 98))
    z = (300 - 25 * 30 / 2) / math.sqrt(25 * 30 * 56 / 12)
    assert st.z_from_u(300, 25, 30) == pytest.approx(z)
    assert st.critical_value(0.95) == pytest.approx(1.959964, abs=1e-6)


def test_p_ranges_use_the_rounding_interval():
    t_rng = st.t_range(R("0.120"), R("0.080"))
    assert t_rng == pytest.approx((0.1195 / 0.0805, 0.1205 / 0.0795))
    p_rng = st.p_range_from_t(t_rng)
    assert p_rng == pytest.approx((2 * sp.norm.sf(0.1205 / 0.0795), 2 * sp.norm.sf(0.1195 / 0.0805)))
    assert st.p_range_stat("t", R("2.20"), 28) == pytest.approx((2 * sp.t.sf(2.205, 28), 2 * sp.t.sf(2.195, 28)))
    lo, hi = st.p_range_stat("F", R("3.10"), 2, 57)
    assert lo < sp.f.sf(3.10, 2, 57) < hi
    assert st.t_range(R("0.05"), R("0.000"))[1] == math.inf  # a zero SE cannot refute anything
    assert st.p_range_u_total(R("300"), 55)[0] <= st.p_range_u(R("300"), 25, 30)[0]


def test_reported_p_values_and_decisions():
    computed = st.p_range_stat("F", R("3.10"), 2, 57)
    assert not st.p_consistent(computed, st.PReport("<", R(".05")))
    assert st.reported_significant(st.PReport("<", R(".05"))) is True
    assert st.computed_significant(computed) is False
    assert st.p_consistent(st.p_range_stat("t", R("2.20"), 28), st.PReport("=", R(".04")))
    assert st.reported_significant(st.PReport("=", R(".05"))) is True  # statcheck's convention
    assert st.reported_significant(st.PReport("<", R(".10"))) is None
    assert st.PReport("=", R("0.000")).interval == pytest.approx((0.0, 0.0005))


# ================================================================ star thresholds
@pytest.mark.parametrize("note,expected", [
    ("Notes: Robust standard errors in parentheses. * $p<0.10$, ** $p<0.05$, *** $p<0.01$.",
     {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("*** p<0.01, ** p<0.05, * p<0.1", {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("*, ** and *** denote significance at the 10%, 5% and 1% levels", {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("***, **, and * indicate significance at the 1, 5, and 10 percent levels", {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("*/**/*** significant at 10/5/1 percent", {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("Significance levels: * 10%, ** 5%, *** 1%", {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("+ p<0.10, * p<0.05, ** p<0.01, *** p<0.001", {"+": 0.10, "*": 0.05, "**": 0.01, "***": 0.001}),
    ("p < 0.01 (***), p < 0.05 (**), p < 0.1 (*)", {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("Significant at the 1% (***), 5% (**) and 10% (*) levels", {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("$^{\\dagger}$ p<0.10, $^{*}$ p<0.05", {"†": 0.10, "*": 0.05}),
    ("*** denotes significance at the 1 percent level, ** at the 5 percent level and * at the 10 percent level.",
     {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("The 10, 5 and 1 percent significance levels are denoted by *, ** and ***.", {"*": 0.10, "**": 0.05, "***": 0.01}),
    ("Standard errors in parentheses.", None),
    ("* p<0.01, ** p<0.05", None),  # more stars must mean a smaller p
])
def test_star_thresholds_are_read_from_the_note(note, expected):
    found = st.parse_star_thresholds(note)
    if expected is None:
        assert found is None
    else:
        assert found == pytest.approx(expected)


def test_implied_intervals():
    th = st.DEFAULT_THRESHOLDS
    assert st.implied_interval("***", th) == (0.0, 0.01)
    assert st.implied_interval("**", th) == (0.01, 0.05)
    assert st.implied_interval("*", th) == (0.05, 0.10)
    assert st.implied_interval("", th) == (0.10, 1.0)
    assert st.implied_interval("****", th) is None
    dag = {"†": 0.10, "*": 0.05, "**": 0.01}
    assert st.implied_interval("†", dag) == (0.05, 0.10) and st.implied_interval("**", dag) == (0.0, 0.01)
    assert st.implied_significant((0.01, 0.05)) is True and st.implied_significant((0.05, 0.10)) is False


# ================================================================ star check
def test_star_check_on_table_1():
    th = st.parse_star_thresholds("* p<0.10, ** p<0.05, *** p<0.01")
    for b, se, mark in [("-0.018", "0.008", "**"), ("0.250", "0.050", "***"), ("-0.031", "0.042", "")]:
        assert st.check_stars(R(b), R(se), mark, th).verdict == "consistent", b
    res = st.check_stars(R("0.120"), R("0.080"), "***", th)
    assert res.verdict == "overstated" and res.strong
    assert res.p_range[0] > 0.10


def test_star_check_flags_only_when_the_whole_range_is_outside():
    th = st.DEFAULT_THRESHOLDS
    # t = 1.96 exactly at the 5% boundary: both ** and * are possible after rounding
    assert st.check_stars(R("0.196"), R("0.100"), "**", th).verdict == "consistent"
    assert st.check_stars(R("0.196"), R("0.100"), "*", th).verdict == "consistent"
    # 0.120 (0.050) gives t from 2.37 to 2.43, p from 0.015 to 0.018: ** fits, *** does not
    weak = st.check_stars(R("0.120"), R("0.050"), "***", th)
    assert weak.verdict == "overstated" and not weak.strong  # the 5% conclusion does not flip
    assert st.check_stars(R("0.120"), R("0.050"), "**", th).verdict == "consistent"
    # the same estimate printed with two decimals allows t from 2.09 to 2.78, so *** cannot be refuted
    assert st.check_stars(R("0.12"), R("0.05"), "***", th).verdict == "consistent"
    assert st.check_stars(R("0.1"), R("0.1"), "*", th).verdict == "consistent"


def test_star_check_degrees_of_freedom_decide_understated_marks():
    th = st.DEFAULT_THRESHOLDS
    res = st.check_stars(R("0.030"), R("0.010"), "**", th, df_low=11)
    assert res.verdict == "understated"  # under the normal, p < 0.01
    assert res.verdict_low_df == "consistent" and res.df_sensitive  # with 12 clusters, ** is right
    over = st.check_stars(R("0.120"), R("0.080"), "***", th, df_low=11)
    assert over.verdict == over.verdict_low_df == "overstated" and not over.df_sensitive


def test_star_check_with_t_statistics_or_p_values_in_parentheses():
    th = st.DEFAULT_THRESHOLDS
    assert st.check_stars(R("0.120"), R("1.50"), "***", th, paren_kind="t").verdict == "overstated"
    assert st.check_stars(R("0.120"), R("2.70"), "***", th, paren_kind="t").verdict == "consistent"
    assert st.check_stars(R("0.120"), R("0.134"), "***", th, paren_kind="p").verdict == "overstated"


def test_star_check_never_flags_correct_stars_after_rounding():
    """Stars set from the unrounded estimate never fail the rounding-interval check."""
    rng = random.Random(7)
    th = st.DEFAULT_THRESHOLDS
    for _ in range(3000):
        se = 10 ** rng.uniform(-3, 0)
        b = rng.uniform(0, 6) * se * rng.choice([-1, 1])
        p = 2 * sp.norm.sf(abs(b) / se)
        mark = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""
        places = rng.choice([2, 3, 4])
        b_txt, se_txt = rounded(b, places), rounded(se, places)
        if float(se_txt) == 0:
            continue
        assert st.check_stars(R(b_txt), R(se_txt), mark, th).verdict == "consistent", (b_txt, se_txt, mark)


# ================================================================ GRIM, DEBIT, GRIMMER, bounds
def test_grim_planted_mean_and_edge_cases():
    res = st.grim("3.47", 25)
    assert res.testable and res.consistent is False
    assert res.nearest == ["3.44", "3.48"] and res.sum_interval == pytest.approx((86.625, 86.875))
    assert st.grim("3.48", 25).consistent
    assert not st.grim("3.4", 25).testable  # with 25 responses every one-decimal mean is possible
    assert not st.grim("3.47", 25, items=4).testable  # 100 item responses
    assert not st.grim("3", 25).testable
    assert st.grim("-1.47", 25).consistent is False  # scales centred on zero
    # a tie such as 25/8 = 3.125 may be printed 3.12 or 3.13; both are accepted
    assert st.grim("3.12", 8).consistent and st.grim("3.13", 8).consistent
    assert st.grim("23.5", 40, percent=True).consistent is False
    assert st.grim("22.5", 40, percent=True).consistent
    assert st.grim("33.3", 30, percent=True).consistent


def test_grim_grimmer_and_bounds_accept_every_achievable_sample():
    """Brute force: every mean and SD that some set of 1-5 ratings produces passes all three tests."""
    for n in range(2, 7):
        seen = set()
        for combo in itertools.combinations_with_replacement(range(1, 6), n):
            t, q = sum(combo), sum(x * x for x in combo)
            sd = Fraction(math.sqrt(Fraction(q * n - t * t, n * (n - 1)))).limit_denominator(10 ** 12)
            for mode in (ROUND_HALF_UP, ROUND_HALF_EVEN):
                seen.add((rounded(Fraction(t, n), 2, mode), rounded(sd, 2, mode)))
        for mean, sd in seen:
            assert st.grim(mean, n).consistent in (True, None)
            assert st.grimmer(mean, sd, n, (1, 5)).consistent is True, (n, mean, sd)
            assert st.sd_bounds(mean, sd, n, 1, 5).consistent is True, (n, mean, sd)


def test_grimmer_and_bounds_reject_impossible_values():
    assert st.grimmer("3.00", "1.01", 5, (1, 5)).consistent is False
    res = st.sd_bounds("4.80", "1.50", 25, 1, 5)
    assert res.consistent is False and res.feasible[1] < 1.0
    assert st.sd_bounds("5.30", None, 30, 1, 5).mean_in_bounds is False
    cont = st.sd_bounds("4.8", "1.5", 25, 1, 5, integer=False)  # Bhatia-Davis for any bounded data
    assert cont.consistent is False


def test_debit_binary_means_and_sds():
    assert st.debit("0.43", "0.50", 120).consistent
    assert st.debit("0.43", "0.30", 120).consistent is False
    assert st.debit("0.50", "0.53", 10).consistent and st.debit("0.50", "0.50", 10).consistent  # n-1 or n
    assert not st.debit("3.2", "0.4", 50).testable
    assert st.debit("0.437", "0.50", 20).grim_consistent is False
    for n in range(2, 40):  # no false positives on real binary data
        for k in range(n + 1):
            for sd in (math.sqrt(k * (n - k) / (n * (n - 1))), math.sqrt(k * (n - k)) / n):
                for mode in (ROUND_HALF_UP, ROUND_HALF_EVEN):
                    r = st.debit(rounded(Fraction(k, n), 2, mode), rounded(sd, 2, mode), n)
                    assert r.consistent in (True, None), (n, k)


def test_confidence_interval_and_sum_checks():
    ok = st.check_ci(R("0.50"), R("0.30"), R("0.70"), R("0.10"))
    assert ok.contains_estimate and ok.width_verdict == "ok" and ok.excludes_zero is True
    assert st.check_ci(R("0.50"), R("0.55"), R("0.70"), R("0.10")).contains_estimate is False
    assert st.check_ci(R("0.50"), R("0.40"), R("0.60"), R("0.10")).width_verdict == "narrow"
    assert st.check_ci(R("0.05"), R("-0.10"), R("0.20")).excludes_zero is False
    assert st.sum_check([R("40"), R("35"), R("20")], R("100"))["consistent"] is False
    assert st.sum_check([R("33.3"), R("33.3"), R("33.3")], R("100"))["consistent"]
    assert st.share_check(R("40"), 45, 120)["consistent"] is False
    assert st.share_check(R("37.5"), 45, 120)["consistent"]
    assert st.log_points_to_percent(R("0.50"))[0] == pytest.approx(100 * math.expm1(0.495))


# ================================================================ parsing in numbers.py
def test_math_is_normalized_with_a_map_back_to_the_source():
    text = "We find $t(28) = 2.20$, $p = .04$ and $\\chi^2(1) = 4.5$."
    norm, starts, ends = num.normalize_math(text)
    assert "t(28) = 2.20, p = .04" in norm and "χ2(1) = 4.5" in norm
    i = norm.index("p = .04")
    assert text[starts[i]:ends[i + len("p = .04") - 1]] == "p = .04"


def test_years_labels_columns_and_citations_are_never_results():
    text = ("In 2019, Section 2, Table 3, column (2), Equation (1) and Study 2 show that 401(k) plans of Smith (2018) "
            "have an effect of 0.47 among 120 participants on a 5-point scale.")
    pm = make_map([("paragraph", "3 Results", text, ["Smith (2018)"])])
    paper = num._paper(pm)
    kinds = {t.raw: t.kind for s in paper.sents for t in s.tokens}
    assert kinds["2019"] == "year" and kinds["2"] == "label" and kinds["3"] == "label" and kinds["1"] == "label"
    assert kinds["401"] == "other" and kinds["120"] == "count" and kinds["5"] == "descriptor"
    assert "2018" not in kinds  # masked: it sits inside the citation
    assert kinds["0.47"] == "result"
    assert all(s.has_citation for s in paper.sents)
    plain = make_map([("paragraph", "2 Design", "We study 400 participants.")])
    assert [t.kind for s in num._paper(plain).sents for t in s.tokens] == ["count"]


@pytest.mark.parametrize("raw,kind,value,stars", [
    ("0.120***", "num", 0.12, "***"), ("$-0.018^{**}$", "num", -0.018, "**"), ("(0.080)", "brack", 0.08, ""),
    ("[0.30, 0.70]", "pair", 0.30, ""), ("0.12** (0.05)", "combo", 0.12, "**"), ("−0.031", "num", -0.031, ""),
    ("1,150", "num", 1150, ""), ("12.5%", "num", 12.5, ""), ("—", "empty", None, ""), ("Yes", "text", None, ""),
])
def test_cells_are_parsed(raw, kind, value, stars):
    cell = num.parse_cell(raw)
    assert cell.kind == kind and cell.stars == stars
    if value is not None:
        assert cell.num.value == pytest.approx(value)


def test_test_paper_table_is_parsed(latex_map):
    pm, _ = latex_map
    paper = num._paper(pm)
    pt = paper.tables[0]
    assert pt.row_kinds[:2] == ["colnums", "header"]
    assert [(e.label, e.col, e.coef.raw, e.se.raw) for e in pt.estimates] == [
        ("Treatment", 0, "-0.018**", "(0.008)"), ("Treatment", 1, "0.120***", "(0.080)"),
        ("Present bias index", 0, "0.250***", "(0.050)"), ("Present bias index", 1, "-0.031", "(0.042)")]
    assert pt.columns == {0: "(1) Zero contributions", 1: "(2) Contribution rate"}
    assert pt.stats["control_mean"][0].num.raw == "0.099" and pt.stats["observations"][1].num.value == 1150
    assert pt.thresholds == {"*": 0.10, "**": 0.05, "***": 0.01}
    assert pt.paren == "se" and pt.paren_source == "table note" and pt.se_types == ["robust"]


# ================================================================ the test paper
def _planted(item_id):
    key = yaml.safe_load((FIXTURES / "latex_basic" / "expected.yaml").read_text())
    if item_id == "negatives":
        return key["negatives"]
    return next(p for p in key["planted"] if p["id"] == item_id)


def _matches(f, item):
    if f.check_id not in item["checks"]:
        return False
    if "quote" in item:
        return bool(f.quote and (find_quote(item["quote"], f.quote) or find_quote(f.quote, item["quote"])))
    return f.extra.get("table") == item.get("table")


@pytest.fixture()
def paper_findings(latex_map, run):
    pm, work = latex_map
    findings, coverage = run(pm, work)
    return pm, work, findings, coverage


@pytest.mark.parametrize("item_id", ["P01", "P19", "P20", "P21", "P22", "P02"])
def test_planted_number_problems_are_found(paper_findings, item_id):
    _, _, findings, _ = paper_findings
    item = _planted(item_id)
    hits = [f for f in findings if _matches(f, item)]
    assert hits, f"{item_id} not found: {item['truth']}"
    if item_id == "P22":
        assert hits[0].extra["cell"] == "0.120***" and hits[0].extra["strong"]


def test_planted_findings_have_honest_statuses(paper_findings):
    _, _, findings, _ = paper_findings
    p01 = next(f for f in findings if _matches(f, _planted("P01")))
    assert p01.status == "confirmed" and "18.2%" in p01.problem and p01.fix.replacement == "by 18%"
    p20 = next(f for f in findings if _matches(f, _planted("P20")))
    assert p20.status == "confirmed" and "5 percentage points" in p20.fix.replacement
    p21 = next(f for f in findings if _matches(f, _planted("P21")))
    assert p21.status == "confirmed" and p21.severity == "major" and "NUM-08" in p21.extra["also_checks"]
    p22 = next(f for f in findings if _matches(f, _planted("P22")))
    assert p22.status == "confirmed" and p22.fix.original == "0.120***" and p22.fix.replacement == "0.120"
    p19 = next(f for f in findings if _matches(f, _planted("P19")))
    assert p19.status == "likely"  # GRIM assumes one integer rating per participant
    assert "3.44" in p19.problem and "3.48" in p19.problem
    p02 = next(f for f in findings if _matches(f, _planted("P02")))
    assert p02.status == "likely"  # 1,200 could count an earlier stage, such as recruitment


def test_negatives_are_not_flagged(paper_findings):
    pm, _, findings, _ = paper_findings
    for neg in _planted("negatives"):
        if "cell" in neg:
            assert not [f for f in findings if f.check_id == "NUM-03" and f.extra.get("cell") == neg["cell"]], neg
        else:
            for f in findings:
                block = pm.block(f.locations[0].block)
                span = find_quote(neg["quote"], block.text)
                fspan = find_quote(f.quote, block.text)
                assert not (span and fspan and fspan[0] < span[1] and span[0] < fspan[1]), (neg["quote"], f.title)


def test_only_expected_findings_on_the_test_paper(paper_findings):
    """No false positives: every finding is a planted item, or the abstract's unsupported beta = 0.82."""
    _, _, findings, _ = paper_findings
    planted = [_planted(i) for i in ("P01", "P02", "P19", "P20", "P21", "P22")]
    for f in findings:
        known = any(_matches(f, item) for item in planted)
        beta = f.check_id == "NUM-01" and f.status == "needs_human" and "0.82" in f.problem
        assert known or beta, (f.check_id, f.title, f.problem)
    assert len(findings) == 7


def test_findings_meet_the_evidence_rules(paper_findings):
    pm, work, findings, _ = paper_findings
    assert_well_formed(pm, findings, work)
    path = work.parent / "numbers_findings.json"
    FindingSet(producer="scripts", findings=findings).save(path)
    fs, errors, _ = load_findings_file(path)
    assert fs is not None and not errors and len(fs.findings) == len(findings)


def test_coverage_on_the_test_paper(paper_findings):
    _, _, _, coverage = paper_findings
    assert set(coverage) == NUM_IDS
    for cid, c in coverage.items():
        assert c.status in ("run", "not_applicable", "skipped")
        if c.status != "run":
            assert c.reason, cid
    assert coverage["NUM-06"].status == "not_applicable"  # no sentence quotes a number with "Table 1"
    assert coverage["NUM-03"].status == "run" and coverage["NUM-03"].count == 2
    assert "4 table estimates" in coverage["NUM-03"].reason
    assert coverage["BEH-09"].status == "run" and coverage["BEH-09"].count == 0  # robust SEs, individual assignment


# ================================================================ coverage on other papers
def test_no_tables_means_not_applicable(run):
    pm = make_map([("paragraph", "1 Introduction", "Saving is too low in many countries.")])
    _, cov = run(pm)
    for cid in ("NUM-03", "NUM-06", "BEH-09"):
        assert cov[cid].status == "not_applicable" and cov[cid].reason, cid


def test_unparseable_starred_table_is_skipped_with_a_reason(run):
    rows = [["", "(1)", "(2)"], ["Treatment", "0.120***a", "0.08**b"], ["Controls", "Yes", "Yes"]]
    pm = make_map([("paragraph", "3 Results", "Table 1 reports the estimates.")], [(rows, "* p<0.1", "1")])
    _, cov = run(pm)
    assert cov["NUM-03"].status == "skipped" and "could be paired" in cov["NUM-03"].reason


# ================================================================ regression tables
def _table_paper(rows, notes, caption="Main results", text="Table 1 reports the estimates."):
    return make_map([("paragraph", "3 Results", text)], [(rows, notes, "1", caption)])


def test_default_thresholds_flag_only_what_fails_under_both_conventions(run, tmp_path):
    rows = [["", "(1)", "(2)", "(3)"], ["Treatment", "0.25*", "0.10**", "0.120*"], ["", "(0.10)", "(0.08)", "(0.045)"],
            ["Observations", "400", "400", "400"]]
    pm = _table_paper(rows, "Robust standard errors in parentheses.")
    findings, _ = run(pm)
    stars = by_check(findings, "NUM-03")
    cells = {f.extra["cell"]: f for f in stars}
    assert set(cells) == {"0.10**", "0.120*"}  # 0.25* fits the esttab convention, so it is not flagged
    assert cells["0.10**"].status == "likely" and "star thresholds" in cells["0.10**"].extra["assumptions"]
    assert cells["0.10**"].severity == "major" and cells["0.120*"].severity == "minor"
    assert_well_formed(pm, findings, tmp_path)


def test_ratio_tables_and_other_tests_are_not_star_checked(run):
    rows = [["", "(1)"], ["Treatment", "1.25***"], ["", "(0.10)"]]
    for caption, notes in [("Odds ratios", "Standard errors in parentheses. *** p<0.01"),
                           ("Results", "Stars denote the difference from the control group. *** p<0.01")]:
        findings, cov = run(_table_paper(rows, notes, caption))
        assert not by_check(findings, "NUM-03")
        assert "not checked" in (cov["NUM-03"].reason or "")


def test_unmarked_columns_constants_and_sds_are_not_flagged(run):
    rows = [["", "Control", "Treatment", "Difference"], ["Age", "34.2", "33.9", "0.3"], ["", "(10.1)", "(9.8)", "(0.9)"],
            ["Constant", "2.10", "2.20", "0.10**"], ["", "(0.10)", "(0.20)", "(0.05)"]]
    findings, _ = run(_table_paper(rows, "Means; standard deviations in parentheses. ** p<0.05"))
    assert not by_check(findings, "NUM-03")
    findings, _ = run(_table_paper(rows, "Standard errors in parentheses. ** p<0.05"))
    assert not [f for f in by_check(findings, "NUM-03") if f.extra.get("row") in ("Age", "Constant")
                and f.extra.get("verdict") == "understated"]


def test_clustered_table_with_few_clusters(run, tmp_path):
    rows = [["", "(1)", "(2)"], ["", "Log earnings", "Hours"], ["Treatment", "0.50***", "0.030**"],
            ["", "(0.10)", "(0.010)"], ["", "[0.30, 0.70]", "[0.010, 0.050]"], ["Clusters", "12", "12"],
            ["Observations", "400", "400"]]
    notes = ("Standard errors clustered at the session level in parentheses; 95% confidence intervals in brackets. "
             "*** p<0.01, ** p<0.05, * p<0.1.")
    paras = [("paragraph", "2 Design", "Treatment was randomized at the session level, and we ran 12 sessions.")]
    pm = make_map(paras, [(rows, notes, "1", "Earnings")])
    findings, cov = run(pm)
    # 0.030 (0.010)** is understated under the normal but fine under t(11): left to a person, if flagged at all
    assert all(f.status == "needs_human" for f in by_check(findings, "NUM-03"))
    assert "2 intervals" in cov["NUM-03"].reason
    few = [f for f in by_check(findings, "BEH-09") if "Few clusters" in f.title]
    assert few and few[0].status == "needs_human"
    assert_well_formed(pm, findings, tmp_path)


def test_confidence_interval_that_misses_the_estimate(run):
    rows = [["", "(1)"], ["Treatment", "0.50***"], ["", "(0.10)"], ["", "[0.55, 0.90]"]]
    findings, _ = run(_table_paper(rows, "Robust standard errors in parentheses; 95% confidence intervals in "
                                         "brackets. *** p<0.01"))
    ci = [f for f in by_check(findings, "NUM-03") if "interval" in f.title]
    assert ci and ci[0].status == "confirmed" and "does not contain" in ci[0].problem


def test_impossible_r_squared(run):
    rows = [["", "(1)"], ["Treatment", "0.50***"], ["", "(0.10)"], ["R-squared", "1.12"], ["Adj. R-squared", "-0.01"]]
    findings, _ = run(_table_paper(rows, "Robust standard errors in parentheses. *** p<0.01"))
    r2 = [f for f in by_check(findings, "NUM-03") if "R squared" in f.title]
    assert len(r2) == 1 and "1.12" in r2[0].problem  # a negative adjusted R squared is possible


# ================================================================ statistics in the text
TEXT_STATS = [
    ("paragraph", "3 Results", "Participants who saw the default gave more, t(28) = 2.20, p = .04."),
    ("paragraph", "3 Results", "A second test gave t(28) = 2.20, p = .01."),
    ("paragraph", "3 Results", "The interaction was F(2, 57) = 3.10, p < .05."),
    ("paragraph", "3 Results", "Choices differed, $\\chi^2(1, N = 120) = 4.50$, $p = .03$."),
    ("paragraph", "3 Results", "Ratings correlated with giving, r(98) = .25, p = .01."),
    ("paragraph", "3 Results", "The Mann-Whitney U = 300, n1 = 25, n2 = 30, p = .04."),
    ("paragraph", "3 Results", "Without degrees of freedom, t = 2.0, p = .06, which a small df can explain."),
    ("paragraph", "3 Results", "The effect is 0.12 (SE = 0.05), which is significant at the 5% level."),
]


def test_statcheck_style_reports(run, tmp_path):
    pm = make_map(TEXT_STATS)
    findings, cov = run(pm)
    flagged = {f.quote: f for f in by_check(findings, "NUM-03")}
    assert set(flagged) == {"t(28) = 2.20, p = .01", "F(2, 57) = 3.10, p < .05", "U = 300, n1 = 25, n2 = 30, p = .04"}
    assert flagged["t(28) = 2.20, p = .01"].severity == "minor"  # both below .05
    f_test = flagged["F(2, 57) = 3.10, p < .05"]
    assert f_test.severity == "major" and f_test.status == "confirmed"  # the 5% conclusion flips
    assert flagged["U = 300, n1 = 25, n2 = 30, p = .04"].status == "needs_human"
    assert "8 statistics in the text" in cov["NUM-03"].reason
    assert_well_formed(pm, findings, tmp_path)


def test_significance_claims(run, tmp_path):
    pm = make_map([
        ("paragraph", "3 Results", "The effect on effort is not significant (p = 0.01)."),
        ("paragraph", "3 Results", "The effect on time is significant (p = 0.25)."),
        ("paragraph", "3 Results", "The effect on giving is not significant (p = 0.30), but the effect on time is "
                                   "significant (p = 0.01)."),
        ("paragraph", "3 Results", "The effect is economically significant (p = 0.40)."),
        ("paragraph", "3 Results", "The effect on A is 0.12 (SE 0.08), while the effect on B is significant at the 5% level."),
    ])
    findings, _ = run(pm)
    claims = {f.quote: f for f in by_check(findings, "NUM-08")}
    assert set(claims) == {"The effect on effort is not significant (p = 0.01)",
                           "The effect on time is significant (p = 0.25)"}
    assert not by_check(findings, "NUM-03")  # the claim about B is not attached to A's estimate
    assert_well_formed(pm, findings, tmp_path)


# ================================================================ arithmetic, percent and points
def test_changes_counts_and_shares(run, tmp_path):
    pm = make_map([
        ("paragraph", "3 Results", "Giving rose from 40% to 50%, an increase of 10%."),
        ("paragraph", "3 Results", "Donations rose from 100 to 150, an increase of 40%."),
        ("paragraph", "3 Results", "Effort rose from 20 to 30, a 50% increase."),
        ("paragraph", "3 Results", "Take-up rose from 20% to 25%, an increase of about 5 percentage points."),
        ("paragraph", "3 Results", "Ratings ranged from 1 to 7, and sessions ran from 2019 to 2021."),
        ("paragraph", "3 Results", "The share rose from 0.20 to 0.25, an increase of 5 percentage points."),
        ("paragraph", "3 Results", "Of the participants, 40% chose A, 35% chose B and the remaining 20% chose C."),
        ("paragraph", "3 Results", "In total, 45 of 120 participants (40%) chose the safe lottery, and 30 of 120 (25%) "
                                   "chose the risky one."),
    ])
    findings, _ = run(pm)
    num02 = {f.title: f for f in by_check(findings, "NUM-02")}
    assert set(num02) == {"Stated change does not match the values", "Percentage does not match the count",
                          "Shares do not add up to 100%"}
    assert num02["Stated change does not match the values"].fix.replacement == "an increase of 50%"
    assert num02["Percentage does not match the count"].fix.original == "45 of 120 participants (40%)"
    num09 = by_check(findings, "NUM-09")
    assert len(num09) == 1 and num09[0].title == "Percentage-point change reported as percent"
    assert_well_formed(pm, findings, tmp_path)


def test_log_outcome_coefficients(run):
    rows = [["", "(1)", "(2)"], ["", "Log earnings", "Hours"], ["Treatment", "0.50***", "0.04"],
            ["", "(0.10)", "(0.05)"]]
    pm = make_map([("paragraph", "3 Results", "Table 1 shows that the treatment raises earnings by 50%."),
                   ("paragraph", "3 Results", "Effort rose from 20 to 30, a 50% increase."),
                   ("paragraph", "3 Results", "Table 1 shows that hours rise by 4%.")],
                  [(rows, "Robust standard errors in parentheses. *** p<0.01", "1", "Earnings")])
    findings, _ = run(pm)
    logs = [f for f in by_check(findings, "NUM-09") if "Log-point" in f.title]
    assert len(logs) == 1 and "64.9%" in logs[0].problem
    assert logs[0].quote == "Table 1 shows that the treatment raises earnings by 50%."


# ================================================================ GRIM and friends in the text and tables
def test_grim_family_in_text_and_tables(run, tmp_path):
    pm = make_map([
        ("paragraph", "3 Results", "Exactly 23.5% of the 40 participants chose the risky option."),
        ("paragraph", "3 Results", "Mean trust was 5.30 on a five-point scale (N = 30 participants)."),
        ("paragraph", "3 Results", "Mean liking was 4.80 (SD = 1.50) on a 1-5 scale (N = 25 participants)."),
        ("paragraph", "3 Results", "The mean index of four items was 3.47 on a five-point scale (N = 25 participants)."),
        ("paragraph", "3 Results", "The average treatment effect was 0.47 on a five-point scale (N = 25 participants)."),
        ("paragraph", "3 Results", "Mean patience was 3.48 on a five-point scale (N = 25 participants)."),
        ("paragraph", "3 Results", "Mean liking was 3.00 (SD = 1.01) on a five-point scale (N = 5 participants)."),
    ], [([["", "Mean", "SD", "N"], ["Female (=1)", "0.43", "0.30", "120"], ["Age", "34.2", "10.1", "120"]],
         "Summary statistics.", "1", "Summary statistics")])
    findings, _ = run(pm)
    titles = sorted(f.title for f in by_check(findings, "NUM-04"))
    assert titles == ["Mean and SD inconsistent for a binary variable in Table 1 (DEBIT)", "Mean outside the scale",
                      "Percentage impossible for 40 people (GRIM)", "Standard deviation impossible for the scale",
                      "Standard deviation may be impossible (GRIMMER)"]
    outside = next(f for f in findings if f.title == "Mean outside the scale")
    assert outside.status == "confirmed"
    grimmer = next(f for f in findings if "GRIMMER" in f.title)
    assert grimmer.status == "needs_human" and grimmer.confidence == "low"
    assert_well_formed(pm, findings, tmp_path)


# ================================================================ sample sizes
def test_sample_sizes_and_participant_flow(run, tmp_path):
    pm = make_map([
        ("abstract", None, "We study 400 participants in a lab experiment."),
        ("paragraph", "2 Design", "We randomized 1,000 participants: 480 to the control group and 500 to the treatment group."),
        ("paragraph", "2 Design", "Of the 520 participants recruited, 40 were excluded for failing attention checks, "
                                  "leaving 470."),
        ("paragraph", "3 Results", "Mean trust was 3.48 on a five-point scale (N = 25 participants)."),
    ], [([["", "(1)"], ["Treatment", "0.25**"], ["", "(0.10)"], ["Observations", "400"]],
         "Robust standard errors in parentheses. ** p<0.05", "1")])
    findings, _ = run(pm)
    titles = {f.title: f for f in by_check(findings, "NUM-05")}
    assert set(titles) == {"Sample size of participants disagrees across the paper", "Arms do not add up to the sample",
                           "Participant flow does not add up"}
    size = titles["Sample size of participants disagrees across the paper"]
    assert "1,000" in size.quote and "400" in size.problem  # abstract and Observations outvote the design section
    assert_well_formed(pm, findings, tmp_path)


def test_separate_studies_are_not_compared(run):
    pm = make_map([("paragraph", "2 Study 1", "Study 1 has 200 participants."),
                   ("paragraph", "3 Study 2", "Study 2 has 300 participants.")])
    findings, _ = run(pm)
    assert not by_check(findings, "NUM-05")


# ================================================================ text against tables
def test_numbers_quoted_with_a_table(run, tmp_path):
    rows = [["", "(1)", "(2)"], ["Treatment", "-0.018**", "0.120"], ["", "(0.008)", "(0.080)"],
            ["Control mean", "0.099", "3.12"]]
    pm = make_map([
        ("paragraph", "3 Results", "Table 1 shows an effect of 0.35 on giving, and column (2) of Table 1 adds controls."),
        ("paragraph", "3 Results", "Table 1 shows that the treatment lowers zero contributions by 1.8 percentage points, "
                                   "or 18.2% of the control mean of 9.9%."),
        ("paragraph", "3 Results", "Table 1 reports a coefficient of 0.102 in column (2)."),
    ], [(rows, "Robust standard errors in parentheses. ** p<0.05", "1")])
    findings, _ = run(pm)
    num06 = {f.extra["value"]: f for f in by_check(findings, "NUM-06")}
    assert set(num06) == {"0.35", "0.102"}  # derived values (1.8 points, 18.2%, 9.9%) are accepted
    assert num06["0.35"].status == "needs_human"
    assert num06["0.102"].status == "likely" and "swapped" in num06["0.102"].problem  # the table has 0.120
    assert_well_formed(pm, findings, tmp_path)


# ================================================================ precision, units, standard errors
def test_precision_and_units(run, tmp_path):
    rows = [["", "(1)"], ["Treatment", "0.018**"], ["", "(0.008)"], ["Control mean", "0.099"]]
    pm = make_map([
        ("paragraph", "3 Results", "The share of givers was 87.2341% in the treatment group (p = 0.000)."),
        ("paragraph", "3 Results", "Table 1 shows that the treatment raises take-up by 0.018 percentage points."),
        ("paragraph", "3 Results", "The session lasted 90 minutes (2.5 hours)."),
    ], [(rows, "Robust standard errors in parentheses. ** p<0.05", "1")])
    findings, _ = run(pm)
    titles = sorted(f.title for f in by_check(findings, "NUM-07"))
    assert titles == ["False precision", "Share coefficient reported in the wrong unit", "Unit conversion is wrong",
                      "p-value reported as zero"]
    assert_well_formed(pm, findings, tmp_path)


def test_standard_error_notes(run, tmp_path):
    rows = [["", "(1)"], ["Treatment", "0.25**"], ["", "(0.10)"]]
    session = [("paragraph", "2 Design", "Each session was randomly assigned to one treatment.")]
    cases = {
        "Standard errors in parentheses. ** p<0.05": "does not state the type",
        "Robust standard errors in parentheses. ** p<0.05": "not clustered at the level of assignment",
        "Standard errors clustered at the individual level in parentheses. ** p<0.05": "finer than the level",
    }
    for notes, expected in cases.items():
        pm = make_map(session, [(rows, notes, "1")])
        findings, _ = run(pm)
        beh = by_check(findings, "BEH-09")
        assert len(beh) == 1 and expected in beh[0].title, notes
        assert_well_formed(pm, findings, tmp_path)
    individual = [("paragraph", "2 Design", "We randomized 400 participants into two groups.")]
    findings, cov = run(make_map(individual, [(rows, "Robust standard errors in parentheses. ** p<0.05", "1")]))
    assert not by_check(findings, "BEH-09") and cov["BEH-09"].status == "run"


# ================================================================ robustness
def test_odd_inputs_do_not_crash(run):
    tables = [([], "", "1"), ([["only one column"]], "", "2"), ([["", "(1)"], ["x", "(0.000)***"], ["", "(0.000)"]], "", "3"),
              ([["", "a", "b"], ["Treatment", "0.000*", "1e-3"], ["", "(0.000)", "(abc)"]], "* p<0.1", "4")]
    pm = make_map([("paragraph", "3 Results", "Table 4 shows −12.5% (SE = 0.0), p = 1.5 and t = ."),
                   ("abstract", None, "We reduce saving by 0.0%."), ("paragraph", None, "")], tables)
    _, cov = run(pm)
    assert set(cov) == NUM_IDS
    assert not [c for c in cov.values() if (c.reason or "").startswith("check crashed")]


# ================================================================ a clean paper, and the same paper with planted errors
CLEAN_PARAS = [
    ("abstract", None, "In an online experiment with 1,204 participants, an opt-out default raises take-up of the "
                       "savings plan by 14.6 percentage points, a 47% increase over the control group."),
    ("paragraph", "2 Design", "Our sample consists of 1,240 participants recruited on Prolific, of whom 1,204 passed "
                              "both attention checks."),
    ("paragraph", "2 Design", "Participants were randomly assigned to the treatment or the control condition."),
    ("paragraph", "2 Design", "Participants were paid a show-up fee of £1.50 and earned on average £2.35 "
                              "(SD = 0.87) from the incentivized choices."),
    ("paragraph", "2 Design", "We ran 24 sessions with between 18 and 24 participants each."),
    ("paragraph", "3 Results", "In the control group, 31.2% of participants chose the plan, compared with 45.8% in the "
                               "treatment group (p < 0.001, Fisher's exact test)."),
    ("paragraph", "3 Results", "The treatment increased take-up by 14.6 percentage points (Table 1, column 1), a 47% "
                               "increase relative to the control mean of 31.2%."),
    ("paragraph", "3 Results", "The coefficient is 0.146 and significant at the 1% level (Table 1)."),
    ("paragraph", "3 Results", "Column (2) adds demographic controls; the estimate barely changes (0.139 vs. 0.146)."),
    ("paragraph", "3 Results", "Mean trust in the experimenter was 5.12 (SD = 1.31) on a seven-point scale (N = 1,204)."),
    ("paragraph", "3 Results", "Take-up rose from 31.2% to 45.8%, an increase of 14.6 percentage points or 47%."),
    ("paragraph", "3 Results", "A one-standard-deviation increase in present bias (0.23) reduces contributions by "
                               "0.8 percentage points (SE 0.3)."),
    ("paragraph", "3 Results", "A Wilcoxon rank-sum test confirms the difference (z = 4.21, p < 0.001), and choices "
                               "differed across arms ($\\chi^2(2) = 9.87$, $p = 0.007$)."),
    ("paragraph", "3 Results", "Table 2 shows that the treatment raises log savings by 0.083, or about 8.7%."),
    ("paragraph", "3 Results", "The effect is robust to excluding the 36 participants who failed an attention check "
                               "(Table A2)."),
    ("paragraph", "1 Introduction", "In 2023, 45% of US workers had access to an employer plan (Bureau of Labor "
                                    "Statistics, 2023), and Madrian and Shea (2001) found that participation rose from "
                                    "37% to 86%."),
    ("paragraph", "5 Conclusion", "Defaults raised take-up by nearly 15 percentage points."),
    ("footnote", "3 Results", "Of the 1,204 participants, 602 were assigned to the control group and 602 to the "
                              "treatment group."),
]
CLEAN_TABLES = [
    ([["", "(1)", "(2)"], ["", "Take-up", "Take-up"], ["Treatment", "0.146***", "0.139***"], ["", "(0.027)", "(0.026)"],
      ["Present bias", "", "-0.008**"], ["", "", "(0.003)"], ["Constant", "0.312***", "0.298***"],
      ["", "(0.019)", "(0.041)"], ["Controls", "No", "Yes"], ["Control mean", "0.312", "0.312"],
      ["Observations", "1,204", "1,204"], ["R-squared", "0.022", "0.048"]],
     "Robust standard errors in parentheses. *** p<0.01, ** p<0.05, * p<0.1.", "1", "Effect of the default on take-up"),
    ([["", "(1)"], ["", "Log savings"], ["Treatment", "0.083**"], ["", "(0.036)"], ["", "[0.012, 0.154]"],
      ["Observations", "1,204"]],
     "Heteroskedasticity-robust standard errors in parentheses and 95% confidence intervals in brackets. "
     "*** p<0.01, ** p<0.05, * p<0.1.", "2", "Savings"),
    ([["", "Control", "Treatment", "p-value"], ["Female (=1)", "0.51", "0.49", "0.48"], ["", "(0.50)", "(0.50)", ""],
      ["Age", "34.2", "33.9", "0.61"], ["", "(10.1)", "(9.8)", ""], ["Observations", "602", "602", ""]],
     "Means with standard deviations in parentheses. The last column reports p-values of t-tests.", "3", "Balance"),
]


def _perturbed(where, old, new):
    paras = [list(p) for p in CLEAN_PARAS]
    tables = [[[list(r) for r in t[0]]] + list(t[1:]) for t in CLEAN_TABLES]
    if where[0] == "para":
        assert old in paras[where[1]][2]
        paras[where[1]][2] = paras[where[1]][2].replace(old, new)
    elif where[0] == "note":
        assert tables[where[1]][1] == old
        tables[where[1]][1] = new
    else:
        _, t, i, j = where
        assert tables[t][0][i][j] == old
        tables[t][0][i][j] = new
    return make_map([tuple(p) for p in paras], [tuple(t) for t in tables])


def test_clean_paper_has_no_findings(run):
    findings, cov = run(make_map(CLEAN_PARAS, CLEAN_TABLES))
    assert not findings, [(f.check_id, f.title, f.problem) for f in findings]
    assert all(c.status == "run" for c in cov.values())


@pytest.mark.parametrize("where,old,new,check", [
    (("para", 0), "by 14.6 percentage points", "by 16.4 percentage points", "NUM-01"),
    (("table", 0, 3, 2), "(0.026)", "(0.096)", "NUM-03"),
    (("para", 10), "an increase of 14.6 percentage points or 47%", "an increase of 14.6%", "NUM-09"),
    (("table", 2, 1, 1), "0.51", "0.31", "NUM-04"),
    (("para", 17), "602 to the treatment group", "612 to the treatment group", "NUM-05"),
    (("para", 9), "(SD = 1.31)", "(SD = 3.10)", "NUM-04"),
    (("para", 12), "z = 4.21", "z = 1.21", "NUM-03"),
    (("para", 6), "by 14.6 percentage points (Table 1", "by 16.4 percentage points (Table 1", "NUM-06"),
    (("para", 7), "significant at the 1% level", "not significant at the 5% level", "NUM-08"),
    (("para", 10), "to 45.8%, an increase", "to 44.8%, an increase", "NUM-02"),
    (("note", 0), "Robust standard errors in parentheses. *** p<0.01, ** p<0.05, * p<0.1.",
     "Standard errors in parentheses. *** p<0.01, ** p<0.05, * p<0.1.", "BEH-09"),
    (("para", 5), "(p < 0.001, Fisher's exact test)", "(p = 0.000, Fisher's exact test)", "NUM-07"),
    (("para", 13), "or about 8.7%", "or 8.3%", None),  # 100 (exp(0.083) - 1) = 8.65: the approximation is fine
])
def test_planted_errors_in_the_clean_paper_are_caught(run, tmp_path, where, old, new, check):
    pm = _perturbed(where, old, new)
    findings, _ = run(pm)
    if check is None:
        assert not findings, [(f.check_id, f.problem) for f in findings]
        return
    assert [f.check_id for f in findings] == [check], [(f.check_id, f.title, f.problem) for f in findings]
    assert_well_formed(pm, findings, tmp_path)


# ================================================================ more paths
def test_total_rows_and_best_values(run, tmp_path):
    totals = [["", "Control", "Treatment"], ["Session 1", "20", "22"], ["Session 2", "18", "20"], ["Total", "38", "45"]]
    est = [["", "(1)", "(2)", "(3)"], ["Treatment", "0.120**", "0.250***", "0.080*"], ["", "(0.050)", "(0.060)", "(0.045)"]]
    pm = make_map([("paragraph", "3 Results", "Table 2 shows that the largest effect, 0.120, is in column (1).")],
                  [(totals, "Number of participants per session.", "1"),
                   (est, "Robust standard errors in parentheses. *** p<0.01, ** p<0.05, * p<0.1", "2")])
    findings, _ = run(pm)
    total = [f for f in by_check(findings, "NUM-02") if "Total row" in f.title]
    assert len(total) == 1 and "42" in total[0].problem and "45" in total[0].problem
    best = [f for f in by_check(findings, "NUM-06") if "largest" in f.title]
    assert len(best) == 1 and best[0].status == "needs_human"
    assert_well_formed(pm, findings, tmp_path)


def test_bold_cell_that_is_not_the_best(run):
    rows = [["", "(1)", "(2)", "(3)"], ["Accuracy", "0.71", "0.65", "0.80"]]
    # bold marks the middle value, which is neither the highest nor the lowest
    raw = "\\begin{tabular}{lccc}\n & (1) & (2) & (3) \\\\\nAccuracy & \\textbf{0.71} & 0.65 & 0.80 \\\\\n\\end{tabular}"
    findings, _ = run(make_map([], [(rows, "", "1", "Accuracy", raw)]))
    bold = [f for f in by_check(findings, "NUM-06") if "Bold" in f.title]
    assert len(bold) == 1 and bold[0].status == "needs_human"


def test_impossible_shares_probabilities_and_standard_errors(run):
    rows = [["", "(1)"], ["Treatment", "0.50***"], ["", "(-0.10)"]]
    pm = make_map([("paragraph", "3 Results", "The share of givers was 112% in the treatment group."),
                   ("paragraph", "3 Results", "The probability of choosing the lottery is 1.3 in the treatment group."),
                   ("paragraph", "3 Results", "The share of givers was 112% higher than in the control group, and the "
                                              "probability of giving is 1.5 times as large.")],
                  [(rows, "Robust standard errors in parentheses. *** p<0.01", "1")])
    findings, _ = run(pm)
    assert sorted(f.title for f in by_check(findings, "NUM-07")) == ["Impossible probability", "Impossible share"]
    assert [f.title for f in by_check(findings, "NUM-03") if "Negative" in f.title] == ["Negative standard error in Table 1"]


def test_points_reported_as_percent(run, tmp_path):
    rows = [["", "(1)"], ["Treatment", "-0.018**"], ["", "(0.008)"], ["Control mean", "0.099"]]
    pm = make_map([("abstract", None, "Automatic enrollment reduces the share of employees who save nothing by 1.8%."),
                   ("paragraph", "3 Results", "Automatic enrollment lowers the share of employees who save nothing from "
                                              "9.9% in the control group to 8.1% in the treatment group."),
                   ("paragraph", "3 Results", "Table 1 shows that automatic enrollment lowers zero saving by 1.8%.")],
                  [(rows, "Robust standard errors in parentheses. ** p<0.05", "1", "Zero saving")])
    findings, _ = run(pm)
    titles = sorted(f.title for f in by_check(findings, "NUM-09"))
    assert titles == ["Percentage-point change reported as percent", "Percentage-point effect reported as percent"]
    assert not by_check(findings, "NUM-01")  # the headline matches the point change, so it is a unit problem
    assert_well_formed(pm, findings, tmp_path)


def test_roles_and_table_blocks_from_other_readers():
    pm = make_map([("paragraph", "Abstract", "We find a 23% reduction."), ("paragraph", "3.1 Summary statistics", "x"),
                   ("paragraph", "6 Conclusion", "y"), ("paragraph", "1 Introduction", "z")],
                  [([["", "(1)"], ["Treatment", "0.120***"], ["", "(0.080)"]], "*** p<0.01", "1")])
    for b in pm.blocks:
        b.attrs.pop("table_id", None)  # a reader that does not link tables to their blocks
    paper = num._paper(pm)
    assert [s.role for s in paper.sents] == ["abstract", "body", "conclusion", "intro"]
    assert paper.tables[0].block is pm.blocks[-1] and len(paper.tables[0].estimates) == 1


def test_p_values_next_to_estimates(run, tmp_path):
    rows = [["", "(1)", "(2)"], ["Treatment", "0.120", "0.250***"], ["", "(0.080)", "(0.050)"]]
    pm = make_map([("paragraph", "3 Results", "Treatment increases giving by 0.12 (SE 0.08; p < 0.05)."),
                   ("paragraph", "3 Results", "In Table 1, the coefficient in column (1) is 0.120 (p < 0.01), and the one "
                                              "in column (2) is 0.250 (p < 0.01).")],
                  [(rows, "Robust standard errors in parentheses. *** p<0.01", "1")])
    findings, _ = run(pm)
    flagged = sorted(f.quote for f in by_check(findings, "NUM-03"))
    assert flagged == ["0.12 (SE 0.08; p < 0.05)", "0.120 (p < 0.01)"]
    assert all(f.severity == "major" for f in by_check(findings, "NUM-03"))  # both claim p < 0.05; t = 1.5
    assert_well_formed(pm, findings, tmp_path)


def test_percentages_and_money_are_not_head_counts(run):
    paras = [("paragraph", "1 Introduction", "In our data, 94 percent of households report incomes below 25,000, and "
              "a \\$2,000 fluctuation for a household is common."),  # LaTeX writes a dollar sign as \\$
             ("paragraph", "3 Data", "The sample has 1,200 households."),
             ("paragraph", "4 Results", "Only 24 percent of households borrowed.")]
    findings, _ = run(make_map(paras, []))
    assert not by_check(findings, "NUM-05"), [(f.title, f.problem) for f in by_check(findings, "NUM-05")]


def test_numbers_the_sentence_places_outside_the_table_or_in_its_note(run):
    rows = [["", "(1)", "(2)"], ["Treatment", "0.051**", "0.047**"], ["", "(0.020)", "(0.021)"]]
    note = "Robust standard errors in parentheses. ** p<0.05. The break-even rate implied by column (2) is 0.37."
    pm = make_map([
        ("paragraph", "3 Results", "Two further estimates, not reported in Table 1, are 0.0061 and 0.0275."),
        ("paragraph", "3 Results", "The break-even rate is 0.37 (Table 1)."),
        ("paragraph", "3 Results", "Table 1 reports a coefficient of 0.066 in column (1)."),
    ], [(rows, note, "1")])
    findings, _ = run(pm)
    assert {f.extra["value"] for f in by_check(findings, "NUM-06")} == {"0.066"}


def test_a_table_named_by_a_cross_reference_field_is_masked_but_still_read_as_not_shown():
    assert num._NOT_IN_TABLE.search("two estimates, not reported in " + num.MASK * 7 + ", are 0.1 and 0.2")
    assert num._NOT_IN_TABLE.search("values omitted from Table 3 are small")
    assert not num._NOT_IN_TABLE.search("the estimates reported in Table 3 are 0.1 and 0.2")
