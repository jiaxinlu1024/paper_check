# Paper Check skill: design

Status: v0.4, 2026-10-17. Adopts the P0 and P1 recommendations from the survey of existing tools in `reports/Existing paper check tools.md`. No code is built yet.

## 1. Goal

Given a paper draft as LaTeX source, PDF, or Word, produce a report that a writer or a fixing agent can act on. Every finding quotes the original text, gives its exact location, shows the proof, and records the trajectory: the steps, tools, and sources used to reach the finding.

The skill reports only. It never edits the paper.

### Decisions so far

| Topic | Decision |
|---|---|
| Field | Behavioral economics, both experimental and empirical work |
| Run time and cost | Not a constraint. Quality comes first, so the default mode is deep. |
| Finding order | By severity, with an index of findings in paper order |
| Reviewer view | A full dimension alongside the correctness checks |
| Citation support | A core module that checks every citation, following case study 1 in `docs/case-studies/` |
| Survey recommendations | P0 and P1 adopted on 2026-10-17. P2 deferred, see section 16 |
| Network | Full access in the cloud environment, set on 2026-10-17 |
| Repository | https://github.com/jiaxinlu1024/paper_check |
| Test drafts | Real drafts to be supplied later |
| Target journals | The top behavioral economics journals, listed in section 12 |
| Credentials | A work email as the contact address. OpenAlex key requested on 2026-10-17; Semantic Scholar and RePEc applications prepared. See `docs/api-access.md` |
| Sources folder | The user keeps PDFs of the cited works |
| Case-study section | Not available for testing |

## 2. Build order

The survey found no tool that reports its accuracy on economics papers. It also found that a verifier's strictness alone can move the share of citations judged unsupported from about 3% to about 18%. Every threshold therefore has to be set against test data, so the evaluation sets come first.

1. **Evaluation sets and harness,** section 13 and `evals/README.md`.
2. **Ingestion** into the paper map, section 3.
3. **Reference checks** under the policy in section 6.
4. **Citation support,** section 7.
5. **Number and statistics scripts,** including regression tables, section 8.3.
6. **Reading checks** with prompts adapted from MIT-licensed projects, section 4.
7. **The behavioral economics module and venue profiles,** sections 8.12 and 12.
8. **Verification, coverage and the report,** sections 9 and 11.

Each step is measured on the evaluation sets before the next one starts.

## 3. Inputs and how they are read

All three formats become one internal paper map. Every block of text keeps an anchor back to the original, so every finding can quote and point.

| Input | Reader | Anchor | Notes |
|---|---|---|---|
| LaTeX, multi-file, with `.bib` | flachtex flattens `\input` and `\include` and maps every character back to its file and line. pylatexenc or tree-sitter-latex finds labels, references and citations with line and column. bibtexparser v2 reads `.bib` entries with their start lines and flags duplicate keys | `file:line` | Most precise. A supplied `.log`, `.blg` or `.bbl` file feeds the build checks, and a compiled PDF feeds page limits and visual checks |
| PDF | pdfplumber gives every character with coordinates, page crops for visual checks, and tables. pypdf reads metadata and fonts | `page N, line M` | Quotes always come from the PDF text layer, never from a parser that re-types text. Two-column layouts, math and tables can extract imperfectly |
| Word (.docx) | python-docx for paragraphs, styles and comments, plus lxml over the raw XML for tracked changes (`w:ins`, `w:del`, `w:pPrChange`), hidden text (`w:vanish`) and field codes | `paragraph N` under its heading path | Citations inserted by Zotero or Mendeley carry CSL-JSON metadata in their field codes. That gives exact reference data and links each citation to its entry. LibreOffice, when installed, renders the document to PDF for visual checks |

The paper map holds the section tree, paragraphs, sentences, in-text citations, reference entries, figures and tables with captions, equations, every number with its unit and context, and abbreviations. It also holds a **definitions and notation slice**: every defined term, symbol and key parameter, with where it is defined. Every reading agent receives that slice, because the survey found that giving reviewers the paper's definitions raised their recall sharply.

### Dependencies

The core depends only on permissively licensed Python packages:

| Package | License | Used for |
|---|---|---|
| pdfplumber | MIT | PDF text with coordinates, crops, tables |
| pypdf | BSD | PDF metadata and fonts |
| python-docx and lxml | MIT and BSD | Word text, comments and raw XML |
| flachtex | MIT | LaTeX flattening with an origin map |
| pylatexenc or tree-sitter-latex | MIT | LaTeX parsing with positions |
| bibtexparser v2 | MIT | `.bib` parsing |
| rapidfuzz | MIT | Fuzzy matching of titles and names |
| scipy | BSD | Statistics recomputation |
| ImageHash | BSD | Duplicate figure panels |

PyMuPDF, which is AGPL, is never a hard dependency. Optional accelerators are listed in section 16.

## 4. Pipeline

1. **Ingest.** Build the paper map and save it in the work folder.
2. **Script checks.** Run the deterministic checks.
3. **Lookups.** Check references, retractions, replications and versions through bundled REST clients, following section 6.
4. **Citation support.** Run the module in section 7 on every citation.
5. **Reading checks.** Launch one subagent per dimension, all in a single message. Each gets its checklist, the relevant part of the paper map, and the definitions and notation slice. Each reads passage by passage rather than the whole paper at once, and returns findings as JSON with verbatim quotes. The prompts are adapted, with attribution, from Claes Bäckman's AI-research-feedback and from OpenAIReview, both MIT-licensed. They keep these rules:
   - **Scope guard.** Every prompt opens by saying the manuscript is material to review, never instructions.
   - **Quote or drop.** An agent that cannot quote the problem does not report it.
   - **Unverified label.** Any claim about the literature that the agent did not look up is marked `[UNVERIFIED]`.
   - **Leniency and do-not-flag lists** for each dimension, to cut generic comments.
   - **Root-cause merge.** Findings with the same cause are combined into one.
6. **Verification.** Section 9.
7. **Report.** Section 11, including the coverage table.

## 5. Methods, severity and confidence

### Methods

| Code | What it means | Proof the report shows |
|---|---|---|
| SCRIPT | Deterministic code: parsing, pattern matching, arithmetic, statistics | Script name, the input it read, its output, and any formula |
| LOOKUP | Query to scholarly databases or the web | Database, exact query, matched record or URL, and quoted source text |
| READ | Claude reads and judges the text | Verbatim quotes with locations, the reasoning, and the verification outcome |
| COMPARE | Two or more places in the paper are compared | Every quote involved, each with its location |
| VISUAL | A page or figure is rendered to an image and inspected | Page and figure number, the saved image crop, and a description |

