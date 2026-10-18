"""Pipeline commands: saved settings, validate, verify, merge-runs, skip and the report."""

import json
from pathlib import Path

from paper_check.cli import main
from paper_check.config import PaperSettings
from paper_check.model import FindingSet

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CAUSAL = "This correlation shows that defaults cause higher saving among present-biased employees."
SESSIONS = "We ran 12 survey sessions between March and May 2025."


def _write(work, name, data, folder="findings"):
    path = work / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _finding(**kw):
    base = {"check_id": "LOG-03", "title": "Causal claim", "severity": "major", "status": "likely",
            "problem": "Causal language from correlational evidence.", "quote": CAUSAL}
    base.update(kw)
    return base


def test_ingest_saves_settings(tmp_path):
    assert main(["ingest", str(FIXTURES / "latex_basic"), "--out", str(tmp_path), "--venue", "aer",
                 "--mode", "standard", "--language", "US"]) == 0
    work = tmp_path / "paper-check-work"
    saved = json.loads((work / "settings.json").read_text())
    assert saved["venue"] == "aer" and saved["mode"] == "standard" and saved["language_variant"] == "US"
    s = PaperSettings.for_work(work)
    assert s.venue == "aer" and s.network is True
    assert PaperSettings.for_work(work, {"venue": "qje"}).venue == "qje"


def test_validate_repairs_slips_and_reports_errors(work_copy, capsys):
    _write(work_copy, "agent_logic.json", {"findings": [
        _finding(check_id="log-03", severity="Major", status="Needs human", locations=["b0026"],
                 evidence=["a plain note"], fix="rewrite the sentence"),
    ]})
    assert main(["validate", str(work_copy)]) == 0
    _write(work_copy, "agent_bad.json", {"findings": [_finding(check_id="LOG-99", severity="huge")]})
    assert main(["validate", str(work_copy)]) == 1
    out = capsys.readouterr().out
    assert "unknown check_id 'LOG-99'" in out and "severity 'huge'" in out


def test_verify_drops_invented_quotes_and_fills_locations(work_copy):
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(locations=[{"block": "b0026"}]),
        _finding(check_id="LOG-02", title="Invented", quote="This sentence is not in the paper."),
        _finding(check_id="LOG-04", title="Wrong block", quote=SESSIONS, locations=[{"block": "b0026"}]),
    ]})
    main(["verify", str(work_copy)])
    fs = FindingSet.load(work_copy / "findings" / "agent_logic.json")
    kept, invented, moved = fs.findings
    assert kept.status == "likely" and kept.locations[0].anchor.file == "sections/results.tex"
    assert invented.status == "dropped" and "not found in the paper" in invented.verification["dropped_reason"]
    assert moved.status == "likely" and moved.locations[0].anchor.file == "sections/design.tex"


def test_merge_runs_marks_single_run_findings_likely(work_copy):
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(status="confirmed"),
        _finding(check_id="LOG-05", title="Only in run one", quote="The experiment was preregistered.",
                 status="confirmed"),
    ], "coverage": [{"check_id": "LOG-03", "status": "run"}]})
    _write(work_copy, "agent_logic_run2.json", {"producer": "agent_logic", "findings": [
        _finding(check_id="LOG-02", quote="defaults cause higher saving among present-biased employees"),
        _finding(check_id="LOG-04", title="Only in run two", quote=SESSIONS),
    ], "coverage": [{"check_id": "LOG-04", "status": "run"}]}, folder="runs")
    assert main(["merge-runs", str(work_copy), "--dimension", "logic"]) == 0
    fs = FindingSet.load(work_copy / "findings" / "agent_logic.json")
    by_title = {f.title: f for f in fs.findings}
    assert by_title["Causal claim"].verification["runs"] == "2 of 2 runs"
    assert by_title["Causal claim"].status == "confirmed"
    assert by_title["Only in run one"].verification["runs"] == "1 of 2 runs"
    assert by_title["Only in run one"].status == "likely"
    assert by_title["Only in run two"].status == "likely"
    assert {c.check_id for c in fs.coverage} == {"LOG-03", "LOG-04"}
    assert (work_copy / "runs" / "agent_logic_run2.json.merged").exists()


