# Sources for the latex_hard answer key

This file documents every cited work that a planted or negative citation item in `expected.yaml` depends on: the full text that was read, its version, and the verbatim passages that settle each item. All texts were downloaded and read on 2026-10-18 into a scratch folder outside the repository; no copy of any cited work is stored here.

How passages are located:

- **p. N** is the printed page number of the version read; **PDF p. M** is the page in the PDF file. NBER working papers have an unnumbered cover page and abstract page.
- Texts from PubMed Central (PMC) were read as full-text XML through NCBI E-utilities (`efetch.fcgi?db=pmc&id=…`). PMC author manuscripts carry no page numbers, so their passages are located by section heading; the published page range is given for reference.
- Quotes are verbatim, except that line-break hyphens are joined, footnote and reference markers that the text layer runs into the words are shown in brackets (for example "[20]"), and, in one passage of Carrera et al. (2022), the math accents of β̂ and β̃ are restored (the PDF text layer separates them from the letters). Apostrophes are typed straight.

| Key | Work | Version read | Items |
|---|---|---|---|
| royer2015 | Royer, Stehr and Sydnor (2015) | NBER WP 18580 (Nov 2012, rev. Aug 2013) | P03, P20, one negative |
| acland2015 | Acland and Levy (2015) | Working paper of 10 Mar 2013 (LSE Research Online) | P07, one negative |
| carrera2018incentives | Carrera, Royer, Stehr and Sydnor (2018a) | NBER WP 23567 (Jul 2017) and PMC author manuscript PMC5899425 | P01, one negative |
| carrera2018plans | Carrera, Royer, Stehr, Sydnor and Taubinsky (2018b) | NBER WP 24959 (Aug 2018) and PMC author manuscript PMC7872013 | P23 (wrong source), one negative |
| carrera2022 | Carrera, Royer, Stehr, Sydnor and Taubinsky (2022) | NBER WP 26161 (Aug 2019, rev. Aug 2021) | P06, P23 (true source), four negatives |
| augenblick2015 | Augenblick, Niederle and Sprenger (2015) | NBER WP 18734 (Jan 2013) | one negative |
| bhattacharya2015 | Bhattacharya, Garber and Goldhaber-Fiebert (2015) | NBER WP 21406 (Jul 2015), the cited version | P04, one negative |
| milkman2014 | Milkman, Minson and Volpp (2014) | PMC author manuscript PMC4381662 | P05, one negative |
| milkman2021 | Milkman et al. (2021) | PMC author manuscript PMC8822539 | P08, two negatives |

---

## 1. royer2015: Royer, Stehr and Sydnor (2015)

Cited as: *American Economic Journal: Applied Economics* 7(3): 51–84, doi:10.1257/app.20130327.

Read: NBER Working Paper 18580, "Incentives, Commitments and Habit Formation in Exercise: Evidence from a Field Experiment with Workers at a Fortune-500 Company", November 2012, revised August 2013. Landing page https://www.nber.org/papers/w18580, PDF https://www.nber.org/system/files/working_papers/w18580/w18580.pdf. The published article is behind the AEA paywall and was not read; OpenAlex gives this NBER paper as the open-access location of the published DOI.

**P03** (paper: "22 percent of the employees offered a self-funded commitment contract signed one"). 22 percent is the take-up among employees who had attended the gym during the incentive period; overall take-up was 12 percent.

> "Overall 12% of the employees offered the commitment option decided to take it, and among those who had attended the gym at least once during the incentive period, the take up rate was 22%." (p. 3, PDF p. 5)

> "Overall among the 346 subjects in the incentive+commit group, 12.4% chose to make a commitment and on average these committers placed $58 at stake.[20] Among ex‐ante gym members, the take‐up rate of commitments was 23%. For those who were not members of the gym prior to the study, the overall take‐up rate was 6%, but take‐up was 21% for those making at least one visit during the incentive period." (p. 21, PDF p. 23)

**P20** (paper: "consistent with Royer et al. (2015), who find that the demand for commitment comes mainly from employees who fall short of their own exercise targets"). The paper's own discussion says the opposite:

> "On a similar note, in column 4, we observe that being below one's personal exercise target, another possible measure of time inconsistency, is again not statistically significant and is actually slightly negatively correlated with takeup." (p. 23, PDF p. 25)

