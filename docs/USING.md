# Using the paper-check skill

paper-check is a Claude Code skill. It checks a paper draft and writes a report in which every finding quotes the draft, gives its location, shows the proof and the steps taken, and suggests a fix. It never edits the paper.

## Set up once

1. **Get the repository.** Clone https://github.com/jiaxinlu1024/paper_check and open the folder in Claude Code desktop. The skill is in `.claude/skills/paper-check/`, so it is available in that project at once. To use it in every project, copy that folder to `~/.claude/skills/paper-check/`.
2. **Python.** The scripts need Python 3.9 or later. On the first run, Claude runs `pc.py doctor`. If packages are missing, it asks before running `pc.py setup`, which creates a private environment in `~/.paper-check/venv` and installs the packages in `requirements.txt` there. Nothing is installed system-wide.
3. **Contact email and keys.** Create `~/.paper-check/config.yaml` as described in [api-access.md](api-access.md). The contact email matters most. Without the keys the lookups still run, only more slowly.
4. **Network.** The lookups need internet access. On a Claude Code cloud environment, see [network-setup.md](network-setup.md). Run `python3 tools/check_network.py` to test it.

## Run a check

Ask in plain words, for example:

- "Check my paper in ~/Papers/defaults/ before we submit to the AER."
- "My coauthor sent draft.docx. Do the citations say what we claim?"
- "Quick check of paper.pdf: numbers and references only."

Useful things to mention, all optional:

| Setting | Example | Effect |
|---|---|---|
| Journal | "for JEBO" | Applies that journal's profile: limits, required statements, anonymization, experiment policies. `pc.py venues` lists the 21 profiles |
| Mode | "quick", "standard" or nothing | Deep is the default and checks everything. Quick runs only the scripts, reference lookups and abstract fidelity |
| PDFs of cited works | "the cited PDFs are in sources/" | The single best way to strengthen citation checks. By default the skill looks for `sources/` beside the paper; file names do not matter |
| Study type | "it's a lab experiment" | Switches on the matching experiment checks |
| English variant | "UK English" | Spelling consistency is checked against it |

You can also put these in a `paper-check.yaml` beside the paper:

```yaml
venue: jebo
mode: deep
study_type: lab experiment
language_variant: US
sources: sources        # folder of PDFs of the cited works
```

**Which input to give.** LaTeX source gives exact file-and-line locations and the most reliable text. Word works well, including tracked changes and comments. A PDF works too, but tables, math and two-column layouts extract less reliably. If you have the LaTeX source and the compiled PDF, give the source folder; the PDF helps with page images.

**How long it takes.** A deep check launches many subagents, one per dimension plus citation judges, so it takes a while and uses a fair amount of your plan. Quality comes first by design. Use quick mode for a fast pass while writing.

**Permissions.** The skill writes only inside a `paper-check-work/` folder beside the paper, plus the two report files. If Claude Code asks for permission to write there, allowing it for the session avoids repeated prompts.

## Read the report

Two files appear beside the paper:

- `paper-check-report.md` for people: a summary, the findings grouped by severity, an index in paper order for fixing the draft from top to bottom, a coverage table of all 119 checks, and appendices for references, citation support and recomputed numbers.
- `paper-check-findings.json` for agents: the same findings with the same IDs, ready for a fixing agent.

Each finding shows:

- **Severity.** Critical means a likely desk rejection or a false main claim. Major is what a referee would raise. Minor is a correctness or polish problem. Suggestion is optional.
- **Status.** Confirmed means the evidence settles it, likely means it deserves a look, and needs human judgment means the skill could not decide.
- **Where and the quote.** Every quote was checked against the paper by a script.
- **Proof and trajectory.** What was compared, computed or searched, step by step.
- **Suggested fix** and how to tell the fix worked.

The coverage table matters as much as the findings. A skipped check was not passed; it was not run, and the table says why.

`paper-check-work/` holds the proof trail: the paper map, the reference evidence cards, the cited texts read, the term searches, and each agent's findings. Keep it if you want to rerun only the report, and delete it when you are done.

## Improve the skill

Read [../dev/ARCHITECTURE.md](../dev/ARCHITECTURE.md) first. The design is [DESIGN.md](DESIGN.md). Run the tests with `python -m pytest` from the repository root. Send changes back by pull request.
