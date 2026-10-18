# paper_check

A Claude Code skill that checks behavioral economics paper drafts before submission. It reads LaTeX, PDF or Word, and writes a report in which every finding quotes the draft, gives its location, shows the proof and the steps that led to it, and suggests a fix, so that a writer or an agent can fix the paper. It never edits the paper.

It covers 125 checks in twelve dimensions: format and journal rules, references, whether each cited work supports its sentence, numbers and statistics, outside facts, logic, coherence, language, methods, ethics, figures and tables, the reviewer's view, and behavioral and experimental economics standards.

Status: first usable version (0.1). It has been tested on four synthetic test papers with answer keys and on a real draft. In round 2 it found 117 of the 121 known problems and flagged none of 50 correct passages; see [evals/results/](evals/results/). A deep check takes about an hour.

## Set up

Ask Claude Code, in any folder:

> Set up the paper-check skill from https://github.com/jiaxinlu1024/paper_check by following the steps for Claude Code in its README.

You give your work or university email once, click the activation email that OpenAlex sends, and approve the commands Claude asks to run. Claude does the rest.

### Steps for Claude Code

The user's request to set up the skill covers every step below, including installing the Python packages, so don't ask again. Ask the user only for their email (step 2). Never print, copy or commit `~/.paper-check/config.yaml` or any key.

1. **Get the repository.** Clone it to `~/paper_check`, unless the user names another folder: `git clone https://github.com/jiaxinlu1024/paper_check ~/paper_check`. If that folder already holds this repository, run `git -C ~/paper_check pull` instead; if it holds something else, clone to `~/paper-check-skill` and use that path below.
2. **Ask for the email.** Ask for the user's work or university email address, and say why: the lookup services ask for a contact address, and OpenAlex sends the activation link for a free API key to it. Use only an address the user gives you in reply. A free address such as Gmail works for the lookups, but Semantic Scholar does not issue keys to free addresses. If the user would rather not give one, go on without it: in step 3, leave out both options. Nothing then sends an address anywhere, and the lookups still run, more slowly.
3. **Install.** Run `python3 ~/paper_check/.claude/skills/paper-check/scripts/pc.py install --email "ADDRESS" --request-openalex-key`. On Windows, use `python` and `%USERPROFILE%\paper_check\.claude\skills\paper-check\scripts\pc.py`. In about a minute it:
   - builds the Python environment in `~/.paper-check/venv`;
   - links the skill into `~/.claude/skills/paper-check`, so it works from any folder;
   - writes `~/.paper-check/config.yaml`, readable only by the user;
   - requests the OpenAlex key;
   - checks a sample paper and runs `pc.py doctor`.

   It also checks that the lookup services can be reached; without an email, none of these checks sends one. It is safe to run again and never replaces a value already set. If Python 3.9 or newer is missing, ask the user to install it from https://www.python.org/downloads/ and then continue.
4. **Report back.** Pass on the "Next steps" that `install` printed, as printed: they depend on what was set up, such as clicking OpenAlex's activation email when a key was requested. They always end with starting a new Claude Code session, so it loads the skill. If a step failed, say which one and what `install` suggested.
5. **Show how to use it.** In a new session, the user asks, for example, "Check my paper at ~/Papers/draft.docx before I submit it to JEBO." A deep check takes about an hour; "quick check" takes about half an hour. [docs/USING.md](docs/USING.md) explains the settings and the report.

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
