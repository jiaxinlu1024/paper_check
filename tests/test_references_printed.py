"""FMT-08 on printed reference lists: acronyms that a style or reference manager lowercased."""

from pathlib import Path

from paper_check.checks import Context, run_checks
from paper_check.config import PaperSettings
from paper_check.ingest import ingest
from paper_check.model import PaperMap

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_lowercased_acronym_in_printed_pdf_reference(tmp_path):
    ingest(FIXTURES / "pdf_basic" / "paper.pdf", output=str(tmp_path))
    work = tmp_path / "paper-check-work"
    pm = PaperMap.load(work / "paper_map.json")
    result = run_checks(pm, Context(work=work, settings=PaperSettings()), {"FMT-08"})
    found = [f for f in result.findings if f.title == "Acronym printed in lowercase in a reference title"]
    assert len(found) == 1
    f = found[0]
    assert f.extra["acronyms"] == ["OECD"] and "oecd" in f.quote
    assert f.fix.replacement.endswith("Evidence from the OECD")


def test_bibtex_titles_are_not_rechecked_as_printed(latex_map, work_copy):
    pm, _ = latex_map
    result = run_checks(pm, Context(work=work_copy, settings=PaperSettings()), {"FMT-08"})
    assert not [f for f in result.findings if f.title == "Acronym printed in lowercase in a reference title"]
