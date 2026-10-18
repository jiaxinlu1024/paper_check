"""BEH-15 script part: citing sentences against the verified misattribution list."""

from paper_check.checks import Context, run_checks
from paper_check.config import PaperSettings


def _run(pm, work):
    return run_checks(pm, Context(work=work, settings=PaperSettings()), {"BEH-15"})


def test_loss_aversion_estimate_attributed_to_1979(latex_map, work_copy):
    pm, _ = latex_map
    result = _run(pm, work_copy)
    found = [f for f in result.findings if f.check_id == "BEH-15"]
    assert len(found) == 1, [f.quote for f in found]
    f = found[0]
    assert f.quote.startswith("Loss aversion, with a coefficient of about 2.25")
    assert f.extra["entry"] == "loss-aversion-coefficient" and f.extra["failure_code"] == "S4"
    assert f.status == "likely" and f.severity == "major"
    assert f.fix.original == "Kahneman and Tversky (1979)" and f.fix.replacement == "Tversky and Kahneman (1992)"
    cov = {c.check_id: c for c in result.coverage}
    assert cov["BEH-15"].status == "run" and "misattribution list" in cov["BEH-15"].reason


def test_correct_classic_citations_are_not_flagged(latex_map, work_copy):
    pm, _ = latex_map
    quotes = [f.quote for f in _run(pm, work_copy).findings]
    assert not any("401(k) participation" in q for q in quotes)
    assert not any("flat-rate contracts" in q for q in quotes)
