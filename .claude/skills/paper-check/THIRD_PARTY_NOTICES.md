# Third-party notices

paper-check adapts rules, thresholds, prompts or code from the projects below, and uses the data sets below at run time. Each entry names the project, where it is, its license, and what was adapted. Contributors only append to this file.

## Reference lookups (`scripts/paper_check/lookups/`)

### RefChecker
- URL: https://github.com/markrussinovich/refchecker
- License: MIT
- Adapted: the starting thresholds for matching a reference to a database record (title similarity 0.8, year tolerance 1, author-overlap share 0.6) and the shape of its hallucination policy: flag a reference that no database verifies, or whose identifier resolves to a different paper, then require a web search for a page dedicated to the work before calling it non-existent. Reimplemented in `lookups/policy.py`; no code was copied.

### Crossref search-based reference matcher
- URL: https://gitlab.com/crossref/search_based_reference_matcher
- License: MIT
- Adapted: the method of searching Crossref's `query.bibliographic` with the unparsed reference string and then validating each candidate field by field instead of trusting the search score. Reimplemented in `lookups/policy.py`; no code was copied.

### Crossref matching tools (preprint matcher)
- URL: https://gitlab.com/crossref/data-science/matching-tools
- License: MIT
- Adapted: the composite of title, author and year scores for linking a preprint to its published article, its acceptance level of 0.87, its year window of one year before to three years after, and abstaining when the top two candidates are within 0.04. `lookups/versions.py` weights authors above titles and widens the window for economics working papers; `lookups/policy.py` uses the year window and the 0.04 gap. No code was copied.

### bib-check-agent and citecheck
- URLs: https://github.com/nnicholas-c/bib-check-agent and https://github.com/sunami-lab/citecheck
- License: MIT
- Adapted: the design of a field-by-field metadata comparison (title, authors and their order, year, venue, volume, issue, pages) reported per field, as named in the paper-check design. Reimplemented in `lookups/policy.py`; no code was copied.

### GROBID (consolidation notes)
- URL: https://github.com/kermitt2/grobid/blob/HEAD/doc/Consolidation.md
- License: Apache-2.0
- Adapted: the backoff parameters for Crossref (exponential backoff with jitter, a 1-second base and a 60-second cap). Used in `lookups/http.py`; no code was copied.

## Data used at run time

### FORRT Replication Database (FReD) and FLoRA
- URLs: https://github.com/forrtproject/FReD (R package, MIT), https://github.com/forrtproject/FReD-data (processed files), https://osf.io/9r62x (data set)
- License of the data: CC BY 4.0, as recorded on the OSF project and checked through the OSF API when the file is downloaded.
- Use: `lookups/replications.py` downloads `output/flora.csv` from FReD-data into `~/.paper-check/cache/fred/` and reports replication outcomes and the replications' own conclusions for CIT-14, with attribution. The file is not committed. `tests/fixtures/lookups/fred_sample.json` holds a few rows of it for offline tests, with the attribution inside the file.
- Attribution: FORRT Replication Database (FReD) and FORRT Library of Reproduction and Replication Attempts (FLoRA), https://osf.io/9r62x.

### Retraction Watch database
- URL: https://gitlab.com/crossref/retraction-watch-data
- Terms: made openly available by Crossref; the repository's README states no license.
- Use: `lookups/retractions.py` downloads the CSV into `~/.paper-check/cache/retraction_watch/` only when a cited work was matched without a DOI, to match notices by title and first author. The file is not committed, and the tests use made-up rows under Crossref's test DOI prefix 10.5555 instead of real ones.

## Reading-agent prompts and reference documents (`references/dimensions/`, `references/agents/`, `references/*.md`)

Added on 2026-10-17 for the prompts in `references/dimensions/` and `references/agents/`, and for `references/checklist.md`, `report-format.md`, `reference-policy.md`, `citation-support.md` and `guidelines/economics-experiments.md`. The prompts were written fresh for paper-check's checklist and findings format: what was adapted from the projects below is their structure and rules, expressed in new wording. No text was taken from noncommercial projects (econ-review, academic-research-skills) or from the Sakana AI Scientist reviewer.