def test_skip_records_reasons_and_uncovered(work_copy):
    assert main(["skip", str(work_copy), "--checks", "FIG,REV-04", "--reason", "no images"]) == 0
    fs = FindingSet.load(work_copy / "findings" / "orchestrator.json")
    assert {c.check_id for c in fs.coverage} >= {"FIG-01", "FIG-06", "REV-04"}
    assert main(["skip", str(work_copy), "--uncovered", "--reason", "not run in quick mode"]) == 0
    fs = FindingSet.load(work_copy / "findings" / "orchestrator.json")
    import yaml
    checks = yaml.safe_load((Path(__file__).resolve().parents[1] / ".claude/skills/paper-check/references/checks.yaml").read_text())
    assert len(fs.coverage) == len(checks["checks"])


def test_report_layout_order_coverage_and_appendices(work_copy):
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(),
        _finding(check_id="LOG-04", title="Session counts disagree", severity="critical", quote=SESSIONS,
                 related_quotes=[{"quote": "We ran 10 survey sessions in total."}]),
        _finding(check_id="COH-02", title="Abstract number", severity="minor",
                 quote="reduces the share of employees who save nothing by 23%"),
        _finding(check_id="LOG-02", title="Refuted one", quote=CAUSAL,
                 verification={"refuter": "refuted", "refuter_note": "Section 2 randomizes the default."}),
        _finding(check_id="LANG-08", title="Wordy", severity="suggestion", quote="The rest of the paper is organized as follows."),
    ], "coverage": [{"check_id": "LOG-03", "status": "run"}, {"check_id": "LOG-04", "status": "run"},
                    {"check_id": "LOG-02", "status": "skipped", "reason": "agent ran out of time"}]})
    _write(work_copy, "scripts_extra.json", {"producer": "scripts_extra", "findings": [],
                                             "coverage": [{"check_id": "LOG-02", "status": "run"}]})
    _write(work_copy, "verdicts_1.json", [{"id": "c002", "section": "1 Introduction", "claim": "gym attendance",
                                           "ref": "r005", "verdict": "not supported: topic absent"}], folder="citations")
    _write(work_copy, "verdicts_2.json", [{"id": "c001", "section": "1 Introduction", "claim": "participation",
                                           "ref": "r005", "verdict": "supported"}], folder="citations")
    main(["verify", str(work_copy)])
    assert main(["report", str(work_copy), "--min-severity", "minor"]) == 0
    md = (work_copy.parent / "paper-check-report.md").read_text()
    data = json.loads((work_copy.parent / "paper-check-findings.json").read_text())

    # Severity order, then paper order; headings at the right levels.
    assert (md.index("## What to fix first") < md.index("## Summary") < md.index("## Critical findings (1)")
            < md.index("## Major findings (1)") < md.index("## Minor findings and suggestions (1 Minor, 0 Suggestion)"))
    assert md.index("## Evidence") < md.index("## About this check")
    assert "### F-001 · Critical · LOG-04 · Session counts disagree" in md
    assert "Where: 2 Experimental design, paragraph 2, sentence 2 (sections/design.tex:4-5)" in md
    # A Minor finding is a row of the Minor table in the report and a full entry in the evidence file.
    minor_table = md.split("## Minor findings and suggestions (1 Minor, 0 Suggestion)")[1].split("\n## ")[0]
    assert "Abstract, sentence 2 (main.tex:12-13)" in minor_table
    assert "Where: Abstract, sentence 2 (main.tex:12-13)" in (work_copy.parent / "paper-check-evidence.md").read_text()
    ev = (work_copy.parent / "paper-check-evidence.md").read_text()
    assert 'Related, A Additional details, paragraph 1 (sections/appendix.tex:1-3): "We ran 10 survey sessions in total."' in ev
    # The refuted finding moves to its appendix in the evidence file; the suggestion is below the minimum severity.
    assert "## Appendix: refuted findings" in ev and "Section 2 randomizes the default." in ev
    assert "## Appendix" not in md and "Proof and steps: [F-001](paper-check-evidence.md#f-001)" in md
    assert "Wordy" not in md and "1 finding below the minimum severity (minor) is left out" in md
    # Coverage: run by one producer and skipped by another reads "partly run".
    cov = {r["check_id"]: r for r in data["coverage"]}
    assert cov["LOG-02"]["status"] == "partly run" and "agent ran out of time" in cov["LOG-02"]["detail"]
    # Coverage notes are written before the refuters run, so the row says how many were overturned.
    assert "1 later refuted" in cov["LOG-02"]["detail"]
    assert cov["LOG-03"]["status"] == "run" and cov["FIG-01"]["status"] == "not run"
    # Verdict files are merged, and the JSON carries ids, dimensions and labels.
    assert [v["id"] for v in data["appendices"]["citation_support"]] == ["c001", "c002"]
    assert [f["id"] for f in data["findings"]] == ["F-001", "F-002", "F-003"]
    assert data["findings"][0]["dimension"] == "LOG" and data["findings"][0]["where"].startswith("2 Experimental design")


