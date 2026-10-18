"""Data model shared by every stage: the paper map, findings and coverage.

Everything is a dataclass that round-trips through JSON with `to_dict` and
`from_dict`. Files in the work folder:

    paper_map.json            PaperMap, written by `pc.py ingest`
    findings/<producer>.json  FindingSet: findings plus coverage, one file per producer
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1

SEVERITIES = ("critical", "major", "minor", "suggestion")
CONFIDENCES = ("high", "medium", "low")
STATUSES = ("confirmed", "likely", "needs_human", "dropped")
BLOCK_KINDS = (
    "title", "author", "abstract", "keywords", "jel", "heading", "paragraph", "list_item",
    "footnote", "caption", "table", "equation", "reference", "acknowledgment", "front_matter", "other",
)


def _clean(obj: Any) -> Any:
    """Drop None values and empty containers so JSON stays small and readable."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if v is not None and v != [] and v != {}}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


class _Base:
    def to_dict(self) -> dict:
        return _clean(dataclasses.asdict(self))

    @classmethod
    def from_dict(cls, data: dict):
        kwargs = {}
        for f in dataclasses.fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            sub = _NESTED.get((cls.__name__, f.name))
            if sub is not None and value is not None:
                if isinstance(value, list):
                    value = [sub.from_dict(v) for v in value]
                else:
                    value = sub.from_dict(value)
            kwargs[f.name] = value
        return cls(**kwargs)


@dataclass
class Anchor(_Base):
    """Where text came from. LaTeX uses file and lines, PDF uses page and line, Word uses paragraph."""

    file: Optional[str] = None
    line: Optional[int] = None
    line_end: Optional[int] = None
    page: Optional[int] = None
    page_line: Optional[int] = None
    bbox: Optional[list] = None
    paragraph: Optional[int] = None

    def label(self) -> str:
        if self.file:
            if self.line and self.line_end and self.line_end != self.line:
                return f"{self.file}:{self.line}-{self.line_end}"
            return f"{self.file}:{self.line}" if self.line else self.file
        if self.page:
            return f"p. {self.page}, line {self.page_line}" if self.page_line else f"p. {self.page}"
        if self.paragraph:
            return f"paragraph {self.paragraph}"
        return "unknown location"


@dataclass
class Sentence(_Base):
    id: str
    start: int
    end: int


@dataclass
class Citation(_Base):
    """An in-text citation. Offsets index into the block's text."""

    keys: list
    start: int
    end: int
    command: str
    raw: str
    resolved: bool = True


@dataclass
class CrossRef(_Base):
    """A reference to a label, such as "Table 3". Offsets index into the block's text."""

    labels: list
    start: int
    end: int
    command: str
    raw: str
    resolved: bool = True


@dataclass
class Block(_Base):
    id: str
    kind: str
    text: str
    anchor: Anchor
    section: list = field(default_factory=list)
    level: Optional[int] = None
    sentences: list = field(default_factory=list)
    citations: list = field(default_factory=list)
    crossrefs: list = field(default_factory=list)
    parent: Optional[str] = None
    raw: Optional[str] = None
    attrs: dict = field(default_factory=dict)

    def sentence_text(self, sentence: Sentence) -> str:
        return self.text[sentence.start:sentence.end]


@dataclass
class Reference(_Base):
    """One entry of the reference list. `fields` follows CSL-like names:
    title, authors (list of {family, given}), year, container (journal or series),
    volume, issue, pages, doi, url, publisher, type, number (report number), note."""

    id: str
    raw: str
    anchor: Anchor
    source: str
    key: Optional[str] = None
    fields: dict = field(default_factory=dict)


@dataclass
class Table(_Base):
    id: str
    anchor: Anchor
    caption: str = ""
    label: Optional[str] = None
    number: Optional[str] = None
    caption_block: Optional[str] = None
    rows: list = field(default_factory=list)
    notes: str = ""
    raw: Optional[str] = None


@dataclass
class Figure(_Base):
    id: str
    anchor: Anchor
    caption: str = ""
    label: Optional[str] = None
    number: Optional[str] = None
    caption_block: Optional[str] = None
    files: list = field(default_factory=list)


@dataclass
class Label(_Base):
    name: str
    kind: str
    anchor: Anchor
    number: Optional[str] = None
    block: Optional[str] = None


