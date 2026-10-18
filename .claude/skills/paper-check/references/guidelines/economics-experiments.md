# Reporting checklist for economics experiments

Version 0.4.0, 2026-10-17. The composite checklist behind BEH-01 to BEH-16 and MTH-06.

Economics has no reporting guideline of the CONSORT kind, and a targeted search found none for lab or online experiments. This checklist is therefore assembled from journal and data-editor policies, with the source of each rule listed at the end. It applies to lab, online, lab-in-the-field, field and survey experiments; section O covers natural experiments and observational studies.

**How to use it.** Each item says what a paper should report, which check owns it, and where the rule comes from. Items marked **MTH-06** are owned by that check alone (the methods agent); the others feed the named checks, mostly in the behavioral agent. When a venue profile is given, its quoted rules override this list for that journal: they decide what is required and how severe a gap is. A rule here that the venue does not impose is good practice, reported at the lower end of the check's typical severity.

## A. Registration and analysis plan

- **A1 Registration identified** (MTH-07, BEH-06). The registry, the registration ID or DOI, and when the study was registered relative to data collection. Field RCTs submitted to AEA journals must be registered in the AEA RCT Registry, with the `AEARCTR-` ID cited in the title footnote and the reference list. Laboratory experiments are exempt. The AEA Data Editor's template flags registration only on OSF or AsPredicted as a warning. [AEA RCT Registry policy; AEA replication template]
- **A2 Registration in the package** (BEH-06). ReStud asks for the pre-registration's DOI in the replication package's README. [ReStud data policy]
- **A3 Plan followed, deviations labelled** (BEH-07). When a pre-analysis plan exists, the primary outcomes, hypotheses, sample size, exclusions and specifications match it; every deviation is labelled, and exploratory analyses are marked as such. Across thousands of RCT test statistics, registration alone did not reduce p-hacking, while a complete pre-analysis plan did. [Brodeur et al.]

## B. Ethics

- **B1 Approval and consent** (ETH-01). The approving board, the protocol number or the exemption, and how informed consent was obtained.
- **B2 Placement of the approval** (BEH-12). AEA journals expect the IRB's name and the protocol number in the title footnote. ReStud requires the IRB approval documentation in the replication package. [AEA Data Editor compliance list; ReStud data policy]
- **B3 No deception** (BEH-01). Giving participants false information is deception; withholding information is a gray area that needs human judgment. *Experimental Economics* considers only studies without deception and with incentivized participants. Elsewhere, any deception needs a justification (no feasible honest design) and a debriefing. [Experimental Economics, about the journal; Charness, Samek and van de Ven]

## C. Participants and recruitment

- **C1 Subject pool** (MTH-06). The population, the recruitment system (ORSEE, hroot, SONA, Prolific, MTurk or another), and the eligibility and exclusion criteria. [AEA policy for experimental papers]
- **C2 Time and place** (MTH-06). The location, the dates, the number of sessions and the participants per session.
- **C3 Participant flow** (MTH-06; the arithmetic is NUM-05). Recruited, started, excluded with reasons, and analyzed, by arm.
- **C4 Recruitment software cited** (BEH-11). ORSEE's license requires citing Greiner (2015). [ORSEE README]

## D. Design and procedures

- **D1 Treatments** (MTH-06; confounded arms are LOG-08). What differs between arms, and only that; between- or within-subject; the order of tasks.
- **D2 Randomization** (MTH-06). The procedure and the unit of assignment. BEH-09 uses the unit to judge clustering.
- **D3 Matching** (BEH-05). Partner or stranger matching, the size of matching groups, and how roles were assigned.
- **D4 Experiment software cited** (BEH-11). oTree's terms require citing Chen, Schonger and Wickens (2016). Citing Fischbacher (2007) for z-Tree is customary; whether its licence requires it is unconfirmed. [oTree documentation]
- **D5 Procedures** (MTH-06). Oral instructions or the experimenter's script, the timing of stages, and how participants were paid.

## E. Incentives

- **E1 Payment mechanism** (BEH-02). One randomly chosen decision or every round; paying every round needs a justification, because it can create wealth and hedging effects.
- **E2 Amounts** (BEH-02). The exchange rate for experimental currency, the show-up fee, average earnings with their range, session length, and when and how payment was made.
- **E3 Belief elicitation** (BEH-02). The scoring rule and its incentive properties.
- **E4 Incentivized choices** (BEH-02). Hypothetical choices need a stated reason; *Experimental Economics* requires incentivized participants. [Experimental Economics, about the journal]

## F. Materials

- **F1 Instructions** (BEH-03). The full instructions in an appendix (at submission, for AEA journals), translations for sessions not run in English, screenshots, and the comprehension questions. [AEA policy for experimental papers]
- **F2 Experiment files** (BEH-03). The programs that ran the experiment or survey (z-Tree, oTree, Qualtrics `.qsf`, LimeSurvey) in the replication package. At ReStud, a pointer to an online appendix is not enough, because online appendices have no DOI. [AEA policy for experimental papers; AEA replication template; ReStud data policy]

## G. Comprehension, attention and online samples

- **G1 Comprehension checks** (BEH-04). What they asked, and what happened to participants who failed.
- **G2 Exclusions fixed in advance** (BEH-04). Attention checks and exclusion rules stated before the data were seen, ideally in the registration.
- **G3 Prolific's rule** (BEH-04). In studies of five minutes or more, a participant may be rejected only after failing at least two attention checks. Excluding a participant from the analysis is a different decision from rejecting their payment. [Prolific attention-check policy]
- **G4 Online data quality** (MTH-06). The platform and prescreens, screens for bots, AI-assisted answers and very fast completion, and the hourly pay.

