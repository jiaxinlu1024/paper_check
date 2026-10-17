"""Behavioral economics checks with a script part: BEH-15 classic attributions.

BEH-15 compares every citing sentence with the verified list of common
misattributions in references/guidelines/misattributions.yaml. A sentence is a
lead when it uses an entry's terms and cites one of the sources the entry lists
as a common misattribution, and does not also cite the original. A lead is
reported as likely: a paper can cite a later source for a refinement or a review
for an overview, so the citation judge and the refuter make the final call.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from ..model import Evidence, Fix
from . import register

LIST_PATH = Path(__file__).resolve().parents[3] / "references" / "guidelines" / "misattributions.yaml"
_STOP = {"the", "of", "a", "an", "and", "in", "on", "for", "to", "as", "by", "is", "are", "with", "about", "than"}
_SOURCE = re.compile(r"([A-Z][A-Za-z'’\-]+)(?:,? (?:and|&) [A-Z][A-Za-z'’\-]+)?(?: et al\.?)?,? \(?(\d{4})\)?")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[\s ]+", " ", text.replace("’", "'").replace("-", " "))


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9λβδ.]+", _fold(text)) if w not in _STOP and len(w) > 1}


def _term_hit(term: str, sentence: str) -> bool:
    """An exact term, or every content word of a multi-word term, in the sentence."""
    folded = _fold(sentence)
    if _fold(term) in folded:
        return True
    words = _words(term)
    return len(words) >= 2 and words <= _words(sentence)


def _family(name: str) -> str:
    return re.sub(r"[^a-z]", "", _fold(name.split(",")[0] if "," in name else name.split()[-1]))


def _ref_matches(ref, item: dict) -> bool:
    fields = ref.fields or {}
    doi = str(fields.get("doi") or "").lower().strip()
    if item.get("doi") and doi and doi == str(item["doi"]).lower():
        return True
    if item.get("doi") and doi:
        return False  # both have DOIs and they differ
    authors = fields.get("authors") or []
    first = authors[0] if authors else {}
    fam = re.sub(r"[^a-z]", "", _fold(first.get("family") or first.get("literal") or "")) if isinstance(first, dict) else ""
    year = str(fields.get("year") or "")
    for m in _SOURCE.finditer(item.get("source") or ""):
        if fam and re.sub(r"[^a-z]", "", _fold(m.group(1))) == fam and m.group(2) == year[:4]:
            return True
    return False


def _is_original(ref, original: dict) -> bool:
    fields = ref.fields or {}
    doi = str(fields.get("doi") or "").lower().strip()
    if doi and original.get("doi"):
        return doi == str(original["doi"]).lower()
    authors = fields.get("authors") or []
    first = authors[0] if authors else {}
    fam = re.sub(r"[^a-z]", "", _fold(first.get("family") or "")) if isinstance(first, dict) else ""
    orig_first = (original.get("authors") or [""])[0]
    return bool(fam) and fam == _family(orig_first) and str(fields.get("year") or "")[:4] == str(original.get("year"))


def _load_list() -> Optional[dict]:
    if not LIST_PATH.exists():
        return None
    import yaml
    return yaml.safe_load(LIST_PATH.read_text(encoding="utf-8"))


def _replacement(printed: Optional[str], original: dict) -> Optional[str]:
    """The original source in the same citation form as the printed one."""
    if not printed:
        return None
    fams = [a.split(",")[0].strip() for a in original.get("authors") or []]
    if not fams or not original.get("year"):
        return None
    names = fams[0] if len(fams) == 1 else f"{fams[0]} and {fams[1]}" if len(fams) == 2 else f"{fams[0]} et al."
    if re.fullmatch(r"\(.+,\s*\d{4}[a-z]?\)", printed.strip()):
        return f"({names}, {original['year']})"
    if re.fullmatch(r".+\(\d{4}[a-z]?\)", printed.strip()):
        return f"{names} ({original['year']})"
    return None


def _cite_name(original: dict) -> str:
    fams = [a.split(",")[0].strip() for a in original.get("authors") or []]
    name = fams[0] if len(fams) == 1 else f"{fams[0]} and {fams[1]}" if len(fams) == 2 else f"{fams[0]} et al."
    return f"{name} ({original.get('year')})"


@register("BEH-15")
def classic_attributions(pm, ctx):
    data = _load_list()
    if not data or not data.get("entries"):
        ctx.skip("BEH-15", "the misattribution list references/guidelines/misattributions.yaml is missing")
        return
    entries = data["entries"]
    checked = 0
    for block in pm.blocks:
        if block.kind in ("reference", "heading", "table", "equation") or not block.citations:
            continue
        for sent in block.sentences or []:
            cites = [c for c in block.citations if sent.start <= c.start < sent.end]
            if not cites:
                continue
            checked += 1
            text = block.text[sent.start:sent.end]
            refs = [pm.reference(k) for c in cites for k in c.keys]
            refs = [r for r in refs if r is not None]
            for entry in entries:
                hits = [t for t in entry.get("terms") or [] if _term_hit(t, text)]
                if not hits:
                    continue
                original = entry.get("original") or {}
                if any(_is_original(r, original) for r in refs):
                    continue
                for ref in refs:
                    wrong = next((item for item in entry.get("often_miscited_as") or [] if _ref_matches(ref, item)), None)
                    if wrong is None:
                        continue
                    span = next((c for c in cites if ref.key in c.keys or ref.id in c.keys), None)
                    printed = block.text[span.start:span.end] if span else None
                    replacement = _replacement(printed, original) if span and len(span.keys) == 1 else None
                    evidence = [Evidence("note", text=f"List entry {entry['id']}: {entry.get('finding')}"),
                                Evidence("note", text=f"Rule: {entry.get('rule')}")]
                    for ev in (entry.get("evidence") or [])[:3]:
                        evidence.append(Evidence("lookup_record", text=f'"{ev.get("quote")}"', url=ev.get("url"),
                                                 data={"database": ev.get("kind") or "source", "record": entry["id"]}))
                    status = "likely" if entry.get("status") == "verified" else "needs_human"
                    yield ctx.finding(
                        "BEH-15", "Classic finding attributed to the wrong source", "major",
                        problem=(f"This sentence attributes what the verified list describes as \"{entry.get('finding')}\" "
                                 f"to {ref.raw[:80]}. {wrong.get('why')} The original is {_cite_name(original)}."),
                        block=block, quote=text.strip(), evidence=evidence,
                        trajectory=[f"Compared {len(entries)} entries of the misattribution list with the citing sentence.",
                                    f"Matched the entry's terms: {', '.join(hits[:3])}.",
                                    f"The sentence cites {ref.key or ref.id}, which the entry lists as a common "
                                    f"misattribution ({wrong.get('code')}), and does not cite the original."],
                        fix=Fix("replace" if replacement else "investigate",
                                original=printed if replacement else None,
                                replacement=replacement,
                                detail=f"Cite {_cite_name(original)}, {original.get('title')}, "
                                       f"{original.get('container')} {original.get('volume')}"
                                       f"({original.get('issue')}): {original.get('pages')}, doi:{original.get('doi')}, "
                                       "for this claim, after checking it says so; keep the current citation only "
                                       "if it supports a different part of the sentence.",
                                resolved_when=f"The claim cites {_cite_name(original)}, or the citation judge confirms "
                                              "the current source supports it."),
                        confidence="medium", status=status, script="checks.behavioral",
                        extra={"entry": entry["id"], "ref": ref.id, "failure_code": wrong.get("code"),
                               "original_doi": original.get("doi")})
    ctx.note("BEH-15", f"script part: compared {checked} citing sentences with {len(entries)} entries of the "
                       "verified misattribution list; the reading agent covers the rest")
