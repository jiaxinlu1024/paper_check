# paper_check

A Claude Code skill that checks behavioral economics paper drafts before submission. It reads LaTeX, PDF or Word, and writes a report in which every finding quotes the draft, gives its location, shows the proof and the steps that led to it, and suggests a fix, so that a writer or an agent can fix the paper. It never edits the paper.

It covers 125 checks in twelve dimensions: format and journal rules, references, whether each cited work supports its sentence, numbers and statistics, outside facts, logic, coherence, language, methods, ethics, figures and tables, the reviewer's view, and behavioral and experimental economics standards.

Status: working version 0.1. The scripts, the agent prompts and the orchestration are built and tested on synthetic LaTeX, Word and PDF test papers. Tests on real drafts come next.

## Use it

Open this repository in Claude Code and ask, for example, "check my paper in ~/Papers/defaults/ before we submit to the AER". The skill is `.claude/skills/paper-check/`. [docs/USING.md](docs/USING.md) explains setup, settings and how to read the report. Each person needs a contact email and, ideally, two free API keys: see [docs/api-access.md](docs/api-access.md).

## What is here

| Path | Content |
|---|---|
| `.claude/skills/paper-check/SKILL.md` | The orchestration Claude follows when the skill runs |
| `.claude/skills/paper-check/scripts/` | `pc.py` and the `paper_check` package: readers, checks, lookups, citation support, verification and the report |
| `.claude/skills/paper-check/references/` | The checklist, the reading-agent prompts, the digest, judge, refuter and web-check prompts, the policies, the reporting checklist for experiments, the list of common misattributions, and 21 journal profiles |
| `.claude/skills/paper-check/evals/` | Eval prompts and scoring scripts for the skill-creator loop |
| `tests/` | The test suite and three synthetic test papers with answer keys |
| `docs/DESIGN.md` | The design: pipeline, full checklist, report format, modes, guardrails |
| `docs/USING.md` | The user guide |
| `dev/ARCHITECTURE.md` | The developer guide: how the code realizes the design |
| `docs/case-studies/` | Real problems the skill must catch, starting with citations that do not support their claims |
| `docs/network-setup.md`, `docs/api-access.md` | Network access for cloud sessions, and the contact email and keys |
| `evals/README.md` | The evaluation sets and metrics |
| `reports/`, `research_notes/` | The survey of existing tools and what was reused from them |
| `tools/` | Network check and venue-profile validators |

## Develop it

```bash
python3 -m venv ~/.paper-check/venv && ~/.paper-check/venv/bin/pip install -r .claude/skills/paper-check/requirements.txt pytest
~/.paper-check/venv/bin/python -m pytest            # from the repository root
```

Read [dev/ARCHITECTURE.md](dev/ARCHITECTURE.md) before changing code. Licenses of adapted prompts and rules are in `.claude/skills/paper-check/THIRD_PARTY_NOTICES.md`.

## Check your network

```bash
python3 tools/check_network.py
```
