# Citation support (CIT-06)

This file restates section 7 of `docs/DESIGN.md` (v0.4) and the failure codes of case study 1 (`docs/case-studies/01-unsupported-citations.md`). The digest and judge agents follow it, through `agents/source-digest.md` and `agents/citation-judge.md`, and the refuter checks their negative verdicts against it. Some of the judge's rules are adapted from citecheck's claims rubric, MIT-licensed; see `THIRD_PARTY_NOTICES.md` at the skill root.

## Why this module exists

In case study 1, a coauthor's literature review cited real papers for claims those papers never make: a sentence said earlier work had studied a topic and cited a paper that never mentions it. Such citations pass every existence check, because the references are real and their metadata is right. Finding them takes reading each cited work, which is slow by hand and is exactly what this module automates. It runs on every citation by default.

Two errors matter most. Checkers wrongly accept a citation most often because its topic overlaps the claim, and a judge without a proper search wrongly rejects correct citations. The design answers both the same way: every verdict carries its proof, and every negative verdict shows a full-text search record.

## Pipeline

1. **Find attributed propositions.** `pc.py cite-prepare` extracts each citing sentence with the sentence before it, splits it so that each claim is paired with the citations meant to support it, and tags the claim type: topic, finding, direction of effect, method, number, definition, or origin of a concept. Output: `WORK/citations/propositions.jsonl` (ids `c001`, `c002`, ...) and `WORK/citations/by_ref.json`.
2. **Get the full text legally, best source first:** the user's sources folder of PDFs; OpenAlex's best open-access location; Unpaywall; Semantic Scholar's open-access PDF; NBER working papers, free 18 months after release; CORE; and the abstract alone, as a last resort. OpenAlex's paid PDFs stay off unless the user turns them on, and shadow libraries are never used. The version read is always recorded, because a submitted version may differ significantly from the published article. Output: `WORK/citations/sources/<ref>.txt` with page markers, `sources/<ref>.json`, and `WORK/citations/status.json`.
3. **Digest each cited work once.** A digest agent writes a page-anchored digest of each work with full text: topics, questions, methods, samples, main findings and key parameter estimates, each with a verbatim quote and page. Every citation of the work reuses the digest. Output: `WORK/citations/digests/<ref>.json`.
4. **Expand the terms.** Turn the claimed concept into synonyms, related terms from the STW Thesaurus for Economics, model names, and symbols and parameters, such as β for present bias. Keep each term's relation to the concept, because it decides the verdict (see the table below).
5. **Scan and rank.** `pc.py scan WORK --ref <ref> --terms ...` searches the full text for every term and records the hits per term, with pages, in `WORK/citations/scans/<ref>.jsonl`. That record is the proof of absence. It then ranks the passages around the hits, and the judge reads the best ones with the digest. Dense retrieval is optional; the evaluation sets decide whether it is needed.
6. **Judge.** A judge agent gives each proposition a verdict and a failure code under the rules below, and writes findings to `WORK/findings/agent_citations_<n>.json` and one row per citation to `WORK/citations/verdicts_<n>.json`.
7. **Verify.** `pc.py verify` checks every quote taken from a source against its cached text. The refuter re-examines every negative verdict, searching appendices, tables and footnotes, and may overturn a verdict only by quoting counter-evidence.
8. **Suggest a fix.** Either rewrite the sentence to match what the source says, quoting it, or propose replacement citations. Every replacement must itself pass the existence and support checks, so the skill never introduces a new bad citation.
9. **Summarize.** The report counts the verdicts for each section, for example "Section 2: 14 of 31 citations not supported or contradicted". This shows the scale of a problem without speculating about how the text was written.

## Failure codes

| Code | Failure | Pattern |
|---|---|---|
| S1 | Off-topic | The cited work does not address the topic at all: "prior work studied X in Y", but the work never mentions Y |
| S2 | Wrong finding | The work is on topic but finds something different, or the opposite |
| S3 | Overreach | The finding holds in a narrower setting than the sentence claims, such as a student lab sample cited as a general fact |
| S4 | Wrong source | The claim is right but belongs to another work, such as a classic estimate credited to an earlier paper by the same authors |
| S5 | Secondhand | The work only repeats the claim from another source, such as a survey cited for an original result |
| S6 | Misdescribed method | The design, sample or data are described wrongly, such as a lab study described as a field experiment |
| S7 | Partial | The work supports only one part of a compound claim |

## Verdicts and the proof each needs

