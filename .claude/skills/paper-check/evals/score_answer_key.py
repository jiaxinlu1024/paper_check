"""Score a paper-check run against a test paper's answer key (expected.yaml).

Usage:
    python score_answer_key.py FINDINGS_JSON EXPECTED_YAML [--json]

FINDINGS_JSON is the paper-check-findings.json a run wrote. A planted item counts as
found when one kept finding is both at the item's place and about the item's problem.

Place: the finding's quote, a related quote or an evidence quote overlaps the item's
quote or related quote (case and whitespace insensitive; a fragment of the item's quote
must be at least 15 characters long); or the finding quotes or names the item's
reference entry (`key`); or it contains the item's note text (`note_contains`), table
cell (`cell`), one of its `mentions` (such as a file name), or a metadata value.

Problem: one of the finding's checks, its own or one merged into it, is among the item's
`checks`; or its title, problem or fix uses one of the item's `about` words. When the
item sets `about_required`, only the `about` words count, because a finding under the
same check at the same place can be about something else.

A finding at the place but about another problem is listed as "near": a reader can judge
it, and it does not count. Where the key gives a severity, the severities of the
matching findings are reported next to it, and where it gives a PDF anchor (page and line),
whether the report's location is on that page within one line.

A negative is a correct passage. It counts as flagged when a finding's quote contains
it, lies inside it, or shares at least 25 characters with it; a shared short phrase from
another place, such as a caption with the same words, does not count. When the negative
lists `wrong_if` checks, only findings under those checks (their own or merged ones) are
false positives, and other findings that quote the passage are listed as "also quoted"
(they raise different problems). A Critical or Major finding that is confirmed or likely
is a hard false positive, anything else a soft one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

SEVERITIES = ["suggestion", "minor", "major", "critical"]
MIN_FRAGMENT = 15


def _squeeze(text: str) -> str:
    text = (text or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("−", "-").replace("–", "-")
    text = re.sub(r"(?<=[a-z])-\s*(?=[a-z])", "", text)
    return re.sub(r"[\s ]+", "", text)


def _overlaps(item_text: str, found: str) -> bool:
    """The finding's text covers the item's text, or a long piece of it."""
    a, b = _squeeze(item_text), _squeeze(found)
    if not a or not b:
        return False
    if a in b:
        return True
    if b in a:
        return len(b) >= min(MIN_FRAGMENT, len(a))
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    need = min(25, max(MIN_FRAGMENT, int(len(short) * 0.6)))
    if len(short) < need:
        return False
    return any(short[i:i + need] in long_ for i in range(0, len(short) - need + 1, 3))


def _contains_or_long(a: str, b: str) -> bool:
    """Stricter overlap for negatives: containment either way, or a shared piece of 25 characters."""
    a, b = _squeeze(a), _squeeze(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 25 and any(short[i:i + 25] in long_ for i in range(0, len(short) - 24))


def _hard(f: dict) -> bool:
    return f.get("severity") in ("critical", "major") and f.get("status") in ("confirmed", "likely")


def _label(f: dict) -> str:
    return f"{f.get('id')} {f.get('check_id')} {f.get('severity')} {f.get('status')}"


def _also(f: dict) -> list:
    return [a for a in (f.get("extra") or {}).get("also", []) if isinstance(a, dict)]


def _checks(f: dict) -> set:
    """The finding's own check and the checks of findings merged into it."""
    return {c for c in [f.get("check_id")] + [a.get("check_id") for a in _also(f)] if c}


def _texts(f: dict) -> list:
    out = [f.get("quote") or ""]
    out += [(q.get("quote") if isinstance(q, dict) else str(q)) or "" for q in f.get("related_quotes", [])]
    out += [e.get("text") or "" for e in f.get("evidence", []) if e.get("type") == "quote"]
    return [t for t in out if t]


def _words(f: dict) -> str:
    """What the finding says: title, problem and fix, with those of findings merged into it."""
    fix = f.get("fix")
    parts = [f.get("title"), f.get("problem"), fix.get("detail") if isinstance(fix, dict) else fix]
    for a in _also(f):
        parts += [a.get("title"), a.get("problem")]
    return " ".join(p for p in parts if isinstance(p, str)).lower()


def _at_place(item: dict, f: dict, refs: dict) -> bool:
    texts = _texts(f)
    blob = json.dumps(f, ensure_ascii=False).lower()
    if item.get("quote") and any(_overlaps(item["quote"], t) for t in texts):
        return True
    if item.get("related") and any(_overlaps(item["related"], t) for t in texts):
        return True
    if item.get("key"):
        key = item["key"].lower()
        raw = (refs.get(item["key"]) or {}).get("raw") or ""
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", blob):
            return True
        if raw and any(_overlaps(raw, t) for t in texts):
            return True
    if item.get("note_contains"):
        note = item["note_contains"]
        if any(_overlaps(note, t) for t in texts) or note.lower() in blob:
            return True
    if item.get("cell"):
        cell = _squeeze(item["cell"])
        if _squeeze((f.get("extra") or {}).get("cell") or "") == cell or cell in _squeeze(blob):
            return True
    if any(m.lower() in blob for m in item.get("mentions") or []):
        return True
    for mkey, mval in (item.get("metadata") or {}).items():
        # A flag such as `true` would match any finding; such items name their place with `mentions`.
        if not isinstance(mval, bool) and len(str(mval)) >= 4 and str(mval).lower() in blob:
            return True
    return False


def _about(item: dict, f: dict) -> bool:
    words = _words(f)
    if any(w.lower() in words for w in item.get("about") or []):
        return True
    if item.get("about_required"):
        return False
    return bool(_checks(f) & set(item.get("checks") or []))


