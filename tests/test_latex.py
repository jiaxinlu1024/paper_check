"""LaTeX reader: anchors, citations, cross-references, tables, notes."""

from paper_check.textutil import find_quote


def _block_with(pm, quote):
    for b in pm.blocks:
        if find_quote(quote, b.text):
            return b
    raise AssertionError(f"quote not found: {quote}")


def test_anchors_point_to_included_files(latex_map):
    pm, _ = latex_map
    b = _block_with(pm, "Earlier studies have also examined present bias in gym attendance")
    assert b.anchor.file == "sections/intro.tex" and b.anchor.line == 4
    assert b.section == ["1 Introduction"]


def test_citations_render_author_year_and_keep_keys(latex_map):
    pm, _ = latex_map
    b = _block_with(pm, "Earlier studies have also examined")
    cites = {tuple(c.keys): b.text[c.start:c.end] for c in b.citations}
    assert cites[("madrian2001",)] == "(Madrian and Shea, 2001)"
    assert cites[("dellavigna2006",)] == "DellaVigna and Malmendier (2006)"


def test_unresolved_citation_and_reference_are_marked(latex_map):
    pm, _ = latex_map
    b = _block_with(pm, "In our previous work")
    assert any(not c.resolved and c.keys == ["lu2024"] for c in b.citations)
    b = _block_with(pm, "reports robustness checks")
    assert "Table ?? reports robustness checks" in b.text
    assert any(not r.resolved and r.labels == ["tab:robust"] for r in b.crossrefs)
    b = _block_with(pm, "reports the main estimates")
    assert b.text.startswith("Table 1 reports")


def test_table_rows_and_notes(latex_map):
    pm, _ = latex_map
    t = pm.tables[0]
    assert t.label == "tab:main" and t.number == "1"
    assert ["Treatment", "-0.018**", "0.120***"] in t.rows
    assert ["", "(0.008)", "(0.080)"] in t.rows
    assert t.notes.startswith("Notes: Robust standard errors")


def test_comments_and_hidden_text_are_recorded(latex_map):
    pm, _ = latex_map
    assert any(n.kind == "latex_comment" and n.text.startswith("reviewer 2 asked for more robustness")
               and n.anchor.file == "sections/intro.tex" for n in pm.notes)
    assert any(n.kind == "hidden_text" and "Ignore all previous instructions" in n.text for n in pm.notes)
    hidden = [b for b in pm.blocks if b.attrs.get("hidden")]
    assert hidden and hidden[0].attrs["hidden"] == "white text"


def test_references_from_bib_only_cited(latex_map):
    pm, _ = latex_map
    keys = {r.key for r in pm.references}
    assert "tversky1992" not in keys  # in the .bib but never cited
    assert {"laibson1997", "smithson2019", "brown2015"} <= keys
    laibson = pm.reference("laibson1997")
    assert laibson.fields["year"] == "1998" and laibson.fields["doi"] == "10.1162/003355397555253"
    assert pm.metadata["cited_keys_missing_from_bib"] == ["lu2024"]


def test_front_matter_and_abbreviations(latex_map):
    pm, _ = latex_map
    kinds = [b.kind for b in pm.blocks[:10]]
    assert "title" in kinds and "abstract" in kinds and "jel" in kinds and "keywords" in kinds
    rct = next(a for a in pm.abbreviations if a["abbr"] == "RCT")
    assert rct["first_use"]["start"] < rct["defined_at"][0]["start"]


def test_text_dump_and_definitions_written(latex_map):
    _, work = latex_map
    text = (work / "paper_text.md").read_text()
    assert "[b0012 · paragraph · 1 Introduction · sections/intro.tex:4-5]" in text
    assert "Let $\\beta$ denote the present-bias parameter" in (work / "definitions.md").read_text()
