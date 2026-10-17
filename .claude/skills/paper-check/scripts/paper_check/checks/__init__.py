"""Registry for deterministic checks.

A check module registers functions with the checklist IDs they cover:

    from . import register

    @register("FMT-05")
    def broken_crossrefs(pm, ctx):
        for block in pm.blocks:
            ...
            yield ctx.finding("FMT-05", "Broken cross-reference", "major",
                              problem="...", block=block, quote="...")

A check may yield Finding objects, or call ctx.skip(check_id, reason) or
ctx.not_applicable(check_id, reason). A check that yields nothing and records no
coverage is recorded as run with zero findings.
"""

from __future__ import annotations

import importlib
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from .. import __version__
from ..model import Coverage, Evidence, Finding, FindingSet, Fix, Location, PaperMap

_REGISTRY: list = []
MODULES = ["format", "numbers", "venue", "coherence", "language", "references_local", "integrity", "behavioral", "samples"]


def register(*check_ids: str, name: Optional[str] = None):
    def decorator(func: Callable):
        _REGISTRY.append((check_ids, func, name or func.__name__))
        return func
    return decorator


@dataclass
class Context:
    work: Path
    settings: object = None
    venue: Optional[dict] = None
    producer: str = "script"
    coverage: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)
    current: Optional[str] = None  # name of the check function running now

    def finding(self, check_id: str, title: str, severity: str, problem: str, *,
                block=None, quote: Optional[str] = None, related=None, evidence=None,
                trajectory=None, fix: Optional[Fix] = None, confidence: str = "high",
                status: str = "confirmed", extra: Optional[dict] = None, script: str = "") -> Finding:
        locations = []
        if block is not None:
            locations.append(Location(block=block.id, anchor=block.anchor, section=list(block.section)))
        return Finding(
            check_id=check_id, title=title, severity=severity, problem=problem, quote=quote,
            locations=locations, related_quotes=list(related or []), evidence=list(evidence or []),
            trajectory=list(trajectory or []), fix=fix, confidence=confidence, status=status,
            producer={"kind": "script", "name": script or self.producer, "version": __version__},
            extra=dict(extra or {}),
        )

    def note(self, check_id: str, text: str) -> None:
        """Attach a note to a check that ran, such as what it compared. Shown in the coverage table."""
        self.notes[check_id] = text

    def skip(self, check_id: str, reason: str) -> None:
        self.coverage[check_id] = Coverage(check_id, "skipped", reason, self.current or self.producer)

    def not_applicable(self, check_id: str, reason: str) -> None:
        self.coverage[check_id] = Coverage(check_id, "not_applicable", reason, self.current or self.producer)


def load_modules(names: Iterable[str] = MODULES) -> list:
    loaded, errors = [], []
    for name in names:
        try:
            importlib.import_module(f"{__name__}.{name}")
            loaded.append(name)
        except ModuleNotFoundError as exc:
            if exc.name == f"{__name__}.{name}":
                continue  # module not written yet
            errors.append((name, traceback.format_exc(limit=2)))
        except Exception:
            errors.append((name, traceback.format_exc(limit=2)))
    return errors


def run_checks(pm: PaperMap, ctx: Context, only: Optional[set] = None) -> FindingSet:
    errors = load_modules()
    out = FindingSet(producer="scripts", settings={"version": __version__})
    for check_ids, func, name in _REGISTRY:
        if only and not (set(check_ids) & only):
            continue
        ctx.current = name
        try:
            found = [f for f in (func(pm, ctx) or []) if f is not None]
        except Exception as exc:
            for cid in check_ids:
                ctx.coverage[cid] = Coverage(cid, "skipped", f"check crashed: {type(exc).__name__}: {exc}", name)
            continue
        for f in found:
            f.producer.setdefault("check", name)
        out.findings.extend(found)
        for cid in check_ids:
            if cid not in ctx.coverage:
                n = sum(1 for f in found if f.check_id == cid)
                ctx.coverage[cid] = Coverage(cid, "run", ctx.notes.get(cid), name, n)
    for name, tb in errors:
        out.settings.setdefault("module_errors", {})[name] = tb
    out.coverage = sorted(ctx.coverage.values(), key=lambda c: c.check_id)
    return out


__all__ = ["register", "Context", "run_checks", "Evidence", "Fix", "Finding"]
