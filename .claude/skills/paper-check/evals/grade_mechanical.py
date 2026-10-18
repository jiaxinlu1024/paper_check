"""Mechanical grading for paper-check evals: checks a run's outputs without judgment calls.

Usage:
    python grade_mechanical.py RUN_OUTPUTS_DIR PAPER_PATH [--out FILE]

It finds the report in RUN_OUTPUTS_DIR (paper-check-report.md, or the largest .md
file for a run without the skill), ingests the paper into a scratch folder, and
reports:

- quotes_verbatim: the share of passages the report presents as the paper's text
  that appear in the paper. A passage counts when it is a blockquote or a quoted
  span of at least four words on a line that is not a suggested rewrite, a search,
  a lookup or a quote from a cited work. Quote marks are paired in order, so the
  text between two quotes is never taken for a quote. The paper's text includes
  its notes (comments, tracked changes, hidden text, PDF annotations), table cells
  and, for LaTeX, the source files, so a quote of the source counts. An ellipsis
  splits a quote into parts that must each be found.
- severity_ordered: the findings sit under severity headings, at least two
  severities, never a lower one before a higher one (the summary, index, coverage
  and appendices are not counted).
- has_index: a section titled as an index or paper-order list holds a table with a
  row per finding; with a findings file, the rows must follow the paper's order.
- has_coverage: a coverage section that names checks not run, skipped or not
  applicable, or a section that says what the review did not check.
- findings_json: a machine-readable findings file exists, with a quote or
  location on every finding.
- size: lines and kilobytes of the report, for the record.

The output is JSON with expectations in the skill-creator grading format
(text, passed, evidence), so it can be merged into grading.json.
"""

from __future__ import annotations

import argparse
import contextlib
import io
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

SEVERITY_WORDS = [("critical", 0), ("blocker", 0), ("major", 1), ("minor", 2), ("suggestion", 3), ("nit", 3)]
# A quote counts as the paper's text when it is a blockquote, sits on a "Related" or "Quote" line, or has a
# place in the paper just before it ("Abstract:", "section 2 says", "p. 3, line 4"). Words just before it
# that point elsewhere (a cited work, a journal rule, a search, a suggested rewrite) rule it out.
PLACE = re.compile(r"(abstract|section|§|paragraph|\bpara\b|page|p\.\s?\d|line\s?\d|table\s?\d|figure\s?\d|footnote|"
                   r"appendix|equation|caption|intro|results|conclusion|design|\.tex:\d|the (paper|draft|manuscript|text)"
                   r" (says|writes|states|reads)|you write|reads:|says:|sentence)", re.I)
ELSEWHERE = re.compile(r"(source|cited|rule|profile|guide|polic|requir|journal|closest|record|titled|title|official|"
                       r"suggest|replac|instead|rewrite|rephrase|reword|e\.g\.|for example|search|query|lookup|"
                       r"could|should read|verified list|database|crossref|openalex)", re.I)
SKIP_LINE = re.compile(r"^\W*(computed|lookup|searched|suggested fix|resolved when|verifier settings)", re.I)
END_SECTIONS = re.compile(r"^#+ .*(appendix|index|coverage|paper order|summary|top issues|overview|at a glance)",
                          re.I)
ID_RE = re.compile(r"\b(F-\d{3})\b")


def _report(outputs: Path):
    named = list(outputs.rglob("paper-check-report.md"))
    if named:
        return named[0]
    mds = sorted(outputs.rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True)
    return mds[0] if mds else None


def _paper(paper: Path):
    tmp = Path(tempfile.mkdtemp(prefix="pc-grade-"))
    with contextlib.redirect_stdout(io.StringIO()):
        ingest(paper, output=str(tmp))
    pm = PaperMap.load(tmp / "paper-check-work" / "paper_map.json")
    parts = [b.text for b in pm.blocks]
    parts += [n.text for n in pm.notes if getattr(n, "text", None)]
    parts += [" | ".join(row) for t in pm.tables for row in t.rows]
    parts += [" ".join(row) for t in pm.tables for row in t.rows]
    root = paper if paper.is_dir() else paper.parent
    if paper.is_dir() or paper.suffix == ".tex":
        for src in sorted(root.rglob("*")):
            if src.suffix in (".tex", ".bib") and src.is_file():
                parts.append(src.read_text(encoding="utf-8", errors="replace"))
    return pm, "\n".join(parts)