> "We find that employees who were exercising consistently prior to the study make commitments at rates similar to those who appear more likely to have a time inconsistency problem." (p. 31, PDF p. 33)

> "Perhaps most interestingly we find that the demand for commitment is similar even among those who were exercising regularly prior to the study and have no apparent need for commitment." (p. 4, PDF p. 6)

**Negative** ("Those who committed placed 58 dollars at stake on average, and 63 percent of them met their target"):

> "… on average these committers placed $58 at stake." (p. 21, PDF p. 23; full sentence quoted under P03)

> "Sixty‐three percent of those who created commitments in our study successfully maintained the commitment of not missing more than 14 days in a row at the gym." (p. 21, PDF p. 23)

## 2. acland2015: Acland and Levy (2015)

Cited as: *Management Science* 61(1): 146–160, doi:10.1287/mnsc.2014.2091.

Read: working-paper version "Naiveté, Projection Bias, and Habit Formation in Gym Attendance", dated 10 March 2013 (SSRN 2233004), LSE Research Online eprint 46827: https://researchonline.lse.ac.uk/id/eprint/46827/ (PDF https://researchonline.lse.ac.uk/id/eprint/46827/1/__libfile_REPOSITORY_Content_Levy%2C%20M_Naivete%20projection%20bias_Levy_Naivete%20projection%20bias_2013.pdf). The published article was not read; OpenAlex gives this PDF as the best open-access location of the published DOI.

**P07** (paper: "Acland and Levy (2015), by contrast, recorded both entry and exit swipes and could therefore measure how long each visit lasted"):

> "This attendance data was based on recorded ID-card swipes required for gym entry. Because swipes were necessary to enter the gym but not exit, we cannot determine the length of a visit." (p. 7, PDF p. 9)

**Negative** ("the habit formed during the incentive month largely decayed over the winter break"):

> "… estimate is 0.256 additional visits per week for the immediate post-treatment period, representing approximately a doubling of average attendance in our sample. In the later post-treatment period, after the winter break, we see no statistically significant difference between the groups, with a point estimate of 0.045 additional visits per week, suggesting that the habit induced by four weeks of exogenous gym attendance largely decayed over a similar period of quasi-exogenous non-attendance." (p. 12, PDF p. 14)

> "Like Charness and Gneezy, we find subjects do form a significant short-run habit, though we find substantial decay caused by the semester break." (abstract, PDF p. 2)

The abstract of the published version does not mention the decay, so a reader who checks only the published abstract cannot confirm this sentence; the body settles it.

## 3. carrera2018incentives: Carrera, Royer, Stehr and Sydnor (2018a)

Cited as: *Journal of Health Economics* 58: 202–214, doi:10.1016/j.jhealeco.2018.02.010 (aer.bst prints "2018a").

Read: (a) NBER Working Paper 23567, July 2017, https://www.nber.org/papers/w23567 (PDF https://www.nber.org/system/files/working_papers/w23567/w23567.pdf); (b) the PMC author manuscript of the published article, PMC5899425, https://pmc.ncbi.nlm.nih.gov/articles/PMC5899425/. Both passages below are identical in the two versions.

**P01** (paper: "and that the effects on average visits were largest among members who already exercised regularly"). The direction is reversed:

> "Overall we do not detect substantial heterogeneity in the treatment effects by these cuts. However, we are limited in power to detect differences across the groups. The incentive effect point estimates on encouraging people to exceed the 9-visit threshold are elevated for those with more successful previous exercise routines, which may reflect the fact that this group was more likely to be near that threshold to begin with. The effects on average visit rates during and after the intervention, though, are higher for low exercisers and those with less prior success with exercise." (NBER WP p. 15, PDF p. 16; PMC5899425, section 4.3 "Heterogeneity")

**Negative** ("credited a visit toward the incentive only after at least ten minutes in the gym"):

> "We also introduced a new checkout procedure partway through the study (in February 2016). Participants after that time were required to swipe out after attending the gym for at least 10 minutes in order to get credit for a visit toward their incentive." (NBER WP p. 4, PDF p. 5; PMC5899425, section 3.1 "Setting")

Version note, not used by any item: the NBER abstract says 836 new members were randomized; the published abstract says 690 participants (of the 836 new members, 690 took part).

## 4. carrera2018plans: Carrera, Royer, Stehr, Sydnor and Taubinsky (2018b)