| Verdict (as written in `verdicts_<n>.json`) | Failure codes | Proof required |
|---|---|---|
| supported | none | A quoted passage that names the concept or an approved synonym, or the equation or estimate that is the concept |
| partly supported | S3, S7, or support only through a related concept | A quoted passage, and the part of the claim it does not cover |
| not supported: topic absent | S1 | The full-text search record: version read, pages, every term with its hit count, the closest passages, and what the work is about; or, from an abstract alone, the abstract's sentence showing that the work is about a different subject altogether |
| not supported: misattributed | S4, S5 | A passage showing that the work does not originate the claim, and the likely original source if found |
| not supported: misdescribed | S2, S6 | A passage showing what the work actually found or did |
| contradicted | S2, when the work finds the opposite | A quoted passage stating the opposite |
| cannot verify | none | What was tried. The report asks for the PDF |

## Rules for the judge

- **Sharing the topic is not support.** In the survey's evidence, checkers that wrongly passed a citation usually did so because the topic overlapped.
- **A related concept is not a synonym.** A source that only fits a hyperbolic discount function partly supports a sentence about present bias.
- **Equations count.** A source that estimates a present-bias parameter below 1 supports a sentence about present bias even if the phrase never appears.
- **An abstract cannot show that a detail is absent, but it can show what the work is.** Citing sentences attribute about a fifth more concepts to a paper than its abstract contains, so a concept missing from the abstract proves nothing. When the abstract shows that the work is about a different subject, population or setting altogether (S1), is a different kind of work than the sentence needs, such as a review or bibliometric study cited as original evidence (S5) or a theory paper cited for an empirical finding (S6), or states a finding at odds with the claim (S2), give that verdict from the abstract: record `version_read` as "abstract only", make the finding likely, never confirmed, quote the abstract's sentence that shows it, and say that the full text would settle it. Otherwise, with only the abstract, a negative verdict becomes cannot verify.
- **Judge only the part of the sentence attributed to this citation.** In "X (A) and Y (B)", A answers for X only.
- **Background citations** are supported when the work addresses the specific topic named, not a neighbouring one; **tools, datasets and methods** cited for their use are supported when the work introduces or documents them; **surveys** are supported for claims within their scope, but a survey cited as the source of an original result is S5.
- **Record the version read.** A working paper and its published article can differ in results and numbers.
- **When torn between two verdicts, choose the milder one and mark it needs human judgment.** A false alarm costs the writer time and trust, and people themselves agree only weakly on borderline cases. A milder verdict never excuses a missing quote: "supported" always needs the passage that names the concept.
- **Never judge from memory** of a cited work; only from its cached text, its digest or a page opened in this run.

## How term relations shape the verdict

| Relation to the claimed concept | Example, for a claim about present bias | Can it support the claim? |
|---|---|---|
| Synonym | "present-biased preferences" | Yes |
| Narrower form or measure | "quasi-hyperbolic discounting", an estimate of β below 1 | Yes, by the equations rule |
| Symbol or parameter, as the work defines it | "β" defined as the present-bias factor | Yes |
| Broader concept | "time inconsistency" in general | Partly, at most |
| Related concept | "hyperbolic discounting", "procrastination" | Partly, at most; never supported alone |
| Same setting only | "retirement saving" | No: that is topical overlap |

## Direct quotations (CIT-13)

When a citing sentence quotes a work directly, the judge scans the cached text for the quoted words. Every changed, added or dropped word is reported, and an omission must be marked with an ellipsis. The page number is checked when the style requires one, from the venue's citation style or the paper's own practice. Altered wording is Major; a missing or wrong page is Minor. Without the full text, the quotation is recorded as not checked.

## Verdict rows

Each judge writes `WORK/citations/verdicts_<n>.json`, a JSON list with one object per proposition and reference:

```json
[{"id": "c027", "section": "2 Related literature", "claim": "Overconfidence drives excessive trading in retirement accounts",
  "ref": "r031", "verdict": "not supported: topic absent", "failure_code": "S1",
  "version_read": "published article, sources folder", "finding": "Cited work does not study overconfidence or trading"}]
```

`section` is the top-level heading of the citing block, so that the report's per-section summary adds up. `finding` is the title of the matching finding, or null for supported and cannot verify. The report merges every `verdicts*.json` file.

## Tone

The report describes mismatches and the evidence for them. It never speculates about who wrote a passage or whether AI was used: AI-text detectors are unreliable, while a citation mismatch is a verifiable fact. That makes the report safe to forward to a coauthor as it stands, which is how case study 1 was handled.

## Measuring it

Verifier strictness alone can move the share of citations judged unsupported from about 3% to about 18%, and human annotators agree only weakly on citation accuracy. Every threshold and prompt change is therefore measured on the evaluation sets in `evals/README.md`, which test false accepts as hard as false rejects, and every trajectory records the verifier settings.
