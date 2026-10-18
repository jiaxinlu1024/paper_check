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
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from . import __version__
from .config import OUTPUT_FINDINGS, OUTPUT_REPORT
from .model import PaperMap
from .textutil import find_quote, normalize

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
        labels = list(dict.fromkeys(labels))
        if len(labels) > 3:
            return "; ".join(labels[:3]) + f"; and {len(labels) - 3} more places"
        return "; ".join(labels) or "whole paper"

    def first_order(self, f) -> int:
        return self.position(f)[0]

    def position(self, f) -> tuple:
        """Where a finding first appears: (block order, offset of its quote in the block). A location with
        only an anchor, such as a PDF annotation's page and line, sorts after the block it follows."""
        for loc in f.locations:
            if loc.block in self.order:
                block = self.pm.block(loc.block)
                span = find_quote(f.quote, block.text) if f.quote and block is not None else None
                return (self.order[loc.block], span[0] if span else 0)
        for loc in f.locations:
            near = self._block_near(loc.anchor)
            if near is not None:
                return (self.order[near.id], 10**6)
        return (10**9, 0)

    def _block_near(self, anchor):
        """The last block that starts at or before an anchor without a block (same page and line,
        Word paragraph, or LaTeX file and line)."""
        if anchor is None:
            return None
        if anchor.page is not None:
            key = (lambda a: (a.page, a.page_line or 0)) if anchor.page_line is not None else (lambda a: (a.page, 0))
            target = (anchor.page, anchor.page_line or 0)
            pool = [b for b in self.pm.blocks if b.anchor.page is not None]
        elif anchor.paragraph is not None:
            key, target = (lambda a: (a.paragraph,)), (anchor.paragraph,)
            pool = [b for b in self.pm.blocks if b.anchor.paragraph is not None]
        elif anchor.file and anchor.line is not None:
            key, target = (lambda a: (a.line,)), (anchor.line,)
            pool = [b for b in self.pm.blocks if b.anchor.file == anchor.file and b.anchor.line is not None]
        else:
            return None
        before = [b for b in pool if key(b.anchor) <= target]
        return max(before, key=lambda b: (key(b.anchor), self.order[b.id])) if before else (pool[0] if pool else None)


# Checks that often report the same underlying problem from different angles. Findings
# from one family whose quotes overlap in the same block are merged into one finding,
# which keeps every producer's problem statement and evidence.
RELATED = [
    {"NUM-01", "COH-02", "NUM-05", "NUM-06", "COH-04", "LOG-04"},
    {"NUM-03", "NUM-08", "LOG-09", "BEH-09"},
    {"NUM-02", "NUM-09", "NUM-07"},
    {"CIT-06", "FACT-02", "FACT-03", "BEH-15", "CIT-13", "CIT-08"},
    {"CIT-02", "CIT-03", "CIT-12"},
    {"LOG-02", "LOG-03", "LANG-03", "LOG-09"},
    {"BEH-06", "MTH-07", "BEH-07"},
    {"FMT-11", "FMT-12"},
    {"COH-05", "COH-06", "COH-07"},
    {"CIT-01", "FMT-05"},
    {"FMT-05", "FMT-16", "COH-03"},
    {"BEH-01", "ETH-01"},
    {"BEH-12", "ETH-01", "FMT-03"},
    {"BEH-13", "MTH-03", "CIT-11"},
    {"BEH-11", "CIT-11"},
    {"FIG-04", "FMT-10", "NUM-07"},
    {"LANG-02", "LANG-08", "COH-08"},
    {"FACT-06", "REV-02", "CIT-09"},
    {"BEH-16", "FMT-03", "FMT-01"},
    {"FMT-18", "ETH-04"},
]
STATUS_RANK = {"confirmed": 0, "likely": 1, "needs_human": 2}
CONF_RANK = {"high": 0, "medium": 1, "low": 2}


def _related(a: str, b: str) -> bool:
    return a == b or any(a in g and b in g for g in RELATED)


def _span(f):
    sp = (f.verification or {}).get("quotes", {}).get("quote_span")
    return (sp["block"], sp["start"], sp["end"]) if sp else None


def _strength(f) -> tuple:
    return (SEVERITY_RANK.get(f.severity, 9), STATUS_RANK.get(f.status, 9), CONF_RANK.get(f.confidence, 9),
            0 if f.producer.get("kind") == "script" else 1)