Cited as: *Journal of Health Economics* 62: 95–104, doi:10.1016/j.jhealeco.2018.09.002 (aer.bst prints "2018b").

Read: (a) NBER Working Paper 24959, August 2018, https://www.nber.org/papers/w24959 (PDF https://www.nber.org/system/files/working_papers/w24959/w24959.pdf); (b) the PMC author manuscript, PMC7872013, https://pmc.ncbi.nlm.nih.gov/articles/PMC7872013/.

**Negative** ("total planned visits were three times actual visits (7.04 against 2.33)"):

> "Consistent with other studies showing that people are overoptimistic about their future exercise patterns (Royer et al., 2015), we observe individuals making considerably overambitious plans to visit the gym, with their total planned visits being three times as large as their actual visits (7.04 vs. 2.33)." (NBER WP p. 16, PDF p. 17; PMC7872013, Discussion)

**P23** (paper credits this paper with the 27–34 percent take-up of contracts for fewer visits). This study tests a planning prompt and offers no contracts of any kind:

> "Subjects were randomized into i) a treatment group who selected the days and times they intended to attend the gym over the next two weeks or ii) a control group who instead recorded their days of exercise in the prior two weeks." (abstract; NBER WP PDF p. 2 and PMC7872013)

A full-text search for "commit" finds one hit in the NBER version, in the reference-list title of Royer, Stehr and Sydnor (2015) (p. 18), and none in the PMC manuscript. The finding comes from Carrera et al. (2022), section 5 below.

## 5. carrera2022: Carrera, Royer, Stehr, Sydnor and Taubinsky (2022)

Cited as: *Review of Economic Studies* 89(3): 1205–1244, doi:10.1093/restud/rdab056 (published online 9 September 2021; print issue 2022).

Read: NBER Working Paper 26161, "Who Chooses Commitment? Evidence and Welfare Implications", August 2019, revised August 2021, https://www.nber.org/papers/w26161 (PDF https://www.nber.org/system/files/working_papers/w26161/w26161.pdf). The published article was not read (paywall); its abstract (OpenAlex record of the DOI) matches the working-paper abstract in substance.

**P23** (true source of the finding):

> "Most strikingly, we find that 27-34 percent of participants chose commitment contracts to attend the gym less, and that the take-up of “more” and “less” contracts at each threshold is significantly positively correlated." (p. 3, PDF p. 5)

> "We also asked participants to choose between receiving $80 unconditionally or conditional on going to the gym fewer than 8, 12, or 16 times over the next four weeks." (p. 3, PDF p. 5)

**P06** (paper: "an average present-bias parameter of 0.84 and a perceived parameter of 0.55, so that members are more pessimistic"). The estimates are the other way round, which implies overoptimism (partial naiveté):

> "We estimate an actual average present focus parameter of β̂ = 0.55 and an average (across both information treatment and control groups) perceived present focus parameter of β̃ = 0.84." (p. 4, PDF p. 6)

**Negative** ("64, 49 and 32 percent for thresholds of 8, 12 and 16 visits in four weeks"):

> "In Section 6, we report results on commitment contract take-up. We find high take-up of commitment contracts to attend the gym more, consistent with the take-up rates observed in other studies with similar designs (64% for 8+ visits, 49% for 12+ visits, and 32% for 16+ visits)." (p. 3, PDF p. 5; the four-week horizon is in the passage quoted under P23)

**Negative** ("an information treatment that made members more aware of their overoptimism reduced demand for contracts"):

> "Finally, the information treatment significantly decreased the take-up of commitment contracts for higher gym attendance, suggesting that in our setting increased sophistication reduces desire for commitment contracts." (p. 4, PDF p. 6)

**Negative** ("estimate that offering their contracts lowered consumer surplus, and that linear subsidies producing the same average change in attendance would have been more efficient"):

> "Structural estimates of a model of quasi-hyperbolic discounting and gym attendance imply that offering our commitment contracts lowers consumer surplus, and is less socially efficient than utilizing linear exercise subsidies that achieve the same average change in behavior." (abstract, PDF p. 2)

> "On average, consumers who take up the 8+, 12+, and 16+ commitment contracts incur losses equivalent to −$7.91, −$18.69, and −$10.51 per person, respectively, under the long-run criterion. Moreover, while we estimate that the contracts lead to modest gains in the social efficiency of gym attendance, these gains pale in comparison to the effects of linear per-attendance incentives that are offered to the entire population and scaled to generate the same increases in average attendance." (p. 4, PDF p. 6; the welfare section is on pp. 28–29)

