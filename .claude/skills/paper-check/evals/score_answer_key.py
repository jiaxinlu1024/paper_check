"""Score a paper-check run against a test paper's answer key (expected.yaml).

Usage:
    python score_answer_key.py FINDINGS_JSON EXPECTED_YAML [--json]

FINDINGS_JSON is the paper-check-findings.json a run wrote. A planted item counts
as found when a kept finding's quote, a related quote or an evidence quote overlaps
the item's quote (case and whitespace insensitive), or, for items keyed to a
reference, when a finding quotes that reference's entry or names its key. The
check IDs are reported but not required to match, because one problem can be
caught under a neighbouring check.

A negative is a correct passage. It counts as flagged when a finding's quote
contains it, lies inside it, or shares at least 25 characters with it; a shared
short phrase from another place, such as a caption with the same words, does
not count. When the negative lists `wrong_if` checks, only findings under those
checks are false positives, and other findings that quote the passage are
listed as "also quoted" (they raise different problems). Each flag shows its
severity and status: a Critical or Major finding that is confirmed or likely is
a hard false positive, anything else a soft one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


def _squeeze(text: str) -> str:
    text = (text or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"(?<=[a-z])-\s*(?=[a-z])", "", text)
    return re.sub(r"[\s ]+", "", text)


def _overlaps(a: str, b: str) -> bool:
    a, b = _squeeze(a), _squeeze(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    # A long shared piece counts: at least 25 characters or most of the shorter text.
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    need = min(25, max(8, int(len(short) * 0.6)))
    return any(short[i:i + need] in long_ for i in range(0, max(1, len(short) - need + 1), 3))


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


def _texts(f: dict) -> list:
    out = [f.get("quote") or ""]
    out += [(q.get("quote") if isinstance(q, dict) else str(q)) or "" for q in f.get("related_quotes", [])]
    out += [e.get("text") or "" for e in f.get("evidence", []) if e.get("type") == "quote"]
    return [t for t in out if t]


def score(findings_path: Path, expected_path: Path) -> dict:
    data = json.loads(findings_path.read_text(encoding="utf-8"))
    findings = data.get("findings", [])
    key = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
    refs = {c.get("key"): c for c in data.get("appendices", {}).get("references", []) if isinstance(c, dict)}
    rows = []
    for item in key.get("planted", []):
        hits = []
        for f in findings:
            texts = _texts(f)
            blob = json.dumps(f, ensure_ascii=False).lower()
            ok = False
            if item.get("quote"):
                ok = any(_overlaps(item["quote"], t) for t in texts)
            if not ok and item.get("related"):
                ok = any(_overlaps(item["related"], t) for t in texts)
            if not ok and item.get("key"):
                raw = (refs.get(item["key"]) or {}).get("raw") or ""
                ok = item["key"].lower() in blob or (raw and any(_overlaps(raw, t) for t in texts))
            if not ok and item.get("note_contains"):
                ok = any(_overlaps(item["note_contains"], t) for t in texts) or item["note_contains"].lower() in blob
            if not ok and item.get("table") and item.get("checks"):
                ok = f.get("check_id") in item["checks"] and ("table" in blob)
            if not ok and item.get("metadata") and f.get("check_id") in (item.get("checks") or []):
                # Metadata problems have no quote: match the metadata key or its value.
                for mkey, mval in item["metadata"].items():
                    leaf = mkey.split(".")[-1] if not mkey.split(".")[-1].isdigit() else mkey.split(".")[0]
                    if str(mval).lower() in blob or leaf.lower() in blob:
                        ok = True
                        break
            if ok:
                hits.append(f"{f.get('id')} {f.get('check_id')} {f.get('severity')}")
        rows.append({"id": item["id"], "checks": item.get("checks"), "found": bool(hits), "by": hits,
                     "truth": item.get("truth")})
    negatives = []
    for neg in key.get("negatives", []):
        flagged, also, hard = [], [], 0
        if neg.get("quote"):
            wrong_if = set(neg.get("wrong_if") or [])
            for f in findings:
                if not _contains_or_long(neg["quote"], f.get("quote") or ""):
                    continue
                if wrong_if and f.get("check_id") not in wrong_if:
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
                             if f.get("check_id", "").startswith(("NUM", "FIG")) and _flags_cell(f)]
            flagged = [_label(f) for f in cell_findings]
            hard = sum(_hard(f) for f in cell_findings)
        negatives.append({"negative": neg.get("quote") or neg.get("cell"), "flagged_by": flagged,
                          "hard": hard, "also_quoted_by": also})
    found = sum(r["found"] for r in rows)
    return {"planted_found": found, "planted_total": len(rows),
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
    print(f"Planted problems found: {result['planted_found']} of {result['planted_total']}; "
          f"negatives flagged: {result['negatives_flagged']} of {result['negatives_total']} "
          f"({result['negatives_hard']} by a Critical or Major finding); "
          f"findings in the report: {result['findings_total']}")
    for r in result["items"]:
        mark = "found " if r["found"] else "MISSED"
        print(f"  {mark} {r['id']:4s} {','.join(r['checks'] or []):18s} {'; '.join(r['by'][:3])}")
    for n in result["negatives"]:
        if n["flagged_by"]:
            kind = "FALSE POSITIVE" if n["hard"] else "soft flag"
            print(f"  {kind} on negative {n['negative']!r}: {', '.join(n['flagged_by'])}")
        if n["also_quoted_by"]:
            print(f"  also quoted (other problems) {n['negative']!r}: {', '.join(n['also_quoted_by'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
