"""Integrity checks: ETH-06 verbatim overlap with cited works, ETH-07 duplicate images."""

import random
import shutil
from pathlib import Path

import pytest

from paper_check.checks import Context, run_checks
from paper_check.checks.integrity import _quoted
from paper_check.config import PaperSettings
from paper_check.ingest import ingest
from paper_check.model import FindingSet, PaperMap
from paper_check.verify import verify_work

FIXTURES = Path(__file__).resolve().parent / "fixtures"
COPIED = ("We partnered with a large employer and randomized 1,150 newly hired employees into a control "
          "group and a treatment group with automatic enrollment at a 3% contribution rate.")


def _run(pm, work, only):
    ctx = Context(work=work, settings=PaperSettings())
    return run_checks(pm, ctx, only)


def test_quoted_detection():
    text = 'They wrote "the quick brown fox jumps" and left.'
    s = text.index("the quick")
    assert _quoted(text, s, s + len("the quick brown fox jumps"))
    plain = "They wrote the quick brown fox jumps and left."
    s = plain.index("the quick")
    assert not _quoted(plain, s, s + 25)


def test_eth06_skipped_before_cite_prepare(latex_map, work_copy):
    pm, _ = latex_map
    result = _run(pm, work_copy, {"ETH-06"})
    cov = {c.check_id: c for c in result.coverage}
    assert cov["ETH-06"].status == "skipped" and "cite-prepare" in cov["ETH-06"].reason


def test_eth06_finds_copied_passage_and_quotes_verify(latex_map, work_copy):
    pm, _ = latex_map
    src = work_copy / "citations" / "sources"
    src.mkdir(parents=True)
    ref = pm.reference("madrian2001").id
    (src / f"{ref}.txt").write_text(
        "[[page 1]]\nSome unrelated opening text about pensions.\n[[page 2]]\n"
        "In our study, we partnered with a large employer and randomized 1,150 newly hired\n"
        "employees into a control group and a treatment group with automatic enrollment at a 3%\n"
        "contribution rate. Other words follow here.\n", encoding="utf-8")
    result = _run(pm, work_copy, {"ETH-06"})
    found = [f for f in result.findings if f.check_id == "ETH-06"]
    assert len(found) == 1
    f = found[0]
    assert f.quote.startswith("We partnered with a large employer") and f.quote.endswith("3% contribution rate")
    src_ev = [e for e in f.evidence if e.type == "source_quote"][0]
    assert src_ev.ref == ref and src_ev.page == "2"
    assert "not cited in this passage" in f.problem
    result.save(work_copy / "findings" / "scripts.json")
    verify_work(work_copy)
    saved = FindingSet.load(work_copy / "findings" / "scripts.json")
    assert [x.status for x in saved.findings if x.check_id == "ETH-06"] == ["likely"]


def test_eth06_ignores_short_shared_phrases(latex_map, work_copy):
    pm, _ = latex_map
    src = work_copy / "citations" / "sources"
    src.mkdir(parents=True)
    (src / "r001.txt").write_text("[[page 1]]\nWe partnered with a large employer and then did other things.",
                                  encoding="utf-8")
    result = _run(pm, work_copy, {"ETH-06"})
    assert not [f for f in result.findings if f.check_id == "ETH-06"]


def test_eth07_missing_figure_files_are_skipped(latex_map, work_copy):
    pm, _ = latex_map
    result = _run(pm, work_copy, {"ETH-07"})
    cov = {c.check_id: c for c in result.coverage}
    assert cov["ETH-07"].status == "skipped" and "figures/dist.pdf" in cov["ETH-07"].reason


def _noise(seed, size=(240, 240)):
    from PIL import Image

    rnd = random.Random(seed)
    img = Image.new("RGB", size)
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(size[0] * size[1])])
    return img.resize((size[0] * 2, size[1] * 2))


def test_eth07_flags_duplicate_figures(tmp_path):
    pytest.importorskip("imagehash")
    paper = tmp_path / "paper"
    shutil.copytree(FIXTURES / "latex_basic", paper)
    figs = paper / "figures"
    figs.mkdir(exist_ok=True)
    _noise(1).save(figs / "dist.png")
    _noise(1).save(figs / "copy.png")      # the same image again
    _noise(2).save(figs / "other.png")     # a different image
    results = paper / "sections" / "results.tex"
    tex = results.read_text(encoding="utf-8").replace("figures/dist.pdf", "figures/dist.png")
    tex += ("\n\\begin{figure}\\includegraphics{figures/copy.png}\\caption{Robustness of the distribution.}"
            "\\end{figure}\n\\begin{figure}\\includegraphics{figures/other.png}\\caption{Another figure.}\\end{figure}\n")
    results.write_text(tex, encoding="utf-8")
    ingest(paper, output=str(tmp_path / "out"))
    work = tmp_path / "out" / "paper-check-work"
    pm = PaperMap.load(work / "paper_map.json")
    result = _run(pm, work, {"ETH-07"})
    found = [f for f in result.findings if f.check_id == "ETH-07"]
    assert len(found) == 1, [f.problem for f in found]
    f = found[0]
    assert "Figure 1 (dist.png)" in f.problem and "Figure 2 (copy.png)" in f.problem
    assert f.status == "needs_human"
    images = [e for e in f.evidence if e.type == "image"]
    assert all(Path(e.data["path"]).exists() for e in images)
    cov = {c.check_id: c for c in result.coverage}
    assert cov["ETH-07"].status == "run" and "3 raster images" in cov["ETH-07"].reason