ABSTRACT_23 = "reduces the share of employees who save nothing by 23%"


def test_refutation_without_real_counter_evidence_is_set_aside(work_copy):
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(severity="minor", verification={
            "refuter": "downgraded",
            "refuter_note": 'Downgraded from major to minor: "this association need not be causal" (b0040).'},
            evidence=[{"type": "quote", "text": "this association need not be causal",
                       "data": {"role": "counter-evidence"}}]),
        _finding(check_id="LOG-04", title="Sessions", quote=SESSIONS, verification={
            "refuter": "refuted", "refuter_note": "The appendix counts pilot sessions separately."},
            evidence=[{"type": "quote", "text": "We ran 10 survey sessions in total.",
                       "data": {"role": "counter-evidence"}}]),
    ]})
    main(["verify", str(work_copy)])
    fs = FindingSet.load(work_copy / "findings" / "agent_logic.json")
    voided, refuted = fs.findings
    assert voided.status != "dropped" and voided.severity == "major"
    assert voided.verification["refuter"] == "not refuted" and voided.verification["refutation_voided"]
    assert not [e for e in voided.evidence if (e.data or {}).get("role") == "counter-evidence"]
    assert refuted.verification["refuter"] == "refuted" and refuted.status != "dropped"
    main(["report", str(work_copy)])
    md = (work_copy.parent / "paper-check-report.md").read_text()
    ev = (work_copy.parent / "paper-check-evidence.md").read_text()
    assert "## Appendix: refuted findings" in ev and "pilot sessions separately" in ev
    assert "### F-001 · Major · LOG-03" in md and "### F-001 · Major · LOG-03" in ev


