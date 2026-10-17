"""Mechanical grading for paper-check evals: checks a run's outputs without judgment calls.

Usage:
    python grade_mechanical.py RUN_OUTPUTS_DIR PAPER_PATH [--out FILE]

It finds the report in RUN_OUTPUTS_DIR (paper-check-report.md, or the largest .md
file for a run without the skill), ingests the paper into a scratch folder, and
reports:

- quotes_verbatim: the share of quoted passages of 20+ characters in the report
  that appear verbatim in the paper (whitespace and case insensitive);
- has_coverage, has_index, severity_ordered: report structure;
- findings_json: whether a machine-readable findings file exists, and its counts.

The output is JSON with expectations in the skill-creator grading format
(text, passed, evidence), so it can be merged into grading.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from paper_check.ingest import ingest  # noqa: E402
from paper_check.model import PaperMap  # noqa: E402
from paper_check.textutil import find_quote  # noqa: E402

QUOTE_RE = re.compile(r"[\"“]([^\"“”\n]{20,400})[\"”]")


def _report(outputs: Path):
    named = list(outputs.rglob("paper-check-report.md"))
    if named:
        return named[0]
    mds = sorted(outputs.rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True)
    return mds[0] if mds else None


def _paper_text(paper: Path) -> str:
    tmp = Path(tempfile.mkdtemp(prefix="pc-grade-"))
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        ingest(paper, output=str(tmp))
    pm = PaperMap.load(tmp / "paper-check-work" / "paper_map.json")
    return "\n".join(b.text for b in pm.blocks)


def grade(outputs: Path, paper: Path) -> dict:
    report = _report(outputs)
    exp = []
    if report is None:
        exp.append({"text": "A report file was written", "passed": False, "evidence": f"No .md file in {outputs}"})
        return {"expectations": exp}
    md = report.read_text(encoding="utf-8", errors="replace")
    exp.append({"text": "A report file was written", "passed": True, "evidence": str(report.relative_to(outputs))})

    text = _paper_text(paper)
    # Only quotes that claim to come from the paper: skip lines with suggested rewrites
    # and lines quoting cited works or search terms.
    skip_line = re.compile(r"suggest|replace|rewrite|rephrase|instead|change\b.*\bto\b|\bfix|could say|"
                           r"e\.g\.|for example|source|cited work|searched|query|terms?:", re.I)
    quotes = [q.strip() for line in md.splitlines() if not skip_line.search(line) for q in QUOTE_RE.findall(line)]
    found = [q for q in quotes if find_quote(q, text)]
    missing = [q for q in quotes if not find_quote(q, text)]
    share = len(found) / len(quotes) if quotes else 0.0
    exp.append({"text": "At least 90% of quoted passages appear verbatim in the paper",
                "passed": bool(quotes) and share >= 0.9,
                "evidence": f"{len(found)} of {len(quotes)} quotes found ({share:.0%}). "
                            + (f"Not found, e.g.: {missing[:3]}" if missing else "")})

    has_cov = bool(re.search(r"^#+ .*coverage", md, re.I | re.M)) and bool(re.search(r"skipped|not run|not applicable", md, re.I))
    exp.append({"text": "The report has a coverage section that names checks not run or skipped",
                "passed": has_cov, "evidence": "coverage heading and skipped entries found" if has_cov else "no coverage section"})
    has_index = bool(re.search(r"^#+ .*(index|paper order)", md, re.I | re.M))
    exp.append({"text": "The report has an index of findings in paper order", "passed": has_index,
                "evidence": "index heading found" if has_index else "no index heading"})
    pos = [m.start() for m in (re.search(rf"^#+ .*{w}", md, re.I | re.M) for w in ("critical", "major", "minor")) if m]
    ordered = len(pos) >= 1 and pos == sorted(pos)
    exp.append({"text": "Findings are grouped by severity, most severe first", "passed": ordered,
                "evidence": f"{len(pos)} severity headings, at offsets {pos}"})

    fj = list(outputs.rglob("paper-check-findings.json"))
    if fj:
        data = json.loads(fj[0].read_text(encoding="utf-8"))
        n = len(data.get("findings", []))
        ok = n > 0 and all(f.get("quote") or f.get("locations") for f in data["findings"])
        exp.append({"text": "A machine-readable findings file lists every finding with a quote or location",
                    "passed": ok, "evidence": f"{n} findings; by severity {data.get('summary', {}).get('by_severity')}"})
    else:
        exp.append({"text": "A machine-readable findings file lists every finding with a quote or location",
                    "passed": False, "evidence": "no paper-check-findings.json"})
    return {"expectations": exp}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outputs")
    ap.add_argument("paper")
    ap.add_argument("--out")
    args = ap.parse_args()
    result = grade(Path(args.outputs), Path(args.paper))
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
