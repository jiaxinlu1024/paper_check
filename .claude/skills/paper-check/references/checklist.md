# Checklist

All 119 checks of the paper-check skill, grouped by dimension. Generated on 2026-10-17 from `references/checks.yaml` (version 0.4, itself generated from `docs/DESIGN.md` section 8). When checks.yaml changes, regenerate this file rather than editing it by hand.

## How to read it

- **How** is the method: SCRIPT (deterministic code), LOOKUP (scholarly databases or the web), READ (an agent reads and judges), COMPARE (two or more places in the paper compared) and VISUAL (a rendered page or figure inspected).
- **Typical** is the default severity. The actual severity depends on the instance, and for venue rules on the venue profile.
- **Covered by** names the producers. *Scripts* means `pc.py checks`, which writes `findings/scripts.json`; *lookups* means `pc.py refs`, which writes `references/cards.json` and `findings/refs.json`; the *citation module* is `pc.py cite-prepare` with the digest and judge agents. Files under `dimensions/` and `agents/` are the prompts in `references/`.
- Every Critical and Major finding, and every negative citation verdict, also goes to the refuter (`agents/refuter.md`). In deep mode, the logic, numbers, behavioral, methods, facts and coherence agents run twice (`agents/second-run.md`), and findings found in only one run are marked likely.
- Each producer records an outcome for every check it owns: run, not applicable, or skipped with the reason. The report's coverage table lists all of them, so a check that did not run never looks passed. SKILL.md section 8 says which checks each mode runs.

## Format and compliance (FMT)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| FMT-01 | Venue limits: page count, abstract word count, file type, page size | SCRIPT against a venue profile; page-limit, margin and font logic adapted from aclpubcheck | Critical | scripts |
| FMT-02 | Anonymization for double-blind review: names, affiliations, acknowledgments, grant numbers, revealing self-citations such as "our previous work [12]", repository links with usernames, PDF and Word metadata author fields | SCRIPT for patterns and metadata, READ for revealing phrasing | Critical | scripts; `dimensions/format.md` |
| FMT-03 | Required statements present: limitations, ethics, data availability, funding, conflicts, venue checklist | SCRIPT for headings, READ for content | Major | scripts; `dimensions/format.md` |
| FMT-04 | Section structure and heading hierarchy: expected sections exist, levels are consistent, no empty sections or lone subsections | SCRIPT, rules reimplemented from TeXtidote's list | Minor | scripts |
| FMT-05 | Broken cross-references: "??", "[?]", undefined or duplicate labels, references to sections or appendices that do not exist | SCRIPT | Major | scripts |
| FMT-06 | Numbering of figures, tables and equations is sequential; every figure and table is labelled and referenced in the text, near where it appears; no hard-coded numbers | SCRIPT, rules reimplemented from TeXtidote's list | Minor | scripts |
| FMT-07 | Captions exist, explain the content on their own, and share one style | SCRIPT and READ | Minor | scripts; `dimensions/format.md` |
| FMT-08 | Reference list consistency: one style, author name format, title capitalization including BibTeX lowercasing such as "Bert" for "BERT", venue naming, required fields, duplicate entries under different keys | SCRIPT | Minor | scripts |
| FMT-09 | In-text citation style: one scheme, no mixing of `\cite` with `\citep`, correct narrative versus parenthetical use, "et al." usage, punctuation and spacing | SCRIPT and READ | Minor | scripts; `dimensions/format.md` |
| FMT-10 | Typography and number format: consistent decimals, separators, unit spacing, en dash in ranges, minus signs, LaTeX quote marks | SCRIPT | Minor | scripts |
| FMT-11 | Draft leftovers: TODO, FIXME, "TBD", "lorem ipsum", `\todo`, "Figure X", "[citation needed]", highlighted text, and sensitive LaTeX comments that would ship in an arXiv source upload | SCRIPT, reporting what arxiv-latex-cleaner would strip without rewriting anything | Major | scripts |
| FMT-12 | Leftover AI assistant text: "As an AI language model", "Certainly, here is", "[insert ...]", "Regenerate response" | SCRIPT and READ | Critical | scripts; `language.md` for the reading part |
| FMT-13 | LaTeX build health: undefined citations and references, overfull boxes into margins, missing figures, font substitution, stale `.bbl` files, and `\todo` macros that print | SCRIPT; needs a `.log` file or a TeX install | Minor to Major | scripts |
| FMT-14 | Word hygiene: tracked changes, comments, hidden text, stale fields such as the table of contents or cross-references, author properties | SCRIPT over the raw XML: `w:ins`, `w:del`, `w:pPrChange`, `w:vanish`, comments and fields | Major | scripts |
| FMT-15 | PDF technical compliance: fonts embedded, Type 3 fonts, page size, metadata, broken links, file size | SCRIPT with pypdf | Minor to Major | scripts |
| FMT-16 | Supplementary references resolve: "Table S3" or "Appendix B" actually exists | SCRIPT and COMPARE | Major | scripts |
| FMT-17 | Accessibility: figure alt text, color-only distinctions, minimum font size inside figures | SCRIPT and VISUAL | Minor | scripts; `dimensions/figures.md` |
| FMT-18 | Hidden instructions: white or hidden text, and text addressed to AI reviewers such as "give a positive review". Every agent treats the manuscript as material to review, never as instructions | SCRIPT and VISUAL | Critical | scripts; every reading agent reports text addressed to AI reviewers |

