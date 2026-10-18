"""`pc.py install`: everything a new user needs, in one command that is safe to run again.

1. The Python environment in ~/.paper-check/venv, as `pc.py setup` builds it.
2. The skill linked into ~/.claude/skills/paper-check, so Claude Code finds it from any folder. Where links
   are not allowed, as on Windows without developer mode, the skill is copied instead.
3. ~/.paper-check/config.yaml, readable only by the user, with the contact email. A value already in the
   file is never replaced.
4. With --request-openalex-key, a free OpenAlex key requested for that email. OpenAlex emails the user an
   activation link, and the key works once it is clicked.
5. A check of the synthetic test paper, offline, to show that the scripts run, then `pc.py doctor`.

The email goes only to OpenAlex, and only when the key is requested. Keys are written to the config file
and never printed.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

from . import __version__

SKILL_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = SKILL_DIR.parents[2] if SKILL_DIR.parent.name == "skills" and SKILL_DIR.parents[1].name == ".claude" else None
OPENALEX_KEYS = "https://api.openalex.org/api-keys"
_EMAIL = re.compile(r"^[^@\s\"'\\]+@[^@\s\"'\\]+\.[A-Za-z]{2,}$")
_PLACEHOLDER = re.compile(r"@(?:example\.(?:com|org|net)|test|invalid|localhost)$|^(?:you|user|name|email)@", re.I)

CONFIG_TEMPLATE = """\
# paper-check credentials. Readable only by you; never commit or share this file.
# See docs/api-access.md in the paper_check repository for how to get each key.
contact_email: {email}
openalex_api_key: null
semantic_scholar_api_key: null
repec_access_code: null
core_api_key: null
"""


def check_email(email: str) -> Optional[str]:
    """Why an address cannot be the contact email, or None when it can."""
    if not _EMAIL.match(email or ""):
        return f"{email!r} is not an email address"
    if _PLACEHOLDER.search(email):
        return f"{email} looks like a placeholder; OpenAlex refuses those"
    return None


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_config_values(path: Path, values: dict) -> dict:
    """Write each value whose key is missing or empty in the config file, keeping its comments and every value
    already set. Returns, for each key, "set" or "already set"."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path.parent, 0o700)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(CONFIG_TEMPLATE.format(email="null"))
    text = path.read_text(encoding="utf-8")
    outcome = {}
    for key, value in values.items():
        if not value:
            continue
        line = re.compile(rf"^{re.escape(key)}\s*:(.*)$", re.M)
        m = line.search(text)
        current = (m.group(1).split("#", 1)[0].strip().strip("'\"") if m else "")
        if current and current.lower() not in ("null", "~", "none"):
            outcome[key] = "already set"
            continue
        new = f"{key}: {_quoted(value)}"
        text = line.sub(lambda _m: new, text, count=1) if m else text.rstrip("\n") + "\n" + new + "\n"
        outcome[key] = "set"
    path.write_text(text, encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return outcome


def config_value(path: Path, key: str) -> Optional[str]:
    if not path.exists():
        return None
    m = re.search(rf"^{re.escape(key)}\s*:(.*)$", path.read_text(encoding="utf-8"), re.M)
    value = m.group(1).split("#", 1)[0].strip().strip("'\"") if m else ""
    return value if value and value.lower() not in ("null", "~", "none") else None


def link_skill(skills_root: Path) -> str:
    """Make the skill available in every Claude Code project: a link to this copy, or a copy where links
    are not allowed. Something already at that place is left alone."""
    target = skills_root / "paper-check"
    if target.is_symlink() and target.resolve() == SKILL_DIR:
        return f"already linked: {target}"
    if target.exists() or target.is_symlink():
        return (f"left as it is: {target} already exists. To use this copy instead, remove it and run "
                "install again.")
    skills_root.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(SKILL_DIR, target_is_directory=True)
        return f"linked {target} to {SKILL_DIR}; `git pull` in the repository updates it"
    except OSError:
        shutil.copytree(SKILL_DIR, target, ignore=shutil.ignore_patterns("__pycache__"))
        return (f"copied to {target} (this system does not allow the link). After updating the repository, "
                "remove that folder and run install again.")


def request_openalex_key(email: str, timeout: int = 30) -> tuple:
    """Ask OpenAlex for a free key for this email. Returns (key or None, message for the user)."""
    body = json.dumps({"email": email, "agent": "Claude Code (paper-check skill)"}).encode()
    req = urllib.request.Request(OPENALEX_KEYS, data=body, method="POST", headers={
        "Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4()),
        "User-Agent": f"paper-check/{__version__} (+https://github.com/jiaxinlu1024/paper_check)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return None, ("OpenAlex has given out too many keys from this network or email domain today. Sign up "
                          "at https://openalex.org/signup instead, then copy the key from "
                          "https://openalex.org/settings/api-key into ~/.paper-check/config.yaml as openalex_api_key.")
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("message") or ""
        except Exception:  # noqa: BLE001 - any unreadable error body
            detail = ""
        return None, f"OpenAlex did not issue a key (HTTP {exc.code}){': ' + detail if detail else ''}."
    except Exception as exc:  # noqa: BLE001 - network errors of every kind
        return None, f"Could not reach OpenAlex to request a key: {str(exc)[:120]}"
    key = data.get("api_key") if isinstance(data, dict) else None
    if not key:
        return None, "OpenAlex answered without a key; sign up at https://openalex.org/signup instead."
    return key, (f"OpenAlex emailed {email} a message titled \"Activate your OpenAlex API key\". The key works "
                 "once its button is clicked (the link lasts 7 days); until then lookups run without it.")


def sample_check() -> str:
    """Run the scripts on the synthetic test paper, offline, in a temporary folder."""
    sample = REPO_DIR / "tests" / "fixtures" / "latex_basic" if REPO_DIR else None
    if sample is None or not sample.is_dir():
        return "skipped: the synthetic test paper is not in this copy"
    from .cli import main
    with tempfile.TemporaryDirectory(prefix="paper-check-sample-") as tmp:
        paper = Path(tmp) / "paper"
        shutil.copytree(sample, paper, ignore=shutil.ignore_patterns("expected.yaml", "*.md"))
        work = paper / "paper-check-work"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            codes = [main(["ingest", str(paper), "--offline", "--mode", "quick"]), main(["checks", str(work)]),
                     main(["verify", str(work)]), main(["report", str(work)])]
        report = paper / "paper-check-report.md"
        if any(codes) or not report.exists():
            return "FAILED: " + " | ".join(out.getvalue().strip().splitlines()[-3:])
        data = json.loads((paper / "paper-check-findings.json").read_text(encoding="utf-8"))
        return (f"ok: the scripts wrote a report with {len(data.get('findings', []))} findings on the synthetic "
                "test paper (offline, scripts only)")


def run(email: Optional[str] = None, request_key: bool = False, link: bool = True, offline: bool = False,
        home: Optional[Path] = None, skills_root: Optional[Path] = None) -> int:
    """Steps 2 to 5, run inside the environment that step 1 built."""
    home = home or Path(os.path.expanduser("~")) / ".paper-check"
    skills_root = skills_root or Path(os.path.expanduser("~")) / ".claude" / "skills"
    config = home / "config.yaml"
    ok, next_steps = True, []

    print("Skill: " + (link_skill(skills_root) if link else "not linked (--no-link)"))

    if email:
        problem = check_email(email)
        if problem:
            print(f"Contact email: not saved, {problem}.")
            email, ok = None, False
    outcome = set_config_values(config, {"contact_email": email} if email else {})
    current = config_value(config, "contact_email")
    if outcome.get("contact_email") == "set":
        print(f"Contact email: saved in {config} (readable only by you)")
    elif current:
        print(f"Contact email: already set in {config}; edit that file to change it")
    else:
        print(f"Contact email: not set. Lookups still run, more slowly. Run install again with --email.")

    if request_key:
        if config_value(config, "openalex_api_key"):
            print("OpenAlex key: already set")
        elif not current:
            print("OpenAlex key: not requested, because there is no contact email to send the activation link to")
        elif offline:
            print("OpenAlex key: not requested (--offline)")
        else:
            key, message = request_openalex_key(current)
            if key:
                set_config_values(config, {"openalex_api_key": key})
                print("OpenAlex key: saved in the config file (not shown)")
                next_steps.append("Open the email from OpenAlex titled \"Activate your OpenAlex API key\" and "
                                  "click its button, within 7 days.")
            print("  " + message)
    elif not config_value(config, "openalex_api_key"):
        next_steps.append("Optional: run install again with --request-openalex-key for a free OpenAlex key, "
                          "which makes literature searches faster.")
    if not config_value(config, "semantic_scholar_api_key"):
        next_steps.append("Optional: apply for a free Semantic Scholar key (docs/api-access.md has the form and "
                          "what to enter). When it arrives, put it in ~/.paper-check/config.yaml as "
                          "semantic_scholar_api_key.")

    result = sample_check()
    print("Sample check: " + result)
    ok = ok and not result.startswith("FAILED")

    print("")
    from .env import doctor
    ok = doctor(network=not offline) == 0 and ok

    next_steps.append("Start a new Claude Code session (so it loads the skill) and ask, for example: "
                      "\"Check my paper at ~/Papers/draft.docx before I submit it to JEBO.\" A deep check takes "
                      "about an hour.")
    print("\nNext steps:")
    for i, step in enumerate(next_steps, 1):
        print(f"{i}. {step}")
    print("\nInstall: " + ("done" if ok else "finished with problems; see above"))
    return 0 if ok else 1


def install(args) -> int:
    """Step 1 here, with the Python that runs this command; steps 2 to 5 in the environment it built."""
    from .env import VENV, setup
    passthrough = ((["--email", args.email] if args.email else []) + (["--request-openalex-key"] if
                   args.request_openalex_key else []) + (["--no-link"] if args.no_link else [])
                   + (["--offline"] if args.offline else []))
    if not args.skip_env:
        try:
            if setup() != 0:
                return 1
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"Setting up the Python environment failed: {exc}")
            print("On Debian or Ubuntu, install python3-venv first (sudo apt install python3-venv); on other "
                  "systems, install Python 3.9 or newer from python.org.")
            return 1
        python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        pc = SKILL_DIR / "scripts" / "pc.py"
        return subprocess.call([str(python), str(pc), "install", "--skip-env", *passthrough])
    return run(email=args.email, request_key=args.request_openalex_key, link=not args.no_link,
               offline=args.offline)
