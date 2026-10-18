# Reference verification: existence, metadata accuracy, preprint-to-published updates, retractions, and citation/reference-list cross-checks

> Research conditions (2026-10-17). Scholarly and product sites (arxiv.org, crossref.org, openalex.org, semanticscholar.org, gptzero.me, inera.com, retractionwatch.com and others) were blocked for both WebFetch and curl in this session. Findings therefore come from (a) web-search result summaries, (b) primary files read directly from GitHub (raw.githubusercontent.com), GitLab (Crossref's own repositories), PyPI, npm and RubyGems metadata, (c) two shallow clones (RefChecker, Hallucinator) that were grepped and then deleted, and (d) counts I computed from the Retraction Watch CSV snapshot of 2026-10-16. The session-wide web-search budget ran out part-way through. Commercial products are therefore covered only partly, and some numbers rest on search summaries rather than full reads. Each such item is marked. Check IDs (CIT-01 to CIT-12) refer to /home/user/paper_check/docs/DESIGN.md.

## 1. Which open-source tools exist for reference-level checks?

### Takeaway
Since mid-2025 a group of open-source "hallucinated reference" checkers has appeared: RefChecker (MIT), Hallucinator (AGPL-3.0), HaRC (MIT), refcheck-mcp (MIT, an MCP server for Claude Code) and HalluCiteChecker (Apache-2.0). They sit alongside older BibTeX updaters: Rebiber, reffix and bibtex-autocomplete (all MIT), bibcure (AGPL), and betterbib (now under a paid license). Validators include bibtex-tidy, BibLatex-Check and checkcites. Together they cover DOI and title lookup, field-by-field metadata diffs, and arXiv-to-published updates. Only RefChecker, Hallucinator and Zotero screen for retractions. None of them handles economics working papers (NBER, SSRN, IZA, CEPR or RePEc). The best permissively licensed parts to reuse are RefChecker's three-stage hallucination policy and thresholds, Crossref's MIT-licensed SBMV and preprint matchers, and bibtex-autocomplete's normalization and majority-vote merging.

### Cited Findings

#### A. Hallucinated or fabricated reference detectors

**RefChecker** (Mark Russinovich): the most complete open-source checker
- Link and maturity: [github.com/markrussinovich/refchecker](https://github.com/markrussinovich/refchecker). Published on PyPI as `academic-refchecker` v3.1.6, released 2026-10-12; the first release was 2025-08-03. Status "4 - Beta", Python ≥3.11 — [PyPI](https://pypi.org/project/academic-refchecker/)
- What it checks: titles, authors, years, venues, DOIs, arXiv IDs and URLs; hallucination detection; an inline-citation numbering and ordering check that "abstains when unclear"; retraction screening that "flags only references OpenAlex reports retracted"; and gap-finder suggestions for missing references — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md)
- Sources: Semantic Scholar, OpenAlex, Crossref, DBLP and ACL Anthology, plus LLM-driven deep web search — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md). The source tree also has checkers for DataCite, GitHub, web pages, OpenReview, arXiv, official proceedings and institutional reports — [checkers directory](https://github.com/markrussinovich/refchecker/tree/HEAD/src/refchecker/checkers)
- Inputs and outputs: accepts arXiv IDs or URLs, PDF, LaTeX, BibTeX (.bib/.bbl) and plain text. Writes JSON, JSONL, CSV or text reports, plus corrected BibTeX, plain-text and `\bibitem` entries, an HTML report and a RIS export. In `--json` mode JSON goes to stdout and progress goes to stderr — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md)
- How hallucination is judged. **Stage 1** is a deterministic pre-filter. It flags a reference that is unverified in every database, matches fewer than 60% of cited authors (for 3+ authors), has a DOI or arXiv ID that resolves to a different paper, or has a broken URL. "References with only minor issues (year off by one, venue variation) are not flagged". **Stage 2** sends flagged references to an LLM, which must search the web for a *dedicated page* for the work, "not just a citation in another paper's reference list". **Stage 3** re-runs title, author and year comparison against the metadata the LLM found. The verdict is LIKELY, UNCERTAIN or UNLIKELY — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md)
- Result classes: Error (author, title or DOI mismatch), Warning (year or venue differences), Suggestion (add arXiv/DOI URL), Unverified, and Hallucination — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md)
- Thresholds in the code: title `similarity_threshold` 0.8 and `year_tolerance` 1 — [settings.py](https://github.com/markrussinovich/refchecker/blob/HEAD/src/refchecker/config/settings.py). Author-match thresholds for hallucination flags are 0.6 for unverified references and 0.4 for verified ones — [hallucination_policy.py](https://github.com/markrussinovich/refchecker/blob/HEAD/src/refchecker/core/hallucination_policy.py). Retractions are checked by a batch OpenAlex query with `select=doi,is_retracted,display_name` — [backend/retraction.py](https://github.com/markrussinovich/refchecker/blob/HEAD/backend/retraction.py)
- Extraction: "LLM extraction is generally more accurate, but PDFs can fall back to GROBID". "Claude Sonnet 4 performs best for extraction; GPT-4o may hallucinate DOIs" — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md)
- Speed and cost: with a Semantic Scholar API key a reference takes 1–2 s, against 5–10 s without one — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md). A venue-scale scan cost "about $0.04 per paper" — [docs/PAPER.md](https://github.com/markrussinovich/refchecker/blob/HEAD/docs/PAPER.md)
- Accuracy: Badalova and Mayr's independent evaluation "helped identify weaknesses in RefChecker's accuracy and source coverage and informed subsequent improvements" — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md). I could not get per-tool numbers (see Gaps).
- License: MIT — [LICENSE](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/LICENSE). It depends on `fuzzywuzzy` (GPLv2) and `python-Levenshtein` (GPL-2.0-or-later) — [PyPI requires_dist](https://pypi.org/project/academic-refchecker/), [fuzzywuzzy](https://pypi.org/project/fuzzywuzzy/), [Levenshtein](https://pypi.org/project/Levenshtein/)
- Weakness for our use: it is built around CS and ML venues (OpenReview, DBLP, ACL). A grep of a shallow clone on 2026-10-17 found no NBER, RePEc, IZA or CEPR logic; "ssrn.com" appears only in a list of web-page domains — [repo](https://github.com/markrussinovich/refchecker)

**Hallucinator** (Gianluca Stringhini)
- Link and maturity: [github.com/gianlucasb/hallucinator](https://github.com/gianlucasb/hallucinator). It ships as a Rust TUI and CLI plus Python bindings (wheels for Python 3.12). PyPI `hallucinator` v0.2.2 was released 2026-08-12, the first release was 2026-02-12, and the status is "3 - Alpha" — [README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md), [PyPI](https://pypi.org/project/hallucinator/)
- What it checks: existence ("Not Found"), author mismatch, and retraction status. Retractions come from "CrossRef's retraction metadata (which includes the Retraction Watch database)" by DOI lookup, falling back to title search — [README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md)
- Sources: Crossref, arXiv, DBLP, Semantic Scholar, ACL Anthology, Europe PMC, PubMed, the doi.org resolver, OpenAlex, Open Library, GovInfo, IACR ePrint, a URL liveness checker, and an optional SearxNG web search. OpenReview is "Disabled. API unreachable after the Nov 2025 incident" — [README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md)
- How: extract text with MuPDF, find the References or Bibliography section, parse title and authors, then query all databases in parallel, 4 references at a time. It stops at the first match, retries timeouts at the end, and skips URLs and titles shorter than 5 words — [README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md)
- Matching details in code. Titles are normalized: HTML unescaping, repair of separated PDF diacritics ("R´enyi" → "Rényi"), Greek and math transliteration, NFKD, ASCII alphanumerics only, lowercase. Then rapidfuzz `ratio ≥ 0.95`, or a cautious prefix match (shorter title ≥30 characters, subtitle-aware) — [matching.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/matching.rs). Letters such as ß→ss, ı→i and ø→o are transliterated "the standard way" to match DBLP, arXiv and OpenAlex — [matching.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/matching.rs). Web-search matches use 0.85 rather than 0.95 — [searxng.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/db/searxng.rs). Titles count as "short" if they have fewer than 6 words and fewer than 25 characters — [orchestrator.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/orchestrator.rs). The cache keeps positive results 7 days and negative results 24 hours — [cache.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/cache.rs)
- DOI check: `GET https://doi.org/{doi}` with `Accept: application/vnd.citationstyles.csl+json`; HTTP 404 means the DOI does not exist. The DOI's title must then match (ratio ≥0.95, prefix or substring), followed by an author check — [doi.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/doi.rs)
- Operational lessons: the DBLP online API sits behind Anubis bot protection and "returns a JavaScript challenge page (with an HTTP 200 status)". arXiv enforces a 3-second gap, so 50 references take more than 2 minutes. Offline DBLP, ACL, arXiv and OpenAlex snapshots are recommended, with a staleness warning after 30 days — [README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md)
- Stated stance: "This tool surfaces suspicion, not proof … Confirm every detection by hand" — [README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md)
- License: AGPL-3.0-or-later — [LICENSE](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/LICENSE), [PyPI](https://pypi.org/project/hallucinator/)

**HaRC / harcx** (Hallucinated Reference Checker)
- Link and maturity: [github.com/gurusha01/HaRC](https://github.com/gurusha01/HaRC). PyPI `harcx` v0.2.0, 2026-01-26, Alpha, MIT — [PyPI](https://pypi.org/project/harcx/), [LICENSE](https://raw.githubusercontent.com/gurusha01/HaRC/HEAD/LICENSE)
- What and how: verifies `.bib` entries against Semantic Scholar (DOI, arXiv ID, title), DBLP (title), Google Scholar (title) and Open Library (ISBN, title). `--check-urls` checks that URLs are reachable and their titles match. Defaults: author threshold 0.6 and URL title threshold 0.6 — [README](https://raw.githubusercontent.com/gurusha01/HaRC/HEAD/README.md)
- Weakness: Google Scholar is reached through the `scholarly` scraping package — [PyPI requires_dist](https://pypi.org/project/harcx/). It does not use Crossref or OpenAlex — [README](https://raw.githubusercontent.com/gurusha01/HaRC/HEAD/README.md)

**refcheck-mcp** (UMN Choi Lab): an MCP server usable directly from Claude Code
- Link and maturity: [github.com/UMN-Choi-Lab/refcheck](https://github.com/UMN-Choi-Lab/refcheck). PyPI `refcheck-mcp` v0.1.0, 2026-02-25, Beta, MIT, Python ≥3.11 — [PyPI](https://pypi.org/project/refcheck-mcp/)
- Tools: `verify_reference`, `search_references` and `get_bibtex`. Sources are Crossref, Semantic Scholar, arXiv, Scopus (needs an Elsevier key and optionally an institutional token) and IEEE Xplore (free tier 200 requests per day). It runs in a "degraded mode" when keys are missing — [PyPI description](https://pypi.org/project/refcheck-mcp/)
- Pipeline: a DOI lookup through Crossref comes first ("A DOI match is near-certain verification"). A parallel title search follows. Candidates are scored on title token-set ratio, Jaccard overlap of author last names, year (±1) and venue similarity. The weighted score gives `verified` (≥0.85), `partial_match` (0.50–0.85) or `not_found` (<0.50, "Likely hallucinated"). Corrected BibTeX is returned — [PyPI description](https://pypi.org/project/refcheck-mcp/)

**HalluCiteChecker** (NAIST, Yusuke Sakai)
- Link and maturity: [github.com/yusuke1997/HalluCiteChecker](https://github.com/yusuke1997/HalluCiteChecker). PyPI 0.1.2, 2026-03-29, Apache-2.0 — [PyPI](https://pypi.org/project/hallucitechecker/), [LICENSE](https://raw.githubusercontent.com/yusuke1997/HalluCiteChecker/HEAD/LICENSE.txt). The paper is "HalluCiteChecker: A Lightweight Toolkit for Hallucinated Citation Detection and Verification in the Era of AI Scientists" — [arXiv 2604.26835](https://arxiv.org/pdf/2604.26835)
- Input is PDF. It writes a highlighted PDF only when it detects a hallucinated citation, so "you only need to manually verify the PDFs in the output directory" — [README](https://raw.githubusercontent.com/yusuke1997/HalluCiteChecker/HEAD/README.md). Dependencies include docling, acl-anthology, openreview-py, onnxruntime and lmdb — [PyPI](https://pypi.org/project/hallucitechecker/)

**Other detectors named in the literature but not inspected**
- Badalova and Mayr evaluated CheckIfExist, HalluCiteChecker, Hallucinator, Hallucinated Reference Finder (HalRef) and RefChecker — [arXiv 2607.22693 (search summary)](https://arxiv.org/html/2607.22693v2)
- CiteTracer, a multi-agent detector (paper only) — [arXiv 2605.08583](https://arxiv.org/pdf/2605.08583). AtomGPT's "Hallucination Detector" combines LLM field extraction with Semantic Scholar tool calling — [arXiv 2607.09774](https://arxiv.org/pdf/2607.09774)

#### B. BibTeX validators and updaters

**betterbib** (Nico Schlömer, now "texworld")
- What and how: `betterbib sync` updates entries from Crossref, DBLP, PubMed, arXiv and Zenodo (the default source order is crossref,dblp,pubmed). It also has `format` (field sorting, journal (un)abbreviation), `convert` (BibTeX, BibLaTeX, RIS, CSL-JSON) and `doi-to`. The option `-m/--minimum-score` defaults to 0.0 — [README](https://raw.githubusercontent.com/nschloe/betterbib/HEAD/README.md)
- Maturity and license: v7.6.1 on PyPI, 2026-09-17. The PyPI history now starts 2025-10-29, and the package depends on `stonefish-license-manager` — [PyPI](https://pypi.org/project/betterbib/). The README says "See here for licensing information", pointing to texworld, whose profile says "Full access to all TeX World functionality requires a license", bought at mondaytech.com — [texworld profile](https://github.com/texworld)
- The license is not suitable for an open shared skill to depend on. The combination of a default minimum score of 0.0 and auto-sync is risky: a wrong nearest match can be written over correct data.

**Rebiber** (Bill Yuchen Lin)
- What and how: replaces arXiv or unofficial BibTeX entries with official DBLP or ACL Anthology records, keeping cite keys. A title hit converts only if the first author's last name matches or at least two last names overlap; empty authors never match. Title keys preserve digits (16x16 ≠ 32x32). Live DBLP lookup prefers a published (non-CoRR) hit and "skips if several published hits remain". The arXiv `eprint` is copied onto the replacement. `--used-in paper.tex` limits replacement to keys actually cited. `--dry-run` and `--report` are available — [README](https://raw.githubusercontent.com/yuchenlin/rebiber/HEAD/README.md)
- Coverage: venue dumps are CS only (AAAI, ACL, CVPR, ICLR, ICML, NeurIPS, KDD, WWW and so on), refreshed by a monthly GitHub Action — [README](https://raw.githubusercontent.com/yuchenlin/rebiber/HEAD/README.md)
- Maturity: v1.4 is installed from GitHub only. The PyPI release 1.1.3 dates from 2021 — [README](https://raw.githubusercontent.com/yuchenlin/rebiber/HEAD/README.md), [PyPI](https://pypi.org/project/rebiber/). License MIT — [LICENSE](https://raw.githubusercontent.com/yuchenlin/rebiber/HEAD/LICENSE)

**reffix** (Zdeněk Kasner)
- What and how: queries the DBLP API with the title and first author. It can replace arXiv preprints with published versions (opt-in) and wraps capitalized words in braces. Its approach is conservative: "papers are updated only if the title and at least one of the authors match", no references are deleted, and an interactive mode is available — [README](https://raw.githubusercontent.com/kasnerz/reffix/HEAD/README.md)
- Maturity and license: v1.3.2, 2026-05-23, MIT — [PyPI](https://pypi.org/project/reffix/), [LICENSE](https://raw.githubusercontent.com/kasnerz/reffix/HEAD/LICENSE). Coverage is limited to DBLP, so CS papers — [README](https://raw.githubusercontent.com/kasnerz/reffix/HEAD/README.md)

**bibtex-autocomplete / btac** (Dorian Lesbre)
- Sources: OpenAlex (~240M), Crossref (~150M), arXiv, Semantic Scholar (~215M), Unpaywall (~48M), DBLP, researchr and INSPIRE-HEP — [README](https://raw.githubusercontent.com/dlesbre/bibtex-autocomplete/HEAD/README.md)
- Matching: looks up by DOI or by full title, compared without case and punctuation; "titles with missing words will not match". If authors are present, entries with no common author (last names, lowercase) are rejected, and if the year is known, entries with a different year are rejected. Fields are merged by majority vote across sources. DOIs are checked against dx.doi.org, URLs must lead to a valid page, ISSN and ISBN check digits are verified, and venue matching is abbreviation-aware (ACM ↔ Association for Computing Machinery). User fields are never overwritten without `-f`. `-p` prefixes new fields with `BTAC` for review — [README](https://raw.githubusercontent.com/dlesbre/bibtex-autocomplete/HEAD/README.md)
- Maturity and license: v1.4.3, 2025-08-24, "Production/Stable", MIT — [PyPI](https://pypi.org/project/bibtexautocomplete/)

**bibcure**: checks whether arXiv items have been published and updates them, completes fields from DOIs, finds missing DOIs and abbreviates journal names. The last release, 0.3.0, dates from 2017. License AGPLv3 — [README](https://raw.githubusercontent.com/bibcure/bibcure/HEAD/README.md), [PyPI](https://pypi.org/project/bibcure/)

**bibtex-tidy**: formats and sorts entries. Duplicates can be detected by DOI, key, abstract similarity or "citation (similar author and titles)", with merge strategies such as first, last, combine and overwrite. The latest version is 1.15.1 (2026-08-05), first published 2017, MIT — [README](https://raw.githubusercontent.com/FlamingTempura/bibtex-tidy/HEAD/README.md), [npm registry](https://www.npmjs.com/package/bibtex-tidy)

**BibLatex-Check**: checks required fields per entry type and the consistency of proceedings names. With an `.aux` file it limits the check to cited entries. It writes an HTML report with Google Scholar and DBLP links and returns an exit code. It is "no longer under active development" but maintained. MIT — [README](https://raw.githubusercontent.com/Pezmc/BibLatex-Check/HEAD/README.md), [LICENSE](https://raw.githubusercontent.com/Pezmc/BibLatex-Check/HEAD/LICENSE.txt)

**checkcites**: a Lua script that runs with any recent TeX distribution, such as TeX Live, and reports *unused* references (in the .bib but not cited) and *undefined* ones (cited but missing). It reads `.aux` files with the bibtex backend or `.bcf` with the biber backend. License LPPL 1.3c — [README](https://raw.githubusercontent.com/cereda/checkcites/HEAD/README.md), [LICENSE](https://raw.githubusercontent.com/cereda/checkcites/HEAD/LICENSE)

#### C. Zotero retraction alerts and plugins
- Zotero's built-in retraction check (code copyright 2019) covers DOIs and PMIDs. DOIs are lowercased and SHA-1-hashed; PMIDs are used as plain prefixes. It downloads a prefix list from the Zotero API (`retractions/list`) and asks `retractions/search` only about prefixes that match. The full library is never uploaded. License AGPL-3.0 — [retractions.js](https://github.com/zotero/zotero/blob/HEAD/chrome/content/zotero/xpcom/retractions.js)
- The scite Zotero plugin adds Smart Citation tallies (supporting, contrasting, mentioning) and links to scite reports. It needs no account; v2.x requires Zotero 7 — [README](https://raw.githubusercontent.com/scitedotai/scite-zotero-plugin/HEAD/README.md)
- Zotero DOI Manager fetches DOIs from Crossref, "verifies that stored DOIs are valid and marks invalid DOIs", and strips `doi:` and URL prefixes. MPL-2.0 — [README](https://raw.githubusercontent.com/bwiernik/zotero-shortdoi/HEAD/README.md)

#### D. Crossref's own open-source matching code (MIT)
- `search_based_reference_matcher` is a Java implementation of Search-Based Matching with Validation (SBMV) for structured or unstructured references. MIT, last activity 2024-09 — [GitLab](https://gitlab.com/crossref/search_based_reference_matcher). Algorithm details are in Q4.
- `data-science/matching-tools/preprint_matching` is Python code that matches preprints to journal articles and back. MIT (2026), last activity 2026-04-19 — [GitLab](https://gitlab.com/crossref/data-science/matching-tools). Details are in Q4.
- A 2026 metadata sprint, "Automated Detection of Reference Rot", built a two-stage URL checker. Stage 1 checks HTTP status, redirect chain and base domain; stage 2 compares the citation's metadata with the resolved page. Outcomes use a 7-category taxonomy: page exists; redirected to the same page; page exists but different; redirected to same site; redirected to a different page or site; page missing but site exists; site missing — [GitLab README](https://gitlab.com/crossref/metadata-sprints/sprint-2026/automated-detection-of-reference-rot)

#### E. Licenses of likely Python dependencies
- MIT: rapidfuzz, bibtexparser 2.1.0, pybtex, pdfplumber, python-docx, habanero (Crossref client), pyalex (OpenAlex client) and semanticscholar (unofficial client) — [rapidfuzz](https://pypi.org/project/rapidfuzz/), [bibtexparser](https://pypi.org/project/bibtexparser/), [pybtex](https://pypi.org/project/pybtex/), [pdfplumber](https://pypi.org/project/pdfplumber/), [python-docx](https://pypi.org/project/python-docx/), [habanero](https://pypi.org/project/habanero/), [pyalex](https://pypi.org/project/pyalex/), [semanticscholar](https://pypi.org/project/semanticscholar/)
- Copyleft: PyMuPDF is dual-licensed AGPL-3.0 or Artifex commercial; fuzzywuzzy is GPLv2; Levenshtein is GPL-2.0-or-later — [PyMuPDF](https://pypi.org/project/PyMuPDF/), [fuzzywuzzy](https://pypi.org/project/fuzzywuzzy/), [Levenshtein](https://pypi.org/project/Levenshtein/)

### Inferences
- **What we can depend on or adapt.** Code and thresholds can be adapted freely from RefChecker, refcheck-mcp, HaRC, reffix, Rebiber, bibtex-autocomplete and bibtex-tidy (MIT), Crossref's matchers (MIT), and GROBID, biblio-glutton and HalluCiteChecker (Apache-2.0). Code from Hallucinator, bibcure, CERMINE and Zotero (AGPL) should only be studied, not copied, unless the skill accepts AGPL terms. Running an AGPL tool as an optional external command the user installs is a lighter obligation, but still needs a license review. betterbib now needs a paid license, so avoid it.
- **PDF library.** DESIGN.md lists "pdfplumber or PyMuPDF". pdfplumber (MIT) is the safer default for a skill shared by pull request; PyMuPDF is AGPL. Use `rapidfuzz` (MIT) rather than `fuzzywuzzy` (GPL).
- **Mapping existing tools to our checks:**
  - CIT-01, citation ↔ reference list:
    - LaTeX: checkcites logic on `.aux`/`.bcf`; Rebiber's `--used-in` and BibLatex-Check's `-a aux` show the same idea.
    - PDF: GROBID citation-context linking (see Q5).
    - Word: Recite does this commercially (Q2); Zotero field codes give structured data (Q5).
  - CIT-02, existence: RefChecker, Hallucinator and refcheck-mcp cascades.
  - CIT-03, metadata accuracy: RefChecker's typed field errors and bibtex-autocomplete's majority-vote, never-overwrite policy.
  - CIT-04, preprint to published: Rebiber, reffix and bibcure cover CS and arXiv only. Crossref's preprint matcher and OpenAlex `locations` are general. Economics needs new logic (Q4).
  - CIT-05, retractions: Crossref `update-to` and the `updates:` filter, the Retraction Watch CSV, OpenAlex `is_retracted`, and Zotero's privacy-preserving hashed lookup as a pattern.
  - CIT-10, age and balance: no existing tool found. OpenAlex `referenced_works` can supply field baselines (Q3).
  - CIT-12, URLs and DOIs: doi.org content negotiation (Hallucinator), bibtex-autocomplete's DOI and URL validation, HaRC's `--check-urls`, and Crossref's 7-category reference-rot taxonomy.
- **Where we can add value.** No open-source tool found handles economics working-paper series or RePEc version links. CIT-04 for NBER, SSRN, IZA and CEPR is where our skill can contribute most.
- **Thresholds disagree.** Titles: RefChecker uses 0.8, Hallucinator 0.95 on normalized strings. Authors: HaRC 0.6, RefChecker 0.6 or 0.4. Our skill should calibrate its own thresholds on a small economics test set rather than copy one tool's numbers.

### Gaps
- I could not find the repositories, licenses or methods of CheckIfExist and HalRef; the web-search budget ran out.
- I did not obtain Badalova and Mayr's per-tool precision and recall, or whether RefChecker's later fixes changed them.
- The source of Zotero's retraction list (widely reported as Retraction Watch data) is not stated in the code I read, so it is unconfirmed here.
- Not covered: JabRef's integrity checks; the scite Zotero plugin's license (no LICENSE file found); and how HalluCiteChecker's detection actually works.

## 2. Which commercial products do this, how do they work, and what do they cost?

### Takeaway
The commercial tools found fall into four kinds:
- **Publisher-grade reference editing.** Inera's Edifix links references to PubMed and Crossref, diffs fields, and flags retractions, using Retraction Watch since April 2023. It is sold by subscription priced by reference volume, with credits per reference.
- **Editorial-notice screening.** scite Reference Check takes an uploaded PDF and flags cited works with retractions, corrections or other notices. It is a premium feature with a one-month trial.
- **In-text versus reference-list cross-checking.** Recite (ReciteWorks) handles APA and Harvard. In 2023 its free tier allowed 2 uploads per day, checking the first 2,500 words and 50 references.
- **Hallucination detection.** GPTZero Hallucination Check combines a failure-mode taxonomy, a local database, external APIs, web retrieval and an LLM fallback. Third-party reviews put paid tiers at about $12.99–24.99 per month on annual billing. Its self-reported 0.2% false-positive rate and 99.1% recall are disputed.

I gathered no reliable information on Citely, Paperpal, Writefull, Grammarly or EndNote features in this session.

### Cited Findings

#### Edifix (Inera)
- What it checks: Edifix corrects references with data from PubMed and Crossref and inserts PubMed IDs and Crossref DOIs. It checks both PubMed and Crossref records for discrepancies in author names, titles, journal titles, volume, issue, pages and dates — [Inera support: What is Edifix (search summary)](https://support.inera.com/support/solutions/articles/1000201380-what-is-edifix-), [Edifix features](https://www.edifix.com/features)
- Retractions: Edifix flags retractions found in PubMed and Crossref metadata. Since April 2023 it also queries Retraction Watch and looks for retraction notices in article titles. Inera recommends running with both PubMed and Crossref linking on, because Retraction Watch checks are most accurate when the query uses an identifier (PMID or DOI) — [How does Edifix detect retracted articles?](https://support.inera.com/support/solutions/articles/11000120609-how-does-edifix-detect-retracted-articles-), [Inera blog](https://inera.com/blog/edifix-retraction-detection-and-notification/)
- Pricing model: monthly and annual subscriptions based on reference volume. "Reference credits will be deducted when Edifix parses and restructures a reference, or parses enough of it to link to Crossref or PubMed". A free trial is offered. No per-reference price was found — [eXtyles transition resources](https://inera.com/extyles-transition-resources-edifix/), [Will I be charged for references Edifix didn't restructure?](https://support.inera.com/support/solutions/articles/1000080368-will-i-be-charged-for-references-that-edifix-didn-t-restructure-)
- Inera documents that Crossref and PubMed corrections can differ — [support article](https://support.inera.com/support/solutions/articles/11000035625-how-are-crossref-and-pubmed-correction-different-why-are-they-different-)

#### scite Reference Check
- How it works: the user picks Reference Check from the Product menu and uploads a PDF; the report is saved to the user's profile. It flags cited works that carry retractions, corrections or other editorial notices, and shows each citation statement that points to a flagged reference — [scite help center](https://help.scite.ai/zh/article/how-do-i-use-the-scite-reference-check-u52q0w), [CUHK library guide](https://libguides.lib.cuhk.edu.hk/scite/reference)
- Price: a help page calls it a premium feature with a one-month free trial for new accounts; no current price was found — [scite help center (search summary)](https://help.scite.ai/zh/article/how-do-i-use-the-scite-reference-check-u52q0w)
- Integration: in 2021 scite and Aries Systems announced Reference Check inside Editorial Manager, arriving in version 17.0 — [SSP announcement](https://www.sspnet.org/?p=47393)

#### Recite (ReciteWorks)
- What it checks: matches in-text citations against the reference list for APA and Harvard styles. It flags missing references or citations and inconsistent authors and dates. Results are color-coded: green for a correct citation, orange for a possible match with an error, red for an issue or an unmatched reference — [Stellenbosch University library blog, 2023-04-26](https://blogs.sun.ac.za/libraryresearchnews/2023/04/26/references-all-over-the-place-try-reciteworks/), [Substack review](https://toureme.substack.com/p/recite-works)
- Price: as of April 2023 the free tier allowed "2 uploads per day and the first 2500 words and 50 references". A monthly plan costs "the price of a couple of cups of coffee", with unlimited uploads — [Stellenbosch blog](https://blogs.sun.ac.za/libraryresearchnews/2023/04/26/references-all-over-the-place-try-reciteworks/), [Substack review](https://toureme.substack.com/p/recite-works). I did not find a current official price list.

#### GPTZero Hallucination Check
- Method, according to GPTZero's technical report:
  - a formal taxonomy of citation failure modes;
  - "exhaustive sourcing" against a local database, external citation APIs and an internet-scale retrieval pipeline;
  - LLM reasoning when programmatic matching is inconclusive;
  - a triage step that separates citations that can be checked field by field from unstructured or canonical citations that need semantic reasoning.
  - Each citation gets a card with its final class, the most similar source found, component-level similarity and a natural-language justification. Title, authors, journal, date, URL and DOI are compared, and one matching field is not enough to pass. "The scan provides evidence; it is not an oracle."
  - [GPTZero technical report (search summary)](https://gptzero.me/news/how-does-gptzeros-hallucination-check-detector-work-a-technical-report/), [TrueStandard explainer](https://truestandard.ai/blog/gptzero-hallucination-detector)
- Accuracy is disputed. GPTZero reports a 0.2% false-positive rate on real citations (2 "unsure" out of 1,023, no "fake" verdicts) and 99.1% recall on hallucinated citations (3 "exist" out of 333) — [GPTZero, "What Counts as a Hallucinated Citation?"](https://gptzero.me/news/what-counts-as-a-hallucinated-citation/). The CiteTracer paper measured GPTZero at 62.8% recall on real and 67.5% recall on hallucinated citations, against CiteTracer's 90.9% and 99.8%, on a 2,450-citation synthetic benchmark. GPTZero cannot output that benchmark's "POTENTIAL" class — [arXiv 2605.08583 (search summary)](https://arxiv.org/pdf/2605.08583); GPTZero attributes the gap to definitions — [GPTZero response](https://gptzero.me/news/what-counts-as-a-hallucinated-citation/)
- Price, from third-party reviews that disagree with each other: a free tier of 10,000 words per month; Premium at $12.99 per month billed annually (300,000 words); Professional at $24.99 per month billed annually (500,000 words; one source says API access comes with this tier); and a separate listing of $14.99 per month, or $8.33 per month billed annually — [Fritz.ai review](https://fritz.ai/gptzero-review/), [aitoolsli.st](https://aitoolsli.st/tool/gpt-zero), [ConversionGems](https://www.conversiongems.com/tools/gptzero). One review says a "Superhuman acquisition [was] announced June 2026"; I could not confirm this — [aitoolsli.st (search summary)](https://aitoolsli.st/tool/gpt-zero)
- Published audits (GPTZero's own data, not peer reviewed):
  - ICLR 2026: 50 of 300 sampled submissions had at least one obvious hallucinated citation, and most of the 3–5 reviewers per paper missed them. GPTZero said it was scanning all 20,000 submissions with ICLR; I found no published result of that scan — [GPTZero ICLR 2026](https://gptzero.me/news/iclr-2026/), [BetaKit](https://betakit.com/start-up-investigation-reveals-50-peer-reviewed-papers-contained-hallucinated-citations/)
  - NeurIPS 2025: 4,841 of 5,290 accepted papers were scanned, and 100 confirmed hallucinated citations were found across 51 papers. Fortune reported "at least 53" papers — [GPTZero NeurIPS](https://gptzero.me/news/neurips/), [The Decoder](https://the-decoder.com/over-100-fake-citations-slip-through-peer-review-at-top-ai-conference/), [Fortune, 2026-01-21](https://fortune.com/2026/01/21/neurips-ai-conferences-research-papers-hallucinations/)

### Inferences
- None of these products targets economics working papers. Edifix leans toward PubMed but links Crossref, which covers economics journals. Recite's author–date matching is the closest commercial counterpart to CIT-01 for Word and PDF drafts in economics styles.
- Commercial pricing is per word or per reference. For our skill the binding limit is API rate limits, not money: the free scholarly APIs in Q3 are enough.
- GPTZero's design (field check, then retrieval, then LLM fallback, with an evidence card per citation) matches RefChecker's and fits DESIGN.md's "proof plus trajectory" format. Our per-reference evidence card could hold the closest record, field-level similarities and the queries used.
- Vendor accuracy figures are self-reported, and benchmark scores depend on how "hallucinated" is defined. The team should build its own small labeled set of economics references rather than rely on vendor numbers.

### Gaps
- Not researched (search budget exhausted, product sites blocked): Citely, Paperpal, Writefull, Grammarly and EndNote — how they work and what they cost. From my prior knowledge, not verified this session: EndNote has added retraction alerts based on Retraction Watch data, and Paperpal and Writefull market reference or citation checks. Treat both as leads only.
- Current Edifix tier prices, current scite pricing, current Recite pricing, and GPTZero's official API price for Hallucination Check.
- Whether scite's Editorial Manager integration is still live.

## 3. Which data sources and APIs are best (limits, terms, keys, economics coverage)?

### Takeaway
The backbone should be:
- **Crossref.** DOIs and metadata, plus `update-to` and the `updates:` filter for retractions, including Retraction Watch records. The polite pool is reached with `mailto`. New limits since 1 December 2025: 10 requests/s with 3 concurrent for single-DOI lookups, 3/s with 3 concurrent for searches.
- **OpenAlex.** An API key has been required since 13 February 2026. There is $1 of free usage per day, and singleton DOI lookups are free and unlimited. Useful fields are `is_retracted` (from Retraction Watch) and `locations`, which carry version labels.

Secondary sources:
- **Semantic Scholar.** 1 request/s per key, a title-match endpoint, and it aggregates SSRN.
- **DataCite.** Data and software DOIs.
- **The Retraction Watch CSV on GitLab.** Updated daily, good for offline screening.
- **Unpaywall.** Open-access versions.

**RePEc/IDEAS** is the best source for linking economics working-paper versions, but its API needs approval and has no search. DBLP and arXiv are CS-oriented and currently slow or bot-blocked.

### Cited Findings

#### Crossref REST API
- Polite pool: add a `mailto` parameter, or put `mailto:` in the User-Agent; the docs also ask for an identifying User-Agent. These GitHub docs are marked deprecated in favour of api.crossref.org — [CrossRef/rest-api-doc README](https://github.com/CrossRef/rest-api-doc)
- Limits from 1 December 2025, the first change since the API launched in 2013 (all figures from search summaries of Crossref pages):
  - polite pool: single-DOI lookups 10 requests/s with concurrency 3; list queries 3/s with concurrency 3;
  - public pool: 5/s with concurrency 1, and 1/s with concurrency 1;
  - Metadata Plus: 150/s with no concurrency limit.
  - HTTP 429 means back off. Limits are reported in the `x-rate-limit-limit`, `x-rate-limit-interval` and `x-rate-limit-type` headers.
  - An interim forum post gave polite concurrency as 5; the current docs say 3.
  - [Crossref community: announcing changes](https://community.crossref.org/t/announcing-changes-to-rest-api-rate-limits-crossref/14726), [Updates to rate limits](https://community.crossref.org/t/updates-to-rest-api-rate-limits/14872), [Access and authentication docs](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
- GROBID's tuned Crossref client:
  - starting concurrency is 1 (public), 3 (polite) or 50 (Plus), then adjusted from the `x-concurrency-limit` header;
  - it reads `x-api-pool`;
  - on 429 it backs off exponentially with full jitter (1 s base, 60 s cap) and drops to concurrency 1.
  - With citation consolidation, 10,000 PDFs took about 45 h in the polite pool against about 12 h with Plus, with 4.7% against 0.85% failed documents.
  - [GROBID Consolidation.md](https://github.com/kermitt2/grobid/blob/HEAD/doc/Consolidation.md)
- Query fields and filters:
  - `query.bibliographic` covers "titles, authors, ISSNs and publication years"; `query.title` was deprecated in 2019 — [rest-api-doc](https://github.com/CrossRef/rest-api-doc)
  - Ranking uses Elasticsearch BM25, and the score "is not the threshold for all queries" — [Crossref forum](https://community.crossref.org/t/rejecting-false-positive-doi-matches-with-simple-text-query/3005)
  - Filters: `updates:{doi}` returns "records that represent editorial updates to the DOI"; also `is-update`, `update-type`, `has-relation`, and `relation.type` (for example `is-preprint-of`) — [rest-api-doc](https://github.com/CrossRef/rest-api-doc)
  - `update-to` holds entries with `updated` (date), `DOI`, `type` (for example retraction or correction) and `label` — [api_format.md](https://github.com/CrossRef/rest-api-doc/blob/HEAD/api_format.md)
- Retraction Watch in Crossref: retractions appear in `update-to`, with a `source` field of `publisher` or `retraction-watch`. Crossref acquired the Retraction Watch database in September 2023 — [Crossref Retraction Watch documentation](https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/), [Crossref blog](https://www.crossref.org/blog/retraction-watch-retractions-now-in-the-crossref-api/)

#### Retraction Watch dataset (CSV)
- Repository and format: [gitlab.com/crossref/retraction-watch-data](https://gitlab.com/crossref/retraction-watch-data) holds one CSV, "updated every working day"; the README was generated on 2026-10-16. Columns include Record ID, Title, Subject, Journal, Publisher, Author, ArticleType, RetractionDate, RetractionDOI, RetractionPubMedID, OriginalPaperDate, OriginalPaperDOI, OriginalPaperPubMedID, RetractionNature, Reason (a controlled vocabulary), Paywalled and Notes. RetractionNature is Retraction, Correction, Expression of concern, or Reinstatement. Expressions of concern and corrections "are not as comprehensive as retractions" — [README](https://gitlab.com/crossref/retraction-watch-data)
- My counts from the 2026-10-16 snapshot (67.6 MB) — [CSV](https://gitlab.com/crossref/retraction-watch-data/-/blob/main/retraction_watch.csv):
  - 73,283 rows: 67,845 retractions, 3,732 expressions of concern, 1,543 corrections and 163 reinstatements.
  - 67,331 rows have an original DOI, so about 8% need title or author matching.
  - 2,534 of 64,271 distinct DOIs have more than one notice.
  - 4,239 rows carry the subject "(B/T) Business - Economics" and 2,325 "(SOC) Psychology".
  - The economics-tagged rows are dominated by 2009–2011 conference proceedings; for example, the 2011 International Conference on E-Business and E-Government (ICEE) accounts for 695 rows.
- Behavioral-science test cases from the same snapshot — [CSV](https://gitlab.com/crossref/retraction-watch-data/-/blob/main/retraction_watch.csv):

  | Paper | DOI | Notices |
  |---|---|---|
  | Shu, Mazar, Gino, Ariely & Bazerman, PNAS 2012, "Signing at the beginning…" | 10.1073/pnas.1209746109 | Retraction 2021-09-13. Subjects: Ethics, Sociology, not Economics |
  | Mazar, Amir & Ariely, JMR 2008, "The Dishonesty of Honest People" | 10.1509/jmkr.45.6.633 | Expression of concern 2024-09-20. Subjects: Ethics, Psychology |
  | Shu, Gino & Bazerman, PSPB 2011 | 10.1177/0146167211398138 | Expression of concern 2025-08-28 |
  | Heyman & Ariely, Psychological Science 2004 | 10.1111/j.0956-7976.2004.00757.x | Expression of concern 2021-07-23 |
  | Gino & Wiltermuth, Psychological Science 2014 | 10.1177/0956797614520714 | Retraction 2023-07-06 |
  | Hanks, Just & Wansink, JAMA Pediatrics 2013 | 10.1001/jamapediatrics.2013.82 | Expression of concern 2018-04-13, then retraction 2018-09-19 |
  | Schulze, Maertens & Wansink, JEBO 2013 | 10.1016/j.jebo.2013.06.004 | Correction 2013-10-11 |

- The README does not state a license or terms for the dataset — [README](https://gitlab.com/crossref/retraction-watch-data)

#### OpenAlex
- Keys: "All API requests now require an API key", effective 13 February 2026 — [OpenAlex changelog](https://help.openalex.org/hc/en-us/articles/38868153578263-Changelog). The key is free; "a few calls without an API key for demo purposes" still work — [OpenAlex blog](https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/)
- Pricing (search summaries of official help pages):
  - $1 of free usage per day per key;
  - single-work lookups by DOI or ID: unlimited and free;
  - list or filter calls: $0.0001 each, so about 10,000 per day free, capped at 1,000,000 results;
  - text search: $0.001 per call (10 credits);
  - without a key: about $0.10 per day, according to one source;
  - the budget resets at midnight UTC, and `X-RateLimit-*` headers show what is left.
  - [Pricing overview](https://help.openalex.org/access/pricing/), [Example costs](https://help.openalex.org/access/example-costs/), [OpenAlex blog](https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/)
  - **Conflict:** a February 2026 announcement and the GitHub-hosted docs still describe 100,000 credits per day and 100 requests/s, with 1 credit per singleton and 10 per list call — [openalex-users group](https://groups.google.com/g/openalex-users/c/rI1GIAySpVQ), [openalex-docs rate limits](https://github.com/ourresearch/openalex-docs/blob/HEAD/how-to-use-the-api/rate-limits-and-authentication.md)
- Useful fields:
  - `is_retracted`: "True if we know this work has been retracted", taken from Retraction Watch; it is also a filter — [work object](https://github.com/ourresearch/openalex-docs/blob/HEAD/api-entities/works/work-object/README.md), [filter docs](https://github.com/ourresearch/openalex-docs/blob/HEAD/api-entities/works/filter-works.md)
  - `doi`: a work may have a preprint DOI and a published DOI, but "this field always has just one DOI, the DOI for the published work" — [work object](https://github.com/ourresearch/openalex-docs/blob/HEAD/api-entities/works/work-object/README.md)
  - `locations[].version` is submittedVersion, acceptedVersion or publishedVersion, and `primary_location` is the copy closest to the version of record — [work object](https://github.com/ourresearch/openalex-docs/blob/HEAD/api-entities/works/work-object/README.md)
  - `indexed_in` can be arxiv, crossref, doaj or pubmed — [work object](https://github.com/ourresearch/openalex-docs/blob/HEAD/api-entities/works/work-object/README.md)
  - `referenced_works` lists the outgoing citations, which can supply CIT-10 baselines — [work object](https://github.com/ourresearch/openalex-docs/blob/HEAD/api-entities/works/work-object/README.md)
- Search: the `search` parameter covers titles, abstracts and full text, while `title.search` is a field filter. Both stem words, and stemming can be turned off — [search works](https://github.com/ourresearch/openalex-docs/blob/HEAD/api-entities/works/search-works.md). Up to 50 IDs can be combined in one request with OR syntax — [rate-limit doc](https://github.com/ourresearch/openalex-docs/blob/HEAD/how-to-use-the-api/rate-limits-and-authentication.md)

#### Semantic Scholar
- Limits:
  - Without a key, most endpoints share a pool of "1000 requests per second … among all unauthenticated users" and may be throttled further. A key gets an introductory 1 RPS on all endpoints, which can be raised after review — [S2 API product page](https://www.semanticscholar.org/product/api), [tutorial](https://webflow.semanticscholar.org/product/api/tutorial)
  - History: the unauthenticated pool was 5,000 requests per 5 minutes in March 2023. It was reduced in 2024, when "All new key requests receive a 1 RPS rate limit" — [S2 release notes](https://github.com/allenai/s2-folks/blob/HEAD/API_RELEASE_NOTES.md)
- Policies (October–November 2024): no key requests from free email domains and no keys for third-party apps; keys inactive for about 60 days are pruned; exponential backoff is required; Springer abstracts are not available through the API — [S2 release notes](https://github.com/allenai/s2-folks/blob/HEAD/API_RELEASE_NOTES.md)
- Title matching: a Title Search endpoint added in June 2024 "returns a single paper with the closest title match" (`/paper/search/match`) — [S2 release notes](https://github.com/allenai/s2-folks/blob/HEAD/API_RELEASE_NOTES.md). Third-party docs say it can return a `matchScore`; the score's range is undocumented — [search summary of MCP docs](https://glama.ai/mcp/servers/@zongmin-yu/semantic-scholar-fastmcp-mcp-server/blob/64d0e94f9be36ce558433716edaeb62a821d7a6b/semantic_scholar/api/papers.py)
- Coverage: Semantic Scholar "aggregates Academia.edu, SSRN, PubMed, and more" — [Hallucinator README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md)

#### DataCite, doi.org, Unpaywall, arXiv, DBLP
- DataCite (changes announced for Q3 2025): authenticated users get 3,000 requests per 5 minutes per IP; users who give an email via `mailto` or the User-Agent get 1,000; anonymous users get 500. doi.org content negotiation is capped at 1,000 per 5 minutes — [DataCite rate-limit changes](https://support.datacite.org/docs/rate-limit), [DataCite FAQ](https://support.datacite.org:443/docs/is-there-a-rate-limit-for-making-requests-against-the-datacite-apis). RefChecker has a DataCite checker — [checkers directory](https://github.com/markrussinovich/refchecker/tree/HEAD/src/refchecker/checkers)
- doi.org content negotiation (`Accept: application/vnd.citationstyles.csl+json`) returns CSL-JSON, and a 404 means the DOI does not exist — [Hallucinator doi.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/doi.rs)
- Unpaywall: requests must include an email; keep to 100,000 calls per day; download the snapshot for bulk use — [Unpaywall API](https://unpaywall.org/api/v2)
- arXiv requires a 3-second gap between requests. DBLP's online API currently returns an Anubis JavaScript challenge — [Hallucinator README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md)
- Scopus needs an Elsevier API key (and optionally an institutional token). IEEE Xplore's free tier allows 200 requests per day — [refcheck-mcp](https://pypi.org/project/refcheck-mcp/)

#### RePEc / IDEAS (economics)
- API access: "currently not openly available". Users email Christian Zimmermann and receive an access code that expires but can be renewed. Functions such as `getref`, `getrecentpapers`, `getpubsfromwpseries` and `getauthorshortid` are unlocked per user. Output is JSON, and "there is no search function through the API" — [IDEAS API page](https://ideas.repec.org/api.html). An R client, `repec`, reads the code from `REPEC_API_KEY` — [CRAN repec](https://cran.r-project.org/web/packages/repec/refman/repec.html)
- Version links: RePEc keeps all versions and links a working paper to its published version. Fuzzy title matching runs "only across the works listed in an author's profile". This "cannot be done for works where none of the authors is registered" or where an author did not add all versions. IDEAS pages show "Other versions of this item" in both directions; this description comes from a 2009 post — [RePEc blog 2009](https://blog.repec.org/2009/08/21/on-versioning-in-repec/), [IDEAS tutorial 2017](https://blog.repec.org/2017/03)

### Inferences
- **Suggested lookup order per reference.** Use the cheapest and most precise source first, and cache everything (per DESIGN.md §8.6):
  1. If there is a DOI, query doi.org content negotiation, or Crossref `works/{doi}`.
  2. OpenAlex singleton lookup by DOI (free): gets `is_retracted`, locations and the published-version DOI.
  3. Crossref `query.bibliographic` on the raw reference string or on title, authors and year (SBMV-style).
  4. Semantic Scholar `/paper/search/match`.
  5. OpenAlex `search` (paid credits beyond the daily budget).
  6. DataCite, for data and software DOIs.
  7. RePEc, if the team gets access; otherwise web search via Claude as the last step, recorded in the trajectory.
- **Retraction screening (CIT-05).** Match DOIs and PMIDs against a locally cached copy of the daily Retraction Watch CSV, then confirm with Crossref `updates:{doi}` or `update-to` and OpenAlex `is_retracted`. Aggregate all notices per DOI: 2,534 DOIs have more than one. Report expressions of concern and corrections separately from retractions, and handle reinstatements. Do not filter by the Subject column: the key behavioral-economics retractions are tagged Psychology, Sociology or Ethics.
- **Configuration for a shared skill.** Each coworker needs their own free OpenAlex key and a Semantic Scholar key, which requires an institutional email. Both belong in environment variables or `paper-check.yaml`. A `mailto` for Crossref, DataCite and Unpaywall should be required. When keys are missing the skill should run in degraded mode and say so in the coverage table.
- **Throughput.** With polite-pool Crossref (10/s singleton, 3/s search, 3 concurrent) and 1 RPS on Semantic Scholar, a 60-reference economics paper should take about 1–2 minutes if lookups are cascaded and cached. This is an estimate, not a measurement.

### Gaps
- No sourced figures on how well Crossref, OpenAlex or Semantic Scholar cover economics journals and working papers.
- Whether OpenAlex merges SSRN or NBER working papers with their journal versions into one work, or keeps them as separate works.
- The Crossref record types for NBER (believed prefix 10.3386) and SSRN (believed 10.2139) DOIs, and whether IZA and CEPR discussion papers have DOIs at all. A search summary claimed IZA uses 10.1596; no source supported this and I disregard it. These prefixes come from prior knowledge and are unverified here.
- Not researched: EconBiz (ZBW) API, CitEc, PubMed ECitMatch, the license and terms of the Retraction Watch data, and Google Scholar (no official API).

## 4. What matching strategies work, and how do tools handle economics working papers versus published versions?

### Takeaway
The pattern that holds up is:
1. **Identifier first.** Resolve the DOI or arXiv ID, and confirm that the resolved title and authors match the citation.
2. **Search.** Search on the raw string, or on title, first author and year.
3. **Validate.** Check each candidate on several fields (title similarity, author overlap, a year window, volume and pages) with precision-oriented thresholds, and abstain when the top candidates are close.

Published settings include: title similarity ≥0.8 (RefChecker) or ≥0.95 on normalized strings (Hallucinator); a composite score ≥0.85 (refcheck-mcp); and a composite ≥0.87 with a year window of −1 to +3 (Crossref's preprint matcher). Most tools tolerate a year difference of ±1. Economics working-paper-to-journal links need wider year windows, tolerance for changed titles, and version-aware sources (RePEc, OpenAlex locations); no open-source tool implements this yet.

### Cited Findings
- **Crossref SBMV evaluation (December 2018).** On 2,000 unstructured reference strings, the best search-based variant (SBMV) reached F1 96.3%, against 92.5% for the legacy parsing-based approach. Precision was 98.09% against 98.95%, and recall 94.56% against 86.85%. Errors came mainly from incomplete or wrong target metadata — [Crossref blog: Reference matching: for real this time](https://www.crossref.org/blog/reference-matching-for-real-this-time/). Later posts discuss the precision–recall trade-off — [How good is your matching?](https://www.crossref.org/blog/how-good-is-your-matching/), [The myth of perfect metadata matching](https://www.crossref.org/blog/the-myth-of-perfect-metadata-matching/)
- **SBMV algorithm (Crossref Java code, MIT):**
  - It queries `query.bibliographic`, taking 20 rows for unstructured references and 100 for structured ones — [MatchRequest.java](https://gitlab.com/crossref/search_based_reference_matcher/-/blob/main/src/main/java/org/crossref/refmatching/MatchRequest.java), [CandidateSelector.java](https://gitlab.com/crossref/search_based_reference_matcher/-/blob/main/src/main/java/org/crossref/refmatching/CandidateSelector.java)
  - Candidates are kept only if relevance score ÷ query length ≥ 0.4.
  - Validation is a generalized Jaccard similarity over the relevance score, the normalized score, volume, year, issue, pages, title, container title and author. A year off by ±1 earns half weight, and title or author similarity above 0.7 count as signals.
  - A match is accepted at a validation score ≥0.34 for unstructured references and ≥0.76 for structured ones — [MatchRequest.java](https://gitlab.com/crossref/search_based_reference_matcher/-/blob/main/src/main/java/org/crossref/refmatching/MatchRequest.java), [Candidate.java](https://gitlab.com/crossref/search_based_reference_matcher/-/blob/main/src/main/java/org/crossref/refmatching/Candidate.java)
- **Crossref preprint ↔ article matcher (Python, MIT, 2026):**
  - Article to preprint: query `query.bibliographic` with the title, family names and year, filtered to `type:posted-content`, keeping only `subtype == "preprint"`.
  - Score = mean of three parts. Year score: 1 if (article year − preprint year) is between −1 and +3. Title score: rapidfuzz `token_set_ratio`, divided by 1.5 if one title starts with "correction", "response", "reply" or "appendix" and the other lacks that word. Author score: greedy best-pair `fuzz.ratio` over name variants, with ORCID equality deciding when both records have an ORCID.
  - Accept at ≥0.87 and within 0.04 of the top score.
  - [match_articles.py](https://gitlab.com/crossref/data-science/matching-tools/-/blob/main/preprint_matching/offline_dataset/match_articles.py)
  - The reverse direction (preprint to article) filters `type:journal-article` and accepts ≥0.87 within 0.2 of the top score — [discover_article_candidates.py](https://gitlab.com/crossref/data-science/matching-tools/-/blob/main/preprint_matching/offline_dataset/discover_article_candidates.py)
- **biblio-glutton against the Crossref API (measured September 2021).** On 17,015 PubMed Central reference strings extracted by GROBID: glutton reached P 97.33, R 95.52, F1 96.42 at 0.067 s per reference. The Crossref API reached P 97.19, R 94.26, F1 95.69 at 0.18 s per reference with about 50 concurrent queries. Many apparent errors come from wrong DOIs in the NLM ground truth — [biblio-glutton Benchmarking](https://github.com/kermitt2/biblio-glutton/blob/HEAD/doc/Benchmarking.md)
- **Post-validation.** GROBID post-validates Crossref results with a fuzzy first-author surname match "to filter false positives (the CrossRef API is a search API and may return inexact matches)" — [GROBID Consolidation.md](https://github.com/kermitt2/grobid/blob/HEAD/doc/Consolidation.md). It reports DOI or PMID resolution above 0.95 F1 from PDF extraction — [GROBID README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)
- **No universal score cutoff.** Crossref staff say a score is not a threshold for all queries — [Crossref forum](https://community.crossref.org/t/rejecting-false-positive-doi-matches-with-simple-text-query/3005). One client warns that "CrossRef Metadata Search can be prone to false positives" — [RefManageR docs](https://docs.ropensci.org/RefManageR/reference/ReadCrossRef.html). A 2025 pipeline paper reports 100% precision but about 58% recall on the Crossref dataset it tested — [arXiv 2511.18408 (search summary)](https://arxiv.org/pdf/2511.18408)
- **Thresholds in open-source tools:**
  - RefChecker: title 0.8, year tolerance ±1, author thresholds 0.6 and 0.4 for hallucination flags — [settings.py](https://github.com/markrussinovich/refchecker/blob/HEAD/src/refchecker/config/settings.py), [hallucination_policy.py](https://github.com/markrussinovich/refchecker/blob/HEAD/src/refchecker/core/hallucination_policy.py)
  - Hallucinator: normalized-title ratio ≥0.95, web matches 0.85, short-title rules — [matching.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/matching.rs)
  - refcheck-mcp: composite ≥0.85 for verified, 0.50–0.85 for partial — [PyPI](https://pypi.org/project/refcheck-mcp/)
  - HaRC: authors 0.6 — [README](https://raw.githubusercontent.com/gurusha01/HaRC/HEAD/README.md)
  - bibtex-autocomplete: exact normalized title, at least one shared last name, same year — [README](https://raw.githubusercontent.com/dlesbre/bibtex-autocomplete/HEAD/README.md)
  - Rebiber: first-author match or ≥2 shared last names, with digit-preserving title keys — [README](https://raw.githubusercontent.com/yuchenlin/rebiber/HEAD/README.md)
  - reffix: title plus at least one author — [README](https://raw.githubusercontent.com/kasnerz/reffix/HEAD/README.md)
- **Author name normalization:**
  - Hallucinator transliterates ß, ı and ø to match DBLP, arXiv and OpenAlex, and repairs PDF-split diacritics — [matching.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/matching.rs)
  - Crossref compares name variants ("given family", "family given", first given name plus family) and uses ORCID when present — [match_articles.py](https://gitlab.com/crossref/data-science/matching-tools/-/blob/main/preprint_matching/offline_dataset/match_articles.py)
  - bibtex-autocomplete treats authors as matching when last names agree and one first name equals, or abbreviates, the other — [README](https://raw.githubusercontent.com/dlesbre/bibtex-autocomplete/HEAD/README.md)
  - Rebiber strips trailing "et al." and "and others" — [README](https://raw.githubusercontent.com/yuchenlin/rebiber/HEAD/README.md)
  - RefChecker reports typed errors such as "First author mismatch: cited 'Minh-Thang Luong', actual 'Thang Luong'" — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md)
- **Year tolerance and version drift:**
  - RefChecker treats a year off by one as a warning, not a hallucination, and its sample report includes a "year (v1 vs v2 update)" error type — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md)
  - Its paper counts only "identity-level" failures and excludes "venue/year differences, publication-status updates, or minor name variants" — [docs/PAPER.md](https://github.com/markrussinovich/refchecker/blob/HEAD/docs/PAPER.md)
  - bibtex-autocomplete rejects any year mismatch — [README](https://raw.githubusercontent.com/dlesbre/bibtex-autocomplete/HEAD/README.md)
  - SBMV uses ±1 at half weight, and Crossref's preprint matcher uses −1 to +3 — [Candidate.java](https://gitlab.com/crossref/search_based_reference_matcher/-/blob/main/src/main/java/org/crossref/refmatching/Candidate.java), [match_articles.py](https://gitlab.com/crossref/data-science/matching-tools/-/blob/main/preprint_matching/offline_dataset/match_articles.py)
- **Preprint and working-paper handling today:**
  - Rebiber, reffix and bibcure update arXiv entries from DBLP, ACL Anthology or arXiv only — [Rebiber](https://raw.githubusercontent.com/yuchenlin/rebiber/HEAD/README.md), [reffix](https://raw.githubusercontent.com/kasnerz/reffix/HEAD/README.md), [bibcure](https://raw.githubusercontent.com/bibcure/bibcure/HEAD/README.md)
  - Crossref's preprint matcher considers only `posted-content` records with subtype `preprint` — [match_articles.py](https://gitlab.com/crossref/data-science/matching-tools/-/blob/main/preprint_matching/offline_dataset/match_articles.py)
  - OpenAlex can carry preprint and published versions as locations of one work, with the published DOI in `doi` — [work object](https://github.com/ourresearch/openalex-docs/blob/HEAD/api-entities/works/work-object/README.md)
  - RePEc links versions within author profiles — [RePEc blog](https://blog.repec.org/2009/08/21/on-versioning-in-repec/)
  - RefChecker's code has no NBER, SSRN, IZA, CEPR or RePEc logic — [repo](https://github.com/markrussinovich/refchecker)
- **Short and generic titles.** Hallucinator skips titles under 5 words as "too generic, false matches" — [README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md). Its prefix-matching rule exists to stop "Won't Somebody Think of the Children?" from matching a different paper that shares that title as its prefix — [matching.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/matching.rs)

### Inferences
- **Recommended cascade for CIT-02 and CIT-03.** Thresholds are starting points to calibrate.
  1. Normalize the text: strip LaTeX and HTML, transliterate, NFKD.
  2. Extract identifiers: DOI regex; arXiv ID; SSRN `abstract_id`; NBER "w12345"; IZA "DP No."; CEPR "DP" number.
  3. Resolve the DOI through doi.org or Crossref. If it resolves, require title ratio ≥0.9 or prefix logic, plus first-author agreement. If the title or authors disagree, report an identifier conflict (Major), as RefChecker does.
  4. If there is no DOI, or it fails, run SBMV-style search: Crossref `query.bibliographic` on the raw string, then OpenAlex and Semantic Scholar match. Validate on a composite of title token-set ratio, author last-name overlap and year window. Abstain when the top two candidates are within about 0.04.
  5. Diff the matched record field by field for CIT-03, with typed findings (first author, author order, year, venue, volume, pages, DOI) and severity rules.
- **Economics working papers (CIT-04).**
  - Treat a cited WP as *existing* if a WP record is found: NBER and SSRN DOIs, a RePEc handle, or an IZA or CEPR series page.
  - Then search separately for the published version: Crossref `type:journal-article` with title, authors and year; RePEc "other versions"; OpenAlex locations.
  - Use a wider year window, such as WP year −1 to +6. This is my inference from economics publication lags and is unmeasured.
  - Weight author-set equality and abstract or JEL similarity more than title equality, because titles often change. Escalate unclear cases to READ-style LLM adjudication with quoted evidence.
  - Report CIT-04 as a Suggestion with confidence, and never as an error.
- **Severity mapping.** Use RefChecker's identity-level definition for Critical, and only after DESIGN.md guardrail 3 is satisfied: the DOI fails and no close title exists in any database. Author-list mismatches are Major. A year off by one, venue naming or a status update are Minor or Suggestion.
- **Caching.** Cache negative results for a shorter time than positive ones (Hallucinator: 24 h against 7 days), so that newly indexed papers are found on rerun.

### Gaps
- No empirical evaluation exists of any matcher on economics references (NBER, SSRN, IZA or CEPR versus journal), and no data on how often titles change between a WP and its journal version.
- The current RePEc matching pipeline (the only description is from 2009) and the API's terms for a shared tool.
- Score ranges for `matchScore` in Semantic Scholar and `score` in Crossref, which differ by query length.

## 5. How are reference strings parsed from PDFs and Word files, and how accurate is it?

### Takeaway
GROBID (Apache-2.0) is the best-documented open parser. Its v0.9.0 benchmark on PubMed Central (1,943 PDFs, 90,125 references) gives field-level micro-F1 of 83.1 (strict) to 87.6 (Levenshtein). Only 44.0 to 63.2 F1 of references are parsed *entirely* correctly. Linking in-text citations to their references scores 76.3 F1, and consolidation brings DOI resolution above 0.95 F1. Studies of hallucination checkers find extraction errors to be a leading cause of failure. The skill should therefore prefer LaTeX `.bib`/`.bbl` input or Word citation field codes. For PDFs it should match raw reference strings by search, as SBMV does, rather than trust parsed fields, or use LLM extraction as RefChecker does.

### Cited Findings
- **GROBID's own summary.** Reference extraction scores "around .87 F1-score" on PMC 1,943 (90,125 references) and "around .90" on 2,000 bioRxiv PDFs with the deep-learning citation model. References parsed in isolation score above .90 instance-level F1 and .95 field-level F1. Citation-context resolution scores ".76 and .91". The default configuration uses CRF; deep-learning models "perform significantly better" for reference parsing — [GROBID README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)
- **GROBID v0.9.0 end-to-end, PMC 1,943** — [Benchmarking-pmc.md](https://github.com/kermitt2/grobid/blob/HEAD/doc/benchmarks/Benchmarking-pmc.md):

  | Measure | Strict | Soft | Levenshtein |
  |---|---|---|---|
  | Field-level micro-F1, all fields | 83.13 | 86.35 | 87.63 |
  | Field-level F1, title | 76.85 | 88.12 | 90.29 |
  | Field-level F1, authors | 78.77 | 79.22 | 84.64 |
  | Instance-level F1 (whole reference correct) | 44.03 | 57.72 | 63.2 |

  - Field-level F1 for date is 88.46.
  - 90,125 references were expected and 85,510 extracted.
  - Citation contexts: precision 84.55, recall 69.53, F1 76.31.
  - Runtime was 0.75 s per PDF on 16 CPUs with a GPU.
- **GROBID on bioRxiv (2,000 preprints, 98,799 references).** Instance-level F1 is 44.22 strict, 55.3 soft and 59.55 Levenshtein — [Benchmarking-biorxiv.md](https://github.com/kermitt2/grobid/blob/HEAD/doc/benchmarks/Benchmarking-biorxiv.md)
- **Consolidation.** Using biblio-glutton raised header metadata F1 from 74.59 to 88.89 in GROBID 0.5.6. Consolidation runs through Crossref (the default) or biblio-glutton — [Consolidation.md](https://github.com/kermitt2/grobid/blob/HEAD/doc/Consolidation.md). A Python client is available under Apache-2.0 (grobid-client-python 0.2.1, 2026-10-16) — [grobid_client_python](https://github.com/kermitt2/grobid_client_python), [PyPI](https://pypi.org/project/grobid-client-python/)
- **CERMINE (Java).** Extracts metadata, full text and parsed references, has a stand-alone reference-string parser (`CRFBibReferenceParser`), and outputs JATS or BibTeX. The web demo is for fewer than 50 files. Version 1.13, AGPL-3.0. Its paper is Tkaczyk et al., IJDAR 2015 — [CERMINE README](https://raw.githubusercontent.com/CeON/CERMINE/HEAD/README.md)
- **AnyStyle (Ruby).** Has a machine-learning "finder" and "parser", aimed at being easy to train on your own data, and outputs structured fields (author family and given names, date, title, publisher, type) — [AnyStyle README](https://raw.githubusercontent.com/inukshuk/anystyle/HEAD/README.md). anystyle 1.6.0 and anystyle-cli 1.5.0, both 2025-05-11, BSD-2-Clause — [RubyGems](https://rubygems.org/gems/anystyle)
- **refextract (INSPIRE-HEP).** Extracts journal references written in physics style, such as "J.Phys.,A39,13445". GPL-2.0-or-later, v1.1.7 released 2026-10-01; it "cannot be locally installed on a mac" — [README](https://raw.githubusercontent.com/inspirehep/refextract/HEAD/README.md), [PyPI](https://pypi.org/project/refextract/)
- **LLM extraction.** RefChecker prefers LLM extraction and falls back to GROBID; it reports "Claude Sonnet 4 performs best for extraction; GPT-4o may hallucinate DOIs" — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md)
- **Heuristic extraction.** Hallucinator extracts text with MuPDF, finds the "References" or "Bibliography" heading, and repairs split diacritics. It lists "PDF extraction — Bad PDF formatting can mangle references" among its limitations — [README](https://raw.githubusercontent.com/gianlucasb/hallucinator/HEAD/README.md), [matching.rs](https://github.com/gianlucasb/hallucinator/blob/HEAD/hallucinator-rs/crates/hallucinator-core/src/matching.rs). HalluCiteChecker depends on docling — [PyPI](https://pypi.org/project/hallucitechecker/)
- **Independent finding.** Badalova and Mayr list "reference extraction errors, incomplete metadata, limited database coverage, and inconsistent verification results" as the main limitations of the tools they tested — [arXiv 2607.22693 (search summary)](https://arxiv.org/html/2607.22693v2)
- **Search-based matching skips parsing.** Crossref's SBMV, which matches unstructured strings directly, beat parse-then-match on F1 (96.3% against 92.5%) — [Crossref blog](https://www.crossref.org/blog/reference-matching-for-real-this-time/). biblio-glutton reached 96.4 F1 on raw strings extracted by GROBID — [biblio-glutton Benchmarking](https://github.com/kermitt2/biblio-glutton/blob/HEAD/doc/Benchmarking.md)
- **Word.** Zotero's Word integration stores each citation as a field whose code is `ITEM CSL_CITATION {CSL-JSON}`, and it recognizes Mendeley item URIs when re-linking — [Zotero integration.js](https://github.com/zotero/zotero/blob/HEAD/chrome/content/zotero/xpcom/integration.js)

### Inferences
- **Per-format plan.**
  - LaTeX: parse `.bib` or `.bbl` directly (bibtexparser or pybtex, both MIT), with no PDF parsing.
  - Word: first read citation field codes from `document.xml` (Zotero CSL-JSON, Mendeley, EndNote), which give exact structured metadata and the in-text-to-reference link for CIT-01. Fall back to text parsing (AnyStyle or GROBID) for references typed by hand.
  - PDF: run GROBID with deep-learning citation models, or an LLM, for segmentation. Always match the raw string by search, not only the parsed fields. Keep the raw string in the finding as the quote.
- **CIT-01 from PDFs.** GROBID's citation-context F1 of 76% shows that automatic linking misses many links. Unmatched in-text citations from a PDF should be "needs human judgment" or verified by regex for author–date patterns ("Author (Year)", "Author et al., Year", with a/b year suffixes) before being reported as Major.
- **False positives from parsing.** Instance-level accuracy of 44–63% means that a parsed field which disagrees with the database could be a parsing error rather than an error in the paper. CIT-03 diffs on PDF input need a confidence downgrade, or a check that the disputed text really appears in the PDF; DESIGN.md's verify_quotes.py fits this.

### Gaps
- No accuracy numbers retrieved for CERMINE or AnyStyle, nor the head-to-head parser comparison by Tkaczyk et al. (JCDL 2018), which could not be fetched.
- No accuracy data for economics reference styles (author–date with long working-paper entries).
- The EndNote and Mendeley field-code formats in Word were not checked against primary sources.

## 6. What do studies report about fabricated references, and what lessons follow for a checker?

### Takeaway
LLMs fabricate references at high rates. Walters and Wilder (2023) found 55% of GPT-3.5 citations and 18% of GPT-4 citations fabricated. An economics-specific study (Buchanan et al., 2024) found more than 30% for GPT-3.5 and more than 20% for GPT-4. A 2026 audit of 10 LLMs found 11.4% to 56.8%. Fabricated references now reach the published record:
- 1 in 277 PubMed-indexed papers in early 2026, up from 1 in 2,828 in 2023 (Topaz et al., *Lancet*);
- about 1 in 20 NeurIPS and USENIX Security 2025 papers with at least two likely hallucinated references (Russinovich et al.);
- GPTZero: 50 of 300 sampled ICLR 2026 submissions, and 100 citations in 51 NeurIPS 2025 papers.

Checkers are good at screening but should not deliver verdicts. Badalova and Mayr find current tools not reliable enough for final decisions. Benchmark disputes show that definitions drive the numbers, and HALLMARK argues that the false-positive rate decides whether a verifier can be deployed.

### Cited Findings
- **Walters and Wilder, *Scientific Reports* 13:14045 (September 2023).** ChatGPT wrote short literature reviews on 42 topics, producing 636 citations. 55% of GPT-3.5 citations and 18% of GPT-4 citations were fabricated. Among the real ones, 43% (GPT-3.5) and 24% (GPT-4) had substantive errors — [PMC10484980](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10484980/)
- **Buchanan, Hill and Shapoval, *The American Economist* 69(1):80–87 (2024).** More than 30% of the citations ChatGPT (GPT-3.5) suggested for economics topics do not exist. A GPT-4 rerun gave "over 20%". Accuracy "declines as the question becomes more specific". The working paper appeared on SSRN in June 2023 — [Economist Writing Every Day, 2023-06-04](https://economistwritingeveryday.com/2023/06/04/new-paper-with-evidence-that-chatgpt-hallucinates-nonexistent-citations/), [GPT-4 follow-up](https://economistwritingeveryday.com/tag/research-methods/)
- **Naser, "How LLMs Cite and Why It Matters" (arXiv 2603.03299).** A search summary gives the submission date as 7 February 2026, which conflicts with the identifier's March 2026 prefix. 10 commercial LLMs across four domains produced 69,557 citation instances, verified against Crossref, OpenAlex and Semantic Scholar. Hallucination rates ranged from 11.4% to 56.8%, depending on model, domain and prompt framing. No model produced formal citations unless asked — [arXiv 2603.03299 (search summary)](https://arxiv.org/pdf/2603.03299)
- **Topaz et al., *Lancet* research letter (2026-05-07).**
  - Scope: about 2.5 million open-access PMC papers from January 2023 to February 2026, checked against PubMed, Crossref, OpenAlex and Google Scholar. AI was used to separate true fabrications from formatting problems such as abbreviated journal titles.
  - Paper-level rates: about 1 in 2,828 in 2023, 1 in 458 in 2025, and 1 in 277 in the first seven weeks of 2026, with the sharpest rise from mid-2024.
  - Retraction Watch reports 4,406 fabricated references in 2,810 papers; other summaries give 4,046. In February more than 98% had seen no publisher action.
  - Mohammad Hosseini called the analysis "simplistic" because it does not distinguish critical references from minor ones.
  - [Retraction Watch](https://retractionwatch.com/2026/05/07/one-in-277-pubmed-indexed-papers-in-2026-shows-fabricated-references-says-analysis/), [Infodocket](https://www.infodocket.com/2026/05/07/report-one-in-277-pubmed-indexed-papers-in-2026-shows-fabricated-references-says-analysis/), [CASRAI](https://casrai.org/news/fabricated-citations-1-in-277-pubmed-lancet-audit)
- **Russinovich, Siva Kumar and Salem, "Phantom References" (arXiv 2607.00738, 2026-07-01).** Accepted papers at ICLR, ICML, NeurIPS and USENIX Security were audited with RefChecker, counting only identity-level failures. Reference-level rates are "usually below 1%", but in 2025 roughly one in twenty NeurIPS and USENIX Security papers had at least two likely hallucinated references. Rates rose after ChatGPT, some papers had five or more failures, and failures appeared even in award-winning papers. Cost was about $0.04 per paper — [docs/PAPER.md](https://github.com/markrussinovich/refchecker/blob/HEAD/docs/PAPER.md), [arXiv abstract](https://arxiv.org/abs/2607.00738), [The Decoder](https://the-decoder.com/hallucinated-references-are-passing-peer-review-at-top-ai-conferences-and-a-new-open-tool-wants-to-fix-that/)
- **GPTZero audits.** ICLR 2026: 50 of 300 sampled submissions. NeurIPS 2025: 100 hallucinated citations in 51 of 4,841 scanned papers (Fortune says 53). Fabricated references included invented authors, wrong journals, blends of several real papers, and arXiv IDs that point to a different article — [GPTZero ICLR](https://gptzero.me/news/iclr-2026/), [Fortune](https://fortune.com/2026/01/21/neurips-ai-conferences-research-papers-hallucinations/), [feedbagel summary](https://feedbagel.com/post/gptzero-analysis-finds-100-hallucinations-in-neurips-2025-accepted-papers), [GIGAZINE](https://gigazine.net/gsc_news/en/20260123-gptzero-finds-100-hallucinations-neurips-2025). A taxonomy study of these 100 NeurIPS citations ("Compound Deception") relies only on GPTZero-flagged items, so it cannot measure recall — [arXiv 2602.05930 (search summary)](https://arxiv.org/pdf/2602.05930)
- **Badalova and Mayr (GESIS), arXiv 2607.22693 (July 2026).** They tested CheckIfExist, HalluCiteChecker, Hallucinator, HalRef and RefChecker on a manually verified set of 104 references from three documents (71 verified, 33 problematic). The tools "proved useful for initial screening and flagging" but "their performance was not sufficiently reliable to support definitive decisions without further verification". They call for transparent multi-source systems. The dataset is on Zenodo and "should not be used to estimate the prevalence" of hallucinated citations — [arXiv 2607.22693 (search summary)](https://arxiv.org/html/2607.22693v2), [Zenodo dataset](https://zenodo.org/records/21457492). RefChecker's README cites the dataset under a different Zenodo DOI, 10.5281/zenodo.23236264 — [README](https://raw.githubusercontent.com/markrussinovich/refchecker/HEAD/README.md). A Pith review says the numbers in Table 4 need a documented annotation protocol — [Pith (search summary)](https://pith.science/paper/2607.22693)
- **Benchmarks:**
  - HALLMARK sorts 14 citation-hallucination types into three tiers, from DOIs that fail to resolve up to near-miss titles, and argues that the false-positive rate, not recall, decides whether a verifier can be deployed — [arXiv 2607.18360 (search summary)](https://arxiv.org/pdf/2607.18360)
  - CiteAudit pairs real citations from OpenReview and Google Scholar with synthetic hallucinated ones — [CiteAudit](https://www.alphaxiv.org/abs/2602.23452)
  - CiteTracer's benchmark has 2,450 citations in three classes, Real, Potential and Hallucinated; it reports 97.1% accuracy and class F1 of 97.0, 95.8 and 98.5 — [arXiv 2605.08583 (search summary)](https://arxiv.org/pdf/2605.08583)
- **A Nature analysis (2026)** reportedly suggests that "tens of thousands of publications from 2025 might include invalid references generated by AI". This is known only through forum summaries of article d41586-026-00969-z, a weak source — [Physics Forums thread](https://www.physicsforums.com/posts/7307843/)

### Inferences
Lessons for the skill:
1. **Define classes before counting.**
   - Non-existent work: Critical, only after DOI failure and multi-source search.
   - Chimeric citation: a real title with the wrong authors, or a DOI or arXiv ID that resolves to a different paper. Major, or Critical if the authors are entirely different.
   - Metadata drift (year, venue, pages): Minor.
   - Status drift (a preprint now published): Suggestion.
   
   This mirrors RefChecker's identity-level definition and the disputes between GPTZero and CiteTracer, and it fits DESIGN.md guardrail 3.
2. **Optimize for low false positives.** A false "fabricated" flag on a coworker's real economics reference is costly. Follow HALLMARK's emphasis on the false-positive rate and abstain to "unverified" with the exact queries listed.
3. **Use several sources and keep the evidence.** Every verdict should carry the closest record found, field similarities and the queries made, as GPTZero's per-citation card and RefChecker's report records do. That gives DESIGN.md its proof and trajectory.
4. **Use the LLM as a last stage with strict rules.** Require a dedicated page for the work, not a mention in someone else's bibliography, then re-verify against the metadata the LLM found (RefChecker stage 3).
5. **Plan for economics coverage gaps.** Working papers, book chapters, government reports and data sets are poorly indexed in CS-oriented sources. Hallucinator's and RefChecker's caveats about books, reports and new work apply even more strongly in economics. Add RePEc, DataCite and web search before concluding "not found".
6. **Build a small labeled test set.** Include behavioral-economics references: real NBER and SSRN working papers and their published versions, retracted and EoC items such as the Shu et al. 2012 PNAS paper and Mazar et al. 2008 JMR, plus known-fake references generated by an LLM. Badalova and Mayr's 104-reference dataset is a template but should not be used for prevalence.
7. **Calibrate expectations.** At reference level, fabrication rates in published work are low (under 1%). At paper level they matter: about 5% of ML papers had two or more. In drafts written with LLM help the rate can be much higher. The 11–57% rates come from unconstrained LLM generation, not from human-curated drafts.

### Gaps
- No study found that measures fabricated-reference rates in economics papers that were submitted or published, as opposed to LLM-generated lists.
- Per-tool precision and recall from Badalova and Mayr, the category breakdown from the "Compound Deception" taxonomy, and details of the 2026 Nature analysis.
- Findings of "Detecting and Correcting Reference Hallucinations in Commercial LLMs and Deep Research Agents" (arXiv 2604.03173), which was not retrieved.
