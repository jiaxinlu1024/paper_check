"""`pc.py ingest PAPER`: detect the format and build the paper map."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from ..config import work_dir_for


def detect_format(paper: Path) -> str:
    if paper.is_dir():
        return "latex"
    suffix = paper.suffix.lower()
    if suffix in (".tex", ".ltx"):
        return "latex"
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".docx", ".docm"):
        return "docx"
    raise SystemExit(f"Unsupported input {paper}. Give a .tex file or LaTeX folder, a .pdf, or a .docx.")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    for p in files:
        h.update(p.read_bytes())
    return h.hexdigest()


def ingest(paper: Path, output: Optional[str] = None, main_file: Optional[str] = None) -> int:
    paper = paper.resolve()
    if not paper.exists():
        raise SystemExit(f"{paper} does not exist.")
    fmt = detect_format(paper)
    work = work_dir_for(paper, output)
    work.mkdir(parents=True, exist_ok=True)
    if fmt == "latex":
        from .latex import read_latex as reader
        pm = reader(paper, main_file=main_file)
    elif fmt == "docx":
        try:
            from .docx_reader import read_docx as reader
        except ImportError as exc:
            raise SystemExit(f"Word ingestion is not available in this version: {exc}")
        pm = reader(paper)
    else:
        try:
            from .pdf_reader import read_pdf as reader
        except ImportError as exc:
            raise SystemExit(f"PDF ingestion is not available in this version: {exc}")
        pm = reader(paper)
    pm.source.setdefault("path", str(paper))
    pm.source["format"] = fmt
    pm.source["paper_dir"] = str(paper if paper.is_dir() else paper.parent)
    pm.source["sha256"] = sha256_of(paper if fmt != "latex" or paper.is_dir() else paper)
    from .common import finish
    finish(pm, work)
    counts = {k: sum(1 for b in pm.blocks if b.kind == k) for k in ("heading", "paragraph", "footnote", "table", "caption")}
    print(f"Paper map: {work / 'paper_map.json'}")
    print(f"  {len(pm.blocks)} blocks ({', '.join(f'{v} {k}s' for k, v in counts.items())}), "
          f"{len(pm.references)} references, {len(pm.tables)} tables, {len(pm.figures)} figures, "
          f"{len(pm.numbers)} numbers, {len(pm.notes)} comments or hidden items")
    for w in pm.warnings[:20]:
        print(f"  warning: {w}")
    print(f"Readable text for agents: {work / 'paper_text.md'}")
    return 0
