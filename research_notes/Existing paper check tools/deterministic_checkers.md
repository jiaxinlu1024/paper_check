# Deterministic manuscript checkers: statistics consistency tools, writing and LaTeX linters, format compliance checkers, and research-integrity screeners

Research date: 2026-10-17. Scope: rule-based and statistical tools that a "paper check" Claude Code skill for behavioral-economics drafts (LaTeX, PDF, Word) could call or reimplement, mapped to the DESIGN.md groups FMT, NUM, LANG, FIG and ETH. Method note: GitHub files were read through raw.githubusercontent.com or shallow clones (all deleted afterwards), package metadata through the PyPI JSON API and the npm registry, and `pdffonts` and `pdfinfo` were run locally. Many hosts were unreachable from this session, including arxiv.org, uhasselt.be, peerreviewcongress.org, vale.sh, nongnu.org, matt.might.net, ctan.org, the vendor sites and Homebrew. The shared WebSearch budget ran out partway through. Claims about those sources come from search-result snippets and are marked as such.

## 1. Statistics consistency tools (statcheck, the GRIM family, p-curve and z-curve, and economics regression tables)

### Takeaway
Psychology has a mature, mostly R-based toolkit: statcheck for APA-style in-text tests; scrutiny for GRIM, GRIMMER and DEBIT; rsprite2 and unsum for SPRITE and CLOSURE; and zcurve. There are Python ports: `statcheck` on PyPI, ScrutiPy and pysprite. These are young (statcheck, ScrutiPy) or stale (pysprite). The one validated automated approach for economics regression tables is DORIS, a research tool by Bruns et al. It checks significance stars against coefficient and standard error and has a 1.2% false discovery rate. No installable, maintained package for that check was found. The skill should therefore implement a Pütz–Bruns/DORIS-style star check itself, plus GRIM and DEBIT for means and shares. These are short arithmetic routines whose reference implementations are MIT-licensed.

### Cited Findings

#### statcheck (R package and web app)
- **What and how:** statcheck is a "spellchecker for statistics". It finds APA-style NHST results such as "t(28) = 2.2, p < .05" and recomputes p from the test statistic and degrees of freedom. A mismatch is flagged as an *inconsistency* (`error`). If the reported p is significant and the recomputed one is not, or vice versa, it is flagged as a *gross inconsistency* (`decision_error`). — [statcheck README](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/README.md)
- **Test types and settings:** It recognizes t, F, r, z, χ² and Q tests (Q from meta-analyses), but only when the test statistic, df and p are all reported, in APA style. It accounts for correct rounding of the test statistic and can optionally account for one-tailed tests. The pipeline has four steps: convert PDF or HTML to text, search, recompute, compare. — [statcheck README](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/README.md)
- **Inputs and outputs:** It accepts a text string, a PDF or HTML file, or a folder of them. The point-and-click web interface at statcheck.io scans PDF, HTML or DOCX. Output is a data frame of extracted tests with `error` and `decision_error` flags. — [statcheck DESCRIPTION](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/DESCRIPTION); [README](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/README.md)
- **Maturity, license and dependencies:** The GitHub development version is 1.6.1.9000, dated 2026-01-26. The license is GPL-3. Imports are ggplot2, plyr, rlang, rmarkdown, stringi, tcltk, stringr and pdftools. Version 1.6.0 replaced the external Xpdf program with the R package pdftools. The DESCRIPTION text still says Xpdf is needed, so the documentation is inconsistent. — [DESCRIPTION](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/DESCRIPTION); [NEWS](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/NEWS.md)
- **Recent fixes that show what parsing has to handle:**
  - better chi-square reading from HTML and PDF (1.6.1.9000)
  - no warning when a minus sign is used as a dash after a test (1.6.1.9000)
  - narrow no-break spaces in HTML, which caused problems in JESP 2019 articles (1.5.0)
  - one-tailed p computed from the tail area with rounding, rather than p/2 (1.4.0)
  - results with multiple comparison signs, such as "t(38) >= 2.25", are no longer extracted (1.4.0)
  - wrongly encoded minus signs are detected (1.4.0)

  Source: [NEWS](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/NEWS.md)
- **Regex structure, useful for a port:**
  - separate df patterns for t, r and Q `\(\s?\d*\.?\d+\s?\)`, F `(df1, df2)`, and χ² with an optional `N = n`
  - a p pattern `p\s?[<>=]\s?\d?\.\d+(?:[eE]-?\d+)?`, which handles exponent forms
  - an "n.s." pattern
  - a thousands-separator pattern
  - a "weird minus" pattern

  Source: [statcheck R/regex.R](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/R/regex.R)