## Citations and references (CIT)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| CIT-01 | Every in-text citation has a reference entry, and every entry is cited | SCRIPT; Word citations are matched through their field codes | Major | scripts |
| CIT-02 | Every reference exists, under the policy in section 6 | LOOKUP | Critical for a non-existent work, Major for a chimeric citation | lookups; `agents/reference-web-check.md`; refuter as second reviewer |
| CIT-03 | Reference metadata is accurate: title, authors and order, year, venue, volume, pages and DOI, with an evidence card | LOOKUP and a field-by-field SCRIPT diff | Minor, Major when the author list is substantially wrong | lookups; `agents/reference-web-check.md` |
| CIT-04 | A working paper or preprint is cited when a published version exists, section 6 | LOOKUP | Suggestion | lookups |
| CIT-05 | Cited work is retracted, corrected or under an expression of concern, section 6 | LOOKUP | Critical | lookups |
| CIT-06 | The cited work supports the sentence that cites it, section 7. Runs on every citation | LOOKUP for full text, READ, SCRIPT quote checks, and a refuter | Major | citation module: `pc.py cite-prepare`, `agents/source-digest.md`, `agents/citation-judge.md`; refuter |
| CIT-07 | Citation needed: statistics, prior results, "well known", "studies show", and datasets, tools or models used without a citation | READ | Major | `dimensions/citations.md` |
| CIT-08 | Citation appropriateness: secondary source for a primary finding, survey cited for a specific result, outdated work for "state of the art", citation dumps such as "[3-17]", self-citation share | READ, SCRIPT for ratios | Minor | scripts; `dimensions/citations.md` |
| CIT-09 | Important related work is missing, especially work that weakens a novelty claim | LOOKUP by search and citation graph, then READ | Major | `dimensions/citations.md` |
| CIT-10 | Age and balance of the reference list against field norms | SCRIPT | Suggestion | scripts |
| CIT-11 | Datasets, code, pretrained models and tools used are cited, with version and license where required | READ and SCRIPT | Minor to Major | scripts; `dimensions/citations.md` |
| CIT-12 | URLs and DOIs resolve; dead links get an archived alternative | LOOKUP | Minor | lookups |
| CIT-13 | Direct quotations match the source word for word and carry page numbers when the style requires | LOOKUP and SCRIPT | Major | `agents/citation-judge.md` |
| CIT-14 | Replication status: cited findings that failed to replicate, or replicated with smaller effects, are reported with the replication's own label and quote, section 6 | LOOKUP | Major when the paper relies on the finding without saying so | lookups |

