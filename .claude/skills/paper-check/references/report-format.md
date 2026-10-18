# Report format

This file restates section 11 of `docs/DESIGN.md` (v0.4) for the agents and people who produce or read the report, and says which files feed each part. `pc.py report WORK` builds the report; nothing else should write it.

The report is written for two readers: a writer fixing the draft, and a fixing agent working through it. Every finding therefore quotes the paper, says exactly where, shows the proof, lists the steps that led to it, and suggests a fix with a test for when it is resolved. The writer gets a short report that leads with what to fix first, keeps each finding's quote, place, problem and fix, and stays within about one and a half times the draft's length; the proof and the steps go to a companion evidence file under the same IDs. It describes mismatches and the evidence for them, and never speculates about who wrote a passage or whether AI was used: a citation mismatch is a verifiable fact, while guesses about authorship are not, and a report written this way can be forwarded to a coauthor as it stands.

## Files

Written beside the work folder, next to the paper unless an output folder was given:

| File | For | Contents |
|---|---|---|
| `paper-check-report.md` | People | The report described below: what to fix first, every finding's quote, place, problem and fix |
| `paper-check-evidence.md` | People checking a finding | Every finding in full, with its proof, the steps that led to it and the test for when it is resolved, under the same IDs; the coverage table in full; and the appendices |
| `paper-check-findings.json` | Agents | The same findings with the same IDs, the refuted and dropped findings, the coverage rows, the settings, and the appendices as data, including the reference evidence cards |
| `paper-check-work/` | The proof trail | The paper map, findings files, source texts and digests, scan records, lookup cache and image crops |

## What feeds the report

| Input in the work folder | Written by | Used for |
|---|---|---|
| `paper_map.json`, `settings.json` | `pc.py ingest` | Locations, paper order, header, mode and venue |
| `findings/*.json` | Every producer: `scripts.json`, `refs.json`, `agent_<dimension>.json`, `agent_citations_<n>.json`, `agent_refweb_<n>.json`, `orchestrator.json` | Findings and coverage |
| `references/cards.json` | `pc.py refs` | Appendix of reference evidence cards |
| `references/web_checks_*.json` | The reference web-check agents | Web-check outcome for references no database matched |
| `citations/verdicts*.json` | The citation judges, and the refuter for overturned verdicts | Citation support appendix and per-section summary |
| `agents/claim_map.json` | The logic agent | Claim-evidence map appendix |

Each findings file is one FindingSet: `{"producer", "settings", "findings": [...], "coverage": [...]}`. `pc.py validate` checks a file's format; `pc.py verify` checks every quote and drops findings whose quotes cannot be found.

## Report sections

1. **Header.** The paper's title and one line: when it was checked, the skill version, the mode and the journal profile. A sequential run says so here. Warnings follow: unreadable findings files, network off, ingestion problems, findings below the minimum severity.
2. **Short answer.** When the user asked a specific question, two to five sentences answering it, with the finding IDs behind each claim, written by the orchestrator to `WORK/answer.md`.
3. **What to fix first.** One page. A numbered list of the top issues, and any Critical finding, each with its title, the place in short form (for example "Section 3.2, paragraph 2, sentence 1, and 2 more places") and the fix: a replacement whole when it is short, otherwise the words to reword and a pointer to the new wording in the entry, or the fix's first sentence. Then the other Major findings, one line each: title and place. Every item links to its entry. Nothing is cut inside a sentence or a quotation.
4. **Summary.** Counts by severity, split into confirmed, likely and needs human judgment; how the Minor findings and suggestions are split between the two lists below; counts by dimension; and one line of coverage counts.
5. **Findings.** Critical and Major findings as full entries: quote, place, problem, fix, and a link to the proof in the evidence file. An entry shows at most two fixes from findings merged into it, one wording per passage, and counts the rest, which are in the evidence file. Minor findings and suggestions about substance as one table in paper order, and a second table of small fixes (wording, style, captions, reference format, file anonymization). Each table row links to its full entry in the evidence file and gives the place in short form, the quote cut at a word, the problem's first whole sentences and the fix in short form. An **index in paper order** follows, for writers fixing the draft from top to bottom.
6. **Coverage.** One line gives how many checks ran in full; the evidence file lists them. A table gives every other check its outcome, with the first note whole and a count of the others: partly run, not applicable, skipped with the reason, or not run when no producer covered it; checks left out for one shared reason, such as the mode, share a row. A skipped check was not passed. `paper-check-findings.json` has every check's outcome, with the number of findings and any note.
7. **Evidence.** A pointer to `paper-check-evidence.md`, which holds every finding in full and these appendices: the reference table with an evidence card per reference; the citation support table, one row per citation, with a per-section summary such as "Section 2: 14 of 31 citations not supported or contradicted"; the claim-evidence map; every recomputed number; refuted findings with the refuter's counter-evidence; dropped findings with the reason; and ingestion warnings.
8. **About this check.** The paper's path and format, the venue profile and the date its rules were checked (with a warning when the profile is more than 180 days old), the sources folder, the producers, and how to read the report.

IDs stay the same when the report is built again from the same work folder: `WORK/finding_ids.json` maps each finding's key to its ID, and a new finding gets the next free number. Personal names from a file's metadata appear as initials in the report and the evidence file; the findings file keeps the value for a fixing agent.