### Severity

| Level | Meaning | Examples |
|---|---|---|
| Critical | Likely desk rejection, retraction, or a false main claim | Non-existent reference, anonymity breach, main result number wrong, page limit exceeded, leftover AI assistant text |
| Major | A reviewer would raise it, or it weakens a claim | Unsupported conclusion, numbers disagree between abstract and table, citation does not support the claim |
| Minor | A correctness or polish problem that does not change meaning | Abbreviation not defined, inconsistent decimals, figure never referenced |
| Suggestion | Optional improvement | Wordiness, a related paper worth citing |

### Confidence and status

Confidence is high, medium or low. It combines three inputs:

- **Evidence type.** Computed results and quotes from full text are strongest.
- **Refutation.** Whether the finding survived the refuter in section 9.
- **Run agreement.** Whether the finding appeared in both runs of a high-value reading check.

Status is confirmed, likely, or needs human judgment. Mathematical correctness (LOG-07) and design validity (LOG-08) default to needs human judgment unless the error is computed. The survey found that no model reliably finds deep errors in economics papers without human guidance.

## 6. Lookups and the reference policy

### Clients

Every lookup goes through a bundled script with a cache, an identifying user agent, the service's contact or key parameter, rate limiting and exponential backoff. MCP servers are optional extras, never the backbone. The limits below were reported by the survey on 2026-10-17 and must be rechecked when the clients are written.

| Service | Access | Limits and notes |
|---|---|---|
| Crossref | Contact email, for the polite pool | 10 requests per second for DOI lookups and 3 for searches, since December 2025. Retractions appear in `update-to` |
| OpenAlex | Free API key, required since February 2026 | Single-DOI lookups are free; other use draws on a daily allowance. Labels each copy of a work as submitted, accepted or published |
| Semantic Scholar | Free API key, issued only to institutional email addresses | 1 request per second |
| DataCite | Contact email | Dataset DOIs |
| Unpaywall | Contact email on every request | Open-access locations by DOI |
| arXiv | None | 3 seconds between requests |
| doi.org | None | Content negotiation for metadata |
| RePEc | API access only on emailed request, with no search | Links working papers to their published versions |
| NBER | None | DOIs of the form `10.3386/w#####` |

Positive results are cached for 7 days and negative results for 24 hours, so a temporary failure is retried soon. Keys and the contact email live in a user-level file, `~/.paper-check/config.yaml`, outside any repository.

### Reference policy

Adapted from RefChecker, bib-check-agent, citecheck and Crossref's matchers, all MIT-licensed.

1. **Identifier first.** Resolve the DOI, arXiv ID, NBER number or SSRN ID when the entry has one.
2. **Search-based matching.** Search Crossref with the raw reference string rather than trusting parsed fields. Then validate the candidate field by field: title similarity, author overlap, year and venue.
3. **Two sources for verified.** A reference is verified only when two independent databases agree.
4. **Non-existent only after three failures.** A reference is called non-existent only when its identifier fails, every database fails to match it, and a web search for the exact title finds no page dedicated to the work. A second reviewer must agree. A failed or unreachable lookup makes a reference unverified, never fabricated.
5. **Severity by kind.**

   | Kind | Example | Severity |
   |---|---|---|
   | Non-existent work | No record anywhere, and no dedicated page | Critical |
   | Chimeric citation | A real NBER number paired with another paper's title | Major |
   | Metadata drift | Year off by one, venue or pages wrong | Minor |
   | Status drift | A working paper that has since been published | Suggestion |

6. **Calibrated thresholds.** Start from the MIT tools' values and calibrate them on the evaluation sets. RefChecker uses title similarity 0.8, a year within one, and author overlap 0.6. Crossref's preprint matcher accepts at 0.87, with a year window from one year before to three years after.
7. **Evidence card for every reference.** The closest record found, the similarity of each field, every query made, and which databases were reached.

### Working papers and published versions (CIT-04)

No open tool handles economics working papers, so this part is new.

1. Extract NBER, SSRN, IZA and CEPR identifiers from each entry, and resolve NBER DOIs.
2. Search Crossref for journal articles, OpenAlex for other locations of the same work, and RePEc for linked versions once access is granted.
3. Use a wide year window, and weight the author set above the title, because titles often change between versions.
4. Report a published version as a Suggestion. Pass the version actually read on to the citation support and baseline checks.

### Retractions and replications (CIT-05, CIT-14)

1. Cache the daily Retraction Watch file and the FORRT Replication Database (FReD) locally.
2. Confirm every hit with Crossref's `update-to` field and OpenAlex's `is_retracted` flag, and list every notice for a DOI.
3. Never filter by subject. The behavioral cases that matter most are tagged Psychology, Ethics or Sociology, not Economics.
4. Match notices that have no DOI by title and authors.
5. Report each replication with its outcome label and a quote of the replication's own conclusion. Never call a finding false.
6. Use Institute for Replication (I4R) reports as a second source.

## 7. Citation support module (CIT-06)

1. **Find attributed propositions.** Extract each citing sentence with the sentence before it. Split it so that each claim is paired with the citations meant to support it. Tag the claim type: topic, finding, direction of effect, method, number, definition, or origin of a concept.
2. **Get the full text legally, best source first.**
   1. The user's folder of PDFs.
   2. OpenAlex's best open-access location.
   3. Unpaywall.
   4. Semantic Scholar's open-access PDF.
   5. NBER working papers, which are free 18 months after release.
   6. CORE.
   7. The abstract alone, as a last resort.

   OpenAlex also sells cached PDFs, which stay off unless the user turns them on. Shadow libraries are never used. The version read is always recorded, because OpenAlex warns that a submitted version may differ significantly from the published article.
3. **Digest each cited work once.** A reading agent writes a page-anchored digest of the work: topics, questions, methods, samples, main findings and key parameter estimates, each with verbatim quotes. A script checks every quote against the cached text. Every citation of that work reuses the digest.
4. **Expand the terms.** Turn the claimed concept into synonyms, related terms from the STW Thesaurus for Economics, model names, and symbols and parameters, such as β for present bias. Keep each term's relation to the concept, because it decides the verdict.
5. **Scan and rank.** Search the full text for every term and record the hits per term, with pages. That record is the proof of absence. Then rank the passages around the hits by BM25, and pass the best ones and the digest to the judge.

   This step adapts the survey's recommendation. Dense embeddings and a reranker are optional, because they add a heavy PyTorch dependency, and the digest covers paraphrase instead. The evaluation sets decide whether dense retrieval is needed.
