"""The service clients for one run, built from config.Credentials and one HttpClient."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import Credentials
from .arxiv import Arxiv
from .crossref import Crossref
from .datacite import DataCite
from .doiorg import DoiOrg
from .http import HttpClient
from .nber import Nber
from .openalex import OpenAlex
from .semanticscholar import SemanticScholar


class Services:
    def __init__(self, http: HttpClient, credentials: Optional[Credentials] = None):
        creds = credentials or Credentials()
        self.http = http
        self.credentials = creds.summary()
        self.crossref = Crossref(http, creds.contact_email)
        self.openalex = OpenAlex(http, creds.openalex_api_key)
        self.semanticscholar = SemanticScholar(http, creds.semantic_scholar_api_key)
        self.doiorg = DoiOrg(http)
        self.datacite = DataCite(http)
        self.arxiv = Arxiv(http)
        self.nber = Nber(http)

    @classmethod
    def create(cls, work: Path, *, offline: bool = False, credentials: Optional[Credentials] = None,
               cache_dir: Optional[Path] = None, **http_options) -> "Services":
        creds = credentials if credentials is not None else Credentials.load()
        http = HttpClient(cache_dir if cache_dir is not None else Path(work) / "cache" / "http", offline=offline,
                          contact=creds.contact_email,
                          secrets=[creds.openalex_api_key, creds.semantic_scholar_api_key, creds.repec_access_code],
                          **http_options)
        return cls(http, creds)

    def status(self) -> dict:
        """What the run could use, without revealing any credential."""
        notes = {
            "crossref": "polite pool (contact email sent)" if self.crossref.mailto else "public pool: no contact email set",
            "openalex": f"API key {self.openalex.key_status}"
                        + (f"; {self.openalex.search_blocked}" if self.openalex.search_blocked else ""),
            "semanticscholar": ("API key configured" if self.semanticscholar.key else "no API key")
                               + (f"; {self.semanticscholar.blocked}" if self.semanticscholar.blocked else ""),
            "repec": "not used: RePEc API access needs an access code, which is not configured"
                     if not self.credentials.get("repec_access_code") else
                     "access code configured, but the RePEc client is not written yet",
        }
        return {"offline": self.http.offline, "credentials": self.credentials, "services": notes,
                "requests": self.http.stats}
