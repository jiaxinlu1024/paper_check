"""`pc.py report WORK`: merge all findings and write the report and the JSON file.

Inputs, all inside the work folder:
  paper_map.json                 the paper map
  settings.json                  settings saved at ingest (mode, venue, network, ...)
  findings/*.json                one FindingSet per producer (scripts, refs, agents)
  references/cards.json          optional: one evidence card per reference
  citations/verdicts.json        optional: one row per citation, from the judge agents
  agents/claim_map.json          optional: claim-evidence map from the logic agent

Outputs, beside the work folder:
  paper-check-report.md          for people
  paper-check-findings.json      the same findings for agents, with the same IDs
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from . import __version__
from .config import OUTPUT_FINDINGS, OUTPUT_REPORT
from .model import PaperMap
from .textutil import normalize

SKILL_DIR = Path(__file__).resolve().parents[2]
SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2, "suggestion": 3}
SEVERITY_TITLE = {"critical": "Critical", "major": "Major", "minor": "Minor", "suggestion": "Suggestion"}
STATUS_TEXT = {"confirmed": "confirmed", "likely": "likely", "needs_human": "needs human judgment"}
FRONT_KINDS = {"title": "Title", "author": "Author line", "abstract": "Abstract", "keywords": "Keywords",
               "jel": "JEL codes", "acknowledgment": "Acknowledgments", "front_matter": "Front matter"}

HOW_TO_READ = (
    "How to read this report. Findings are grouped by severity and, within each group, follow the order of "
    "the paper. Every quote was checked against the paper text by a script; findings whose quotes could not "
    "be found were dropped and are listed at the end. *Confirmed* means the evidence settles the point, "
    "*likely* means it probably holds but deserves a second look, and *needs human judgment* means the skill "
    "could not decide. The index lists every finding in paper order, for fixing the draft from top to bottom. "
    "The coverage table lists every check, including the ones that were skipped: a skipped check was not "
    "passed, it was not run."
)


def _load_checklist() -> tuple[dict, dict]:
    import yaml

    data = yaml.safe_load((SKILL_DIR / "references" / "checks.yaml").read_text(encoding="utf-8"))
    return {c["id"]: c for c in data["checks"]}, data["dimensions"]


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except json.JSONDecodeError:
        return None


def _cell(value, limit: Optional[int] = None) -> str:
    text = normalize(str(value if value is not None else ""))
    if limit and len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return text.replace("|", "\\|")


def _md_table(header: list, rows: list) -> list:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append("| " + " | ".join(_cell(c) for c in r) + " |")
    return out


class Locator:
    """Turns block ids into labels such as "1 Introduction, paragraph 2, sentence 1 (intro.tex:4-5)"."""

    def __init__(self, pm: PaperMap):
        self.pm = pm
        self.order = pm.block_order()
        self.para_no: dict = {}
        counts: Counter = Counter()
        for b in pm.blocks:
            if b.kind in ("paragraph", "list_item"):
                counts[(tuple(b.section), b.kind)] += 1
                self.para_no[b.id] = counts[(tuple(b.section), b.kind)]
        self.caption_of: dict = {}
        for t in pm.tables:
            if t.caption_block:
                self.caption_of[t.caption_block] = f"Table {t.number}" if t.number else "a table"
        for fg in pm.figures:
            if fg.caption_block:
                self.caption_of[fg.caption_block] = f"Figure {fg.number}" if fg.number else "a figure"

    def ref_name(self, ref_id: Optional[str]) -> str:
        ref = self.pm.reference(ref_id) if ref_id else None
        if ref is None:
            return ref_id or "cited work"
        authors = ref.fields.get("authors") or []
        fams = [a.get("family") or a.get("literal") or "" for a in authors if isinstance(a, dict)]
        fams = [f for f in fams if f]
        year = ref.fields.get("year") or "n.d."
        if not fams:
            return f"{ref.key or ref.id} ({year})"
        name = fams[0] if len(fams) == 1 else f"{fams[0]} and {fams[1]}" if len(fams) == 2 else f"{fams[0]} et al."
        return f"{name} ({year})"

    def element(self, block) -> str:
        kind, attrs = block.kind, block.attrs or {}
        num = attrs.get("number")
        if kind in ("paragraph", "list_item"):
            word = "paragraph" if kind == "paragraph" else "list item"
            n = self.para_no.get(block.id)
            return f"{word} {n}" if n else word
        if kind == "table":
            return f"Table {num}" if num else "table"
        if kind == "caption":
            target = self.caption_of.get(block.id)
            if not target and num:
                target = f"{str(attrs.get('float') or 'table').capitalize()} {num}"
            return f"caption of {target}" if target else "caption"
        if kind == "equation":
            return f"Equation ({num})" if num else "equation"
        if kind == "footnote":
            return f"footnote {num}" if num else "footnote"
        if kind == "reference":
            return f"entry {self.ref_name(attrs.get('ref'))}" if attrs.get("ref") else "entry"
        return kind.replace("_", " ")

    def sentence_no(self, block, start: Optional[int]) -> Optional[int]:
        if start is None or len(block.sentences) < 2:
            return None
        for i, s in enumerate(block.sentences, 1):
            if s.start <= start < s.end:
                return i
        return None

    def label(self, block_id: Optional[str], anchor=None, section=None, start: Optional[int] = None) -> str:
        block = self.pm.block(block_id) if block_id else None
        anchor = anchor or (block.anchor if block else None)
        anchor_label = anchor.label() if anchor else ""
        if block is None:
            return anchor_label or block_id or "whole paper"
        parts = []
        if block.kind in FRONT_KINDS:
            parts.append(FRONT_KINDS[block.kind])
        else:
            sec = list(section or block.section)
            if sec:
                parts.append(sec[-1])
            if block.kind != "heading":
                parts.append(self.element(block))
            elif not sec:
                parts.append("heading")
        n = self.sentence_no(block, start)
        if n:
            parts.append(f"sentence {n}")
        text = ", ".join(p for p in parts if p)
        return f"{text} ({anchor_label})" if anchor_label and text else (text or anchor_label)

    def where(self, f) -> str:
        span = (f.verification or {}).get("quotes", {}).get("quote_span") or {}
        labels = []
        for loc in f.locations:
            start = span.get("start") if span.get("block") == loc.block else None
            labels.append(self.label(loc.block, loc.anchor, loc.section, start))
        return "; ".join(dict.fromkeys(labels)) or "whole paper"

    def first_order(self, f) -> int:
        for loc in f.locations:
            if loc.block in self.order:
                return self.order[loc.block]
        return 10**9


def _dedupe(findings: list) -> list:
    merged: dict = {}
    for f in findings:
        block = f.locations[0].block if f.locations else None
        key = (f.check_id, block, normalize(f.quote or "").lower()[:200],
               normalize(f.problem).lower()[:80] if not f.quote else "")
        if key not in merged:
            merged[key] = f
            continue
        keep = merged[key]
        if SEVERITY_RANK.get(f.severity, 9) < SEVERITY_RANK.get(keep.severity, 9):
            keep.severity = f.severity
        keep.evidence.extend(e for e in f.evidence if e not in keep.evidence)
        keep.trajectory.extend(t for t in f.trajectory if t not in keep.trajectory)
        keep.extra.setdefault("merged_from", []).append(f.producer.get("name"))
    return list(merged.values())


def _refuted(f) -> bool:
    return str((f.verification or {}).get("refuter") or "").strip().lower().startswith(("refuted", "overturned"))


def _evidence_line(ev, loc: Locator) -> str:
    d = ev.data or {}
    if ev.type == "quote":
        where = loc.label(ev.block) if ev.block else ""
        return f'Quote{", " + where if where else ""}: "{normalize(ev.text or "")}"'
    if ev.type == "source_quote":
        bits = [loc.ref_name(ev.ref) if ev.ref else None, f"p. {ev.page}" if ev.page else None,
                d.get("version") and f"{d['version']} version"]
        return f'Source ({", ".join(b for b in bits if b)}): "{normalize(ev.text or "")}"'
    if ev.type == "computed_result":
        inputs = d.get("inputs")
        line = f"Computed: {d.get('formula') or ev.text or ''}"
        if inputs:
            line += f" with {json.dumps(inputs, ensure_ascii=False)}"
        if "output" in d:
            line += f" = {d['output']}"
        if d.get("tolerance") is not None:
            line += f" (tolerance {d['tolerance']})"
        if d.get("formula") and ev.text:
            line += f". {ev.text}"
        return line
    if ev.type == "checked_absence":
        terms = d.get("terms") or {}
        hits = ", ".join(f'"{t}" {n}' for t, n in terms.items()) if isinstance(terms, dict) else str(terms)
        scope = d.get("scope") or "the full text"
        if ev.ref:
            scope = f"{scope} of {loc.ref_name(ev.ref)}"
        version = f" ({d['version']} version)" if d.get("version") else ""
        line = f"Searched {scope}{version}: {hits}" if hits else f"Searched {scope}{version}"
        return line + (f". {ev.text}" if ev.text else "")
    if ev.type == "lookup_record":
        bits = [d.get("database"), d.get("query") and f'query "{d.get("query")}"', d.get("record"), ev.url]
        return "Lookup: " + "; ".join(str(b) for b in bits if b) + (f". {ev.text}" if ev.text else "")
    if ev.type == "image":
        page = f"page {ev.page}, " if ev.page else ""
        return f"Image: {page}{d.get('path') or ''} {ev.text or ''}".strip()
    if ev.type == "script_output":
        return f"{d.get('script', 'Script')}: {ev.text or json.dumps(d, ensure_ascii=False)}"
    return ev.text or json.dumps(d, ensure_ascii=False)


def _render_finding(f, loc: Locator, checklist: dict, dimensions: dict) -> str:
    info = checklist.get(f.check_id, {})
    check_title = info.get("title", "")
    dim = dimensions.get(f.dimension, f.dimension)
    lines = [f"### {f.id} · {SEVERITY_TITLE.get(f.severity, f.severity)} · {f.check_id} · {f.title or check_title}",
             f"Check: {f.check_id} {check_title} ({dim}) · Status: {STATUS_TEXT.get(f.status, f.status)} · "
             f"Confidence: {f.confidence}",
             f"Where: {loc.where(f)}", ""]
    if f.quote:
        lines += [f"> \"{normalize(f.quote)}\"", ""]
    lines += [f"Problem: {f.problem}", ""]
    proof = [_evidence_line(e, loc) for e in f.evidence]
    for rq in f.related_quotes:
        text = rq.get("quote") if isinstance(rq, dict) else rq
        where = loc.label(rq.get("block")) if isinstance(rq, dict) and rq.get("block") else (
            rq.get("location") if isinstance(rq, dict) else None)
        proof.append(f'Related{", " + where if where else ""}: "{normalize(text or "")}"')
    if proof:
        lines.append("Proof:")
        lines += [f"- {p}" for p in proof]
        lines.append("")
    trajectory = list(f.trajectory)
    ver = f.verification or {}
    if ver.get("refuter"):
        trajectory.append(f"Refuter: {ver['refuter']}" + (f". {ver['refuter_note']}" if ver.get("refuter_note") else ""))
    if ver.get("runs"):
        trajectory.append(f"Found in {ver['runs']}.")
    if trajectory:
        lines.append("Trajectory:")
        lines += [f"{i}. {t}" for i, t in enumerate(trajectory, 1)]
    settings = f.producer.get("settings")
    if isinstance(settings, dict) and settings:
        lines.append("Verifier settings: " + ", ".join(f"{k} {v}" for k, v in settings.items()))
    if trajectory or settings:
        lines.append("")
    if f.fix:
        fx = f.fix
        if fx.action == "replace" and fx.original and fx.replacement is not None:
            lines.append(f'Suggested fix: replace "{fx.original}" with "{fx.replacement}".' + (f" {fx.detail}" if fx.detail else ""))
        elif fx.action == "investigate":
            lines.append(f"Suggested fix (investigate): {fx.detail or 'check this passage against the evidence above.'}")
        else:
            lines.append(f"Suggested fix ({fx.action}): {fx.detail or ''}".rstrip())
        if fx.resolved_when:
            lines.append(f"Resolved when: {fx.resolved_when}")
        lines.append("")
    return "\n".join(lines)


def _coverage(checklist: dict, coverage: dict, kept: list) -> list:
    rows = []
    found = Counter(f.check_id for f in kept)
    for cid, info in checklist.items():
        entries = coverage.get(cid, [])
        statuses = {c.status for c in entries}
        reasons = sorted({f"{c.producer + ': ' if c.producer else ''}{c.reason}" for c in entries
                          if c.reason and c.status != "run"})
        if not entries:
            status, detail = "not run", "No producer covered this check in this run."
        elif statuses == {"run"} or statuses == {"run", "not_applicable"}:
            notes = sorted({c.reason for c in entries if c.status == "run" and c.reason})
            status, detail = "run", f"{found.get(cid, 0)} findings" + ("; " + "; ".join(notes) if notes else "")
        elif "run" in statuses:
            status = "partly run"
            detail = f"{found.get(cid, 0)} findings; not run in part: " + "; ".join(reasons)
        elif statuses == {"not_applicable"}:
            status, detail = "not applicable", "; ".join(reasons)
        else:
            status, detail = "skipped", "; ".join(reasons) or "no reason given"
        rows.append({"check_id": cid, "title": info["title"], "dimension": info.get("dimension"),
                     "status": status, "detail": detail,
                     "producers": sorted({c.producer for c in entries if c.producer})})
    return rows


def build_report(work: Path, settings=None, venue_id: Optional[str] = None) -> int:
    from .verify import load_findings_file

    pm = PaperMap.load(work / "paper_map.json")
    checklist, dimensions = _load_checklist()
    loc = Locator(pm)
    if settings is None:
        from .config import PaperSettings
        settings = PaperSettings.for_work(work, {"venue": venue_id})
    venue = None
    if settings.venue:
        from .venues import load_venue
        venue = load_venue(settings.venue)

    sets, unreadable = [], []
    for path in sorted((work / "findings").glob("*.json")) if (work / "findings").exists() else []:
        fs, errors, _notes = load_findings_file(path)
        if fs is None:
            unreadable.append((path.name, errors[0] if errors else "unreadable"))
        else:
            sets.append(fs)

    warnings = []
    verdicts = []
    for vpath in sorted((work / "citations").glob("verdicts*.json")) if (work / "citations").exists() else []:
        data = _load_json(vpath)
        if isinstance(data, dict):
            data = data.get("verdicts") or []
        if isinstance(data, list):
            verdicts.extend(v for v in data if isinstance(v, dict))
        else:
            warnings.append(f"{vpath.name} could not be read, so its citation verdicts are missing.")
    verdicts.sort(key=lambda v: str(v.get("id") or ""))

    findings, coverage = [], defaultdict(list)
    for fs in sets:
        for f in fs.findings:
            f.producer.setdefault("name", fs.producer)
            findings.append(f)
        for c in fs.coverage:
            c.producer = c.producer or fs.producer
            coverage[c.check_id].append(c)
    dropped = [f for f in findings if f.status == "dropped" and not _refuted(f)]
    refuted = [f for f in findings if _refuted(f)]
    kept = _dedupe([f for f in findings if f.status != "dropped" and not _refuted(f)])
    min_rank = SEVERITY_RANK.get(settings.min_severity, 3)
    below = [f for f in kept if SEVERITY_RANK.get(f.severity, 9) > min_rank]
    kept = [f for f in kept if SEVERITY_RANK.get(f.severity, 9) <= min_rank]
    kept.sort(key=lambda f: (SEVERITY_RANK.get(f.severity, 9), loc.first_order(f), f.check_id))
    for i, f in enumerate(kept, 1):
        f.id = f"F-{i:03d}"

    counts = Counter(f.severity for f in kept)
    by_dim = Counter(f.dimension for f in kept)
    cov_rows = _coverage(checklist, coverage, kept)
    cov_counts = Counter(r["status"] for r in cov_rows)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- header ---------------------------------------------------------
    paper_name = pm.title or Path(pm.source.get("path", "")).name
    md = [f"# Paper check report: {paper_name}", ""]
    files = pm.source.get("files") or []
    md.append(f"- **Paper:** {pm.source.get('path')} ({pm.source.get('format')})"
              + (f", {len(files)} source files" if len(files) > 1 else ""))
    md.append(f"- **Checked:** {now} with paper-check {__version__}, mode {settings.mode}, "
              f"network {'on' if settings.network else 'off'}")
    if venue:
        stale = " This profile is more than 180 days old; recheck the journal's guidelines." if venue.get("_stale") else ""
        md.append(f"- **Venue profile:** {venue['name']}, rules checked {venue['checked_on']}.{stale}")
    else:
        md.append("- **Venue profile:** none, so journal-specific rules were not checked.")
    md.append(f"- **Cited-work PDFs:** {settings.sources or 'no sources folder'}")
    md.append(f"- **Producers:** {', '.join(sorted({fs.producer for fs in sets})) or 'none'}")
    md += ["", HOW_TO_READ, ""]
    for name, err in unreadable:
        warnings.append(f"The findings file {name} could not be read, so its findings are missing: {err}")
    if not settings.network:
        warnings.append("The network was off, so reference and citation lookups were skipped, not passed.")
    if pm.warnings:
        warnings.append(f"Reading the paper produced {len(pm.warnings)} warnings; see the appendix on ingestion.")
    if below:
        warnings.append(f"{len(below)} findings below the minimum severity ({settings.min_severity}) are left out.")
    if warnings:
        md += ["**Warnings**", ""] + [f"- {w}" for w in warnings] + [""]

    # ---- summary --------------------------------------------------------
    md += ["## Summary", ""]
    md += _md_table(["Severity", "Findings", "Confirmed", "Likely", "Needs human judgment"],
                    [[SEVERITY_TITLE[s], counts.get(s, 0),
                      sum(1 for f in kept if f.severity == s and f.status == "confirmed"),
                      sum(1 for f in kept if f.severity == s and f.status == "likely"),
                      sum(1 for f in kept if f.severity == s and f.status == "needs_human")] for s in SEVERITY_RANK])
    md.append("")
    if by_dim:
        md += _md_table(["Dimension", "Findings"],
                        [[f"{dimensions.get(d, d)} ({d})", n] for d, n in sorted(by_dim.items(), key=lambda x: (-x[1], x[0]))])
        md.append("")
    top = kept[:5]
    if top:
        md += ["Top issues:", ""]
        md += [f"{i}. **{f.id}** ({SEVERITY_TITLE[f.severity]}, {f.check_id}): {f.title}. {f.problem}"
               for i, f in enumerate(top, 1)]
        md.append("")
    else:
        md += ["No findings.", ""]
    md.append(f"Coverage: of {len(cov_rows)} checks, {cov_counts.get('run', 0)} ran, "
              f"{cov_counts.get('partly run', 0)} ran in part, {cov_counts.get('not applicable', 0)} did not apply, "
              f"{cov_counts.get('skipped', 0)} were skipped and {cov_counts.get('not run', 0)} were not run.")
    md.append("")

    # ---- findings -------------------------------------------------------
    for sev in SEVERITY_RANK:
        group = [f for f in kept if f.severity == sev]
        if group:
            md += [f"## {SEVERITY_TITLE[sev]} findings ({len(group)})", ""]
            md += [_render_finding(f, loc, checklist, dimensions) for f in group]

    if kept:
        md += ["## Index in paper order", ""]
        index_rows = sorted(kept, key=lambda f: (loc.first_order(f), SEVERITY_RANK.get(f.severity, 9)))
        md += _md_table(["Finding", "Where", "Check", "Severity", "Problem"],
                        [[f.id, loc.where(f), f.check_id, SEVERITY_TITLE[f.severity], _cell(f.problem, 160)]
                         for f in index_rows])
        md.append("")

    md += ["## Coverage", "",
           "Every check in the checklist and what happened to it in this run. Skipped checks were not passed: "
           "they were not run.", ""]
    md += _md_table(["Check", "Title", "Outcome", "Detail"],
                    [[r["check_id"], r["title"], r["status"], r["detail"]] for r in cov_rows])
    md.append("")

    # ---- appendices -----------------------------------------------------
    appendices = {}
    cards = _load_json(work / "references" / "cards.json")
    if isinstance(cards, dict):
        cards = cards.get("cards") or list(cards.values())
    if cards:
        appendices["references"] = cards
        md += ["## Appendix: references", "",
               "One evidence card per reference. The full cards, with every query made, are in "
               f"{OUTPUT_FINDINGS} and paper-check-work/references/cards.json.", ""]
        rows = []
        for c in cards:
            matched = c.get("matched") if isinstance(c.get("matched"), dict) else {}
            rows.append([c.get("ref"), _cell(c.get("raw"), 110), c.get("verdict"),
                         _cell(c.get("matched_title") or matched.get("title") or "", 80),
                         ", ".join(c.get("databases_reached") or c.get("databases") or [])])
        md += _md_table(["Ref", "Reference", "Verdict", "Matched record", "Databases"], rows)
        md.append("")
    if verdicts:
        appendices["citation_support"] = verdicts
        md += ["## Appendix: citation support", "",
               "One row per citation: does the cited work support the sentence that cites it?", ""]
        md += _md_table(["Citation", "Section", "Claim", "Cited work", "Verdict", "Version read"],
                        [[v.get("id"), v.get("section"), _cell(v.get("claim"), 120),
                          loc.ref_name(v.get("ref")) if v.get("ref") else "", v.get("verdict"),
                          v.get("version_read") or ""] for v in verdicts])
        md.append("")
        per_section = defaultdict(Counter)
        for v in verdicts:
            per_section[v.get("section") or "Unknown"][v.get("verdict") or "unknown"] += 1
        names = sorted({k for c in per_section.values() for k in c})
        md += ["Per section:", ""]
        md += _md_table(["Section"] + names, [[s] + [c.get(k, 0) for k in names] for s, c in per_section.items()])
        md.append("")
    claim_map = _load_json(work / "agents" / "claim_map.json")
    if isinstance(claim_map, dict):
        claim_map = claim_map.get("claims") or []
    if claim_map:
        appendices["claim_evidence_map"] = claim_map
        md += ["## Appendix: claim-evidence map", "",
               "Each main claim, where the paper makes it, and the evidence offered for it.", ""]
        md += _md_table(["Claim", "Where", "Evidence", "Assessment"],
                        [[_cell(c.get("claim"), 140), c.get("location") or c.get("where") or "",
                          _cell(c.get("evidence") if isinstance(c.get("evidence"), str)
                                else json.dumps(c.get("evidence"), ensure_ascii=False), 140),
                          c.get("assessment") or c.get("verdict") or ""] for c in claim_map])
        md.append("")
    numeric = [(f, e) for f in kept for e in f.evidence if e.type == "computed_result"]
    if numeric:
        md += ["## Appendix: recomputed numbers", "", "Every number the scripts recomputed for a finding.", ""]
        md += _md_table(["Finding", "Check", "Computation", "Result"],
                        [[f.id, f.check_id, _cell((e.data or {}).get("formula") or e.text, 110),
                          _cell((e.data or {}).get("output"), 40)] for f, e in numeric])
        md.append("")
    if refuted:
        md += ["## Appendix: refuted findings", "",
               "An independent refuter overturned these with quoted counter-evidence. They are listed so nothing "
               "disappears silently.", ""]
        md += _md_table(["Check", "Title", "Where", "Refuter's evidence"],
                        [[f.check_id, f.title, loc.where(f), _cell(f.verification.get("refuter_note"), 200)]
                         for f in refuted])
        md.append("")
    if dropped:
        md += ["## Appendix: dropped findings", "",
               "These failed quote verification: a quote could not be found in the paper or in the cited work.", ""]
        md += _md_table(["Check", "Title", "Reason"],
                        [[f.check_id, f.title, _cell(f.verification.get("dropped_reason"), 200)] for f in dropped])
        md.append("")
    if pm.warnings:
        md += ["## Appendix: ingestion warnings", "",
               "Problems met while reading the paper. Checks near these places may be less reliable.", ""]
        md += [f"- {_cell(w, 300)}" for w in pm.warnings[:100]]
        md.append("")

    paper_dir = work.parent
    (paper_dir / OUTPUT_REPORT).write_text("\n".join(md), encoding="utf-8")
    out_findings = []
    for f in kept:
        d = f.to_dict()
        d["dimension"] = f.dimension
        d["where"] = loc.where(f)
        out_findings.append(d)
    out = {
        "schema_version": 1, "generated": now, "tool": f"paper-check {__version__}",
        "paper": {"path": pm.source.get("path"), "format": pm.source.get("format"), "title": pm.title},
        "settings": {"mode": settings.mode, "venue": settings.venue, "network": settings.network,
                     "sources": settings.sources, "min_severity": settings.min_severity},
        "venue": {"id": venue["id"], "checked_on": venue["checked_on"]} if venue else None,
        "summary": {"by_severity": {s: counts.get(s, 0) for s in SEVERITY_RANK}, "by_dimension": dict(by_dim),
                    "coverage": dict(cov_counts), "below_min_severity": len(below)},
        "findings": out_findings,
        "refuted": [f.to_dict() for f in refuted],
        "dropped": [f.to_dict() for f in dropped],
        "coverage": cov_rows,
        "appendices": appendices,
        "warnings": warnings,
    }
    (paper_dir / OUTPUT_FINDINGS).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {paper_dir / OUTPUT_REPORT} and {paper_dir / OUTPUT_FINDINGS}: {len(kept)} findings "
          f"({', '.join(f'{counts.get(s, 0)} {s}' for s in SEVERITY_RANK)}), {len(refuted)} refuted, "
          f"{len(dropped)} dropped.")
    for name, err in unreadable:
        print(f"WARNING: {name} could not be read: {err}")
    return 0
