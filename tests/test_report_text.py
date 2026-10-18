"""How the report shortens text for its first page and its tables: whole sentences, places in a few words,
and fixes that say what to change without being cut in the middle."""

from paper_check.model import Finding, Fix
from paper_check.report import Locator, _clip, _fix_lines, _fix_short, _lead


def test_a_short_replacement_is_shown_whole_without_a_second_period():
    fx = Fix(action="replace", original="Our second result is to bound this effect.",
             replacement="Our first result also bounds this effect.")
    assert _fix_short(fx, 260) == ('replace "Our second result is to bound this effect." with '
                                   '"Our first result also bounds this effect."')


def test_a_long_replacement_names_the_words_and_where_the_new_wording_is():
    fx = Fix(action="replace", original="shows that the default causes higher saving",
             replacement="is consistent with the default raising saving in the pilot sample; " + "x " * 200)
    assert _fix_short(fx, 320) == ('reword "shows that the default causes higher saving"; '
                                   'the new wording is in the entry.')
    long_original = Fix(action="replace", original="word " * 60, replacement="new " * 60)
    short = _fix_short(long_original, 320, "paper-check-evidence.md")
    assert short.startswith('reword the passage beginning "word word') and "…" not in short
    assert short.endswith("the new wording is in paper-check-evidence.md.")


def test_other_fixes_give_their_first_sentence_or_nothing():
    fx = Fix(action="insert", detail="Report the 23% in the results, or drop it. Then say why.")
    assert _fix_short(fx, 300) == "Report the 23% in the results, or drop it."
    assert _fix_short(Fix(action="insert", detail="A very long sentence " * 30 + "."), 300) is None


def test_a_first_sentence_does_not_stop_inside_a_quoted_example():
    text = ("In Word, right-click the figure and add a short description, for example: 'Bar chart. Bars "
            "show the saving rate in each treatment arm.' Keep it under 125 characters.")
    assert _lead(text, 0) == ("In Word, right-click the figure and add a short description, for example: 'Bar "
                              "chart. Bars show the saving rate in each treatment arm.'")
    # A stray apostrophe, as in '90s, runs on for at most three more sentences.
    stray = "Use data from the '90s. " + " ".join(f"Sentence {i} ends here." for i in range(8))
    assert _lead(stray, 0).count(".") <= 4


def test_clip_cuts_at_a_word():
    assert _clip("the default, in turn, raises the saving rate by a 4.2-percentage-point margin", 50) == \
        "the default, in turn, raises the saving rate by a…"


def test_section_names_are_shortened_without_losing_the_number(latex_map):
    loc = Locator(latex_map[0])
    assert loc.section_short("1. Introduction") == "1 Introduction"
    assert loc.section_short("5.2 Heterogeneous effects by age, income and tenure") == "Section 5.2"
    assert loc.section_short("A Model of Present Bias") == "A Model of Present Bias"
    assert loc.section_short("Appendix B: Survey instrument and variable definitions") == "Appendix B"


def test_a_short_place_keeps_the_latex_file_and_line(latex_map):
    pm = latex_map[0]
    loc = Locator(pm)
    block = next(b for b in pm.blocks if b.kind == "paragraph" and b.anchor.file and b.section)
    f = Finding(check_id="LOG-03", title="t", severity="minor", problem="p",
                locations=[{"block": block.id}, {"block": pm.blocks[0].id}])
    f = Finding.from_dict(f.to_dict())
    short = loc.short_where(f)
    assert block.anchor.file in short and short.endswith("and 1 more place")


def test_merged_fixes_show_one_wording_per_passage():
    main_fix = Fix(action="replace", original="so on balance the default acts as a commitment device",
                   replacement="so the two effects largely offset each other")
    f = Finding(check_id="NUM-08", title="t", severity="major", problem="p", fix=main_fix)
    f.extra["also"] = [
        {"check_id": "COH-04", "fix": 'replace "so on balance the default acts as a commitment device" with "x".',
         "fix_parts": {"action": "replace", "original": "so on balance the default acts as a commitment device",
                       "replacement": "x"}},
        {"check_id": "LOG-05", "fix": "Report the total effect.",
         "fix_parts": {"action": "insert", "detail": "Report the total effect."}},
    ]
    lines = _fix_lines(f, compact=True)
    assert "Also fix (LOG-05): Report the total effect." in lines
    assert not any("COH-04" in line for line in lines)
    assert lines[-1] == "And 1 other wording proposed for the same passage, in paper-check-evidence.md."
    # The evidence file keeps every proposal.
    assert any("COH-04" in line for line in _fix_lines(f))