6. **Judge.** Give a verdict and a failure code under the rules below.
7. **Verify.** A script checks every quote taken from the source. A refuter re-examines every negative verdict, searching appendices, tables and footnotes. It may overturn a verdict only by quoting counter-evidence.
8. **Suggest a fix.** Either rewrite the sentence to match what the source says, quoting it, or propose replacement citations. Every replacement must itself pass the existence and support checks.
9. **Summarize.** Count the verdicts for each section in the report.

### Verdicts

| Verdict | Failure codes | Proof required |
|---|---|---|
| Supported | None | A quoted passage that names the concept or an approved synonym |
| Partly supported | S3 overreach, S7 partial, or support only through a related concept | A quoted passage, and the part of the claim it does not cover |
| Not supported: topic absent | S1 | The full-text search record: version read, pages, every term with its hit count, the closest passages, and what the work is about |
| Not supported: misattributed | S4 wrong source, S5 secondhand | A passage showing that the work does not originate the claim, and the likely original source if found |
| Not supported: misdescribed | S2 different finding, S6 wrong method or sample | A passage showing what the work actually found or did |
| Contradicted | S2 when the source finds the opposite | A quoted passage stating the opposite |
| Cannot verify | None | What was tried. The report asks for the PDF |

Rules for the judge:

- **Sharing the topic is not support.** In the survey's evidence, checkers that wrongly passed a citation usually did so because the topic overlapped.
- **A related concept is not a synonym.** A source that only fits a hyperbolic discount function partly supports a sentence about present bias.
- **Equations count.** A source that estimates a present-bias parameter below 1 supports a sentence about present bias even if the phrase never appears.
- **An abstract can never show a topic absent.** It can support or contradict a claim. With only the abstract, a negative verdict becomes cannot verify.

## 8. The checklist

Typical severity is a default. The actual severity depends on the instance.

### 8.1 Format and compliance (FMT)

| ID | Check | How | Typical |
|---|---|---|---|
| FMT-01 | Venue limits: page count, abstract word count, file type, page size | SCRIPT against a venue profile; page-limit, margin and font logic adapted from aclpubcheck | Critical |
| FMT-02 | Anonymization for double-blind review: names, affiliations, acknowledgments, grant numbers, revealing self-citations such as "our previous work [12]", repository links with usernames, PDF and Word metadata author fields | SCRIPT for patterns and metadata, READ for revealing phrasing | Critical |
| FMT-03 | Required statements present: limitations, ethics, data availability, funding, conflicts, venue checklist | SCRIPT for headings, READ for content | Major |
| FMT-04 | Section structure and heading hierarchy: expected sections exist, levels are consistent, no empty sections or lone subsections | SCRIPT, rules reimplemented from TeXtidote's list | Minor |
| FMT-05 | Broken cross-references: "??", "[?]", undefined or duplicate labels, references to sections or appendices that do not exist | SCRIPT | Major |
| FMT-06 | Numbering of figures, tables and equations is sequential; every figure and table is labelled and referenced in the text, near where it appears; no hard-coded numbers | SCRIPT, rules reimplemented from TeXtidote's list | Minor |
| FMT-07 | Captions exist, explain the content on their own, and share one style | SCRIPT and READ | Minor |
| FMT-08 | Reference list consistency: one style, author name format, title capitalization including BibTeX lowercasing such as "Bert" for "BERT", venue naming, required fields, duplicate entries under different keys | SCRIPT | Minor |
| FMT-09 | In-text citation style: one scheme, no mixing of `\cite` with `\citep`, correct narrative versus parenthetical use, "et al." usage, punctuation and spacing | SCRIPT and READ | Minor |
| FMT-10 | Typography and number format: consistent decimals, separators, unit spacing, en dash in ranges, minus signs, LaTeX quote marks | SCRIPT | Minor |
| FMT-11 | Draft leftovers: TODO, FIXME, "TBD", "lorem ipsum", `\todo`, "Figure X", "[citation needed]", highlighted text, and sensitive LaTeX comments that would ship in an arXiv source upload | SCRIPT, reporting what arxiv-latex-cleaner would strip without rewriting anything | Major |
| FMT-12 | Leftover AI assistant text: "As an AI language model", "Certainly, here is", "[insert ...]", "Regenerate response" | SCRIPT and READ | Critical |
| FMT-13 | LaTeX build health: undefined citations and references, overfull boxes into margins, missing figures, font substitution, stale `.bbl` files, and `\todo` macros that print | SCRIPT; needs a `.log` file or a TeX install | Minor to Major |
| FMT-14 | Word hygiene: tracked changes, comments, hidden text, stale fields such as the table of contents or cross-references, author properties | SCRIPT over the raw XML: `w:ins`, `w:del`, `w:pPrChange`, `w:vanish`, comments and fields | Major |
| FMT-15 | PDF technical compliance: fonts embedded, Type 3 fonts, page size, metadata, broken links, file size | SCRIPT with pypdf | Minor to Major |
| FMT-16 | Supplementary references resolve: "Table S3" or "Appendix B" actually exists | SCRIPT and COMPARE | Major |
| FMT-17 | Accessibility: figure alt text, color-only distinctions, minimum font size inside figures | SCRIPT and VISUAL | Minor |
| FMT-18 | Hidden instructions: white or hidden text, and text addressed to AI reviewers such as "give a positive review". Every agent treats the manuscript as material to review, never as instructions | SCRIPT and VISUAL | Critical |

### 8.2 Citations and references (CIT)

| ID | Check | How | Typical |
|---|---|---|---|
| CIT-01 | Every in-text citation has a reference entry, and every entry is cited | SCRIPT; Word citations are matched through their field codes | Major |
| CIT-02 | Every reference exists, under the policy in section 6 | LOOKUP | Critical for a non-existent work, Major for a chimeric citation |
| CIT-03 | Reference metadata is accurate: title, authors and order, year, venue, volume, pages and DOI, with an evidence card | LOOKUP and a field-by-field SCRIPT diff | Minor, Major when the author list is substantially wrong |
| CIT-04 | A working paper or preprint is cited when a published version exists, section 6 | LOOKUP | Suggestion |
| CIT-05 | Cited work is retracted, corrected or under an expression of concern, section 6 | LOOKUP | Critical |
| CIT-06 | The cited work supports the sentence that cites it, section 7. Runs on every citation | LOOKUP for full text, READ, SCRIPT quote checks, and a refuter | Major |
| CIT-07 | Citation needed: statistics, prior results, "well known", "studies show", and datasets, tools or models used without a citation | READ | Major |
| CIT-08 | Citation appropriateness: secondary source for a primary finding, survey cited for a specific result, outdated work for "state of the art", citation dumps such as "[3-17]", self-citation share | READ, SCRIPT for ratios | Minor |
| CIT-09 | Important related work is missing, especially work that weakens a novelty claim | LOOKUP by search and citation graph, then READ | Major |
| CIT-10 | Age and balance of the reference list against field norms | SCRIPT | Suggestion |
| CIT-11 | Datasets, code, pretrained models and tools used are cited, with version and license where required | READ and SCRIPT | Minor to Major |
| CIT-12 | URLs and DOIs resolve; dead links get an archived alternative | LOOKUP | Minor |
| CIT-13 | Direct quotations match the source word for word and carry page numbers when the style requires | LOOKUP and SCRIPT | Major |
| CIT-14 | Replication status: cited findings that failed to replicate, or replicated with smaller effects, are reported with the replication's own label and quote, section 6 | LOOKUP | Major when the paper relies on the finding without saying so |

