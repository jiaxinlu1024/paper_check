"""`pc.py refs WORK`: look up every reference under the reference policy.

Reads paper_map.json (and settings.json when ingest saved one) and writes:

    references/cards.json   one evidence card per reference: the reference, its verdict,
                            the matched record and its fields, the similarity of each field,
                            every query made, the databases reached, version links,
                            retraction notices, replication records and needs_web_check
    findings/refs.json      a FindingSet for CIT-02, CIT-03, CIT-04, CIT-05, CIT-12, CIT-14

The HTTP cache is work/cache/http/; FReD and Retraction Watch copies are kept in
~/.paper-check/cache/. With --offline, or with the network off in the paper's settings,
only cached answers are used, and whatever could not be looked up is recorded as skipped
coverage with the reason. Nothing is ever recorded as passed without a lookup behind it.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Optional

from .. import __version__
from ..checks import Context
from ..model import FindingSet, PaperMap
from ..textutil import find_quote
from . import replications, retractions
from .findings import CHECKS, PRODUCER, Builder, coverage_entries
from .links import check_links
from .policy import THRESHOLDS, ReferenceCheck
from .services import Services
from .versions import find_published_versions

VERDICT_TEXT = {"verified": "verified", "metadata_drift": "with metadata drift", "single_source": "found in one database",
                "chimeric": "chimeric", "not_found_in_databases": "not found in databases",
                "unverified": "could not be looked up"}


def _settings(work: Path):
    try:
        from ..config import PaperSettings
        return PaperSettings.for_work(work)
    except Exception:
        return None


def _ref_label(card: dict) -> str:
    return f"{card['ref']} ({card['key']})" if card.get("key") else card["ref"]


def _unverified_reason(card: dict) -> str:
    failed = card.get("databases_failed") or []
    if failed:
        return "; ".join(f"{d['database']}: {d['reason']}" for d in failed[:3])
    return "no database answered"


def _summary(cards: list) -> str:
    counts = Counter(c["verdict"] for c in cards)
    parts = [f"{counts[v]} {VERDICT_TEXT[v]}" for v in ("verified", "metadata_drift", "single_source", "chimeric",
                                                          "not_found_in_databases", "unverified") if counts.get(v)]
    web = sum(1 for c in cards if c.get("needs_web_check"))
    text = ", ".join(parts)
    if web:
        text += f"; {web} need a web search for the exact title before a verdict"
    return text


def run_reference_checks(work: Path, offline: bool = False, limit: Optional[int] = None, *,
                         services: Optional[Services] = None, data_root: Optional[Path] = None,
                         credentials=None, quiet: bool = False) -> int:
    work = Path(work)
    pm = PaperMap.load(work / "paper_map.json")
    settings = _settings(work)
    network_setting = getattr(settings, "network", True) if settings is not None else True
    offline = bool(offline or not network_setting)
    mode = getattr(settings, "mode", "deep") if settings is not None else "deep"
    quick = mode == "quick"
    if services is None:
        services = Services.create(work, offline=offline, credentials=credentials)
    blocks = {b.attrs.get("ref"): b for b in pm.blocks if b.kind == "reference" and b.attrs.get("ref")}
    refs = list(pm.references)
    for ref in refs:
        if ref.id not in blocks:  # readers that do not tag reference blocks: find the entry's text
            hit = next((b for b in pm.blocks if b.kind == "reference" and ref.raw and
                        (b.text == ref.raw or find_quote(ref.raw[:120], b.text))), None)
            if hit is not None:
                blocks[ref.id] = hit
    checked = refs[:limit] if limit else refs
    left_out = refs[len(checked):]

    # ---- per reference: identity, versions, links ---------------------------
    rcs = []
    for ref in checked:
        rc = ReferenceCheck(ref, blocks.get(ref.id), services)
        card = rc.run()
        if not quick:
            rc.stage = "versions"
            info = find_published_versions(rc, services)
            card["version_check"] = {k: info[k] for k in ("is_working_paper", "why", "notes") if info.get(k) is not None}
            card["version_links"] = info["links"]
            rc.stage = "links"
            card["links"] = check_links(rc, services)
        rcs.append(rc)

    # ---- all references at once: notices, then replications --------------------
    rw_meta: dict = {}
    fred_meta: dict = {}
    fred = None
    if not quick and rcs:
        for rc in rcs:
            rc.stage = "retractions"

        def rw_loader():
            return retractions.load_retraction_watch(services.http, root=data_root)

        notices = retractions.check_all(rcs, services, rw_loader)
        rw_meta = notices.pop("_retraction_watch", {}) or {}
        for rc in rcs:
            entry = notices.get(rc.ref.id, {})
            rc.card["retraction_dois"] = entry.get("dois", [])
            rc.card["retraction_notices"] = entry.get("notices", [])
            rc.card["is_retracted"] = entry.get("is_retracted", {})
            rc.card["retraction_checked"] = entry.get("checked", [])
            if entry.get("reason"):
                rc.card["retraction_reason"] = entry["reason"]
            rc.card["_assessment"] = retractions.assess(rc.card["retraction_notices"])
        if any(rc.identity_records() for rc in rcs):
            fred, fred_meta = replications.load_fred(services.http, root=data_root)
        else:
            fred_meta = {"unavailable": "no reference was identified, so FReD was not needed"}
        for rc in rcs:
            rc.stage = "replications"
            rc.card["replications"] = replications.check(rc, fred) if fred is not None else []

    # ---- cards ---------------------------------------------------------------
    cards = []
    for rc in rcs:
        rc.card["queries"] = [q.to_dict() for q in rc.queries]
        cards.append(rc.card)

    # ---- findings --------------------------------------------------------------
    ctx = Context(work=work, settings=settings, producer=PRODUCER)
    builder = Builder(ctx, blocks)
    for card in cards:
        builder.existence(card)
        builder.metadata(card)
        builder.missing_parts(card)
        if not quick:
            builder.versions(card)
            builder.retractions(card, card.pop("_assessment", None))
            builder.links(card)
            builder.replications(card)
        card.pop("_assessment", None)
    counts = Counter(f.check_id for f in builder.findings)

    # ---- coverage ----------------------------------------------------------------
    coverage = []
    unverified = [c for c in cards if c["verdict"] == "unverified"]
    conclusive = [c for c in cards if c["verdict"] != "unverified"]
    identified = [c for c in cards if c.get("matched")]
    why_offline = ("offline mode" if offline and network_setting else
                   "the network is off in the paper's settings" if not network_setting else None)
    skipped_refs = None
    if unverified:
        skipped_refs = (f"{len(unverified)} reference(s) could not be looked up"
                        + (f" ({why_offline})" if why_offline else "") + ": "
                        + "; ".join(f"{_ref_label(c)}: {_unverified_reason(c)}" for c in unverified[:6])
                        + ("; ..." if len(unverified) > 6 else ""))
    if left_out:
        extra = f"{len(left_out)} reference(s) not checked because of --limit {limit}: {left_out[0].id} to {left_out[-1].id}"
        skipped_refs = f"{skipped_refs}; {extra}" if skipped_refs else extra
    if not refs:
        for cid in CHECKS:
            coverage += coverage_entries(cid, None, 0, not_applicable="the paper has no reference list")
    else:
        coverage += coverage_entries("CIT-02", f"{len(cards)} of {len(refs)} references: {_summary(cards)}"
                                     if conclusive else None, counts["CIT-02"], skipped_refs)
        coverage += coverage_entries(
            "CIT-03", (f"fields compared for {len(identified)} reference(s) with a matched record"
                       if identified else "no reference matched a record, so no fields could be compared")
            if conclusive else None, counts["CIT-03"], skipped_refs)
        if quick:
            for cid in ("CIT-04", "CIT-05", "CIT-12", "CIT-14"):
                coverage += coverage_entries(cid, None, 0, "quick mode checks reference existence and metadata only")
        else:
            wps = [c for c in cards if (c.get("version_check") or {}).get("is_working_paper")]
            notes = sorted({n for c in wps for n in (c.get("version_check") or {}).get("notes", [])
                            if n.startswith("RePEc")})
            v_failed = [c for c in wps if not any(q["status"] in ("ok", "no_results", "not_found")
                                                 for q in c["queries"] if q.get("stage") == "versions")]
            v_note = (f"{len(wps)} working paper(s) or preprint(s) among {len(cards)} references"
                      + (f" ({', '.join(_ref_label(c) for c in wps[:6])})" if wps else "")
                      + ("; " + " ".join(notes) if notes else ""))
            v_skip = [x for x in [
                f"published versions could not be searched for {', '.join(_ref_label(c) for c in v_failed)}"
                if v_failed else None, skipped_refs] if x]
            coverage += coverage_entries("CIT-04", v_note if conclusive else None, counts["CIT-04"],
                                         "; ".join(v_skip) or None)
            checked_n = [c for c in cards if c.get("retraction_checked")]
            r_failed = [c for c in cards if c.get("matched") and not c.get("retraction_checked")]
            sources = sorted({s for c in checked_n for s in c["retraction_checked"]})
            r_note = (f"notices checked for {len(checked_n)} identified reference(s) through {', '.join(sources)}; "
                      "notices are never filtered by subject") if checked_n else None
            r_skip = [x for x in [
                ("notices could not be checked for "
                 + "; ".join(f"{_ref_label(c)}: {c.get('retraction_reason')}" for c in r_failed)) if r_failed else None,
                skipped_refs] if x]
            if r_note is None and not r_skip:
                r_skip = ["no reference was identified, so there was no work to check for notices"]
            coverage += coverage_entries("CIT-05", r_note, counts["CIT-05"], "; ".join(r_skip) or None)
            items = [l for c in cards for l in c.get("links") or []]
            done = [l for l in items if l["status"] != "unchecked"]
            undone = [l for l in items if l["status"] == "unchecked"]
            n_doi = sum(1 for l in done if l["kind"] == "doi")
            n_url = len(done) - n_doi
            if not items:
                coverage += coverage_entries("CIT-12", None, 0, skipped_refs,
                                             not_applicable="the references have no DOIs or URLs")
            else:
                coverage += coverage_entries(
                    "CIT-12", f"{n_doi} DOI(s) and {n_url} URL(s) checked" if done else None, counts["CIT-12"],
                    "; ".join(x for x in [
                        (f"{len(undone)} link(s) could not be checked: "
                         + "; ".join(f"{l['value']} ({l.get('error') or 'no answer'})" for l in undone[:5]))
                        if undone else None, skipped_refs if left_out else None] if x) or None)
            if fred is None:
                coverage += coverage_entries("CIT-14", None, 0, "FReD not available: " + (
                    fred_meta.get("unavailable") or "unknown reason"))
            else:
                lic = (fred_meta.get("license") or {}).get("name") or "CC BY 4.0 (OSF project 9r62x)"
                coverage += coverage_entries(
                    "CIT-14", f"{len(identified)} identified reference(s) looked up in FReD's paper-level file "
                              f"({fred_meta.get('rows', '?')} records, downloaded {fred_meta.get('downloaded_at', '?')}, "
                              f"license {lic})", counts["CIT-14"],
                    skipped_refs if (unverified or left_out) else None)

    out = FindingSet(producer=PRODUCER, findings=builder.findings, coverage=coverage, settings={
        "version": __version__, "mode": mode, "offline": offline, "network_setting": network_setting,
        "limit": limit, "thresholds": THRESHOLDS, "lookups": services.status(),
        "datasets": {"fred": fred_meta, "retraction_watch": rw_meta},
    })
    out.save(work / "findings" / "refs.json")
    cards_path = work / "references" / "cards.json"
    cards_path.parent.mkdir(parents=True, exist_ok=True)
    cards_doc = {"version": __version__, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "offline": offline, "thresholds": THRESHOLDS, "cards": cards}
    cards_path.write_text(json.dumps(cards_doc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if not quiet:
        sev = Counter(f.severity for f in builder.findings)
        print(f"References: {len(cards)} of {len(refs)} looked up" + (" (offline: cache only)" if offline else "")
              + (f": {_summary(cards)}." if cards else "."))
        print(f"Findings: {len(builder.findings)}" + (" (" + ", ".join(f"{sev[s]} {s}" for s in
                                                                         ("critical", "major", "minor", "suggestion")
                                                                         if sev.get(s)) + ")" if builder.findings else ""))
        web = [c for c in cards if c.get("needs_web_check")]
        for c in web:
            print(f"  needs a web check: {_ref_label(c)} {c['web_check']['query']}")
        print(f"Cards: {cards_path}")
        print(f"Findings file: {work / 'findings' / 'refs.json'}")
    return 0
