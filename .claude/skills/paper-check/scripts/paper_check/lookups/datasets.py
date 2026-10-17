"""Local copies of open data files: the FORRT Replication Database and Retraction Watch.

Each lives in its own folder under ~/.paper-check/cache/ (PAPER_CHECK_CACHE overrides the
root), next to a meta.json that records where the file came from, when, its size, its
SHA-256 and its license as checked at download time. A copy older than its refresh age is
downloaded again when the network is on; offline, any copy is used and its age reported.
A file above its size limit, or one that cannot be fetched, is not an error: the caller
records skipped coverage with the reason.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..config import HOME
from .http import HttpClient


def cache_root() -> Path:
    env = os.environ.get("PAPER_CHECK_CACHE")
    return Path(env) if env else HOME / "cache"


@dataclass
class Dataset:
    name: str
    path: Optional[Path] = None
    meta: dict = field(default_factory=dict)
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.path is not None and self.path.exists()

    def age_days(self) -> Optional[float]:
        ts = self.meta.get("downloaded_ts")
        return round((time.time() - ts) / 86400, 1) if ts else None

    def describe(self) -> dict:
        out = {k: v for k, v in self.meta.items() if k not in ("downloaded_ts",)}
        out["name"] = self.name
        if self.age_days() is not None:
            out["age_days"] = self.age_days()
        if self.reason:
            out["unavailable"] = self.reason
        return out


def ensure(http: HttpClient, name: str, url: str, filename: str, *, max_bytes: int, max_age_days: float,
           root: Optional[Path] = None, license_check: Optional[Callable[[HttpClient], dict]] = None,
           extra_meta: Optional[dict] = None) -> Dataset:
    folder = Path(root or cache_root()) / name
    data, meta_path = folder / filename, folder / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    except (OSError, ValueError):
        meta = {}
    age = (time.time() - meta["downloaded_ts"]) / 86400 if meta.get("downloaded_ts") else None
    if data.exists() and (http.offline or (age is not None and age <= max_age_days)):
        return Dataset(name, data, meta)
    if http.offline:
        return Dataset(name, None, meta, "offline, and no local copy has been downloaded yet")
    dl = http.download(url, data, max_bytes=max_bytes)
    if not dl.ok:
        if data.exists():
            meta = dict(meta, refresh_failed=dl.reason)
            return Dataset(name, data, meta)
        return Dataset(name, None, {"source_url": dl.url}, f"could not download {dl.url}: {dl.reason}")
    meta = {"source_url": dl.url, "downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "downloaded_ts": time.time(), "size": dl.size, "sha256": dl.sha256,
            "last_modified": dl.last_modified, **(extra_meta or {})}
    if license_check is not None:
        try:
            meta["license"] = license_check(http)
        except Exception as exc:  # the license check must never break the run
            meta["license"] = {"checked": False, "reason": f"{type(exc).__name__}: {exc}"}
    try:
        folder.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return Dataset(name, data, meta)