### 8.3 Numbers inside the paper (NUM)

| ID | Check | How | Typical |
|---|---|---|---|
| NUM-01 | The same quantity is reported identically in the abstract, introduction, results, tables, figures and conclusion | SCRIPT extraction, then COMPARE | Major |
| NUM-02 | Arithmetic is right: differences, relative versus absolute changes, sums, means, percentages that should total 100, table totals | SCRIPT | Major |
| NUM-03 | Statistics are internally consistent. For regression tables: widen each coefficient and standard error by half a unit in their last decimal, compute the implied range of t and p, read the star thresholds from the table note, and flag only when the whole range falls outside the interval the stars imply. A flag is strong when the 5% conclusion flips, and needs human judgment when the degrees-of-freedom assumption decides it, as with few clusters. Also check confidence intervals against b ± 1.96·SE and N across tables. For results in the text: statcheck-style patterns extended to t, F, z, chi-square with N, Mann-Whitney and "(p < 0.05)" | SCRIPT, rebuilt from the published DORIS method | Major. Target false discovery rate: 1.2% or lower |
| NUM-04 | GRIM, DEBIT and standard-deviation bounds: means, shares and standard deviations of integer or binary data are possible for the stated N. GRIMMER only as a cautious flag | SCRIPT, reimplemented from the methods in scrutiny | Major, flagged cautiously |
| NUM-05 | Counts add up: participant flow, sample splits, N in tables against N in text | SCRIPT and COMPARE | Major |
| NUM-06 | Text, tables and figures agree, including stated trends; every estimate quoted in the text appears in some table or figure; values marked as best really are best | SCRIPT for tables, VISUAL for figures | Major |
| NUM-07 | Units, magnitudes and precision: units present and consistent, conversions correct, magnitudes plausible, no false precision such as 87.2341% | SCRIPT and READ | Minor |
| NUM-08 | "Significant" is used only with a statistical test, and gains within the reported uncertainty are not claimed as effects | COMPARE and READ | Major |
| NUM-09 | Percent and percentage points, and log outcomes. A rise from 20% to 25% is 5 percentage points or 25%. A coefficient of 0.50 on a log outcome implies a 64.9% change, not 50% | SCRIPT | Major |

### 8.4 Facts about the outside world (FACT)

| ID | Check | How | Typical |
|---|---|---|---|
| FACT-01 | External factual claims such as dates, definitions, history and population statistics. Verdict: verified, contradicted, outdated, or unverifiable | LOOKUP: split claims into atomic facts, search, and verify against retrieved evidence, after SAFE and VeriScore | Major when contradicted |
| FACT-02 | What the paper says other papers did or found matches those papers | LOOKUP and READ, through the citation support module | Major |
| FACT-03 | Baseline numbers copied from other papers match the source table and setting, in the version read | LOOKUP and COMPARE | Major |
| FACT-04 | Names of people, methods, datasets, organizations and software are spelled correctly and consistently | SCRIPT and LOOKUP | Minor |
| FACT-05 | Time-sensitive statements such as "recently", "the latest model" or "no current work" are not stale | READ and LOOKUP | Minor |
| FACT-06 | Priority claims such as "first", "only", "novel" or "no prior work" survive a literature search. The best verdict possible is "no contrary evidence in N searches", never "verified novel" | LOOKUP and READ | Major, Critical if clearly false |

### 8.5 Logic and argument (LOG)

| ID | Check | How | Typical |
|---|---|---|---|
| LOG-01 | Claim-evidence map: every contribution and conclusion links to evidence in the paper; unsupported claims are flagged. The map is included in the report | READ | Major |
| LOG-02 | Overclaiming: conclusions broader than the evidence, "prove" for suggestive results, "state of the art" with partial comparisons, generalizing from one sample | READ and COMPARE | Major |
| LOG-03 | Causal language such as "leads to" or "because" drawn from correlational or observational evidence; confounders not addressed | READ | Major |
| LOG-04 | Internal contradictions, for example 12 sessions in the design section and 10 in the appendix | COMPARE | Major |
| LOG-05 | Hidden or unjustified assumptions, and missing scope conditions | READ | Minor to Major |
| LOG-06 | Reasoning fallacies: circularity, false dichotomy, hasty generalization, cherry-picked outcomes or samples, survivorship bias, ecological fallacy, base-rate neglect, Simpson's paradox risk | READ | Minor to Major |
| LOG-07 | Mathematical correctness: definitions before use, each derivation step follows, theorem conditions match how the proof uses them, quantifiers and edge cases, dimensional consistency. Defaults to needs human judgment unless computed | READ, SCRIPT with sympy for algebra spot checks | Major to Critical |
| LOG-08 | Design validity: the identification strategy and its assumptions, comparison groups, confounds, and reported uncertainty; for computational work, fair baselines and no leakage. Defaults to needs human judgment | READ | Major |
| LOG-09 | Interpretation errors: a non-significant result read as "no effect", p-values read as the probability a hypothesis is true, results described differently than they appear | READ and COMPARE | Major |
| LOG-10 | Plausible alternative explanations for the main result are considered | READ | Minor to Major |
| LOG-11 | The limitations section covers the real weaknesses found by other checks and does not contradict claims made elsewhere | COMPARE and READ | Minor |

### 8.6 Coherence and structure (COH)