## Numbers inside the paper (NUM)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| NUM-01 | The same quantity is reported identically in the abstract, introduction, results, tables, figures and conclusion | SCRIPT extraction, then COMPARE | Major | scripts; `dimensions/numbers.md` |
| NUM-02 | Arithmetic is right: differences, relative versus absolute changes, sums, means, percentages that should total 100, table totals | SCRIPT | Major | scripts; `dimensions/numbers.md` |
| NUM-03 | Statistics are internally consistent. For regression tables: widen each coefficient and standard error by half a unit in their last decimal, compute the implied range of t and p, read the star thresholds from the table note, and flag only when the whole range falls outside the interval the stars imply. A flag is strong when the 5% conclusion flips, and needs human judgment when the degrees-of-freedom assumption decides it, as with few clusters. Also check confidence intervals against b ± 1.96·SE and N across tables. For results in the text: statcheck-style patterns extended to t, F, z, chi-square with N, Mann-Whitney and "(p < 0.05)" | SCRIPT, rebuilt from the published DORIS method | Major. Target false discovery rate: 1.2% or lower | scripts |
| NUM-04 | GRIM, DEBIT and standard-deviation bounds: means, shares and standard deviations of integer or binary data are possible for the stated N. GRIMMER only as a cautious flag | SCRIPT, reimplemented from the methods in scrutiny | Major, flagged cautiously | scripts |
| NUM-05 | Counts add up: participant flow, sample splits, N in tables against N in text | SCRIPT and COMPARE | Major | scripts; `dimensions/numbers.md` |
| NUM-06 | Text, tables and figures agree, including stated trends; every estimate quoted in the text appears in some table or figure; values marked as best really are best | SCRIPT for tables, VISUAL for figures | Major | scripts; `dimensions/numbers.md`; `dimensions/figures.md` for figure images (FIG-06) |
| NUM-07 | Units, magnitudes and precision: units present and consistent, conversions correct, magnitudes plausible, no false precision such as 87.2341% | SCRIPT and READ | Minor | scripts; `dimensions/numbers.md` |
| NUM-08 | "Significant" is used only with a statistical test, and gains within the reported uncertainty are not claimed as effects | COMPARE and READ | Major | scripts; `dimensions/numbers.md` |
| NUM-09 | Percent and percentage points, and log outcomes. A rise from 20% to 25% is 5 percentage points or 25%. A coefficient of 0.50 on a log outcome implies a 64.9% change, not 50% | SCRIPT | Major | scripts; `dimensions/numbers.md` |

## Facts about the outside world (FACT)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| FACT-01 | External factual claims such as dates, definitions, history and population statistics. Verdict: verified, contradicted, outdated, or unverifiable | LOOKUP: split claims into atomic facts, search, and verify against retrieved evidence, after SAFE and VeriScore | Major when contradicted | `dimensions/facts.md` |
| FACT-02 | What the paper says other papers did or found matches those papers | LOOKUP and READ, through the citation support module | Major | citation module; `dimensions/facts.md` for descriptions the module does not reach |
| FACT-03 | Baseline numbers copied from other papers match the source table and setting, in the version read | LOOKUP and COMPARE | Major | `dimensions/facts.md` |
| FACT-04 | Names of people, methods, datasets, organizations and software are spelled correctly and consistently | SCRIPT and LOOKUP | Minor | scripts; `dimensions/facts.md` |
| FACT-05 | Time-sensitive statements such as "recently", "the latest model" or "no current work" are not stale | READ and LOOKUP | Minor | `dimensions/facts.md` |
| FACT-06 | Priority claims such as "first", "only", "novel" or "no prior work" survive a literature search. The best verdict possible is "no contrary evidence in N searches", never "verified novel" | LOOKUP and READ | Major, Critical if clearly false | `dimensions/facts.md` |

