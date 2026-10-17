# Evaluation sets

Every threshold and prompt in the skill is tuned against these sets, and every change is measured on them again. The survey found that a verifier's strictness alone can move the share of citations judged unsupported from about 3% to about 18%. It also found that people agree only weakly on whether a citation is accurate. Without these sets, no number the skill reports can be trusted.

## Sets

| Set | What it tests | Source | Labels | Status |
|---|---|---|---|---|
| case-study | Citation support on a real literature review | The section from case study 1, with the reviewing author's notes | Verdict and failure code per citation, taken from the notes | Not available, because the section will not be shared. The seeded set reproduces its pattern |
| seeded-citations | Citation support for S1, S2 and S4 errors | Clean literature-review paragraphs from open-access behavioral economics papers, with citations swapped | Known by construction. Untouched paragraphs act as negative controls | To build |
| propositions | Citation support on real drafts | 50 to 100 attributed propositions from behavioral drafts, about a third of them correct | Two people label each one independently. Disagreements are resolved and recorded | Needs drafts |
| references | Reference existence and metadata | Published planted-error sets, such as HALLMARK and bib-check-agent's test, plus an economics set of working papers with their published versions, chimeric citations and metadata drift | Known by construction | To build. Check each set's license before copying it |
| perturbations | Reading and number checks | Clean drafts with injected errors: abstract and table disagree, wrong significance stars, broken cross-references, notation drift, contradictions | Known by construction | Needs drafts |
| misattributions | Classic attributions, check BEH-15 | Well-known behavioral findings with their original sources | Each entry confirmed against the original paper before use | To build |

## What each run records

- **Verifier settings:** model, prompt versions, strictness, number of runs and thresholds.
- **Version and date** of the skill.
- **Per item:** the expected label, the skill's label, and whether the evidence shown was enough for a person to decide.

## Metrics

| Metric | Meaning |
|---|---|
| Precision and recall | Per check, and per verdict for citation support |
| False accepts | Wrong citations or real errors that the skill passed. Tested as hard as false rejects |
| False rejects | Correct citations or correct text that the skill flagged |
| Run-to-run agreement | Share of findings that appear in both runs |
| Agreement with people | Cohen's kappa between the skill and each human labeller, next to the kappa between the labellers |
| Review time | Minutes a coauthor needs to confirm or dismiss each finding using only the report |

Targets are set after the first baseline run. One target is fixed in advance: the regression-table star check should reach a false discovery rate of 1.2% or lower, the rate reported for the DORIS method.

## Data handling

Unpublished drafts and coauthors' notes never go into the repository unless the authors agree. They live in `evals/private/`, which git ignores. Published papers are referenced by DOI and downloaded at run time from legal open-access sources. They are not committed.

## Layout

```
evals/
  README.md          this file
  sets/              one folder per set, with labels in JSONL
  private/           drafts and notes, ignored by git
  results/           one folder per run, with its settings
```

One label per line, for example:

```json
{"set": "seeded-citations", "item": "sc-0001", "citing_sentence": "...", "cited_doi": "...", "expected_verdict": "not_supported_topic_absent", "expected_code": "S1", "notes": "..."}
```