def _key(f) -> str:
    """A key that names a finding across report builds: its producer, check, block and quote."""
    base = "|".join([str(f.producer.get("name") or ""), str(f.producer.get("check") or ""), f.check_id,
                     str((f.locations[0].block if f.locations else "") or ""), normalize(f.quote or "").lower()[:300],
                     "" if f.quote else normalize(f.problem or "").lower()[:200]])
    return f"{f.check_id}-{hashlib.sha1(base.encode('utf-8')).hexdigest()[:8]}"


def _chosen_top(kept: list, work: Path, warnings: list, n: int = 5) -> tuple:
    """The top issues the consolidation agent chose (consolidation.json "top": keys in order of
    importance), as ([findings], True); ([], False) when it chose none."""
    path = work / "consolidation.json"
    data = _load_json(path) if path.exists() else None
    keys = data.get("top") if isinstance(data, dict) else None
    if not isinstance(keys, list) or not keys:
        return [], False
    index: dict = {}
    for f in kept:
        for k in [f.extra.get("key")] + list(f.extra.get("absorbed_keys") or []):
            if k:
                index.setdefault(k, f)
    out = []
    for k in keys:
        f = index.get(k) if isinstance(k, str) else None
        if f is None:
            warnings.append(f"consolidation.json names a top issue that this report does not have: {k}")
        elif f not in out:
            out.append(f)
    return out[:n], bool(out)


def _top_issues(kept: list, n: int = 5) -> list:
    """The findings to name first: the most severe, then confirmed before likely before needs human
    judgment, then those reported from the most dimensions, then the most confident, then paper order."""
    order = {id(f): i for i, f in enumerate(kept)}

    def dimensions(f) -> int:
        return len({f.check_id.split("-")[0]} | {a["check_id"].split("-")[0] for a in f.extra.get("also", [])})
    return sorted(kept, key=lambda f: (SEVERITY_RANK.get(f.severity, 9), STATUS_RANK.get(f.status, 9),
                                       -dimensions(f), CONF_RANK.get(f.confidence, 9), order[id(f)]))[:n]


def _assign_keys(findings: list) -> None:
    """Give every finding a key no other finding in the report shares. Two findings with one producer,
    check, block and quote (a reference's wrong year and its missing DOI) are told apart by their title
    and problem; the shared plain key is then given to neither, so a consolidation that named it is
    reported instead of applied to the wrong finding."""
    base = [_key(f) for f in findings]
    counts = Counter(base)
    used: Counter = Counter()
    for f, k in zip(findings, base):
        if counts[k] > 1:
            tail = normalize(f"{f.title}|{f.problem or ''}").lower()[:400]
            k = f"{k}{hashlib.sha1(tail.encode('utf-8')).hexdigest()[:4]}"
            used[k] += 1
            if used[k] > 1:
                k = f"{k}-{used[k]}"
        f.extra["key"] = k


def _take_keys(keep, other) -> None:
    keys = keep.extra.setdefault("absorbed_keys", [])
    for k in [other.extra.get("key")] + list(other.extra.get("absorbed_keys") or []):
        if k and k not in keys and k != keep.extra.get("key"):
            keys.append(k)


def _absorb(keep, other, note: str) -> None:
    _take_keys(keep, other)
    keep.evidence.extend(e for e in other.evidence if e not in keep.evidence)
    keep.related_quotes.extend(q for q in other.related_quotes if q not in keep.related_quotes)
    keep.trajectory.extend(t for t in other.trajectory if t not in keep.trajectory)
    keep.extra.setdefault("also", []).append({
        "check_id": other.check_id, "title": other.title, "severity": other.severity, "status": other.status,
        "producer": other.producer.get("name"), "source": list(_source(other)), "problem": other.problem,
        "note": note})
    # A less severe finding cannot confirm a more severe claim: a confirmed Major "the DOI belongs to
    # another paper" does not confirm a likely Critical "the work does not exist".
    if SEVERITY_RANK.get(other.severity, 9) <= SEVERITY_RANK.get(keep.severity, 9):
        if STATUS_RANK.get(other.status, 9) < STATUS_RANK.get(keep.status, 9):
            keep.status = other.status
        if CONF_RANK.get(other.confidence, 9) < CONF_RANK.get(keep.confidence, 9):
            keep.confidence = other.confidence


def _sentence_of(pm, block_id: str, pos: int):
    block = pm.block(block_id) if pm is not None else None
    if block is None:
        return None
    for i, sent in enumerate(block.sentences):
        if sent.start <= pos < sent.end:
            return i
    return None


