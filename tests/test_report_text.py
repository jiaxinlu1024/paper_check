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


def _word_map(abstract_parts):
    """A small Word paper map: a structured abstract, then one numbered section."""
    from paper_check.model import PaperMap
    blocks = [{"id": f"b{i:04d}", "kind": "abstract", "text": t, "anchor": {"paragraph": i}}
              for i, t in enumerate(abstract_parts, 1)]
    n = len(blocks) + 1
    blocks.append({"id": f"b{n:04d}", "kind": "paragraph", "text": "We ran the field experiment in 2024.",
                   "anchor": {"paragraph": n}, "section": ["3.1 Design and sample"]})
    return PaperMap.from_dict({"source": {"format": "docx"}, "blocks": blocks})


def test_a_place_in_a_structured_abstract_names_its_part():
    pm = _word_map(["Purpose – This study asks whether defaults raise saving.",
                    "Design/methodology/approach – We randomize the default at 12 firms.",
                    "Findings– Saving rises by four points.", "Keywords Defaults; Saving"])
    loc = Locator(pm)
    assert loc.short_label("b0003") == "Abstract, Findings"
    assert loc.short_label("b0002") == "Abstract, Design/methodology/approach"
    assert loc.short_label("b0004") == "Abstract, Keywords"
    # A Word paragraph count is not shown in the short form, and a short section title keeps its number.
    assert loc.short_label("b0005") == "3.1 Design and sample, paragraph 1"
    plain = Locator(_word_map(["We study defaults.", "We find that saving rises."]))
    assert plain.short_label("b0002") == "Abstract, paragraph 2"


def test_cells_show_the_sentence_after_a_setup_and_say_when_steps_follow():
    assert _lead("Partly supported (S7). The source supports only the first clause.", 60) == \
        "Partly supported (S7). The source supports only the first clause."
    assert _lead("The abstract says saving rises for everyone. Table 3 shows it rises only for new hires. "
                 "Later text.", 60) == ("The abstract says saving rises for everyone. Table 3 shows it rises only "
                                        "for new hires.")
    fx = Fix(action="investigate", detail="Stack the data by firm. (1) Re-estimate with firm fixed effects. "
                                          "(2) Cluster by firm. Equation (3) stays.")
    assert _fix_short(fx, 300) == "Stack the data by firm. Steps (1) to (2) are in the entry."


def test_a_long_first_sentence_stops_before_its_example_with_a_note():
    text = ("In Word, right-click the figure, choose View Alt Text and add a short description, for example: "
            "'Bar chart. " + "Bars show the saving rate in each arm and the gap between them; " * 12 + "'")
    assert _lead(text, 100) == ("In Word, right-click the figure, choose View Alt Text and add a short description "
                                "(the entry gives an example).")


def test_internal_labels_read_as_places_and_plain_words():
    from paper_check.report import _display
    pm = _word_map(["We study defaults.", "We find that saving rises."])
    loc = Locator(pm)
    text = ("Delete the sentence (b0003). Partly supported (S7): the source covers one clause. "
            "[UNVERIFIED] It is usually cited as Madrian and Shea (2001). Unknown id b9999 stays.")
    assert _display(text, loc) == ("Delete the sentence (3.1 Design and sample, paragraph 1). Partly supported: "
                                   "the source covers one clause. *Not verified:* It is usually cited as Madrian "
                                   "and Shea (2001). Unknown id b9999 stays.")


def test_two_findings_that_reword_the_same_words_name_each_other():
    from paper_check.report import _mark_same_words
    words = "the default raises saving for every employee in the sample"
    a = Finding(check_id="LOG-02", title="a", severity="major", problem="p", id="F-001",
                fix=Fix(action="replace", original=words, replacement="x"))
    b = Finding(check_id="COH-02", title="b", severity="minor", problem="p", id="F-002",
                fix=Fix(action="replace", original=words + ".", replacement="y"))
    c = Finding(check_id="NUM-01", title="c", severity="minor", problem="p", id="F-003",
                fix=Fix(action="replace", original="a different sentence about attrition rates", replacement="z"))
    _mark_same_words([a, b, c])
    assert a.extra["same_words"] == [["F-002", "minor"]] and b.extra["same_words"] == [["F-001", "major"]]
    assert "same_words" not in c.extra
    assert _fix_lines(a, compact=True)[-1].startswith("Same words as [F-002](paper-check-evidence.md#f-002)")
    assert _fix_lines(a)[-1].startswith("Same words as [F-002](#f-002)")