def _spans_at(line: str) -> list:
    """(start, text) of quoted spans on a line, pairing quote marks in order."""
    out = [(m.start(), m.group(1)) for m in re.finditer(r"“([^”]*)”", line)]
    straight = [i for i, ch in enumerate(line) if ch == '"']
    out += [(a, line[a + 1:b]) for a, b in zip(straight[0::2], straight[1::2])]
    return out


def _clean(q: str) -> str:
    # Markdown bold around words, not the significance stars after a number.
    q = re.sub(r"(?<![\w*])\*\*(?=\S)(.+?)(?<=\S)\*\*(?![\w*])", r"\1", q).replace("`", "")
    return q.strip().strip(".,;:")


def _quotes(md: str) -> list:
    quotes = []
    for line in md.splitlines():
        s = line.strip()
        if not s or SKIP_LINE.search(s.lstrip("-* ")):
            continue
        if s.startswith(">"):
            body = s.lstrip("> ").strip()
            spans = [t for _, t in _spans_at(body)] or re.findall(r"`([^`]+)`", body)
            quotes += spans if spans else [re.sub(r"\s*\([^()]*\)\s*$", "", body)]
            continue
        if re.match(r"^[-*]?\s*(related|quote)\b", s, re.I):
            quotes += [t for _, t in _spans_at(s)]
            continue
        for start, t in _spans_at(s):
            # The place must be close to the quote; a pointer elsewhere anywhere before it rules it out.
            if PLACE.search(s[max(0, start - 50):start]) and not ELSEWHERE.search(s[:start]):
                quotes.append(t)
    out = []
    for q in quotes:
        q = _clean(q)
        if len(q.split()) >= 4 and len(q) <= 600:
            out.append(q)
    return out


def _found(q: str, text: str) -> bool:
    parts = [p.strip(" .,;:") for p in re.split(r"\.\.\.|…|\[\.\.\.\]", q)]
    parts = [p for p in parts if len(p.split()) >= 3] or [q]
    return all(find_quote(p, text) for p in parts)


def _severity_order(md: str):
    ranks, headings = [], []
    for line in md.splitlines():
        if not line.startswith("#"):
            continue
        if END_SECTIONS.search(line):
            if ranks:
                break
            continue
        low = line.lower()
        hits = [(low.find(w), r) for w, r in SEVERITY_WORDS if re.search(rf"\b{w}", low)]
        if hits:
            ranks.append(min(hits)[1])
            headings.append(line.strip()[:70])
    ordered = len(set(ranks)) >= 2 and all(a <= b for a, b in zip(ranks, ranks[1:]))
    return ordered, ranks, headings


def _section(md: str, heading_re: str):
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#") and re.search(heading_re, line, re.I):
            level = len(line) - len(line.lstrip("#"))
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith("#") and len(nxt) - len(nxt.lstrip("#")) <= level:
                    break
                body.append(nxt)
            return line, body
    return None, []


