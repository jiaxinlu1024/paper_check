"""`pc.py cite-prepare WORK`: what the citation judges need, prepared by script (DESIGN section 7).

1. Propositions. Every sentence that carries a citation gives one record per citation group (one
   \\cite command, or one bracket of citations) in citations/propositions.jsonl, with the sentence,
   the sentence before it, the section, the citation as printed, the reference ids, the clause the
   citation most likely supports, and a claim type guessed from cue words: topic, finding,
   direction, method, number, definition or origin. by_ref.json groups the records by reference.
2. Full text. Each cited reference goes through the legal cascade in fulltext.py; the text is saved
   with [[page N]] markers in citations/sources/<ref>.txt and its provenance in <ref>.json.
   References with nothing get "cannot verify: no full text".
3. Status. A printed summary and citations/status.json: what was read, which version, and which
   references still need a PDF.

Re-running is cheap: full texts are reused, a new or changed PDF in the sources folder replaces
what was fetched before, and misses are retried after 24 hours. Offline runs use only the sources
folder and the cache.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Optional

from .. import __version__
from ..config import USER_CONFIG, Credentials, PaperSettings
from ..model import PaperMap
from ..textutil import extract_numbers
from .fulltext import NEGATIVE_TTL, Cascade, Fetcher, match_sources

CLAIM_TYPES = ("origin", "number", "definition", "direction", "finding", "method", "topic")
FLOW_KINDS = {"paragraph", "list_item", "abstract"}
NARRATIVE_COMMANDS = {"citet", "citet*", "Citet", "Citet*", "textcite", "Textcite", "citeauthor", "citeauthor*",
                      "Citeauthor", "citealt", "citealt*", "Citealt", "narrative", "textual", "inline"}
PARENTHETICAL_COMMANDS = {"citep", "citep*", "Citep", "Citep*", "parencite", "Parencite", "autocite", "Autocite",
                          "cite", "Cite", "citealp", "citealp*", "Citealp", "footcite", "supercite", "citeyearpar",
                          "parenthetical"}
_CUES = {
    "origin": re.compile(
        r"\b(?:first|originally)\s+(?:\w+ly\s+)?\w+(?:ed|en|wn)\b|\bthe\s+first\s+to\b|\boriginat\w*|\bcoined\b|"
        r"\bpioneer\w*|\bseminal\b|\bintroduced\s+(?:the\s+)?(?:concept|term|notion|idea|model)\b|"
        r"\b(?:dates?|goes|went|traced?)\s+back\b", re.I),
    "definition": re.compile(
        r"\bdefined\s+as\b|\bdefines?\b|\bdefinition\b|\brefers?\s+to\b|\bis\s+known\s+as\b|\btermed\b|"
        r"\bso-called\b|\bthe\s+tendency\s+(?:to|of|for)\b|\bdenot\w*|\bis\s+called\b|\bwe\s+call\b", re.I),
    "direction": re.compile(
        r"\b(?:increas\w*|decreas\w*|rais(?:e|es|ed|ing)|reduc\w*|lower(?:s|ed|ing)?|higher|boost\w*|improv\w*|"
        r"worsen\w*|declin\w*|ris(?:e|es|ing)|rose|f[ae]ll(?:s|ing)?|drop\w*|more\s+likely|less\s+likely|"
        r"positive(?:ly)?|negative(?:ly)?|caus(?:e|es|ed|ing)|leads?\s+to|led\s+to|effects?\s+(?:of|on)|"
        r"impacts?\s+(?:of|on)|affect\w*|harm\w*|benefit\w*|sharply|substantially|crowd\w*\s+out)\b", re.I),
    "finding": re.compile(
        r"\b(?:show(?:s|n|ed)?|finds?|findings?|found|document(?:s|ed)?|demonstrat\w*|report(?:s|ed)?|evidence|"
        r"establish\w*|reveal\w*|confirm\w*|suggest(?:s|ed)?|conclud\w*|observ\w*|estimat\w*|results?|"
        r"identif\w*|overestimat\w*|underestimat\w*|indicat\w*)\b", re.I),
    "method": re.compile(
        r"\b(?:using|uses?|employ\w*|methods?|methodolog\w*|approach\w*|design(?:s|ed)?|experiment\w*|survey\w*|"
        r"panel|data(?:set|sets)?|regressions?|structural|instrument\w*|difference-in-differences|randomi[sz]\w*|"
        r"RCTs?|sampl\w*|models?|modell?ed|modell?ing|framework|elicit\w*|measur\w*|calibrat\w*|simulat\w*|"
        r"administrative|laboratory|lab)\b", re.I),
    "topic": re.compile(
        r"\b(?:stud(?:y|ies|ied|ying)|examin\w*|investigat\w*|analy[sz]\w*|explor\w*|literature|research|"
        r"work\s+on|contribut\w*|address\w*|focus\w*|consider\w*|discuss\w*|explanations?|review\w*|topic)\b", re.I),
}


# ================================================================ propositions
def _is_narrative(citation, rendered: str) -> bool:
    if citation.command in NARRATIVE_COMMANDS:
        return True
    if citation.command in PARENTHETICAL_COMMANDS:
        return False
    return not rendered.lstrip().startswith(("(", "["))


def _numbers(text: str) -> list:
    """Numbers that make a claim quantitative: not years, plan names such as 401(k), or labels like COVID-19."""
    t = re.sub(r"\b\d{3}\s?\([a-z]\)", " ", text)
    t = re.sub(r"\b[A-Za-z]+-\d+\b", " ", t)
    out = []
    for n in extract_numbers(t):
        if not n["unit"] and n["decimals"] == 0 and 1900 <= abs(n["value"]) <= 2099:
            continue
        out.append(n["raw"].strip())
    return out


def classify_claim(text: str) -> tuple:
    """(primary type, all types, cues) from cue words. A guess for the judge to confirm."""
    cues = OrderedDict()
    numbers = _numbers(text)
    for kind in CLAIM_TYPES:
        if kind == "number":
            if numbers:
                cues["number"] = numbers[:5]
            continue
        found = [m.group(0) for m in _CUES[kind].finditer(text)]
        if found:
            cues[kind] = list(dict.fromkeys(f.lower() for f in found))[:5]
    types = [k for k in CLAIM_TYPES if k in cues]
    return (types[0] if types else "topic"), (types or ["topic"]), dict(cues)


def _units(block) -> list:
    """(sentence id, start, end) for each sentence; lines when the block has no sentences."""
    if block.sentences:
        return [(s.id, s.start, s.end) for s in block.sentences]
    out, pos = [], 0
    for line in block.text.split("\n"):
        if line.strip():
            out.append((None, pos, pos + len(line)))
        pos += len(line) + 1
    return out


def _blank_spans(text: str, start: int, end: int, spans: list) -> str:
    chars = list(text[start:end])
    for s, e in spans:
        for k in range(max(s, start), min(e, end)):
            chars[k - start] = " "
    return "".join(chars)


def extract_propositions(pm: PaperMap) -> list:
    """One record per citation group in each citing sentence, in reading order."""
    props, last_flow, counter = [], {}, 0
    for block in pm.blocks:
        if block.kind == "reference":
            continue
        units = _units(block)
        citations = sorted(block.citations, key=lambda c: c.start)
        if citations:
            placed = set()
            for ui, (sid, s0, s1) in enumerate(units):
                group = [c for c in citations if s0 <= c.start < s1]
                if not group:
                    continue
                placed.update(id(c) for c in group)
                sentence = block.text[s0:s1].strip()
                if ui > 0:
                    psid, p0, p1 = units[ui - 1]
                    previous, previous_id = block.text[p0:p1].strip(), psid
                elif block.kind in FLOW_KINDS:
                    previous_id, previous = last_flow.get(tuple(block.section), (None, None))
                else:
                    previous_id, previous = None, None
                skip = [(c.start, c.end) for c in citations] + [(x.start, x.end) for x in block.crossrefs]
                for gi, c in enumerate(group):
                    counter += 1
                    rendered = block.text[c.start:c.end]
                    narrative = _is_narrative(c, rendered)
                    if len(group) == 1:
                        a, b, basis = s0, s1, "whole sentence"
                    elif narrative:
                        a, b = c.start, (group[gi + 1].start if gi + 1 < len(group) else s1)
                        basis = "from this citation to the next one"
                    else:
                        a, b = (group[gi - 1].end if gi > 0 else s0), c.end
                        basis = "from the previous citation to this one"
                    claim = block.text[a:b].strip(" ,;:")
                    primary, types, cues = classify_claim(_blank_spans(block.text, a, b, skip))
                    ref_ids, unresolved = [], []
                    for key in c.keys:
                        ref = pm.reference(key)
                        (ref_ids if ref is not None else unresolved).append(ref.id if ref is not None else key)
                    props.append({
                        "id": f"c{counter:03d}", "block": block.id, "block_kind": block.kind,
                        "sentence_id": sid, "sentence": sentence,
                        "previous_sentence": previous, "previous_sentence_id": previous_id,
                        "section": list(block.section), "location": block.anchor.label(),
                        "citation": rendered, "citation_span": [c.start, c.end], "command": c.command,
                        "narrative": narrative, "keys": list(c.keys), "ref_ids": ref_ids,
                        "unresolved_keys": unresolved, "group": gi + 1, "groups_in_sentence": len(group),
                        "claim": claim, "claim_basis": basis, "claim_type": primary, "claim_types": types,
                        "cues": cues,
                    })
            missing = [c for c in citations if id(c) not in placed]
            for c in missing:  # a citation outside every sentence span: keep it, with the block as context
                counter += 1
                primary, types, cues = classify_claim(block.text)
                props.append({
                    "id": f"c{counter:03d}", "block": block.id, "block_kind": block.kind, "sentence_id": None,
                    "sentence": block.text.strip(), "previous_sentence": None, "previous_sentence_id": None,
                    "section": list(block.section), "location": block.anchor.label(),
                    "citation": block.text[c.start:c.end], "citation_span": [c.start, c.end], "command": c.command,
                    "narrative": _is_narrative(c, block.text[c.start:c.end]), "keys": list(c.keys),
                    "ref_ids": [pm.reference(k).id for k in c.keys if pm.reference(k) is not None],
                    "unresolved_keys": [k for k in c.keys if pm.reference(k) is None], "group": 1,
                    "groups_in_sentence": 1, "claim": block.text.strip(), "claim_basis": "whole block",
                    "claim_type": primary, "claim_types": types, "cues": cues})
        if block.kind in FLOW_KINDS and units:
            sid, s0, s1 = units[-1]
            last_flow[tuple(block.section)] = (sid, block.text[s0:s1].strip())
    return props


def group_by_ref(pm: PaperMap, props: list) -> dict:
    refs = OrderedDict()
    for r in pm.references:
        refs[r.id] = {"key": r.key, "reference": r.raw, "title": (r.fields or {}).get("title"),
                      "propositions": [], "sentences": [], "claim_types": {}}
    unresolved: dict = {}
    for p in props:
        for rid in p["ref_ids"]:
            entry = refs[rid]
            entry["propositions"].append(p["id"])
            if p["sentence_id"] and p["sentence_id"] not in entry["sentences"]:
                entry["sentences"].append(p["sentence_id"])
            entry["claim_types"][p["claim_type"]] = entry["claim_types"].get(p["claim_type"], 0) + 1
        for key in p["unresolved_keys"]:
            unresolved.setdefault(key, []).append(p["id"])
    return {
        "references": OrderedDict((rid, e) for rid, e in refs.items() if e["propositions"]),
        "unresolved_keys": unresolved,
        "uncited": [rid for rid, e in refs.items() if not e["propositions"]],
    }


# ================================================================ settings
def _settings(work: Path, pm: PaperMap, sources_arg: Optional[str]) -> dict:
    """Sources folder, paid_pdfs and network: --sources first, then the settings saved at ingest
    (WORK/settings.json), then paper-check.yaml beside the paper, then sources/ beside the paper."""
    paper_dir = Path(pm.source.get("paper_dir") or work.parent)
    try:
        for_work = getattr(PaperSettings, "for_work", None)
        ps = for_work(work) if for_work else PaperSettings.load(paper_dir)
    except (SystemExit, Exception):  # a broken settings file must not stop the citation step
        ps = PaperSettings()
    warnings = []
    chosen = sources_arg or ps.sources
    folder = None
    if chosen:
        path = Path(os.path.expanduser(str(chosen)))
        candidates = [path] if path.is_absolute() else [Path.cwd() / path, paper_dir / path]
        folder = next((c.resolve() for c in candidates if c.is_dir()), None)
        if folder is None:
            warnings.append(f"Sources folder not found: {chosen}")
    return {"paper_dir": str(paper_dir), "sources": str(folder) if folder else None,
            "paid_pdfs": bool(ps.paid_pdfs), "network": bool(ps.network), "warnings": warnings}


def _core_key(creds: Credentials) -> Optional[str]:
    key = getattr(creds, "core_api_key", None) or os.environ.get("CORE_API_KEY")
    if key:
        return key
    try:
        import yaml

        data = yaml.safe_load(USER_CONFIG.read_text(encoding="utf-8")) if USER_CONFIG.exists() else {}
        return (data or {}).get("core_api_key")
    except Exception:
        return None


# ================================================================ reuse
def _reusable(prev: Optional[dict], match: Optional[dict], offline: bool) -> bool:
    if not prev:
        return False
    if match:
        sm = prev.get("sources_match") or {}
        return (prev.get("source") == "sources" and sm.get("file") == match["file"]
                and sm.get("size") == match["size"] and sm.get("mtime") == match["mtime"])
    if prev.get("source") == "sources":
        return False  # the PDF left the sources folder
    if prev.get("status") == "full_text":
        return True
    if offline:
        return True
    if prev.get("offline") or prev.get("transient_failure"):
        return False  # a miss recorded offline, or after a rate limit or network error, is retried
    try:
        fetched = dt.datetime.fromisoformat(prev["fetched_at"]).timestamp()
    except (KeyError, ValueError):
        return False
    return time.time() - fetched < NEGATIVE_TTL


# ================================================================ main
def prepare(work: Path, sources: Optional[str] = None, offline: bool = False) -> int:
    work = Path(work)
    pm = PaperMap.load(work / "paper_map.json")
    out = work / "citations"
    (out / "sources").mkdir(parents=True, exist_ok=True)
    settings = _settings(work, pm, sources)
    offline = bool(offline or not settings["network"])

    props = extract_propositions(pm)
    with (out / "propositions.jsonl").open("w", encoding="utf-8") as fh:
        for p in props:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    by_ref = group_by_ref(pm, props)
    (out / "by_ref.json").write_text(json.dumps(by_ref, ensure_ascii=False, indent=1), encoding="utf-8")

    cited = [pm.reference(rid) for rid in by_ref["references"]]
    creds = Credentials.load()
    core_key = _core_key(creds)
    secrets = [s for s in (creds.openalex_api_key, creds.semantic_scholar_api_key, core_key) if s]
    fetcher = Fetcher(out / "cache", email=creds.contact_email, offline=offline, secrets=secrets)
    matched = match_sources(Path(settings["sources"]) if settings["sources"] else None, cited,
                            out / "cache" / "sources_index.json")
    cascade = Cascade(fetcher, out / "sources", email=creds.contact_email, openalex_key=creds.openalex_api_key,
                      s2_key=creds.semantic_scholar_api_key, core_key=core_key, paid_pdfs=settings["paid_pdfs"],
                      source_matches=matched["matches"], sources_folder=settings["sources"], offline=offline)

    results = OrderedDict()
    for ref in cited:
        meta_path = out / "sources" / f"{ref.id}.json"
        prev = None
        if meta_path.exists():
            try:
                prev = json.loads(meta_path.read_text(encoding="utf-8"))
            except ValueError:
                prev = None
        if _reusable(prev, matched["matches"].get(ref.id), offline) and (
                prev.get("status") == "not_found" or (out / "sources" / f"{ref.id}.txt").exists()):
            prev["reused"] = True
            results[ref.id] = prev
            continue
        try:
            results[ref.id] = cascade.run(ref)
        except Exception as exc:  # never let one reference stop the run
            results[ref.id] = {"ref": ref.id, "key": ref.key, "status": "not_found", "source": None,
                               "note": f"cannot verify: no full text (error: {type(exc).__name__}: {fetcher.scrub(str(exc))[:200]})"}

    status = build_status(pm, props, by_ref, results, matched, settings, cascade, creds, offline, fetcher)
    (out / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print_summary(status, work)
    return 0


def build_status(pm, props, by_ref, results, matched, settings, cascade, creds, offline, fetcher) -> dict:
    counts = Counter(r.get("status") for r in results.values())
    items, needs_pdf = [], []
    for rid, r in results.items():
        ref = pm.reference(rid)
        entry = by_ref["references"].get(rid, {})
        items.append({
            "ref": rid, "key": ref.key if ref else r.get("key"), "status": r.get("status"), "source": r.get("source"),
            "version": r.get("version"), "pages": r.get("pages"), "abstract_only": bool(r.get("abstract_only")),
            "url": r.get("url"), "fetched": r.get("fetched"), "note": r.get("note"),
            "file": f"citations/{r['file']}" if r.get("file") else None,
            "propositions": len(entry.get("propositions", [])), "warnings": r.get("warnings", []),
            "reused": bool(r.get("reused")),
        })
        if r.get("status") != "full_text":
            needs_pdf.append({"ref": rid, "key": ref.key if ref else None, "reference": ref.raw if ref else None,
                              "have": r.get("status"), "propositions": len(entry.get("propositions", []))})
    services = dict(cascade.service_notes)
    services.update({k: f"disabled for this run: {v}" for k, v in cascade.disabled.items()})
    if not cascade.core_key:
        services["core"] = "skipped: no CORE API key"
    services["openalex_content"] = "on (paid_pdfs: true)" if cascade.paid_pdfs else "off (paid_pdfs: false)"
    if offline:
        services["network"] = "offline: only the sources folder and the cache were used"
    claim_counts = Counter(p["claim_type"] for p in props)
    unresolved = sorted(by_ref["unresolved_keys"])
    full = counts.get("full_text", 0)
    if not results:
        readiness = {"state": "nothing_cited", "detail": "the paper cites no reference in its reference list"}
    elif full == 0:
        readiness = {"state": "no_full_text", "detail": "no full text for any cited work; judges can only support, "
                     "contradict or say cannot verify" + (" (offline)" if offline else "")}
    else:
        readiness = {"state": "partial" if full < len(results) else "ready",
                     "detail": f"full text for {full} of {len(results)} cited works"}
    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tool": f"paper-check {__version__}",
        "offline": offline,
        "settings": {"sources_folder": settings["sources"], "paid_pdfs": settings["paid_pdfs"],
                     "network": settings["network"]},
        "credentials": creds.summary() | {"core_api_key": bool(cascade.core_key)},
        "warnings": settings["warnings"],
        "propositions": {"total": len(props), "citing_sentences": len({(p["block"], p["sentence_id"]) for p in props}),
                         "by_claim_type": dict(claim_counts), "unresolved_keys": unresolved},
        "references": {"cited": len(results), "uncited": by_ref["uncited"], "full_text": full,
                       "abstract_only": counts.get("abstract_only", 0), "not_found": counts.get("not_found", 0),
                       "by_source": dict(Counter(r.get("source") for r in results.values() if r.get("source"))),
                       "by_version": dict(Counter(r.get("version") for r in results.values() if r.get("version")))},
        "sources_folder": {"path": matched.get("folder"), "exists": matched.get("exists"),
                           "pdfs": len(matched.get("pdfs", [])),
                           "matched": {rid: m["rel"] for rid, m in matched.get("matches", {}).items()},
                           "unmatched_pdfs": matched.get("unmatched_pdfs", []), "warnings": matched.get("warnings", [])},
        "items": items,
        "needs_pdf": needs_pdf,
        "services": services,
        "network_requests": fetcher.requests,
        "readiness": readiness,
        "outputs": {"propositions": "citations/propositions.jsonl", "by_ref": "citations/by_ref.json",
                    "sources": "citations/sources/", "status": "citations/status.json"},
    }


def print_summary(status: dict, work: Path) -> None:
    p, r = status["propositions"], status["references"]
    print(f"Citation support: {p['total']} propositions in {p['citing_sentences']} citing sentences, "
          f"citing {r['cited']} references.")
    if p["unresolved_keys"]:
        print(f"  Citation keys with no reference entry: {', '.join(p['unresolved_keys'])}")
    print(f"Full text: {r['full_text']} of {r['cited']}; abstract only: {r['abstract_only']}; nothing: {r['not_found']}."
          + ("  (offline)" if status["offline"] else ""))
    for item in status["items"]:
        where = item["source"] or "-"
        version = item["version"] or "-"
        pages = f"{item['pages']} pages" if item.get("pages") else ""
        tail = {"full_text": "", "abstract_only": "  abstract only: can support or contradict, never show absence"
                }.get(item["status"], f"  {item['note']}")
        print(f"  {item['ref']} {str(item['key'] or ''):18s} {item['status']:13s} {where:18s} {version:9s} {pages:10s}"
              f"{' (reused)' if item['reused'] else ''}{tail}")
        for w in item["warnings"][:2]:
            print(f"      warning: {w}")
    sf = status["sources_folder"]
    if sf["path"]:
        print(f"Sources folder {sf['path']}: {sf['pdfs']} PDFs, {len(sf['matched'])} matched.")
        for u in sf["unmatched_pdfs"]:
            print(f"  not matched to any reference: {u['file']} ({u.get('title_guess') or 'no title found'})")
        for w in sf["warnings"]:
            print(f"  warning: {w}")
    else:
        print("No sources folder. PDFs of the cited works in sources/ beside the paper make the check far stronger.")
    if status["needs_pdf"]:
        print("Add PDFs of these works to the sources folder to check their citations in full:")
        for n in status["needs_pdf"]:
            print(f"  {n['ref']} {n['reference']}")
    for name, note in status["services"].items():
        print(f"  {name}: {note}")
    for w in status["warnings"]:
        print(f"WARNING: {w}")
    print(f"Wrote {work / 'citations'}: propositions.jsonl, by_ref.json, sources/, status.json")
