"""`pc.py doctor` and `pc.py setup`: check and prepare the environment."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .config import HOME, USER_CONFIG, Credentials

SKILL_DIR = Path(__file__).resolve().parents[2]
REQUIREMENTS = SKILL_DIR / "requirements.txt"
VENV = HOME / "venv"
MIN_PYTHON = (3, 9)

# import name for each requirement
MODULES = {
    "pdfplumber": "pdfplumber", "pypdf": "pypdf", "python-docx": "docx", "lxml": "lxml",
    "flachtex": "flachtex", "pylatexenc": "pylatexenc", "bibtexparser": "bibtexparser",
    "rapidfuzz": "rapidfuzz", "scipy": "scipy", "ImageHash": "imagehash", "PyYAML": "yaml",
    "jsonschema": "jsonschema",
}
OPTIONAL_TOOLS = {
    "pdffonts": "PDF font checks (FMT-15)",
    "soffice": "rendering Word files for visual checks",
    "pdflatex": "LaTeX build checks (FMT-13)",
    "curl": "fallback fetcher for sites that challenge Python",
}
PROBES = {
    "Crossref": "https://api.crossref.org/works?rows=0",
    "OpenAlex": "https://api.openalex.org/works?per_page=1",
    "Semantic Scholar": "https://api.semanticscholar.org/graph/v1/paper/search?query=nudge&limit=1&fields=title",
    # No email in the probe: Unpaywall's "email required" answer shows it is reachable.
    "Unpaywall": "https://api.unpaywall.org/v2/10.2307/1914185",
    "arXiv": "https://export.arxiv.org/api/query?search_query=all:nudge&max_results=1",
    "NBER": "https://www.nber.org/",
}


def missing_packages() -> list:
    missing = []
    for package, module in MODULES.items():
        try:
            importlib.import_module(module)
        except Exception:
            missing.append(package)
    return missing


def _probe(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "paper-check doctor"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return f"ok (HTTP {resp.status})"
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return "reachable but rate-limited (HTTP 429): lookups will slow down, retry later or add the API key"
        if exc.code in (401, 403):
            return f"reachable, but access was refused (HTTP {exc.code}): check the key or the network policy"
        if exc.code == 422:
            return "reachable (it asks for a contact email, which the lookups add when one is set)"
        return f"reachable (HTTP {exc.code})"
    except Exception as exc:
        return f"unreachable: {str(exc)[:60]}"


def doctor(network: bool = True) -> int:
    ok = True
    print(f"Python {sys.version.split()[0]} at {sys.executable}")
    if sys.version_info < MIN_PYTHON:
        print(f"  ERROR: Python {'.'.join(map(str, MIN_PYTHON))} or newer is required.")
        ok = False
    in_venv = Path(sys.prefix).resolve() == VENV.resolve()
    print(f"Virtual environment: {'in use' if in_venv else ('present, not in use' if VENV.exists() else 'not created')} ({VENV})")
    missing = missing_packages()
    if missing:
        ok = False
        print("Missing packages: " + ", ".join(missing))
        print("  Fix: python3 pc.py setup   (asks nothing; run it only after the user agrees)")
    else:
        print("Packages: all core packages import.")
    creds = Credentials.load()
    print(f"Credentials file: {'found' if USER_CONFIG.exists() else 'missing'} ({USER_CONFIG})")
    for name, present in creds.summary().items():
        print(f"  {name}: {'set' if present else 'not set'}")
    for tool, purpose in OPTIONAL_TOOLS.items():
        print(f"Optional tool {tool}: {'found' if shutil.which(tool) else 'not found'}, for {purpose}")
    if network:
        print("Network:")
        for name, url in PROBES.items():
            print(f"  {name}: {_probe(url)}")
    print("Result: " + ("ready" if ok else "not ready"))
    return 0 if ok else 1


def setup() -> int:
    """Create ~/.paper-check/venv and install requirements into it."""
    if sys.version_info < MIN_PYTHON:
        print(f"Python {'.'.join(map(str, MIN_PYTHON))} or newer is required.")
        return 1
    HOME.mkdir(parents=True, exist_ok=True)
    if not VENV.exists():
        print(f"Creating virtual environment at {VENV}")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    print("Installing requirements (this can take a few minutes)")
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    print("Done. pc.py now runs with this environment automatically.")
    return 0