def _merge_root_causes(findings: list, pm=None) -> list:
    """Merge findings of related checks that quote the same passage: their quotes overlap by
    half or more in one block, or overlap at all within one sentence."""
    findings = sorted(findings, key=_strength)
    kept: list = []
    for f in findings:
        sf = _span(f)
        target = None
        if sf:
            for k in kept:
                sk = _span(k)
                if _source(k) == _source(f) or _source(f) in {tuple(a.get("source") or ()) for a in k.extra.get("also", [])}:
                    continue
                if not sk or sk[0] != sf[0] or not (_related(k.check_id, f.check_id) or any(
                        _related(a.get("check_id", ""), f.check_id) for a in k.extra.get("also", []))):
                    continue
                inter = min(sk[2], sf[2]) - max(sk[1], sf[1])
                if inter <= 0:
                    continue
                same_sentence = (_sentence_of(pm, sf[0], max(sk[1], sf[1])) is not None and
                                 _sentence_of(pm, sf[0], sf[1]) == _sentence_of(pm, sk[0], sk[1]))
                if inter >= 0.5 * min(sk[2] - sk[1], sf[2] - sf[1]) or same_sentence:
                    target = k
                    break
        if target is None:
            kept.append(f)
        else:
            _absorb(target, f, "same passage, related check")
    return kept


def _source(f) -> tuple:
    """Who produced a finding: the producer and, for scripts, the check function."""
    return (f.producer.get("name"), f.producer.get("check"))


def _pair_runs(findings: list) -> list:
    """Join the run-1 and run-2 copies of one problem that merge-runs left unpaired: a producer with exactly
    one single-run finding of a check from each run."""
    groups: dict = defaultdict(list)
    for f in findings:
        if (f.verification or {}).get("runs") == "1 of 2 runs":
            groups[(f.producer.get("name"), f.check_id)].append(f)
    drop = set()
    for (_name, _cid), fs in groups.items():
        one = [f for f in fs if f.producer.get("run") != 2]
        two = [f for f in fs if f.producer.get("run") == 2]
        if len(one) == 1 and len(two) == 1:
            keep, other = one[0], two[0]
            keep.verification["runs"] = "2 of 2 runs"
            if keep.verification.get("status_before_runs"):
                keep.status = keep.verification.pop("status_before_runs")
            keep.evidence.extend(e for e in other.evidence if e not in keep.evidence)
            keep.related_quotes.extend(q for q in other.related_quotes if q not in keep.related_quotes)
            if other.quote and other.quote != keep.quote:
                keep.related_quotes.append({"quote": other.quote})
            keep.trajectory.append("Second run found it independently, quoting another passage.")
            _take_keys(keep, other)
            drop.add(id(other))
    return [f for f in findings if id(f) not in drop]


GROUP_MIN = 4  # this many minor findings of one kind from one producer become one finding


def _group_patterns(findings: list) -> list:
    """Collapse a recurring minor problem, such as 17 overlong sentences, into one finding that lists every
    instance. Critical and Major findings always stay separate."""
    groups: dict = defaultdict(list)
    for f in findings:
        if f.severity in ("minor", "suggestion"):
            groups[(_source(f), f.check_id, f.title, f.severity)].append(f)
    drop = set()
    for key, fs in groups.items():
        if len(fs) < GROUP_MIN:
            continue
        keep, rest = fs[0], fs[1:]
        keep.extra["instances"] = len(fs)
        keep.problem = f"{len(fs)} instances of this problem; the first is quoted, the others are listed below. {keep.problem}"
        for o in rest:
            if o.quote:
                keep.related_quotes.append({"quote": o.quote, "block": o.locations[0].block if o.locations else None})
            keep.locations.extend(l for l in o.locations if l.block not in {x.block for x in keep.locations})
            _take_keys(keep, o)
            drop.add(id(o))
        keep.trajectory.append(f"Grouped {len(fs)} findings of the same kind from {keep.producer.get('name')}.")
    return [f for f in findings if id(f) not in drop]


def _dedupe(findings: list, pm=None) -> list:
    """Collapse exact repeats from one producer, then merge what different producers found
    about the same passage. Two findings from the same producer are never merged here,
    because a producer that reports two findings means two problems."""
    merged: dict = {}
    findings = _pair_runs(findings)
    for f in findings:
        block = f.locations[0].block if f.locations else None
        key = (_source(f), f.check_id, block, normalize(f.quote or "").lower()[:200],
               normalize(f.problem).lower()[:200])
        if key not in merged:
            merged[key] = f
            continue
        keep = merged[key]
        if SEVERITY_RANK.get(f.severity, 9) < SEVERITY_RANK.get(keep.severity, 9):
            keep.severity = f.severity
        if STATUS_RANK.get(f.status, 9) < STATUS_RANK.get(keep.status, 9):
            keep.status = f.status
        if CONF_RANK.get(f.confidence, 9) < CONF_RANK.get(keep.confidence, 9):
            keep.confidence = f.confidence
        keep.evidence.extend(e for e in f.evidence if e not in keep.evidence)
        keep.trajectory.extend(t for t in f.trajectory if t not in keep.trajectory)
        keep.extra.setdefault("merged_from", []).append(f.producer.get("name"))
        _take_keys(keep, f)
    return _group_patterns(_merge_root_causes(list(merged.values()), pm))


