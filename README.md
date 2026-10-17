# paper_check

A Claude Code skill, in development, that checks behavioral economics paper drafts before submission. It reads LaTeX, PDF or Word. It writes a report in which every finding quotes the draft, gives its location, shows the proof, and records how it was found, so that a writer or an agent can fix the paper.

Status: design stage. No skill code yet.

## What is here

| Path | Content |
|---|---|
| `docs/DESIGN.md` | The design: pipeline, full checklist, report format, modes, guardrails and open questions |
| `docs/case-studies/` | Real problems the skill must catch, starting with citations that do not support their claims |
| `docs/network-setup.md` | How to give cloud sessions the internet access the lookups need |
| `docs/api-access.md` | How each person gets the contact email and API keys the lookups use |
| `.claude/skills/paper-check/references/venues/` | One dated, source-quoted profile per target journal |
| `evals/README.md` | The test sets and metrics that come before any tuning |
| `reports/Existing paper check tools.md` | Survey of existing tools and projects, and what to reuse from them |
| `research_notes/` | Raw notes behind the survey |
| `config/allowed-domains.txt` | Domain list to paste into a cloud environment's custom network settings |
| `tools/check_network.py` | Tests whether every service the skill uses is reachable |
| `tools/validate_venues.py` | Checks venue profiles, and re-fetches their sources to verify every quote |
| `tools/venue_status.py` | Writes the status page of confirmed rules and blocked sources for the profiles |

## Check your network

```bash
python3 tools/check_network.py
```
