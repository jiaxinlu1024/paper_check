"""NUM-10: sample sizes across tables and models, the user's checklist item B1."""

from pathlib import Path

from paper_check.checks import Context, run_checks
from paper_check.config import PaperSettings
from paper_check.model import Anchor, Block, PaperMap, Table


def _pm(tables, paragraphs):
    blocks = [Block(id=f"p{i}", kind="paragraph", text=t, anchor=Anchor(paragraph=i)) for i, t in enumerate(paragraphs, 1)]
    for t in tables:
        text = "\n".join(" | ".join(r) for r in t.rows) + (f"\nNotes: {t.notes}" if t.notes else "")
        blocks.append(Block(id=f"t{t.number}", kind="table", text=text, anchor=Anchor(paragraph=100),
                            attrs={"number": t.number, "table_id": t.id}))
    return PaperMap(source={"format": "docx"}, blocks=blocks, tables=tables)


def _run(pm, tmp_path):
    result = run_checks(pm, Context(work=tmp_path, settings=PaperSettings()), {"NUM-10"})
    return [f for f in result.findings if f.check_id == "NUM-10"], {c.check_id: c for c in result.coverage}


def _table(num, rows, notes=""):
    return Table(id=f"tab{num}", anchor=Anchor(paragraph=100), number=str(num), rows=rows, notes=notes)


def test_unexplained_subsample_is_flagged(tmp_path):
    t1 = _table(1, [["", "(1)", "(2)"], ["Observations", "5,000", "5,000"]])
    t2 = _table(2, [["", "(1)", "(2)"], ["Observations", "5,000", "3,210"]])
    t3 = _table(3, [["", "(1)"], ["Observations", "5,000"]])
    found, _ = _run(_pm([t1, t2, t3], ["Table 2 reports the main estimates."]), tmp_path)
    assert len(found) == 1 and found[0].extra["n"] == 3210 and found[0].severity == "major"
    assert found[0].quote == "Observations | 5,000 | 3,210"


def test_splits_text_mentions_and_note_explanations_are_not_flagged(tmp_path):
    split = _table(1, [["", "All", "Treated", "Control"], ["Observations", "5,000", "2,100", "2,900"]])
    stated = _table(2, [["", "(1)"], ["Observations", "4,321"]])
    noted = _table(3, [["", "(1)"], ["Observations", "4,800"]], notes="The sample excludes respondents with missing income.")
    main = _table(4, [["", "(1)"], ["Observations", "5,000"]])
    found, cov = _run(_pm([split, stated, noted, main], ["Our survey sample has 4,321 respondents in wave 2."]), tmp_path)
    assert not found
    assert cov["NUM-10"].status == "run" and "splits" in cov["NUM-10"].reason


def test_unit_counts_are_explained_as_units(tmp_path):
    t1 = _table(1, [["", "(1)"], ["Observations", "412"]])
    t2 = _table(2, [["", "(1)"], ["Observations", "1,647"]])
    t3 = _table(3, [["", "(1)"], ["Observations", "1,647"]])
    found, _ = _run(_pm([t1, t2, t3], []), tmp_path)
    assert len(found) == 1 and found[0].severity == "minor" and "about 4 times" in found[0].problem


def test_no_observation_rows_is_not_applicable(tmp_path):
    found, cov = _run(_pm([_table(1, [["", "Mean"], ["Income", "52.1"]])], []), tmp_path)
    assert not found and cov["NUM-10"].status == "not_applicable"