def _consolidate(findings: list, work: Path) -> tuple:
    """Merge the groups a consolidation agent wrote to WORK/consolidation.json: findings from different
    dimensions that report one root cause, which one fix resolves. Each group goes under its most
    severe finding; the others become "also reported" entries with their quotes and places."""
    path = work / "consolidation.json"
    data = _load_json(path) if path.exists() else None
    if not data:
        return findings, []
    groups = data.get("groups") if isinstance(data, dict) else data
    index: dict = {}
    for f in findings:
        for k in [f.extra.get("key")] + list(f.extra.get("absorbed_keys") or []):
            if k:
                index.setdefault(k, f)
    notes, drop, merged = [], set(), 0
    for g in groups if isinstance(groups, list) else []:
        if not isinstance(g, dict):
            continue
        members, seen = [], set()
        for k in g.get("keys") or []:
            f = index.get(k) if isinstance(k, str) else None
            if f is None:
                notes.append(f"consolidation.json names a finding key that this report does not have: {k}")
                continue
            if id(f) not in seen and id(f) not in drop:
                seen.add(id(f))
                members.append(f)
        if len(members) < 2:
            continue
        strongest = min(members, key=_strength)
        prefer = index.get(g.get("keep")) if isinstance(g.get("keep"), str) else None
        keep = prefer if (prefer is not None and id(prefer) in seen and SEVERITY_RANK.get(prefer.severity, 9)
                          <= SEVERITY_RANK.get(strongest.severity, 9)) else strongest
        reason = str(g.get("reason") or "the same root cause").strip().rstrip(".")
        for o in members:
            if o is keep:
                continue
            _absorb(keep, o, f"same root cause: {reason}")
            if o.quote and normalize(o.quote) != normalize(keep.quote or "") and not any(
                    isinstance(q, dict) and q.get("quote") == o.quote for q in keep.related_quotes):
                keep.related_quotes.append({"quote": o.quote, "block": o.locations[0].block if o.locations else None})
            keep.locations.extend(l for l in o.locations if l.block not in {x.block for x in keep.locations})
            drop.add(id(o))
            merged += 1
        keep.trajectory.append(f"Consolidated with {len(members) - 1} finding(s) from other checks that report the "
                               f"same root cause: {reason}.")
    if merged:
        notes.insert(0, f"Consolidated {merged} findings into others that report the same root cause "
                        "(consolidation.json).")
    return [f for f in findings if id(f) not in drop], notes


def _refuted(f) -> bool:
    return str((f.verification or {}).get("refuter") or "").strip().lower().startswith(("refuted", "overturned"))