## H. Analysis and inference

- **H1 Primary outcomes** (MTH-05). The primary outcomes and hypotheses named, and the main specification identified before the robustness checks.
- **H2 Clustering** (BEH-09). The type of standard errors stated, and errors clustered at the level of treatment assignment. With few clusters, a wild cluster bootstrap or randomization inference; in AEA experimental papers, randomization inference finds fewer significant effects than conventional methods. [Abadie, Athey, Imbens and Wooldridge; Young]
- **H3 Independent units** (BEH-05). When participants interact, sessions or matching groups are the independent units of observation.
- **H4 Multiple testing** (BEH-08). With several outcomes, arms or subgroups, a family-wise or false-discovery correction with its family defined: List-Shaikh-Xu, Romano-Wolf, Holm, or Anderson's sharpened q-values. [List, Shaikh and Xu]
- **H5 Power** (BEH-10). An ex-ante power analysis or a minimum detectable effect.
- **H6 Attrition and balance** (BEH-10). Attrition by arm with a test for differences, a balance table, and bounds such as Lee bounds when attrition differs between arms.
- **H7 Tests and effect sizes** (MTH-04). Each test named; effect sizes with standard errors or intervals.

## I. Structural estimates

- **I1 Behavioral parameters** (BEH-14). Present bias, the discount factor, loss aversion, risk aversion and social-preference weights reported with standard errors, values in a plausible range, the argument for what identifies them, and their sensitivity to assumptions such as utility curvature.

## J. Data, code and repository

- **J1 Availability statement** (MTH-03). The access conditions and costs, the repository and the link or DOI. [DCAS rules]
- **J2 Trusted repository** (BEH-13). A trusted archive such as openICPSR, Zenodo or Dataverse; the AEA does not accept GitHub alone. [AEA Data Editor on GitHub as an archive; DCAS rules]
- **J3 Data citations** (CIT-11). Every dataset the authors did not create is cited in the text and in the reference list, and in the package's README. [DCAS rules]
- **J4 Replication package** (BEH-13). With a package supplied: a README following the template (data availability and provenance, the dataset list, computational requirements, a description of the code, instructions to replicators, and a list of tables and programs that also maps the numbers given in the text), checked as the AEA Data Editor's guidance for AI assistants describes. [Template README; AEA guidance for AI assistants]

## K. Journal requirements

- **K1 Front matter and statements** (BEH-16). JEL codes, keywords, highlights and disclosure statements, as the venue profile requires.

## L. Cited findings

- **L1 Original sources** (BEH-15). Well-known findings are cited to the work that first reported them.
- **L2 Replication status** (CIT-14). Cited findings that failed to replicate, or replicated with smaller effects, are reported with the replication's own label and a quote of its conclusion, never called false. [FORRT Replication Database]

## O. Natural experiments and observational studies (MTH-06)

- **O1** Data provenance, access conditions and the terms of use.
- **O2** Sample construction, with the number of observations after each restriction.
- **O3** Variable definitions, with units and timing.
- **O4** The identifying assumptions, stated and argued.
- **O5** Inference that matches the design, such as clustering at the level of the policy variation.

## Leads for BEH-15, all unverified

These are commonly mentioned attribution errors, gathered by the survey from memory and not yet confirmed against the original papers. Use them only as leads: confirm the original source with a lookup before reporting anything, and never report one from this list alone. The misattribution evaluation set in `evals/README.md` will replace this list with confirmed entries.

- The loss-aversion coefficient of about 2.25 comes from Tversky and Kahneman (1992), cumulative prospect theory, not from Kahneman and Tversky (1979), which proposed a value function steeper for losses without estimating it.
- The quasi-hyperbolic model is usually traced to Phelps and Pollak (1968) and was popularized by Laibson (1997); "present-biased preferences" is usually credited to O'Donoghue and Rabin (1999).
- The term "endowment effect" is from Thaler (1980); the mug experiments are Kahneman, Knetsch and Thaler (1990).
- A dictator-style allocation appears in Kahneman, Knetsch and Thaler (1986), before Forsythe et al. (1994) named the dictator game; the ultimatum game is Güth, Schmittberger and Schwarze (1982), and the trust game Berg, Dickhaut and McCabe (1995).
- The hot-hand fallacy of Gilovich, Vallone and Tversky (1985) was challenged by Miller and Sanjurjo (2018), who found a selection bias that reverses the original inference.
- The jam study on choice overload (Iyengar and Lepper 2000) has a meta-analytic mean effect near zero (Scheibehenne, Greifeneder and Todd 2010).
- The often-quoted share of drivers who rate themselves above average (Svenson 1981) comes from a US student sample; the Swedish sample was lower.

## Sources

Gathered by the survey on 2026-10-17 (DESIGN section 17). Recheck each source before relying on a rule that depends on it, because journals change their policies.

- Experimental Economics, no deception and incentivized participants: https://www.cambridge.org/core/journals/experimental-economics/information/about-this-journal
- What counts as deception (Charness, Samek and van de Ven): https://www.cambridge.org/core/journals/experimental-economics/article/what-is-considered-deception-in-experimental-economics/B92D3DCAA5CDAB1357D49B7443244E50
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
- FORRT Replication Database: https://github.com/forrtproject/FReD