- **Accuracy (validity preprint, Nuijten et al. 2017):** Sensitivity was 85.3–100% and specificity 96.0–100%, depending on assumptions and settings. Overall accuracy was 96.2–99.9%. — [Tilburg research portal](https://research.tilburguniversity.edu/en/publications/the-validity-of-the-tool-statcheck-in-discovering-statistical-rep/); [OSF](https://osf.io/3cvkn) (search snippets)
- **Coverage:** An ICOTS paper by Nuijten reports that statcheck detected about 60% of reported NHST results. This is recall of extraction, not sensitivity. — [ICOTS10 8B2](https://icots.info/10/proceedings/pdfs/ICOTS10_8B2.pdf) (search snippet)
- **Input quality:** PDF-to-text conversion is less reliable than HTML, so HTML input is recommended. — [PMC review article](https://pmc.ncbi.nlm.nih.gov/articles/PMC7540394) (search snippet)
- **Critiques:**
  - Schmidt (2016): statcheck cannot handle corrected p-values. Properly corrected tests can be flagged while uncorrected ones pass. — [arXiv 1610.01010](https://arxiv.org/pdf/1610.01010) (search snippet)
  - Böschen (2024), "statcheck is flawed by design and no valid spell checker for statistical results": he tested 187 short strings covering standard reports, unsupported tests, varied styles and typos. statcheck only recognizes strict APA style. He concludes it should not be used to flag irregularities, and suggests JATSdecoder or LLMs as more flexible alternatives. — [arXiv 2408.07948](https://arxiv.org/html/2408.07948v1) (search snippet)
- **Effect in peer review:** Nuijten & Wicherts (2024, *AMPPS*, doi 10.1177/25152459241258945) ran a preregistered pretest-posttest quasi-experiment on more than 7,000 articles and more than 147,000 statistics. Inconsistencies declined considerably more steeply in the two journals that adopted statcheck (*Psychological Science*, *JESP*) than in the matched controls. — [APS AMPPS page](https://www.psychologicalscience.org/journals/ampps/25152459241258945/); [Tilburg](https://research.tilburguniversity.edu/en/publications/implementing-statcheck-during-peer-review-is-related-to-a-steep-d/)
  - A press account reports 4.5% fewer errors in the statcheck journals against about 1% in the controls. This was not verified against the paper. — [ACM TechNews](https://cacmb4.acm.org/news/271041-spell-checker-for-statistics-reduces-errors-in-psychology-literature)
- **Economics:** A BITSS post notes that economics has no APA-like standard for reporting results in the text, so psychology tools such as statcheck cannot easily check economics tables. — [BITSS](https://www.bitss.org/searching-30000-psychology-articles-for-statistical-errors/)
- **Other front ends:** the statcheck Shiny web app, and a simplified edition by Steve Haroz. — [scrutiny "Related software" vignette](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/vignettes/related.Rmd)

#### statcheck Python port (PyPI `statcheck`)
- **What it is:** A "Python implementation of the R package 'statcheck'", ported from R statcheck version 1.4.0-beta.4 with the original tests recoded in Python. Version 0.0.7 was uploaded 2025-09-17; the first upload was 2022-12-20. — [PyPI](https://pypi.org/project/statcheck/); [README](https://raw.githubusercontent.com/hplisiecki/statcheck_python/HEAD/README.md)
- **Install and license:** It is a pure-Python wheel. Dependencies are numpy, pandas, scipy, PyPDF2, beautifulsoup4 and matplotlib. The license text is GPL v3, but the trove classifier says GPLv2, so the metadata conflict. — [PyPI JSON](https://pypi.org/pypi/statcheck/json)

#### JATSdecoder `get.stats()` and tableParser (R, Ingmar Böschen)
- **JATSdecoder 1.3.1 (2026-04-09), GPL-3:** `get.stats()` extracts statistical results from text and recomputes p-values for many standard test statistics. It checks reported against recomputed p and estimates sample size from the abstract and the reported df. PDFs must first be converted to NISO-JATS with CERMINE, or read with pdftools, where tables "may cause corrupt text". — [DESCRIPTION](https://raw.githubusercontent.com/ingmarboeschen/JATSdecoder/HEAD/DESCRIPTION); [README](https://raw.githubusercontent.com/ingmarboeschen/JATSdecoder/HEAD/README.md)
- **Other extractors:** `get.sig.adjectives()` (inadequate adjectives before "significant"), `get.multiple.comparison()`, `get.power()`, `get.alpha.error()`. There is a web app at get-stats.app. The evaluation paper is Böschen (2021), *Scientific Reports* 11:19525; its numbers were not retrieved. — [README](https://raw.githubusercontent.com/ingmarboeschen/JATSdecoder/HEAD/README.md)
- **tableParser, GPL-3:** DESCRIPTION says version 1.0.5 (2026-04-09); the README says 1.0.6.
  - It extracts tables from JATS XML, HTML, DOCX and PDF. PDF extraction uses tabulapdf and cannot read captions or footnotes, so PDF results are "less precise".
  - It collapses each table to text the way a screen reader would.
  - It can decode p-value codings defined in captions and footnotes: stars, and bold or italic marking (`decodeP`).
  - It extracts t, Z, χ², F, r, d, β, SE, η², ω², OR, RR and p, recomputes p and flags errors.
  - `noSign2p` treats unmarked cells as non-significant, which "may result in false positive imputations".
  - For correlation matrices it imputes df as N − 2.
  - Preprint: arXiv:2603.19756 (2026).

  Source: [tableParser README](https://raw.githubusercontent.com/ingmarboeschen/tableParser/HEAD/README.md); [DESCRIPTION](https://raw.githubusercontent.com/ingmarboeschen/tableParser/HEAD/DESCRIPTION)

#### Economics regression tables: Pütz & Bruns (2021) and DORIS
- **Pütz & Bruns (2021), *Journal of Economic Surveys* 35(1):348–373, doi 10.1111/joes.12397:** They checked about 31,000 hypothesis tests from 370 articles in three top economics journals. A *reporting error* is a mismatch between the significance stars and the p-value recalculated from the reported coefficient and standard error.
  - About 36% of articles have at least one error, but only 1.3% of tests do.
  - *Strong* errors, where one signal says significant and the other does not, affect 0.5% of tests and 21.6% of articles.
  - Errors are biased toward stars that signal significance the recalculated p does not support.

  Source: [RePEc/IDEAS](https://ideas.repec.org/a/bla/jecsur/v35y2021i1p348-373.html); [UHasselt record](https://documentserver.uhasselt.be/handle/1942/32738) (search snippets; one snippet says "roughly a third" of articles)
- **DORIS (Bruns, Herwartz, Ioannidis, Islam, Raters):** The tool checks whether significance stars in economics tables match the reported statistics. It scrapes coefficients and standard errors from **HTML** article tables in R and interprets them with Python text mining.
  - Coverage: 578,132 tests from the top 50 economics journals.
  - Prevalence: 14.88% of articles have at least one strong error in their main tests.
  - Validation: a 1.2% false discovery rate on 3,068 checked tests.
  - Policy finding: mandatory data-and-code policies significantly reduce "overstated" errors, and top-5 journals are not less error-prone.
  - Status: working paper, DOI 10.31222/osf.io/mbx62. The manuscript's file name ("20240223_Statistical_reporting_errors_in_economics…") suggests a 2024-02-23 version.

  Source: [UHasselt record](https://documentserver.uhasselt.be/handle/1942/42667); [DFG GEPRIS project 405039391](https://gepris.dfg.de/gepris/projekt/405039391/ergebnisse) (search snippets)
- **Conflicting coverage figures:** A Peer Review Congress abstract describes 15,725 tables in 3,746 articles from **31** journals, with a median of 27 tests per table. The preprint says **50** journals, and neither source explains the difference. — [PRC abstract](https://peerreviewcongress.org/abstract/automated-interpretation-of-statistical-tables-to-assess-reporting-errors-and-associations-with-open-science-policies-in-economics-journals/) (search snippet)

#### GRIM, GRIMMER and DEBIT (R scrutiny; Python ScrutiPy)
- **GRIM (Brown & Heathers 2017, *SPPS* 8(4):363–369):** It tests whether a reported mean of integer data, such as a Likert item, is possible for the stated N.
  - Of 260 articles, 71 were testable, 36 had at least one impossible mean and 16 had several.
  - The authors requested data for 21 flagged articles and received 9 datasets; all 9 had at least one reporting error.

  Source: [Wikipedia: GRIM test](https://en.wikipedia.org/wiki/GRIM_test); [PeerJ preprint](https://peerj.com/preprints/2064.pdf)
- **scrutiny (R, Lukas Jung) 0.6.1, MIT since 0.5.0:**
  - GRIM, including percentages via `percent = TRUE`
  - GRIMMER for SDs (citing Allard 2018's analytic GRIMMER)
  - DEBIT for the mean and SD of binary data (Heathers & Brown 2019, https://osf.io/5vb3u/)
  - duplicate detection, rounding utilities (`unround`, `reround`), and a framework for writing new consistency tests
  - a Shiny "Error detection" app

  Source: [DESCRIPTION](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/DESCRIPTION); [README](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/README.md)
- **scrutiny accuracy caveats:**
  - 0.6.1 shows a warning whenever GRIMMER runs, because of a known bug that can produce **false positives in test 3** (#80).
  - 0.6.0 fixed a DEBIT bug that could return `FALSE` when the answer should be `TRUE`; the changelog notes "DEBIT is not widely used".
  - 0.5.0 requires means as strings, to keep trailing zeros. It added a `probability` column: the chance that a random mean with that many decimals is GRIM-inconsistent (for example 0.6 for two decimals with n = 40).

  Source: [scrutiny NEWS](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/NEWS.md)
- **ScrutiPy 0.1.12 (2026-01-13), MIT, "Alpha":** A Python front end with a Rust back end (PyO3), "based on the R Scrutiny library". It offers `grim_scalar`, `grim_map` (pandas and polars), `grimmer`, `debit` and `debit_map`, plus CLOSURE and confusion-matrix recalculation. Wheels exist for macOS, Windows and Linux. — [PyPI](https://pypi.org/project/scrutipy/); [README](https://raw.githubusercontent.com/nrposner/scrutipy/HEAD/README.md); [scrutiny related software](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/vignettes/related.Rmd)

#### SPRITE, CLOSURE and CORVIDS (reconstructing possible raw data)
- **SPRITE** (Heathers et al. 2018, doi:10.7287/peerj.preprints.26968v1) generates possible discrete distributions from a mean, SD and range. **rsprite2** (R, MIT, development version 0.2.1.9002) builds on Nick Brown's rSPRITE Shiny app and supports multi-item Likert scales and restrictions on response frequencies. — [rsprite2 DESCRIPTION](https://raw.githubusercontent.com/LukasWallrich/rsprite2/HEAD/DESCRIPTION)
- **pysprite** is a Python 3 reimplementation, MIT, version 1.2.1, marked "Beta". Its last upload was 2019-07-10, so it has not been updated in more than seven years. Jordan Anaya also built a Python SPRITE web app. — [PyPI](https://pypi.org/project/pysprite/); [README](https://raw.githubusercontent.com/QuentinAndre/pysprite/HEAD/README.md); [related software](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/vignettes/related.Rmd)
- **CLOSURE in unsum** (R, MIT, 0.3.0) exhaustively lists every sample consistent with a mean, SD, n and scale bounds. Its core is in Rust (closure-core), and building from source needs Cargo and rustc. It is computationally intensive, and the README suggests SPRITE when CLOSURE is too slow. The README calls it "the ultimate consistency test". The original Python implementation is by Nathanael Larigaldie. — [unsum README](https://raw.githubusercontent.com/lhdjung/unsum/HEAD/README.md); [DESCRIPTION](https://raw.githubusercontent.com/lhdjung/unsum/HEAD/DESCRIPTION)
- **CORVIDS** (Wilner, Wood & Simons 2018) is written in Python and ships standalone Mac and Windows GUIs. It returns all solutions for Likert data but "takes very long to run, often prohibitively so". — [CORVIDS README](https://raw.githubusercontent.com/katherinemwood/corvids/HEAD/README.md); [unsum README](https://raw.githubusercontent.com/lhdjung/unsum/HEAD/README.md)

#### RIVETS
- In scrutiny's current source, RIVETS exists only as **commented-out development code**, ported from Nick Brown (https://osf.io/7fdxh/). The code describes the method as: "Simulate 'perfect t statistics' from M/SD/N or b/SE". The planned functions are `rivets_perfect_mean_sd()`, `rivets_perfect_b_se()` and `rivets_t_test()`. — [rivets-t-test.R](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/R/rivets-t-test.R); [rivets_new.R](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/R/rivets_new.R)

#### Bounds checks and newer summary-statistic tools (Ian Hussey)
- **strait** is the R package served from the `ianhussey/tides` repository (MIT, "experimental"). `brimmer()` computes the smallest and largest SD attainable for a given mean, n and scale bounds, and flags a reported SD outside that range as inconsistent. — [strait README](https://raw.githubusercontent.com/ianhussey/tides/HEAD/README.md)
- The related **ANCHOR** app checks a whole sample against its subgroups, and the **PORT** app tests correlation tables for consistency. — [scrutiny related software](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/vignettes/related.Rmd)

#### p-checker, p-curve and z-curve
- **p-checker** (Felix Schönbrodt) is a Shiny app implementing p-curve, the R-Index and TIVA (Test of Insufficient Variance), and it "checks whether p-values are reported correctly". Its code is adapted from Uri Simonsohn's. The README lists open TODOs, such as separating inference from UI code and making TIVA robust to outliers. — [p-checker README](https://raw.githubusercontent.com/nicebread/p-checker/HEAD/README.md)
- **zcurve** (R) 2.4.6, GPL-3, by Bartoš & Schimmack, estimates expected discovery and replicability rates from the test statistics of published studies, using density, EM and censored-EM fits. — [zcurve DESCRIPTION](https://raw.githubusercontent.com/FBartos/zcurve/HEAD/DESCRIPTION)

#### metacheck (formerly papercheck): the closest existing analog to the planned skill
- **What it is:** R, AGPL-3 or later, version 0.1.0 (2026-06-16), lifecycle "experimental". It describes itself as "a modular, extendable system for checking research outputs for best practices using text search, R code, and/or (optional) LLM queries". It imports statcheck and the LLM client ellmer. The authors are DeBruine, Mesquida, Werner and Lakens. — [metacheck DESCRIPTION](https://raw.githubusercontent.com/scienceverse/metacheck/HEAD/DESCRIPTION); [README](https://raw.githubusercontent.com/scienceverse/metacheck/HEAD/README.md); [papercheck moved notice](https://raw.githubusercontent.com/scienceverse/papercheck/HEAD/README.md)
- **Modules at HEAD (2026-09-20):**
  - statistics: `stat_check` (statcheck), `stat_effect_size` (effect sizes in t and F tests), `stat_p_exact` (imprecise p such as "p < .05", "n.s." or "p = .000"), `stat_p_nonsig` (warns about misreading p > .05), `all_p_values`, `marginal` ("marginally significant")
  - claims and design: `causal_claims` (randomization and causal language in title or abstract), `power`
  - statements: `coi_check`, `funding_check`, `open_practices`, `prereg_check`
  - code and links: `repo_check`, `code_check`, `all_urls`
  - references: `ref_consistency` (cited vs. listed), `ref_accuracy` (against CrossRef), `ref_retraction` (Retraction Watch), `ref_pubpeer`, `ref_replication` (FLoRA database), `ref_miscitation` (a proof of concept whose database is not yet populated), `ref_summary`

  Source: [metacheck modules](https://github.com/scienceverse/metacheck/tree/main/inst/modules) (read via shallow clone)
- **Input:** PDFs go through GROBID, either a local server at localhost:8070 or an online one; by default this is now a GDPR-compliant server at TU Eindhoven. A converter called "bibr" is the only route for DOC and DOCX. — [R/import-convert.R](https://raw.githubusercontent.com/scienceverse/metacheck/HEAD/R/import-convert.R); [NEWS](https://raw.githubusercontent.com/scienceverse/metacheck/HEAD/NEWS.md)

### Inferences
- **Recall on economics papers will be low.** statcheck's APA-only scope, about 60% recall and the Böschen critique imply this for economics drafts. Economists rarely write "t(df) = x, p = y" in the text, and lab papers often report nonparametric tests (Mann–Whitney, Wilcoxon, Fisher exact), which statcheck does not support. The NUM-03 script should port statcheck's ideas and extend the grammar to "z = …", "χ²(1) = …" with N, "two-sided Mann–Whitney U test, p = …" and "(p < 0.05)". When only U and group sizes are reported, the normal approximation is the most a script can do, so those cases should be "needs human judgment".
- **The highest-value economics check is a DORIS-style star check on regression tables, done with rounding intervals.** The recipe:
  1. Take the reported b (k_b decimals) and SE (k_s decimals).
  2. Form b ∈ [|b| − 0.5·10^−k_b, |b| + 0.5·10^−k_b] and SE ∈ [SE − 0.5·10^−k_s, SE + 0.5·10^−k_s].
  3. Compute t_min = b_lo/SE_hi and t_max = b_hi/SE_lo, then the p-range under N(0,1). Use t(df) when the residual df, or G − 1 for cluster-robust SEs with G clusters, is known.
  4. Flag only when the whole p-range falls outside the interval implied by the stars. Read the star thresholds from the table note; economics usually uses * 0.10, ** 0.05, *** 0.01.
  5. Call it a "strong" error, following Pütz & Bruns, when the 5% conclusion flips.
  6. Downgrade to "needs human judgment" when the df assumption changes the verdict. This is common in behavioral economics, where errors are often clustered by session with few clusters.

  The same parse supports more checks: t = b/SE when t-statistics are in parentheses, p in brackets, 95% CI ≈ b ± 1.96·SE, R² in [0, 1], and an "Observations" row consistent across tables and with N in the text (NUM-05). tableParser's caption and footnote star decoding, and its warning about false-positive imputations, show how to read table notes.
- **GRIM, DEBIT and bounds checks fit behavioral-economics reporting.** Such papers report shares of subjects choosing an option (percent with N), Likert means and binary means with SDs. These checks are exact arithmetic: GRIM (is p·N/100 an integer within rounding?), DEBIT (SD of a 0/1 variable = sqrt(m(1−m)·N/(N−1)) within rounding) and strait-style bounds on the SD. They are ideal SCRIPT checks. GRIMMER should stay "flagged cautiously" (the DESIGN default), because the reference implementation currently warns about false positives. SPRITE and CLOSURE are better kept for a deep mode, since they are expensive and their output (possible distributions) needs interpretation.
- **Licensing pattern.** The arithmetic tools are MIT: scrutiny, ScrutiPy, rsprite2, unsum and pysprite. The text-mining extractors are copyleft: statcheck (GPL-3) and its Python port, JATSdecoder and tableParser (GPL-3), zcurve (GPL-3) and metacheck (AGPL-3). If the skill is shared beyond the team, the safest course is to reimplement from the published method descriptions, since algorithms and regex ideas can be re-expressed, or to call these tools as optional external processes rather than vendoring their code. This is a licensing judgment, not legal advice.
- **ScrutiPy is the best fit for an optional Python dependency.** It has macOS and Windows wheels and an MIT license. It is alpha, though. Because GRIM and DEBIT are about 20 lines each, vendoring a reimplementation, with tests copied conceptually from scrutiny's examples (`pigs1`–`pigs3`), is just as cheap.
- **metacheck's module list is a ready checklist that maps onto DESIGN IDs:**

  | metacheck module | DESIGN ID |
  |---|---|
  | `stat_check`, `stat_p_exact` | NUM-03 |
  | `marginal` | LANG-04 and LOG-09 |
  | `causal_claims` | LOG-03 |
  | `coi_check`, `funding_check` | ETH-02 |
  | `open_practices` | MTH-03 |
  | `prereg_check` | MTH-07 |
  | `power` | MTH-04 |
  | `ref_consistency` | CIT-01 |
  | `ref_retraction` | CIT-05 |

  Its design choice of regex first with an optional LLM mirrors the skill's SCRIPT-then-READ approach. It depends on GROBID for PDFs, which is a Java service and heavy for a laptop.
- **p-curve and z-curve are meta-analytic.** On one paper with a handful of focal tests they have little power. They are better left out of the default mode, or offered only as a "suggestion" in deep mode.

### Gaps
- **p-curve app (p-curve.com):** its current version, input syntax and license could not be checked, because the site was not fetched and the search budget was exhausted. From background knowledge (unverified): the app takes lines such as "t(38)=2.1", and its R code is posted on the site.
- **StatReviewer:** no current information was retrieved. From background knowledge (unverified): it is an automated statistical and reporting-guideline reviewer by Timothy Houle and Chadwick DeVoss (NEX7), trialled around 2016–2018 with BMC and Springer Nature journals. Its 2026 status is unknown.
- **GRIMMER:** the original paper (Anaya 2016, PeerJ Preprints) and the DEBIT and RIVETS preprints were not read. The RIVETS method details are known only from the comments in scrutiny's code.
- **DORIS code:** whether the code is public, and its license, could not be determined because the UHasselt PDF host was DNS-blocked. Its recall (as opposed to its FDR) was not found.
- **Validation figures** for JATSdecoder `get.stats()` (Sci Rep 2021) and tableParser (arXiv 2603.19756) were not retrieved.
- **CRAN release versions and dates** for statcheck, scrutiny, unsum and rsprite2 were not verified; only GitHub HEAD versions are given above.

## 2. Writing and LaTeX linters

### Takeaway
A skill running offline on a coworker's laptop has three light options:
- **Vale:** one Go binary, MIT, offline, with rules written in YAML.
- **proselint:** installed with pip, BSD-3.
- **Ported regex lists:** Matt Might's weasel-word, passive-voice and duplicate-word scripts, as carried into Academic-Writing-Check and write-good, run on LaTeX-stripped text with an offset map back to `file:line`.

TeXtidote's LaTeX-structure rules (GPL-3, Java) and ChkTeX's typography checks (in maintenance mode, 1.7.9 released 2024-04-26) are best reimplemented in Python, or called when they are already installed. Real grammar checking needs LanguageTool (LGPL, Java 17, heavy), through LTeX+ or language_tool_python, or Harper (Rust, English only, fast). No academic-writing Vale style package was found.

### Cited Findings

#### ChkTeX
- **Release and status:** The latest release is 1.7.9, released 2024-04-26 by Ivan Andrus. It is mostly bug fixes, such as using "SeenSpace" to avoid a false positive on spacing. The project says development is "in maintenance mode", and development has moved to a Savannah git repository. — [nongnu.org/chktex](https://www.nongnu.org/chktex) (search snippet); [Debian NEWS](https://sources.debian.org/src/chktex/1.7.9-2/NEWS); [CTAN announcement](https://ctan.org/ctan-ann/id/mailman.8580.1715099207.3764.ctan-ann@ctan.org)
- **Packaging:** Debian uploaded 1.7.9-1 on 2024-05-06. — [Launchpad/Ubuntu](https://blueprints.launchpad.net/ubuntu/+source/chktex/1.7.9-1)

#### TeXtidote (Sylvain Hallé)
- **What and how:** TeXtidote strips LaTeX markup and checks the result with its own rules. With `--check en` it also runs LanguageTool, which adds more than 2,000 grammar and spelling rules but takes considerably longer. `--languagemodel` enables LanguageTool's n-gram data.
  - Output formats are console, `singleline` and an HTML report.
  - `--ignore` takes rule IDs; `--remove` and `--remove-macros` drop environments and macros; `--replace` applies replacements.
  - `--clean` prints the cleaned text, and `--map` writes a position map alongside it.
  - The exit code equals the number of warnings, so CI needs "continue-on-error".
  - Markdown is also supported, but without the LaTeX-specific rules.

  Source: [TeXtidote Readme](https://raw.githubusercontent.com/sylvainhalle/textidote/HEAD/Readme.md)
- **Rules, directly reusable for FMT-04/05/06/07/09/10:**

  | Area | Rules |
  |---|---|
  | Section titles | capital letter (sh:001); no ending punctuation (sh:002); not all caps (sh:003) |
  | Capitalized references | 'Section X', 'Table X', 'Figure X' (sh:secmag, sh:tabmag, sh:figmag) |
  | Captions | end with a period (sh:capperiod) |
  | Citation spacing | one space before `\cite` or `\ref` (sh:c:001), none after (sh:c:002) |
  | Citation usage | no "in [X]" (sh:c:noin); don't mix `\cite` with `\citep`/`\citet` (sh:c:mix); one `\cite` with several keys (sh:c:mul, sh:c:mulp) |
  | Figures | every figure labeled and referenced (sh:figref) |
  | Structure | no lone subsection (sh:nsubdiv); first heading has the highest level (sh:secorder); no skipped levels (sh:secskip); no stacked headings (sh:stacked) |
  | Hard-coding | no local paths in figures (sh:relpath); no hard-coded section, figure or table numbers (sh:hcfig, sh:hctab, sh:hcsec); no `\\` line breaks in paragraphs (sh:nobreak); no `\newpage` (sh:nonp) |
  | LaTeX spacing | "i.e.", "e.g." and "et al." spacing (sh:010, sh:011); no space before ";" or ":" (sh:d:005, sh:d:006) |
  | Section length | at least 100 words between headings (sh:seclen) |

  Source: [TeXtidote Readme, "Rules checked"](https://raw.githubusercontent.com/sylvainhalle/textidote/HEAD/Readme.md)
- **Install and maturity:** It is a single JAR needing Java 8 or later, with a `.deb` for Debian and Ubuntu. The license is GPL-3. `config.xml` says version 0.9, while CITATION.cff lists "version: 0.9, date-released 2021-12-18". The last commit was 2026-09-09, from a shallow clone. — [Readme](https://raw.githubusercontent.com/sylvainhalle/textidote/HEAD/Readme.md); [config.xml](https://raw.githubusercontent.com/sylvainhalle/textidote/HEAD/config.xml); [CITATION.cff](https://raw.githubusercontent.com/sylvainhalle/textidote/HEAD/CITATION.cff); [LICENSE](https://raw.githubusercontent.com/sylvainhalle/textidote/HEAD/LICENSE)

#### LanguageTool, language_tool_python, LTeX LS and LTeX+
- **LanguageTool core:** LGPL. The README lists "Portuguese, Polish, Dutch, and more than 20 other languages". It can run as your own HTTP server, a command line, a GUI or a Java API. Building needs Java 17 and Maven. A shallow clone downloads under 60 MiB and needs under 200 MiB on disk. Version 6.8 was released 2026-05-05, and 6.9 is unreleased. — [LanguageTool README](https://raw.githubusercontent.com/languagetool-org/languagetool/HEAD/README.md); [CHANGES.md](https://raw.githubusercontent.com/languagetool-org/languagetool/HEAD/languagetool-standalone/CHANGES.md)
- **language_tool_python 3.4.0 (2026-05-14), GPL-3.0-only, pure-Python wheel:** It runs a local LanguageTool server, which needs Java 17 or later and downloads LanguageTool 6.8 by default, or uses the public API or your own remote server. — [PyPI](https://pypi.org/project/language-tool-python/); [README](https://raw.githubusercontent.com/jxmorris12/language_tool_python/HEAD/README.md)
- **LTeX LS (valentjn):** MPL-2.0. It is a Language Server Protocol server that checks LaTeX, BibTeX, ConTeXt, Markdown, Org, Quarto, reStructuredText, R Markdown, Sweave and XHTML with LanguageTool. It "comes with everything included, no need to install Java or LanguageTool" and does "offline checking". — [ltex-ls README](https://raw.githubusercontent.com/valentjn/ltex-ls/HEAD/README.md)
- **LTeX+ LS:** It continues LTeX LS after version 16.0.0, since Julian Valentin developed it "until version 16.0.0", and adds Typst, MDX, AsciiDoc and Neorg. It keeps the bundled, offline design. — [ltex-ls-plus README](https://raw.githubusercontent.com/ltex-plus/ltex-ls-plus/HEAD/README.md)
- **Cost of LanguageTool, according to the Harper project:** LanguageTool needs "gigabytes of RAM" and "the ~16GB n-gram dataset" for its best results, and takes "several seconds" on a moderate document. This is a competitor's claim. — [Harper README](https://raw.githubusercontent.com/Automattic/harper/HEAD/README.md)

#### Harper (Automattic)
- It is an English-only grammar checker written in Rust. It claims to lint in milliseconds with "less than 1/50th of LanguageTool's memory footprint", is "completely private", and is small enough to run as WebAssembly. It is distributed as `harper-ls` (crates.io), harper.js (npm), and editor and Obsidian plugins. — [Harper README](https://raw.githubusercontent.com/Automattic/harper/HEAD/README.md)

#### Vale
- **What it is:** a prose linter framework that "doesn't ship opinions of its own". It runs "on macOS, Windows, and Linux, entirely offline" as "one binary, nothing alongside it", written in Go.
  - Install: `brew install vale`, `choco install vale` or `winget install errata-ai.Vale`.
  - It parses Markdown, AsciiDoc, reStructuredText, HTML and other formats so rules can target scopes.
  - A style is a folder of YAML rules, and packages such as Microsoft, Google and Red Hat are one config line away.
  - MIT license. The current Go module path is github.com/vale-cli/vale.

  Source: [Vale README](https://raw.githubusercontent.com/errata-ai/vale/HEAD/README.md)
- **Packages and formats:** Packages are zip files pulled in through `.vale.ini` with `vale sync`; official ones include Microsoft, Google and write-good. Vale targets plain-text markup rather than word-processor files. — [LWN](https://lwn.net/Articles/964075) (search snippet); [mintlify Vale docs](https://www.mintlify.com/errata-ai/vale/reference/cli/sync) (search snippet)
- **No academic style package:** none was found. One curated list mentions "academic custom" styles without a link. — [ecosyste.ms awesome list](https://awesome.ecosyste.ms/projects/291494) (search snippet)

#### proselint
- Version 0.16.0 (2025-11-14), BSD license, Python 3.10 or later. It depends on google-re2 and installs with pip, apt, dnf or nix. — [PyPI](https://pypi.org/project/proselint/); [README](https://raw.githubusercontent.com/amperser/proselint/HEAD/README.md)
- Checks relevant to the skill include `annotations` (annotations left in the text, which bears on FMT-11), `hedging` (LANG-03), `lexical_illusions` (repeated words), `misc.metadiscourse`, `misc.latin`, `misc.phrasal_adjectives`, `misc.preferred_forms`, `nonwords`, `oxymorons`, `cliches.*` and `dates_times.*`. Checks can be selected per file in JSON configuration. — [proselint README "Checks"](https://raw.githubusercontent.com/amperser/proselint/HEAD/README.md)

#### write-good, alex and textlint (Node)
- **write-good 1.0.8:** published 2021-02-16, MIT, unpacked size about 42 kB. Its checks are passive, illusion (repeated word), so, thereIs, weasel, adverb, tooWordy, cliches and eprime, each built on a small npm module (passive-voice, weasel-words and others). The author says it was "based on" Matt Might's weasel-word shell script, and it lists Academic Writing Check as similar. — [npm registry](https://registry.npmjs.org/write-good); [README](https://raw.githubusercontent.com/btford/write-good/HEAD/README.md)
- **alex 11.0.1:** published 2023-08-18, MIT. It catches "insensitive, inconsiderate writing" (gendered, polarizing or race-related phrasing; for example "his" leads to the suggestion "their"). It reads plain text, HTML, MDX and Markdown, and is built on retext-equality and retext-profanities. — [npm registry](https://registry.npmjs.org/alex); [readme](https://raw.githubusercontent.com/get-alex/alex/HEAD/readme.md)
- **textlint 15.8.0:** MIT, needs Node 20.18.0 or later. Its LaTeX plugin, textlint-plugin-latex2e 1.2.1, was last published 2023-05-17. The plugin's README announced "Maintainers wanted" and said the repository "may be archived" if maintenance could not continue after 2026-09-30, a date that has now passed. — [npm textlint](https://registry.npmjs.org/textlint/latest); [npm plugin](https://registry.npmjs.org/textlint-plugin-latex2e); [plugin README](https://raw.githubusercontent.com/textlint/textlint-plugin-latex2e/HEAD/README.md)

#### Matt Might's scripts and Academic-Writing-Check
- Matt Might's blog post, "shell scripts for passive voice, weasel words, duplicates", is cited as the origin of both Academic-Writing-Check and write-good. — [Academic-Writing-Check README](https://raw.githubusercontent.com/devd/Academic-Writing-Check/HEAD/README.markdown); [write-good README](https://raw.githubusercontent.com/btford/write-good/HEAD/README.md) (the post itself was unreachable: http://matt.might.net/articles/shell-scripts-for-passive-voice-weasel-words-duplicates/)
- **Academic-Writing-Check (`checkwriting`, Perl, Devdatta Akhawe):**
  - Checks: passive, dups (repeated word across two lines), weasel, abbr ("i.e", "et. al"), typography (footnote before punctuation, numbers without comma, URLs not in `\url`), Strunk-and-White word list, and a user word list.
  - It skips lines starting with `%` and reads `*.tex` and `*.bbl` from a directory.
  - It accepts `git diff` on stdin so only new text is checked.
  - The last commit was 2018-12-10, and the repository has **no LICENSE file**.

  Source: [README](https://raw.githubusercontent.com/devd/Academic-Writing-Check/HEAD/README.markdown); [checkwriting](https://raw.githubusercontent.com/devd/Academic-Writing-Check/HEAD/checkwriting)
- **Exact rules in `checkwriting`:**
  - Passive voice: `\b(am|are|were|being|is|been|was|be)\b\s+(\w+ed|<irregular participles>)\b`
  - Duplicates: `\b(\w+)(\s+)(\1)\b`
  - Weasel words: might, appears to be, it is easy to see, theoretically, actual, In this paper, almost, many, various, very, fairly, several, extremely, exceedingly, quite, remarkably, few, surprisingly, mostly, largely, huge, tiny, (are|is) a number, excellent, interestingly, significantly, substantially, clearly, vast, relatively, completely.

  Source: [checkwriting source](https://raw.githubusercontent.com/devd/Academic-Writing-Check/HEAD/checkwriting)

#### arxiv-latex-cleaner (Google Research)
- Version 1.0.11 (2026-03-27), Apache-2.0, Python 3.9 or later, installed with pip or `brew install arxiv_latex_cleaner`. It writes a cleaned copy to a new `*_arXiv` folder.
  - It removes auxiliary files and **all comments**, including `\begin{comment}`, `\iffalse` and `\if0` blocks.
  - It can optionally delete user commands such as `\todo{}` (`commands_to_delete`) and apply custom regex rules from YAML.
  - It removes unused `.tex` files and images, can resize images, can compress PDFs with Ghostscript (Linux and Mac only), and can conceal TikZ source.

  Source: [README](https://raw.githubusercontent.com/google-research/arxiv-latex-cleaner/HEAD/README.md); [PyPI](https://pypi.org/project/arxiv-latex-cleaner/)

### Inferences
- **Recommended LANG stack, light and offline:**
  1. Strip LaTeX with pylatexenc (MIT, pure Python), keeping a character-offset map to `file:line`, the way TeXtidote's `--clean --map` does.
  2. Run Python ports of the Might/Academic-Writing-Check regexes and of write-good's check categories (weasel, passive, adverbs, "there is", lexical illusions) for LANG-02/04/08.
  3. Optionally run proselint, which installs with pip, for hedging and annotations.
  4. Optionally run Vale with a custom style written for the team (econ terms vocabulary, banned hype words). It works on Windows and macOS with one binary.

  LanguageTool, LTeX+ or Harper should be optional add-ons with honest "skipped: not installed" coverage lines, because LanguageTool needs Java 17 and a large download.
- **TeXtidote's rule list is the best ready-made specification for the LaTeX structure checks** (FMT-04/05/06/07/09/10). Every rule is regex or AST-level and easy to reimplement in Python. Reimplementing avoids a Java dependency and GPL-3 code; re-expressing a rule list is not copying code. ChkTeX's typographic warnings (dashes, interword spacing, quote marks) complement it for FMT-10.
- **Avoid the GPL wrapper's license constraints.** language_tool_python is GPL-3.0-only, while LanguageTool itself is LGPL. Calling the LanguageTool HTTP server directly with a few lines of `requests` code sidesteps the wrapper's terms if that matters.
- **For FMT-11, the skill should not run arxiv-latex-cleaner, because the skill reports only.** It can copy the idea instead: list comments, `\iffalse` blocks and `\todo` macros that would ship in an arXiv source upload, and quote them with line numbers.
- **Word lists need economics tuning.** "Significantly" is a weasel word in the Might list, but it is a technical term in economics. LANG-04 should flag "significant(ly)" only when no test is nearby, which is a COMPARE step, not a blanket rule. Expect high false-positive rates from passive-voice rules in methods sections, so those belong at "Suggestion" severity.

### Gaps
- **lacheck:** CTAN was blocked and no search snippet was obtained, so maintenance and license are unverified. From background knowledge (unverified): it is an old LaTeX checker distributed with TeX Live.
- **ChkTeX:** the license and its availability in TeX Live, MacTeX and MiKTeX were not verified in this session. It is believed to be GPL and bundled with major TeX distributions (unverified).
- **Vale's LaTeX support:** whether Vale reads `.tex` natively or only through a conversion program could not be confirmed, because docs.vale.sh and vale.sh were DNS-blocked. Vale's current version and release date were also not retrieved.
- **Install sizes** of the LanguageTool desktop zip, LTeX+ and Harper binaries, and Harper's license and LaTeX support were not retrieved; only the clone-size figures and Harper's claims above are known. The LTeX+ current version and release date were not retrieved.
- **Matt Might's original scripts:** the post's text, its license and the exact list of irregular verbs could not be read, because the site was unreachable; the Perl derivative was used instead.

## 3. Format and compliance checkers (venue checks, PDF checks, Word checks)

### Takeaway
aclpubcheck (MIT, Python 3.10 or later, last commit 2026-10-07) is the only open, actively maintained venue format checker examined. It is a good template for PDF geometry checks: A4 size, text or images bleeding into margins, page limit found from the page where "References" or "Limitations" starts, the main font and bibliography heuristics, with JSON output plus annotated PNG pages. Poppler's `pdffonts` and `pdfinfo` cover fonts embedded or subset, Type 3 fonts, page size, Creator and Producer, and XMP metadata. Python libraries can do the same without poppler: pikepdf (MPL-2.0) or pypdf (BSD-3); PyMuPDF is AGPL. Word hygiene can be fully deterministic by reading the OOXML parts: `w:ins`, `w:del` and `w:pPrChange` for tracked changes, `comments.xml`, `w:vanish` for hidden text, and `docProps` for author fields. Commercial manuscript-check services could not be verified in this session.

### Cited Findings

#### aclpubcheck (ACL)
- **What it checks:** "font errors, author formatting errors, margin violations, outdated citations, and other issues" in papers that use ACL LaTeX styles. It is meant for camera-ready PDFs. On anonymized versions with line numbers it "may produce spurious margin errors". — [aclpubcheck README](https://raw.githubusercontent.com/acl-org/aclpubcheck/HEAD/README.md)
- **How it checks (`formatchecker.py`):**
  - error classes Size, Parsing, Margin, Spelling, Font, Page Limit, and the warning class Bibliography
  - page size must be A4 (595 × 842 pt)
  - margin bleed of text or images, with image crops used to discard false positives
  - the bottom area of about 2 cm must stay blank (`--disable_bottom_check` turns this off)
  - page limits: short 5, long 9, demo 7. Overflow is detected from the page where the first of "References", "Acknowledgments", "Limitations", "Ethics Statement" or "Broader Impact" appears.
  - the most-used font must cover at least 35% of characters and be a Times-family font such as `NimbusRomNo9L-Reg`
  - bibliography warnings: few ACL Anthology DOIs, few links, and "more than you should" arXiv references

  Source: [formatchecker.py](https://raw.githubusercontent.com/acl-org/aclpubcheck/HEAD/aclpubcheck/formatchecker.py)
- **Metadata and citation names:** It checks that the title and author order in the submission metadata match the PDF text; "only removed or re-ordered (not added) authors will be caught". A separate step extracts citation author names through the **Scholarcy API** and fuzzy-matches them against the ACL Anthology, DBLP and arXiv to flag outdated names. This step needs a network connection, and its warnings can be spurious. — [metadatachecker.py](https://raw.githubusercontent.com/acl-org/aclpubcheck/HEAD/aclpubcheck/metadatachecker.py); [README](https://raw.githubusercontent.com/acl-org/aclpubcheck/HEAD/README.md)
- **Outputs:** a per-paper `errors-<id>.json` plus annotated `errors-<id>-page-N.png` files for margin errors (`--output-dir`). It can be used online through Google Colab or a Hugging Face Space. — [README](https://raw.githubusercontent.com/acl-org/aclpubcheck/HEAD/README.md)
- **Install, license and maintenance:** Python 3.10 or later. Install from GitHub with `uvx --from git+https://github.com/acl-org/aclpubcheck` or `pip install git+…`; it depends on rebiber pinned to a GitHub commit. MIT license, © 2022 ACL. The last commit was 2026-10-07, but the PyPI release (0.2.0, 2022-10-10, requiring Python 3.8 or later) is stale. PyPI dependencies include pdfplumber, pybtex, pylatexenc and rebiber. — [README](https://raw.githubusercontent.com/acl-org/aclpubcheck/HEAD/README.md); [LICENSE](https://raw.githubusercontent.com/acl-org/aclpubcheck/HEAD/LICENSE); [PyPI](https://pypi.org/project/aclpubcheck/)

#### PDF technical checks (poppler `pdffonts` and `pdfinfo`; Python libraries)
- **`pdffonts`** (poppler 24.02.0, run locally) prints one row per font with the columns `name, type, encoding, emb, sub, uni, object ID`. On a test PDF made with LibreOffice it printed `BAAAAA+LiberationMono TrueType WinAnsi yes yes yes`. A "XXXXXX+" name prefix together with `sub = yes` marks a subset font. The options are `-f/-l` for a page range and `-subst` to show font substitutions. — local run of poppler 24.02.0 ([poppler](https://poppler.freedesktop.org))
- **`pdfinfo`** (poppler 24.02.0, run locally) prints Creator, Producer, CreationDate, Custom Metadata, Metadata Stream, Tagged, Form, JavaScript, Pages, Encrypted, Page size (labeled, for example "595.304 x 841.89 pts (A4)"), File size and PDF version. Options include `-meta` (XMP metadata), `-custom`, `-box`, `-url` (URLs in PDF objects), `-js`, `-struct` and `-isodates`. — local run of poppler 24.02.0
- **Python alternatives and their licenses:**
  - pikepdf 10.17.0 (2026-10-11), MPL-2.0, wraps qpdf, ships wheels for macOS, Windows and Linux, and needs Python 3.11 or later.
  - pypdf 6.21.1 (2026-10-17), BSD-3, pure Python.
  - pdfplumber 0.11.10 (2026-06-15), MIT, built on pdfminer.six and pypdfium2.
  - PyMuPDF 1.28.2 (2026-08-06) is dual-licensed: "GNU AFFERO GPL 3.0 or Artifex Commercial License".

  Source: [PyPI pikepdf](https://pypi.org/project/pikepdf/); [PyPI pypdf](https://pypi.org/project/pypdf/); [PyPI pdfplumber](https://pypi.org/project/pdfplumber/); [PyPI PyMuPDF](https://pypi.org/project/PyMuPDF/)

#### Word (.docx) hygiene: tracked changes, comments, hidden text, properties
- **Tracked changes** are stored as revision markup: `w:ins` (insertions), `w:del` (deletions) and `w:pPrChange` (a revision to paragraph properties). Each carries `w:author` and `w:date` attributes, for example `<w:pPrChange w:id="0" w:date="…" w:author="Samantha Smith">`. — [Microsoft Open XML SDK docs: accept all revisions](https://raw.githubusercontent.com/OfficeDev/open-xml-docs/HEAD/docs/word/how-to-accept-all-revisions-in-a-word-processing-document.md)
- **Comments** live in a separate comments part with root `w:comments` and `w:comment` children, which carry ids and author initials. They are anchored in the body by `w:commentReference` with a matching id. — [Open XML docs: retrieve comments](https://raw.githubusercontent.com/OfficeDev/open-xml-docs/HEAD/docs/word/how-to-retrieve-comments-from-a-word-processing-document.md)
- **Hidden text** is the `w:vanish` run property ("Hidden Text"), which is a toggle property. — [Open XML docs: remove hidden text](https://raw.githubusercontent.com/OfficeDev/open-xml-docs/HEAD/docs/word/how-to-remove-hidden-text-from-a-word-processing-document.md)
- **docx2python 3.7.1 (2026-08-06), MIT, pure Python:** It extracts headers, footers, footnotes, endnotes, images and **comments** (as reference_text, author, date, comment_text tuples) and **document properties** such as `creator` and `lastModifiedBy`. — [docx2python README](https://raw.githubusercontent.com/ShayHill/docx2python/HEAD/README.md); [PyPI](https://pypi.org/project/docx2python/)
- **python-docx 1.2.0 (2025-06-16), MIT:** "Add support for comments". The release history read does not mention tracked-change (revision) support. — [python-docx HISTORY](https://raw.githubusercontent.com/python-openxml/python-docx/HEAD/HISTORY.rst)

### Inferences
- **FMT-01/15 can be reimplemented from aclpubcheck's logic with pdfplumber (MIT)** rather than calling aclpubcheck itself, since its hard-coded A4, Times font and ACL page limits do not fit economics venues. The pieces to reuse are character and image boxes compared with margin rectangles, page-limit detection from the page of the "References" heading, main-font share, and JSON output plus PNG evidence crops. The PNG crops fit the DESIGN's VISUAL proof trail. Its caveat about review versions with line numbers should become a note in the report.
- **FMT-15 and FMT-02 from the PDF:**
  - flag `type = Type 3` and `emb = no` rows from `pdffonts`
  - check page size against the venue profile
  - read `pdfinfo -meta` and Author, Creator and Producer for anonymity, for example a Word or LaTeX user name in Author
  - list `-url` links to check repository usernames

  Without poppler, pikepdf or pypdf cover document info and XMP. Avoid making PyMuPDF a hard dependency if the AGPL matters for how the skill is shared.
- **FMT-14 from Word, by direct ZIP and XML reading:**
  - count `w:ins`, `w:del`, `w:moveFrom`, `w:moveTo` and `w:pPrChange`/`w:rPrChange` elements in `word/document.xml`, with author and date
  - list comments from `word/comments.xml` (docx2python works)
  - find `w:vanish` runs and quote their text
  - read `docProps/core.xml` (creator, lastModifiedBy) and `docProps/app.xml` (company, template) for FMT-02
  - detect stale fields (TOC, REF) by looking for field codes

  All of this is pure Python with lxml and works the same on macOS and Windows. The element names come from the Open XML docs; `w:moveFrom`, `w:moveTo` and `w:rPrChange` are the standard counterparts but were not separately verified here.
- **For a .docx, rendering to PDF with LibreOffice before running the PDF checks** is consistent with DESIGN §2. LibreOffice is often not installed on a coworker's laptop, so this step should be optional and reported as skipped when unavailable.

### Gaps
- **Penelope.ai** (automated journal technical checks), **Paperpal Preflight** (Cactus), **IEEE PDF eXpress**, and other journal manuscript-check services were not researched successfully: the search budget ran out and the vendor sites were DNS-blocked. Their current status, checks and pricing as of 2026 are unknown. From background knowledge (unverified): Penelope.ai checks structure, required statements, references and figure citations against journal rules; IEEE PDF eXpress checks font embedding and PDF compatibility.
- **No economics-venue format checker** (for example for AEA journals, Econometrica, Experimental Economics or Management Science) was found. Venue profiles will have to be written by hand.
- **Microsoft Word's built-in Document Inspector** documentation was not fetched.
- **Install routes for poppler on macOS and Windows** (for example `brew install poppler`) were not verified in this session.

## 4. Research-integrity screeners and what can be done locally

### Takeaway
The best-known integrity screeners depend on proprietary full-text databases or machine-learning services. These include the Problematic Paper Screener (PPS), whose tortured-phrase detector queries Dimensions; Clear Skies; the image-forensics tools Proofig and ImageTwin; SciScore; Ripeta; and iThenticate. Locally and without a commercial database, a skill can do four things:
1. Regex "fingerprint" matching: a small tortured-phrase seed list plus AI-leftover phrases. PPS's own team reports a regex-based detector that needs no Dimensions subscription.
2. Within-paper detection of near-duplicate images with perceptual hashing (ImageHash, BSD-2).
3. Detection of transparency statements in the style of ODDPub, rtransparent or metacheck, using keywords and regex. ODDPub's 2026 open-code validation gave sensitivity 0.94 and specificity 0.82.
4. Retraction checks against the Retraction Watch data, which is already planned in DESIGN via Crossref.

### Cited Findings

#### Problematic Paper Screener (Cabanac, Labbé, Magazinov) and tortured phrases
- **What it is:** PPS automatically flags suspect publications for post-publication reassessment. It includes fingerprints for computer-generated text and for synonym-based plagiarism ("tortured phrases", for example "fake neural organization" for "artificial neural network"). The tortured-phrase detector queries the Dimensions database, about 130 million articles. — [PPS preprint, arXiv 2210.04895](https://arxiv.org/pdf/2210.04895) (search snippet)
- **List size over time:**
  - 276 tortured phrases in the 2022 preprint
  - about 4,000 in a 2024 conference paper
  - 6,545 fingerprints in a later paper
  - "more than 7000" suspect expressions in a Peer Review Congress abstract
  - "more than 7,900 confirmed pairs" in a 2026 blog post (not verified against a primary source)

  The exact attribution of each count to each paper was not verified. — [arXiv 2401.02422](https://arxiv.org/pdf/2401.02422); [arXiv 2502.04944](https://arxiv.org/pdf/2502.04944); [PRC regex-detector abstract](https://peerreviewcongress.org/abstract/screening-articles-for-tortured-phrases-with-a-regular-expressions-based-detector); [journalmetrics blog](https://www.journalmetrics.org/blog/tortured-phrases-medical-publishing-integrity-2026) (all search snippets)
- **Regex alternative:** a Peer Review Congress study describes a **regular-expression-based** tortured-phrase detector that does not need a Dimensions subscription, and notes that some fingerprints need redesign. — [PRC abstract](https://peerreviewcongress.org/abstract/screening-articles-for-tortured-phrases-with-a-regular-expressions-based-detector) (search snippet)
- **Social sciences:** tortured phrases have also been documented in the humanities and social sciences, not only in STEM. — [arXiv 2502.04944, "Unveiling tortured phrases in Humanities and Social Sciences"](https://arxiv.org/pdf/2502.04944) (search snippet)
- **Public access:** the public PPS interface lets users search a phrase and see its hits, and a Datawrapper chart shows tortured phrases found by PPS. No official downloadable copy of the full phrase list was found. — [Language Log](https://languagelog.ldc.upenn.edu/nll/?p=54046); [Datawrapper chart](https://datawrapper.dwcdn.net/d2qtw/7) (search snippets)

#### Image-integrity tools (Proofig, ImageTwin, FigCheck) and local alternatives
- **Proofig:** Its pricing page lists one-year packages from $99 for 120 sub-images up to $610 for 1,020 sub-images (a 27% discount). Enterprise pricing is custom and adds SSO and API access; individuals pay as they go by sub-image count. Proofig announced detection for graphs, charts, diagrams and plots, beyond life-science images. — [Proofig pricing](https://proofig.com/pricing-page); [Proofig news](https://www.proofig.com/news/image-integrity-moves-beyond-the-life-sciences-proofig-ai-now-detects-graphs-charts-diagrams-and-plots/) (search snippets)
- **ImageTwin:** developed by Markus Zlabinger and sold by subscription. It processes one PDF or about 20 screenshots at a time and compares against "a large database of open source papers". — [MSKCC Library pilot blog](https://library.mskcc.org/blog/?p=35262) (search snippet)
- **Anecdotal comparison:** Proofig is "very good with Western blots, with fewer false positives than ImageTwin, but slower". This is anecdotal, from the same set of search results; which page said it is uncertain. — [MSKCC Library](https://library.mskcc.org/blog/?p=35262); [Science Integrity Digest FAQ](https://scienceintegritydigest.com/frequently-asked-questions/)
- **STM comparison:** an STM Integrity consultation table compares ImageTwin, FigCheck, ImaCheck and Proofig on image types and duplicate detection. The document itself was DNS-blocked. — [STM IAC comparison PDF](https://stm-assoc.org/wp-content/uploads/2024/09/STM-IAC-Consultation-Comparison_DEC_JvR_Dec9.pdf) (search snippet)
- **Local alternatives:**
  - ImageHash 4.3.2 (2025-02-01), BSD-2, pure-Python wheel; dependencies PyWavelets, numpy, pillow and scipy.
  - imagededup 0.3.3.post2 (2025-08-15), Apache-2.0. It finds exact and near duplicates with PHash, DHash, WHash, AHash or a CNN, but it requires torch and torchvision.

  Source: [PyPI ImageHash](https://pypi.org/project/ImageHash/); [PyPI imagededup](https://pypi.org/project/imagededup/); [imagededup README](https://raw.githubusercontent.com/idealo/imagededup/HEAD/README.md)

#### Transparency indicators (ODDPub, rtransparent, metacheck)
- **ODDPub 7.4.0 (2025-11-13), R, AGPL-3 or later** (Riedel; maintained by Nachev at BIH QUEST): It detects Open Data and Open Code statements from publication PDFs, converted through pdftools. It searches keyword categories, including field-specific repositories, and the repository list can be extended or replaced through YAML. It returns TRUE/FALSE plus the detected statement. The README warns that performance is lower outside biomedicine, "due to unfamiliar discipline-specific repository names". — [ODDPub README](https://raw.githubusercontent.com/quest-bih/oddpub/HEAD/README.md); [DESCRIPTION](https://raw.githubusercontent.com/quest-bih/oddpub/HEAD/DESCRIPTION)
- **ODDPub accuracy:**
  - Open code, v7.3.0, validated 2026-07-21: 3,725 Charité/BIH articles from 2025 were screened, and 100 positives plus 100 negatives were checked by hand. Accuracy 0.87, sensitivity 0.94, specificity 0.82, PPV 0.79, NPV 0.95, F1 0.86. Most false positives were generic landing pages or empty repositories.
  - Open data, legacy version: sensitivity 0.73 and specificity 0.97 on 792 PubMed papers. A new open-data validation is planned for Q4 2026.

  Source: [ODDPub README "Validation"](https://raw.githubusercontent.com/quest-bih/oddpub/HEAD/README.md)
- **rtransparent 0.2.5, R, GPL-3** (Serghiou): It identifies data availability, code availability, conflicts of interest, funding and protocol registration from TXT files (made from PDFs) and PubMed Central XML, and it depends on oddpub. It was validated in a bioRxiv preprint (10.1101/2020.10.30.361618). The README "Coming soon" section is still unfinished. — [rtransparent README](https://raw.githubusercontent.com/serghiou/rtransparent/HEAD/README.md); [DESCRIPTION](https://raw.githubusercontent.com/serghiou/rtransparent/HEAD/DESCRIPTION)
- **metacheck modules** `coi_check`, `funding_check`, `open_practices`, `prereg_check`, `ref_retraction` (with a Retraction Watch database bundled and updated in the package) and `ref_pubpeer` cover the same ground with regex plus optional LLM. — [metacheck modules](https://github.com/scienceverse/metacheck/tree/main/inst/modules); [NEWS](https://raw.githubusercontent.com/scienceverse/metacheck/HEAD/NEWS.md)

### Inferences
- **ETH-07 locally:**
  1. Extract embedded images from the PDF, or render figure regions with pdftoppm or pypdfium2.
  2. Compute pHash and dHash with ImageHash, which is light, rather than imagededup, which pulls in torch.
  3. Flag pairs within a small Hamming distance, including rotated and flipped variants.
  4. Show both crops as VISUAL evidence.

  This covers duplicated panels within a paper. It cannot do cross-literature matching, which is what ImageTwin's database adds. Behavioral-economics papers are mostly plots and screenshots, so expect few hits. A duplicate plot with a different caption is still worth flagging.
- **ETH-06 and FMT-12 locally:** keep a small curated fingerprint file with tortured-phrase pairs from published examples and AI-assistant leftovers, and match it with regex, as the PRC regex detector does. Clean drafts should yield little. The value is a cheap guard plus honest coverage reporting.
- **ETH-02 and MTH-03:** reimplement ODDPub and rtransparent-style keyword categories in Python for economics: data and code availability, funding, conflicts, preregistration such as the AEA RCT Registry, and IRB approval. Replace the biomedical repository list with economics ones. Candidates are openICPSR/AEA Data Editor, Harvard Dataverse, Zenodo, OSF and GitHub; this list is a suggestion and was not taken from any source. ODDPub's validation shows that keyword detection reaches high sensitivity with moderate specificity, so the matched statement should be quoted for the READ step to confirm.
- **iThenticate, Clear Skies, SciScore and Ripeta cannot be reproduced locally**, because they need proprietary databases or trained classifiers. The report's coverage table should say "not performed (no database access)" rather than imply a pass, consistent with DESIGN §8.4.

### Gaps
- **Clear Skies Papermill Alarm:** two searches returned only unrelated results before the budget ran out. Its method, accuracy and pricing are unverified. From background knowledge (unverified): it is a commercial ML service by Adam Day that scores titles and abstracts for paper-mill similarity, offered to publishers through an API.
- **SciScore, Ripeta and iThenticate:** no current information was retrieved, because the searches ran out and the vendor sites were DNS-blocked. From background knowledge (unverified):
  - SciScore (SciCrunch) scores methods sections against rigor criteria such as RRIDs, randomization, blinding and power.
  - Ripeta's "trust markers" were acquired by Digital Science.
  - iThenticate (Turnitin) powers Crossref Similarity Check, with per-manuscript pricing for individuals.

  All need current confirmation.
- **FigCheck:** its maker, features and pricing were not found beyond its listing in the STM comparison.
- **PPS tortured-phrase list:** no official machine-readable copy was located, and the license of any public list is unknown.
- **rtransparent:** its validated accuracy per indicator was not retrieved.

## 5. Cross-cutting summary: platform, installation, license and maintenance per tool

### Takeaway
For a skill run from Claude Code desktop on macOS or Windows, the lowest-friction building blocks are pure-Python packages with permissive licenses: pdfplumber, pypdf, pikepdf, docx2python, python-docx, pylatexenc, ImageHash, proselint, arxiv-latex-cleaner and ScrutiPy (which has wheels). Vale is a single binary installed with brew, choco or winget. R tools (statcheck, scrutiny, JATSdecoder, tableParser, metacheck, ODDPub) need an R install. Java tools (LanguageTool 17 or later, TeXtidote 8 or later) and Node tools (write-good, alex, textlint 20.18 or later) add runtimes. These should be optional, with results reported as "skipped" when absent.

### Cited Findings

| Tool | Group | Runtime and install | macOS / Windows | License | Latest version and date (maintenance) | Source |
|---|---|---|---|---|---|---|
| statcheck (R) | NUM | R package; PDF via pdftools | via R | GPL-3 | dev 1.6.1.9000, 2026-01-26 | [DESCRIPTION](https://raw.githubusercontent.com/MicheleNuijten/statcheck/HEAD/DESCRIPTION) |
| statcheck (Python) | NUM | `pip install statcheck` (pure Python) | yes | GPL (v3 text, v2 classifier) | 0.0.7, 2025-09-17 | [PyPI](https://pypi.org/project/statcheck/) |
| JATSdecoder / tableParser | NUM | R; PDF via CERMINE or pdftools, PDF tables via tabulapdf | via R | GPL-3 | 1.3.1 / 1.0.5–1.0.6, 2026-04-09 | [JATSdecoder](https://raw.githubusercontent.com/ingmarboeschen/JATSdecoder/HEAD/DESCRIPTION); [tableParser](https://raw.githubusercontent.com/ingmarboeschen/tableParser/HEAD/DESCRIPTION) |
| scrutiny | NUM | R (`install.packages("scrutiny")`) | via R | MIT | 0.6.1 (GRIMMER warning) | [DESCRIPTION](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/DESCRIPTION); [NEWS](https://raw.githubusercontent.com/lhdjung/scrutiny/HEAD/NEWS.md) |
| ScrutiPy | NUM | `pip install scrutipy` (Rust wheels) | wheels for both | MIT | 0.1.12, 2026-01-13 (alpha) | [PyPI](https://pypi.org/project/scrutipy/) |
| rsprite2 / pysprite | NUM | R / pip | yes | MIT / MIT | 0.2.1.9002 dev / 1.2.1, 2019-07-10 | [rsprite2](https://raw.githubusercontent.com/LukasWallrich/rsprite2/HEAD/DESCRIPTION); [pysprite](https://pypi.org/project/pysprite/) |
| unsum (CLOSURE) | NUM | R; Rust toolchain for source builds | via R | MIT | 0.3.0 | [DESCRIPTION](https://raw.githubusercontent.com/lhdjung/unsum/HEAD/DESCRIPTION) |
| zcurve | NUM | R | via R | GPL-3 | 2.4.6 | [DESCRIPTION](https://raw.githubusercontent.com/FBartos/zcurve/HEAD/DESCRIPTION) |
| metacheck | NUM/CIT/ETH | R ≥ 4.3; GROBID for PDF | via R | AGPL-3+ | 0.1.0, 2026-06-16 (experimental) | [DESCRIPTION](https://raw.githubusercontent.com/scienceverse/metacheck/HEAD/DESCRIPTION) |
| DORIS | NUM (econ) | research tool; R scraping plus Python | n/a | unknown | working paper, 2023–2024 | [UHasselt](https://documentserver.uhasselt.be/handle/1942/42667) |
| ChkTeX | FMT/LANG | native binary (Debian package; TeX-distribution bundling not verified) | see Gaps | not verified | 1.7.9, 2024-04-26 (maintenance mode) | [nongnu](https://www.nongnu.org/chktex) |
| TeXtidote | FMT/LANG | Java 8+ JAR | yes (Java) | GPL-3 | 0.9 in repo; last commit 2026-09-09 | [Readme](https://raw.githubusercontent.com/sylvainhalle/textidote/HEAD/Readme.md) |
| LanguageTool | LANG | Java 17 server | yes (Java) | LGPL | 6.8, 2026-05-05 | [CHANGES](https://raw.githubusercontent.com/languagetool-org/languagetool/HEAD/languagetool-standalone/CHANGES.md) |
| language_tool_python | LANG | pip (pure Python) plus Java 17+ | yes | GPL-3.0-only | 3.4.0, 2026-05-14 | [PyPI](https://pypi.org/project/language-tool-python/) |
| LTeX+ LS | LANG | LSP server bundling Java and LanguageTool | yes | MPL-2.0 | continuation after 16.0.0 | [README](https://raw.githubusercontent.com/ltex-plus/ltex-ls-plus/HEAD/README.md) |
| Harper | LANG | Rust binary, harper-ls, WASM | yes | not verified | active | [README](https://raw.githubusercontent.com/Automattic/harper/HEAD/README.md) |
| Vale | LANG | single Go binary (brew, choco, winget) | yes, offline | MIT | active (version not retrieved) | [README](https://raw.githubusercontent.com/errata-ai/vale/HEAD/README.md) |
| proselint | LANG | pip (Python 3.10+, google-re2) | yes | BSD | 0.16.0, 2025-11-14 | [PyPI](https://pypi.org/project/proselint/) |
| write-good | LANG | npm | yes (Node) | MIT | 1.0.8, 2021-02-16 | [npm](https://registry.npmjs.org/write-good) |
| alex | LANG | npm | yes (Node) | MIT | 11.0.1, 2023-08-18 | [npm](https://registry.npmjs.org/alex) |
| textlint plus latex2e | LANG | npm, Node 20.18+ | yes (Node) | MIT | 15.8.0; plugin 1.2.1, 2023-05-17 (seeking maintainers) | [npm](https://registry.npmjs.org/textlint/latest); [plugin](https://raw.githubusercontent.com/textlint/textlint-plugin-latex2e/HEAD/README.md) |
| Academic-Writing-Check | LANG | Perl script | Perl on Windows: the repo has a windows.md guide | no LICENSE file | last commit 2018-12-10 | [README](https://raw.githubusercontent.com/devd/Academic-Writing-Check/HEAD/README.markdown) |
| arxiv-latex-cleaner | FMT-11 | pip or brew | yes (Ghostscript compression on Linux and Mac only) | Apache-2.0 | 1.0.11, 2026-03-27 | [PyPI](https://pypi.org/project/arxiv-latex-cleaner/) |
| aclpubcheck | FMT | pip/uvx from GitHub, Python 3.10+ | yes (pure Python) | MIT | last commit 2026-10-07; PyPI 0.2.0 stale | [README](https://raw.githubusercontent.com/acl-org/aclpubcheck/HEAD/README.md) |
| poppler pdffonts / pdfinfo | FMT-15 | system binaries | see Gaps | not verified | 24.02.0 in this sandbox | local run |
| pikepdf / pypdf / pdfplumber / PyMuPDF | FMT-15 | pip | wheels or pure Python | MPL-2.0 / BSD-3 / MIT / AGPL-3 or commercial | 10.17.0 / 6.21.1 / 0.11.10 / 1.28.2 (all 2026) | [PyPI](https://pypi.org/project/pikepdf/) etc. |
| docx2python / python-docx | FMT-14 | pip (pure Python) | yes | MIT / MIT | 3.7.1, 2026-08-06 / 1.2.0, 2025-06-16 | [docx2python](https://pypi.org/project/docx2python/); [python-docx](https://pypi.org/project/python-docx/) |
| ImageHash / imagededup | ETH-07 | pip | yes | BSD-2 / Apache-2.0 (needs torch) | 4.3.2, 2025-02-01 / 0.3.3.post2, 2025-08-15 | [ImageHash](https://pypi.org/project/ImageHash/); [imagededup](https://pypi.org/project/imagededup/) |
| ODDPub / rtransparent | ETH/MTH | R | via R | AGPL-3+ / GPL-3 | 7.4.0, 2025-11-13 / 0.2.5 | [ODDPub](https://raw.githubusercontent.com/quest-bih/oddpub/HEAD/DESCRIPTION); [rtransparent](https://raw.githubusercontent.com/serghiou/rtransparent/HEAD/DESCRIPTION) |
| PPS, Clear Skies, Proofig, ImageTwin, FigCheck, SciScore, Ripeta, iThenticate | ETH | web or commercial services | browser only | commercial or free web | see section 4 | section 4 |

### Inferences
- **Proposed `requirements.txt` core** (all pure Python or with wheels, permissive licenses): pdfplumber, pypdf (or pikepdf), docx2python, lxml, pylatexenc, ImageHash and scipy (for p recomputation), with ScrutiPy optional.
  - Reimplement in Python: statcheck-style extraction, star checking, GRIM, DEBIT and bounds checks, TeXtidote's structure rules, and the Might-style word lists. Each finding then carries the formula and input as proof, as DESIGN §4 requires.
  - Detect and run when installed: Vale, proselint, chktex, pdffonts/pdfinfo, R (statcheck, tableParser) and Java (LanguageTool).
  - Never require the commercial services; list them in the coverage table as not performed.
- **Stale or risky tools:** pysprite (2019), write-good (2021), Academic-Writing-Check (2018, no license), textlint-plugin-latex2e (maintainer call), and ChkTeX (maintenance mode, though stable). Copy their ideas, not their packages.
- **No existing tool covers economics regression tables in a way a laptop skill can call.** That makes the star, SE and N consistency check the main differentiating feature to build and test, with the DORIS 1.2% FDR as the accuracy target.

### Gaps
- **Search coverage:** the shared WebSearch budget for this turn was exhausted after about 15 searches, and many primary hosts were DNS-blocked. The commercial products in sections 3 and 4, and some current version numbers (Vale, LTeX+, Harper, ChkTeX's license, CRAN versions), rest on search snippets or remain unverified. A follow-up session with working search, or local network access from the coworker's laptop, should confirm them.
- **Platform friction:** macOS and Windows installation was not tested for any tool (for example, R's tcltk dependency in statcheck on macOS, poppler on Windows, google-re2 wheels for proselint). The platform column above relies on package metadata (wheel tags) and README claims.
