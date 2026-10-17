"""Settings: user-level credentials and per-paper options.

User file, never committed:  ~/.paper-check/config.yaml
    contact_email, openalex_api_key, semantic_scholar_api_key, repec_access_code, core_api_key
Environment variables override it: PAPER_CHECK_CONTACT_EMAIL, OPENALEX_API_KEY,
SEMANTIC_SCHOLAR_API_KEY, REPEC_ACCESS_CODE, CORE_API_KEY.

Per-paper file, optional:  paper-check.yaml beside the paper
    venue, field, study_type, language_variant, mode, network, sources, paid_pdfs,
    min_severity. The YAML key `field` is stored as `research_field`.

`pc.py ingest` resolves the settings once (paper-check.yaml plus command-line
options) and saves them to paper-check-work/settings.json. Later commands read
that file, so options such as --venue are given once.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

HOME = Path(os.path.expanduser("~")) / ".paper-check"
USER_CONFIG = HOME / "config.yaml"
OUTPUT_REPORT = "paper-check-report.md"
OUTPUT_FINDINGS = "paper-check-findings.json"
OUTPUT_WORK = "paper-check-work"
SETTINGS_FILE = "settings.json"
MODES = ("quick", "standard", "deep")

_ENV = {
    "contact_email": "PAPER_CHECK_CONTACT_EMAIL",
    "openalex_api_key": "OPENALEX_API_KEY",
    "semantic_scholar_api_key": "SEMANTIC_SCHOLAR_API_KEY",
    "repec_access_code": "REPEC_ACCESS_CODE",
    "core_api_key": "CORE_API_KEY",
}


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    import yaml  # PyYAML is a core requirement

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


@dataclass
class Credentials:
    contact_email: Optional[str] = None
    openalex_api_key: Optional[str] = None
    semantic_scholar_api_key: Optional[str] = None
    repec_access_code: Optional[str] = None
    core_api_key: Optional[str] = None

    @classmethod
    def load(cls) -> "Credentials":
        data = _load_yaml(USER_CONFIG)
        values = {k: data.get(k) for k in _ENV}
        for key, env in _ENV.items():
            if os.environ.get(env):
                values[key] = os.environ[env]
        return cls(**values)

    def summary(self) -> dict:
        """Which credentials are set, without revealing them."""
        return {k: bool(v) for k, v in asdict(self).items()}


@dataclass
class PaperSettings:
    venue: Optional[str] = None
    research_field: str = "behavioral economics"
    study_type: Optional[str] = None
    language_variant: Optional[str] = None
    mode: str = "deep"
    network: bool = True
    sources: Optional[str] = None
    paid_pdfs: bool = False
    min_severity: str = "suggestion"
    extra: dict = field(default_factory=dict)

    @classmethod
    def _build(cls, data: dict, paper_dir: Path, overrides: Optional[dict]) -> "PaperSettings":
        data = dict(data)
        if "field" in data:
            data["research_field"] = data.pop("field")
        data.update({k: v for k, v in (overrides or {}).items() if v is not None})
        known = {f for f in cls.__dataclass_fields__}
        extra = {k: v for k, v in data.items() if k not in known}
        settings = cls(**{k: v for k, v in data.items() if k in known})
        settings.extra.update(extra)
        if settings.mode not in MODES:
            raise SystemExit(f"Unknown mode {settings.mode!r}. Use one of: {', '.join(MODES)}.")
        if settings.sources is None:
            default = Path(paper_dir) / "sources"
            settings.sources = str(default) if default.is_dir() else None
        elif not Path(settings.sources).is_absolute():
            settings.sources = str((Path(paper_dir) / settings.sources).resolve())
        return settings

    @classmethod
    def load(cls, paper_dir: Path, overrides: Optional[dict] = None) -> "PaperSettings":
        """Settings from paper-check.yaml beside the paper, plus overrides."""
        return cls._build(_load_yaml(Path(paper_dir) / "paper-check.yaml"), paper_dir, overrides)

    @classmethod
    def for_work(cls, work: Path, overrides: Optional[dict] = None) -> "PaperSettings":
        """Settings saved at ingest time, plus overrides. Falls back to the paper folder."""
        work = Path(work)
        paper_dir = work.parent
        pm_path = work / "paper_map.json"
        if pm_path.exists():
            paper_dir = Path(json.loads(pm_path.read_text(encoding="utf-8"))["source"].get("paper_dir") or paper_dir)
        path = work / SETTINGS_FILE
        if path.exists():
            return cls._build(json.loads(path.read_text(encoding="utf-8")), paper_dir, overrides)
        return cls.load(paper_dir, overrides)

    def save(self, work: Path) -> Path:
        path = Path(work) / SETTINGS_FILE
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def summary(self) -> str:
        bits = [f"mode {self.mode}", f"venue {self.venue or 'none'}", f"network {'on' if self.network else 'off'}",
                f"field {self.research_field}"]
        if self.study_type:
            bits.append(f"study type {self.study_type}")
        if self.language_variant:
            bits.append(f"{self.language_variant} English")
        bits.append(f"sources folder {self.sources or 'none'}")
        if self.paid_pdfs:
            bits.append("paid PDFs allowed")
        if self.min_severity != "suggestion":
            bits.append(f"minimum severity {self.min_severity}")
        return ", ".join(bits)


def paper_dir_of(paper: Path) -> Path:
    paper = Path(paper).resolve()
    return paper if paper.is_dir() else paper.parent


def work_dir_for(paper: Path, output: Optional[str] = None) -> Path:
    base = Path(output).resolve() if output else paper_dir_of(paper)
    return base / OUTPUT_WORK