def score(findings_path: Path, expected_path: Path) -> dict:
    data = json.loads(findings_path.read_text(encoding="utf-8"))
    findings = data.get("findings", [])
    key = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
    refs = {c.get("key"): c for c in data.get("appendices", {}).get("references", []) if isinstance(c, dict)}
    rows = []
    for item in key.get("planted", []):
        hits, near = [], []
        for f in findings:
            if not _at_place(item, f, refs):
                continue
            (hits if _about(item, f) else near).append(f)
        row = {"id": item["id"], "checks": item.get("checks"), "found": bool(hits),
               "by": [f"{f.get('id')} {f.get('check_id')} {f.get('severity')}" for f in hits],
               "near": [f"{f.get('id')} {f.get('check_id')} {f.get('severity')}" for f in near],
               "truth": item.get("truth"), "origin": item.get("origin", "planted")}
        if item.get("anchor") and hits:
            # The report's location for the item, against the page and line where its quote starts.
            want = (item["anchor"]["page"], item["anchor"]["page_line"])
            given = []
            for f in hits:
                # Every place the finding names, not only the first.
                for pg, ln in re.findall(r"p\. (\d+), line (\d+)", f.get("where") or ""):
                    given.append((int(pg), int(ln)))
            best = min(given, key=lambda g: (g[0] != want[0], abs(g[1] - want[1]))) if given else None
            row["anchor"] = {"expected": list(want), "given": list(best) if best else None,
                             "within_one": bool(best) and best[0] == want[0] and abs(best[1] - want[1]) <= 1}
        if item.get("severity") and hits:
            want = SEVERITIES.index(item["severity"])
            best = min(hits, key=lambda f: abs(SEVERITIES.index(f.get("severity", "minor")) - want))
            row["severity"] = {"expected": item["severity"], "given": best.get("severity"),
                               "within_one": abs(SEVERITIES.index(best.get("severity", "minor")) - want) <= 1}
        rows.append(row)
    negatives = []
    for neg in key.get("negatives", []):
        flagged, also, hard = [], [], 0
        if neg.get("quote"):
            wrong_if = set(neg.get("wrong_if") or [])
            for f in findings:
                if not _contains_or_long(neg["quote"], f.get("quote") or ""):
                    continue
                if wrong_if and not (_checks(f) & wrong_if):
                    also.append(_label(f))
                    continue
                flagged.append(_label(f))
                hard += _hard(f)
        elif neg.get("cell"):
            # A table finding names its cell in extra.cell, or quotes the row up to the flagged cell.
            def _flags_cell(f):
                cell = (f.get("extra") or {}).get("cell")
                if cell is not None:
                    return _squeeze(cell) == _squeeze(neg["cell"])
                return _squeeze(f.get("quote") or "").endswith(_squeeze(neg["cell"]))
            cell_findings = [f for f in findings
                             if any(c.startswith(("NUM", "FIG")) for c in _checks(f)) and _flags_cell(f)]
            flagged = [_label(f) for f in cell_findings]
            hard = sum(_hard(f) for f in cell_findings)
        negatives.append({"negative": neg.get("quote") or neg.get("cell"), "flagged_by": flagged,
                          "hard": hard, "also_quoted_by": also})
    found = sum(r["found"] for r in rows)
    graded = [r["severity"] for r in rows if r.get("severity")]
    anchored = [r["anchor"] for r in rows if r.get("anchor")]
    return {"planted_found": found, "planted_total": len(rows),
            "planted_near_only": sum(1 for r in rows if not r["found"] and r["near"]),
            "severity_within_one": sum(g["within_one"] for g in graded), "severity_graded": len(graded),
            "anchors_within_one": sum(a["within_one"] for a in anchored), "anchors_graded": len(anchored),
            "negatives_flagged": sum(bool(n["flagged_by"]) for n in negatives), "negatives_total": len(negatives),
            "negatives_hard": sum(bool(n["hard"]) for n in negatives),
            "items": rows, "negatives": negatives, "findings_total": len(findings)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("findings")
    ap.add_argument("expected")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = score(Path(args.findings), Path(args.expected))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print(f"Planted problems found: {result['planted_found']} of {result['planted_total']} "
          f"({result['planted_near_only']} more only near); "
          f"severity within one level: {result['severity_within_one']} of {result['severity_graded']}; "
          + (f"locations within one line: {result['anchors_within_one']} of {result['anchors_graded']}; "
             if result["anchors_graded"] else "") +
          f"negatives flagged: {result['negatives_flagged']} of {result['negatives_total']} "
          f"({result['negatives_hard']} by a Critical or Major finding); "
          f"findings in the report: {result['findings_total']}")
    for r in result["items"]:
        mark = "found " if r["found"] else ("near  " if r["near"] else "MISSED")
        sev = r.get("severity")
        sev_note = f" [key {sev['expected']}, given {sev['given']}]" if sev else ""
        anc = r.get("anchor")
        if anc and not anc["within_one"]:
            sev_note += f" [line: key {anc['expected']}, given {anc['given']}]"
        shown = r["by"][:3] if r["found"] else r["near"][:3]
        print(f"  {mark} {r['id']:4s} {','.join(r['checks'] or []):18s} {'; '.join(shown)}{sev_note}")
    for n in result["negatives"]:
        if n["flagged_by"]:
            kind = "FALSE POSITIVE" if n["hard"] else "soft flag"
            print(f"  {kind} on negative {n['negative']!r}: {', '.join(n['flagged_by'])}")
        if n["also_quoted_by"]:
            print(f"  also quoted (other problems) {n['negative']!r}: {', '.join(n['also_quoted_by'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