def test_related_findings_on_one_passage_are_merged(work_copy):
    _write(work_copy, "scripts_num.json", {"producer": "scripts", "findings": [
        _finding(check_id="NUM-01", title="Abstract and Table 1 disagree", severity="major", status="confirmed",
                 quote=ABSTRACT_23, problem="Table 1 implies 18.2%, not 23%.",
                 evidence=[{"type": "computed_result", "data": {"formula": "(9.9 - 8.1) / 9.9", "output": "18.2%"}}]),
    ]})
    _write(work_copy, "agent_coherence.json", {"producer": "agent_coherence", "findings": [
        _finding(check_id="COH-02", title="Abstract number not in the body", severity="major", status="likely",
                 quote="by 23% relative to the control group", problem="The body never reports 23%.",
                 fix={"action": "investigate", "detail": "Report the 23% in the results, or drop it.",
                      "resolved_when": "The body supports the abstract's number."}),
        _finding(check_id="LANG-04", title="Vague wording", severity="minor", quote=ABSTRACT_23,
                 problem="A different problem on the same words."),
    ]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    data = json.loads((work_copy.parent / "paper-check-findings.json").read_text())
    by_check = {f["check_id"]: f for f in data["findings"]}
    assert set(by_check) == {"NUM-01", "LANG-04"}
    merged = by_check["NUM-01"]
    assert merged["status"] == "confirmed" and merged["extra"]["also"][0]["check_id"] == "COH-02"
    lang = by_check["LANG-04"]
    assert not any(t.startswith("Status raised") for t in lang.get("trajectory", []))
    md = (work_copy.parent / "paper-check-report.md").read_text()
    assert "(Numbers inside the paper), also COH-02" in md
    ev = (work_copy.parent / "paper-check-evidence.md").read_text()
    assert "Also reported by agent_coherence under COH-02" in ev
    # The merged finding keeps the absorbed finding's own fix, in the report and in the evidence file.
    assert "Also fix (COH-02): Report the 23% in the results, or drop it." in md
    assert "Also fix (COH-02): Report the 23% in the results, or drop it." in ev
    cov = {r["check_id"]: r for r in data["coverage"]}
    assert cov["COH-02"]["detail"].startswith("1 finding;")


def test_merge_runs_pairs_single_findings_of_one_check(work_copy):
    _write(work_copy, "agent_behavioral.json", {"producer": "agent_behavioral", "findings": [
        _finding(check_id="BEH-03", title="Materials missing", quote="The experiment was preregistered.", status="confirmed"),
    ]})
    _write(work_copy, "agent_behavioral_run2.json", {"producer": "agent_behavioral", "findings": [
        _finding(check_id="BEH-03", title="Instructions not provided", quote=SESSIONS),
    ]}, folder="runs")
    main(["merge-runs", str(work_copy), "--dimension", "behavioral"])
    fs = FindingSet.load(work_copy / "findings" / "agent_behavioral.json")
    assert len(fs.findings) == 1
    assert fs.findings[0].verification["runs"] == "2 of 2 runs" and fs.findings[0].status == "confirmed"


def test_recurring_minor_findings_are_grouped_but_major_ones_are_not(work_copy):
    quotes = ["The experiment was preregistered.", SESSIONS, "We ran 10 survey sessions in total.",
              "Table 1 reports the main estimates.", "Figure 1 shows the distribution of contribution rates."]
    _write(work_copy, "agent_language.json", {"producer": "agent_language", "findings":
        [_finding(check_id="LANG-02", title="Overlong sentence", severity="minor", quote=q, problem="Too long.") for q in quotes]
        + [_finding(check_id="LOG-04", title="Contradiction", severity="major", quote=q, problem="Conflict.") for q in quotes[:2]]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    data = json.loads((work_copy.parent / "paper-check-findings.json").read_text())
    lang = [f for f in data["findings"] if f["check_id"] == "LANG-02"]
    assert len(lang) == 1 and lang[0]["extra"]["instances"] == 5 and len(lang[0]["related_quotes"]) == 4
    assert "and 2 more places" in lang[0]["where"]
    assert len([f for f in data["findings"] if f["check_id"] == "LOG-04"]) == 2


def test_merged_runs_keep_the_second_runs_disputes():
    from paper_check.runs import merge_disputes

    first = {"disputed_script_findings": [{"check_id": "NUM-05", "block": "b0010", "quote": "94 vs 24", "reason": "a"}]}
    second = {"disputed_script_findings": [{"check_id": "NUM-05", "block": "b0010", "quote": "94 vs 24", "reason": "b"},
                                           {"check_id": "BEH-09", "block": "b0148", "quote": "Note: Table 1",
                                            "reason": "a table of means"}]}
    assert merge_disputes(first, second) == 1
    assert [d["check_id"] for d in first["disputed_script_findings"]] == ["NUM-05", "BEH-09"]
    assert first["disputed_script_findings"][1]["from_run"] == 2
    empty = {}
    assert merge_disputes(empty, {}) == 0 and "disputed_script_findings" not in empty


def test_consolidation_groups_one_root_cause_from_several_dimensions(work_copy):
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(check_id="LOG-03", title="Causal claim", severity="major", problem="Causal wording from a correlation."),
    ]})
    _write(work_copy, "agent_reviewer.json", {"producer": "agent_reviewer", "findings": [
        _finding(check_id="REV-06", title="No design for causal claims", severity="minor", status="likely",
                 quote=SESSIONS, problem="Survey sessions cannot support the causal claim."),
        _finding(check_id="REV-05", title="Other problem", severity="minor", quote=SESSIONS,
                 problem="Something else entirely."),
    ]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    first = json.loads((work_copy.parent / "paper-check-findings.json").read_text())["findings"]
    keys = {f["check_id"]: f["key"] for f in first}
    assert len(first) == 3 and all(keys.values())
    (work_copy / "consolidation.json").write_text(json.dumps({"groups": [
        {"keys": [keys["REV-06"], keys["LOG-03"]], "keep": keys["REV-06"], "reason": "one causal overclaim"},
        {"keys": ["NUM-01-00000000", keys["REV-05"]], "reason": "a key that does not exist"},
    ]}))
    main(["report", str(work_copy)])
    data = json.loads((work_copy.parent / "paper-check-findings.json").read_text())
    by_check = {f["check_id"]: f for f in data["findings"]}
    assert set(by_check) == {"LOG-03", "REV-05"}            # the Major keeps the group, whatever "keep" says
    merged = by_check["LOG-03"]
    assert merged["extra"]["also"][0]["check_id"] == "REV-06"
    assert any(q.get("quote") == SESSIONS for q in merged["related_quotes"])
    assert any("NUM-01-00000000" in w for w in data["warnings"])
    # the keys stay stable across builds
    assert merged["key"] == keys["LOG-03"]


def test_findings_that_share_a_quote_get_distinct_keys(work_copy):
    """Two findings of one producer and check on one quote (a reference's wrong year and its missing
    DOI) must not share a key, or a consolidation group meant for one lands on the other."""
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(check_id="LOG-03", title="Causal claim", problem="Causal wording from a correlation."),
        _finding(check_id="LOG-03", title="Causal claim in the conclusion", problem="Repeated in the conclusion."),
        _finding(check_id="LOG-01", title="Other", quote=SESSIONS, problem="A different passage."),
    ]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    first = json.loads((work_copy.parent / "paper-check-findings.json").read_text())["findings"]
    keys = [f["key"] for f in first]
    assert len(keys) == len(set(keys)) == 3
    main(["report", str(work_copy)])
    again = json.loads((work_copy.parent / "paper-check-findings.json").read_text())["findings"]
    assert sorted(f["key"] for f in again) == sorted(keys)     # stable across builds


def test_top_issues_follow_the_consolidators_choice_then_the_ranking(work_copy):
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(check_id="LOG-03", title="Causal claim", severity="major", status="likely",
                 problem="Causal wording from a correlation."),
        _finding(check_id="LOG-01", title="Confirmed but minor point", severity="major", status="confirmed",
                 quote=SESSIONS, problem="A smaller problem."),
    ]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    report = (work_copy.parent / "paper-check-report.md").read_text()
    first = report.split("## What to fix first")[1].split("\n## ")[0]
    assert first.index("Confirmed but minor point") < first.index("Causal claim")   # confirmed before likely
    keys = {f["check_id"]: f["key"] for f in
            json.loads((work_copy.parent / "paper-check-findings.json").read_text())["findings"]}
    (work_copy / "consolidation.json").write_text(json.dumps({"groups": [], "top": [keys["LOG-03"], "LOG-09-deadbeef"]}))
    main(["report", str(work_copy)])
    report = (work_copy.parent / "paper-check-report.md").read_text()
    chosen = report.split("## What to fix first")[1].split("\n## ")[0]
    items = [line for line in chosen.splitlines() if line[:2] in ("1.", "2.")]
    # The chosen top issue comes first, with its fix; the other Major finding follows by title.
    assert "most threaten" in chosen and "Causal claim" in items[0] and "**Fix:**" in items[0]
    assert "Confirmed but minor point" in items[1] and "Fix:" not in items[1]
    assert chosen.index("Other Major findings") < chosen.index("Confirmed but minor point")
    about = report.split("## About this check")[1]
    assert "LOG-09-deadbeef" in about                                # an unknown key is a note for the runner,
    assert "LOG-09-deadbeef" not in report.split("## Summary")[0]   # not a warning on the author's first page


def test_index_follows_sentence_order_and_places_anchor_only_findings(work_copy):
    """Within one paragraph the index follows the quotes' order, not severity; a finding with only an
    anchor (a file comment, an annotation) sits after the block it follows, not at the end."""
    from paper_check.model import PaperMap
    pm = PaperMap.load(work_copy / "paper_map.json")
    paras = [b for b in pm.blocks if b.kind == "paragraph"]
    block = next(b for b in paras if len(b.sentences) >= 2 and b.anchor.file and b.anchor.line)
    later = next(b for b in paras[paras.index(block) + 1:] if b.anchor.file == block.anchor.file)
    first = block.text[block.sentences[0].start:block.sentences[0].end].strip()
    second = block.text[block.sentences[1].start:block.sentences[1].end].strip()
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(check_id="LOG-03", title="Second sentence", severity="major", quote=second,
                 locations=[{"block": block.id}], problem="About the second sentence."),
        _finding(check_id="LOG-01", title="First sentence", severity="minor", quote=first,
                 locations=[{"block": block.id}], problem="About the first sentence."),
        _finding(check_id="LOG-05", title="Later paragraph", severity="minor", quote=later.text[:60].strip(),
                 locations=[{"block": later.id}], problem="About a later paragraph."),
    ]})
    _write(work_copy, "agent_format.json", {"producer": "agent_format", "findings": [
        {"check_id": "FMT-11", "title": "Comment left in the file", "severity": "minor", "status": "confirmed",
         "problem": "A comment is left in the source.", "quote": "",
         "locations": [{"anchor": {"file": block.anchor.file, "line": block.anchor.line}}]},
    ]})
    main(["report", str(work_copy)])
    report = (work_copy.parent / "paper-check-report.md").read_text()
    index = report.split("## Index in paper order")[1].split("## Coverage")[0]
    titles = [r.split("|")[4].strip() for r in index.splitlines() if r.startswith("| [F-")]
    order = [titles.index(t) for t in ("First sentence", "Second sentence", "Comment left in the file",
                                       "Later paragraph")]
    assert order == sorted(order), titles