## One finding

```markdown
### F-012 · Major · NUM-01 · Effect size differs between abstract and table
Check: NUM-01 Numbers consistent across sections (Numbers inside the paper) · Status: confirmed · Confidence: high
Where: Abstract (main.tex:18); 3 Results, Table 3 (results.tex:102)

> "reduces default rates by 23% compared with the control group"

Problem: Table 3 reports a default rate of 8.1% under treatment and 9.9% in
the control group. That is an 18% reduction, not 23%.

Proof:
- Quote, 3 Results, Table 3 (results.tex:102): "Treatment | 8.1"
- Computed: (9.9 - 8.1) / 9.9, with control: 9.9; treatment: 8.1 = 0.182 (tolerance 0.005)

Trajectory:
1. The number scripts extracted 41 numeric claims; this one is tagged "default rate, relative".
2. Matched to Table 3 by outcome name and arm.
3. Recomputed the reduction: 18.2%.
4. Searched every table and the appendix for 23%: no match.
5. Refuter: not refuted. Tried other arms, tables and the appendix.
6. Found in 2 of 2 runs.
Verifier settings: model <model id>, prompt numbers.md 0.4.0, runs 2

Suggested fix: replace "23%" with "18%".
Resolved when: the abstract and Table 3 imply the same reduction.
```

That is the entry in `paper-check-evidence.md`. In the report, a Critical or Major finding keeps the heading, the check line, the place, the quote, the problem and the fix, drops the proof, the steps and the "Resolved when" test, shows at most two fixes of findings merged into it, and ends with "Proof and steps: F-012 in paper-check-evidence.md". Minor findings and suggestions are table rows in the report and full entries in the evidence file, where their trajectory sits on one line: "Trajectory: (1) ... (2) ...".

## Fields of a finding

| Field | Content |
|---|---|
| `id` | Assigned by the report: F-001, F-002, ... in severity and paper order |
| `check_id`, `dimension` | The checklist ID, such as NUM-01, from `references/checks.yaml`; the dimension is its prefix |
| `title` | A few words saying what is wrong, not only the topic: "Effect size differs between abstract and table", not "Effect size". Page one shows most Major findings by title alone |
| `severity` | critical, major, minor or suggestion, as defined in DESIGN section 5, and set by the consequence for the paper rather than the check's typical level |
| `status` | confirmed (the evidence settles it), likely (it probably holds), needs_human (the skill could not decide), or dropped (set by `pc.py verify` when a quote fails) |
| `confidence` | high, medium or low: evidence type, refutation and run agreement combined |
| `locations` | Block IDs; `pc.py verify` adds the anchor (file and line, page and line, or paragraph) and the section path |
| `quote`, `related_quotes` | Verbatim text from the paper, checked by script |
| `problem` | One or two sentences |
| `evidence` | Typed items: `quote` and `source_quote` (verbatim, checked by script); `computed_result` (formula, inputs, output, tolerance); `checked_absence` (scope searched, terms with hit counts, version read); `lookup_record` (database, query, record, URL); `script_output`; `image` (page, crop path, description); `note` |
| `trajectory` | The steps taken, in order |
| `fix` | `action` (replace, insert, delete or investigate), the exact `original` and `replacement` for a replace, `detail`, and `resolved_when`. Put the first step in the first sentence of `detail`: page one and the tables show that sentence alone |
| `producer` | Who produced it, with `settings`: model, prompt version, strictness, number of runs |
| `verification` | Written by the pipeline: `quotes` by `pc.py verify`; `runs` ("2 of 2 runs" or "1 of 2 runs") by `pc.py merge-runs`; `refuter` ("not refuted", "refuted" or "downgraded") and `refuter_note` by the refuter |
| `extra` | Producer-specific data, such as a citation finding's proposition, reference, verdict and failure code |

## Files written by agents for the appendices

- `agents/claim_map.json`: a list of `{"claim", "location", "evidence", "assessment"}`, with `assessment` one of supported, partly supported or unsupported.
- `citations/verdicts_<n>.json`: a list with one object per citation, `{"id", "section", "claim", "ref", "verdict", "failure_code", "version_read", "finding"}`. `verdict` is one of supported, partly supported, not supported: topic absent, not supported: misattributed, not supported: misdescribed, contradicted, or cannot verify; `failure_code` is S1 to S7 or null. See `citation-support.md`.
- `references/web_checks_<n>.json`: one row per reference that needed a web search, from `agents/reference-web-check.md`.

## Coverage entries

Each producer records, for every check it owns, `{"check_id", "status", "reason", "count"}` with status run, not_applicable or skipped. A check that could not run is skipped with the reason. A check that ran on only part of what it covers gets two entries: `run` for what was done, and `skipped` with the reason for the rest, such as "the replication README was not supplied"; the report shows it as partly run, never as run in full. A note on what a run covered may go in `reason`; the findings file keeps it. The note says what this check read or compared, not what another check concluded: producers write their coverage before the refuters run, so "already a CIT-06 verdict" can be wrong by the time the report is built. `pc.py skip` records checks left out on purpose, such as those a mode does not run.
