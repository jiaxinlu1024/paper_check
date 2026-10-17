"""Findings validation and quote verification: the guardrails that stop invented evidence.

`pc.py validate WORK [--file F]` checks that findings files are well formed. Agents
write these files by hand, so the loader repairs small slips (upper-case
severities, a string where a list was expected) and reports real errors, such
as an unknown check ID, so the agent can fix them.

`pc.py verify WORK` reads every findings file and checks:
  - the finding's quote, which must appear in the paper map;
  - each related quote and each evidence item of type "quote";
  - each evidence item of type "source_quote", which must appear in the cited
    work's cached text at citations/sources/<ref>.txt.

A finding whose paper quotes cannot be found is marked dropped. A quote found in
a different block than the finding claims is accepted, and the location is
corrected. Results are written back into each findings file under
`verification`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .model import CONFIDENCES, SEVERITIES, STATUSES, Anchor, FindingSet, Location, PaperMap
from .textutil import find_quote, normalize

EVIDENCE_TYPES = ("quote", "source_quote", "computed_result", "checked_absence", "lookup_record",
                  "script_output", "image", "note")
FIX_ACTIONS = ("replace", "insert", "delete", "investigate")
COVERAGE_STATUSES = ("run", "not_applicable", "skipped")
_CHECK_IDS: Optional[set] = None


def _check_ids() -> set:
    global _CHECK_IDS
    if _CHECK_IDS is None:
        import yaml

        path = Path(__file__).resolve().parents[2] / "references" / "checks.yaml"
        _CHECK_IDS = {c["id"] for c in yaml.safe_load(path.read_text(encoding="utf-8"))["checks"]}
    return _CHECK_IDS


def _norm_word(value, allowed: tuple, default: Optional[str] = None):
    if value is None:
        return default
    v = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    v = {"needs_human_judgment": "needs_human", "needs_human_judgement": "needs_human",
         "not_run": "skipped", "n/a": "not_applicable", "na": "not_applicable", "passed": "run"}.get(v, v)
    return v if v in allowed else None


def _repair_finding(raw: dict, where: str, errors: list, notes: list) -> Optional[dict]:
    if not isinstance(raw, dict):
        errors.append(f"{where}: a finding must be a JSON object, got {type(raw).__name__}")
        return None
    f = dict(raw)
    cid = str(f.get("check_id") or "").strip().upper()
    if not cid:
        errors.append(f"{where}: missing check_id")
    elif cid not in _check_ids():
        errors.append(f"{where}: unknown check_id {cid!r}; use an id from references/checks.yaml")
    f["check_id"] = cid or "UNKNOWN"
    for key in ("title", "problem"):
        if not str(f.get(key) or "").strip():
            errors.append(f"{where}: missing {key}")
            f[key] = f.get(key) or ""
    sev = _norm_word(f.get("severity"), SEVERITIES)
    if sev is None:
        errors.append(f"{where}: severity {f.get('severity')!r} is not one of {', '.join(SEVERITIES)}")
        sev = "minor"
    f["severity"] = sev
    status = _norm_word(f.get("status"), STATUSES, "likely")
    if status is None:
        notes.append(f"{where}: status {f.get('status')!r} unknown, set to likely")
        status = "likely"
    f["status"] = status
    conf = _norm_word(f.get("confidence"), CONFIDENCES, "medium")
    if conf is None:
        notes.append(f"{where}: confidence {f.get('confidence')!r} unknown, set to medium")
        conf = "medium"
    f["confidence"] = conf
    if f.get("quote") is not None and not isinstance(f["quote"], str):
        errors.append(f"{where}: quote must be a string")
        f["quote"] = str(f["quote"])
    # Lists that agents sometimes write as a single item.
    for key in ("locations", "related_quotes", "evidence", "trajectory"):
        value = f.get(key)
        if value is None:
            f[key] = []
        elif not isinstance(value, list):
            notes.append(f"{where}: {key} should be a list; wrapped the single value")
            f[key] = [value]
    locs = []
    for loc in f["locations"]:
        if isinstance(loc, str):
            locs.append({"block": loc})
        elif isinstance(loc, dict):
            locs.append(loc)
        else:
            errors.append(f"{where}: each location must be an object with a block id")
    f["locations"] = locs
    evidence = []
    for i, ev in enumerate(f["evidence"]):
        if isinstance(ev, str):
            evidence.append({"type": "note", "text": ev})
            continue
        if not isinstance(ev, dict):
            errors.append(f"{where}: evidence item {i} must be an object")
            continue
        ev = dict(ev)
        t = _norm_word(ev.get("type"), EVIDENCE_TYPES)
        if t is None:
            notes.append(f"{where}: evidence item {i} type {ev.get('type')!r} unknown, kept as note")
            t = "note"
        ev["type"] = t
        if ev.get("page") is not None:
            ev["page"] = str(ev["page"])
        if t == "source_quote" and not ev.get("ref"):
            errors.append(f"{where}: source_quote evidence needs the reference id in `ref`")
        evidence.append(ev)
    f["evidence"] = evidence
    f["trajectory"] = [t if isinstance(t, str) else json.dumps(t, ensure_ascii=False) for t in f["trajectory"]]
    fix = f.get("fix")
    if isinstance(fix, str):
        f["fix"] = {"action": "investigate", "detail": fix}
    elif isinstance(fix, dict):
        fix = dict(fix)
        action = _norm_word(fix.get("action"), FIX_ACTIONS)
        if action is None:
            notes.append(f"{where}: fix action {fix.get('action')!r} unknown, set to investigate")
            action = "investigate"
        fix["action"] = action
        if action == "replace" and not (fix.get("original") and fix.get("replacement") is not None):
            notes.append(f"{where}: a replace fix should give the exact original and replacement text")
        f["fix"] = fix
    elif fix is not None:
        errors.append(f"{where}: fix must be an object")
        f["fix"] = None
    for key in ("producer", "verification", "extra"):
        if not isinstance(f.get(key) or {}, dict):
            notes.append(f"{where}: {key} must be an object; moved it into extra")
            f.setdefault("extra", {})
            f["extra"] = f["extra"] if isinstance(f["extra"], dict) else {}
            f["extra"][key] = f.pop(key)
    return f


def load_findings_file(path: Path):
    """Load and repair one findings file. Returns (FindingSet or None, errors, notes)."""
    errors: list = []
    notes: list = []
    name = Path(path).name
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{name}: not valid JSON: {exc}"], notes
    if isinstance(data, list):
        notes.append(f"{name}: the file is a bare list; read it as the findings of producer {Path(path).stem}")
        data = {"producer": Path(path).stem, "findings": data}
    if not isinstance(data, dict):
        return None, [f"{name}: the top level must be an object with producer, findings and coverage"], notes
    data = dict(data)
    data.setdefault("producer", Path(path).stem)
    findings = []
    for i, raw in enumerate(data.get("findings") or []):
        f = _repair_finding(raw, f"{name} finding {i + 1}", errors, notes)
        if f is not None:
            findings.append(f)
    data["findings"] = findings
    coverage = []
    for i, c in enumerate(data.get("coverage") or []):
        if not isinstance(c, dict) or not c.get("check_id"):
            errors.append(f"{name} coverage {i + 1}: each entry needs check_id and status")
            continue
        c = dict(c)
        c["check_id"] = str(c["check_id"]).strip().upper()
        if c["check_id"] not in _check_ids():
            errors.append(f"{name} coverage {i + 1}: unknown check_id {c['check_id']!r}")
        status = _norm_word(c.get("status"), COVERAGE_STATUSES)
        if status is None:
            errors.append(f"{name} coverage {i + 1}: status {c.get('status')!r} is not run, not_applicable or skipped")
            status = "skipped"
        if status != "run" and not c.get("reason"):
            notes.append(f"{name} coverage {i + 1}: {c['check_id']} is {status} without a reason")
        c["status"] = status
        coverage.append(c)
    data["coverage"] = coverage
    if not isinstance(data.get("settings") or {}, dict):
        data["settings"] = {"value": data["settings"]}
    try:
        return FindingSet.from_dict(data), errors, notes
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return None, errors + [f"{name}: does not match the findings format: {exc}"], notes


def validate_command(work: Path, file: Optional[str] = None) -> int:
    paths = [Path(file)] if file else sorted((work / "findings").glob("*.json"))
    if not paths:
        print("No findings files yet.")
        return 0
    bad = 0
    for path in paths:
        if not path.is_absolute() and not path.exists():
            path = work / "findings" / path.name
        fs, errors, notes = load_findings_file(path)
        status = "ok" if fs is not None and not errors else "needs fixing"
        count = len(fs.findings) if fs else 0
        print(f"{path.name}: {status}, {count} findings, {len(fs.coverage) if fs else 0} coverage entries")
        for e in errors:
            print(f"  error: {e}")
        for n in notes:
            print(f"  repaired: {n}")
        bad += bool(errors) or fs is None
    return 1 if bad else 0


def locate(pm: PaperMap, quote: str, prefer: Optional[str] = None):
    """Return (block, start, end) for a quote, preferring the given block id."""
    if not quote or not quote.strip():
        return None
    order = list(pm.blocks)
    if prefer:
        first = pm.block(prefer)
        if first is not None:
            order = [first] + [b for b in order if b.id != prefer]
    for block in order:
        span = find_quote(quote, block.text)
        if span:
            return block, span[0], span[1]
    # A quote may straddle two consecutive blocks, such as a paragraph broken by a page.
    for a, b in zip(pm.blocks, pm.blocks[1:]):
        joined = a.text + " " + b.text
        span = find_quote(quote, joined)
        if span and span[0] < len(a.text) < span[1]:
            return a, span[0], len(a.text)
    return None


def _source_text(work: Path, ref: str) -> Optional[str]:
    path = work / "citations" / "sources" / f"{ref}.txt"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def _fill_location(pm: PaperMap, loc: Location) -> None:
    block = pm.block(loc.block) if loc.block else None
    if block is None:
        return
    if loc.anchor is None:
        loc.anchor = Anchor.from_dict(block.anchor.to_dict())
    if not loc.section:
        loc.section = list(block.section)


def verify_finding(pm: PaperMap, work: Path, finding, source_cache: dict) -> dict:
    report = {"checked": 0, "failed": [], "unverifiable": [], "moved": False}
    prefer = finding.locations[0].block if finding.locations else None

    def check_paper(quote: str, block_hint: Optional[str], what: str):
        report["checked"] += 1
        hit = locate(pm, quote, block_hint or prefer)
        if not hit:
            report["failed"].append(f"{what}: not found in the paper: {quote[:80]!r}")
        return hit

    if finding.quote:
        hit = check_paper(finding.quote, prefer, "quote")
        if hit:
            block, start, end = hit
            report["quote_span"] = {"block": block.id, "start": start, "end": end}
            if prefer != block.id:
                report["moved"] = bool(prefer)
                loc = Location(block=block.id, anchor=Anchor.from_dict(block.anchor.to_dict()),
                               section=list(block.section))
                finding.locations = [loc] + [l for l in finding.locations if l.block != block.id]
    for rq in finding.related_quotes:
        text = rq.get("quote") if isinstance(rq, dict) else str(rq)
        hint = rq.get("block") if isinstance(rq, dict) else None
        if text:
            hit = check_paper(text, hint, "related quote")
            if hit and isinstance(rq, dict):
                rq["block"] = hit[0].id
                rq["location"] = hit[0].anchor.label()
    for ev in finding.evidence:
        if ev.type == "quote" and ev.text:
            hit = check_paper(ev.text, ev.block, "evidence quote")
            if hit:
                ev.block = hit[0].id
        elif ev.type == "source_quote" and ev.text:
            report["checked"] += 1
            ref = ev.ref or ""
            if ref not in source_cache:
                source_cache[ref] = _source_text(work, ref)
            source = source_cache[ref]
            if source is None:
                report["unverifiable"].append(f"source quote from {ref}: no cached text to check against")
            elif not find_quote(ev.text, source):
                report["failed"].append(f"source quote from {ref}: not found in the cached text: {ev.text[:80]!r}")
    for loc in finding.locations:
        _fill_location(pm, loc)
    return report


def verify_work(work: Path) -> int:
    pm = PaperMap.load(work / "paper_map.json")
    files = sorted((work / "findings").glob("*.json")) if (work / "findings").exists() else []
    source_cache: dict = {}
    total = dropped = moved = unverifiable = 0
    unreadable = []
    for path in files:
        fs, errors, _notes = load_findings_file(path)
        if fs is None:
            unreadable.append((path.name, errors))
            continue
        for f in fs.findings:
            total += 1
            result = verify_finding(pm, work, f, source_cache)
            f.verification["quotes"] = result
            if result["failed"]:
                if f.status != "dropped":
                    dropped += 1
                f.status = "dropped"
                f.verification["dropped_reason"] = "; ".join(result["failed"])
            elif f.status == "dropped" and f.verification.get("dropped_reason", "").startswith(("quote", "related", "evidence", "source")):
                f.status = "likely"  # a repaired finding gets another chance
                f.verification.pop("dropped_reason", None)
            moved += bool(result.get("moved"))
            unverifiable += bool(result["unverifiable"])
        fs.save(path)
    print(f"Verified {total} findings in {len(files) - len(unreadable)} files: {dropped} dropped for quotes not found, "
          f"{moved} relocated to the block where the quote was found, "
          f"{unverifiable} with source quotes that have no cached text.")
    for name, errors in unreadable:
        print(f"ERROR: {name} could not be read, so its findings are missing from the report: {errors[0]}")
    return 1 if unreadable else 0


def find_command(work: Path, quote: str) -> int:
    pm = PaperMap.load(work / "paper_map.json")
    found = 0
    for block in pm.blocks:
        span = find_quote(quote, block.text)
        if span:
            found += 1
            s, e = span
            context = normalize(block.text[max(0, s - 80):min(len(block.text), e + 80)])
            print(json.dumps({"block": block.id, "kind": block.kind, "location": block.anchor.label(),
                              "section": block.section, "context": context}, ensure_ascii=False))
    if not found:
        print("Not found. Copy the quote exactly from paper_text.md; a shorter exact piece is better than a paraphrase.")
        return 1
    return 0