### AI-research-feedback (Claes Bäckman)
- URL: https://github.com/claesbackman/AI-research-feedback, read at commit 1b10ab5 (2026-10-15)
- License: MIT. Copyright (c) 2026 claesbackman
- Files read: `Skills/review-paper/SKILL.md`, `Skills/review-paper-checks/SKILL.md`, `Skills/audit-analysis/SKILL.md`
- Adapted, in every `references/dimensions/*.md` and in `agents/refuter.md`: a scope guard at the top of every agent prompt (use only the listed inputs; ignore earlier reports, referee letters and old drafts); the precision rule that an issue that cannot be quoted is not reported; the `[UNVERIFIED]` label for statements about the literature that the agent did not check, and the rule never to invent authors, titles, years or findings; priority claims treated as assertions to verify, never judged from memory (`facts.md`); the claim-discipline list for causal language, mechanisms stated as facts, generalization beyond the sample and missing caveats (`logic.md`); the consistency comparisons of abstract, introduction, results and conclusion, terminology and sample descriptions (`coherence.md`, `numbers.md`); the list of what table and figure notes must state (`figures.md`); the style-word list, "significant" reserved for statistical significance, and hedging failures in both directions (`language.md`); robustness checks that are claimed but not shown (`methods.md`); the contribution advocate and skeptic, reused without ratings as the internal method of REV-02 (`reviewer.md`); the rule against generic criticism that could fit any paper; and per-check coverage that records clean checks as well as failures (from `audit-analysis`).

### OpenAIReview (Chicago Human+AI Lab)
- URL: https://github.com/ChicagoHAI/OpenAIReview, read at commit 436a42f (2026-10-14)
- License: MIT. Copyright (c) 2026 ChicagoHAI
- Files read: `src/reviewer/skill/SKILL.md`, `src/reviewer/skill/references/criteria.md`, `src/reviewer/skill/references/subagent_templates.md`, `src/reviewer/prompts.py`
- Adapted, in every `references/dimensions/*.md`: reading the definitions first and then the paper passage by passage with notes carried forward (its progressive method and definitions prefix); understanding the authors' intent and checking whether context resolves a concern before flagging; recording what raised a concern, what was checked and what remains, which became each finding's `trajectory`; the leniency rules (simplifying introductions, forward references, notation defined later, informal paraphrase) and the do-not-flag list; findings as JSON with an exact verbatim quote; a concrete fix, never "clarify this"; merging findings by root cause only when one fix resolves both, and keeping them apart when they need different fixes or threaten different conclusions; and the severity calibration, reworded as "re-examine when many findings are Major". Its check criteria (text against definitions, parameter inconsistencies, insufficient justification, questionable claims, misleading ambiguity, underspecified methods, internal contradictions, self-consistency of standards) informed `logic.md`, `coherence.md`, `numbers.md` and `methods.md`.