def test_a_sequential_run_is_labelled_and_never_merges_runs(tmp_path, capsys):
    """One agent doing every step cannot produce independent second runs: merge-runs refuses, and the
    report's header says how the run was done."""
    assert main(["ingest", str(FIXTURES / "latex_basic"), "--out", str(tmp_path), "--sequential"]) == 0
    work = tmp_path / "paper-check-work"
    assert PaperSettings.for_work(work).sequential is True
    _write(work, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(),
        _finding(check_id="LOG-04", title="Sessions", quote=SESSIONS, verification={
            "refuter": "refuted", "refuter_note": "The appendix counts pilot sessions separately."},
            evidence=[{"type": "quote", "text": "We ran 10 survey sessions in total.",
                       "data": {"role": "counter-evidence"}}])]})
    _write(work, "agent_logic_run2.json", {"producer": "agent_logic", "findings": [_finding()]}, folder="runs")
    capsys.readouterr()
    assert main(["merge-runs", str(work), "--dimension", "logic"]) == 2
    assert "sequential" in capsys.readouterr().out
    main(["verify", str(work)])
    main(["report", str(work)])
    report = (tmp_path / "paper-check-report.md").read_text()
    assert "**Run:** sequential" in report.split("## Summary")[0]
    evidence = (tmp_path / "paper-check-evidence.md").read_text()
    appendix = evidence.split("## Appendix: refuted findings")[1]
    assert "not independent" in appendix and "An independent refuter" not in appendix
    first = json.loads((work / "findings" / "agent_logic.json").read_text())["findings"][0]
    assert "runs" not in (first.get("verification") or {})


