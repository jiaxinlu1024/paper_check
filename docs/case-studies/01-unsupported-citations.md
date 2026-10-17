# Case study 1: real references that do not support the claims

## What happened

A coauthor sent their section of a joint behavioral economics paper. During a routine re-check, the other author found that the literature review cited real papers for claims those papers do not make. A typical sentence said that earlier work had studied a topic and cited a paper, but the cited paper never mentions that topic. After re-checking every citation, the reviewing author judged the problem serious. They sent the section back for revision, tactfully and without accusing anyone. They suspected the review had been written with AI help.

## Why this case matters

- **It passes every existence check.** The references are real and their metadata is correct, so tools that look for fabricated references find nothing.
- **It is slow to catch by hand.** The only way to find it is to read each cited work, which is what the reviewing author had to do.
- **It is a typical failure of AI-assisted literature reviews.** A model can pair a topic with a plausible citation from memory without the source ever being read.
- **It costs credibility.** Referees who know the cited work notice the mismatch, and it undermines trust in the rest of the paper.

## Failure types the skill will name

| Code | Failure | Pattern |
|---|---|---|
| S1 | Off-topic | The cited work does not address the topic at all. "Prior work studied a [X]", but X never mentions a. |
| S2 | Wrong finding | The cited work is on topic but finds something different, or the opposite. |
| S3 | Overreach | The finding holds in a narrower setting than the sentence claims, such as a student lab sample cited as a general fact. |
| S4 | Wrong source | The claim is right but belongs to another paper. Example: a loss aversion coefficient of about 2.25 attributed to Kahneman and Tversky (1979) instead of Tversky and Kahneman (1992). This example still has to be confirmed against both original papers. |
| S5 | Secondhand | The cited work only repeats the claim from another source, such as a survey cited for an original result. |
| S6 | Misdescribed method | The design, sample or data are described wrongly, such as a lab study described as a field experiment. |
| S7 | Partial | The source supports only one part of a compound claim. |

Each citation gets one verdict:

- **Supported.** A quoted passage states the specific claim.
- **Partly supported.** The report names the part of the claim the source does not cover.
- **Not supported: topic absent.** The source never addresses the topic, failure code S1.
- **Not supported: misattributed.** The claim belongs to another work, failure codes S4 and S5.
- **Not supported: misdescribed.** The source found or did something different, failure codes S2 and S6.
- **Contradicted.** The source says the opposite.
- **Cannot verify.** The full text was not available. The report asks for the PDF.

## How the skill will check it

The authoritative version of this pipeline, including the proof each verdict needs, is section 7 of `docs/DESIGN.md`.

1. **Find every citing sentence.** Extract each sentence that carries a citation, plus the sentence before it for context. Split compound sentences so that each claim is paired with the citations meant to support it. Tag the claim type: topic, finding, direction of effect, method, number, definition, or origin of a concept.
2. **Get the cited work's text, best source first.**
   1. PDFs the user places in a sources folder. These come first, because authors often have institutional access to paywalled journals.
   2. Open-access full text from Unpaywall, OpenAlex, Semantic Scholar, arXiv or CORE.
   3. Working-paper versions from NBER, IZA, CEPR, RePEc, SSRN, OSF or the authors' homepages. The report notes when the version read differs from the published article.
   4. The abstract alone, as a last resort.

   The report always records which version was read.