@dataclass
class NumberMention(_Base):
    block: str
    start: int
    end: int
    raw: str
    value: float
    unit: Optional[str] = None
    sentence: Optional[str] = None
    decimals: Optional[int] = None


@dataclass
class Definition(_Base):
    term: str
    kind: str
    definition: str
    block: str
    anchor: Anchor


@dataclass
class Note(_Base):
    """A comment, hidden text or tracked change found in the source."""

    kind: str
    text: str
    anchor: Anchor
    author: Optional[str] = None
    date: Optional[str] = None
    detail: Optional[str] = None


@dataclass
class PaperMap(_Base):
    source: dict
    blocks: list = field(default_factory=list)
    references: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    figures: list = field(default_factory=list)
    labels: list = field(default_factory=list)
    numbers: list = field(default_factory=list)
    definitions: list = field(default_factory=list)
    abbreviations: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    title: str = ""
    authors: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    # ---- convenience -------------------------------------------------
    def block(self, block_id: str) -> Optional[Block]:
        index = getattr(self, "_index", None)
        if index is None:
            index = {b.id: b for b in self.blocks}
            object.__setattr__(self, "_index", index)
        return index.get(block_id)

    def block_order(self) -> dict:
        return {b.id: i for i, b in enumerate(self.blocks)}

    def reference(self, key_or_id: str) -> Optional[Reference]:
        for r in self.references:
            if r.id == key_or_id or r.key == key_or_id:
                return r
        return None

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "PaperMap":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class Evidence(_Base):
    """One piece of proof. `type` is one of:
    quote            verbatim text from the paper (block, text)
    source_quote     verbatim text from a cited work (ref, text, page, version)
    computed_result  inputs, tool, tolerance, output
    checked_absence  scope searched, terms with hit counts, version read
    lookup_record    database, query, record id, url, fields
    script_output    script name and output
    image            path of a saved crop, page, description
    note             anything else"""

    type: str
    text: Optional[str] = None
    block: Optional[str] = None
    ref: Optional[str] = None
    page: Optional[str] = None
    url: Optional[str] = None
    data: dict = field(default_factory=dict)


@dataclass
class Fix(_Base):
    action: str
    original: Optional[str] = None
    replacement: Optional[str] = None
    resolved_when: Optional[str] = None
    detail: Optional[str] = None


@dataclass
class Location(_Base):
    block: Optional[str] = None
    anchor: Optional[Anchor] = None
    section: list = field(default_factory=list)


@dataclass
class Finding(_Base):
    check_id: str
    title: str
    severity: str
    problem: str
    quote: Optional[str] = None
    locations: list = field(default_factory=list)
    related_quotes: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    trajectory: list = field(default_factory=list)
    fix: Optional[Fix] = None
    confidence: str = "medium"
    status: str = "likely"
    producer: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    id: Optional[str] = None

    @property
    def dimension(self) -> str:
        return self.check_id.split("-")[0]


@dataclass
class Coverage(_Base):
    """Outcome of one check: run, not_applicable, or skipped with a reason."""

    check_id: str
    status: str
    reason: Optional[str] = None
    producer: Optional[str] = None
    count: Optional[int] = None
    caveat: Optional[str] = None  # the check ran, but its verdicts rest on something unconfirmed


@dataclass
class FindingSet(_Base):
    producer: str
    findings: list = field(default_factory=list)
    coverage: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "FindingSet":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


_NESTED = {
    ("Block", "anchor"): Anchor, ("Block", "sentences"): Sentence, ("Block", "citations"): Citation,
    ("Block", "crossrefs"): CrossRef, ("Reference", "anchor"): Anchor, ("Table", "anchor"): Anchor,
    ("Figure", "anchor"): Anchor, ("Label", "anchor"): Anchor, ("Definition", "anchor"): Anchor,
    ("Note", "anchor"): Anchor, ("PaperMap", "blocks"): Block, ("PaperMap", "references"): Reference,
    ("PaperMap", "tables"): Table, ("PaperMap", "figures"): Figure, ("PaperMap", "labels"): Label,
    ("PaperMap", "numbers"): NumberMention, ("PaperMap", "definitions"): Definition,
    ("PaperMap", "notes"): Note, ("Finding", "locations"): Location, ("Finding", "evidence"): Evidence,
    ("Finding", "fix"): Fix, ("Location", "anchor"): Anchor, ("FindingSet", "findings"): Finding,
    ("FindingSet", "coverage"): Coverage,
}