## Logic and argument (LOG)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| LOG-01 | Claim-evidence map: every contribution and conclusion links to evidence in the paper; unsupported claims are flagged. The map is included in the report | READ | Major | `dimensions/logic.md` |
| LOG-02 | Overclaiming: conclusions broader than the evidence, "prove" for suggestive results, "state of the art" with partial comparisons, generalizing from one sample | READ and COMPARE | Major | `dimensions/logic.md` |
| LOG-03 | Causal language such as "leads to" or "because" drawn from correlational or observational evidence; confounders not addressed | READ | Major | `dimensions/logic.md` |
| LOG-04 | Internal contradictions, for example 12 sessions in the design section and 10 in the appendix | COMPARE | Major | `dimensions/logic.md` |
| LOG-05 | Hidden or unjustified assumptions, and missing scope conditions | READ | Minor to Major | `dimensions/logic.md` |
| LOG-06 | Reasoning fallacies: circularity, false dichotomy, hasty generalization, cherry-picked outcomes or samples, survivorship bias, ecological fallacy, base-rate neglect, Simpson's paradox risk | READ | Minor to Major | `dimensions/logic.md` |
| LOG-07 | Mathematical correctness: definitions before use, each derivation step follows, theorem conditions match how the proof uses them, quantifiers and edge cases, dimensional consistency. Defaults to needs human judgment unless computed | READ, SCRIPT with sympy for algebra spot checks | Major to Critical | `dimensions/logic.md` |
| LOG-08 | Design validity: the identification strategy and its assumptions, comparison groups, confounds, and reported uncertainty; for computational work, fair baselines and no leakage. Defaults to needs human judgment | READ | Major | `dimensions/logic.md` |
| LOG-09 | Interpretation errors: a non-significant result read as "no effect", p-values read as the probability a hypothesis is true, results described differently than they appear | READ and COMPARE | Major | `dimensions/logic.md` |
| LOG-10 | Plausible alternative explanations for the main result are considered | READ | Minor to Major | `dimensions/logic.md` |
| LOG-11 | The limitations section covers the real weaknesses found by other checks and does not contradict claims made elsewhere | COMPARE and READ | Minor | `dimensions/logic.md` |

## Coherence and structure (COH)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| COH-01 | The thread from problem to research question, contributions, design, results and conclusions holds; every contribution is delivered and evaluated; every analysis answers a stated question | READ | Major | `dimensions/coherence.md` |
| COH-02 | Abstract fidelity: every claim and number in the abstract appears in the body and matches it | COMPARE | Major | `dimensions/coherence.md` |
| COH-03 | Forward references such as "we show in Section 5 that ..." are fulfilled at that location | COMPARE | Minor to Major | `dimensions/coherence.md` |
| COH-04 | The conclusion adds no new results and summarizes the results correctly | COMPARE | Minor | `dimensions/coherence.md` |
| COH-05 | Terminology: one name per concept, no drift between names for the same thing, terms defined before use | SCRIPT for variants, then READ | Minor | scripts; `dimensions/coherence.md` |
| COH-06 | Notation: every symbol defined, used consistently, not overloaded, and the same in text, equations and figures | SCRIPT symbol inventory, then READ | Minor to Major | scripts; `dimensions/coherence.md` |
| COH-07 | Abbreviations defined at first use in the abstract and again in the body, defined once, and actually used after definition | SCRIPT | Minor | scripts |
| COH-08 | Paragraph and section flow: each paragraph makes one point, transitions connect, the order is logical | READ | Minor | `dimensions/coherence.md` |
| COH-09 | Substantially repeated passages across sections | SCRIPT similarity, then READ | Minor | scripts; `dimensions/coherence.md` |
| COH-10 | The title and keywords fit the content and scope | READ | Minor | `dimensions/coherence.md` |
| COH-11 | Related work says how this paper differs, rather than only listing papers | READ | Minor to Major | `dimensions/coherence.md` |
| COH-12 | Each figure and table supports a point in the text, and the text says what to see in it | READ | Minor | `dimensions/coherence.md` |

## Language and clarity (LANG)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| LANG-01 | Spelling, grammar and punctuation; one language variant such as US or UK throughout | SCRIPT for variant words, then READ | Minor | scripts; `dimensions/language.md` |
| LANG-02 | Clarity: overlong sentences, ambiguous "this" or "it", dangling modifiers, deep nesting | SCRIPT for length, then READ | Minor | scripts; `dimensions/language.md` |
| LANG-03 | Hedging matches the strength of the evidence, linked to LOG-02 | READ | Minor | `dimensions/language.md` |
| LANG-04 | Vague or loaded words such as "clearly", "obviously" and "groundbreaking". "Significantly" is flagged only when no statistical test is nearby, because it is a technical term in economics | SCRIPT word list, then READ | Minor | scripts; `dimensions/language.md` |
| LANG-05 | Tense and voice follow section conventions | READ | Suggestion | `dimensions/language.md` |
| LANG-06 | Readability for the target audience: jargon explained, acronym density | SCRIPT metrics, then READ | Suggestion | scripts; `dimensions/language.md` |
| LANG-07 | Inclusive and bias-free language | SCRIPT word list, then READ | Minor | scripts; `dimensions/language.md` |
| LANG-08 | Wordiness and filler | SCRIPT, then READ | Suggestion | scripts; `dimensions/language.md` |