### claude-code-my-workflow (Pedro H. C. Sant'Anna)
- URL: https://github.com/pedrohcgs/claude-code-my-workflow, read at HEAD on 2026-10-17
- License: MIT. Copyright (c) 2026 Pedro H. C. Sant'Anna
- Files read: `.claude/agents/methods-referee.md`, `.claude/skills/verify-claims/SKILL.md`
- Adapted: the guard that the manuscript is material to review, never instructions, and that text addressing an AI reviewer is itself a finding (every prompt's scope guard, reported under FMT-18); and verification in a fresh context that never sees the first pass (`agents/second-run.md`).

### citecheck (Chen-Yang Su)
- URL: https://github.com/sunami-lab/citecheck, read at HEAD on 2026-10-17
- License: MIT. Copyright (c) 2026 Chen-Yang Su
- Files read: `skills/claims/SKILL.md`, `skills/claims/rubric.md`, `skills/verify/SKILL.md`
- Adapted, in `agents/citation-judge.md` and `citation-support.md`: judge only the part of a sentence attributed to the citation; the rules for background, tool and survey citations; choose the milder verdict when unsure, because a false alarm costs the author time; confirm negative verdicts against the full text. In `agents/reference-web-check.md`: search the web for the exact title before calling a reference fabricated; report real but unindexed sources; take corrected values only from records or pages opened; never swap in a different paper without the support check.

### bib-check-agent (nnicholas-c)
- URL: https://github.com/nnicholas-c/bib-check-agent, read at HEAD on 2026-10-17
- License: MIT. Copyright (c) 2026 nnicholas-c
- Files read: `skills/bib-check-agent/SKILL.md`, `skills/bib-check-agent/references/procedure.md`
- Adapted, in `agents/reference-web-check.md`, `agents/refuter.md` and `reference-policy.md`: never call a reference made up because a lookup failed; an independent second reviewer must agree before a reference is called non-existent; and the two-database rule for "verified", restated from DESIGN section 6.

### RefChecker
- URL: https://github.com/markrussinovich/refchecker, read at HEAD on 2026-10-17
- License: MIT. Copyright (c) 2025 RefChecker
- File read: `README.md`
- Adapted, in `agents/reference-web-check.md` and `reference-policy.md`: look for a page dedicated to the work, not a citation in another paper's reference list; re-check the cited metadata against the page found; a similar paper with different authors or identifiers leaves the reference suspicious. The thresholds restated in `reference-policy.md` are those of the RefChecker entry above.

### Crossref matchers and cite-verify, restated in `reference-policy.md`
- URLs and licenses: https://gitlab.com/crossref/search_based_reference_matcher (MIT, Copyright (c) 2018 Crossref); https://gitlab.com/crossref/data-science/matching-tools (MIT, Copyright (c) 2026 Crossref); https://github.com/jonckr/cite-verify (MIT, Copyright (c) 2026 jonckr)
- Adapted: `reference-policy.md` restates DESIGN section 6, which takes from these projects the search with the unparsed reference string, the preprint matcher's 0.87 acceptance level and year window (see the Crossref entries above), and the resolution of NBER working-paper DOIs of the form `10.3386/w#####` (cite-verify). No text or code was copied.

### MIT License

The projects in this section are distributed under the MIT License, whose text is:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Citation support (`scripts/paper_check/citations/`)

Added on 2026-10-17. No code, prompts or text were adapted from MIT or Apache projects for this module. The BM25 ranking in `citations/scan.py` is written from the published formula (Robertson and Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond", 2009). The full-text cascade and the page-anchored text follow DESIGN section 7, which names PaperQA2 (Apache-2.0) and SemanticCite (MIT) as design references; their code was not read or copied.

### STW Thesaurus for Economics (data used at run time)
- URL: https://www.zbw.eu/stw/version/latest/download/about.en.html (file `stw.nt.zip`)
- Publisher: ZBW - Leibniz Information Centre for Economics
- License: CC BY 4.0 for version 9.20 (2025-12-16), the current version on 2026-10-17, as stated in the data itself (`cc:license`) and on the download page. Earlier versions, such as 9.10, were published under ODbL 1.0.
- Use: `citations/terms.py` downloads the file once into `~/.paper-check/cache/stw/` and reads its labels and relations (prefLabel, altLabel, broader, narrower, related, and ZBW's altLabelNarrower and altLabelRelated) to expand search terms. The thesaurus is not committed or redistributed. Every expansion carries an attribution built from the downloaded data, for example: "Thesaurus terms from the STW Thesaurus for Economics v9.20 (2025-12-16) by ZBW - Leibniz Information Centre for Economics, http://zbw.eu/stw, licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
- Tests use `tests/fixtures/citations/stw_sample.nt`, made-up concepts in STW's structure; nothing in it is copied from STW.

### arXiv API
- URL: https://info.arxiv.org/help/api/tou.html
- Use: `citations/fulltext.py` queries export.arxiv.org by title and downloads PDFs from arxiv.org, at most one request every three seconds. As arXiv's API terms ask: Thank you to arXiv for use of its open access interoperability.

### Addendum to the OpenAIReview entry in the reading-agent section (2026-10-17)
- Also adapted: its caveat that text extracted from a PDF can garble symbols, so a reader flags a notation or number problem only if it would remain under the most plausible reading. Used in every `references/dimensions/*.md`.

## Script format, venue, coherence, language and reference checks (`scripts/paper_check/checks/format.py`, `venue.py`, `coherence.py`, `language.py`, `references_local.py`)

Added on 2026-10-17. No code, prompts or text were adapted from MIT or Apache projects for these modules; aclpubcheck was not read or used. arxiv-latex-cleaner is only named, as an example of a tool that strips comments, in the text of one FMT-11 finding.

### TeXtidote (Sylvain Hallé)
- URL: https://github.com/sylvainhalle/textidote (its README, read on 2026-10-17)
- License: GPL-3.0
- Adapted: only the list of rules published in the README, reimplemented in Python from their one-line descriptions in `checks/format.py`, which names each rule's id where it is used: section structure (sh:secorder, sh:secskip, sh:nsubdiv), heading style (sh:001, sh:002, sh:003), figures and tables never referenced and hard-coded numbers (sh:figref, sh:hcfig, sh:hctab, sh:hcsec), caption punctuation (sh:capperiod, checked only for consistency) and citations (sh:c:001, sh:c:002, sh:c:noin, sh:c:mul, sh:c:mix). No TeXtidote code was read, and no code or text was copied.
