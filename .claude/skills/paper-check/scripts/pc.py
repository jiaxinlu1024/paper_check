#!/usr/bin/env python3
"""Entry point for the paper-check skill's scripts.

    python3 pc.py install           first-time setup in one step (see the README)
    python3 pc.py doctor            check Python, packages, keys and network
    python3 pc.py setup             create ~/.paper-check/venv and install requirements
    python3 pc.py ingest PAPER      build the paper map
    python3 pc.py --help            list every command

When ~/.paper-check/venv exists, this file re-runs itself with that environment's
Python, so callers can always use the system `python3`.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(os.path.expanduser("~"), ".paper-check", "venv")


def _venv_python():
    if os.name == "nt":
        return os.path.join(VENV, "Scripts", "python.exe")
    return os.path.join(VENV, "bin", "python")


def _in_venv():
    return os.path.realpath(sys.prefix) == os.path.realpath(VENV)


def _maybe_reexec():
    if os.environ.get("PAPER_CHECK_NO_VENV") == "1" or _in_venv():
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("setup", "install") and "--skip-env" not in sys.argv:
        return  # setup and install build the venv with the current interpreter
    python = _venv_python()
    if not os.path.exists(python):
        return
    args = [python, os.path.abspath(__file__), *sys.argv[1:]]
    if os.name == "nt":
        sys.exit(subprocess.call(args))
    os.execv(python, args)


if __name__ == "__main__":
    _maybe_reexec()
    sys.path.insert(0, HERE)
    from paper_check.cli import main

    sys.exit(main())
