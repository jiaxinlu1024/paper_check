"""`pc.py merge-runs WORK --dimension D`: compare two independent runs of one reading agent.

High-value reading checks run twice (DESIGN section 9, guardrail 5). The first run
writes findings/agent_<D>.json and the second writes runs/agent_<D>_run2.json
without seeing the first. This script matches the two by check and quote overlap:

- found in both runs: kept once, with verification.runs "2 of 2 runs";
- found in one run only: kept, with verification.runs "1 of 2 runs" and status
  likely (a needs_human status stays as it is).

The merged result replaces findings/agent_<D>.json, and the second-run file is
renamed with a .merged suffix so it is not read twice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .model import FindingSet, PaperMap
from .verify import load_findings_file, locate


def _span(pm: PaperMap, f) -> Optional[tuple]:
    if not f.quote:
        return None
    hit = locate(pm, f.quote, f.locations[0].block if f.locations else None)
    return (hit[0].id, hit[1], hit[2]) if hit else None


def _overlap(a: Optional[tuple], b: Optional[tuple]) -> float:
    if not a or not b or a[0] != b[0]:
        return 0.0
    inter = min(a[2], b[2]) - max(a[1], b[1])
    if inter <= 0:
        return 0.0
    return inter / max(1, min(a[2] - a[1], b[2] - b[1]))


def _same(f1, s1, f2, s2) -> float:
    """A match score; 0 means different findings."""
    if f1.dimension != f2.dimension:
        return 0.0
    ov = _overlap(s1, s2)
    if f1.check_id == f2.check_id:
        if ov > 0:
            return 2 + ov
        if not f1.quote and not f2.quote:
            b1 = f1.locations[0].block if f1.locations else None
            b2 = f2.locations[0].block if f2.locations else None
            return 1.5 if b1 == b2 else 0.0
        return 0.0
    # The two runs may file the same problem under neighbouring checks.
    return 1 + ov if ov >= 0.5 else 0.0


def merge_runs(work: Path, dimension: str) -> int:
    dim = dimension.strip().lower().removeprefix("agent_")
    first_path = work / "findings" / f"agent_{dim}.json"
    second_path = work / "runs" / f"agent_{dim}_run2.json"
    if not first_path.exists() or not second_path.exists():
        missing = [str(p) for p in (first_path, second_path) if not p.exists()]
        raise SystemExit(f"Cannot merge runs: missing {', '.join(missing)}")
    pm = PaperMap.load(work / "paper_map.json")
    first, err1, _ = load_findings_file(first_path)
    second, err2, _ = load_findings_file(second_path)
    if first is None or second is None:
        raise SystemExit("Cannot merge runs: " + "; ".join(err1 + err2))

    spans1 = [_span(pm, f) for f in first.findings]
    spans2 = [_span(pm, f) for f in second.findings]
    pairs = []
    for i, f1 in enumerate(first.findings):
        for j, f2 in enumerate(second.findings):
            score = _same(f1, spans1[i], f2, spans2[j])
            if score > 0:
                pairs.append((score, i, j))
    pairs.sort(reverse=True)
    used1, used2, matched = set(), set(), []
    for score, i, j in pairs:
        if i in used1 or j in used2:
            continue
        used1.add(i)
        used2.add(j)
        matched.append((i, j))

    for i, j in matched:
        f1, f2 = first.findings[i], second.findings[j]
        f1.verification["runs"] = "2 of 2 runs"
        note = "Second run found it independently"
        if f2.check_id != f1.check_id:
            note += f" under {f2.check_id}"
        if f2.severity != f1.severity:
            note += f", rated {f2.severity}"
        f1.trajectory.append(note + ".")
    for i, f1 in enumerate(first.findings):
        if i not in used1:
            f1.verification["runs"] = "1 of 2 runs"
            if f1.status == "confirmed":
                f1.status = "likely"
    added = 0
    for j, f2 in enumerate(second.findings):
        if j in used2:
            continue
        f2.verification["runs"] = "1 of 2 runs"
        if f2.status == "confirmed":
            f2.status = "likely"
        f2.producer["run"] = 2
        first.findings.append(f2)
        added += 1

    cov = {c.check_id: c for c in first.coverage}
    for c in second.coverage:
        if c.check_id not in cov or (cov[c.check_id].status != "run" and c.status == "run"):
            cov[c.check_id] = c
    first.coverage = sorted(cov.values(), key=lambda c: c.check_id)
    first.settings["runs"] = 2
    first.save(first_path)
    second_path.rename(second_path.with_name(second_path.name + ".merged"))
    only1 = len(spans1) - len(matched)
    print(f"Merged runs for {dim}: {len(matched)} found in both runs, {only1} only in the first, "
          f"{added} only in the second. Findings in one run only are marked likely.")
    return 0