## Methods, data and reproducibility (MTH)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| MTH-01 | Enough detail to reproduce the analysis: data sources, sample construction, variable definitions, estimation methods and software, specifications | READ against a list | Major | `dimensions/methods.md` |
| MTH-02 | Data description: source, collection, size, inclusion and exclusion criteria, cleaning, known biases, license | READ | Major | `dimensions/methods.md` |
| MTH-03 | Code and data availability statements name the access conditions and a trusted repository, with working links | SCRIPT and LOOKUP | Minor to Major | scripts; lookups; `dimensions/methods.md` |
| MTH-04 | Statistical methods: tests named, assumptions checked, effect sizes and intervals reported, sample size justified | READ | Major | `dimensions/methods.md` |
| MTH-05 | Analysis protocol: the main specification is identified, robustness checks are reported, and any specification search is disclosed | READ | Major | `dimensions/methods.md` |
| MTH-06 | Reporting guideline for the study type. No CONSORT-style checklist exists for economics, so economics papers use the composite checklist in the BEH module. Biomedical guidelines such as CONSORT or PRISMA apply only to papers of that type | READ against the loaded guideline file | Major | `dimensions/methods.md` |
| MTH-07 | Preregistration and plan deviations, covered in detail by BEH-06 and BEH-07 | READ and LOOKUP | Minor to Major | `dimensions/methods.md` |

## Ethics, integrity and disclosures (ETH)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| ETH-01 | Human or animal research: ethics approval, consent, participant compensation | READ | Major to Critical | `dimensions/ethics.md` |
| ETH-02 | Conflict of interest and funding statements where required | SCRIPT and READ | Major | scripts; `dimensions/ethics.md` |
| ETH-03 | Author contribution statement where required | SCRIPT | Minor | scripts; `dimensions/ethics.md` |
| ETH-04 | Personal data in examples, figures, screenshots or supplements | READ and VISUAL | Critical | `dimensions/ethics.md` |
| ETH-05 | AI-use disclosure where the venue requires it | SCRIPT and READ | Minor to Major | scripts; `dimensions/ethics.md` |
| ETH-06 | Verbatim overlap with cited abstracts or prior papers the user supplies. Limited: no plagiarism database | LOOKUP and SCRIPT n-gram overlap | Major | scripts; `dimensions/ethics.md` |
| ETH-07 | Duplicated or near-duplicate image panels within the paper. Limited: not full image forensics | SCRIPT with ImageHash, then VISUAL | Major | scripts; `dimensions/ethics.md` |
| ETH-08 | Broader impact, dual-use and risk statements where the venue or topic requires | READ | Minor to Major | `dimensions/ethics.md` |

## Figures and tables (FIG)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| FIG-01 | Legibility: font size against body text, resolution, axis labels, units, legends, grayscale printing | VISUAL | Minor | `dimensions/figures.md` |
| FIG-02 | Honest presentation: truncated or broken axes, mismatched scales across compared panels, error bars present and defined as SD, SE or CI | VISUAL and READ | Minor to Major | `dimensions/figures.md` |
| FIG-03 | Color accessibility: color-only encoding, red-green contrasts | VISUAL | Minor | `dimensions/figures.md` |
| FIG-04 | Table hygiene: units in headers, consistent decimals, star legend present, symbols explained | SCRIPT and READ | Minor | scripts; `dimensions/figures.md` |
| FIG-05 | Consistent styling across figures, such as the same color for the same treatment everywhere | VISUAL | Suggestion | `dimensions/figures.md` |
| FIG-06 | Caption, figure and text agree; legend labels match the names used in the text | VISUAL and COMPARE | Minor to Major | `dimensions/figures.md` |

## Contribution and reviewer view (REV)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| REV-01 | Contributions are stated clearly and specifically, usually at the end of the introduction | READ | Minor | `dimensions/reviewer.md` |
| REV-02 | Novelty holds up against the searches from FACT-06 and CIT-09 | LOOKUP and READ | Major | `dimensions/reviewer.md`, after `facts.md` and `citations.md` have searched |
| REV-03 | The paper argues why the result matters | READ | Suggestion | `dimensions/reviewer.md` |
| REV-04 | Simulated reviews: two or three independent reviewer personas list likely objections and questions, each tied to a quote. Its redesign is deferred, see section 16 | READ | Suggestion | deferred (DESIGN section 16); `dimensions/reviewer.md` records it as skipped |