| ID | Check | How | Typical |
|---|---|---|---|
| COH-01 | The thread from problem to research question, contributions, design, results and conclusions holds; every contribution is delivered and evaluated; every analysis answers a stated question | READ | Major |
| COH-02 | Abstract fidelity: every claim and number in the abstract appears in the body and matches it | COMPARE | Major |
| COH-03 | Forward references such as "we show in Section 5 that ..." are fulfilled at that location | COMPARE | Minor to Major |
| COH-04 | The conclusion adds no new results and summarizes the results correctly | COMPARE | Minor |
| COH-05 | Terminology: one name per concept, no drift between names for the same thing, terms defined before use | SCRIPT for variants, then READ | Minor |
| COH-06 | Notation: every symbol defined, used consistently, not overloaded, and the same in text, equations and figures | SCRIPT symbol inventory, then READ | Minor to Major |
| COH-07 | Abbreviations defined at first use in the abstract and again in the body, defined once, and actually used after definition | SCRIPT | Minor |
| COH-08 | Paragraph and section flow: each paragraph makes one point, transitions connect, the order is logical | READ | Minor |
| COH-09 | Substantially repeated passages across sections | SCRIPT similarity, then READ | Minor |
| COH-10 | The title and keywords fit the content and scope | READ | Minor |
| COH-11 | Related work says how this paper differs, rather than only listing papers | READ | Minor to Major |
| COH-12 | Each figure and table supports a point in the text, and the text says what to see in it | READ | Minor |

### 8.7 Language and clarity (LANG)

| ID | Check | How | Typical |
|---|---|---|---|
| LANG-01 | Spelling, grammar and punctuation; one language variant such as US or UK throughout | SCRIPT for variant words, then READ | Minor |
| LANG-02 | Clarity: overlong sentences, ambiguous "this" or "it", dangling modifiers, deep nesting | SCRIPT for length, then READ | Minor |
| LANG-03 | Hedging matches the strength of the evidence, linked to LOG-02 | READ | Minor |
| LANG-04 | Vague or loaded words such as "clearly", "obviously" and "groundbreaking". "Significantly" is flagged only when no statistical test is nearby, because it is a technical term in economics | SCRIPT word list, then READ | Minor |
| LANG-05 | Tense and voice follow section conventions | READ | Suggestion |
| LANG-06 | Readability for the target audience: jargon explained, acronym density | SCRIPT metrics, then READ | Suggestion |
| LANG-07 | Inclusive and bias-free language | SCRIPT word list, then READ | Minor |
| LANG-08 | Wordiness and filler | SCRIPT, then READ | Suggestion |

### 8.8 Methods, data and reproducibility (MTH)

These checks verify that the paper reports what a replicator needs. They do not try to reproduce results.

| ID | Check | How | Typical |
|---|---|---|---|
| MTH-01 | Enough detail to reproduce the analysis: data sources, sample construction, variable definitions, estimation methods and software, specifications | READ against a list | Major |
| MTH-02 | Data description: source, collection, size, inclusion and exclusion criteria, cleaning, known biases, license | READ | Major |
| MTH-03 | Code and data availability statements name the access conditions and a trusted repository, with working links | SCRIPT and LOOKUP | Minor to Major |
| MTH-04 | Statistical methods: tests named, assumptions checked, effect sizes and intervals reported, sample size justified | READ | Major |
| MTH-05 | Analysis protocol: the main specification is identified, robustness checks are reported, and any specification search is disclosed | READ | Major |
| MTH-06 | Reporting guideline for the study type. No CONSORT-style checklist exists for economics, so economics papers use the composite checklist in the BEH module. Biomedical guidelines such as CONSORT or PRISMA apply only to papers of that type | READ against the loaded guideline file | Major |
| MTH-07 | Preregistration and plan deviations, covered in detail by BEH-06 and BEH-07 | READ and LOOKUP | Minor to Major |

### 8.9 Ethics, integrity and disclosures (ETH)

| ID | Check | How | Typical |
|---|---|---|---|
| ETH-01 | Human or animal research: ethics approval, consent, participant compensation | READ | Major to Critical |
| ETH-02 | Conflict of interest and funding statements where required | SCRIPT and READ | Major |
| ETH-03 | Author contribution statement where required | SCRIPT | Minor |
| ETH-04 | Personal data in examples, figures, screenshots or supplements | READ and VISUAL | Critical |
| ETH-05 | AI-use disclosure where the venue requires it | SCRIPT and READ | Minor to Major |
| ETH-06 | Verbatim overlap with cited abstracts or prior papers the user supplies. Limited: no plagiarism database | LOOKUP and SCRIPT n-gram overlap | Major |
| ETH-07 | Duplicated or near-duplicate image panels within the paper. Limited: not full image forensics | SCRIPT with ImageHash, then VISUAL | Major |
| ETH-08 | Broader impact, dual-use and risk statements where the venue or topic requires | READ | Minor to Major |

### 8.10 Figures and tables (FIG)

| ID | Check | How | Typical |
|---|---|---|---|
| FIG-01 | Legibility: font size against body text, resolution, axis labels, units, legends, grayscale printing | VISUAL | Minor |
| FIG-02 | Honest presentation: truncated or broken axes, mismatched scales across compared panels, error bars present and defined as SD, SE or CI | VISUAL and READ | Minor to Major |
| FIG-03 | Color accessibility: color-only encoding, red-green contrasts | VISUAL | Minor |
| FIG-04 | Table hygiene: units in headers, consistent decimals, star legend present, symbols explained | SCRIPT and READ | Minor |
| FIG-05 | Consistent styling across figures, such as the same color for the same treatment everywhere | VISUAL | Suggestion |
| FIG-06 | Caption, figure and text agree; legend labels match the names used in the text | VISUAL and COMPARE | Minor to Major |

### 8.11 Contribution and reviewer view (REV)

| ID | Check | How | Typical |
|---|---|---|---|
| REV-01 | Contributions are stated clearly and specifically, usually at the end of the introduction | READ | Minor |
| REV-02 | Novelty holds up against the searches from FACT-06 and CIT-09 | LOOKUP and READ | Major |
| REV-03 | The paper argues why the result matters | READ | Suggestion |
| REV-04 | Simulated reviews: two or three independent reviewer personas list likely objections and questions, each tied to a quote. Its redesign is deferred, see section 16 | READ | Suggestion |

### 8.12 Behavioral economics module (BEH)

Rebuilt from journal and data-editor policies, as the survey recommended. Each rule's source is in section 17. Venue-specific rules take their severity from the venue profile.

