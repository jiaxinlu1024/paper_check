# Skill Benchmark: paper-check

**Model**: <model-name>
**Date**: 2026-10-18T19:12:37Z
**Evals**: 1, 2, 3, 4 (1 run each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 96% ± 5% | 69% ± 9% | +0.27 |
| Time | 3531.8s ± 1735.9s | 1169.7s ± 536.4s | +2362.1s |
| Tokens | 465379 ± 253301 | 225720 ± 88405 | +239659 |
## Notes

- One run per configuration and paper, so there is no run-to-run variance; the +/- figures are spread across papers.
- The baselines for papers 1-3 are round 1's runs, reused (same paper, same prompt); only paper 4's baseline is new.
- On substance the hard paper (eval 4) is a tie: both arms found 25 of 26 known problems and 9 of 9 citation errors, and neither flagged any of 29 correct passages. The baseline took 31% of the time.
- Across the four papers the skill flagged no correct passage as wrong; the baseline flagged one (eval 2, a correctly cited sentence called 'slightly overstated').
- The baseline missed items the skill caught: the hidden instruction to AI reviewers (eval 3), the self-identifying 'In our previous work' (eval 2), an implausibly small standard error (evals 2 and 3), an unbraced acronym (eval 1), the oTree citation (eval 3).
- The skill's failed assertions are honesty and consistency slips in its own report (eval 4: an 'independent refuter' line in a sequential run, a merged finding marked confirmed while its steps say likely, a sources header that disagrees with the citation rows) and one text bug (eval 2).
- Token counts are the final context sizes the harness reported; eval 2's skill run (148k) almost certainly had its context compacted, so its tokens are not comparable with round 1's 764k for the same job.
- The skill ran in its sequential fallback inside a subagent (no parallel agents), which is slower than its normal mode.