**Negative on the reference year** (2022): Crossref's `issued` date is 2021-09-09 (online first) and its `published-print` date is 2022; volume 89, issue 3 is the 2022 print issue.

## 6. augenblick2015: Augenblick, Niederle and Sprenger (2015)

Cited as: *Quarterly Journal of Economics* 130(3): 1067–1115, doi:10.1093/qje/qjv020.

Read: NBER Working Paper 18734, "Working Over Time: Dynamic Inconsistency in Real Effort Tasks", January 2013, https://www.nber.org/papers/w18734 (PDF https://www.nber.org/system/files/working_papers/w18734/w18734.pdf). The published article is closed and was not read.

**Negative** ("59 percent of their subjects chose a commitment device when it was offered at a price of zero"):

> "Third, we find that the elicited demand for commitment is limited to price zero, at which price 59% of subjects would prefer a higher likelihood of implementing one of their initial allocations over their subsequent reallocations." (p. 5, PDF p. 6)

The same figure for the published paper is reported by Carrera et al. (2022, NBER WP 26161, p. 6, footnote 7): "For example, in Augenblick, Niederle, and Sprenger (2015), 33 percent of subjects are identified as present-focused based on effort allocation decisions, yet 59 percent take up an offer of a commitment contract."

## 7. bhattacharya2015: Bhattacharya, Garber and Goldhaber-Fiebert (2015)

Cited as: NBER Working Paper 21406, doi:10.3386/w21406, which is the version read: https://www.nber.org/papers/w21406 (PDF https://www.nber.org/system/files/working_papers/w21406/w21406.pdf), July 2015.

**P04** (paper: "Longer defaults led users to choose longer contracts but also made them less likely to sign a contract at all"):

> "Longer duration nudges increased the duration of contracts without reducing the likelihood of signing a contract or altering choices of other contract characteristics. The fraction of users who ultimately signed contracts did not differ significantly across different nudges." (p. 4, PDF p. 5)

**Negative** ("Only 22.7 percent of the signed contracts put money at stake"):

> "Users committed to financial stakes in 22.7% of the signed contracts, with approximately $23 on average at risk for each week that they failed." (p. 4, PDF p. 5)

Version note, not used by any item: the abstract describes nudges toward 20 or 8 weeks; the body (p. 4) describes randomized defaults of 8, 12 or 20 weeks.

## 8. milkman2014: Milkman, Minson and Volpp (2014)

Cited as: *Management Science* 60(2): 283–299, doi:10.1287/mnsc.2013.1784.

Read: PMC author manuscript PMC4381662, https://pmc.ncbi.nlm.nih.gov/articles/PMC4381662/ (full-text XML from E-utilities; no page numbers).

**P05** (paper: "participants in that study were willing to pay $9.61 on average"):

> "Average willingness to pay for the program was $6.91 (t(210) = 9.34; p < 0.0001), with only 39.3% (t(210) = 18.00; p < 0.0001) of participants stating a $0 willingness to pay" (section 4.3, "Willingness to Pay for Temptation Bundling Devices")

The abstract gives only the share willing to pay: "After the study, 61% of participants opted to pay to have gym-only access to iPods containing tempting audiobooks, suggesting demand for this commitment device."

**Negative** ("and the program helped the busiest participants most"):

> "Although not anticipated ex ante, we discovered one additional variable that interacted significantly with our treatment effect. … We find that temptation bundling particularly benefits our busiest participants: a one-standard-deviation decrease in availability corresponds to an increase in the initial treatment effect of 0.21 gym visits per week (p = 0.014; Table 3, Models 5 and 7)." (section 4.2, "Treatment Effect Interactions")

Context for the paper's description of the study: "The participants in this study were 226 students, faculty, and staff at a large northeastern U.S. university …" (section 3.1); "Initially, full and intermediate treatment participants visited the gym 51% and 29% more frequently, respectively, than control participants, but treatment effects declined over time (particularly following Thanksgiving)." (abstract)

## 9. milkman2021: Milkman et al. (2021)

Cited as: *Nature* 600(7889): 478–483, doi:10.1038/s41586-021-04128-4.

