# paper_check

This repository is the paper-check skill (`.claude/skills/paper-check/`) with its tests, design and evaluations.

- **Setting the skill up for a user:** follow "Steps for Claude Code" in README.md. The one command is `python3 .claude/skills/paper-check/scripts/pc.py install --email "ADDRESS" --request-openalex-key`, with the address the user gives you.
- **Checking a paper:** the skill's SKILL.md says how; the user only names the paper.
- **Changing the code:** read dev/ARCHITECTURE.md first. Run the tests with `~/.paper-check/venv/bin/python -m pytest tests -q` from the repository root.
- **Privacy:** never commit `~/.paper-check/config.yaml`, keys, email addresses or a user's drafts. Drafts used for trials stay in `evals/private/`, which git ignores.