| ID | Check | How | Typical |
|---|---|---|---|
| BEH-01 | Deception: giving participants false information counts as deception. Withholding information is a gray area and needs human judgment | READ | Critical where banned, as at Experimental Economics; Major elsewhere unless justified. The Journal of the Economic Science Association follows the ESA guidelines, which ask authors to avoid deception if at all possible and to consult the editors |
| BEH-02 | Incentives: participants are paid, the payment mechanism is described and incentive compatible, and show-up fee, average earnings and session length are reported | READ | Major |
| BEH-03 | Materials: full instructions in an appendix, translations where relevant, screenshots, and the experiment files such as z-Tree, oTree or Qualtrics in the replication package. For ReStud, a reference to an online appendix is not enough | READ | Major |
| BEH-04 | Comprehension and attention checks are described, with exclusion rules stated in advance. On Prolific, a participant in a study of five minutes or more can be rejected only after failing at least two attention checks | READ | Major |
| BEH-05 | Matching protocol and independent units: partner or stranger matching is described, and inference uses the number of independent units, such as sessions or matching groups | READ | Major |
| BEH-06 | Registration: field RCTs in AEA journals are registered in the AEA RCT Registry, with the `AEARCTR-` ID in the title footnote and the references. Lab experiments are exempt. Registration only on OSF or AsPredicted is a warning under the AEA Data Editor's template | SCRIPT for IDs, LOOKUP and READ | Major |
| BEH-07 | Plan comparison: when a pre-analysis plan is available, primary outcomes, sample and specifications match it, and deviations are labelled. Registration alone, without a plan, did not reduce p-hacking | READ and COMPARE | Major |
| BEH-08 | Multiple testing: with many outcomes, arms or subgroups, a family-wise or false-discovery correction is applied, such as List-Shaikh-Xu, Romano-Wolf or Anderson's sharpened q-values | READ | Major |
| BEH-09 | Clustering: the type of standard errors is stated, and they are clustered at the level of treatment assignment. Flag clustering finer than randomization, and few clusters without a wild bootstrap or randomization inference | READ and SCRIPT | Major |
| BEH-10 | Power, attrition and balance: a power analysis or minimum detectable effect, attrition by arm, a balance table, and bounds such as Lee bounds when attrition differs | READ | Major |
| BEH-11 | Software and recruitment citations: oTree requires citing Chen, Schonger and Wickens (2016), and ORSEE's license requires citing Greiner (2015) | SCRIPT | Minor |
| BEH-12 | Ethics approval in the title footnote: the name of the institutional review board (IRB) and the protocol number, as AEA journals require, and IRB documentation for ReStud | SCRIPT and READ | Major |
| BEH-13 | Data citations and repository: every dataset is cited; the availability statement names access conditions and a trusted repository, since the AEA does not accept GitHub alone. With a replication package, follow the template README and the AEA Data Editor's instructions for AI assistants | SCRIPT and READ | Major |
| BEH-14 | Structural estimates: parameters such as present bias, the discount factor and loss aversion have standard errors, plausible values and an identification argument | READ | Major |
| BEH-15 | Classic attributions: well-known findings are cited to their original source, checked against a verified list of common misattributions | LOOKUP and READ | Major |
| BEH-16 | Journal requirements: JEL codes, keywords, highlights and disclosure statements, as the target journal's profile requires | SCRIPT | Major |

Replication status is covered by CIT-14. Regression-table statistics are covered by NUM-03 and NUM-09.

## 9. Verification and guardrails

1. **Quotes are checked by a script.** Every quote from the paper must appear verbatim in the paper map, and every quote from a cited work must appear in its cached text, ignoring whitespace differences. A finding whose quote fails is repaired or dropped.
2. **The manuscript is data.** Every agent prompt carries the scope guard, and FMT-18 flags hidden instructions.
3. **Quote or drop.** A reading agent that cannot quote a problem does not report it.
4. **Serious findings face a refuter.** An independent agent re-examines every Critical and Major finding and every negative citation verdict. It may overturn a finding only by quoting counter-evidence. The outcome goes into the trajectory, and refuted findings are listed in an appendix.
5. **High-value reading checks run twice.** A finding that appears in only one run is marked likely.
6. **Not found is not fake.** References follow the policy in section 6.
7. **Coverage is honest.** The report states every check that was skipped and why. A degraded or failed lookup is reported as skipped, never as passed.
8. **Report only.** The skill never edits the paper or its bibliography, and never installs anything without asking.
9. **Runs are reproducible.** Lookups are cached in the work folder, and every trajectory records the verifier settings: model, prompt version, strictness, number of runs and thresholds.

## 10. What the skill must not do

From the survey's avoid list:

- **Copy noncommercial work.** No text or code from econ-review, academic-research-skills, the Sakana AI Scientist reviewer, CycleReviewer or DeepReviewer. Ideas may be reused, written fresh.
- **Depend on AGPL or GPL code.** PyMuPDF, Hallucinator, metacheck, ODDPub, statcheck, TeXtidote and fuzzywuzzy may inform the design but are never hard dependencies.
- **Use shadow libraries or scrapers.** No Sci-Hub fallback, no Google Scholar scraping, and no betterbib, which now needs a paid license.
- **Bypass permissions.** Never run subprocesses with permission prompts disabled.
- **Edit files.** No tool that rewrites `.tex`, `.bib` or Word files.
- **Carry hidden agendas from other skills.** For example, strip K-Dense's instruction to cite K-Dense in the user's paper from anything adapted.
- **Change the user's setup.** No installers that modify `~/.claude`.
- **Send drafts away without consent.** No cloud or GPU parsers by default, and no MinerU skill.
- **Guess authorship.** No AI-text detection.
- **Score with personas or debate.** No persona scores, no multi-agent debate, and no p-curve on a single paper.

## 11. Report format

### Files

Written to an output folder next to the paper:

- `paper-check-report.md` for people.
- `paper-check-findings.json` for agents. It holds the same findings with the same IDs, plus the reference evidence cards.
- `paper-check-work/` with the paper map, source digests, script outputs, lookup cache and image crops. This is the proof trail.

### Report sections

1. **Header.** Paper title, input files, mode, date, venue profile.
2. **Summary.** Counts by severity and dimension, and the top five issues.
3. **Findings.** Critical first, then Major, Minor and Suggestion. Within a level, findings follow the order of the paper. An index lists every finding in paper order, for writers fixing the draft from top to bottom.
4. **Coverage.** Every check ID with its outcome: run, not applicable, or skipped with the reason.
5. **Appendices.** Reference table with an evidence card per reference; citation support table with one row per citation and a per-section summary; claim-evidence map; numeric consistency table; refuted findings.

### One finding