def test_quick_report_is_brief_and_coverage_lists_only_what_did_not_run(tmp_path):
    """A quick check's report keeps three proof lines and a one-line trajectory per finding, and the
    coverage table groups the checks left out for one shared reason."""
    assert main(["ingest", str(FIXTURES / "latex_basic"), "--out", str(tmp_path), "--mode", "quick"]) == 0
    work = tmp_path / "paper-check-work"
    evidence = [{"type": "quote", "text": t} for t in (
        "We ran 10 survey sessions in total.", "We ran 12 survey sessions between March and May 2025.",
        "Table 1 reports the main estimates.", "Figure 1 shows the distribution of contribution rates.",
        "The experiment was preregistered.")]
    _write(work, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(evidence=evidence, trajectory=["Read the design section.", "Compared the appendix."])],
        "coverage": [{"check_id": c, "status": "skipped", "reason": "not run in quick mode"}
                     for c in ("LOG-01", "LOG-05", "LOG-06", "LOG-07")]})
    main(["verify", str(work)])
    main(["report", str(work)])
    md = (tmp_path / "paper-check-report.md").read_text()
    finding = md.split("### F-001")[1].split("\n## ")[0]
    # The report keeps the quote, place, problem and fix; the proof and the steps are in the evidence file.
    assert "Proof:" not in finding and "Proof and steps: [F-001](paper-check-evidence.md#f-001)" in finding
    ev = (tmp_path / "paper-check-evidence.md").read_text()
    entry = ev.split("### F-001")[1].split("\n## ")[0]
    assert all(e["text"] in entry for e in evidence) and "Read the design section." in entry
    coverage = md.split("## Coverage")[1].split("\n## ")[0]
    assert "| LOG-01, LOG-05, LOG-06, LOG-07 | 4 checks | skipped |" in coverage
    # The page gives the count; the evidence file names the checks that ran in full.
    assert "checks ran in full (paper-check-evidence.md lists them)" in coverage
    assert "checks ran in full:" in ev.split("## Coverage, in full")[1]
    data = json.loads((tmp_path / "paper-check-findings.json").read_text())
    assert len(data["coverage"]) == 125 and len(data["findings"][0]["evidence"]) == 5