3. **Search the cited work for the claim.** Expand the concept into synonyms and related terms. For present bias, that means terms such as hyperbolic discounting, quasi-hyperbolic, beta-delta and time inconsistency. Search the full text for every term, and also retrieve the passages closest in meaning. Keep page numbers and equations, because a source that estimates a present-bias parameter below 1 supports a sentence about present bias even if the phrase never appears. The relation between terms shapes the verdict: a related concept is not a synonym. A source that only fits a hyperbolic discount function partly supports a sentence about present bias.
4. **Judge.** Claude reads the closest passages and gives a verdict and a failure code. A "supported" verdict must quote a passage that names the specific concept or an approved synonym. Sharing the topic is not support. The survey found that automated checkers most often fail by accepting a citation because its topic overlaps with the claim. A "not supported" verdict must show the search record: the version read, the pages covered, the terms searched with their hit counts, the closest passages, and what the paper is actually about.
5. **Verify.** A second agent re-reads independently and tries to find support that the first pass missed. The refuter may overturn a verdict only by quoting counter-evidence. Any "not supported" verdict requires the full text. When only the abstract is available, the verdict can be supported, contradicted, or cannot verify, and the report asks for the PDF. Abstracts leave out about a fifth of the concepts that citing sentences attribute to a paper, so an abstract can confirm a citation but can never prove a topic absent.
6. **Suggest a fix.** Either rewrite the sentence to match what the source says, quoting it, or propose replacement citations found by a literature search, each with the passage that supports the claim. Every suggested replacement must itself pass the existence and support checks, so the skill never introduces a new bad citation.
7. **Summarize the pattern.** Count the verdicts for each section, for example "Section 2: 14 of 31 citations not supported or contradicted". This shows the scale of a problem without speculating about how the text was written.

## Example finding

This example is fictional. It shows the format only.

```markdown
### F-031 · Major · CIT-06 Citation supports the claim · Not supported: topic absent (S1)
Status: confirmed · Confidence: high
Where: Section 2.1, paragraph 3, sentence 2 (lit_review.tex:48)

> "Earlier studies have examined present bias in gym attendance (Doe and Roe, 2015)."

Problem: Doe and Roe (2015) study default effects in retirement savings plans.
The paper does not discuss exercise or gym attendance, and none of the terms
for present bias appear in it.

Proof:
- Version read: published article, 31 pages, from the user's sources folder.
- Terms searched, with hits: "present bias" 0, "present-biased" 0, "hyperbolic" 0,
  "quasi-hyperbolic" 0, "time inconsistency" 0, "self-control" 0, "exercise" 0,
  "gym" 0, "procrastination" 3.
- Closest passage, p. 12: "...employees procrastinate in changing their
  contribution rate..."
- The paper's own summary, p. 1: "...we show that automatic enrollment raises
  participation..."

Trajectory:
1. Extracted the citing sentence and tagged it as a topic claim about present bias in exercise.
2. Loaded the cited article and confirmed it matches the reference entry.
3. Searched nine terms and retrieved the five closest passages.
4. Verdict: not supported, failure code S1.
5. A verification agent searched the footnotes and appendix for support: none found.

Suggested fix: cite a study of present bias in gym attendance, after the skill
confirms it supports the sentence. Otherwise rewrite the sentence to describe
what Doe and Roe (2015) actually show.
```

## Tone of the report

The report describes mismatches and the evidence for them. It never speculates about who wrote a passage or whether AI was used. AI-text detectors are unreliable, while a citation mismatch is a verifiable fact. That makes the report safe to forward to a coauthor as it stands, which matches how this case was handled.

## Test cases to build

1. **This case itself is not available.** The section will not be shared, so the seeded errors below reproduce its pattern instead.
2. **Seeded errors.** Take a correct literature review paragraph and swap in citations that create known S1, S2 and S4 errors. Check that the skill flags those errors and nothing else.
3. **Classic misattributions.** Build a fixed set of commonly misattributed behavioral economics findings, each confirmed against the original sources, and rerun it after every change to the skill.

## What this changes in the design

- Citation support becomes a core module, not a single checklist item. It runs on every citation by default, since run time is not a constraint.
- The skill accepts a sources folder of PDFs for cited works, and records which version of each work it read.
- Verdicts use the failure codes above, and absence claims need a full search record as proof.
- The report adds a citation support table with one row per citation, and a per-section summary.
- The survey in `reports/Existing paper check tools.md` found no tool that produces full-text absence proofs. It also found that human annotators agree only weakly on citation accuracy. The test sets above therefore come before any tuning.