```markdown
### F-012 · Major · NUM-01 Numbers consistent across sections
Status: confirmed · Confidence: high
Where: Abstract, sentence 4 (main.tex:18); Table 3 (results.tex:102)

> "reduces default rates by 23% compared with the control group"

Problem: Table 3 reports a default rate of 8.1% under treatment and 9.9% in
the control group. That is an 18% reduction, not 23%.

Proof:
- Table 3, row "Treatment": 8.1 (results.tex:102)
- Table 3, row "Control": 9.9 (results.tex:104)
- Computed result: (9.9 - 8.1) / 9.9 = 18.2%

Trajectory:
1. check_numbers.py extracted 41 numeric claims; this one is tagged "default rate, relative".
2. Matched to Table 3 by outcome name and arm.
3. Recomputed the reduction: 18.2%.
4. Searched every table and the appendix for 23%: no match.
5. Refuter tried other arms, tables and the appendix: not refuted.
Verifier settings: prompt v0.4, strictness standard, 2 runs, both found it.

Suggested fix: replace "23%" with "18%", or update Table 3 if the table is stale.
Resolved when: the abstract and Table 3 imply the same reduction.
```

### JSON fields for each finding

| Field | Content |
|---|---|
| `id`, `check_id`, `dimension` | Finding ID such as F-012, checklist ID such as NUM-01, dimension name |
| `severity`, `confidence`, `status` | As defined in section 5 |
| `locations` | List of anchors: file and line, or page and line, or paragraph, plus section path |
| `quote`, `related_quotes` | Verbatim text from the paper |
| `problem` | One or two sentences |
| `evidence` | Typed items. `quote` and `source_quote` hold verbatim text. `computed_result` records the inputs, tool, tolerance and output. `checked_absence` records the scope searched, the terms and the hit counts. `lookup_record` and `image` hold the rest, with source URLs |
| `trajectory` | Ordered steps, the verifier settings, the refuter outcome and the run agreement |
| `fix` | Action: replace, insert, delete or investigate. For replace, the exact original and replacement text. `resolved_when` states the condition that shows the fix worked |

## 12. Modes and configuration

| Mode | What runs | Use it for |
|---|---|---|
| quick | Script checks, reference existence, abstract fidelity | A fast pass while writing |
| standard | Everything except deep reads of cited works and simulated reviews. Fact checks cover the abstract, contributions, conclusions and numbers attributed to other papers | Normal pre-submission check |
| deep (default) | Every check. Citation support for every citation, fact check of every external claim, related-work search, simulated reviewers | Any check where quality matters, which is the default |

### Venue profiles

A venue profile is a small file holding one journal's submission rules. Without one, the skill checks general quality only. With one, it also checks the rules that journal enforces. A missing required part or an exceeded limit can get a paper returned before review.

A profile records, with the source URL and the date it was checked:

- **Limits:** abstract length, word or page limits, and the number of keywords or highlights.
- **Required parts:** JEL codes, keywords, highlights, disclosure statements, data availability statement, ethics approval, registration ID.
- **Review type:** double-blind or single-blind, which decides whether anonymization is checked.
- **Style:** citation style such as AEA author-date, heading and table conventions.
- **Policies:** data and code requirements, deception rules for experiments, and AI-use disclosure.

A style guide is the writing and citation part of a profile, such as the AEA style or APA 7. Several journals can share one style guide. Each profile is built from the journal's current author guidelines and rechecked before use, because journals change their rules. Profiles live in `.claude/skills/paper-check/references/venues/`, one YAML file per journal. Every confirmed rule carries a verbatim quote from its source, and `tools/validate_venues.py --verify-quotes` re-fetches each source to find each quote.

The first set covers the top journals for behavioral economics:

| Group | Journals |
|---|---|
| General, top five | American Economic Review; Quarterly Journal of Economics; Journal of Political Economy; Econometrica; Review of Economic Studies |
| General | AER: Insights; AEJ: Applied Economics; AEJ: Economic Policy; AEJ: Microeconomics; Journal of the European Economic Association; Economic Journal; Review of Economics and Statistics |
| Field | Journal of Economic Behavior & Organization; Experimental Economics; Journal of the Economic Science Association; Games and Economic Behavior; Management Science; Journal of Risk and Uncertainty; Journal of Behavioral and Experimental Economics; Journal of Economic Psychology; Behavioural Public Policy |

### Settings for each paper

Settings come from the request or from a `paper-check.yaml` beside the paper:

- **venue**: a venue profile.
- **field and study type**: these switch on the relevant guidelines and statistics depth.
- **language variant**: US or UK English.
- **mode**: quick, standard or deep. The default is deep.
- **network**: on or off. With it off, lookup checks are reported as skipped, not passed.
- **sources folder**: a folder of PDFs of the cited works, read first. By default it is `sources/` beside the paper. File names do not matter: the skill matches each PDF to a reference by the DOI or title in its text, and reports PDFs it could not match and references that have no PDF.
- **paid PDFs**: whether OpenAlex's paid PDF service may be used. Off by default.
- **output folder** and **minimum severity** to include.

### Credentials

Keys and the contact email live in `~/.paper-check/config.yaml`, outside any repository and outside the paper's folder: the Crossref and Unpaywall contact email, the OpenAlex key, the Semantic Scholar key, and RePEc access once granted. A file is used instead of environment variables because, according to the survey, the desktop app on macOS does not see variables exported in a shell profile.

## 13. Evaluation

The evaluation sets come before any tuning. `evals/README.md` describes them:

- **The case-study section** is not available, so the seeded citation errors reproduce its pattern instead.
- **Seeded citation errors:** clean literature-review paragraphs with swapped citations that create known S1, S2 and S4 errors.
- **Attributed propositions:** 50 to 100 from real behavioral drafts, about a third of them correct, each labelled by two people.
- **Reference sets:** published benchmarks of planted fake references, plus an economics set of working papers, published versions and chimeric citations.
- **Perturbation set:** clean drafts with injected errors for the reading and number checks.
- **Misattribution set:** classic findings with their original sources, each confirmed against the original paper.

Each check is measured by precision, recall, false accepts and false rejects, and by run-to-run agreement. The skill is also measured by the time a coauthor needs to confirm or dismiss each finding.

## 14. Known limits

- **Plagiarism.** There is no access to commercial plagiarism databases, so overlap checks only cover open sources the skill can fetch.
- **Image forensics.** Only duplicate panels within the paper are detected.
- **Paywalled sources.** Without the full text, a citation can be supported or contradicted from its abstract, but never shown unsupported. The report asks for the PDF.
- **PDF extraction.** Math, tables and two-column layouts can extract imperfectly. LaTeX source gives the best results, and supplying source plus PDF is better still.
- **Deep errors.** Mathematical review and design validity default to needs human judgment.
- **Network and keys.** Lookups need internet access, a Semantic Scholar key, an OpenAlex key and a contact email. `docs/network-setup.md` explains the settings, and `tools/check_network.py` tests them. RePEc linking waits on API access.
- **Local dependencies.** The scripts need Python 3 and the packages in section 3.