def test_the_report_opens_with_the_answer_to_the_users_question(work_copy):
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [_finding()]})
    (work_copy / "answer.md").write_text("No: the causal claim is not supported (F-001).\n", encoding="utf-8")
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    md = (work_copy.parent / "paper-check-report.md").read_text()
    assert md.index("## Short answer") < md.index("## Summary")
    assert "No: the causal claim is not supported (F-001)." in md.split("## Summary")[0]
    data = json.loads((work_copy.parent / "paper-check-findings.json").read_text())
    assert data["answer"].startswith("No: the causal claim")


def test_checks_against_unconfirmed_journal_rules_carry_a_caveat(tmp_path):
    """A check that ran against rules the venue profile could not confirm is not listed as run in full."""
    assert main(["ingest", str(FIXTURES / "latex_basic"), "--out", str(tmp_path), "--venue", "jebo",
                 "--offline"]) == 0
    work = tmp_path / "paper-check-work"
    assert main(["checks", str(work)]) == 0
    main(["verify", str(work)])
    main(["report", str(work)])
    data = json.loads((tmp_path / "paper-check-findings.json").read_text())
    cov = {r["check_id"]: r for r in data["coverage"]}
    # FMT-01 also ran only in part (no page count from LaTeX); its caveat names the unconfirmed rule.
    assert cov["FMT-01"]["status"] == "partly run" and "abstract_max_words" in (cov["FMT-01"]["caveat"] or "")
    caveated = [cid for cid, r in cov.items() if r["status"] == "run" and r.get("caveat")]
    assert caveated and all("unconfirmed JEBO rule" in cov[c]["caveat"] for c in caveated)
    md = (tmp_path / "paper-check-report.md").read_text()
    coverage = md.split("## Coverage")[1].split("\n## ")[0]
    evidence = (tmp_path / "paper-check-evidence.md").read_text()
    ran_in_full = evidence.split("## Coverage, in full")[1].split("checks ran in full:")[1].split(".")[0]
    assert not any(c in ran_in_full for c in caveated + ["FMT-01"]) and "run, with a caveat" in coverage
    assert "against unconfirmed journal rules" in md.split("## Summary")[1].split("\n## ")[0]


