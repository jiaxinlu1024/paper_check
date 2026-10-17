# Behavioral economics paper check: field standards, policies, replication infrastructure, common errors and tools

*Research date: 2026-10-17. How this was gathered: aeaweb.org, publisher sites (Cambridge, Elsevier, Springer, OUP, INFORMS), the Wayback Machine, arXiv and most other hosts could not be fetched from this session. Only GitHub could be read directly. Evidence labels used below:*
- *[G] a GitHub-hosted primary source that I read myself, with its last-commit or page date.*
- *[S] a web-search tool summary of the linked page. The page was not read in full.*
- *[T] the title or existence of a work only.*
- *[3P] a third-party, non-official source.*

*The web-search budget, which is shared by all agents in this turn, ran out after the journal and statistics searches. Writing guides, misattributed findings and some reporting pitfalls are therefore only partly verified. Unverified items are listed under Gaps and marked [unverified], so they can be checked in a follow-up session.*

## 1. Experimental economics norms: incentives, deception, instructions, checks, online samples, software, recruitment, reporting standards

### Takeaway
*Experimental Economics* is the Economic Science Association (ESA) flagship, published by Cambridge University Press since January 2025. It only considers studies that use no deception and that pay participants for their decisions, and it wants the participants' instructions at submission. AEA journals and ReStud add three requirements:
- the full instructions go in an appendix at submission;
- the experiment and survey code (z-Tree, oTree, Qualtrics .qsf and similar) goes in the replication package;
- IRB details go in the title footnote (AEA), and IRB documentation goes in the package (ReStud).

I found no economics-specific reporting checklist of the CONSORT kind. The closest general standard is the APSA experimental reporting standards. A checker therefore needs a composite checklist built from the AEA, ReStud and *Experimental Economics* policies plus APSA and CONSORT.

