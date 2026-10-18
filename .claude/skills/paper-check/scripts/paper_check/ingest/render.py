"""`pc.py render WORK --page N [--bbox x0,top,x1,bottom] [--out NAME]`: a PDF page, or a
region of it, as a PNG image in WORK/images/, for visual checks and image evidence.
The image is named after the page and region unless --out names it.

Coordinates are points from the page's top-left corner, as in the paper map's
anchors, so a block's `anchor.bbox` can be passed as it is. Rendering goes
through pdfplumber's renderer (pypdfium2).

The PDF is the paper map's source. For a LaTeX or Word paper, a PDF beside the
source with the same name (main.pdf for main.tex, paper.pdf for paper.docx) is
used when there is one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

PAGE_DPI = 150
REGION_DPI = 200


def find_pdf(work: Path) -> Path:
    """The PDF behind a work folder's paper map."""
    pm = json.loads((Path(work) / "paper_map.json").read_text(encoding="utf-8"))
    source = pm.get("source", {})
    metadata = pm.get("metadata", {})
    path = Path(source.get("path") or "")
    candidates = []
    if source.get("format") == "pdf":
        candidates.append(path)
    for key in ("pdf", "compiled_pdf", "rendered_pdf"):
        for where in (source, metadata):
            if where.get(key):
                candidates.append(Path(where[key]))
    if source.get("format") == "latex":
        root = path if path.is_dir() else path.parent
        main = source.get("main")
        if main:
            candidates.append(root / Path(main).with_suffix(".pdf"))
        if path.suffix.lower() in (".tex", ".ltx"):
            candidates.append(path.with_suffix(".pdf"))
    elif source.get("format") == "docx" and path.suffix:
        candidates.append(path.with_suffix(".pdf"))
    for candidate in candidates:
        if candidate.suffix.lower() == ".pdf" and candidate.is_file():
            return candidate
    if source.get("format") == "pdf":
        raise SystemExit(f"The PDF {path} was not found. It may have been moved since `pc.py ingest` ran.")
    raise SystemExit("Rendering needs a PDF, and this paper map was built from "
                     f"{source.get('format') or 'an unknown format'} with no PDF beside it. Compile or export the "
                     "paper to PDF next to its source and run `pc.py render` again.")


def parse_bbox(text: str, width: float, height: float) -> tuple:
    """x0,top,x1,bottom in points, clipped to the page."""
    try:
        parts = [float(v) for v in re.split(r"[,\s]+", text.strip().strip("[]()")) if v]
    except ValueError:
        parts = []
    if len(parts) != 4:
        raise SystemExit("--bbox needs four numbers, x0,top,x1,bottom, in points from the page's top-left corner.")
    x0, top, x1, bottom = parts
    x0, x1 = sorted((x0, x1))
    top, bottom = sorted((top, bottom))
    x0, top, x1, bottom = max(0.0, x0), max(0.0, top), min(width, x1), min(height, bottom)
    if x1 - x0 < 1 or bottom - top < 1:
        raise SystemExit(f"The region {text} is empty or outside the page ({width:g} x {height:g} points).")
    return x0, top, x1, bottom


def _target(images: Path, page: int, region: Optional[tuple], out: Optional[str]) -> Path:
    if out:
        target = Path(out)
        if not target.is_absolute():
            target = images / target
        if target.suffix.lower() != ".png":
            target = target.with_name(target.name + ".png")
        try:
            target.resolve().relative_to(images.resolve())
        except ValueError:
            raise SystemExit(f"--out must name a file in {images}, such as table1.png.") from None
        return target
    name = f"page-{page:03d}"
    if region:
        name += "-" + "-".join(str(int(round(v))) for v in region)
    return images / f"{name}.png"


def render_command(work: Path, page: int, bbox: Optional[str] = None, out: Optional[str] = None) -> int:
    import pdfplumber

    work = Path(work)
    pdf_path = find_pdf(work)
    images = work / "images"
    with pdfplumber.open(str(pdf_path)) as pdf:
        count = len(pdf.pages)
        if not 1 <= page <= count:
            raise SystemExit(f"Page {page} does not exist: {pdf_path.name} has {count} pages.")
        p = pdf.pages[page - 1]
        region = None
        if bbox:
            region = parse_bbox(bbox, float(p.width), float(p.height))
            ox, oy = float(p.bbox[0]), float(p.bbox[1])
            x0, top, x1, bottom = region
            p = p.crop((ox + x0, oy + top, ox + x1, oy + bottom))
        image = p.to_image(resolution=REGION_DPI if region else PAGE_DPI, antialias=True)
        target = _target(images, page, region, out)
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(target), format="PNG")
        width, height = image.original.size
    where = f" region {','.join(f'{v:g}' for v in region)}" if region else ""
    print(f"Rendered page {page}{where} of {pdf_path.name} to {target} ({width} x {height} pixels).")
    return 0