def _evidence_line(ev, loc: Locator) -> str:
    d = ev.data or {}
    if str(d.get("role") or "").lower().replace("_", "-") == "counter-evidence":
        return "Refuter's counter-evidence: " + _evidence_line(type(ev)(**{**ev.__dict__, "data": {}}), loc)
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
    also = f.extra.get("also", [])
    also_ids = list(dict.fromkeys(a["check_id"] for a in also if a.get("check_id") != f.check_id))
    lines = [f"### {f.id} · {SEVERITY_TITLE.get(f.severity, f.severity)} · {f.check_id} · {f.title or check_title}",
             f"Check: {f.check_id} {check_title} ({dim})" + (f", also {', '.join(also_ids)}" if also_ids else "")
             + f" · Status: {STATUS_TEXT.get(f.status, f.status)} · Confidence: {f.confidence}",
             f"Where: {loc.where(f)}", ""]
    if f.quote:
        lines += [f"> \"{normalize(f.quote)}\"", ""]
    lines += [f"Problem: {f.problem}", ""]
    for a in also:
        if normalize(a.get("problem") or "") != normalize(f.problem):
            lines += [f"Also reported by {a.get('producer') or 'another producer'} under {a.get('check_id')} "
                      f"({a.get('title')}): {a.get('problem')}", ""]
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
    for f in kept:
        for cid in {a.get("check_id") for a in f.extra.get("also", [])} - {f.check_id}:
            found[cid] += 1
    for cid, info in checklist.items():
        entries = coverage.get(cid, [])
        # "skipped: waiting for ..." is provisional: a later run of the same check replaces it
        if any(c.status == "run" for c in entries):
            entries = [c for c in entries if not (c.status == "skipped" and
                                                  str(c.reason or "").lower().startswith("waiting"))]
        statuses = {c.status for c in entries}
        reasons = sorted({f"{c.producer + ': ' if c.producer else ''}{c.reason}" for c in entries
                          if c.reason and c.status != "run"})
        if not entries and found.get(cid):
            status, detail = "run", f"{found[cid]} findings; the producer recorded no coverage entry"
        elif not entries:
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
    _assign_keys(findings)
    dropped = [f for f in findings if f.status == "dropped" and not _refuted(f)]
    refuted = [f for f in findings if _refuted(f)]
    kept = _dedupe([f for f in findings if f.status != "dropped" and not _refuted(f)], pm)
    kept, consolidation_notes = _consolidate(kept, work)
    warnings.extend(n for n in consolidation_notes if "does not have" in n)
    min_rank = SEVERITY_RANK.get(settings.min_severity, 3)
    below = [f for f in kept if SEVERITY_RANK.get(f.severity, 9) > min_rank]
    kept = [f for f in kept if SEVERITY_RANK.get(f.severity, 9) <= min_rank]
    kept.sort(key=lambda f: (SEVERITY_RANK.get(f.severity, 9), loc.position(f), f.check_id))
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
    top, chosen = _chosen_top(kept, work, warnings)
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
    if not top:
        top = _top_issues(kept)
    if top:
        md += ["Top issues, the ones that most threaten the paper's conclusions:" if chosen else
               "Top issues, by severity, then certainty, then how many dimensions found them:", ""]
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
        index_rows = sorted(kept, key=lambda f: (loc.position(f), SEVERITY_RANK.get(f.severity, 9)))
        md += _md_table(["Finding", "Where", "Check", "Severity", "Problem"],
                        [[f.id, loc.where(f),
                          " + ".join(dict.fromkeys([f.check_id] + [a["check_id"] for a in f.extra.get("also", [])])),
                          SEVERITY_TITLE[f.severity], _cell(f.problem, 160)] for f in index_rows])
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
        cards = cards.get("cards") or []
    web_rows = {}
    for wpath in sorted((work / "references").glob("web_checks*.json")) if (work / "references").exists() else []:
        data = _load_json(wpath)
        for row in data if isinstance(data, list) else []:
            if isinstance(row, dict) and row.get("ref"):
                web_rows[row["ref"]] = row
    if cards:
        appendices["references"] = cards
        if web_rows:
            appendices["reference_web_checks"] = list(web_rows.values())
        md += ["## Appendix: references", "",
               "One evidence card per reference. Verified means two independent databases agree. "
               "Not found in databases is not the same as non-existent: the web check and a second review "
               f"decide that. The full cards, with every query made, are in {OUTPUT_FINDINGS} and "
               "paper-check-work/references/cards.json.", ""]
        rows = []
        for c in cards:
            matched = c.get("matched") if isinstance(c.get("matched"), dict) else {}
            closest = c.get("closest") if isinstance(c.get("closest"), dict) else {}
            record = matched or closest.get("record") or {}
            label = record.get("title") or ""
            if record and not matched:
                label = f"closest: {label}"
            if record.get("doi"):
                label += f" (doi:{record['doi']})"
            verdict = str(c.get("verdict") or "").replace("_", " ")
            web = web_rows.get(c.get("ref"))
            if web:
                verdict += f"; web check: {web.get('outcome')}"
                if web.get("dedicated_page"):
                    verdict += f" ({web['dedicated_page']})"
            elif c.get("needs_web_check"):
                verdict += "; web check not done"
            dbs = c.get("agreeing_databases") or c.get("databases_reached") or []
            rows.append([f"{c.get('ref')} {c.get('key') or ''}".strip(), _cell(c.get("raw"), 100), verdict,
                         _cell(label, 90), ", ".join(dbs)])
        md += _md_table(["Ref", "Reference", "Verdict", "Matched record", "Databases agreeing"], rows)
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
        d["key"] = f.extra.get("key")
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
    for note in consolidation_notes:
        print(note)
    for name, err in unreadable:
        print(f"WARNING: {name} could not be read: {err}")
    return 0
