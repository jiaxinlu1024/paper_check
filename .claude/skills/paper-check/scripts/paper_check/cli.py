"""Command-line interface. Run `pc.py --help` for the list of commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def _work(path: str) -> Path:
    work = Path(path).resolve()
    if work.name != "paper-check-work" and (work / "paper-check-work").is_dir():
        work = work / "paper-check-work"
    if not (work / "paper_map.json").exists():
        raise SystemExit(f"No paper map in {work}. Run `pc.py ingest PAPER` first.")
    return work


def cmd_doctor(args):
    from .env import doctor
    return doctor(network=not args.offline)


def cmd_setup(args):
    from .env import setup
    return setup()


def _settings(work: Path, **overrides):
    from .config import PaperSettings
    return PaperSettings.for_work(work, overrides)


def cmd_ingest(args):
    from .config import PaperSettings, paper_dir_of, work_dir_for
    from .ingest import ingest
    from .venues import load_venue

    paper = Path(args.paper).resolve()
    overrides = {"venue": args.venue, "mode": args.mode, "sources": args.sources,
                 "language_variant": args.language, "study_type": args.study_type,
                 "min_severity": args.min_severity,
                 "network": False if args.offline else None, "paid_pdfs": True if args.paid_pdfs else None,
                 "sequential": True if args.sequential else None}
    settings = PaperSettings.load(paper_dir_of(paper), overrides)
    load_venue(settings.venue)  # fail early on an unknown venue id
    code = ingest(paper, output=args.out, main_file=args.main)
    if code == 0:
        path = settings.save(work_dir_for(paper, args.out))
        print(f"Settings ({path.name}): {settings.summary()}")
    return code


def cmd_checks(args):
    from .checks import Context, run_checks
    from .model import PaperMap
    from .venues import load_venue

    work = _work(args.work)
    pm = PaperMap.load(work / "paper_map.json")
    settings = _settings(work, venue=args.venue)
    ctx = Context(work=work, settings=settings, venue=load_venue(settings.venue))
    only = {c.strip().upper() for c in args.only.split(",") if c.strip()} if args.only else None
    result = run_checks(pm, ctx, only)
    out_path = work / "findings" / "scripts.json"
    if only and out_path.exists():
        # Rerunning some checks replaces only their findings and coverage.
        from .model import FindingSet
        old = FindingSet.load(out_path)
        old.findings = [f for f in old.findings if f.check_id not in only] + result.findings
        old.coverage = sorted([c for c in old.coverage if c.check_id not in only] + result.coverage,
                              key=lambda c: c.check_id)
        old.settings.update(result.settings)
        result = old
    result.save(out_path)
    print(f"{len(result.findings)} findings from script checks; coverage for {len(result.coverage)} checks.")
    for name, tb in result.settings.get("module_errors", {}).items():
        print(f"WARNING: check module '{name}' failed to load:\n{tb}")
    return 0


def cmd_refs(args):
    try:
        from .lookups.run import run_reference_checks
    except ImportError as exc:
        raise SystemExit(f"Reference lookups are not available in this version: {exc}")
    work = _work(args.work)
    offline = args.offline or not _settings(work).network
    return run_reference_checks(work, offline=offline, limit=args.limit)


def cmd_cite_prepare(args):
    try:
        from .citations.prepare import prepare
    except ImportError as exc:
        raise SystemExit(f"Citation support is not available in this version: {exc}")
    work = _work(args.work)
    settings = _settings(work, sources=args.sources)
    return prepare(work, sources=settings.sources, offline=args.offline or not settings.network)


def cmd_scan(args):
    try:
        from .citations.scan import scan_command
    except ImportError as exc:
        raise SystemExit(f"Scanning is not available in this version: {exc}")
    return scan_command(_work(args.work), args.ref, args.terms, context=args.context, top=args.top)


def cmd_works(args):
    from .lookups.works import works_command
    work = _work(args.work)
    return works_command(work, " ".join(args.query), limit=args.limit, year_from=args.year_from,
                         offline=args.offline or not _settings(work).network)


def cmd_terms(args):
    try:
        from .citations.terms import terms_command
    except ImportError as exc:
        raise SystemExit(f"Term expansion is not available in this version: {exc}")
    return terms_command(args.terms, offline=args.offline)


def cmd_render(args):
    try:
        from .ingest.render import render_command
    except ImportError as exc:
        raise SystemExit(f"Rendering is not available in this version: {exc}")
    return render_command(_work(args.work), page=args.page, bbox=args.bbox, out=args.out)


def cmd_find(args):
    from .verify import find_command
    return find_command(_work(args.work), args.quote)


def cmd_skip(args):
    """Record checks that were deliberately not run, with the reason, in findings/orchestrator.json."""
    import yaml
    from .model import Coverage, FindingSet

    work = _work(args.work)
    checks_file = Path(__file__).resolve().parents[2] / "references" / "checks.yaml"
    known = [c["id"] for c in yaml.safe_load(checks_file.read_text(encoding="utf-8"))["checks"]]
    wanted = set()
    for item in (args.checks or "").split(","):
        item = item.strip().upper()
        if not item:
            continue
        if item in known:
            wanted.add(item)
        elif any(k.startswith(item + "-") for k in known):
            wanted.update(k for k in known if k.startswith(item + "-"))
        else:
            raise SystemExit(f"Unknown check or dimension {item!r}.")
    if args.uncovered:
        from .verify import load_findings_file
        covered = set()
        for path in sorted((work / "findings").glob("*.json")) if (work / "findings").exists() else []:
            fs, _errors, _notes = load_findings_file(path)
            if fs and fs.producer != "orchestrator":
                covered.update(c.check_id for c in fs.coverage)
        wanted.update(k for k in known if k not in covered)
    if not wanted:
        raise SystemExit("Name checks with --checks, or use --uncovered.")
    path = work / "findings" / "orchestrator.json"
    fs = FindingSet.load(path) if path.exists() else FindingSet(producer="orchestrator")
    fs.coverage = [c for c in fs.coverage if c.check_id not in wanted]
    status = "not_applicable" if args.not_applicable else "skipped"
    fs.coverage += [Coverage(cid, status, args.reason, "orchestrator") for cid in sorted(wanted)]
    fs.coverage.sort(key=lambda c: c.check_id)
    fs.save(path)
    print(f"Recorded {len(wanted)} checks as {status.replace('_', ' ')}: {', '.join(sorted(wanted))}")
    return 0


def cmd_merge_runs(args):
    from .runs import merge_runs
    work = _work(args.work)
    if _settings(work).sequential:
        print("Not merged: this run is sequential (ingest --sequential), so a second run by the same agent is not "
              "independent. Leave the first run's file as it is.")
        return 2
    return merge_runs(work, args.dimension)


def cmd_validate(args):
    from .verify import validate_command
    return validate_command(_work(args.work), args.file)


def cmd_verify(args):
    from .verify import verify_work
    return verify_work(_work(args.work))


def cmd_report(args):
    from .report import build_report
    work = _work(args.work)
    return build_report(work, settings=_settings(work, venue=args.venue, min_severity=args.min_severity))


def cmd_status(args):
    from .verify import load_findings_file
    import yaml

    work = _work(args.work)
    pm = json.loads((work / "paper_map.json").read_text(encoding="utf-8"))
    print(f"Paper: {pm['source'].get('path')} ({pm['source'].get('format')})")
    print(f"Blocks: {len(pm.get('blocks', []))}, references: {len(pm.get('references', []))}, "
          f"tables: {len(pm.get('tables', []))}")
    print(f"Settings: {_settings(work).summary()}")
    covered = {}
    for path in sorted((work / "findings").glob("*.json")) if (work / "findings").exists() else []:
        fs, errors, _notes = load_findings_file(path)
        if fs is None:
            print(f"findings/{path.name}: unreadable: {errors[0]}")
            continue
        kept = sum(1 for f in fs.findings if f.status != "dropped")
        print(f"findings/{path.name}: {kept} findings, {len(fs.findings) - kept} dropped, "
              f"coverage for {len(fs.coverage)} checks" + (f", {len(errors)} problems" if errors else ""))
        for c in fs.coverage:
            covered.setdefault(c.check_id, set()).add(c.status)
    checks_file = Path(__file__).resolve().parents[2] / "references" / "checks.yaml"
    ids = [c["id"] for c in yaml.safe_load(checks_file.read_text(encoding="utf-8"))["checks"]]
    missing = [i for i in ids if i not in covered]
    print(f"Coverage: {len(ids) - len(missing)} of {len(ids)} checks have an outcome.")
    if missing:
        by_dim = {}
        for i in missing:
            by_dim.setdefault(i.split("-")[0], []).append(i)
        for dim, items in by_dim.items():
            print(f"  no outcome yet, {dim}: {', '.join(items)}")
    return 0


def cmd_venues(args):
    from .venues import list_venues, load_venue
    if args.id:
        print(json.dumps(load_venue(args.id), ensure_ascii=False, indent=1, default=str))
        return 0
    for v in list_venues():
        print(f"{v['id']:14s} {v['group']:13s} checked {v['checked_on']}  {v['name']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pc.py", description="paper-check scripts")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("doctor", help="check Python, packages, credentials and network")
    s.add_argument("--offline", action="store_true", help="skip the network probes")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("setup", help="create ~/.paper-check/venv and install requirements")
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("ingest", help="build the paper map from LaTeX, PDF or Word, and save the settings")
    s.add_argument("paper", help="a .tex file or LaTeX project folder, a .pdf, or a .docx")
    s.add_argument("--out", help="output folder; default: beside the paper")
    s.add_argument("--main", help="main .tex file when PAPER is a folder")
    s.add_argument("--venue", help="venue profile id; see `pc.py venues`")
    s.add_argument("--mode", choices=["quick", "standard", "deep"], help="default: deep")
    s.add_argument("--sources", help="folder of PDFs of the cited works; default: sources/ beside the paper")
    s.add_argument("--language", dest="language", choices=["US", "UK"], help="English variant")
    s.add_argument("--study-type", dest="study_type",
                   help="for example lab experiment, field experiment, online experiment, survey, observational, theory")
    s.add_argument("--min-severity", dest="min_severity", choices=["critical", "major", "minor", "suggestion"])
    s.add_argument("--offline", action="store_true", help="no network: lookup checks are reported as skipped")
    s.add_argument("--paid-pdfs", dest="paid_pdfs", action="store_true", help="allow OpenAlex paid PDFs")
    s.add_argument("--sequential", action="store_true",
                   help="one agent does every step in turn (no subagents): second runs are skipped and the report "
                        "says the refuter pass was not independent")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("checks", help="run the deterministic checks")
    s.add_argument("work", help="the paper-check-work folder, or the folder that contains it")
    s.add_argument("--venue", help="venue profile id; see `pc.py venues`")
    s.add_argument("--only", help="comma-separated check ids")
    s.set_defaults(func=cmd_checks)

    s = sub.add_parser("refs", help="look up every reference: existence, metadata, retractions, versions")
    s.add_argument("work")
    s.add_argument("--offline", action="store_true", help="use only the cache")
    s.add_argument("--limit", type=int, help="check only the first N references")
    s.set_defaults(func=cmd_refs)

    s = sub.add_parser("cite-prepare", help="extract citing sentences and fetch cited full texts")
    s.add_argument("work")
    s.add_argument("--sources", help="folder of PDFs of the cited works")
    s.add_argument("--offline", action="store_true")
    s.set_defaults(func=cmd_cite_prepare)

    s = sub.add_parser("scan", help="search a cited work's full text for terms")
    s.add_argument("work")
    s.add_argument("--ref", required=True, help="reference id, such as r012")
    s.add_argument("--terms", nargs="+", required=True)
    s.add_argument("--context", type=int, default=300, help="characters of context per hit")
    s.add_argument("--top", type=int, default=8, help="passages to show")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("works", help="search the literature for candidate works, with abstracts (OpenAlex, Crossref)")
    s.add_argument("work")
    s.add_argument("query", nargs="+", help="a short description of the claim or topic, never the paper's text")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--year-from", dest="year_from", type=int)
    s.add_argument("--offline", action="store_true", help="use only the cache")
    s.set_defaults(func=cmd_works)

    s = sub.add_parser("terms", help="expand concepts into synonyms and related terms (STW thesaurus and glossary)")
    s.add_argument("terms", nargs="+")
    s.add_argument("--offline", action="store_true", help="use only the cached thesaurus")
    s.set_defaults(func=cmd_terms)

    s = sub.add_parser("render", help="render a PDF page, or a region of it, to PNG")
    s.add_argument("work")
    s.add_argument("--page", type=int, required=True)
    s.add_argument("--bbox", help="x0,top,x1,bottom in points")
    s.add_argument("--out", help="file name under WORK/images/")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("find", help="locate a quote in the paper map")
    s.add_argument("work")
    s.add_argument("quote")
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("skip", help="record checks that were not run on purpose, with the reason")
    s.add_argument("work")
    s.add_argument("--checks", help="comma-separated check ids or dimensions, such as LOG-07,FIG")
    s.add_argument("--uncovered", action="store_true", help="every check that no producer has covered yet")
    s.add_argument("--reason", required=True)
    s.add_argument("--not-applicable", dest="not_applicable", action="store_true",
                   help="record as not applicable instead of skipped")
    s.set_defaults(func=cmd_skip)

    s = sub.add_parser("merge-runs", help="compare a second, independent run of a reading agent with the first")
    s.add_argument("work")
    s.add_argument("--dimension", required=True, help="the agent's dimension, such as logic or numbers")
    s.set_defaults(func=cmd_merge_runs)

    s = sub.add_parser("validate", help="check that findings files are well formed")
    s.add_argument("work")
    s.add_argument("--file", help="one findings file; default: every file in findings/")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("verify", help="check every quote in every finding")
    s.add_argument("work")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("report", help="write the report and the findings file")
    s.add_argument("work")
    s.add_argument("--venue", help="override the venue saved at ingest")
    s.add_argument("--min-severity", dest="min_severity", choices=["critical", "major", "minor", "suggestion"])
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("status", help="show what has been produced so far and which checks have no outcome")
    s.add_argument("work")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("venues", help="list venue profiles, or show one")
    s.add_argument("id", nargs="?")
    s.set_defaults(func=cmd_venues)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