def test_a_status_raised_by_merging_is_explained_in_the_trajectory(work_copy):
    """When a group's lead finding is likely and another member is confirmed on the same point, the lead
    becomes confirmed, and its trajectory says why, so the status and the steps agree."""
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(check_id="LOG-03", title="Causal claim", severity="major", status="likely",
                 trajectory=["Compared the claim with the design; the status is likely rather than confirmed."])]})
    _write(work_copy, "agent_numbers.json", {"producer": "agent_numbers", "findings": [
        _finding(check_id="LOG-04", title="Session counts disagree", severity="major", status="confirmed",
                 quote=SESSIONS, problem="Twelve sessions here, ten in the appendix.")]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    first = json.loads((work_copy.parent / "paper-check-findings.json").read_text())["findings"]
    keys = {f["check_id"]: f["key"] for f in first}
    (work_copy / "consolidation.json").write_text(json.dumps({"groups": [
        {"keys": [keys["LOG-03"], keys["LOG-04"]], "keep": keys["LOG-03"], "reason": "one design problem"}]}))
    main(["report", str(work_copy)])
    data = json.loads((work_copy.parent / "paper-check-findings.json").read_text())
    lead = next(f for f in data["findings"] if f["check_id"] == "LOG-03")
    assert lead["status"] == "confirmed"
    assert any(t.startswith("Status raised from likely to confirmed: LOG-04") for t in lead["trajectory"])


def test_finding_ids_stay_the_same_when_the_report_is_built_again(work_copy):
    """IDs quoted from one build (in a conversation or a coauthor's notes) keep pointing at the same finding;
    a finding added later gets the next free number instead of shifting the others."""
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [
        _finding(check_id="LOG-03", title="Causal claim", severity="major"),
        _finding(check_id="LOG-04", title="Session counts disagree", severity="minor", quote=SESSIONS)]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    first = {f["title"]: f["id"] for f in json.loads((work_copy.parent / "paper-check-findings.json").read_text())["findings"]}
    _write(work_copy, "agent_numbers.json", {"producer": "agent_numbers", "findings": [
        _finding(check_id="NUM-01", title="Headline number", severity="critical",
                 quote="reduces the share of employees who save nothing by 23%")]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    second = {f["title"]: f["id"] for f in json.loads((work_copy.parent / "paper-check-findings.json").read_text())["findings"]}
    assert second["Causal claim"] == first["Causal claim"] and second["Session counts disagree"] == first["Session counts disagree"]
    assert second["Headline number"] == "F-003"


def test_page_one_never_ranks_a_minor_finding_as_a_top_issue(work_copy):
    """Without the consolidator's choice, page one lists only Critical and Major findings; with none, it
    says so instead of promoting a Minor one."""
    _write(work_copy, "agent_language.json", {"producer": "agent_language", "findings": [
        _finding(check_id="LANG-02", title="Overlong sentence", severity="minor", status="confirmed",
                 problem="This sentence has 61 words.")]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    report = (work_copy.parent / "paper-check-report.md").read_text()
    first = report.split("## What to fix first")[1].split("\n## ")[0]
    assert "No Critical or Major findings" in first and "Overlong sentence" not in first
    _write(work_copy, "agent_logic.json", {"producer": "agent_logic", "findings": [_finding()]})
    main(["verify", str(work_copy)])
    main(["report", str(work_copy)])
    report = (work_copy.parent / "paper-check-report.md").read_text()
    first = report.split("## What to fix first")[1].split("\n## ")[0]
    assert "Causal claim" in first and "Overlong sentence" not in first
