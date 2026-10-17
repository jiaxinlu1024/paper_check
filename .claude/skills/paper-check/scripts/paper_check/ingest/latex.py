"""LaTeX reader: a .tex file or project folder into a PaperMap.

Steps:
  1. Flatten \\input and \\include with flachtex, which keeps an origin map, so
     every character can be traced to its file and line.
  2. Blank out comments, \\iffalse blocks and comment environments, keeping
     offsets stable and recording each one as a note.
  3. Scan the document body for headings, the abstract, floats, equations, lists,
     theorem-like environments and the bibliography. Text between them becomes
     paragraphs; footnotes become their own blocks.
  4. Replace citations and cross-references with sentinels, convert LaTeX to text
     with pylatexenc (falling back to a simple stripper), then render citations as
     author-year text and references as numbers, recording their spans.
"""

from __future__ import annotations

import bisect
import re
from pathlib import Path
from typing import Optional

from ..model import Anchor, Block, Citation, CrossRef, Figure, Label, Note, PaperMap, Reference, Table

HEADING_LEVELS = {"part": 0, "chapter": 0, "section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4, "subparagraph": 5}
FLOAT_ENVS = {"figure", "figure*", "table", "table*", "sidewaystable", "sidewaystable*", "sidewaysfigure", "sidewaysfigure*"}
MATH_ENVS = {"equation", "equation*", "align", "align*", "gather", "gather*", "multline", "multline*",
             "eqnarray", "eqnarray*", "displaymath", "flalign", "flalign*"}
LIST_ENVS = {"itemize", "enumerate", "description"}
THEOREM_ENVS = {"theorem", "proposition", "lemma", "corollary", "definition", "hypothesis", "assumption",
                "remark", "example", "conjecture", "claim", "prediction", "result", "observation", "fact", "proof"}
SKIP_ENVS = {"comment", "verbatim", "lstlisting", "tikzpicture", "titlepage"}
TABULAR_ENVS = ("tabular", "tabular*", "tabularx", "longtable", "tabulary", "supertabular", "xltabular")
CITE_RE = re.compile(
    r"\\(cite|citet|citep|citealt|citealp|citeauthor|citeyear|citeyearpar|citenum|parencite|textcite|"
    r"autocite|footcite|smartcite|nocite|Citet|Citep|Citealt|Citeauthor)(\*?)\s*"
    r"((?:\[[^\]]*\]\s*){0,2})\{([^}]*)\}")
REF_RE = re.compile(r"\\(ref|eqref|autoref|cref|Cref|pageref|nameref|vref|Vref)\*?\{([^}]*)\}")
SENT = "QQPCK{}QQ"


# ---------------------------------------------------------------- helpers
def match_brace(s: str, i: int) -> int:
    """Index just past the brace group starting at s[i] == '{'."""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(s)


def read_group(s: str, i: int) -> tuple[Optional[str], int]:
    """Read one {group} after optional spaces; return (content, end) or (None, i)."""
    j = i
    while j < len(s) and s[j] in " \t\n":
        j += 1
    if j < len(s) and s[j] == "{":
        end = match_brace(s, j)
        return s[j + 1:end - 1], end
    return None, i


def skip_optional(s: str, i: int) -> int:
    j = i
    while j < len(s) and s[j] in " \t\n":
        j += 1
    if j < len(s) and s[j] == "[":
        depth = 0
        while j < len(s):
            if s[j] == "[":
                depth += 1
            elif s[j] == "]":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
    return i


def find_env_end(s: str, name: str, start: int) -> int:
    """Given the index after \\begin{name}, return the index after the matching \\end{name}."""
    pat = re.compile(r"\\(begin|end)\{" + re.escape(name) + r"\}")
    depth = 1
    for m in pat.finditer(s, start):
        depth += 1 if m.group(1) == "begin" else -1
        if depth == 0:
            return m.end()
    return len(s)


def blank(s: str, start: int, end: int) -> str:
    return s[:start] + re.sub(r"[^\n]", " ", s[start:end]) + s[end:]


# ---------------------------------------------------------------- conversion
_CONV = None


def _converter():
    global _CONV
    if _CONV is None:
        from pylatexenc.latex2text import LatexNodes2Text
        _CONV = LatexNodes2Text(math_mode="verbatim", strict_latex_spaces=False, keep_comments=False)
    return _CONV


def _fallback_text(latex: str) -> str:
    text = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", latex)
    return re.sub(r"[{}]", "", text)


def to_text(latex: str) -> str:
    pre = latex
    pre = re.sub(r"\\(?:url|path|nolinkurl)\{([^}]*)\}", r"\1", pre)
    pre = re.sub(r"\\href\{[^}]*\}\{", "{", pre)
    pre = re.sub(r"\\(?:ldots|dots|textellipsis)(?![a-zA-Z])\s?", "... ", pre)
    pre = re.sub(r"(?<!\\)~", " ", pre)
    pre = re.sub(r"\\\\(\[[^\]]*\])?|\\newline(?![a-zA-Z])|\\linebreak(?![a-zA-Z])", " ", pre)
    pre = re.sub(r"\\(?:label|index|vspace\*?|hspace\*?|vskip|hskip|phantom|hphantom|vphantom|bibliographystyle|"
                 r"pagestyle|thispagestyle|graphicspath|pagenumbering)\s*\{[^}]*\}", "", pre)
    pre = re.sub(r"\\(?:setcounter|addtocounter|setlength|addtolength)\s*\{[^}]*\}\s*\{[^}]*\}", "", pre)
    pre = re.sub(r"\\(?:re)?newcommand\*?\s*\{?\\[a-zA-Z@]+\}?\s*(?:\[[^\]]*\])*\s*\{.*?\}\s*$", "", pre, flags=re.M)
    pre = re.sub(r"\\num\{([^}]*)\}", r"\1", pre)
    pre = re.sub(r"\\SI\{([^}]*)\}\{\\percent\}", r"\1%", pre)
    pre = re.sub(r"\\SI\{([^}]*)\}\{([^}]*)\}", r"\1 \2", pre)
    pre = re.sub(r"\\(?:sym|textsuperscript|textsubscript)\{([^}]*)\}", r"\1", pre)
    pre = re.sub(r"\\percent(?![a-zA-Z])", "%", pre)
    pre = re.sub(r"\\(?:noindent|centering|raggedright|small|footnotesize|scriptsize|tiny|normalsize|large|Large|"
                 r"bigskip|medskip|smallskip|clearpage|newpage|maketitle|par|hline|toprule|midrule|bottomrule|"
                 r"singlespacing|doublespacing|onehalfspacing)(?![a-zA-Z])", " ", pre)
    try:
        text = _converter().latex_to_text(pre)
    except Exception:
        text = _fallback_text(pre)
    text = text.replace("\xa0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", " ", text)).strip()


