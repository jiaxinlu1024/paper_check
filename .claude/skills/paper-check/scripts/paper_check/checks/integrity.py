"""Integrity checks with a script part: ETH-06 verbatim overlap and ETH-07 duplicate images.

ETH-06 compares the paper with the cited works' texts cached by `pc.py cite-prepare`
in citations/sources/<ref>.txt (full texts or abstracts). It reports runs of at
least MIN_RUN identical words that are not marked as a quotation. Run it again with
`pc.py checks WORK --only ETH-06` after cite-prepare; before that it is skipped.

ETH-07 hashes the raster images in the paper (figure files for LaTeX, embedded
images for PDF and Word) with ImageHash and reports near-identical images or
quadrants. Reuse can be legitimate, so findings need human judgment. Vector plots
inside a PDF are not extracted, so coverage says "raster images only".
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from ..model import Evidence, Fix
from . import register

MIN_RUN = 12            # words; shorter shared runs are mostly stock phrases
SHINGLE = 8
TEXT_KINDS = ("paragraph", "abstract", "footnote", "list_item", "caption")
_WORD = re.compile(r"\w+(?:[-']\w+)*", re.UNICODE)
_PAGE = re.compile(r"\[\[page (\d+)\]\]")
_QUOTES = "\"“”«»„"


def _tokens(text: str) -> list:
    return [(m.group(0).lower(), m.start(), m.end()) for m in _WORD.finditer(text)]


def _page_at(text: str, pos: int):
    page = None
    for m in _PAGE.finditer(text, 0, pos):
        page = m.group(1)
    return page


def _quoted(text: str, start: int, end: int) -> bool:
    """True when the span sits inside quotation marks in the paper."""
    before = text[max(0, start - 3):start]
    after = text[end:end + 3]
    if any(q in before for q in _QUOTES) and any(q in after for q in _QUOTES):
        return True
    opened = sum(text.count(q, 0, start) for q in "“«„")
    closed = sum(text.count(q, 0, start) for q in "”»")
    return opened > closed or text.count('"', 0, start) % 2 == 1


@register("ETH-06")
def verbatim_overlap(pm, ctx):
    src_dir = ctx.work / "citations" / "sources"
    texts = sorted(src_dir.glob("*.txt")) if src_dir.is_dir() else []
    if not texts:
        ctx.skip("ETH-06", "no cited texts cached yet; run `pc.py cite-prepare` and then "
                           "`pc.py checks WORK --only ETH-06`")
        return
    # Index the paper, which is small, and stream each cited text past it.
    blocks = [b for b in pm.blocks if b.kind in TEXT_KINDS and not (b.attrs or {}).get("hidden")]
    btoks = {b.id: _tokens(b.text) for b in blocks}
    index: dict = {}
    for b in blocks:
        toks = btoks[b.id]
        for i in range(len(toks) - SHINGLE + 1):
            index.setdefault(" ".join(t[0] for t in toks[i:i + SHINGLE]), []).append((b.id, i))
    runs = []  # (length, block id, paper token index, ref, source token index)
    for path in texts:
        stext = path.read_text(encoding="utf-8", errors="replace")
        stoks = _tokens(_PAGE.sub(lambda m: " " * len(m.group(0)), stext))
        for j in range(len(stoks) - SHINGLE + 1):
            hits = index.get(" ".join(t[0] for t in stoks[j:j + SHINGLE]))
            for bid, i in hits or ():
                toks = btoks[bid]
                if i > 0 and j > 0 and toks[i - 1][0] == stoks[j - 1][0]:
                    continue  # not the start of a run
                n = SHINGLE
                while i + n < len(toks) and j + n < len(stoks) and toks[i + n][0] == stoks[j + n][0]:
                    n += 1
                if n >= MIN_RUN:
                    runs.append((n, bid, i, path.stem, j, stext, stoks))
    runs.sort(key=lambda r: -r[0])
    taken: dict = {}
    for n, bid, i, ref, j, stext, stoks in runs:
        spans = taken.setdefault(bid, [])
        if any(i < e and s < i + n for s, e in spans):
            continue  # a longer run already covers this passage
        spans.append((i, i + n))
        block = pm.block(bid)
        toks = btoks[bid]
        s, e = toks[i][1], toks[i + n - 1][2]
        if _quoted(block.text, s, e):
            continue
        ss, se = stoks[j][1], stoks[j + n - 1][2]
        cited_here = any(k == ref or (pm.reference(k) is not None and pm.reference(k).id == ref)
                         for c in block.citations for k in c.keys)
        ref_obj = pm.reference(ref)
        label = ref_obj.raw[:90] if ref_obj else ref
        yield ctx.finding(
            "ETH-06", "Passage copied word for word from a cited work", "major",
            problem=(f"{n} consecutive words match {label} word for word, without quotation marks"
                     + (". The work is cited here, but copied wording still needs quotation marks or a rewrite."
                        if cited_here else ", and the work is not cited in this passage.")),
            block=block, quote=block.text[s:e],
            evidence=[Evidence("source_quote", text=stext[ss:se], ref=ref, page=_page_at(stext, ss)),
                      Evidence("computed_result", data={
                          "formula": "longest run of identical words, case-insensitive",
                          "inputs": {"paper_block": bid, "source": ref},
                          "output": f"{n} words", "tolerance": f"minimum {MIN_RUN} words"})],
            trajectory=[f"Indexed every {SHINGLE}-word sequence in the paper and scanned {len(texts)} cached cited texts.",
                        f"Extended the match in block {bid} word by word: {n} words.",
                        "Checked for quotation marks around the passage: none."],
            fix=Fix("investigate", detail="Put the passage in quotation marks with a page number, "
                                         "or paraphrase it and keep the citation.",
                    resolved_when=f"No run of {MIN_RUN} or more words matches a cited work outside quotation marks."),
            confidence="high" if n >= 20 else "medium", status="likely", script="checks.integrity")
    ctx.note("ETH-06", f"compared with {len(texts)} cached cited texts (full texts and abstracts)")


# ---- ETH-07 ---------------------------------------------------------------------------

def _latex_images(pm, paper_dir: Path) -> list:
    out = []
    root = Path(pm.source.get("path") or paper_dir)
    root = root if root.is_dir() else root.parent
    for fig in pm.figures:
        for name in fig.files or []:
            cands = [root / name] if Path(name).suffix else [root / (name + ext) for ext in (".png", ".jpg", ".jpeg", ".pdf")]
            path = next((c for c in cands if c.exists()), None)
            if path is None:
                out.append(("missing", name, fig))
                continue
            out.append(("file", path, fig))
    return out


def _load_image(kind, src):
    from PIL import Image

    if kind == "file":
        path = Path(src)
        if path.suffix.lower() == ".pdf":
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                return pdf.pages[0].to_image(resolution=100).original.convert("RGB")
        if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"):
            return Image.open(path).convert("RGB")
        return None
    if kind == "bytes":
        return Image.open(io.BytesIO(src)).convert("RGB")
    return None


def _usable(img) -> bool:
    if img is None or img.width < 64 or img.height < 64:
        return False
    from PIL import ImageStat
    return max(ImageStat.Stat(img.convert("L")).stddev) > 6


def _hashes(img) -> list:
    import imagehash

    parts = [("whole", img)]
    if img.width >= 200 and img.height >= 200:
        w, h = img.width // 2, img.height // 2
        for name, box in (("top left", (0, 0, w, h)), ("top right", (w, 0, img.width, h)),
                          ("bottom left", (0, h, w, img.height)), ("bottom right", (w, h, img.width, img.height))):
            part = img.crop(box)
            if _usable(part):
                parts.append((name, part))
    return [(name, imagehash.phash(part), part) for name, part in parts]


@register("ETH-07")
def duplicate_images(pm, ctx):
    try:
        import imagehash  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        ctx.skip("ETH-07", f"ImageHash or Pillow is not installed: {exc}")
        return
    fmt = pm.source.get("format")
    paper_path = Path(pm.source.get("path") or ".")
    images = []  # (label, image, block id or None)
    missing = []
    if fmt == "latex":
        for kind, src, fig in _latex_images(pm, Path(pm.source.get("paper_dir") or ".")):
            if kind == "missing":
                missing.append(str(src))
                continue
            try:
                img = _load_image(kind, src)
            except Exception:
                img = None
            if _usable(img):
                images.append((f"Figure {fig.number} ({Path(src).name})", img, fig.caption_block))
    elif fmt == "docx" and paper_path.exists():
        with zipfile.ZipFile(paper_path) as z:
            for name in sorted(n for n in z.namelist() if n.startswith("word/media/")):
                try:
                    img = _load_image("bytes", z.read(name))
                except Exception:
                    img = None
                if _usable(img):
                    images.append((name.split("/")[-1], img, None))
    elif fmt == "pdf" and paper_path.exists():
        import pdfplumber
        with pdfplumber.open(str(paper_path)) as pdf:
            for pno, page in enumerate(pdf.pages, 1):
                for k, im in enumerate(page.images, 1):
                    box = (max(0, im["x0"]), max(0, im["top"]), min(page.width, im["x1"]), min(page.height, im["bottom"]))
                    if box[2] - box[0] < 30 or box[3] - box[1] < 30:
                        continue
                    try:
                        img = page.crop(box).to_image(resolution=110).original.convert("RGB")
                    except Exception:
                        img = None
                    if _usable(img):
                        images.append((f"page {pno}, image {k}", img, None))
    if len(images) < 1:
        reason = "no raster images found to compare"
        if missing:
            reason = f"figure files not found beside the source: {', '.join(missing[:5])}"
        ctx.skip("ETH-07", reason)
        return
    hashed = [(label, block, _hashes(img)) for label, img, block in images]
    out_dir = ctx.work / "images"
    found = 0
    seen = set()
    for a in range(len(hashed)):
        for b in range(a, len(hashed)):
            la, ba, ha = hashed[a]
            lb, bb, hb = hashed[b]
            for pa_name, pa_hash, pa_img in ha:
                for pb_name, pb_hash, pb_img in hb:
                    if a == b and pa_name >= pb_name:
                        continue  # within one image, compare each pair of quadrants once
                    if a == b and "whole" in (pa_name, pb_name):
                        continue
                    whole = pa_name == "whole" and pb_name == "whole"
                    dist = pa_hash - pb_hash
                    if dist > (6 if whole else 4):
                        continue
                    key = (a, b)
                    if key in seen and not whole:
                        continue
                    seen.add(key)
                    found += 1
                    out_dir.mkdir(parents=True, exist_ok=True)
                    pa_path = out_dir / f"eth07_{found:02d}_a.png"
                    pb_path = out_dir / f"eth07_{found:02d}_b.png"
                    pa_img.save(pa_path)
                    pb_img.save(pb_path)
                    what_a = f"{la}" + ("" if pa_name == "whole" else f", {pa_name} quarter")
                    what_b = f"{lb}" + ("" if pb_name == "whole" else f", {pb_name} quarter")
                    block = pm.block(ba) if ba else None
                    yield ctx.finding(
                        "ETH-07", "Near-identical image panels", "major",
                        problem=f"{what_a} and {what_b} are near-identical (perceptual hash distance {dist} of 64). "
                                "Reuse can be legitimate, so a person should look at both.",
                        block=block, quote=block.text if block is not None else None,
                        evidence=[Evidence("image", text=what_a, data={"path": str(pa_path)}),
                                  Evidence("image", text=what_b, data={"path": str(pb_path)}),
                                  Evidence("computed_result", data={
                                      "formula": "perceptual hash (pHash) Hamming distance",
                                      "inputs": {"a": what_a, "b": what_b}, "output": dist,
                                      "tolerance": "6 for whole images, 4 for quarters"})],
                        trajectory=[f"Extracted {len(images)} raster images.",
                                    "Hashed each whole image and its four quarters with pHash.",
                                    f"Compared every pair: distance {dist}."],
                        fix=Fix("investigate", detail="Confirm whether the two panels show different data; "
                                                     "replace the duplicate or say in the caption that it is reused.",
                                resolved_when="Each panel shows distinct data, or reuse is stated."),
                        confidence="medium", status="needs_human", script="checks.integrity")
    ctx.note("ETH-07", f"compared {len(images)} raster images; vector plots are not extracted"
                       + (f"; missing figure files: {', '.join(missing[:5])}" if missing else ""))