## Behavioral economics module (BEH)

| ID | Check | How | Typical | Covered by |
|---|---|---|---|---|
| BEH-01 | Deception: giving participants false information counts as deception. Withholding information is a gray area and needs human judgment | READ | Critical where banned, as at Experimental Economics and the Journal of the Economic Science Association; Major elsewhere unless justified | `dimensions/behavioral.md` |
| BEH-02 | Incentives: participants are paid, the payment mechanism is described and incentive compatible, and show-up fee, average earnings and session length are reported | READ | Major | `dimensions/behavioral.md` |
| BEH-03 | Materials: full instructions in an appendix, translations where relevant, screenshots, and the experiment files such as z-Tree, oTree or Qualtrics in the replication package. For ReStud, a reference to an online appendix is not enough | READ | Major | `dimensions/behavioral.md` |
| BEH-04 | Comprehension and attention checks are described, with exclusion rules stated in advance. On Prolific, a participant in a study of five minutes or more can be rejected only after failing at least two attention checks | READ | Major | `dimensions/behavioral.md` |
| BEH-05 | Matching protocol and independent units: partner or stranger matching is described, and inference uses the number of independent units, such as sessions or matching groups | READ | Major | `dimensions/behavioral.md` |
| BEH-06 | Registration: field RCTs in AEA journals are registered in the AEA RCT Registry, with the `AEARCTR-` ID in the title footnote and the references. Lab experiments are exempt. Registration only on OSF or AsPredicted is a warning under the AEA Data Editor's template | SCRIPT for IDs, LOOKUP and READ | Major | scripts; `dimensions/behavioral.md` |
| BEH-07 | Plan comparison: when a pre-analysis plan is available, primary outcomes, sample and specifications match it, and deviations are labelled. Registration alone, without a plan, did not reduce p-hacking | READ and COMPARE | Major | `dimensions/behavioral.md` |
| BEH-08 | Multiple testing: with many outcomes, arms or subgroups, a family-wise or false-discovery correction is applied, such as List-Shaikh-Xu, Romano-Wolf or Anderson's sharpened q-values | READ | Major | `dimensions/behavioral.md` |
| BEH-09 | Clustering: the type of standard errors is stated, and they are clustered at the level of treatment assignment. Flag clustering finer than randomization, and few clusters without a wild bootstrap or randomization inference | READ and SCRIPT | Major | scripts; `dimensions/behavioral.md` |
| BEH-10 | Power, attrition and balance: a power analysis or minimum detectable effect, attrition by arm, a balance table, and bounds such as Lee bounds when attrition differs | READ | Major | `dimensions/behavioral.md` |
| BEH-11 | Software and recruitment citations: oTree requires citing Chen, Schonger and Wickens (2016), and ORSEE's license requires citing Greiner (2015) | SCRIPT | Minor | scripts |
| BEH-12 | Ethics approval in the title footnote: the name of the institutional review board (IRB) and the protocol number, as AEA journals require, and IRB documentation for ReStud | SCRIPT and READ | Major | scripts; `dimensions/behavioral.md` |
| BEH-13 | Data citations and repository: every dataset is cited; the availability statement names access conditions and a trusted repository, since the AEA does not accept GitHub alone. With a replication package, follow the template README and the AEA Data Editor's instructions for AI assistants | SCRIPT and READ | Major | scripts; `dimensions/behavioral.md` |
| BEH-14 | Structural estimates: parameters such as present bias, the discount factor and loss aversion have standard errors, plausible values and an identification argument | READ | Major | `dimensions/behavioral.md` |
| BEH-15 | Classic attributions: well-known findings are cited to their original source, checked against a verified list of common misattributions | LOOKUP and READ | Major | `dimensions/behavioral.md` |
| BEH-16 | Journal requirements: JEL codes, keywords, highlights and disclosure statements, as the target journal's profile requires | SCRIPT | Major | scripts |