# ---------------------------------------------------------------- reader
class LatexReader:
    def __init__(self, paper: Path, main_file: Optional[str] = None):
        self.root, self.main = self._locate(paper, main_file)
        self.pm = PaperMap(source={"path": str(paper), "main": str(self.main.relative_to(self.root)), "files": []})
        self.counters = {"section": 0, "subsection": 0, "subsubsection": 0, "figure": 0, "table": 0,
                         "equation": 0, "footnote": 0}
        self.theorem_counts: dict = {}
        self.appendix = False
        self.section_path: list = []
        self.n_block = 0
        self.cites: list = []
        self.refs: list = []
        self.label_kind: dict = {}
        self.label_number: dict = {}
        self.cited_keys: list = []
        self.bib: dict = {}
        self.aux_labels: dict = {}
        self._pending: list = []
        self._hidden_spans: list = []

    # -- setup ---------------------------------------------------------
    @staticmethod
    def _locate(paper: Path, main_file: Optional[str]):
        if paper.is_file():
            return paper.parent, paper
        if main_file:
            return paper, paper / main_file
        candidates = [p for p in paper.rglob("*.tex") if "\\documentclass" in p.read_text(errors="replace")]
        if not candidates:
            raise SystemExit(f"No .tex file with \\documentclass in {paper}. Pass --main FILE.")
        candidates.sort(key=lambda p: (p.stem not in ("main", "paper", "manuscript", "draft"), len(p.parts), p.name))
        return paper, candidates[0]

    def _flatten(self):
        try:
            from flachtex import Preprocessor
            ts = Preprocessor(str(self.root)).expand_file(str(self.main.resolve()))
            return ts, str(ts)
        except Exception as exc:
            self.pm.warnings.append(f"Could not follow \\input/\\include ({type(exc).__name__}: {exc}); read the main file only.")
            text = self.main.read_text(encoding="utf-8", errors="replace")
            return None, text

    def _origin(self, i: int) -> Anchor:
        if self.ts is None:
            path, offset = str(self.main), i
        else:
            i = min(max(i, 0), len(self.text) - 1)
            path, offset = self.ts.get_origin(i)
        if path not in self._line_starts:
            try:
                content = Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = ""
            self._line_starts[path] = [0] + [m.end() for m in re.finditer(r"\n", content)]
            rel = str(Path(path).resolve().relative_to(self.root.resolve())) if Path(path).is_absolute() else path
            self._rel[path] = rel
            if rel not in self.pm.source["files"]:
                self.pm.source["files"].append(rel)
        line = bisect.bisect_right(self._line_starts[path], offset)
        return Anchor(file=self._rel[path], line=line)

    def _anchor(self, start: int, end: int) -> Anchor:
        a = self._origin(start)
        b = self._origin(max(start, end - 1))
        if b.file == a.file and b.line and b.line != a.line:
            a.line_end = b.line
        return a

    def _new_id(self) -> str:
        self.n_block += 1
        return f"b{self.n_block:04d}"

    # -- comments and hidden text -----------------------------------------
    def _strip_comments(self, s: str) -> str:
        out = s
        for m in re.finditer(r"\\iffalse\b.*?\\fi\b", s, re.S):
            self.pm.notes.append(Note(kind="latex_comment_block", text=m.group(0)[:2000], anchor=self._anchor(m.start(), m.end()),
                                      detail="\\iffalse block"))
            out = blank(out, m.start(), m.end())
        for m in re.finditer(r"\\begin\{comment\}.*?\\end\{comment\}", out, re.S):
            self.pm.notes.append(Note(kind="latex_comment_block", text=m.group(0)[:2000], anchor=self._anchor(m.start(), m.end()),
                                      detail="comment environment"))
            out = blank(out, m.start(), m.end())
        pos = 0
        for line in out.split("\n"):
            m = re.search(r"(?<!\\)(?:\\\\)*%", line)
            if m:
                c_start = pos + m.end() - 1
                comment = line[m.end() - 1:]
                if comment.strip("% \t"):
                    self.pm.notes.append(Note(kind="latex_comment", text=comment[1:].strip(), anchor=self._origin(c_start)))
                out = out[:c_start] + " " * len(comment) + out[c_start + len(comment):]
            pos += len(line) + 1
        for m in re.finditer(r"\\textcolor\{white\}\{|\{\\color\{white\}", out):
            end = match_brace(out, m.end() - 1) if out[m.end() - 1] == "{" else match_brace(out, m.start())
            self.pm.notes.append(Note(kind="hidden_text", text=to_text(out[m.start():end]), anchor=self._anchor(m.start(), end),
                                      detail="white text"))
            self._hidden_spans.append((m.start(), end, "white text"))
        return out

    # -- bibliography ----------------------------------------------------
    def _load_bib(self, body: str) -> None:
        files = []
        for m in re.finditer(r"\\bibliography\{([^}]*)\}", body):
            files += [f.strip() for f in m.group(1).split(",") if f.strip()]
        for m in re.finditer(r"\\addbibresource(?:\[[^\]]*\])?\{([^}]*)\}", self.text):
            files.append(m.group(1).strip())
        self.pm.metadata["bib_files"] = files
        if not files:
            return
        import bibtexparser
        from bibtexparser import middlewares as mw
        for f in files:
            path = self.root / (f if f.endswith(".bib") else f + ".bib")
            if not path.exists():
                self.pm.warnings.append(f"Bibliography file {path.name} not found.")
                continue
            src = path.read_text(encoding="utf-8", errors="replace")
            raw_lib = bibtexparser.parse_string(src)
            lib = bibtexparser.parse_string(src, append_middleware=[
                mw.LatexDecodingMiddleware(), mw.SeparateCoAuthors(), mw.SplitNameParts()])
            raw_by_key = {e.key: {k: v.value for k, v in e.fields_dict.items()} for e in raw_lib.entries}
            for e in lib.entries:
                self.bib[e.key] = {"entry": e, "raw_fields": raw_by_key.get(e.key, {}), "file": str(path.relative_to(self.root)),
                                   "line": (e.start_line or 0) + 1}
            dups = [getattr(b, "key", None) for b in lib.failed_blocks if b.__class__.__name__ == "DuplicateBlockKeyBlock"]
            if dups:
                self.pm.metadata.setdefault("bib_duplicate_keys", []).extend(dups)
            rel = str(path.relative_to(self.root))
            if rel not in self.pm.source["files"]:
                self.pm.source["files"].append(rel)

    @staticmethod
    def _names(field) -> list:
        out = []
        for n in field or []:
            if hasattr(n, "last"):
                family = " ".join(n.von + n.last).strip()
                given = " ".join(n.first).strip()
                out.append({"family": family, "given": given})
            else:
                parts = str(n).split(",")
                out.append({"family": parts[0].strip(), "given": parts[1].strip() if len(parts) > 1 else ""})
        return out

    def _ref_from_bib(self, key: str, idx: int) -> Reference:
        info = self.bib[key]
        e = info["entry"]
        f = {k: v.value for k, v in e.fields_dict.items()}
        authors = self._names(f.get("author") or f.get("editor"))
        fields = {
            "type": e.entry_type, "title": f.get("title"), "authors": authors,
            "year": str(f.get("year") or f.get("date", ""))[:4] or None,
            "container": f.get("journal") or f.get("journaltitle") or f.get("booktitle") or f.get("institution") or f.get("series"),
            "volume": f.get("volume"), "issue": f.get("number") if e.entry_type == "article" else None,
            "number": f.get("number") if e.entry_type != "article" else None,
            "pages": f.get("pages"), "doi": f.get("doi"), "url": f.get("url"), "publisher": f.get("publisher"),
            "eprint": f.get("eprint"), "note": f.get("note"), "raw_title": info["raw_fields"].get("title"),
        }
        fields = {k: v for k, v in fields.items() if v}
        names = "; ".join(f"{a['family']}, {a['given']}".strip(", ") for a in authors)
        bits = [names, f"({fields.get('year', 'n.d.')})", fields.get("title"), fields.get("container"),
                fields.get("volume"), fields.get("pages"), fields.get("doi") and f"doi:{fields['doi']}"]
        raw = ". ".join(str(b).rstrip(".") for b in bits if b)
        return Reference(id=f"r{idx:03d}", key=key, raw=raw, anchor=Anchor(file=info["file"], line=info["line"]),
                         source="bibtex", fields=fields)

    def _parse_bibitems(self, content: str, offset: int) -> None:
        items = list(re.finditer(r"\\bibitem\s*(\[[^\]]*\])?\s*\{([^}]*)\}", content))
        for k, m in enumerate(items):
            end = items[k + 1].start() if k + 1 < len(items) else len(content)
            text = to_text(content[m.end():end])
            label = (m.group(1) or "")[1:-1]
            year = re.search(r"\b(1[89]\d\d|20\d\d)[a-z]?\b", label or text)
            authors_label = re.sub(r"\(.*", "", label).strip()
            ref = Reference(id=f"r{len(self.pm.references) + 1:03d}", key=m.group(2).strip(), raw=text,
                            anchor=self._anchor(offset + m.start(), offset + end), source="thebibliography",
                            fields={k2: v for k2, v in {"year": year.group(1) if year else None,
                                                         "label": label or None,
                                                         "label_authors": authors_label or None}.items() if v})
            self.pm.references.append(ref)
            self._add_block("reference", text, offset + m.start(), offset + end, raw=content[m.start():end],
                            attrs={"ref": ref.id, "key": ref.key})

    # -- citation and reference rendering ---------------------------------
    def _author_year(self, key: str) -> Optional[tuple]:
        if key in self.bib:
            e = self.bib[key]["entry"]
            f = {k: v.value for k, v in e.fields_dict.items()}
            fams = [a["family"] for a in self._names(f.get("author") or f.get("editor"))]
            year = str(f.get("year") or f.get("date", "n.d."))[:4]
            if not fams:
                return (f.get("title", key)[:30], year)
            names = fams[0] if len(fams) == 1 else (f"{fams[0]} and {fams[1]}" if len(fams) == 2 else f"{fams[0]} et al.")
            return (names, year)
        ref = next((r for r in self.pm.references if r.key == key), None)
        if ref is not None:
            label = ref.fields.get("label") or ""
            m = re.match(r"(.*?)\((\d{4}[a-z]?)\)", label)
            if m:
                return (m.group(1).strip(), m.group(2))
            return (ref.fields.get("label_authors") or key, ref.fields.get("year", "n.d."))
        return None

    def _render_cite(self, info: dict) -> tuple[str, bool]:
        cmd, keys, opts = info["cmd"], info["keys"], info["opts"]
        if cmd == "nocite":
            return "", True
        parts, resolved = [], True
        for key in keys:
            ay = self._author_year(key)
            if ay is None:
                resolved = False
                parts.append(f"[?{key}]")
            else:
                parts.append(ay)
        pre = opts[0] if len(opts) == 2 else ""
        post = opts[-1] if opts else ""
        low = cmd.lower()
        if low in ("citeauthor",):
            return "; ".join(p[0] if isinstance(p, tuple) else p for p in parts), resolved
        if low in ("citeyear",):
            return ", ".join(p[1] if isinstance(p, tuple) else p for p in parts), resolved
        if low in ("citeyearpar",):
            return "(" + ", ".join(p[1] if isinstance(p, tuple) else p for p in parts) + ")", resolved
        if low in ("citet", "textcite"):
            text = "; ".join(f"{p[0]} ({p[1]}{', ' + post if post and i == len(parts) - 1 else ''})" if isinstance(p, tuple) else p
                             for i, p in enumerate(parts))
            return text, resolved
        inner = "; ".join(f"{p[0]}, {p[1]}" if isinstance(p, tuple) else p for p in parts)
        if pre:
            inner = f"{pre} {inner}"
        if post:
            inner = f"{inner}, {post}"
        if low in ("citealt", "citealp"):
            return inner, resolved
        return f"({inner})", resolved

    def _render_ref(self, info: dict) -> tuple[str, bool]:
        out, resolved = [], True
        for label in info["labels"]:
            num = self.aux_labels.get(label) or self.label_number.get(label)
            kind = self.label_kind.get(label, "")
            if num is None:
                resolved = False
                num = "??"
            if info["cmd"] == "eqref":
                out.append(f"({num})")
            elif info["cmd"] in ("autoref", "cref", "Cref", "vref", "Vref"):
                name = {"table": "Table", "figure": "Figure", "section": "Section", "equation": "Equation",
                        "appendix": "Appendix", "footnote": "Footnote"}.get(kind, "")
                if kind == "theorem":
                    name = self.label_kind.get(label + "#env", "").capitalize()
                out.append(f"{name} {num}".strip() if kind != "equation" else f"{name} ({num})")
            elif info["cmd"] == "pageref":
                out.append("?")
            else:
                out.append(str(num))
        return " and ".join(out), resolved

    def _protect(self, latex: str) -> str:
        """Replace citations and references with sentinels."""
        def cite_sub(m):
            opts = re.findall(r"\[([^\]]*)\]", m.group(3) or "")
            keys = [k.strip() for k in m.group(4).split(",") if k.strip()]
            if m.group(1) == "nocite":
                self.cited_keys.extend(k for k in keys if k != "*")
                if "*" in keys:
                    self.cited_keys.append("*")
                return " "
            self.cited_keys.extend(keys)
            self.cites.append({"cmd": m.group(1), "keys": keys, "opts": opts, "raw": m.group(0)})
            return " " + SENT.format(f"C{len(self.cites) - 1}") + " "
        latex = CITE_RE.sub(cite_sub, latex)

        def ref_sub(m):
            labels = [l.strip() for l in m.group(2).split(",") if l.strip()]
            self.refs.append({"cmd": m.group(1), "labels": labels, "raw": m.group(0)})
            return SENT.format(f"R{len(self.refs) - 1}")
        return REF_RE.sub(ref_sub, latex)

    def _render(self, text: str) -> tuple[str, list, list]:
        cites, refs, out, pos = [], [], [], 0
        for m in re.finditer(r"QQPCK([CR])(\d+)QQ", text):
            out.append(text[pos:m.start()])
            start = sum(len(x) for x in out)
            if m.group(1) == "C":
                info = self.cites[int(m.group(2))]
                rendered, ok = self._render_cite(info)
                out.append(rendered)
                cites.append(Citation(keys=info["keys"], start=start, end=start + len(rendered), command=info["cmd"],
                                      raw=info["raw"], resolved=ok))
            else:
                info = self.refs[int(m.group(2))]
                rendered, ok = self._render_ref(info)
                out.append(rendered)
                refs.append(CrossRef(labels=info["labels"], start=start, end=start + len(rendered), command=info["cmd"],
                                     raw=info["raw"], resolved=ok))
            pos = m.end()
        out.append(text[pos:])
        rendered = "".join(out)
        # tidy spaces around rendered citations without moving spans: only collapse runs of spaces
        return rendered, cites, refs

    # -- blocks ------------------------------------------------------------
    def _add_block(self, kind: str, text_latex_or_text: str, start: int, end: int, *, raw: Optional[str] = None,
                   attrs: Optional[dict] = None, parent: Optional[str] = None, level: Optional[int] = None,
                   converted: bool = True) -> Block:
        text = text_latex_or_text if converted else to_text(self._protect(text_latex_or_text))
        block = Block(id=self._new_id(), kind=kind, text=text, anchor=self._anchor(start, end),
                      section=list(self.section_path), level=level, parent=parent,
                      raw=raw if raw is not None else self.text[start:end][:4000], attrs=attrs or {})
        hidden = self._hidden_overlap(start, end)
        if hidden:
            block.attrs["hidden"] = hidden
        self.pm.blocks.append(block)
        self._pending.append(block)
        return block

    def _hidden_overlap(self, start: int, end: int):
        for hs, he, why in self._hidden_spans:
            if hs < end and start < he:
                outside = self.text[start:max(start, hs)] + self.text[min(end, he):end]
                visible = re.sub(r"\\[a-zA-Z@]+\*?|[{}\s]", "", outside)
                return why if not visible else f"partly {why}"
        return None

    def _resolve_pending(self) -> None:
        """Render citations and cross-references once every label and reference is known."""
        for block in self._pending:
            text, cites, refs = self._render(block.text)
            block.text, block.citations, block.crossrefs = self._tidy(text, cites, refs, keep_newlines=block.kind == "table")
        for t in self.pm.tables:
            t.rows = [[self._tidy(self._render(c)[0], [], [])[0] for c in row] for row in t.rows]
            t.notes = self._tidy(self._render(t.notes)[0], [], [])[0]
        by_id = {b.id: b for b in self.pm.blocks}
        for obj in list(self.pm.tables) + list(self.pm.figures):
            if obj.caption_block and obj.caption_block in by_id:
                obj.caption = by_id[obj.caption_block].text
        title = next((b for b in self.pm.blocks if b.kind == "title"), None)
        if title:
            self.pm.title = title.text
        self.pm.authors = [b.text for b in self.pm.blocks if b.kind == "author"]

    @staticmethod
    def _tidy(text: str, cites: list, refs: list, keep_newlines: bool = False):
        """Collapse whitespace and drop spaces before , . ; : ), shifting spans to match."""
        keep, mapping = [], []
        prev_space = True
        for i, ch in enumerate(text):
            is_space = ch.isspace()
            if is_space and prev_space:
                if keep_newlines and ch == "\n" and keep and keep[-1] == " ":
                    keep[-1] = "\n"
                continue
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if is_space and nxt and nxt in ",.;:)" and not (keep_newlines and ch == "\n"):
                continue
            keep.append(("\n" if keep_newlines and ch == "\n" else " ") if is_space else ch)
            mapping.append(i)
            prev_space = is_space
        while keep and keep[-1] == " ":
            keep.pop()
            mapping.pop()
        new = "".join(keep)
        old_to_new = {}
        for n, o in enumerate(mapping):
            old_to_new.setdefault(o, n)

        def shift(pos: int) -> int:
            while pos not in old_to_new and pos < len(text):
                pos += 1
            return old_to_new.get(pos, len(new))
        for span in list(cites) + list(refs):
            span.start, span.end = shift(span.start), shift(span.end) if span.end < len(text) else len(new)
            if span.end < span.start:
                span.end = span.start
        return new, cites, refs

    def _paragraphs(self, start: int, end: int) -> None:
        segment = self.text[start:end]
        for m in re.finditer(r"(?:[^\n]|\n(?![ \t]*\n))+", segment):
            s, e = start + m.start(), start + m.end()
            chunk = self.text[s:e]
            if not re.search(r"[A-Za-z0-9]", re.sub(r"\\[a-zA-Z@]+\*?", "", chunk)):
                continue
            self._text_block("paragraph", s, e)

    def _text_block(self, kind: str, s: int, e: int, **kw) -> Optional[Block]:
        chunk = self.text[s:e]
        footnotes = []
        out, pos = [], 0
        for m in re.finditer(r"\\(footnote|footnotetext|thanks)\s*(\[[^\]]*\])?\s*\{", chunk):
            if m.start() < pos:
                continue
            g_end = match_brace(chunk, m.end() - 1)
            out.append(chunk[pos:m.start()])
            footnotes.append((m.group(1), s + m.end(), s + g_end - 1))
            pos = g_end
        out.append(chunk[pos:])
        body = "".join(out)
        for lm in re.finditer(r"\\label\{([^}]*)\}", body):
            self.label_kind.setdefault(lm.group(1), kw.get("label_kind", "other"))
        if not re.search(r"[A-Za-z0-9]", to_text(re.sub(QQ_RE, "", body))) and not footnotes:
            return None
        block = self._add_block(kind, body, s, e, converted=False, **{k: v for k, v in kw.items() if k != "label_kind"})
        for kind_fn, fs, fe in footnotes:
            if kind_fn == "thanks":
                self._add_block("acknowledgment", self.text[fs:fe], fs, fe, converted=False, parent=block.id)
            else:
                self.counters["footnote"] += 1
                self._add_block("footnote", self.text[fs:fe], fs, fe, converted=False, parent=block.id,
                                attrs={"number": str(self.counters["footnote"])})
        return block

    # -- structure --------------------------------------------------------
    def _heading(self, cmd: str, star: bool, title_latex: str, start: int, end: int) -> None:
        level = HEADING_LEVELS[cmd]
        number = None
        if not star and cmd in ("section", "subsection", "subsubsection"):
            if cmd == "section":
                self.counters["section"] += 1
                self.counters["subsection"] = self.counters["subsubsection"] = 0
                sec = self.counters["section"]
                number = chr(ord("A") + sec - 1) if self.appendix else str(sec)
            elif cmd == "subsection":
                self.counters["subsection"] += 1
                self.counters["subsubsection"] = 0
                number = f"{self._sec_label()}.{self.counters['subsection']}"
            else:
                self.counters["subsubsection"] += 1
                number = f"{self._sec_label()}.{self.counters['subsection']}.{self.counters['subsubsection']}"
        title = to_text(self._protect(title_latex))
        heading_text = f"{number} {title}".strip() if number else title
        depth = max(level, 1)
        self.section_path = self.section_path[:depth - 1] + [heading_text]
        block = self._add_block("heading", heading_text, start, end, level=level,
                                attrs={"number": number, "starred": star, "appendix": self.appendix})
        after = self.text[end:end + 200]
        lm = re.match(r"\s*\\label\{([^}]*)\}", after)
        if lm:
            self.label_kind[lm.group(1)] = "appendix" if self.appendix and level == 1 else "section"
            self.label_number[lm.group(1)] = number
            self.pm.labels.append(Label(name=lm.group(1), kind=self.label_kind[lm.group(1)], number=number,
                                        anchor=block.anchor, block=block.id))

    def _sec_label(self) -> str:
        sec = self.counters["section"]
        return chr(ord("A") + sec - 1) if self.appendix else str(sec)

    def _float(self, env: str, start: int, end: int) -> None:
        content = self.text[start:end]
        is_table = env.startswith("table") or env.startswith("sidewaystable")
        kind = "table" if is_table else "figure"
        self.counters[kind] += 1
        number = (f"{self._sec_label()}{self.counters[kind]}" if False else str(self.counters[kind]))
        if self.appendix and self.pm.metadata.get("appendix_float_prefix"):
            number = f"{self._sec_label()}{self.counters[kind]}"
        labels = re.findall(r"\\label\{([^}]*)\}", content)
        for lab in labels:
            self.label_kind[lab] = kind
            self.label_number[lab] = self.aux_labels.get(lab, number)
        number = self.aux_labels.get(labels[0], number) if labels else number
        cap_m = re.search(r"\\caption\*?\s*(\[[^\]]*\])?\s*\{", content)
        caption_block = None
        caption = ""
        float_id = f"{'t' if is_table else 'f'}{self.counters[kind]}"
        if cap_m:
            cs = start + cap_m.end() - 1
            ce = start + match_brace(content, cap_m.end() - 1)
            caption_block = self._text_block("caption", cs + 1, ce - 1, attrs={"float": kind, "number": number,
                                                                                 "label": labels[0] if labels else None,
                                                                                 "float_id": float_id})
            caption = caption_block.text if caption_block else ""
        for lab in labels:
            self.pm.labels.append(Label(name=lab, kind=kind, number=number, anchor=self._anchor(start, end),
                                        block=caption_block.id if caption_block else None))
        if is_table:
            self._table(content, start, end, number, labels, caption, caption_block, float_id)
        else:
            files = re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", content)
            self.pm.figures.append(Figure(id=float_id, anchor=self._anchor(start, end), caption=caption,
                                          label=labels[0] if labels else None, number=number,
                                          caption_block=caption_block.id if caption_block else None, files=files))

    def _table(self, content: str, start: int, end: int, number, labels, caption, caption_block, float_id) -> None:
        rows, raw_tab = [], ""
        tab_m = re.search(r"\\begin\{(" + "|".join(re.escape(t) for t in TABULAR_ENVS) + r")\}", content)
        notes_parts = []
        if tab_m:
            t_end_rel = find_env_end(content, tab_m.group(1), tab_m.end())
            raw_tab = content[tab_m.start():t_end_rel]
            inner = content[tab_m.end():t_end_rel]
            inner = re.sub(r"\\end\{" + re.escape(tab_m.group(1)) + r"\}$", "", inner)
            j = skip_optional(inner, 0)
            if tab_m.group(1) in ("tabular*", "tabularx", "xltabular"):
                _, j = read_group(inner, j)
            _, j = read_group(inner, j)  # column spec
            inner = inner[j:]
            inner = re.sub(r"\\(?:hline|toprule|midrule|bottomrule|addlinespace|cline\{[^}]*\}|cmidrule(?:\([^)]*\))?\{[^}]*\}|"
                           r"specialrule\{[^}]*\}\{[^}]*\}\{[^}]*\}|endhead|endfoot|endfirsthead|endlastfoot)", " ", inner)
            for raw_row in re.split(r"\\\\(?:\[[^\]]*\])?", inner):
                if not raw_row.strip():
                    continue
                cells = []
                for cell in re.split(r"(?<!\\)&", raw_row):
                    mc = re.match(r"\s*\\multicolumn\{(\d+)\}\{[^}]*\}\{(.*)\}\s*$", cell, re.S)
                    if mc:
                        cells.append(self._cell_text(mc.group(2)))
                        cells.extend([""] * (int(mc.group(1)) - 1))
                    else:
                        cells.append(self._cell_text(cell))
                if any(c for c in cells):
                    rows.append(cells)
            after = content[t_end_rel:]
        else:
            after = content
        for pat in (r"\\begin\{tablenotes\}(.*?)\\end\{tablenotes\}", r"\\floatfoot\{(.*)\}", r"\\caption\*\{(.*?)\}\s*$"):
            for m in re.finditer(pat, content, re.S):
                notes_parts.append(to_text(self._protect(m.group(1))))
        if not notes_parts and tab_m:
            leftover = re.sub(r"\\caption\*?\s*(\[[^\]]*\])?\s*\{.*", "", after, flags=re.S)
            leftover = re.sub(r"\\end\{[^}]*\}|\\begin\{[^}]*\}|\\label\{[^}]*\}", " ", leftover)
            text = to_text(self._protect(leftover))
            if len(re.findall(r"[A-Za-z]{3,}", text)) >= 4:
                notes_parts.append(text)
        notes = " ".join(n for n in notes_parts if n)
        text_rows = [" | ".join(r) for r in rows]
        prefix = "" if re.match(r"\s*notes?\b", notes, re.I) else "Notes: "
        table_text = "\n".join(text_rows) + (f"\n{prefix}{notes}" if notes else "")
        block = self._add_block("table", table_text, start, end, raw=raw_tab[:6000] or content[:4000],
                                attrs={"number": number, "label": labels[0] if labels else None, "float_id": float_id},
                                parent=caption_block.id if caption_block else None)
        self.pm.tables.append(Table(id=float_id, anchor=self._anchor(start, end), caption=caption,
                                    label=labels[0] if labels else None, number=number,
                                    caption_block=caption_block.id if caption_block else None,
                                    rows=rows, notes=notes, raw=raw_tab[:20000] or None))
        block.attrs["table_id"] = float_id

    def _cell_text(self, cell: str) -> str:
        cell = re.sub(r"\$\^\{?(\*{1,3}|\\dagger|\\ddagger)\}?\$", lambda m: m.group(1).replace("\\dagger", "†").replace("\\ddagger", "‡"), cell)
        cell = re.sub(r"\^\{?(\*{1,3})\}?", r"\1", cell)
        return to_text(self._protect(cell)).replace("$", "").strip()

    def _equation(self, env: str, start: int, end: int) -> None:
        content = self.text[start:end]
        labels = re.findall(r"\\label\{([^}]*)\}", content)
        numbered = not env.endswith("*") and env != "displaymath"
        number = None
        if numbered:
            lines = max(1, len(re.findall(r"\\\\", content)) + 1) if env.startswith(("align", "eqnarray", "gather")) else 1
            lines -= len(re.findall(r"\\(?:nonumber|notag)", content))
            first = self.counters["equation"] + 1
            self.counters["equation"] += max(lines, 1)
            number = str(first)
        for lab in labels:
            self.label_kind[lab] = "equation"
            self.label_number[lab] = self.aux_labels.get(lab, number)
        body = re.sub(r"\\begin\{[^}]*\}|\\end\{[^}]*\}|\\label\{[^}]*\}", " ", content)
        block = self._add_block("equation", re.sub(r"\s+", " ", body).strip(), start, end,
                                attrs={"number": number, "labels": labels, "env": env})
        for lab in labels:
            self.pm.labels.append(Label(name=lab, kind="equation", number=self.label_number[lab], anchor=block.anchor, block=block.id))

    def _list(self, env: str, start: int, end: int, inner_start: int, inner_end: int) -> None:
        inner = self.text[inner_start:inner_end]
        items = list(re.finditer(r"\\item\b\s*(\[[^\]]*\])?", inner))
        for k, m in enumerate(items):
            s = inner_start + m.end()
            e = inner_start + (items[k + 1].start() if k + 1 < len(items) else len(inner))
            self._text_block("list_item", s, e, attrs={"env": env, "label": (m.group(1) or "")[1:-1] or None})

    def _theorem(self, env: str, start: int, end: int, inner_start: int, inner_end: int) -> None:
        self.theorem_counts[env] = self.theorem_counts.get(env, 0) + 1
        number = str(self.theorem_counts[env]) if env != "proof" else None
        opt_end = skip_optional(self.text, inner_start)
        title = self.text[inner_start + 1:opt_end - 1] if opt_end > inner_start else None
        labels = re.findall(r"\\label\{([^}]*)\}", self.text[inner_start:inner_end])
        for lab in labels:
            self.label_kind[lab] = "theorem"
            self.label_kind[lab + "#env"] = env
            self.label_number[lab] = self.aux_labels.get(lab, number)
        block = self._text_block("paragraph", opt_end, inner_end, attrs={"env": env, "number": number,
                                                                        "title": to_text(title) if title else None,
                                                                        "labels": labels})
        if block is not None:
            prefix = f"{env.capitalize()} {number}".strip() if number else env.capitalize()
            block.attrs["display"] = prefix
            for lab in labels:
                self.pm.labels.append(Label(name=lab, kind="theorem", number=number, anchor=block.anchor, block=block.id))

    def _front_matter(self) -> None:
        for cmd, kind in (("title", "title"), ("author", "author"), ("date", "front_matter")):
            m = re.search(r"\\" + cmd + r"\s*(\[[^\]]*\])?\s*\{", self.text)
            if not m:
                continue
            g_start = m.end() - 1
            g_end = match_brace(self.text, g_start)
            content = self.text[g_start + 1:g_end - 1]
            if cmd == "author":
                pos = g_start + 1
                for part in re.split(r"\\and\b", content):
                    if part.strip():
                        self._text_block("author", pos, pos + len(part))
                    pos += len(part) + len("\\and")
            else:
                blk = self._text_block(kind, g_start + 1, g_end - 1)
                if cmd == "title" and blk:
                    self.pm.title = blk.text
        for m in re.finditer(r"\\(keywords|JEL|jel|jelcodes|JELcodes|jelclass)\s*\{", self.text):
            g_end = match_brace(self.text, m.end() - 1)
            self._text_block("jel" if "jel" in m.group(1).lower() else "keywords", m.end(), g_end - 1)
        self.pm.authors = [b.text for b in self.pm.blocks if b.kind == "author"]

    def _read_aux(self) -> None:
        aux = self.main.with_suffix(".aux")
        if aux.exists():
            for m in re.finditer(r"\\newlabel\{([^}]*)\}\{\{([^}]*)\}", aux.read_text(errors="replace")):
                self.aux_labels[m.group(1)] = m.group(2)
            self.pm.metadata["aux_file"] = aux.name
        for ext in (".log", ".blg", ".bbl"):
            p = self.main.with_suffix(ext)
            if p.exists():
                self.pm.metadata[f"{ext[1:]}_file"] = p.name

    # -- main ------------------------------------------------------------
    def read(self) -> PaperMap:
        self._line_starts, self._rel = {}, {}
        self.ts, raw = self._flatten()
        self.text = raw
        self.text = self._strip_comments(raw)
        self._read_aux()
        m_class = re.search(r"\\documentclass\s*(\[[^\]]*\])?\s*\{([^}]*)\}", self.text)
        self.pm.metadata["documentclass"] = m_class.group(2) if m_class else None
        self.pm.metadata["documentclass_options"] = (m_class.group(1) or "")[1:-1] if m_class else None
        self.pm.metadata["packages"] = sorted({p.strip() for m in re.finditer(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", self.text)
                                               for p in m.group(1).split(",")})
        if re.search(r"\\renewcommand\s*\{?\\the(?:table|figure)\}?", self.text):
            self.pm.metadata["appendix_float_prefix"] = True
        b = self.text.find("\\begin{document}")
        e = self.text.rfind("\\end{document}")
        body_start = b + len("\\begin{document}") if b >= 0 else 0
        body_end = e if e > body_start else len(self.text)
        self._load_bib(self.text[body_start:body_end])
        self._front_matter()
        self._scan(body_start, body_end)
        self._finalize_references()
        self._resolve_pending()
        return self.pm

    def _scan(self, start: int, end: int) -> None:
        token = re.compile(
            r"\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph)(\*?)\s*(?:\[[^\]]*\])?\s*\{"
            r"|\\begin\{([a-zA-Z*]+)\}|\\\[|\\appendix\b|\\(?:bibliography|printbibliography)\b"
            r"|\\(?:title|author|date|thanks|keywords|JEL|jel|jelcodes)\s*(?:\[[^\]]*\])?\s*\{|\\maketitle\b")
        pos = start
        while pos < end:
            m = token.search(self.text, pos, end)
            if not m:
                self._paragraphs(pos, end)
                break
            self._paragraphs(pos, m.start())
            tok = m.group(0)
            if m.group(1):
                g_end = match_brace(self.text, m.end() - 1)
                self._heading(m.group(1), bool(m.group(2)), self.text[m.end():g_end - 1], m.start(), g_end)
                pos = g_end
            elif m.group(3):
                env = m.group(3)
                env_end = find_env_end(self.text, env, m.end())
                inner_end = self.text.rfind("\\end{" + env + "}", m.end(), env_end)
                inner_end = inner_end if inner_end >= 0 else env_end
                if env == "abstract":
                    self._text_block("abstract", m.end(), inner_end)
                elif env in FLOAT_ENVS:
                    self._float(env, m.start(), env_end)
                elif env in MATH_ENVS:
                    self._equation(env, m.start(), env_end)
                elif env in LIST_ENVS:
                    self._list(env, m.start(), env_end, m.end(), inner_end)
                elif env.rstrip("*") in THEOREM_ENVS:
                    self._theorem(env.rstrip("*"), m.start(), env_end, m.end(), inner_end)
                elif env == "thebibliography":
                    _, j = read_group(self.text, m.end())
                    self.pm.metadata["bib_mode"] = "thebibliography"
                    self._parse_bibitems(self.text[j:inner_end], j)
                elif env in ("keywords",):
                    self._text_block("keywords", m.end(), inner_end)
                elif env in SKIP_ENVS or env in ("document",):
                    pass
                elif env.startswith("tabular"):
                    self._float("table", m.start(), env_end)
                else:
                    self._paragraphs(m.end(), inner_end)
                pos = env_end
            elif tok == "\\[":
                close = self.text.find("\\]", m.end())
                close = close + 2 if close >= 0 else end
                self._add_block("equation", re.sub(r"\s+", " ", self.text[m.end():close - 2]).strip(), m.start(), close,
                                attrs={"number": None, "env": "displaymath"})
                pos = close
            elif tok.startswith("\\appendix"):
                self.appendix = True
                self.counters["section"] = 0
                pos = m.end()
            elif tok.startswith(("\\bibliography", "\\printbibliography")):
                self.pm.metadata.setdefault("bib_mode", "bibtex")
                g = re.match(r"\\bibliography\s*\{[^}]*\}|\\printbibliography(?:\[[^\]]*\])?", self.text[m.start():])
                pos = m.start() + (g.end() if g else len(tok))
            elif tok.startswith("\\maketitle"):
                pos = m.end()
            else:
                g_end = match_brace(self.text, m.end() - 1)
                pos = g_end  # front matter already read

    def _finalize_references(self) -> None:
        if self.pm.metadata.get("bib_mode") == "thebibliography" or not self.bib:
            return
        keys, seen = [], set()
        if "*" in self.cited_keys:
            keys = list(self.bib)
        else:
            for k in self.cited_keys:
                if k not in seen and k in self.bib:
                    keys.append(k)
                    seen.add(k)
        self.pm.metadata["uncited_bib_entries"] = len([k for k in self.bib if k not in seen])
        self.pm.metadata["cited_keys_missing_from_bib"] = sorted({k for k in self.cited_keys if k != "*" and k not in self.bib})
        keys.sort(key=lambda k: (self._author_year(k) or ("", ""))[0].lower())
        heading = Block(id=self._new_id(), kind="heading", text="References", anchor=Anchor(file=self.pm.source["main"]),
                        section=["References"], level=1, attrs={"generated": True})
        self.pm.blocks.append(heading)
        for i, k in enumerate(keys, 1):
            ref = self._ref_from_bib(k, i)
            self.pm.references.append(ref)
            self.pm.blocks.append(Block(id=self._new_id(), kind="reference", text=ref.raw, anchor=ref.anchor,
                                        section=["References"], attrs={"ref": ref.id, "key": k, "generated": True}))


QQ_RE = re.compile(r"QQPCK[CR]\d+QQ")


def read_latex(paper: Path, main_file: Optional[str] = None) -> PaperMap:
    return LatexReader(paper, main_file).read()