### Cited Findings
**Deception and incentives**
- *Experimental Economics* scope statement: "we only consider studies that do not employ deception of participants and in which participants are incentivized." Authors must submit the instructions participants received at the time of submission and supply separate data appendices, which are attached to the journal's web page on publication. The journal also considers methodology and replication articles. — [S] [Experimental Economics, About this journal](https://www.cambridge.org/core/journals/experimental-economics/information/about-this-journal)
- Cambridge University Press publishes *Experimental Economics* (from Volume 28) and JESA (from Volume 11) from January 2025, in partnership with the ESA. Both journals became fully open access under a Creative Commons licence. Springer published them until 2024. — [S] [Cambridge blog: New to Cambridge in 2025](https://www.cambridge.org/core/blog/?p=61413)
- David Cooper, then editor-in-chief of *Experimental Economics*, wrote that he "would have desk-rejected these papers due to the use of deception." He said that accepting blatant deception in the ESA flagship would send the wrong signal, and that these were his personal views rather than journal policy. He described when he would tolerate deception: limited harm, no feasible non-deceptive alternative, and full debriefing. — [S] [Cooper, "A Note on Deception in Economic Experiments", Journal of Wine Economics](https://www.cambridge.org/core/journals/journal-of-wine-economics/article/note-on-deception-in-economic-experiments/A4A0B55C7E7545EF1F8D2D6DB1C62565)
- Charness, Samek and van de Ven (2022, *Experimental Economics*) surveyed researchers and found three things:
  - giving participants false information is generally considered deception;
  - withholding information, or misleading without an outright lie, are "gray areas";
  - such practices may be acceptable when the topic is important and there is no other way to collect the data.

  — [S] [Charness, Samek and van de Ven 2022](https://www.cambridge.org/core/journals/experimental-economics/article/what-is-considered-deception-in-experimental-economics/B92D3DCAA5CDAB1357D49B7443244E50); [S] [Springer version](https://link.springer.com/article/10.1007/s10683-021-09726-7)
- The 2002 *Experimental Economics* article "The Costs of Deception: Evidence from Psychology" concluded that experimental economists' prohibition of deception is a sensible convention that economists should not abandon. The authors, Ortmann and Hertwig, are named from memory; the search result did not show them. — [S] [The Costs of Deception: Evidence from Psychology](https://www.cambridge.org/core/journals/experimental-economics/article/abs/costs-of-deception-evidence-from-psychology/FD1BFDD3876FD68E52B6951590538057)
- Gneezy's review of experimental methods reports that *Experimental Economics* does not consider papers that include deception. — [S] [Gneezy, "Experimental methods: Revisiting the commandments"](https://rady.ucsd.edu/_files/faculty-research/uri-gneezy/Experimental-methods-revisiting.pdf)
- The rule differs outside the ESA. Many applied economics journals ban deception, but the AAEA journals introduced guidelines that allow some forms of it. — [S] [Deception in Experiments: Towards Guidelines on use in Applied Economics Research (AEPP 2015)](https://ideas.repec.org/a/oup/apecpp/v37y2015i3p524-536..html); [S] [Purdue working paper on subject pools and deception](https://Krannert.purdue.edu/research/working-papers-series/2018/1314_sub_pools_deception.pdf)

**Payment mechanisms and incentive compatibility**
- Azrieli, Chambers and Healy (2018, *Journal of Political Economy*): paying for one randomly chosen decision is essentially the only incentive-compatible mechanism under statewise monotonicity. Paying for every period is justified only under a "no complementarities at the top" assumption. — [S] [Incentives in Experiments: A Theoretical Analysis (summary page; aggregator)](https://academicnewsletter.sufe.edu.cn/info/346113)
- In a 2025 *Experimental Economics* paper on objective lotteries, the same authors find that paying for one randomly selected decision remains the only broadly applicable incentive-compatible mechanism. — [S] [Incentives in experiments with objective lotteries](https://core-cms.cambridgecore.org/core/journals/experimental-economics/article/incentives-in-experiments-with-objective-lotteries/C0643FAD1CE9DBB8FA4FD441B88387BA)
- The binarized scoring rule (Hossain and Okui 2013) and multiple price lists are incentive compatible for belief elicitation under fairly general assumptions. Healy's experiments found very little evidence of manipulation. — [S] [P.J. Healy seminar abstract](https://economics.uq.edu.au/node/14813); [S] [Healy, Elicitation overview slides](https://healy.econ.ohio-state.edu/present/Healy-Elicitation_Overview.pdf)
- The binarized scoring rule may still allow ambiguity-averse hedging (Baillon, Halevy and Li 2022, as cited). — [S] [The Supply of Motivated Beliefs (arXiv)](https://arxiv.org/pdf/2111.06062)

**Instructions, protocols and materials**
- The AEA's Policy for Papers Conducting Experiments and Collecting Primary Data asks for the following:
  - summarise the original instructions in the design discussion and include them in full as an appendix at submission, detailed enough for a skilled researcher to replicate;
  - summarise eligibility and exclusion criteria;
  - deposit the programs, configuration files or scripts that ran the experiment or built the survey (z-Tree, Qualtrics and LimeSurvey are given as examples);
  - include a human-readable instrument, such as a PDF of the questionnaire;
  - deposit the raw data;
  - request any exceptions at submission.

  — [S] [AEA policy-experimental](https://www.aeaweb.org/journals/data/policy-experimental) (summarised from the mirror [swlb1.aeaweb.org](https://swlb1.aeaweb.org/journals/data/policy-experimental))
- The AEA Data and Code Availability Policy, as quoted in the AEA Data Editor's January 2023 mapping to DCAS, says: "For papers collecting original data through surveys or experiments, the replication materials shall also include (f) survey instruments or experiment instructions, (g) computer code for experiment or survey collection mechanisms, and (h) original instructions and details on subject selection." The Data Editor adds that the AEA treats "experiment instructions" as code when the experiment ran in software. Section numbers may differ in the February 2026 policy. — [G] [AEA Data Editor, DCAS-compliance-v1.csv (repo updated 2026-10-08)](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_data/DCAS-compliance-v1.csv)
- AEA replicators check that the deposit contains the scripts that implement the experiment or survey. Qualtrics files end in .qsf. Replicators do not run these files; they only check that they are present. When files are missing, the report says: "[REQUIRED] Provide any computer programs, configuration files, or scripts used to run the experiment or develop the survey instrument, e.g., z-Tree code, Qualtrics, SurveyCTO, and LimeSurvey." — [G] [AEA replication report template, REPLICATION.md (fetched at HEAD 2026-10-17)](https://github.com/AEADataEditor/replication-template/blob/HEAD/REPLICATION.md)
- AEA FAQ: for experiments, authors provide the z-Tree code, not the z-Tree software itself. — [G] [AEA Data Editor FAQ source](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/faq.md)
- ReStud's data policy:
  - all survey and experimental instruments must be in the replication package; "A reference to an online appendix of the paper does not suffice: online appendices do not have a DOI";
  - non-English instructions need a translation;
  - on acceptance, authors provide the programs, configuration files or scripts that ran the experiment, and the raw data;
  - a pre-registration must be documented with its DOI in the README;
  - "Authors who collect primary data (e.g., via experiment or survey) are required to include the IRB approval documentation."

  — [G] [ReStud Data Editor, policy.md (repo updated 2026-10-09)](https://github.com/restud/data-editor/blob/HEAD/policy.md)
- A replication case study in *Experimental Economics* found that participants in the NUS replication did not receive the oral instructions used in the original. It recommends experimenter scripts that mark exactly what the experimenter does and says. — [S] [Best practices in replication: a case study of common information in coordination games](https://www.cambridge.org/core/journals/experimental-economics/article/best-practices-in-replication-a-case-study-of-common-information-in-coordination-games/B1C8C8B2FFEBB82529A55B56BD262A40)

**Comprehension checks, attention checks and online sample quality**
- Prolific's attention and comprehension check policy:
  - permitted attention checks are instructional manipulation checks and nonsensical questions; comprehension checks are also covered;
  - time limits and "internal measures" are not permitted as checks;
  - a manipulation check must test attention to the question itself, not to the instructions above it; it must not assume prior knowledge or rely on memory recall;
  - in studies of 5 minutes or longer, a participant must fail at least two checks to be rejected; in shorter studies, one failed check is enough.

  — [S] [Prolific: attention and comprehension check policy](https://researcher-help.prolific.com/en/articles/445153-prolific-s-attention-and-comprehension-check-policy)
- Prolific asks researchers to approve participants who made a real effort but gave weak data, and to exclude them from the analysis rather than reject them. Rejection is for participants who clearly made little effort, failed several checks, or lied to get into the study. Participants who collect too many rejections are removed from the platform. — [S] [Prolific: Who should I reject?](https://researcher-help.prolific.com/en/articles/445218-who-should-i-reject)
- Douglas, Ewell and Brauer (2023, PLOS ONE) compared MTurk, Prolific, CloudResearch, Qualtrics and SONA. Prolific and CloudResearch did better than MTurk and Qualtrics on attention checks and meaningful responses. The cost per high-quality response was about $1.90 on Prolific and $4.36 on MTurk. — [S] [PMC10013894](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10013894/)
- A replication study found that MTurk response quality had declined over five years, with 39% of MTurk responses failing attention checks. — [S] [NSF PAR 10404815](https://par.nsf.gov//servlets/purl/10404815)
- A WU Vienna guide cites a 2025 study (Celeb et al.) reporting the following:
  - Prolific data quality was comparable to the lab;
  - most MTurk responses showed signs of AI assistance;
  - both platforms prohibit using AI tools to complete tasks.

  This is second-hand; the study itself was not read. — [S] [WU Vienna, Detect and Prevent AI in Online Surveys](https://www.wu.ac.at/fileadmin/wu/d/cc/exp/PDFs/Detect_and_Prevent_AI_in_Online_Surveys_Guide.pdf)
- A Johns Hopkins guide says LLM-written answers tend to be less emotional, more analytical and less varied than human ones. It recommends asking participants not to use LLMs and blocking copy and paste. — [S] [JHU, Guarding data integrity in online surveys](https://publichealth.jhu.edu/center-for-global-digital-health-innovation/guarding-data-integrity-tackling-challenges-in-online-surveys)
- Prolific says its authenticity checks detect AI-generated responses with 98.7% precision. This is a company claim and has not been independently verified. — [S] [Prolific: Stop using MTurk for research](https://www.prolific.com/resources/stop-using-mturk-for-research)

**Experiment software and recruitment systems: citation duties**
- oTree docs, "Important note": "If you publish research done with oTree, you are required to cite this paper." The paper is Chen, Schonger and Wickens (2016), *Journal of Behavioral and Experimental Finance* 9: 88–97, doi:10.1016/j.jbef.2015.12.001. — [G] [otree-docs source/install.rst (repo updated 2026-02-22)](https://github.com/oTree-org/otree-docs/blob/HEAD/source/install.rst)
- ORSEE "is released under terms of proprietary open source License. It requires you to acknowledge the software usage by an appropriate citation of this article." The article is Greiner (2015) in JESA, doi:10.1007/s40881-015-0004-4. — [G] [orsee/orsee README](https://github.com/orsee/orsee/blob/HEAD/README.md); licence page linked from it: [orsee.org/web/license.php](http://www.orsee.org/web/license.php)
- The z-Tree reference is Fischbacher (2007), "z-Tree: Zurich toolbox for ready-made economic experiments", *Experimental Economics* 10: 171–178, doi:10.1007/s10683-006-9159-4. There is also a z-Tree 5.1 manual (Fischbacher, Bendrick and Schmid 2021). — [S] [Springer: Fischbacher 2007](https://link.springer.com/article/10.1007%2Fs10683-006-9159-4)
- "z-Tree unleashed" (Duch, Grossmann and Lauer, JBEF 2020) runs z-Tree experiments over the Internet. — [T] [IDEAS listing](https://ideas.repec.org/a/eee/beexfi/v28y2020ics2214635020303270.html)

**Reporting standards**
- The APSA Experimental Research Section's "Recommended Reporting Standards for Experiments (Laboratory, Field, Survey)" is a set of minimum standards modelled on CONSORT. It covers items such as hypotheses, subject eligibility and exclusion, and study context, and leaves statistical analysis largely to the researcher. — [S] [APSA reporting standards PDF](https://www.cambridge.org/core/services/aop-file-manager/file/57922fab308173a70b28ddc9/xps-reportingstandards.pdf)
- The DIRECT checklist (2024) covers discrete choice experiments in health. — [T] [DIRECT checklist, PharmacoEconomics](https://link.springer.com/article/10.1007/s40273-024-01431-6)
- A targeted search found no ESA or economics-journal reporting checklist for lab or online experiments. The closest results were APSA, CHEERS and other health or animal guidelines. — [S] (search result, 2026-10-17)

### Inferences
- **Composite experiment checklist ("EXP") for the behavioral economics module.** Each item is grounded in the findings above:
  - **Deception screen.** Flag phrases such as "participants were told", "cover story", "confederate", "fictitious/simulated partner or opponent", "computer player" without disclosure, and "unbeknownst to participants". For *Experimental Economics* or JESA, a flag is Critical, because a desk rejection is likely. For other journals it is Major and needs justification. Withholding information or omission is "needs human judgment".
  - **Incentives.** Show-up fee, exchange rate between experimental currency units and money, mean and range of earnings, session length, the payment rule (one random decision or all rounds), payment timing, and the belief-elicitation rule. Hypothetical choices without incentives are a red flag for *Experimental Economics*.
  - **Instructions.** A full appendix, translations when needed, screenshots, the comprehension questions and how failures were handled, and the oral and experimenter script.
  - **Materials.** A replication-package statement that covers the z-Tree, oTree or Qualtrics source code.
  - **Subject pool.** Recruitment system (ORSEE, hroot, SONA, Prolific, MTurk), eligibility and exclusions, number of sessions, location and dates, participants per session, matching protocol (partner or stranger), and the independent units of observation (sessions or matching groups).
  - **Online samples.** Platform, prescreens, attention-check rules consistent with Prolific's two-check rule, exclusion rules (ideally pre-registered), measures against bots and LLM use, completion-time screens, and hourly pay.
- **Software citation is a cheap, deterministic check.** If "oTree" or "ORSEE" appears, the Chen, Schonger and Wickens (2016) or Greiner (2015) citation is required by the software's own terms. For z-Tree, citing Fischbacher (2007) is customary; whether the licence requires it is unconfirmed.
- **Venue switch.** The deception and incentive rules should be severity modifiers in the venue profiles. They are near-absolute for *Experimental Economics* and JESA and softer elsewhere, for example at AAEA journals.

### Gaps
- The full *Experimental Economics* and JESA author instructions on Cambridge Core were not read. In particular, the current wording of the deception rule and whether it is a formal ESA policy are unconfirmed. I found no ESA-wide official statement.
- One search summary said the no-deception norm originated with Sidney Siegel and was carried into experimental economics by Vernon Smith and Charles Plott. I could not tie this claim to a specific source.
- [unverified] Danz, Vesterlund and Wilson (2022, AER) report that telling participants about the binarized scoring rule's incentives can bias reports. This was not confirmed this session.
- [unverified] The Becker–DeGroot–Marschak mechanism, the strategy method (Selten 1967; Brandts and Charness 2011) and Smith's (1976) induced-value precepts were not verified.
- [unverified] It is unconfirmed whether the z-Tree licence requires citing Fischbacher (2007). hroot (Bock, Baetge and Nicklisch 2014) and SONA practices were not checked.
- [unverified] Snowberg and Yariv (2021, AER) on behaviour across participant pools, and Arechar, Gächter and Molleman (2018, *Experimental Economics*) on interactive online experiments, were not verified.
- [unverified] Two candidate checklist sources were not verified: Czibor, Jimenez-Gomez and List (2019), "The Dozen Things Experimental Economists Should Do (More of)", and Palfrey and Porter (1991), the Econometrica guidelines for experimental manuscripts. CONSORT 2025 and CONSORT-SPI were not checked either.

## 2. Preregistration, pre-analysis plans, multiple testing, power, attrition and balance, clustering

### Takeaway
AEA journals require field experiments (RCTs) to be registered in the AEA RCT Registry and the registration to be cited in the title footnote and the reference list. Lab experiments are exempt. The AEA Data Editor's template treats a registration only on OSF or AsPredicted as a warning. Evidence on 15,992 RCT test statistics shows that pre-registration without a complete pre-analysis plan does not reduce p-hacking. A checker should therefore look for the following:
- adherence to the plan, with deviations disclosed;
- multiple-testing corrections, such as List–Shaikh–Xu or Romano–Wolf for the family-wise error rate, or Anderson's sharpened q-values for the false discovery rate;
- standard errors clustered at the level where treatment was assigned;
- attrition handling (Lee bounds) and a power justification.

### Cited Findings
**Registration requirements**
- AEA policy, as quoted by the AEA Data Editor: "It is the policy of the AEA that randomized control trials must be registered on the RCT Registry. All such registrations shall be cited in the title footnote and elsewhere in the paper as appropriate." DCAS states the general rule: "If applicable, pre-registration of the research is identified and cited." — [G] [DCAS-compliance-v1.csv](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_data/DCAS-compliance-v1.csv)
- AEA RCT policy page: all work involving field experiments must be registered in the AEA RCT Registry before submission; "Laboratory experiments do not need to be registered at this time." — [S] [AEA RCT Registry policy](https://www.aeaweb.org/journals/policies/rct-registry) (mirror [swlb1](https://swlb1.aeaweb.org/journals/policies/rct-registry))
  - This conflicts with an older AEA page that calls registration voluntary and unlinked to the journals. That page predates the 2018 motion and is outdated. — [S] [aeaweb.org/rct.php](https://www.aeaweb.org/rct.php)
- The AEA Executive Committee passed a motion in January 2018 requiring registration for applicable submissions. Authors give the registry number in the submission form and in the introductory footnote. At that stage, registration after the trial was still accepted. — [S] [World Bank Development Impact, April 2018](https://blogs.worldbank.org/en/impactevaluations/weekly-links-april-7-registration-becomes-compulsory-lessons-reality-tv-and-black-panther-positively)
- The AEA Data Editor's report template classifies RCTs as follows:
  - ✅ the registration number is in the title-page footnote and cited per the AEA Sample References;
  - ⚠️ the number is in the footnote but not cited;
  - ⚠️ the RCT is not mentioned in the footnote;
  - ⚠️ the RCT "is not registered at the AEA RCT Registry, but elsewhere (OSF, AsPredicted, etc.)".

  The required text reads: "the registration number be **cited** in the title page footnote." — [G] [REPLICATION.md](https://github.com/AEADataEditor/replication-template/blob/HEAD/REPLICATION.md)
- Registration in the AEA RCT Registry does not satisfy the ICMJE registration requirement for trials that meet the clinical-trial definition. — [S] [J-PAL: Trial registration](https://www.povertyactionlab.org/resource/trial-registration)
- ReStud: "If applicable, pre-registration of the research project must be documented with a Document Object Identifier for the pre-registration record in the README." — [G] [ReStud policy.md](https://github.com/restud/data-editor/blob/HEAD/policy.md)

**Pre-analysis plans: evidence and norms**
- Brodeur, Cook, Hartley and Heyes (*JPE Microeconomics* 2024, 2(3): 527–561) studied 15,992 test statistics from RCTs in 15 leading economics journals published 2018–2021. Pre-registration alone made no meaningful difference to the distribution of test statistics. With a complete pre-analysis plan, studies were significantly less p-hacked, with evidence of less publication bias. — [S] [IZA DP 15476](https://www.iza.org/publications/dp/15476); [S] [I4R DP 101](https://econpapers.repec.org/RePEc:zbw:i4rdps:101)
- Banerjee, Duflo, Finkelstein, Katz, Olken and Sautmann (2020, NBER w26993) argue that filling in the AEA registry fields usually delivers most of a pre-analysis plan's benefits. More detail is warranted when subgroup analysis matters a lot or a party has a vested interest. They warn that over-specification can hurt research, and they propose a short public "populated PAP" report. — [S] [NBER w26993](https://www.nber.org/papers/w26993); [S] [Development Impact review](https://blogs.worldbank.org/impactevaluations/pre-analysis-plans-and-registered-reports-what-new-opinion-piece-does-and-doesnt)

**Registered reports at economics journals**
- The Journal of Development Economics piloted pre-results review with BITSS in March 2018 and has made it a permanent track. Stage 1 reviews the design and analysis plan; Stage 2 reviews the full paper. — [S] [BITSS: Registered Reports at JDE](https://www.bitss.org/publishing/jde/); [S] [JDE pre-results author guidelines](https://afosterri.org/jdepreresults/author-guidelines/)
- *Experimental Economics* piloted pre-results review through a special-issue call. Its current status is unknown. — [S] [CEGA](https://cega.berkeley.edu/article/experimental-economics-follows-the-journal-of-development-economics-in-piloting-pre-results-review/)
- A 2025 Q Open paper's appendix lists economics journals offering registered reports: JESA, the Journal of Behavioral and Experimental Economics, *JPE Microeconomics*, Oxford Open Economics, Energy Economics and Review of Finance. Some entries link to social-media posts and may be out of date. — [S] [Q Open, "Registered reports and associated benefits for agricultural economics"](https://academic.oup.com/qopen/advance-article/doi/10.1093/qopen/qoae011/7645459)
- RegCheck (arXiv, January 2026) is "a tool for structured comparisons between study registrations and papers". It is relevant to a check that compares a pre-registration with the paper. — [T] [arXiv 2601.13330](https://arxiv.org/pdf/2601.13330)

**Multiple hypothesis testing**
- List, Shaikh and Xu (2019, *Experimental Economics* 22(4): 773–793) address three cases: multiple outcomes, subgroups and multiple treatments. They build on Romano and Wolf (2010), asymptotically control the family-wise error rate, and gain power over Bonferroni and Holm. Stata implementations are `mhtexp` (Seidel and Xu) and the more general `mhtreg` (Steinmayr). — [S] [IDEAS listing](https://ideas.repec.org/a/kap/expeco/v22y2019i4d10.1007_s10683-018-09597-5.html); [S] [NBER w21875](https://www.nber.org/papers/w21875)
- Anderson's sharpened false-discovery-rate q-values, based on the Benjamini, Krieger and Yekutieli (2006) two-stage procedure, are among the most popular corrections. In the World Bank's 20-outcome example, Bonferroni turns p = 0.031 into 0.62, while the sharpened q-value is 0.091. Sharpened q-values can even be smaller than unadjusted p-values when many hypotheses are rejected. — [S] [World Bank: overview of MHT commands in Stata](https://blogs.worldbank.org/en/impactevaluations/overview-multiple-hypothesis-testing-commands-stata); [S] [updated overview](https://blogs.worldbank.org/impactevaluations/updated-overview-multiple-hypothesis-testing-commands-stata)

**Clustering and randomization inference**
- Abadie, Athey, Imbens and Wooldridge, "When Should You Adjust Standard Errors for Clustering?" (QJE, doi:10.1093/qje/qjac038): clustering is a matter of experimental design. Adjust when treatment assignment is correlated within clusters. Conventional cluster-robust errors can be overly conservative, so the authors propose new variance estimators. — [S] [arXiv 1710.02926](https://arxiv.org/abs/1710.02926)
- Young (2019, QJE 134(2): 557–598) applied randomization inference to 53 experimental papers in AEA journals:
  - tests of individual treatment effects found 13–22% fewer significant results than the authors' methods;
  - joint tests found 33–49% fewer.

  — [S] [IDEAS listing](https://ideas.repec.org/a/oup/qjecon/v134y2019i2p557-598..html)

**Power**
- Ioannidis, Stanley and Doucouliagos (2017, *Economic Journal* 127: F236–F265) surveyed 159 empirical economics literatures with 64,076 estimates. Median statistical power is 18% or less. Nearly 80% of reported effects are exaggerated, typically by a factor of two. — [S] [BITSS](https://www.bitss.org/?p=6019); [S] [Deakin repository](https://dro.deakin.edu.au/articles/journal_contribution/The_power_of_bias_in_economics_research/20826892)
- Camerer et al. (2016) designed their replications with at least 90% power to detect the original effect size at the 5% level. — [S] [Caltech record](https://authors.library.caltech.edu/records/gr9cr-qjb08)

**Attrition and balance**
- Lee (2009, ReStud) bounds are one of the most common ways to examine sensitivity to attrition. They rely on monotonicity, meaning treatment moves attrition in one direction only. They add information only when attrition differs between arms. — [S] [Development Impact: Lee bounds in practice](https://blogs.worldbank.org/en/impactevaluations/lee-bounds-in-practice); [S] [Development Impact: a new bounding approach](https://blogs.worldbank.org/en/impactevaluations/help-for-attrition-is-just-a-phone-call-away-a-new-bounding-approach-to-help-deal-with-non-response)
- The original Lee framework does not account for stratified randomization; adjustments were proposed in January 2026. — [S] [arXiv 2601.12566](https://www.arxiv.org/pdf/2601.12566)
- One 2026 online field experiment reports a typical appendix set: attrition by arm, a CONSORT-style flow with a chi-square test for differential attrition, covariate balance, Lee bounds and multiplicity corrections. — [S] [arXiv 2604.10360](https://arxiv.org/pdf/2604.10360)

### Inferences
- **PRE-01.** If the paper reports an RCT or field experiment and targets an AEA journal, require:
  - an AEA RCT Registry ID (pattern `AEARCTR-\d{7}`) in the title footnote;
  - a matching reference-list entry formatted per the AEA Sample References.

  A missing registration is Major for AEA targets; it should not be Critical, because registration after the trial appears possible. For ReStud, require the registration DOI to be named for the README.
- **PRE-02.** Registration only on OSF or AsPredicted plus an AEA target: warn, mirroring the Data Editor's ⚠️.
- **PRE-03.** When a pre-analysis plan is supplied or reachable, compare its hypotheses, primary outcomes, sample size, exclusions and specifications with the paper. Every deviation should be labelled "not pre-specified" or "exploratory". This is the gap Brodeur et al. identify.
- **PRE-04.** Several outcomes, arms or subgroups without a named FWER or FDR procedure should be flagged. If a correction is used, check that its "family" is defined.
- **PRE-05.** Clustering mismatch. Extract "randomized at the X level" and "standard errors clustered at the Y level", and flag Y finer than X. In lab experiments, the session or matching group is often the independent unit.
- **PRE-06.** Check that a power calculation or minimum detectable effect is reported (pre-registered if possible). Low power plus large estimated effects should be flagged as likely exaggeration, per Ioannidis et al.
- **PRE-07.** Check that balance and attrition tables are present, attrition is tested by arm, and Lee bounds (or similar) are reported when attrition is differential.

### Gaps
- The full current text of the AEA RCT Registry policy was not read. In particular, I could not confirm whether registration after the trial is still accepted in 2026.
- [unverified] AsPredicted and OSF Registries were not checked this session: their templates, private versus public status, embargo rules and DOI issuance.
- [unverified] The original Romano–Wolf papers (2005, 2016), the `rwolf` Stata command, Bruhn and McKenzie (2009) on balance, Athey and Imbens (2017), and the guidance on few clusters (Cameron, Gelbach and Miller 2008; MacKinnon, Nielsen and Webb 2023) were not verified.
- The current status of pre-results review at *Experimental Economics* and of registered reports at JESA and JBEE is unknown.

## 3. Data and code: AEA Data Editor, template README, replication checklists, I4R, BITSS/SSRP, journal data policies

### Takeaway
The Data and Code Availability Standard (DCAS) v1.0 has 16 rules in four areas and is endorsed by 19 economics journals, among them:
- all AEA journals;
- Econometrica, Quantitative Economics and Theoretical Economics;
- ReStud, the Economic Journal, the Econometrics Journal, JEEA and JPE;
- the Canadian Journal of Economics, Economic Inquiry and the Review of Financial Studies.

The AEA Data Editor verifies each replication package before acceptance against the Social Science Data Editors' template README, and ReStud runs a similar process on Zenodo. Management Science, QJE and the Elsevier, Springer and Cambridge behavioral journals are not DCAS endorsers. Management Science has its own Data and Code Disclosure Policy, and QJE has an AEA-modelled policy with the QJE Dataverse. After publication, I4R and BITSS's SSRP and ACRe guide handle reproduction.

### Cited Findings
**AEA Data Editor**
- The current AEA Data and Code Availability Policy is dated February 2026. The February 2024–February 2026 version is archived and marked as superseded. — [S] [AEA policy archive 2024–2026](https://www.aeaweb.org/journals/data/archive/2024-2026)
- What the Data Editor assesses: software availability, data availability and data citations, code availability and clarity, computational resources needed, and the time needed. If resources allow, a computational check is run; otherwise the code is inspected visually. — [G] [reproducibility-checks.md (page dated 2021-04-08)](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/reproducibility-checks.md)
- Outcomes are Accept, Accept with changes, Conditional Accept, or Revise and resubmit.
  - Under "Accept with changes", typical manuscript changes are "missing or erroneous data citations, or minor numerical differences in a small number of table cells". Typical package issues are minor bugs, missing non-critical code, incomplete data provenance in the README, and missing information on software.
  - "Revise and resubmit" covers "significant numerical differences that possibly change the conclusions of the paper" and inadequate data descriptions.

  — [G] [reproducibility-checks.md](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/reproducibility-checks.md)
- Pre-submission checklist (a pilot; guidance dated 2025-12-04, steps dated 2026-02-16):
  - one main file, or a small number of single-software main files, that runs all code;
  - paths with forward slashes, relative to one top-level directory that is set dynamically;
  - all dependencies installed by code: Stata packages into a project subdirectory, R through renv, Python through venv or conda;
  - all figures and tables written to files, with the authors' versions provided;
  - a run on a trusted system (SIVACOR) that produces a certified ZIP.

  — [G] [preparing-replication-package.md](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/preparing-replication-package.md)
- The AEA Data Editor publishes official instructions for AI agents, generated from that guidance. It tells authors to give their AI assistant: "Use https://aeadataeditor.github.io/aea-de-guidance/preparing-replication-package.agent.md to review my replication package…". The generator's preamble begins: "You are an AI assistant helping an economics researcher prepare their replication package…". — [G] [preparing-replication-package.md](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/preparing-replication-package.md); [G] [generate_agent_md.py](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/.github/scripts/generate_agent_md.py)
- "All manuscripts will be checked for data citations." Every dataset not created by the authors must be cited, with an in-text author-date citation and an entry in the manuscript's reference list, as well as in the README. — [G] [preparing-for-data-deposit.md](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/preparing-for-data-deposit.md)
- The code must cover all of the following:
  - reading raw data;
  - cleaning;
  - analysis;
  - tables and figures, including maps;
  - web scraping;
  - processing of confidential data;
  - anonymisation;
  - "code that prepares surveys and runs experiments".

  — [G] [preparing-for-data-deposit.md](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/preparing-for-data-deposit.md)
- Standard required items in Data Editor reports:
  - complete code, including the construction of analysis data from raw data, the appendix tables and figures, and the source of in-text numbers;
  - a mapping from programs to figures and tables;
  - setup programs for Stata, R, Python or Julia;
  - a fixed random seed;
  - tables and figures written out by code, with no manual editing of parameters.

  Action-item priority runs from CRITICAL (rights-restricted content such as PSID, DHS or PII) to CODE, then FILES, then METADATA. — [G] [sample-language-report.md](https://github.com/AEADataEditor/replication-template/blob/HEAD/sample-language-report.md)
- Personally identifiable information (PII) is checked with J-PAL's `PII_stata_scan.do`. Since 2024, reports always remind authors to check their data. Authors must assert that individuals cannot be identified. Leaks still happen, for example a verbatim answer to "who takes care of your child when you are at work" or a respondent's IP address. — [G] [post 2026-05-05 on PII](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_posts/2026-05-05-pii.md)
- Breaches of data terms of use most often involve the PSID and UN Comtrade data. — [G] [post 2024-11-01 on PSID](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_posts/2024-11-01-psid-requests.md)
- The Template README (v1.2.rc1) has these sections:
  - data availability and provenance statements, including rights to use and to redistribute and per-source details;
  - a dataset list;
  - computational requirements: software, controlled randomness (where the seed is set), memory, runtime and storage;
  - description of the code, with optional licences;
  - instructions to replicators;
  - a list of tables and programs, ticking "All numbers provided in text in the paper";
  - references.

  — [G] [template-README.md](https://github.com/social-science-data-editors/template_README/blob/HEAD/template-README.md); web: [social-science-data-editors.github.io/template_README](https://social-science-data-editors.github.io/template_README/)

**DCAS**
- The 16 rules fall into four areas:
  - **Data:** data availability statement (including access limits and the monetary and time cost of access), raw data, analysis data, format, metadata, citation.
  - **Code:** data transformation, analysis, format.
  - **Supporting materials:** instruments (survey instruments or experiment instructions and subject selection), ethics approval, pre-registration, a README following the template.
  - **Sharing:** location in a trusted repository, licence, omissions.

  — [G] [DCAS rules.csv (repo updated 2026-07-25)](https://github.com/social-science-data-editors/DCAS/blob/HEAD/_data/rules.csv)
- Endorsing journals (journals.csv): AEJ Applied, AEJ Policy, AEJ Macro, AEJ Micro, AER, AER: Insights, Canadian Journal of Economics, Econometrica, Econometrics Journal, Economic Inquiry, Economic Journal, JEL, JEP, JEEA, JPE, Quantitative Economics, ReStud, Review of Financial Studies and Theoretical Economics. The site's announcements: Econometric Society 2023-07-01, JEEA 2024-02-01, JPE 2025-06-01. — [G] [DCAS journals.csv](https://github.com/social-science-data-editors/DCAS/blob/HEAD/_data/journals.csv); [S] [datacodestandard.org/journals](https://datacodestandard.org/journals/)
  - Conflict: one search summary said ReStud is not on the endorsing list. Both the DCAS repository and ReStud's own policy say it endorses DCAS v1.0, so I follow the primary sources. — [G] [ReStud policy.md](https://github.com/restud/data-editor/blob/HEAD/policy.md)

**Journal data policies**
- **ReStud** (data-editor site updated 2026-10-09):
  - "the default rule is that you are required to submit all code and data necessary to reproduce your work, and permit any reader of the journal to use them";
  - exemptions must be requested in the cover letter at first submission;
  - confidential data must be preserved for at least five years;
  - the README is uploaded to Zenodo as a separate file next to the ZIP, as PDF, plain text or Markdown, not Word;
  - CC-BY 4.0 is recommended.

  — [G] [policy.md](https://github.com/restud/data-editor/blob/HEAD/policy.md); [G] [package-howto.md](https://github.com/restud/data-editor/blob/HEAD/package-howto.md)
- **QJE** adopted the AER data availability policy. Data, programs and computational details are posted to the QJE Dataverse on Harvard Dataverse before publication. The cover letter must say whether data are proprietary. The minimum for econometric and simulation papers is the datasets and programs used to run the final models. — [S] [QJE Data Policy](https://academic.oup.com/qje/pages/data_policy); [G] [policy text as of Feb 2019 in econ-data-policy](https://github.com/atrisovic/econ-data-policy)
- **Econometrica, Quantitative Economics and Theoretical Economics** endorse DCAS v1.0. — [S] [Econometric Society data policy](https://www.econometricsociety.org/publications/es-data-editor-website/data-and-code-availability-policy)
- **JEEA** requires data and programs before publication, and papers that fail the data policy are not entered into editorial review. — [S] [JEEA Instructions to Authors](https://academic.oup.com/jeea/pages/Author_Guidelines)
- **Management Science** requires disclosure of the data associated with submitted manuscripts. At submission, authors certify that they know the policy and plan to comply. Exceptions are possible, for example for proprietary data under a non-disclosure agreement. After acceptance, data and code are uploaded as one ZIP during "First Look" in ScholarOne. — [S] [Management Science submission guidelines](https://pubsonline.informs.org/page/mnsc/submission-guidelines)
- Fišar, Greiner, Huber, Katok, Ozkes and the Management Science Reproducibility Collaboration (2024, *Management Science* 70(3): 1343–1356) used more than 700 reviewers to assess about 500 articles from before and after the journal's 2019 Data and Code Disclosure policy:
  - when data and resources were accessible, more than 95% of articles under the policy were fully or largely reproduced;
  - for 29% of articles, at least part of the data was not accessible to the reviewer;
  - counting all sampled articles, 68% were reproduced;
  - before the policy, only 12% of articles shared materials voluntarily, and 55% of those could be largely reproduced.

  — [S] [Fišar et al. (repository PDF)](https://research.birmingham.ac.uk/files/216900244/Fisar_et_al.pdf)
- A February 2019 survey of 37 economics journals found that about 65% required data sharing and 27% encouraged it. Many policies were modelled on the AEA's. — [G] [atrisovic/econ-data-policy](https://github.com/atrisovic/econ-data-policy) (dated; for history only)

**I4R, BITSS, SSRP and ACRe**
- The Institute for Replication (I4R), launched in 2022, reproduces and replicates studies published from 2022 onwards in leading journals with data or code policies. Its process:
  - editors invite replicators by email; replicators may stay anonymous, and conflicts of interest are excluded;
  - "Replication Games" bring about 65 researchers, in teams of three to five, to re-analyse about 15 papers, and a pre-analysis plan is required;
  - teams report on a template, and the original authors may respond;
  - reports are released as preprints and collated each year into a meta-paper.

  — [S] [BITSS: Introducing I4R](https://www.bitss.org/introducing-the-institute-for-replication-improving-credibility-through-reproductions-and-replications/); [S] [Brodeur slides, ZBW 2024](https://openscienceretreat.zbw.eu/wp-content/uploads/2024/09/Abel-Brodeur_Institute-for-replication-ZBW-Open-Science.pdf)
- The Social Science Reproduction Platform (SSRP) was built by BITSS as part of the ACRe project, in collaboration with the AEA Data Editor. Reproductions focus on individual claims and display items rather than whole papers. — [S] [SSRP About](https://www.socialsciencereproduction.org/about); [S] [BITSS ACRe](https://www.bitss.org/acre/)
- The ACRe guide scores each display item on a 10-point scale:
  - L1: no data or code;
  - L2: code only;
  - L3: partial analytic data and code;
  - L4: all analytic data and code, but they fail to run or give inconsistent results;
  - L5: analytic data and code reproduce the paper; the guide notes that L5 is "the highest level that most published research papers can attain currently";
  - L6–L9: raw data and cleaning code are partly or fully available, with different failure points;
  - L10: everything reproduces from both analytic and raw data; "aspirational".

  Adjusted levels L3* to L10* apply to restricted data with access instructions or third-party certification, for example cascad. — [G] [BITSS/ACRE 04-assess.Rmd (repo last updated 2022-09-20)](https://github.com/BITSS/ACRE/blob/HEAD/04-assess.Rmd)

### Inferences
- **Manuscript-side checks (paper only).** With only the paper as input, the skill can still check these DCAS and AEA items:
  - a data availability statement exists and names access conditions and costs;
  - every dataset used appears in the reference list;
  - an IRB board name and protocol or exemption number are in the title footnote (AEA);
  - an RCT registry ID is cited;
  - an instructions appendix exists for experiments;
  - code and data availability names a trusted repository (openICPSR, Zenodo, Dataverse). GitHub alone is not trusted per the AEA, as the Gaps section notes.
- **Package-side checks.** When the replication package is supplied, check:
  - the README against the template sections;
  - a mapping from tables and figures to programs, including in-text numbers;
  - a main file, relative paths and dependency setup;
  - fixed seeds and no ZIP files inside the deposit;
  - a PII scan, following J-PAL;
  - an ACRe level for each main display item.

  This would mirror the AEA's official agent.md, which the skill could cite or reuse as its checklist source.
- Venue profiles should carry a "DCAS endorser" flag and the journal's repository (openICPSR for the AEA, Zenodo for ReStud, QJE Dataverse, Management Science's First Look upload).

### Gaps
- I could not identify what changed in the February 2026 AEA policy compared with February 2024.
- Not read:
  - the EJ/RES data-editor process (only the DCAS link: https://academic.oup.com/ej/pages/General_Instructions#data);
  - the JEBO, GEB and JBEE research-data policies (Elsevier);
  - the JRU (Springer) and BPP (Cambridge) data policies;
  - the full *Experimental Economics* data policy.
- The current I4R journal partners, its report template and its error taxonomy document were not read.
- SSRP's current activity is unknown; the ACRe repository was last updated in 2022.
- The statement that GitHub is not a trusted archive comes from the AEA Data Editor's 2026 P&P post. — [G] [post 2026-01-19](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_posts/2026-01-19-preparing-pandp-replication-packages.md) I did not check whether other journals take the same view.

## 4. Common errors found by data editors, I4R and replication studies; replication rates; flagging citations of failed replications

### Takeaway
The most frequent manuscript-side problems flagged by data editors are:
- missing data citations;
- inadequate descriptions of how to access the data;
- unclear replicator instructions;
- small numerical mismatches between the paper and the code output.

I4R's 110-paper mass reproduction found:
- more than 85% computational reproducibility;
- coding errors in about a quarter of papers (26 of 110);
- about 72% of significant estimates still significant under robustness checks.

In the lab, Camerer et al. (2016) replicated 61% of studies (11 of 18), with replication effects averaging about 66% of the original. FReD has a reference-list annotator, a downloadable dataset and a Retraction Watch hook, which suit a "replication status" lookup. However, its economics coverage is thin: 29 unique economics originals in the bundled v2.4.2 snapshot.

### Cited Findings
**Data editors**
- AEA: typical fixes are missing or erroneous data citations, minor numerical differences in a few table cells, minor bugs, missing non-critical code, incomplete provenance and missing software information. — [G] [reproducibility-checks.md](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/reproducibility-checks.md)
- ReStud: "The most frequent revision request is the absence of data citations (see details below); the second is the lack of adequate instructions on how to access the data." Another frequent request is "the lack of clear instructions for replicators." — [G] [ReStud package-howto.md](https://github.com/restud/data-editor/blob/HEAD/package-howto.md)
- The AEA Data Editor calls hard-coded file paths a "FOC (frequently occurring problem) that shouldn't be one". — [G] [post 2021-04-09 on paths](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_posts/2021-04-09-paths.md)

**I4R mass reproduction**
- Brodeur, Mikola, Cook et al., "Mass Reproducibility and Replicability: A New Hope" (I4R DP 107, IZA DP 16912), reproduced 110 papers from leading economics and political science journals:
  - more than 85% of results were fully computationally reproducible;
  - setting aside minor issues such as missing packages or file paths, the abstract reports coding errors in about 25% of studies, some with several errors; the body counts minor or major coding errors in 26 of 110 studies;
  - errors are grouped by element: dependent variable, main independent variable, controls, sample or observations, and estimation;
  - not all errors change the conclusions;
  - 5,511 re-analyses gave about 70% robustness reproducibility.

  — [S] [IZA DP 16912 PDF](https://docs.iza.org/dp16912.pdf); [S] [IZA page](https://www.iza.org/cms/language/en/publications/dp/16912)
- Published as "Reproducibility and robustness of economics and political science research", *Nature* 652: 151–156 (2026), doi:10.1038/s41586-026-10251-x:
  - about 72% of significant estimates stayed significant in the same direction;
  - the median reproduced effect was about 99% of the original;
  - more experienced teams found lower robustness.

  — [S] [Miguel's page](https://emiguel.econ.berkeley.edu/research/reproducibility-and-robustness-of-economics-and-political-science-research/); [S] [Strathprints](https://strathprints.strath.ac.uk/96019/)
  - The working paper says "~70%" robustness and *Nature* says "~72%". The figures may be computed on different bases.

**Replication rates and related evidence**
- Camerer et al. (2016, *Science* 351(6280): 1433–1436, doi:10.1126/science.aaf0918) replicated 18 lab experiments from the AER and QJE (2011–2014). 11 of 18 (61%) found a significant effect in the original direction, and the mean replicated effect was about 66% of the original. Analysis plans were pre-registered. — [S] [Caltech record](https://authors.library.caltech.edu/records/gr9cr-qjb08); [S] [Retraction Watch coverage](https://retractionwatch.com/2016/03/03/more-than-half-of-top-tier-economics-papers-are-replicable-study-finds/)
- FReD labels for those 18 studies, from my analysis of the bundled snapshot:
  - **Failed (7):**
    - Abeler, Falk, Goette and Huffman (2011, AER), "Reference Points and Effort Provision", doi:10.1257/aer.101.2.470;
    - Chen and Chen (2011, AER), "The Potential of Social Identity for Equilibrium Selection", doi:10.1257/aer.101.6.2562;
    - Duffy and Puzzello (2014, AER), "Gift Exchange versus Monetary Exchange", doi:10.1257/aer.104.6.1735;
    - Huck, Seltzer and Wallace (2011, AER), "Deferred Compensation in Multiperiod Labor Contracts", doi:10.1257/aer.101.2.819;
    - Ifcher and Zarghamee (2011, AER), "Happiness and Time Preference", doi:10.1257/aer.101.7.3109;
    - Kuziemko, Buell, Reich and Norton (2014, QJE), "'Last-Place Aversion'", doi:10.1093/qje/qjt035;
    - Marzilli Ericson and Fuster (2011, QJE), "Expectations as Endowments", doi:10.1093/qje/qjr034.
  - **Successful (11):** Ambrus and Greiner (2012); Bartling, Fehr and Schmidt (2012); Charness and Dufwenberg (2011); de Clippel, Eliaz and Knight (2014); Dulleck, Kerschbamer and Sutter (2011); Fehr, Herz and Wilkening (2013); Friedman and Oprea (2012); Fudenberg, Rand and Dreber (2012); Kessler and Roth (2012); Kirchler, Huber and Stöckl (2012); Kogan, Kwasnica and Weber (2011).

  — [G] [forrtproject/FReD, inst/extdata/snapshot/data.RDS](https://github.com/forrtproject/FReD/tree/HEAD/inst/extdata/snapshot)
- Chang and Li (FEDS 2015; *Critical Finance Review* 2022) tried to reproduce 67 papers from 13 economics journals:
  - 22 of 67 (33%) reproduced without the authors' help;
  - 29 of 59 (49%) reproduced with help, excluding confidential-data and missing-software cases;
  - the most common cause of failure was that authors had not supplied files to the journal archives (21 of 38 failures).

  — [S] [Federal Reserve FEDS page](https://www.federalreserve.gov/econres/feds/is-economics-research-replicable-sixty-published-papers-from-thirteen-journals-say-quotusually-notquot.htm); [S] [Development Impact](https://blogs.worldbank.org/impactevaluations/infinite-loop-failure-replication-economics)
- Brodeur, Cook and Heyes (2020, AER, pp. 3634–3660, doi:10.1257/aer.20190687) studied more than 21,000 tests from 25 journals:
  - p-hacking and publication bias vary by method, with IV and to a lesser extent difference-in-differences "particularly problematic";
  - RCTs and regression discontinuity are less affected;
  - there is no evidence that top-five journals or the revise-and-resubmit process reduce the problem.

  — [S] [Birmingham repository](https://research.birmingham.ac.uk/en/publications/methods-matter-p-hacking-and-publication-bias-in-causal-analysis-/); [S] [SSRN](https://papers.ssrn.com/abstract=3249910)
- Two further results were covered in section 2: Young (2019) found 13–49% fewer significant results under randomization inference, and Ioannidis et al. (2017) found median power of 18% or less, with about 80% of effects exaggerated.

**Tools to flag citations of findings that failed to replicate**
- The FReD Annotator "allows users to annotate lists of articles (e.g. reading lists for classes, or reference lists for draft articles) with any replication findings". It is online at forrt-replications.shinyapps.io/fred_annotator. Since FReD package version 0.2.0, the local annotator has been removed and `run_annotator()` opens the web version at forrt.org. — [G] [FReD README](https://github.com/forrtproject/FReD/blob/HEAD/README.md); [G] [FReD NEWS.md](https://github.com/forrtproject/FReD/blob/HEAD/NEWS.md)
- FReD data sources: the dataset is an .xlsx at `https://osf.io/2tbvd/download`, and the Retraction Watch database is pulled from Crossref Labs (`https://api.labs.crossref.org/data/retractionwatch`). There is an offline mode with a reminder after 30 days. The package offers several success criteria: replication significance, aggregate significance, CI and prediction-interval consistency, homogeneity, and "small telescopes". — [G] [R/zzz_parameters.R](https://github.com/forrtproject/FReD/blob/HEAD/R/zzz_parameters.R); [G] [R/replication_outcomes.R](https://github.com/forrtproject/FReD/blob/HEAD/R/replication_outcomes.R)
- Bundled snapshot, dataset version 2.4.2 (2025-06-25; repo updated 2026-06-23), from my analysis:
  - 2,164 rows and 786 unique original DOIs;
  - outcomes: 985 successful, 787 failed, 359 mixed, 18 "statistically successful but flawed", 10 descriptive only, 5 uninformative;
  - largely psychology: 643 social psychology rows and 439 cognitive psychology rows;
  - Economics: 104 rows covering 29 unique originals (15 successful, 10 failed, 4 mixed), mostly AER and QJE;
  - fields include `doi_o`, `doi_r`, `reported_success`, `reported_success_quote`, `claim_text_o`, effect sizes and Ns, and pre-registration flags.

  — [G] [FReD snapshot](https://github.com/forrtproject/FReD/tree/HEAD/inst/extdata/snapshot)
- FLoRA, FORRT's separate library of reproduction and replication attempts, has its own annotator. It lists attempts for a given reference and labels them Successful, Failed or Mixed according to how the replication authors describe their results. It holds no statistical data. — [S] [FLoRA](https://forrt.org/replication-hub/flora/)
- A 2024 data paper describes FReD as hosting 1,239 original findings paired with replications. This uses a different unit from the snapshot's 786 DOIs. — [S] [The Replication Database (UvA DARE)](https://www.dare.uva.nl/id/8f33ae48-bbfe-4bbf-b192-38c104874595)

### Inferences
- **Proposed check CIT-14, replication status (LOOKUP).** Cache the FReD .xlsx and the Crossref Retraction Watch CSV, match the paper's reference DOIs, and report every replication with its label, the replication DOI and the `reported_success_quote`.
  - Severity: Suggestion by default. Major if the paper presents a failed or mixed finding as established, or rests a key premise on it. Critical if the cited work is retracted (CIT-05).
  - Never call a finding "false"; show the labels and the quotes.
  - FReD's economics coverage is thin, so I4R discussion papers should be added as a second source.
- **Manuscript-side analogues of data-editor errors to check:**
  - every dataset is cited;
  - there is a data availability statement;
  - every in-text number maps to a table or a script (the AEA asks for inline numbers to be mapped). The skill can list in-text numbers that appear in no table, so authors can map them.
- **The I4R error categories map onto COMPARE and READ checks:**
  - definitions of the dependent and key independent variables match between text, table notes and appendix;
  - control sets match across tables;
  - sample sizes reconcile across tables (NUM-05);
  - the estimator described in the text matches the table notes.

### Gaps
- I4R's own error-type taxonomy and per-paper reports were not read (econstor and i4replication.org were blocked).
- [unverified] ReplicationWiki (Göttingen) and The Replication Network, both economics-specific replication catalogues, were not checked.
- [unverified] Camerer et al. (2018), the Social Sciences Replication Project, was not verified, nor were classic cases such as Herndon, Ash and Pollin (2014) on Reinhart–Rogoff.
- The AEA Data Editor's annual reports in AEA Papers and Proceedings, which carry statistics on issue frequency, were not accessed.

## 5. Submission requirements at the main behavioral economics outlets

### Takeaway
Only part of each journal's rules could be confirmed, because publisher pages were blocked and the search budget ran out. The confirmed rules are listed below with their sources. Several frequently quoted limits, including QJE's 250 words, GEB's 250 words and JEEA's roughly 150 words, come only from third-party guides and must be re-verified before they go into venue profiles. Two rules are confirmed and AEA-wide:
- the IRB and RCT-registry footnote rules;
- data citations formatted per the AEA Sample References (author-date).

The AI-use rule (AI may not be an author, and its use is disclosed at submission) is confirmed for the AER; whether the AEJs have the same wording is unconfirmed.

### Cited Findings
**AER, AER: Insights and the AEJs (AEA)**
- AER: "An abstract of 100 or fewer words is required." The manuscript should be a PDF under 10 MB where reasonably possible. — [S] [AER submission guidelines](https://www.aeaweb.org/journals/aer/submissions)
- AER editorial policy on AI:
  - AI software cannot be listed as an author;
  - authors who used AI in drafting or editing must briefly describe that use during submission, and remain fully responsible for the output;
  - referees must disclose any AI use in their cover letter and may only use tools that guarantee the manuscript will not be used for training.

  I did not see AI language in the excerpts of the AEJ and AER: Insights policies, and I found no single AEA-wide AI policy. — [S] [AER editorial policy](https://www.aeaweb.org/journals/aer/editorial-policy); [S] [AEJ: Policy editorial policy](https://www.aeaweb.org/journals/pol/about-pol/editorial-policy); [S] [AEJ: Applied editorial policy](https://swlb1.aeaweb.org/journals/app/editorial-policy)
- Disclosure statements:
  - each coauthor submits a separate PDF disclosure statement covering funding sources, other conflicts of interest and, if applicable, IRB approval;
  - authors with nothing to disclose must say so explicitly;
  - full statements are posted with the paper;
  - failure to disclose may reverse acceptance;
  - for AER: Insights, a missing statement makes the submission incomplete.

  — [S] [AEA Disclosure Policy](https://www.aeaweb.org/journals/policies/disclosure-policy); [S] [AER: Insights submissions](https://www.aeaweb.org/journals/aeri/submissions); [S] [AEA P&P editorial policy](https://swlb1.aeaweb.org/journals/pandp/editorial-policy)
- IRB: give the ethics board's name and the approval or exemption record number in the title footnote and the disclosure statement. The AEA Data Editor's template checks for "protocol number and home institution", and flags cases where approval is mentioned only in the cover letter. — [G] [DCAS-compliance-v1.csv (§16 quote)](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_data/DCAS-compliance-v1.csv); [G] [REPLICATION.md](https://github.com/AEADataEditor/replication-template/blob/HEAD/REPLICATION.md)
- RCTs: registration in the AEA RCT Registry, cited in the title footnote and the references (see section 2).
- Reference style: AEA Sample References, author-date. In-text citations look like "Smith (2020)" or "(Smith, 2020)", and the guidance points to the *Chicago Manual of Style* author-date quick guide. Data citations follow the same Sample References. — [G] [preparing-for-data-deposit.md](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/preparing-for-data-deposit.md); the Sample References page itself (not read): [aeaweb.org/journals/policies/sample-references](https://www.aeaweb.org/journals/policies/sample-references); [S] [JEL Style Guide](https://www.aeaweb.org/journals/jel/style-guide)
- JEL codes: the JEL classification published by the AEA is "the de facto standard classification system" for economics. The AEA's openICPSR deposit requires a JEL classification. — [S] [ZBW JEL page](https://zbw.eu/beta/external_identifiers/jel/about.en.html); [G] [REPLICATION.md, deposit metadata](https://github.com/AEADataEditor/replication-template/blob/HEAD/REPLICATION.md)
- AER: Insights has a 6,000-word limit that excludes the abstract, keywords and JEL codes. This comes from the 2017 call for papers and may be out of date. — [S] [AER: Insights call for papers](https://www.aeaweb.org/news/aer-insights-call-for-papers-dec-1-2017)

**QJE (OUP)**
- QJE's data policy is described in section 3. A third-party guide claims a 250-word abstract and required JEL codes; these are unconfirmed. — [S] [QJE Data Policy](https://academic.oup.com/qje/pages/data_policy); [3P] [Manusights](https://manusights.com/blog/is-my-paper-ready-for-quarterly-journal-of-economics)

**Management Science (INFORMS)**
- The abstract must be 250 words or fewer, per the official submission guidelines; a third-party template says about 200, which I disregard. Review is double-anonymous, and the data and code disclosure policy is described in section 3. — [S] [Management Science submission guidelines](https://pubsonline.informs.org/page/mnsc/submission-guidelines); [S] [Editorial statement](https://pubsonline.informs.org/page/mnsc/editorial-statement)
- A third-party guide claims that an "AsCollected" project URL is disclosed at submission. This is unconfirmed. — [3P] [Manusights](https://manusights.com/blog/management-science-submission-guide)

**JEBO (Elsevier)**
- The abstract must not exceed 250 words, stand alone and define non-standard abbreviations. Highlights are required at submission: bullet points that capture the novel results and methods. There is a US$175 submission fee for new manuscripts. — [S] [JEBO Guide for Authors](https://www.sciencedirect.com/journal/journal-of-economic-behavior-and-organization/publish/guide-for-authors)
- Elsevier's AI declaration (applies to JEBO, GEB and JBEE):
  - a section titled "Declaration of generative AI and AI-assisted technologies in the [writing / manuscript preparation] process" goes immediately before the references; the two sources word the title differently;
  - suggested wording: "During the preparation of this work the author(s) used [NAME OF TOOL / SERVICE] in order to [REASON]…", followed by a statement that the authors reviewed the output and take responsibility;
  - basic grammar and spelling checks need no declaration.

  — [3P] [CASRAI summary](https://www.casrai.org/guides/elsevier-generative-ai-authorship-policy); [3P] [Enago summary](https://www.enago.com/responsible-ai-movement/publisher-ai-guidelines/elsevier-ai-guidelines)

**Experimental Economics and JESA (Cambridge, ESA)**
- No deception; participants must be incentivized; instructions at submission; separate data appendices; fully open access from Volumes 28 and 11 (section 1). — [S] [About this journal](https://www.cambridge.org/core/journals/experimental-economics/information/about-this-journal); [S] [Cambridge blog](https://www.cambridge.org/core/blog/?p=61413)

**JEEA (OUP, European Economic Association)**
- Rules confirmed:
  - only EEA members may submit;
  - a €100 fee applies from 1 February 2026, non-refundable, waived when all authors are in low- or middle-income countries;
  - submissions are PDF only and in English;
  - the data policy is described in section 3;
  - JEL codes improve discoverability.
- The abstract length is unconfirmed; a template site says about 150 words.

— [S] [JEEA Instructions to Authors](https://academic.oup.com/jeea/pages/Author_Guidelines); [S] [JEEA Submission Fee](https://eeassoc.org/jeea-submission-fee)

**Journal of Risk and Uncertainty (Springer)**
- The official page is springer.com/journal/11166/submission-guidelines; I did not read it. The scope covers decision theory, psychological models of choice, experiments and empirical risk-taking. A third-party note says short notes and pure finance papers are generally not considered; this is unconfirmed. — [S] [CIRAD listing pointing to Springer page](https://ou-publier.cirad.fr/en/node/3901)

**Games and Economic Behavior and the Journal of Behavioral and Experimental Economics (Elsevier)**
- I found no official rules. One third-party Claude-skill file claims a 250-word abstract for GEB. — [3P] [claudskills GEB SKILL.md](https://claudskills.com/skills/games-and-economic-behavior/SKILL.md)

**Behavioural Public Policy (Cambridge)**
- Submission is through ScholarOne. Article types are Research Articles, Findings from the Field, New Voices, Perspectives, Political Economy of BPP pieces, Book Review Essays, Debate Essays and Responses. Special issues may have different word limits. The detailed limits are on the "instructions-contributors" page, which I did not read. — [S] [BPP author instructions](https://core-cms.cambridgecore.org/core/journals/behavioural-public-policy/information/author-instructions)

**ReStud (OUP; extra profile)**
- "Insights" papers are limited to 6,000 words and 5 exhibits; "Communications" to 2,000 words and 2 exhibits. The count covers the main body, including equations, footnotes and endnotes. It excludes the title page, author names, abstract, acknowledgement footnote, references and exhibits. The Data Editor provides an in-browser PDF word counter. — [G] [restud/data-editor word-count/index.html (repo updated 2026-10-09)](https://github.com/restud/data-editor/blob/HEAD/word-count/index.html)

**Cross-publisher**
- Publishers broadly agree that AI tools cannot be authors, and most require disclosure in the manuscript. — [3P] [CASRAI publisher landscape](https://www.casrai.org/guides/ai-in-manuscripts-publisher-policy-landscape)

### Inferences
- Draft venue-profile fields for the behavioral module:
  - `abstract_max_words`: AER 100; Management Science 250; JEBO 250; others unknown or unverified.
  - `jel_required`;
  - `highlights_required`: JEBO yes; other Elsevier journals likely, unverified;
  - `review_anonymity`: Management Science double-anonymous; others unknown;
  - `ai_disclosure`: AER, described at submission; Elsevier, a declaration section before the references;
  - `irb_location`: AEA, the title footnote with board and protocol number;
  - `rct_registry`: AEA, required for field RCTs;
  - `deception_policy`: *Experimental Economics* and JESA, prohibited;
  - `incentives_required`: *Experimental Economics*;
  - `data_policy`: DCAS endorser or own policy;
  - `fee`: JEBO US$175; JEEA €100;
  - `reference_style`: AEA author-date for AEA journals.
- Each profile should carry `source_url`, `verified_on` and `confidence`, because these rules change: for example, JEEA's fee from February 2026 and the AEA data policy revision in February 2026.
- An AEA-target check for significance stars should stay at "Suggestion" until the AEA style rule is verified (see section 8).

### Gaps
- Not confirmed from official pages:
  - abstract limits for QJE, GEB, JRU, JBEE, BPP, JEEA and the AEJs;
  - JEL-code requirements;
  - highlights for GEB and JBEE;
  - blind-review mode for AEA journals (believed single-anonymous, [unverified]), QJE, JEEA, Elsevier, Springer and Cambridge journals;
  - IRB statement rules outside AEA and ReStud.
- The AI policies of Springer Nature (JRU), Cambridge (*Experimental Economics*, JESA, BPP), OUP (QJE, JEEA, ReStud, EJ) and INFORMS (Management Science) were not confirmed. No INFORMS-specific AI policy turned up in search.
- [unverified] It is not confirmed whether AEA style forbids significance asterisks. One AEA forum commenter's impression is that it does, which is not policy. — [S] [AEA forum thread](https://swlb1.aeaweb.org/forum/1231/should-regression-tables-use-for-significant-coefficients)
- Management Science's anonymisation details and *Experimental Economics*' current article length rules were not read.

## 6. Writing guides economists use as checklists, and economics-specific AI review tools

### Takeaway
Only Keith Head's regression-table rules and the statistical-versus-economic significance critique (McCloskey and Ziliak) could be confirmed from sources this session. Cochrane, McCloskey's *Economical Writing*, Shapiro, Bellemare and Head's introduction formula remain unverified leads.

On AI tools, Refine (refine.ink), co-founded in 2025 by Northwestern economist Ben Golub, is the leading economics-specific AI referee, and reportedly several top-five journals are experimenting with it. Anton Korinek's JEL article (2023) and its updates (December 2024; August 2025, on agents) are the reference guides. The AEA Data Editor itself publishes an agent instruction file for replication packages.

### Cited Findings
**Writing and table guides**
- Keith Head, "The 10 Commandments for Regression Tables":
  - display standard errors, not t-statistics or p-values;
  - if significance is shown at all, use superscripts "a" (1%), "b" (5%) and "c" (10%).

  — [S] [Keith Head, Regression Tables](https://blogs.ubc.ca/khead/research/research-advice/regression-tables)
- Marc Bellemare describes the AJAE production team's house rule: list only the significance symbols that actually appear in a table. — [S] [Bellemare post (WordPress API URL)](https://marcfbellemare.com/wordpress/wp-json/wp/v2/posts/13586)
- McCloskey and Ziliak (1996, JEL 34(1): 97–114), "The Standard Error of Regressions", argue that statistical significance should not be the focus of empirical economics. — [S] [IDEAS](https://ideas.repec.org/a/aea/jeclit/v34y1996i1p97-114.html)
- J.W. Mason's "A modest proposal: No more *s" argues that stars confound statistical and economic significance. — [S] [jwmason.org](https://jwmason.org/?p=430)
- Imbens (2021, JEP), "Statistical Significance, p-Values, and the Reporting of Uncertainty". — [T] [PDF copy](https://edisciplinas.usp.br/pluginfile.php/8050685/mod_resource/content/1/imbens-2021-statistical-significance-p-values-and-the-reporting-of-uncertainty.pdf)

**AI review and research tools in economics**
- Refine Technologies, Inc. was co-founded in 2025 by Ben Golub, a Northwestern professor of economics and computer science who is its Chief Scientist, and Yann Calvó López. It builds AI tools that give structured, referee-style feedback on research papers. The feedback identifies errors in mathematics and empirical strategy, clarity problems and consistency issues. — [S] [Wikipedia: Benjamin Golub](https://en.wikipedia.org/wiki/Benjamin_Golub); [S] [Northwestern Economics newsletter, Winter 2026](https://economics.northwestern.edu/about/newsletter/2026-winter-newsletter/faculty-updates-winter-2026.html)
- A Marginal Revolution post (March 2026) gives two second-hand reports: several top-five journals are experimenting with Refine, and Golub says that on papers already refereed at top journals Refine found problems in at least a third of cases. Neither claim comes from a published study. — [S] [Marginal Revolution, "Is AI currently helping economic research?"](https://marginalrevolution.com/marginalrevolution/2026/03/is-ai-currently-helping-economic-research.html)
- John Cochrane on Refine's comments on his inflation booklet: "on the par of the best comments I've received on a paper in my entire academic career". — [S] [Arnold Kling, "John Cochrane gets AI-pilled"](https://arnoldkling.substack.com/p/john-cochrane-gets-ai-pilled)
- Golub gave talks in December 2025: "Modern AI for Economics Research: An Overview of Tools" at Princeton BCF and Markus' Academy. A separate Substack post covers his views on AI referees; I did not open it. — [S] [Princeton BCF event](https://bcf.princeton.edu/events/benjamin-golub-on-modern-ai-for-economics-research-an-overview-of-tools/); [S] [Markus' Academy](https://markusacademy.substack.com/p/modern-ai-for-economics-research); [S] [Empiricrafting](https://empiricrafting.substack.com/p/ben-golub-ai-referees-social-learning)
- Anton Korinek's series:
  - "Generative AI for Economic Research: Use Cases and Implications for Economists", JEL 61(4) (2023), describes use cases in six areas: ideation and feedback, writing, background research, data analysis, coding, and mathematical derivations;
  - "LLMs Learn to Collaborate and Reason" updated it in December 2024 (NBER w33198);
  - "AI Agents for Economic Research" (August 2025) covers building agents that run literature reviews, write and debug econometric code, fetch data and coordinate workflows, as of mid-2025.

  — [S] [JEL article page](https://www.aeaweb.org/articles?id=10.1257%2Fjel.20231736); [S] [NBER w33198](https://www.nber.org/papers/w33198); [S] [GenAI for Econ updates (Substack)](https://genaiforecon.substack.com)
- The AEA Data Editor's official agent instructions for replication-package review are described in section 3. — [G] [generate_agent_md.py](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/.github/scripts/generate_agent_md.py)
- "Read the Paper, Write the Code: Agentic Reproduction of Social-Science Results" (arXiv, April 2026) is a paper on agentic reproduction. — [T] [arXiv 2604.21965](https://arxiv.org/html/2604.21965v1)
- RegCheck compares registrations with papers (section 2). — [T] [arXiv 2601.13330](https://arxiv.org/pdf/2601.13330)
- Third-party Claude-style "skills" for economics journal submission exist: claudskills.com SKILL.md files for GEB, JRU and JEBO, and minicod.com's "AER Submission" final pre-submission audit. Their content was not inspected. — [3P] [claudskills GEB](https://claudskills.com/skills/games-and-economic-behavior/SKILL.md); [3P] [claudskills JRU](https://claudskills.com/skills/journal-of-risk-and-uncertainty/SKILL.md); [3P] [claudskills JEBO](https://claudskills.com/skills/journal-of-economic-behavior-and-organization/SKILL.md); [3P] [minicod AER Submission](https://www.minicod.com/skills/aer-submission)

### Inferences
- Refine is the closest competitor for economics. The skill can set itself apart through:
  - verbatim quotes and proof trails;
  - venue-compliance profiles (AEA footnotes, DCAS, deception rules);
  - replication-infrastructure checks (data citations, registry IDs, FReD and Retraction Watch);
  - reproducibility checks aligned with the AEA's agent.md.

  These are design inferences, not claims about what Refine lacks, since Refine's feature list was not examined.
- Table rules worth encoding as SCRIPT checks:
  - the uncertainty measure (SE, CI or t-statistic) is stated;
  - star legends list only the symbols used;
  - stars are defined;
  - the significance thresholds are stated.

### Gaps
- The following are unverified this session; their content is from memory and must be checked before it goes into the skill:
  - [unverified] John Cochrane, "Writing Tips for Ph.D. Students" (2005), on his website. From memory: put the main result first, keep the abstract and introduction short, cut the literature review from the front, and use concrete language.
  - [unverified] Deirdre McCloskey, *Economical Writing* (3rd edition, University of Chicago Press, 2019).
  - [unverified] Jesse Shapiro, "Four Steps to an Applied Micro Paper" and "How to Give an Applied Micro Talk".
  - [unverified] Marc Bellemare, "How to Write Applied Papers in Economics" (slides on paper structure).
  - [unverified] Keith Head, "The Introduction Formula". From memory: Hook → Question → Antecedents → Value-added → Roadmap.
- Refine's pricing, methods, journal partnerships and any accuracy evaluation were not verified, nor whether the August 2025 Korinek update has a newer successor.

## 7. Classic behavioral economics findings that are commonly misattributed or miscited

### Takeaway
I could not run the planned searches on misattribution, because the search budget ran out. The verified evidence I have comes from the FORRT Replication Database (FReD) snapshot. It flags several behavioral classics that are widely cited in behavioral economics papers as failed or mixed replications:
- scarcity and poverty cognition: Mani et al. 2013; Shah et al. 2012;
- the moral-reminder honesty study: Mazar, Amir and Ariely 2008;
- ego depletion: Muraven, Tice and Baumeister 1998;
- money priming;
- the decoy effect;
- most anchoring variants.

Several core findings replicated: the 1981 framing effect, availability, the Mt Everest anchoring task, default effects on organ-donor consent, and money illusion. The loss-aversion λ ≈ 2.25 point (from Tversky and Kahneman 1992, not the 1979 prospect theory paper) and other attribution errors are listed as unverified leads.

### Cited Findings
All findings in this section come from my analysis of the bundled FReD snapshot (v2.4.2). Outcome labels follow each replication's own description. — [G] [forrtproject/FReD snapshot](https://github.com/forrtproject/FReD/tree/HEAD/inst/extdata/snapshot)

**Failed**
- Mani, Mullainathan, Shafir and Zhao (2013, *Science*), "Poverty Impedes Cognitive Function".
- Shah, Mullainathan and Shafir (2012, *Science*), "Some Consequences of Having Too Little".
- Shah, Zhao, Mullainathan and Shafir (2018, *Social Cognition*), "Money in the Mental Lives of the Poor".
- Mazar, Amir and Ariely (2008, JMR), "The Dishonesty of Honest People" (moral priming).
- Muraven, Tice and Baumeister (1998, JPSP), "Self-control as a limited resource".
- Small, Loewenstein and Slovic (2007), on identifiable versus statistical victims.
- Kouchaki and Gino (2016, PNAS).
- Caruso, Vohs, Baxter and Waytz (2013), money exposure and free-market endorsement.
- Johnson, Bellman and Lohse (2002), defaults in privacy opt-in and opt-out.
- Connolly, Reb and Kausel (2013), on the decoy effect.
- Mussweiler and Englich (2005), subliminal anchoring.
- Rottenstreich and Hsee (2001), "Money, Kisses, and Electric Shocks".

**Mixed**
- Vohs, Mead and Goode (2006, *Science*), "The Psychological Consequences of Money".
- Tversky and Shafir (1992), the disjunction effect.
- Mellers, Hertwig and Kahneman (2001), conjunction effects.

**Successful**
- Tversky and Kahneman (1981, *Science*), "The Framing of Decisions and the Psychology of Choice" (Many Labs).
- Tversky and Kahneman (1973), availability.
- Jacowitz and Kahneman (1995), anchoring on the height of Mt Everest.
- Johnson and Goldstein (2003, *Science*), "Do Defaults Save Lives?".
- Shafir, Diamond and Tversky (1997, QJE), "Money Illusion".
- Gneezy, Keenan and Gneezy (2014, *Science*), overhead aversion in charity.
- Shah, Shafir and Mullainathan (2015, *Psychological Science*), "Scarcity Frames Value".
- Heath, Larrick and Wu (1999), "Goals as Reference Points".

**Anchoring across all FReD entries:** 33 rows, of which 24 failed, 7 succeeded and 2 were mixed.

**Camerer et al. (2016) lab replications:** 7 failed, including Marzilli Ericson and Fuster (2011, QJE), "Expectations as Endowments", which is often cited for reference-dependent preferences, and Abeler et al. (2011, AER), "Reference Points and Effort Provision". The full list is in section 4.

### Inferences
- Proposed check BEH-CIT-01: run the replication-status lookup (CIT-14) on every reference. Also keep a curated, hand-verified "classic claims" table holding the canonical source, the parameter values and the replication status. A checker can then catch misattribution (wrong source for a number) and over-claiming (a failed finding cited as settled).
- Proposed check BEH-CIT-02: when a paper quotes a parameter value next to a citation, such as "λ ≈ 2.25 (Kahneman and Tversky 1979)", compare the pair with the curated table. This combines a SCRIPT regex for the number with the citation key and a LOOKUP.
- FReD labels are per replication, and studies can have several replications with different outcomes. Report every entry rather than one verdict.

### Gaps
None of the following could be checked against sources this session. They are leads from memory and must be confirmed before any of them goes into the curated table.
- [unverified] Loss aversion λ = 2.25, together with α = β = 0.88 and probability-weighting γ = 0.61 for gains and δ = 0.69 for losses, comes from Tversky and Kahneman (1992), "Advances in Prospect Theory: Cumulative Representation of Uncertainty", *Journal of Risk and Uncertainty* 5(4): 297–323. Kahneman and Tversky (1979, *Econometrica* 47(2): 263–291) proposed a value function steeper for losses but did not estimate λ.
- [unverified] Newer meta-analyses of loss aversion report lower central values than 2.25: Brown, Imai, Vieider and Camerer (2024, JEL) and Walasek, Mullett and Stewart (2024). The exact figures were not verified.
- [unverified] The quasi-hyperbolic (β–δ) model was introduced by Phelps and Pollak (1968, ReStud) and popularized by Laibson (1997, QJE). The term "present bias" is usually credited to O'Donoghue and Rabin (1999, AER).
- [unverified] The term "endowment effect" comes from Thaler (1980, JEBO, "Toward a Positive Theory of Consumer Choice"). The mug experiments are Kahneman, Knetsch and Thaler (1990, JPE).
- [unverified] The dictator game is often credited to Forsythe et al. (1994, GEB), but it appears earlier in Kahneman, Knetsch and Thaler (1986). The ultimatum game is from Güth, Schmittberger and Schwarze (1982, JEBO), and the trust game from Berg, Dickhaut and McCabe (1995, GEB).
- [unverified] The "hot hand fallacy" (Gilovich, Vallone and Tversky 1985) was challenged by Miller and Sanjurjo (2018, *Econometrica*), who showed a streak-selection bias that reverses the original inference.
- [unverified] Choice overload: the jam study (Iyengar and Lepper 2000, JPSP) has a meta-analytic mean effect near zero (Scheibehenne, Greifeneder and Todd 2010, JCR). FReD had no entry for it in this snapshot.
- [unverified] The "93% of drivers think they are above average" claim (Svenson 1981) refers to a US student sample; the Swedish sample was lower, about 69%. The figure is often misquoted.
- [unverified] Effect sizes and retractions:
  - Nudge-unit trials show much smaller effects than academic journals: DellaVigna and Linos (2022, *Econometrica*) report about 1.4 percentage points, versus about 8.7 in published studies.
  - Maier et al. (2022, PNAS) find no evidence for nudging after correcting for publication bias.
  - Shu et al. (2012, PNAS), on signing an honesty pledge at the top of a form, was retracted in 2021.
- Retraction status should come from Crossref and Retraction Watch (CIT-05) rather than from memory.

## 8. Economics-specific reporting pitfalls a checker could detect

### Takeaway
Several pitfalls specific to economics are both common and mechanically detectable:
- clustering finer than the level of treatment assignment;
- standard-error type not stated;
- significance stars undefined or used in place of uncertainty;
- statistical significance read as economic significance;
- multiple outcomes left uncorrected;
- p-values bunched just below thresholds, especially in IV and difference-in-differences papers;
- likely exaggerated effects from underpowered designs;
- in-text numbers that no table or code produces.

Percentage points versus percent, log-outcome coefficients, standardized effect sizes, log(1+y) and the inverse hyperbolic sine are classic interpretation errors. The arithmetic for checking them is given under Inferences, but their canonical economics citations were not verified this session.

### Cited Findings
- **Clustering.** Follow the design: adjust when assignment is correlated within clusters; conventional cluster-robust errors can be overly conservative. — [S] [Abadie, Athey, Imbens and Wooldridge (arXiv 1710.02926)](https://arxiv.org/abs/1710.02926)
- **Randomization inference.** Conventional inference overstates significance in AEA experimental papers: randomization tests find 13–22% fewer significant individual effects and 33–49% fewer significant joint results. — [S] [Young 2019](https://ideas.repec.org/a/oup/qjecon/v134y2019i2p557-598..html)
- **Tables.** Report standard errors rather than t-statistics or p-values; if significance is shown, use a/b/c superscripts. The AJAE lists only the symbols used. — [S] [Keith Head](https://blogs.ubc.ca/khead/research/research-advice/regression-tables); [S] [Bellemare](https://marcfbellemare.com/wordpress/wp-json/wp/v2/posts/13586)
- **Statistical versus economic significance.** — [S] [McCloskey and Ziliak 1996](https://ideas.repec.org/a/aea/jeclit/v34y1996i1p97-114.html)
- **p-hacking by method.** IV and difference-in-differences are most affected; RCTs and RDD less. — [S] [Brodeur, Cook and Heyes 2020](https://research.birmingham.ac.uk/en/publications/methods-matter-p-hacking-and-publication-bias-in-causal-analysis-/)
- **Pre-analysis plans.** Pre-registration without a PAP does not reduce p-hacking. — [S] [Brodeur et al. 2024](https://www.iza.org/publications/dp/15476)
- **Power and exaggeration.** Median power is 18% or less, and about 80% of effects are exaggerated, typically twofold. — [S] [Ioannidis, Stanley and Doucouliagos 2017](https://www.bitss.org/?p=6019)
- **Multiple testing.** FWER corrections (List–Shaikh–Xu, Romano–Wolf) and FDR corrections (Anderson sharpened q-values); see section 2. — [S] [List–Shaikh–Xu](https://ideas.repec.org/a/kap/expeco/v22y2019i4d10.1007_s10683-018-09597-5.html); [S] [World Bank MHT overview](https://blogs.worldbank.org/en/impactevaluations/overview-multiple-hypothesis-testing-commands-stata)
- **Numbers that no table produces.** Data editors ask that in-text numbers be traceable to code. The template README asks authors to tick "All numbers provided in text in the paper". Numerical differences in table cells are a standard Data Editor finding. — [G] [template-README.md](https://github.com/social-science-data-editors/template_README/blob/HEAD/template-README.md); [G] [reproducibility-checks.md](https://github.com/AEADataEditor/aeadataeditor.github.io/blob/HEAD/_guidance/reproducibility-checks.md)

### Inferences
These are proposed detection rules for the behavioral module. Most are SCRIPT or READ checks over the paper map.
- **ECON-01, percent versus percentage points.** For each change in a rate or share, compute both the absolute difference (pp) and the relative difference (%), and compare them with the wording.
  - Example: a rise from 20% to 25% is 5 percentage points, or 25%. A paper that says "increased by 5%" is ambiguous or wrong.
  - Flag "%" next to differences of shares when the arithmetic implies pp, and the reverse. The check needs the baseline mean, usually the control-group mean in the table.
- **ECON-02, log outcomes.** In ln(y) = a + bD with a dummy D, the exact percentage effect is 100·(exp(b) − 1), and 100·b is only an approximation.
  - At b = 0.10 the approximation gives 10% against an exact 10.5%; at b = 0.50 it gives 50% against an exact 64.9%.
  - Flag "a b·100 percent effect" for |b| above roughly 0.1 to 0.15. In log-log models, flag coefficients described as percent changes rather than elasticities.
  - Flag log(1+y) or asinh(y) outcomes interpreted as percentage effects or elasticities without discussing units and zeros. The canonical citations were not verified this session.
- **ECON-03, standardized effects.** Check that the paper says which standard deviation is used (control group, pooled, or baseline) and that "SD" units are not mixed with Cohen's d without definition.
  - When the paper gives the raw effect and the SD, recompute effect ÷ SD and compare.
  - For index outcomes, such as an Anderson-style summary index, the construction should be described.
- **ECON-04, standard errors and stars.**
  - Every regression table states the uncertainty measure: SE, CI or t-statistic, and robust, clustered (at what level) or bootstrapped.
  - Stars are defined, and only the symbols used are defined.
  - Venue-specific star policy stays at Suggestion level until confirmed.
  - Recompute the stars from coefficient and SE (z = b/se against 1.645, 1.96 and 2.576), extending NUM-03.
- **ECON-05, clustering mismatch.** Flag when the level of assignment is coarser than the clustering level. Flag few clusters (for example, fewer than about 30) with no wild-bootstrap or randomization-inference discussion; this threshold is [unverified] and needs a source.
- **ECON-06, "insignificant equals no effect".** Flag "no effect" claims without confidence intervals or minimum detectable effects (links to LOG-09). Flag "marginally significant" (p between 0.05 and 0.10) presented as support.
- **ECON-07, threshold bunching.** Collect all reported p-values and t-statistics. Flag an excess just below 0.05 (t ≈ 1.96 to 2.1) as a suggestion-level "garden of forking paths" risk, especially for IV and difference-in-differences papers. This is a weak signal for a single paper.
- **ECON-08, exaggeration risk.** Large effects with wide confidence intervals and small samples, and no power analysis, give a Minor suggestion to discuss Type M error.
- **ECON-09, multiple testing.** Several primary outcomes or arms with no FWER or FDR adjustment should be flagged (cross-reference PRE-04).
- **ECON-10, in-text numbers.** List every in-text estimate that appears in no table or figure. The author should map it to code, following the template README rule.

### Gaps
- [unverified] Canonical citations for the ECON rules were not verified this session:
  - Halvorsen and Palmquist (1980, AER) and Kennedy (1981, AER) on dummy variables in semilog equations;
  - Bellemare and Wichman (2020, OBES) on the inverse hyperbolic sine;
  - Chen and Roth (2024, QJE), "Logs with Zeros? Some Problems and Solutions";
  - Mullahy and Norton (2024) on transformed outcomes with a mass at zero;
  - Kraft (2020) on interpreting standardized effect sizes;
  - Cameron, Gelbach and Miller (2008) and MacKinnon, Nielsen and Webb (2023) on few-cluster inference;
  - the AEA's table and star rules in its style guide.
- No empirical source was found for how often economics drafts confuse percent with percentage points or misread log coefficients. Prevalence is unknown.