Read: PMC author manuscript PMC8822539, https://pmc.ncbi.nlm.nih.gov/articles/PMC8822539/ (full-text XML from E-utilities; no page numbers).

**P08** (paper: "Like Milkman et al. (2021), who preregistered their megastudy as a single study before data collection"):

> "Each of the 20 studies in our megastudy was preregistered on the Open Science Framework …" and "Although all 20 of the substudies in this megastudy were preregistered, the megastudy itself was not. This was an oversight on our part." (Methods, "Megastudy statistical analysis")

**Negative** ("report unadjusted p-values for their 53 comparisons together with an estimate of the false discovery rate"):

> "Rather than adjusting our P values for 53 paired comparisons, we report unadjusted standard errors, two-sided P values and confidence intervals (CI) so readers may choose a preferred correction. Using the Storey–Tibshirani method of computing the false-discovery rate[26], we estimate that the results identified as significant at the 5% level have less than a 5.07% chance of being a true null." (section "The effects of study conditions on exercise")

**Negative** ("raised weekly visits by 0.14, or 9 percent"):

> "The planning, reminders and microincentives to exercise condition produced an estimated 0.14 more weekly gym visits per participant (a 9% increase in exercise) compared with the placebo control condition (b = 0.14, 95% CI = 0.04–0.23, P = 0.006)." (section "The effects of study conditions on exercise")

Context for the paper's description of the study: "In a megastudy targeting physical exercise among 61,293 members of an American fitness chain, 30 scientists from 15 different US universities worked in small independent teams to design a total of 54 different four-week digital programmes (or interventions) encouraging exercise." (abstract)

---

## Other cited works

No item depends on the full text of these works. Each is cited for a general claim that its abstract supports (abstracts read through OpenAlex and Crossref).

| Key | Claim in the paper | Note |
|---|---|---|
| dellavigna2006 | gym members use memberships far less than planned | Cited only for a general claim, on purpose. The published AER text could not be retrieved (the AEA PDF link and the Zurich repository refuse automated access), and the NBER version (WP 10819, 2004, under the title "Overestimating Self-Control: Evidence from the Health Club Industry") reports different numbers from the AER abstract: 7,978 members, 4.8 visits per month and $700 forgone, against 7,752, 4.3 and $600. |
| charness2009 | lasting increases after a month of paid visits, driven by people who were not regular gym users | Closed full text; the abstract says the effect "is entirely driven by people who did not previously attend the gym on a regular basis." |
| kaur2015 | data-entry workers chose contracts that penalize low output | Missing from refs.bib on purpose (P02); the abstract of Kaur, Kremer and Mullainathan (2015) supports the claim. |
| gneezy2012 | incentive effects often fade once payments stop | Year off by one on purpose (P26). |
| laibson1997, odonoghue1999 | present bias and procrastination | Abstracts. |
| bryan2010 | review of commitment devices | Abstract. |
| karlan2016 | reminders help clients of commitment savings accounts reach their goals | Published abstract: "reminder messages increase commitment attainment for clients who recently opened commitment savings accounts". |
| milkman2011 | date-and-time prompts raise flu vaccination | Abstract: the date-and-time prompt raised vaccination by 4.2 percentage points. |
| volpp2008 | deposit contracts helped obese adults lose weight | Abstract. |

## Reference metadata (Crossref, 2026-10-18)

All 18 entries in refs.bib were compared field by field with their Crossref records (title, author family names and order, year, journal, volume, issue, pages). Every field matches except:

- gneezy2012: year 2012 against 2011 in Crossref (planted, P26).
- carrera2022: Crossref's `issued` date is 2021 (online first) and its print date is 2022; 2022 is correct (negative).
- dellavigna2006: Crossref spells the first author "Della Vigna"; the entry keeps "DellaVigna", the form the author uses.
- volpp2008: Crossref's title omits the subtitle "A Randomized Trial", which the JAMA article and PubMed include; Crossref gives only the first page (2631).

## Retrieval notes

PMC article pages and PDFs answered with reCAPTCHA or proof-of-work checks, Europe PMC's PDF service with a Cloudflare challenge, the AEA PDF link with an HTML page, and the Zurich repository with an Anubis block; Harvard DASH rate-limited the Laibson PDF. None of these protections was bypassed. PMC texts were read through the NCBI E-utilities API instead, and works whose full text could not be read were not used for citation items.