## 15. Skill layout and sharing

```
.claude/skills/paper-check/
  SKILL.md                 orchestration, kept under 500 lines
  requirements.txt         the permissive core from section 3
  THIRD_PARTY_NOTICES.md   licenses of adapted prompts and rules
  references/
    checklist.md           section 8 of this document
    report-format.md       section 11
    reference-policy.md    section 6
    citation-support.md    section 7
    dimensions/            one prompt per reading agent, adapted with attribution
    venues/                one dated profile per journal
    guidelines/            the economics composite checklist
  scripts/
    ingest.py              LaTeX, PDF or Word into the paper map
    lookups/               one client per service, with cache and backoff
    check_format.py
    check_references.py
    citation_support.py
    check_numbers.py       regression tables, GRIM, DEBIT, percentage points
    verify_quotes.py
    build_report.py
evals/                     at the repository root, see evals/README.md
```

The skill lives in the shared GitHub repository. Your coworker opens that repository in Claude Code desktop and can use the skill at once, change it, and send changes back by pull request. To use it in every project, they can also copy the folder into `~/.claude/skills/`. The Retraction Watch file, FReD and the STW thesaurus are downloaded on first use and cached, not committed.

## 16. Deferred recommendations (P2)

- **Reviewer personas.** Run REV-04 as two or three independent personas, such as a methodologist, a behavioral field expert and a skeptic. Each reads an anonymized paper map and never sees the others' output. Objections are tied to quotes, with no scores, and a table shows which objections recur.
- **Optional accelerators.** Probe for GROBID, Camelot, pandoc, Vale, proselint, a LanguageTool server, arxiv-mcp-server and zotero-mcp. Use them when present, report "skipped: tool missing" otherwise, and never install anything silently.
- **Packaging.** Ship as a project skill plus a one-plugin `marketplace.json`. Keep the frontmatter to the Agent Skills fields, pre-approve the exact script commands, and quote every path, since drafts often sit in folders with spaces.

## 17. Sources for adopted rules

Gathered by the survey on 2026-10-17. Recheck each source when implementing the rule that depends on it.

**Prompts and reference rules, all MIT-licensed**

- Claes Bäckman, AI-research-feedback: https://github.com/claesbackman/AI-research-feedback
- OpenAIReview: https://github.com/ChicagoHAI/OpenAIReview
- RefChecker: https://github.com/markrussinovich/refchecker
- bib-check-agent: https://github.com/nnicholas-c/bib-check-agent
- citecheck: https://github.com/sunami-lab/citecheck
- cite-verify, for NBER DOI handling: https://github.com/jonckr/cite-verify
- Crossref search-based matcher: https://gitlab.com/crossref/search_based_reference_matcher
- Crossref preprint matcher: https://gitlab.com/crossref/data-science/matching-tools
- aclpubcheck: https://github.com/acl-org/aclpubcheck
- chgagne's research skills: https://github.com/chgagne/claude-skills-research

**Rule lists and methods to reimplement**

- TeXtidote's rule list, GPL-3, rules only: https://github.com/sylvainhalle/textidote
- scrutiny, for GRIM and DEBIT: https://github.com/lhdjung/scrutiny
- DORIS, the star-check method: https://documentserver.uhasselt.be/handle/1942/42667
- Pütz and Bruns on star errors in economics: https://ideas.repec.org/a/bla/jecsur/v35y2021i1p348-373.html

**Lookup services and data**

- Crossref rate limits: https://community.crossref.org/t/announcing-changes-to-rest-api-rate-limits-crossref/14726
- OpenAlex changelog: https://help.openalex.org/hc/en-us/articles/38868153578263-Changelog
- OpenAlex location versions: https://docs.openalex.org/api-entities/works/work-object/location-object
- Semantic Scholar API release notes: https://github.com/allenai/s2-folks/blob/HEAD/API_RELEASE_NOTES.md
- RePEc IDEAS API: https://ideas.repec.org/api.html
- Retraction Watch data: https://gitlab.com/crossref/retraction-watch-data
- FORRT Replication Database: https://github.com/forrtproject/FReD
- STW Thesaurus for Economics, CC BY 4.0 since version 9.20 (earlier versions ODbL): https://www.zbw.eu/stw/version/latest/download/about.en.html

**Behavioral economics policies**

- Experimental Economics, no deception and incentivized participants: https://www.cambridge.org/core/journals/experimental-economics/information/about-this-journal
- What counts as deception: https://www.cambridge.org/core/journals/experimental-economics/article/what-is-considered-deception-in-experimental-economics/B92D3DCAA5CDAB1357D49B7443244E50
- AEA policy for experimental papers: https://www.aeaweb.org/journals/data/policy-experimental
- AEA RCT Registry policy: https://www.aeaweb.org/journals/policies/rct-registry
- AEA Data Editor compliance list, including the IRB footnote: https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_data/DCAS-compliance-v1.csv
- AEA replication report template: https://github.com/AEADataEditor/replication-template/blob/HEAD/REPLICATION.md
- AEA guidance for AI assistants reviewing replication packages: https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/preparing-replication-package.md
- AEA on GitHub as an archive: https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_posts/2026-01-19-preparing-pandp-replication-packages.md
- Data and Code Availability Standard rules: https://github.com/social-science-data-editors/DCAS/blob/HEAD/_data/rules.csv
- Template README: https://github.com/social-science-data-editors/template_README/blob/HEAD/template-README.md
- ReStud data policy: https://github.com/restud/data-editor/blob/HEAD/policy.md
- Prolific attention-check policy: https://researcher-help.prolific.com/en/articles/445153-prolific-s-attention-and-comprehension-check-policy
- oTree citation requirement: https://github.com/oTree-org/otree-docs/blob/HEAD/source/install.rst
- ORSEE citation requirement: https://github.com/orsee/orsee/blob/HEAD/README.md
- Pre-analysis plans and p-hacking, Brodeur et al.: https://www.iza.org/publications/dp/15476
- List, Shaikh and Xu on multiple testing: https://ideas.repec.org/a/kap/expeco/v22y2019i4d10.1007_s10683-018-09597-5.html
- Abadie, Athey, Imbens and Wooldridge on clustering: https://arxiv.org/abs/1710.02926
- Young on randomization inference: https://ideas.repec.org/a/oup/qjecon/v134y2019i2p557-598..html

## 18. Open questions

1. Is the journal list in section 12 right? Add or remove any.
2. Should OpenAlex's paid PDF service ever be used? It stays off unless you say so.
3. When can you share two or three real drafts, ideally with known problems and in different formats?
