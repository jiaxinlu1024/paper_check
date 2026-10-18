# Using the paper-check skill

paper-check is a Claude Code skill. It checks a paper draft and writes a report in which every finding quotes the draft, gives its location, shows the proof and the steps taken, and suggests a fix. It never edits the paper.

## Set up once

Ask Claude Code to do it: "Set up the paper-check skill from https://github.com/jiaxinlu1024/paper_check by following the steps for Claude Code in its README." It clones the repository, asks for your work or university email, and runs one command, `pc.py install`, which:

- creates a private Python environment in `~/.paper-check/venv` (nothing is installed system-wide);
- links the skill into `~/.claude/skills/paper-check`, so it works from any folder;
- writes `~/.paper-check/config.yaml` with your contact email, readable only by you;
- requests a free OpenAlex key for that email (click the activation email OpenAlex sends);
- checks a sample paper and reports what works.

To do it yourself instead, clone the repository and run `python3 .claude/skills/paper-check/scripts/pc.py install --email you@your-university.edu --request-openalex-key` from it. A Semantic Scholar key is optional: [api-access.md](api-access.md) has the form. The lookups need internet access; on a Claude Code cloud environment, see [network-setup.md](network-setup.md).

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

**How long it takes.** A deep check launches many subagents, one per dimension plus citation judges, so it takes a while and uses a fair amount of your plan. In our tests a deep check of a full paper took about an hour and used roughly 450,000 tokens, about twice what asking Claude directly uses; a quick check took about half an hour. Quality comes first by design. Use quick mode for a fast pass while writing.

**Permissions.** The skill writes only inside a `paper-check-work/` folder beside the paper, plus the two report files. If Claude Code asks for permission to write there, allowing it for the session avoids repeated prompts.

## Read the report

Three files appear beside the paper:

- `paper-check-report.md` for people, about one and a half times the length of the paper. Page one is a fix list: the top issues, each with its fix, then the other Major findings. Then come the counts, every Critical and Major finding in full, two tables of Minor findings and suggestions (one about substance, one of small fixes to wording and format), an index in paper order for fixing the draft from top to bottom, and the checks that did not run in full, with the reason.
- `paper-check-evidence.md` for checking the report: every finding in full, with its proof and the steps that led to it, under the same IDs, and the appendices: references, citation support, the claim-evidence map, recomputed numbers, and refuted and dropped findings.
- `paper-check-findings.json` for agents: the same findings with the same IDs, ready for a fixing agent. IDs stay the same if the report is rebuilt.

Each finding shows:

- **Severity.** Critical means a likely desk rejection or a false main claim. Major is what a referee would raise. Minor is a correctness or polish problem. Suggestion is optional.
- **Status.** Confirmed means the evidence settles it, likely means it deserves a look, and needs human judgment means the skill could not decide.
- **Where and the quote.** Every quote was checked against the paper by a script.
- **Proof and trajectory**, in the evidence file. What was compared, computed or searched, step by step.
- **Suggested fix** and how to tell the fix worked.

The coverage section matters as much as the findings. A skipped check was not passed; it was not run, and the table says why. *Not verified* marks a statement about another work that the run did not check.

## Trying it out

The skill is an early version. If you are testing it, send back:

- findings that are wrong or unclear, by ID (F-012), and why;
- problems a careful reader would raise that the report missed;
- how long the check took, the mode, and the input type (LaTeX, Word or PDF);
- any error message, and whether page one told you what to fix first.

You don't need to send the paper. The report files quote it, so share them only if the draft can be shared.

`paper-check-work/` holds the proof trail: the paper map, the reference evidence cards, the cited texts read, the term searches, and each agent's findings. Keep it if you want to rerun only the report, and delete it when you are done.

## Improve the skill

Read [../dev/ARCHITECTURE.md](../dev/ARCHITECTURE.md) first. The design is [DESIGN.md](DESIGN.md). Run the tests with `python -m pytest` from the repository root. Send changes back by pull request.