def _index(md: str, findings: list, pm):
    heading, body = _section(md, r"^#+\s*(\d+\.?\s*)?(index\b|.*\bin paper order|.*index of findings)")
    rows = [r for r in body if r.startswith("|") and not re.match(r"^\|\s*-", r)][1:]
    if heading is None or len(rows) < 2:
        return False, f"no index table ({'heading ' + heading.strip() if heading else 'no heading'}, {len(rows)} rows)"
    if not findings:
        return True, f"{heading.strip()}: {len(rows)} rows; no findings file, so the order was not checked"
    order = pm.block_order()
    by_id = {f.get("id"): f for f in findings}
    positions = []
    for row in rows:
        ids = [i for i in ID_RE.findall(row) if i in by_id]
        if not ids:
            continue
        f = by_id[ids[0]]
        pos = None
        for loc in f.get("locations") or []:
            block = pm.block(loc.get("block")) if loc.get("block") else None
            if block is not None:
                span = find_quote(f.get("quote") or "", block.text) if f.get("quote") else None
                pos = (order[block.id], span[0] if span else 0)
                break
        positions.append((ids[0], pos))
    known = [(i, p) for i, p in positions if p is not None]
    back = [(a[0], b[0]) for a, b in zip(known, known[1:]) if b[1] < a[1]]
    ok = not back and len(positions) >= 0.9 * len(findings)
    return ok, (f"{heading.strip()}: {len(rows)} rows for {len(findings)} findings; "
                + (f"out of order: {back[:5]}" if back else "rows follow the paper's order"))


def _coverage(md: str):
    heading, body = _section(md, r"^#+ .*(coverage|not checked|did not check|could not check|scope|limitations of)")
    text = "\n".join(body)
    named = re.search(r"skipped|not run|not applicable|not checked|could not|did not|was not", text, re.I)
    return bool(heading and named), (f"{heading.strip()}: {len(body)} lines" if heading else "no coverage section")


def grade(outputs: Path, paper: Path) -> dict:
    report = _report(outputs)
    exp = []
    if report is None:
        exp.append({"text": "A report file was written", "passed": False, "evidence": f"No .md file in {outputs}"})
        return {"expectations": exp}
    md = report.read_text(encoding="utf-8", errors="replace")
    exp.append({"text": "A report file was written", "passed": True,
                "evidence": f"{report.relative_to(outputs)}: {len(md.splitlines())} lines, "
                            f"{len(md.encode('utf-8')) // 1024} KB"})

    pm, text = _paper(paper)
    quotes = _quotes(md)
    missing = [q for q in quotes if not _found(q, text)]
    share = (len(quotes) - len(missing)) / len(quotes) if quotes else 0.0
    exp.append({"text": "At least 95% of the passages the report presents as the paper's text appear in the paper",
                "passed": bool(quotes) and share >= 0.95,
                "evidence": f"{len(quotes) - len(missing)} of {len(quotes)} found ({share:.1%}). "
                            + (f"Not found, e.g.: {missing[:4]}" if missing else "")})

    ordered, ranks, headings = _severity_order(md)
    exp.append({"text": "Findings sit under severity headings, most severe first", "passed": ordered,
                "evidence": f"{len(ranks)} severity headings, ranks {ranks[:12]}{'...' if len(ranks) > 12 else ''}; "
                            f"first: {headings[:3]}"})

    fj = list(outputs.rglob("paper-check-findings.json"))
    data = json.loads(fj[0].read_text(encoding="utf-8")) if fj else {}
    findings = data.get("findings", [])
    ok, ev = _index(md, findings, pm)
    exp.append({"text": "The report has an index of findings in paper order", "passed": ok, "evidence": ev})

    ok, ev = _coverage(md)
    exp.append({"text": "The report says which checks were not run or skipped, and why", "passed": ok, "evidence": ev})

    if fj:
        ok = bool(findings) and all(f.get("quote") or f.get("locations") for f in findings)
        exp.append({"text": "A machine-readable findings file lists every finding with a quote or location",
                    "passed": ok, "evidence": f"{len(findings)} findings; by severity "
                                              f"{data.get('summary', {}).get('by_severity')}"})
    else:
        exp.append({"text": "A machine-readable findings file lists every finding with a quote or location",
                    "passed": False, "evidence": "no paper-check-findings.json"})
    return {"expectations": exp, "size": {"lines": len(md.splitlines()), "kb": len(md.encode("utf-8")) // 1024,
                                          "quotes_counted": len(quotes)}}


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
