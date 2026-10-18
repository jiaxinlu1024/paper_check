"""Reference lookups: HTTP client, service clients, policy, versions, notices, replications.

Offline tests run on recorded responses in tests/fixtures/lookups/:
    latex_basic_http.json   `pc.py refs` on tests/fixtures/latex_basic
    extra_http.json         the same on the references in extra_refs.json
    fred_sample.json        four rows of FReD's paper-level file (CC BY 4.0, attributed inside)

To re-record, run `pc.py refs` with the network on, with a fresh work folder, then
`lookups.http.export_bundle(work / "cache" / "http", path, note, redact=client.redact)`.
Cached entries never hold keys or the contact email; the redact pass is a second guard.

Tests marked `network` run the whole step live and check the answer key in
tests/fixtures/latex_basic/expected.yaml.
"""

from __future__ import annotations

import csv
import json
import shutil
import time
import urllib.request
from pathlib import Path

import pytest
import yaml

from paper_check.config import Credentials
from paper_check.lookups import http as lhttp
from paper_check.lookups import identifiers, matching, policy, replications, retractions, versions
from paper_check.lookups.http import CacheStore, HttpClient, TransportError, import_bundle
from paper_check.lookups.links import check_url
from paper_check.lookups.openalex import OpenAlex
from paper_check.lookups.records import Record
from paper_check.lookups.run import run_reference_checks
from paper_check.lookups.semanticscholar import SemanticScholar
from paper_check.model import Anchor, Block, FindingSet, PaperMap, Reference
from paper_check.textutil import find_quote

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "lookups"
LATEX = ROOT / "tests" / "fixtures" / "latex_basic"
CHECKS = ("CIT-02", "CIT-03", "CIT-04", "CIT-05", "CIT-12", "CIT-14")
EMAIL = "someone@example.org"
KEY = "SECRETKEY1234567890"


# ---------------------------------------------------------------- helpers
class FakeTransport:
    """Answers from a function of the URL, recording every call."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, method, url, headers, timeout, max_bytes=None):
        self.calls.append((url, dict(headers)))
        result = self.answer(url, headers, len(self.calls))
        if isinstance(result, Exception):
            raise result
        status, hdrs, body = result
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        return status, hdrs, body, url


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def client(tmp_path, answer, **kw):
    clock = Clock()
    t = FakeTransport(answer)
    c = HttpClient(tmp_path / "cache", contact=EMAIL, secrets=[KEY], transport=t, sleep=clock.sleep, clock=clock,
                   rand=lambda: 0.5, **kw)
    return c, t, clock


def fred_root(tmp_path: Path) -> Path:
    """A data folder holding FReD's sample rows as the cached copy of flora.csv."""
    doc = json.loads((FIX / "fred_sample.json").read_text(encoding="utf-8"))
    folder = tmp_path / "data" / "fred"
    folder.mkdir(parents=True)
    with open(folder / "flora.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=doc["columns"])
        w.writeheader()
        for row in doc["rows"]:
            w.writerow(row)
    meta = {"source_url": replications.FLORA_URL, "downloaded_at": "2026-10-17T20:00:00+00:00",
            "downloaded_ts": time.time(), "license": {"checked": True, "name": doc["license"]},
            "attribution": doc["attribution"]}
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return tmp_path / "data"


def build_extra(tmp: Path) -> Path:
    """A work folder whose references are those of extra_refs.json."""
    spec = json.loads((FIX / "extra_refs.json").read_text(encoding="utf-8"))
    blocks, refs = [], []
    for i, r in enumerate(spec["references"], 1):
        rid = f"r{i:03d}"
        anchor = Anchor(file="extra.bib", line=i * 10)
        refs.append(Reference(id=rid, raw=r["raw"], anchor=anchor, source=r["source"], key=r["key"], fields=r["fields"]))
        blocks.append(Block(id=f"b{i:04d}", kind="reference", text=r["raw"], anchor=anchor, section=["References"],
                            attrs={"ref": rid, "key": r["key"]}))
    pm = PaperMap(source={"path": str(tmp), "format": "latex", "paper_dir": str(tmp), "files": ["extra.bib"],
                          "main": "main.tex"}, blocks=blocks, references=refs)
    work = tmp / "paper-check-work"
    work.mkdir(parents=True, exist_ok=True)
    pm.save(work / "paper_map.json")
    return work


def run_recorded(work: Path, bundle: str, data_root: Path, **kw):
    shutil.rmtree(work / "cache", ignore_errors=True)   # only the recorded answers
    import_bundle(FIX / bundle, work / "cache" / "http")
    run_reference_checks(work, offline=True, data_root=data_root, credentials=Credentials(), quiet=True, **kw)
    return load(work)


def load(work: Path):
    fs = FindingSet.load(work / "findings" / "refs.json")
    cards = json.loads((work / "references" / "cards.json").read_text(encoding="utf-8"))["cards"]
    return fs, {c["key"]: c for c in cards}


def by_key(fs: FindingSet) -> dict:
    out: dict = {}
    for f in fs.findings:
        out.setdefault(f.extra.get("key"), {})[f.check_id] = f
    return out


def coverage(fs: FindingSet) -> dict:
    out: dict = {}
    for c in fs.coverage:
        out.setdefault(c.check_id, []).append(c)
    return out


# ---------------------------------------------------------------- HTTP client
def test_user_agent_names_the_project_and_contact(tmp_path):
    c = HttpClient(tmp_path, contact=EMAIL)
    assert c.user_agent.startswith("paper-check/")
    assert c.user_agent.endswith(f"(+https://github.com/jiaxinlu1024/paper_check; mailto:{EMAIL})")
    assert HttpClient(tmp_path).user_agent.endswith("(+https://github.com/jiaxinlu1024/paper_check)")


def test_contact_email_goes_only_to_services_that_ask_for_it(tmp_path):
    """Crossref and OpenAlex ask for a contact for their polite pools; doi.org, NBER pages and data
    repositories get the project URL alone."""
    c, t, _ = client(tmp_path, lambda url, h, n: (200, {"Content-Type": "application/json"}, {"ok": True}))
    for url in ("https://api.crossref.org/works/10.1/x", "https://api.openalex.org/works/W1",
                "https://doi.org/10.1/x", "https://www.nber.org/papers/w1", "https://osf.io/abcd/"):
        c.get(url)
    agents = {url.split("/")[2]: headers["User-Agent"] for url, headers in t.calls}
    assert all(EMAIL in agents[h] for h in ("api.crossref.org", "api.openalex.org"))
    assert not any(EMAIL in agents[h] for h in ("doi.org", "www.nber.org", "osf.io"))
    assert agents["doi.org"].endswith("(+https://github.com/jiaxinlu1024/paper_check)")


def test_secrets_never_reach_cache_keys_urls_or_bodies(tmp_path):
    c, t, _ = client(tmp_path, lambda url, h, n: (200, {"Content-Type": "application/json"},
                                                 {"echo": f"key {KEY} mail {EMAIL}"}))
    r = c.get("https://api.openalex.org/works", {"search": "nudge", "api_key": KEY, "mailto": EMAIL})
    assert KEY in t.calls[0][0]                     # sent to the service
    assert KEY not in r.url and "mailto" not in r.url and "api_key" not in r.url
    files = list((tmp_path / "cache").rglob("*.json"))
    assert files
    stored = files[0].read_text()
    assert KEY not in stored and EMAIL not in stored and "someone%40example.org" not in stored
    # The cache key ignores the secret parameters, so a keyless call hits the same entry.
    r2 = c.get("https://api.openalex.org/works", {"search": "nudge"})
    assert r2.from_cache and len(t.calls) == 1


def test_cache_keeps_positive_7_days_negative_24_hours_and_offline_reads_any_age(tmp_path):
    answers = {"https://api.crossref.org/works/10.1/found": (200, {}, {"ok": 1}),
               "https://api.crossref.org/works/10.1/missing": (404, {}, {"error": "nope"})}
    c, t, _ = client(tmp_path, lambda url, h, n: answers[url.split("?")[0]])
    assert c.get("https://api.crossref.org/works/10.1/found").ok
    assert c.get("https://api.crossref.org/works/10.1/missing").not_found
    store = CacheStore(tmp_path / "cache")
    classes = sorted(e["class"] for e in store.entries())
    assert classes == ["negative", "positive"]
    # Age both entries by two days: the negative one is refetched, the positive one is not.
    for e in store.entries():
        e["fetched_at"] -= 2 * 86400
        store.put(e["key"], e)
    c.get("https://api.crossref.org/works/10.1/found")
    c.get("https://api.crossref.org/works/10.1/missing")
    assert [u.split("?")[0] for u, _ in t.calls[2:]] == ["https://api.crossref.org/works/10.1/missing"]
    # Offline: only the cache, whatever its age; a miss is reported, never fetched.
    off = HttpClient(tmp_path / "cache", offline=True, transport=t)
    for e in store.entries():
        e["fetched_at"] -= 30 * 86400
        store.put(e["key"], e)
    hit = off.get("https://api.crossref.org/works/10.1/found")
    assert hit.ok and hit.from_cache and hit.stale
    miss = off.get("https://api.crossref.org/works/10.1/other")
    assert miss.offline_miss and miss.outcome == "offline"
    assert len(t.calls) == 3


def test_backoff_on_429_and_5xx_honours_retry_after_and_gives_up_on_long_waits(tmp_path):
    seq = [(503, {}, b""), (429, {"Retry-After": "3"}, b""), (200, {}, {"ok": True})]
    c, t, clock = client(tmp_path, lambda url, h, n: seq[n - 1])
    r = c.get("https://api.crossref.org/works/10.1/x")
    assert r.ok and r.attempts == 3
    assert 3.0 in clock.sleeps and any(0.5 <= s <= 1.0 for s in clock.sleeps)  # jittered first backoff, then Retry-After
    c2, t2, clock2 = client(tmp_path / "b", lambda url, h, n: (429, {"Retry-After": "16000"}, {"error": "budget"}))
    r2 = c2.get("https://api.openalex.org/works", {"search": "x"})
    assert r2.status == 429 and len(t2.calls) == 1 and "hours" in r2.error
    assert not list((tmp_path / "b" / "cache").rglob("*.json"))        # errors are never cached
    c3, t3, _ = client(tmp_path / "c", lambda url, h, n: TransportError("timed out"), max_retries=2)
    r3 = c3.get("https://api.crossref.org/works/10.1/y")
    assert r3.status is None and r3.error == "timed out" and len(t3.calls) == 3


def test_rate_limits_space_requests_within_a_bucket(tmp_path):
    c, t, clock = client(tmp_path, lambda url, h, n: (200, {}, {"n": n}))
    for i in range(3):
        c.get(f"https://export.arxiv.org/api/query?id_list={i}", use_cache=False)
    assert sum(clock.sleeps) >= 6.0 - 1e-9          # 3 seconds between arXiv requests
    c2, t2, clock2 = client(tmp_path / "b", lambda url, h, n: (200, {}, {"n": n}))
    c2.get("https://api.crossref.org/works/10.1/a", use_cache=False)
    c2.get("https://api.openalex.org/works/W1", use_cache=False)   # another bucket: no wait
    assert sum(clock2.sleeps) == 0


def test_bundle_round_trip(tmp_path):
    c, t, _ = client(tmp_path, lambda url, h, n: (200, {}, {"n": n}))
    c.get("https://api.crossref.org/works/10.1/a")
    n = lhttp.export_bundle(tmp_path / "cache", tmp_path / "b.json", note="test")
    assert n == 1 and lhttp.import_bundle(tmp_path / "b.json", tmp_path / "copy") == 1
    off = HttpClient(tmp_path / "copy", offline=True)
    assert off.get("https://api.crossref.org/works/10.1/a").json() == {"n": 1}


# ---------------------------------------------------------------- matching and identifiers
def test_family_names_ignore_spaces_accents_and_apostrophes():
    au = matching.compare_authors([{"family": "DellaVigna"}, {"family": "Malmendier"}],
                                  [{"family": "Della Vigna", "given": "Stefano"}, {"name": "Ulrike M. Malmendier"}])
    assert au["fraction"] == 1.0 and au["first_author"] and au["same_order"]
    assert matching.compare_authors([{"family": "O'Donoghue"}], [{"name": "Ted O’Donoghue"}])["fraction"] == 1.0
    assert matching.compare_authors([{"family": "Kőszegi"}], [{"family": "Koszegi"}])["fraction"] == 1.0
    assert matching.compare_authors([{"family": "Brown"}], [{"family": "Kahneman"}, {"family": "Tversky"}])["fraction"] == 0
    truncated = matching.compare_authors([{"family": "Smith"}, {"family": "others"}], [{"family": "Smith"}, {"family": "Li"}])
    assert truncated["truncated"] and truncated["fraction"] == 1.0


def test_title_similarity_handles_symbols_subtitles_and_retraction_markers():
    ts = matching.title_similarity
    assert ts("Save More Tomorrow: Using Behavioral Economics", "Save More Tomorrow™: Using Behavioral Economics") == 1.0
    assert ts("The Power of Suggestion: {I}nertia in 401(k)", "The Power of Suggestion: Inertia in 401(k)") == 1.0
    assert ts("Prospect Theory", "Prospect Theory: An Analysis of Decision under Risk") == 0.9
    assert ts("Present Bias and Gym Attendance: Evidence from the OECD", "Present Bias") < 0.5
    assert ts("Signing at the beginning makes ethics salient",
              "RETRACTED: Signing at the beginning makes ethics salient") == 1.0
    assert ts("Hyperbolic Discounting in Retirement Plans",
              "Prospect Theory: An Analysis of Decision under Risk") < policy.THRESHOLDS["title"]


def test_venues_pages_and_years():
    cs = matching.container_similarity
    assert cs("Quarterly Journal of Economics", ["The Quarterly Journal of Economics"]) == 1.0
    assert cs("Q. J. Econ.", ["The Quarterly Journal of Economics"]) == 1.0
    assert cs("QJE", ["The Quarterly Journal of Economics"]) == 1.0
    assert cs("ReStud", ["The Review of Economic Studies"]) == 1.0
    assert cs("American Economic Review", ["Econometrica"]) < policy.THRESHOLDS["container_drift"]
    assert matching.compare_pages("263--291", "263") is True          # a record with only the first page
    assert matching.compare_pages("1149--87", "1149-1187") is True
    assert matching.compare_pages("443--478", "443-479") is False
    assert matching.year_difference("1998", [1997]) == -1


def test_identifiers_from_fields_and_text():
    ids = identifiers.extract({"doi": "https://doi.org/10.2307/1914185."}, "")
    assert ids["doi"] == "10.2307/1914185"
    ids = identifiers.extract({"container": "National Bureau of Economic Research", "number": "7682"}, "")
    assert ids["nber"] == "7682"
    raw = ("Smith, J. (2020). A title. NBER Working Paper No. 26789; SSRN https://ssrn.com/abstract=3512345; "
           "IZA Discussion Paper No. 12345; CEPR Discussion Paper DP14567; arXiv:2001.01234")
    ids = identifiers.extract({}, raw)
    assert (ids["nber"], ids["ssrn"], ids["iza"], ids["cepr"], ids["arxiv"]) == ("26789", "3512345", "12345", "14567",
                                                                               "2001.01234")
    assert identifiers.extract({"doi": "10.3386/w10819"}, "")["nber"] == "10819"
    assert identifiers.clean_doi("doi:10.1002/(SICI)1099-0771(199706)10:2<83::AID-BDM255>3.0.CO;2-5)") == \
        "10.1002/(sici)1099-0771(199706)10:2"


# ---------------------------------------------------------------- policy
def test_thresholds_live_in_one_place():
    T = policy.THRESHOLDS
    assert (T["title"], T["author"], T["year_tolerance"]) == (0.80, 0.60, 1)     # RefChecker
    assert T["year_window"] == 3 and T["candidate_gap"] == 0.04                 # Crossref matchers
    assert versions.THRESHOLDS is T


def test_identity_rule():
    d = policy.decide_identity
    assert d(1.0, 1.0, -1, False)[0]                      # laibson1997: same work, year drift
    assert not d(0.37, 0.0, -36, False)[0]                # brown2015's DOI record
    assert not d(0.63, 0.0, -1, False)[0]                 # smithson2019's closest candidate
    assert d(1.0, 1.0, 0, True)[0] and not d(1.0, 1.0, 3, True)[0]   # short titles need the year too
    assert d(0.85, 1.0, 2, False)[0] and not d(0.85, 1.0, 5, False)[0]


def test_year_drift_is_judged_on_crossref_dates_and_names_who_disagrees():
    cited = {"title": "Golden Eggs and Hyperbolic Discounting", "authors": [{"family": "Laibson"}], "year": "1998",
             "type": "article"}
    cr = Record("crossref", "10.1162/x", title=cited["title"], authors=[{"family": "Laibson"}], year=1997,
                years=[1997], doi="10.1162/x")
    oa = Record("openalex", "W1", title=cited["title"], authors=[{"name": "David Laibson"}], year=1998, years=[1998])
    evs = [policy.evaluate(cited, cr, "doi"), policy.evaluate(cited, oa, "doi")]
    year = next(c for c in policy.field_checks(cited, evs) if c["field"] == "year")
    assert year["status"] == "differs" and year["contradicting"] == ["crossref"] and year["agreeing"] == ["openalex"]


def test_version_score_weights_authors_above_title():
    wp = {"title": "Overestimating Self-Control: Evidence from the Health Club Industry",
          "authors": [{"family": "DellaVigna"}, {"family": "Malmendier"}], "year": "2004"}
    retitled = Record("crossref", "10.1257/aer.96.3.694", title="Paying Not to Go to the Gym",
                      authors=[{"family": "Della Vigna"}, {"family": "Malmendier"}], year=2006, type="journal-article")
    assert not versions.version_score(wp, retitled)["accepted"]     # too little title left to be sure
    lightly = Record("crossref", "10.1/x", title="Overestimating Self-Control: Evidence from Health Clubs",
                     authors=[{"family": "Della Vigna"}, {"family": "Malmendier"}], year=2006, type="journal-article")
    assert versions.version_score(wp, lightly)["accepted"]
    others = Record("crossref", "10.1/y", title=wp["title"], authors=[{"family": "Smith"}, {"family": "Jones"}],
                    year=2006, type="journal-article")
    assert not versions.version_score(wp, others)["accepted"]       # same title, other authors


def stub_check(tmp_path, fields, raw, answer):
    """Run the policy for one reference against real clients over a fake transport."""
    from paper_check.lookups.services import Services
    c, t, _ = client(tmp_path, answer)
    ref = Reference(id="r001", raw=raw, anchor=Anchor(file="x.bib", line=1), source="bibtex", key="k", fields=fields)
    block = Block(id="b0001", kind="reference", text=raw, anchor=ref.anchor, attrs={"ref": "r001"})
    rc = policy.ReferenceCheck(ref, block, Services(c, Credentials(contact_email=EMAIL)))
    return rc.run(), rc, t


def empty_answers(url, headers, n):
    if "api.crossref.org/works?" in url:
        return 200, {}, {"message": {"items": []}}
    if "api.openalex.org" in url:
        return 200, {}, {"results": []}
    return 404, {}, {"error": "not found"}


def test_not_found_book_gets_low_confidence(tmp_path):
    card, rc, _ = stub_check(tmp_path, {"type": "book", "title": "A Book Nobody Ever Wrote About Nudges",
                                        "authors": [{"family": "Nobody"}], "year": "2011"},
                             "Nobody (2011). A Book Nobody Ever Wrote About Nudges. Imaginary Press.", empty_answers)
    assert card["verdict"] == "not_found_in_databases" and card["needs_web_check"]
    assert card["confidence"] == "low" and any("poorly indexed" in r for r in card["confidence_reasons"])
    assert card["exists"] is None


def test_unreachable_databases_leave_a_reference_unverified_not_fake(tmp_path):
    card, rc, _ = stub_check(tmp_path, {"type": "article", "title": "Some Real Paper on Defaults",
                                        "authors": [{"family": "Smith"}], "year": "2010"},
                             "Smith (2010). Some Real Paper on Defaults. Journal.", lambda u, h, n: TransportError("timed out"))
    assert card["verdict"] == "unverified" and not card["needs_web_check"] and card["kind"] is None
    assert {d["database"] for d in card["databases_failed"]} >= {"Crossref", "OpenAlex"}


def test_one_database_searched_gives_low_confidence(tmp_path):
    def answer(url, headers, n):
        if "api.crossref.org" in url:
            return 200, {}, {"message": {"items": []}}
        return 429, {"Retry-After": "20000"}, {"error": "budget"}
    card, rc, _ = stub_check(tmp_path, {"type": "article", "title": "Present Bias and Gym Attendance: Evidence from the OECD",
                                        "authors": [{"family": "Smithson"}], "year": "2019"},
                             "Smithson (2019). Present Bias and Gym Attendance: Evidence from the OECD.", answer)
    assert card["verdict"] == "not_found_in_databases" and card["searched_databases"] == ["Crossref"]
    assert card["confidence"] == "low" and "only one database could be searched" in card["confidence_reasons"]


def test_journal_article_cited_with_its_working_paper_doi(tmp_path):
    work = {"DOI": "10.3386/w7682", "type": "report", "title": ["The Power of Suggestion: Inertia in 401(k) Participation"
                                                                  " and Savings Behavior"],
            "author": [{"family": "Madrian", "given": "Brigitte"}, {"family": "Shea", "given": "Dennis"}],
            "issued": {"date-parts": [[2000, 5]]}, "publisher": "National Bureau of Economic Research"}
    def answer(url, headers, n):
        if "api.crossref.org/works/10.3386" in url:
            return 200, {}, {"message": work}
        if "api.openalex.org/works/doi:" in url:
            return 200, {}, {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.3386/w7682", "type": "report",
                             "title": work["title"][0], "publication_year": 2000,
                             "authorships": [{"author": {"display_name": "Brigitte C. Madrian"}},
                                             {"author": {"display_name": "Dennis F. Shea"}}]}
        return empty_answers(url, headers, n)
    card, rc, _ = stub_check(tmp_path, {"type": "article", "title": work["title"][0], "year": "2001",
                                        "authors": [{"family": "Madrian"}, {"family": "Shea"}],
                                        "container": "Quarterly Journal of Economics", "doi": "10.3386/w7682"},
                             "Madrian and Shea (2001). The Power of Suggestion. QJE. doi:10.3386/w7682", answer)
    assert card["verdict"] == "metadata_drift"
    version = next(c for c in card["field_checks"] if c["field"] == "version")
    assert version["status"] == "differs" and "working-paper" in version["detail"]


def _findings_for(card):
    from paper_check.checks import Context
    from paper_check.lookups.findings import Builder
    block = Block(id="b0001", kind="reference", text=card["raw"], anchor=Anchor(file="x.bib", line=1))
    b = Builder(Context(work=Path("."), producer="refs"), {card["ref"]: block})
    b.existence(card)
    b.metadata(card)
    return b.findings


def test_real_title_with_other_authors_is_chimeric(tmp_path):
    title = "Inertia in Retirement Saving Plans and the Power of Default Options"
    item = {"DOI": "10.5555/real.1", "type": "journal-article", "title": [title],
            "author": [{"family": "Realauthor", "given": "A."}, {"family": "Coauthor", "given": "B."}],
            "issued": {"date-parts": [[2012]]}, "container-title": ["Journal of Examples"]}
    def answer(url, headers, n):
        if "api.crossref.org/works?" in url:
            return 200, {}, {"message": {"items": [item]}}
        return empty_answers(url, headers, n)
    card, rc, _ = stub_check(tmp_path, {"type": "article", "title": title, "authors": [{"family": "Invented"}],
                                        "year": "2012"}, f"Invented (2012). {title}. Journal of Examples.", answer)
    assert (card["verdict"], card["basis"], card["severity"]) == ("chimeric", "author_conflict", "major")
    f = _findings_for(card)[0]
    assert f.check_id == "CIT-02" and f.title == "Title belongs to a work by other authors" and "Realauthor" in f.problem


def test_wrong_first_author_is_major_metadata_drift(tmp_path):
    title = "Defaults, Framing and Privacy: Why Opting In-Opting Out"
    work = {"DOI": "10.5555/real.2", "type": "journal-article", "title": [title],
            "author": [{"family": "Johnson", "given": "E."}, {"family": "Bellman", "given": "S."},
                       {"family": "Lohse", "given": "G."}],
            "issued": {"date-parts": [[2002]]}, "container-title": ["Marketing Letters"]}
    def answer(url, headers, n):
        if "api.crossref.org/works/10.5555" in url:
            return 200, {}, {"message": work}
        if "api.openalex.org/works/doi:" in url:
            return 200, {}, {"id": "https://openalex.org/W2", "title": title, "publication_year": 2002,
                             "doi": "https://doi.org/10.5555/real.2", "type": "article",
                             "authorships": [{"author": {"display_name": n}} for n in
                                             ("Eric J. Johnson", "Steven Bellman", "Gerald L. Lohse")]}
        return empty_answers(url, headers, n)
    card, rc, _ = stub_check(tmp_path, {"type": "article", "title": title, "year": "2002", "doi": "10.5555/real.2",
                                        "authors": [{"family": "Bellman"}, {"family": "Johnson"}, {"family": "Lohse"}]},
                             f"Bellman, Johnson and Lohse (2002). {title}. doi:10.5555/real.2", answer)
    assert card["verdict"] == "metadata_drift" and card["severity"] == "major"
    f = _findings_for(card)[0]
    assert f.check_id == "CIT-03" and f.severity == "major" and "first author differs" in f.problem
    assert f.fix.action == "investigate"


# ---------------------------------------------------------------- service clients
def test_openalex_drops_a_refused_key_and_retries_keyless(tmp_path):
    def answer(url, headers, n):
        if "api_key=" in url:
            return 403, {}, {"error": "key_not_activated", "message": "Click the link in the email."}
        return 200, {}, {"id": "https://openalex.org/W1", "title": "A title", "publication_year": 2001,
                         "authorships": [], "is_retracted": False}
    c, t, _ = client(tmp_path, answer)
    oa = OpenAlex(c, KEY)
    rec, q = oa.work_by_doi("10.1/x")
    assert rec is not None and rec.title == "A title" and q.status == "ok"
    assert oa.key is None and "key_not_activated" in oa.key_status
    assert "api_key" in t.calls[0][0] and "api_key" not in t.calls[1][0]


def test_openalex_stops_searching_when_the_budget_is_spent(tmp_path):
    c, t, _ = client(tmp_path, lambda url, h, n: (429, {"Retry-After": "16019"}, {"error": "Rate limit exceeded",
                                                                                 "message": "Insufficient budget."}))
    oa = OpenAlex(c)
    recs, q = oa.search_title("Paying Not to Go to the Gym")
    assert recs == [] and q.status == "throttled"
    recs, q2 = oa.search("anything")
    assert q2.status == "skipped" and "budget" in q2.detail and len(t.calls) == 1


def test_semantic_scholar_without_key_backs_off_once_then_skips(tmp_path):
    c, t, clock = client(tmp_path, lambda url, h, n: (429, {}, {"message": "Too Many Requests"}))
    s2 = SemanticScholar(c)
    rec, q = s2.match("Paying Not to Go to the Gym")
    assert rec is None and q.status == "throttled" and len(t.calls) == 2 and len(clock.sleeps) >= 1
    assert "without an API key" in q.detail
    rec, q2 = s2.paper("DOI:10.1257/aer.96.3.694")
    assert q2.status == "skipped" and len(t.calls) == 2
    keyed, tk, _ = client(tmp_path / "k", lambda url, h, n: (200, {}, {"paperId": "p", "title": "T", "authors": []}))
    SemanticScholar(keyed, "S2KEY").paper("DOI:10.1/x")
    assert tk.calls[0][1].get("x-api-key") == "S2KEY"


def test_link_check_tells_blocked_from_dead(tmp_path):
    from paper_check.lookups.services import Services

    def answer(url, headers, n):
        if "blocked" in url:
            return 403, {}, b"<html>bot check</html>"
        if "gone" in url:
            return 404, {}, b"not found"
        if "archive.org" in url:
            return 200, {}, {"archived_snapshots": {"closest": {"available": True, "url": "https://web.archive.org/x",
                                                                "timestamp": "20200101"}}}
        raise TransportError("host name could not be resolved")
    c, t, _ = client(tmp_path, answer)
    s = Services(c, Credentials(contact_email=EMAIL))
    blocked, _ = check_url("https://example.com/blocked", s)
    gone, _ = check_url("https://example.com/gone", s)
    lost, _ = check_url("https://nowhere.invalid/page", s)
    assert (blocked["status"], blocked["dead"]) == ("blocked", False)
    assert (gone["status"], gone["dead"]) == ("missing", True)
    assert (lost["status"], lost["dead"]) == ("unreachable", True)
    assert all(EMAIL not in h.get("User-Agent", "") for u, h in t.calls)   # no contact email to arbitrary sites


def test_nber_page_published_versions():
    from paper_check.lookups.nber import parse_page
    html = ('<meta name="citation_title" content="The Power of Suggestion" />'
            '<meta name="citation_author" content="Brigitte C. Madrian" />'
            '<meta name="citation_publication_date" content="2000/05/01" />'
            '<h2 class="info-grid__title">Published Versions</h2><p>Madrian, Brigitte C. and Dennis F. Shea. '
            '"<a href="https://ideas.repec.org/a/oup/qjecon/v116y2001i4p1149-1187..html">The Power Of Suggestion: '
            'Inertia In 401(k) Participation And Savings Behavior,</a>" Quarterly Journal of Economics, 2001. '
            '<span>citation courtesy of </span><a href="https://ideas.repec.org">RePEc</a></p></div>')
    rec, versions_ = parse_page(html, "7682")
    assert rec.title == "The Power of Suggestion" and rec.year == 2000 and rec.number == "w7682"
    assert versions_[0]["title"] == "The Power Of Suggestion: Inertia In 401(k) Participation And Savings Behavior"


# ---------------------------------------------------------------- notices and replications
def test_notices_merge_sources_and_rank_severity():
    n = retractions.Notices()
    n.add("retraction", "Crossref (publisher)", doi="10.5555/notice.1", date="2021-09-13")
    n.add("retraction", "Crossref (Retraction Watch)", doi="10.5555/NOTICE.1", record_id="1")
    n.flag_retracted("OpenAlex is_retracted")
    items = n.as_list()
    assert len(items) == 1 and len(items[0]["sources"]) == 3
    assert retractions.assess(items)["severity"] == "critical"
    eoc = retractions.assess([{"type": "expression_of_concern", "sources": ["a", "b"]}])
    assert (eoc["severity"], eoc["status"]) == ("major", "confirmed")
    fix = retractions.assess([{"type": "correction", "sources": ["a"]}])
    assert (fix["severity"], fix["status"]) == ("minor", "needs_human")
    back = retractions.assess([{"type": "retraction", "date": "2020-01-01", "sources": ["a"]},
                               {"type": "reinstatement", "date": "2021-01-01", "sources": ["a"]}])
    assert back["kind"] == "reinstated"


def test_retraction_watch_rows_match_by_title_and_author_whatever_the_subject():
    rows = [{"Record ID": "1", "Title": "Made-up Paper on Honesty Nudges", "Subject": "(SOC) Psychology;(HUM) Ethics;",
             "Journal": "Test Journal", "Author": "Ana Example;Bo Sample", "RetractionDate": "3/6/2024 0:00",
             "RetractionDOI": "10.5555/notice.2", "OriginalPaperDate": "1/1/2020 0:00",
             "OriginalPaperDOI": "10.5555/original.2", "RetractionNature": "Retraction", "Reason": "Concerns/Issues About Data;"}]
    rw = retractions.RetractionWatch(rows, {})
    assert rw.for_doi("10.5555/ORIGINAL.2")
    hits = rw.for_title("Made-up paper on honesty nudges", [{"family": "Example"}])
    assert len(hits) == 1 and not rw.for_title("Made-up paper on honesty nudges", [{"family": "Other"}])
    n = retractions.Notices()
    retractions.add_rw_rows(n, hits, "title and first author")
    item = n.as_list()[0]
    assert item["type"] == "retraction" and item["date"] == "2024-03-06" and "Data" in item["reason"]


RW_COLUMNS = ["Record ID", "Title", "Subject", "Institution", "Journal", "Publisher", "Country", "Author", "URLS",
              "ArticleType", "RetractionDate", "RetractionDOI", "RetractionPubMedID", "OriginalPaperDate",
              "OriginalPaperDOI", "OriginalPaperPubMedID", "RetractionNature", "Reason", "Paywalled", "Notes"]


def test_work_without_doi_is_checked_against_the_retraction_watch_file(tmp_path):
    """Made-up work and notice (test prefix 10.5555): matched in OpenAlex and Semantic Scholar
    without a DOI, so notices come from the Retraction Watch file by title and first author."""
    from paper_check.lookups.services import Services
    title = "A Made-up Study of Honesty Pledges at Tax Offices"
    def answer(url, headers, n):
        if "api.openalex.org/works?" in url:
            return 200, {}, {"results": [{"id": "https://openalex.org/W9", "title": title, "publication_year": 2015,
                                          "type": "article", "is_retracted": True,
                                          "authorships": [{"author": {"display_name": "Ana Example"}}]}]}
        if "api.semanticscholar.org" in url and "/match" in url:
            return 200, {}, {"data": [{"paperId": "abc", "title": title, "year": 2015, "authors": [{"name": "Ana Example"}]}]}
        return empty_answers(url, headers, n)
    root = fred_root(tmp_path)
    folder = root / "retraction_watch"
    folder.mkdir()
    with open(folder / "retraction_watch.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=RW_COLUMNS)
        w.writeheader()
        w.writerow({"Record ID": "99", "Title": title, "Subject": "(SOC) Psychology;(HUM) Ethics;", "Author": "Ana Example",
                    "RetractionDate": "5/1/2020 0:00", "RetractionDOI": "10.5555/notice.9",
                    "OriginalPaperDOI": "unavailable", "RetractionNature": "Retraction", "Reason": "Fabrication;"})
    (folder / "meta.json").write_text(json.dumps({"downloaded_ts": time.time(), "source_url": retractions.RW_URL}))
    work = tmp_path / "paper-check-work"
    work.mkdir()
    raw = f"Example, Ana (2015). {title}. Journal of Made-up Results."
    anchor = Anchor(file="x.bib", line=1)
    PaperMap(source={"path": str(tmp_path), "paper_dir": str(tmp_path), "format": "latex"},
             blocks=[Block(id="b0001", kind="reference", text=raw, anchor=anchor, attrs={"ref": "r001"})],
             references=[Reference(id="r001", raw=raw, anchor=anchor, source="bibtex", key="example2015",
                                   fields={"type": "article", "title": title, "authors": [{"family": "Example"}],
                                           "year": "2015"})]).save(work / "paper_map.json")
    c, t, _ = client(tmp_path, answer)
    run_reference_checks(work, services=Services(c, Credentials(contact_email=EMAIL)), data_root=root, quiet=True)
    fs, cards = load(work)
    card = cards["example2015"]
    assert card["verdict"] == "verified" and card["retraction_dois"] == []
    [notice] = card["retraction_notices"]
    assert notice["notice_doi"] == "10.5555/notice.9" and notice["reason"] == "Fabrication"
    assert set(notice["sources"]) == {"OpenAlex is_retracted", "Retraction Watch file (title and first author)"}
    f = by_key(fs)["example2015"]["CIT-05"]
    assert (f.severity, f.status) == ("critical", "confirmed")
    assert not any("gitlab" in u for u, _ in t.calls)          # the local copy was used, not downloaded


def test_replication_outcomes_and_quotes_are_kept_verbatim(tmp_path):
    assert replications.outcome_severity("failed") == "major"
    assert replications.outcome_severity("mixed") == "minor"
    assert replications.outcome_severity("computationally reproducible, robustness challenges") == "minor"
    assert replications.outcome_severity("successful") is None
    root = fred_root(tmp_path)
    from paper_check.lookups import datasets
    ds = datasets.ensure(HttpClient(None, offline=True), "fred", replications.FLORA_URL, "flora.csv",
                         max_bytes=1, max_age_days=7, root=root)
    fred = replications.Fred.load(ds)
    rows = fred.for_doi("10.1073/PNAS.1209746109")
    assert rows and rows[0]["outcome"] == "failed"
    view = replications.replication_view(rows[0], "doi")
    assert view["outcome_quote"] == rows[0]["outcome_quote"] and view["severity"] == "major"


# ---------------------------------------------------------------- the whole step, offline
def test_latex_basic_answer_key_on_recorded_responses(work_copy, tmp_path):
    fs, cards = run_recorded(work_copy, "latex_basic_http.json", fred_root(tmp_path))
    key = yaml.safe_load((LATEX / "expected.yaml").read_text())
    planted = {p["key"]: p for p in key["planted"] if p.get("key") and set(p["checks"]) & {"CIT-02", "CIT-03"}}
    found = by_key(fs)
    # smithson2019: no database matches; Critical, likely, and a web check is still needed.
    s = cards["smithson2019"]
    assert s["verdict"] == "not_found_in_databases" and s["needs_web_check"] and s["web_check"]["query"]
    f = found["smithson2019"]["CIT-02"]
    assert (f.severity, f.status, f.confidence) == (planted["smithson2019"]["severity"], "likely", "medium")
    assert f.extra["needs_web_check"] is True
    # brown2015: the DOI belongs to Kahneman and Tversky (1979); Major.
    b = cards["brown2015"]
    assert b["verdict"] == "chimeric" and b["basis"] == "identifier_conflict"
    assert b["identifier_conflict"]["resolves_to"]["doi"] == "10.2307/1914185"
    assert "Prospect Theory" in b["identifier_conflict"]["resolves_to"]["title"]
    assert found["brown2015"]["CIT-02"].severity == planted["brown2015"]["severity"] == "major"
    # laibson1997: year 1998 against 1997 in two databases; Minor, with an exact fix.
    l = cards["laibson1997"]
    assert l["verdict"] == "metadata_drift"
    year = next(c for c in l["field_checks"] if c["field"] == "year")
    assert (year["status"], year["cited"], year["found"]) == ("differs", "1998", 1997)
    f = found["laibson1997"]["CIT-03"]
    assert f.severity == planted["laibson1997"]["severity"] == "minor"
    assert (f.fix.original, f.fix.replacement, f.status) == ("1998", "1997", "confirmed")
    # The five correct references are verified by two databases and draw no finding.
    for k in ("dellavigna2006", "kahneman1979", "madrian2001", "odonoghue1999", "thaler2004"):
        assert cards[k]["verdict"] == "verified", k
        assert len(cards[k]["agreeing_databases"]) >= 2 and not cards[k]["needs_web_check"]
        assert k not in found
    assert {f.check_id for f in fs.findings} == {"CIT-02", "CIT-03"} and len(fs.findings) == 3


def test_every_finding_quotes_its_reference_block_and_carries_proof(work_copy, tmp_path):
    from paper_check.verify import verify_finding
    fs, _ = run_recorded(work_copy, "latex_basic_http.json", fred_root(tmp_path))
    pm = PaperMap.load(work_copy / "paper_map.json")
    for f in fs.findings:
        block = pm.block(f.locations[0].block)
        assert block.kind == "reference" and f.quote == block.text and find_quote(f.quote, block.text)
        assert any(e.type == "lookup_record" and e.data.get("database") for e in f.evidence)
        assert len(f.trajectory) >= 3 and f.fix is not None and f.fix.resolved_when
        assert not verify_finding(pm, work_copy, f, {})["failed"]


def test_cards_hold_the_evidence(work_copy, tmp_path):
    fs, cards = run_recorded(work_copy, "latex_basic_http.json", fred_root(tmp_path))
    assert len(cards) == 8
    for card in cards.values():
        for k in ("ref", "key", "raw", "verdict", "matched", "similarity", "field_checks", "queries",
                  "databases_reached", "version_links", "retraction_notices", "replications", "needs_web_check", "links"):
            assert k in card, (card["key"], k)
        assert card["queries"] and all("database" in q and "status" in q for q in card["queries"])
    d = cards["dellavigna2006"]
    assert d["matched"]["doi"] == "10.1257/aer.96.3.694" and d["similarity"]["authors"] == 1.0
    assert set(d["databases_reached"]) >= {"Crossref", "OpenAlex"}
    assert {c["field"] for c in d["field_checks"]} >= {"title", "authors", "year", "container", "pages"}


def test_coverage_is_run_for_all_six_checks(work_copy, tmp_path):
    fs, _ = run_recorded(work_copy, "latex_basic_http.json", fred_root(tmp_path))
    cov = coverage(fs)
    assert set(cov) == set(CHECKS)
    for cid in CHECKS:
        assert [c.status for c in cov[cid]] == ["run"], cid
    assert "5 verified" in cov["CIT-02"][0].reason


def test_extra_references_versions_notices_replications_links(tmp_path):
    work = build_extra(tmp_path / "extra")
    fs, cards = run_recorded(work, "extra_http.json", fred_root(tmp_path))
    spec = json.loads((FIX / "extra_refs.json").read_text())["expected"]
    found = by_key(fs)
    for key, exp in spec.items():
        assert cards[key]["verdict"] == exp["verdict"], key
        for cid in ("CIT-04", "CIT-05", "CIT-12", "CIT-14"):
            if cid in exp:
                assert found[key][cid].severity == exp[cid], (key, cid)
    # NBER w7682 links to its QJE version; w10819, retitled on publication, is left alone.
    link = found["madrian2000wp"]["CIT-04"].extra["published_version"]
    assert link["doi"] == spec["madrian2000wp"]["published_doi"] and link["confidence"] == "high"
    assert any("NBER" in b for b in link["basis"])
    assert cards["dellavigna2004wp"]["version_check"]["is_working_paper"] and not cards["dellavigna2004wp"]["version_links"]
    # Notices: the retraction is confirmed by Crossref and OpenAlex; the concern by Crossref.
    shu = found["shu2012"]["CIT-05"]
    assert (shu.severity, shu.status) == ("critical", "confirmed") and "10.1073/pnas.2115397118" in shu.problem
    assert found["mazar2008"]["CIT-05"].title == "Cited work carries an expression of concern"
    # Replications are quoted verbatim from FReD and never called false.
    sample = {r["doi_o"].lower(): r for r in json.loads((FIX / "fred_sample.json").read_text())["rows"]}
    rep = found["shu2012"]["CIT-14"]
    assert rep.status == "needs_human" and sample["10.1073/pnas.1209746109"]["outcome_quote"] in rep.problem
    assert "not a verdict that the original result is false" in rep.problem
    # Links: the DOI typo gets the matched DOI; a 404 is dead; a live URL is fine.
    typo = found["thaler2004typo"]["CIT-12"]
    assert (typo.fix.original, typo.fix.replacement) == ("10.1086/380085x", spec["thaler2004typo"]["replacement_doi"])
    assert found["mazar2008"]["CIT-12"].title == "Link is dead"
    assert [l["status"] for l in cards["kahneman1979url"]["links"]] == [spec["kahneman1979url"]["url_status"]]


def test_offline_without_cache_records_skips_never_passes(work_copy, tmp_path):
    shutil.rmtree(work_copy / "cache", ignore_errors=True)
    run_reference_checks(work_copy, offline=True, data_root=tmp_path / "empty", credentials=Credentials(), quiet=True)
    fs, cards = load(work_copy)
    assert fs.findings == []
    assert all(c["verdict"] == "unverified" for c in cards.values())
    cov = coverage(fs)
    for cid in CHECKS:
        statuses = {c.status for c in cov[cid]}
        assert "run" not in statuses, cid
        assert all(c.reason for c in cov[cid]), cid
    assert "offline" in cov["CIT-02"][0].reason and "FReD not available" in cov["CIT-14"][0].reason


def test_a_data_file_too_large_is_skipped_with_the_reason(work_copy, tmp_path, monkeypatch):
    def too_large(self, url, dest, *, max_bytes, bucket=None, timeout=180.0):
        return lhttp.Download(False, url, size=99_000_000, status=200,
                              reason=f"the file is 99.0 MB, above the {max_bytes / 1e6:.0f} MB limit")
    monkeypatch.setattr(HttpClient, "download", too_large)
    shutil.rmtree(work_copy / "cache", ignore_errors=True)
    import_bundle(FIX / "latex_basic_http.json", work_copy / "cache" / "http")
    from paper_check.lookups.services import Services
    services = Services(HttpClient(work_copy / "cache" / "http", sleep=lambda s: None), Credentials())
    services.http.offline = False
    services.http.transport = lambda *a, **k: (_ for _ in ()).throw(TransportError("no network in this test"))
    run_reference_checks(work_copy, services=services, data_root=tmp_path / "empty", quiet=True)
    fs, cards = load(work_copy)
    cov = coverage(fs)["CIT-14"]
    assert [c.status for c in cov] == ["skipped"] and "above the 60 MB limit" in cov[0].reason
    assert cards["laibson1997"]["verdict"] == "metadata_drift"       # everything else still ran from the cache


def test_network_off_in_settings_means_cache_only(work_copy, tmp_path):
    settings = json.loads((work_copy / "settings.json").read_text()) if (work_copy / "settings.json").exists() else {}
    settings["network"] = False
    (work_copy / "settings.json").write_text(json.dumps(settings))
    shutil.rmtree(work_copy / "cache", ignore_errors=True)
    run_reference_checks(work_copy, data_root=tmp_path / "empty", credentials=Credentials(), quiet=True)
    fs, _ = load(work_copy)
    assert fs.settings["offline"] is True and "network is off" in coverage(fs)["CIT-02"][0].reason


def test_limit_checks_the_first_references_and_says_so(work_copy, tmp_path):
    fs, cards = run_recorded(work_copy, "latex_basic_http.json", fred_root(tmp_path), limit=3)
    assert len(cards) == 3
    statuses = [c.status for c in coverage(fs)["CIT-02"]]
    assert statuses == ["run", "skipped"] and "--limit 3" in coverage(fs)["CIT-02"][1].reason


def test_quick_mode_checks_existence_only(work_copy, tmp_path):
    settings = json.loads((work_copy / "settings.json").read_text()) if (work_copy / "settings.json").exists() else {}
    settings["mode"] = "quick"
    (work_copy / "settings.json").write_text(json.dumps(settings))
    fs, cards = run_recorded(work_copy, "latex_basic_http.json", fred_root(tmp_path))
    cov = coverage(fs)
    assert cov["CIT-02"][0].status == "run" and cov["CIT-03"][0].status == "run"
    for cid in ("CIT-04", "CIT-05", "CIT-12", "CIT-14"):
        assert [c.status for c in cov[cid]] == ["skipped"] and "quick mode" in cov[cid][0].reason


# ---------------------------------------------------------------- live
def _online() -> bool:
    ua = HttpClient(None).user_agent + " tests"
    for _ in range(3):
        try:
            req = urllib.request.Request("https://api.crossref.org/works?rows=0", headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=20):
                return True
        except Exception:
            time.sleep(2)
    return False


@pytest.mark.network
def test_network_latex_basic_answer_key(latex_map, tmp_path):
    if not _online():
        pytest.skip("Crossref is not reachable from here")
    _, src = latex_map
    work = tmp_path / "paper-check-work"
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("cache", "findings", "references"))
    assert run_reference_checks(work, quiet=True) == 0
    fs, cards = load(work)
    found = by_key(fs)
    smith = found["smithson2019"]["CIT-02"]
    assert cards["smithson2019"]["verdict"] == "not_found_in_databases" and cards["smithson2019"]["needs_web_check"]
    assert (smith.severity, smith.status) == ("critical", "likely") and smith.confidence in ("medium", "low")
    assert cards["brown2015"]["verdict"] == "chimeric" and found["brown2015"]["CIT-02"].severity == "major"
    assert cards["laibson1997"]["verdict"] == "metadata_drift"
    assert found["laibson1997"]["CIT-03"].severity == "minor" and found["laibson1997"]["CIT-03"].fix.replacement == "1997"
    for k in ("dellavigna2006", "kahneman1979", "madrian2001", "odonoghue1999", "thaler2004"):
        assert cards[k]["verdict"] == "verified", (k, cards[k]["databases_failed"])
    cov = coverage(fs)
    assert all(c.status == "run" for c in cov["CIT-02"])


@pytest.mark.network
def test_network_extra_references(tmp_path):
    if not _online():
        pytest.skip("Crossref is not reachable from here")
    work = build_extra(tmp_path / "extra")
    assert run_reference_checks(work, quiet=True) == 0
    fs, cards = load(work)
    found = by_key(fs)
    assert found["shu2012"]["CIT-05"].severity == "critical"
    assert found["madrian2000wp"]["CIT-04"].extra["published_version"]["doi"] == "10.1162/003355301753265543"
    assert not cards["dellavigna2004wp"]["version_links"]
    assert found["thaler2004typo"]["CIT-12"].fix.replacement == "10.1086/380085"


def test_an_article_known_only_as_its_working_paper_is_not_drift(tmp_path):
    """A 1994 journal article whose databases hold only the 1993 working paper: the year and the
    missing journal details are not errors in the entry, and the working paper's DOI is not proposed."""
    wp = {"DOI": "10.3386/w4509", "type": "report", "title": ["Minimum Wages and Employment: A Case Study of the "
                                                                  "Fast Food Industry"],
          "author": [{"family": "Card", "given": "David"}, {"family": "Krueger", "given": "Alan"}],
          "issued": {"date-parts": [[1993, 4]]}, "publisher": "National Bureau of Economic Research"}

    def answer(url, headers, n):
        if "api.crossref.org/works?" in url:
            return 200, {}, {"message": {"items": [wp]}}
        return empty_answers(url, headers, n)
    card, rc, _ = stub_check(tmp_path, {"type": "article-journal", "title": wp["title"][0], "year": "1994",
                                        "authors": [{"family": "Card"}, {"family": "Krueger"}],
                                        "container": "American Economic Review", "volume": "84", "pages": "772-793"},
                             "Card, D., & Krueger, A. B. (1994). Minimum wages and employment: A case study of the fast "
                             "food industry. American Economic Review, 84(4), 772-793.", answer)
    assert card["verdict"] in ("verified", "single_source"), card["field_checks"]
    fields = {c["field"]: c for c in card["field_checks"]}
    assert fields["version"]["status"] == "note" and "doi" not in fields and "year" not in fields


def test_a_record_that_lists_its_authors_twice_is_not_an_author_mismatch():
    from paper_check.lookups.matching import compare_authors
    found = [{"family": "Carlson", "given": "Andrea"}, {"family": "Page", "given": "Elina"}] * 2
    au = compare_authors([{"family": "Carlson"}, {"family": "Page"}], found)
    assert au["record_not_cited"] == [] and au["fraction"] == 1.0 and au["record_count"] == 2


def test_a_working_paper_known_only_as_its_later_chapter_is_a_version_not_drift(tmp_path):
    """A 2011 working paper that the databases know only as its 2015 book chapter, with the title's words
    reordered: the chapter's year, book and DOI are not errors in the entry, and CIT-04 proposes the chapter."""
    chapter = {"DOI": "10.5555/chapter.7", "type": "book-chapter",
               "title": ["Labor Supply over the Life Cycle and Commuting Time"],
               "author": [{"family": "Doe", "given": "Jane"}, {"family": "Roe", "given": "Rex"}],
               "issued": {"date-parts": [[2015]]}, "container-title": ["Essays on Work and Travel"]}

    def answer(url, headers, n):
        if "api.crossref.org/works?" in url:
            return 200, {}, {"message": {"items": [chapter]}}
        return empty_answers(url, headers, n)
    raw = ("Doe, J., & Roe, R. (2011). Commuting Time and Labor Supply over the Life Cycle. Working Papers. "
           "https://ideas.repec.org/p/xyz/wpaper/012.html")
    card, rc, _ = stub_check(tmp_path, {"type": "report", "title": "Commuting Time and Labor Supply over the Life Cycle",
                                        "authors": [{"family": "Doe"}, {"family": "Roe"}], "year": "2011",
                                        "container": "Working Papers"}, raw, answer)
    assert card["verdict"] in ("verified", "single_source"), card["field_checks"]
    fields = {c["field"]: c for c in card["field_checks"]}
    assert fields["version"]["status"] == "note" and "published version" in fields["version"]["detail"]
    assert not {"year", "container", "doi"} & set(fields)
    out = versions.find_published_versions(rc, rc.s)
    assert out["is_working_paper"] and out["links"] and out["links"][0]["doi"] == "10.5555/chapter.7"


def test_a_copy_in_a_data_repository_does_not_correct_the_entry(tmp_path):
    """A 2012 agency report whose only record is a copy deposited in a data repository in 2024: the
    deposit's year and DOI are not proposed as corrections."""
    deposit = {"DOI": "10.5281/zenodo.0000001", "type": "dataset", "title": ["Household Travel Survey Summary Tables, 2010"],
               "author": [{"name": "Example Transit Agency"}], "issued": {"date-parts": [[2024]]},
               "container-title": ["Zenodo"]}

    def answer(url, headers, n):
        if "api.crossref.org/works?" in url:
            return 200, {}, {"message": {"items": [deposit]}}
        return empty_answers(url, headers, n)
    raw = ("Example Transit Agency. (2012). Household Travel Survey Summary Tables, 2010. "
           "https://www.example.gov/travel/summary.html")
    card, rc, _ = stub_check(tmp_path, {"type": "report", "title": "Household Travel Survey Summary Tables, 2010",
                                        "authors": [{"family": "Example Transit Agency"}], "year": "2012"}, raw, answer)
    assert card["verdict"] in ("verified", "single_source"), card["field_checks"]
    fields = {c["field"]: c for c in card["field_checks"]}
    assert fields["version"]["status"] == "note" and "deposited" in fields["version"]["found"]
    assert not {"year", "doi"} & set(fields)
    assert not [f for f in _findings_for(card) if f.check_id == "CIT-03"]


def test_same_authors_other_paper_is_not_the_published_version():
    """Unrelated titles of similar length score about 0.5 on edit distance; the same team's other
    paper is not a published version of this one."""
    wp = {"title": "Bus Rapid Transit and Commuter Welfare in Mid-Sized Cities",
          "authors": [{"family": "Doe"}, {"family": "Roe"}, {"family": "Poe"}], "year": "2012"}
    other = Record("crossref", "10.5555/other", title="Teacher Turnover, Class Size, and Student Welfare",
                   authors=[{"family": "Doe"}, {"family": "Roe"}, {"family": "Poe"}], year=2011, type="journal-article")
    assert not versions.version_score(wp, other)["accepted"]
    retitled = Record("crossref", "10.5555/same", title="Commuter Welfare and Bus Rapid Transit: Evidence from Mid-Sized Cities",
                      authors=[{"family": "Doe"}, {"family": "Roe"}, {"family": "Poe"}], year=2015,
                      type="journal-article")
    assert versions.version_score(wp, retitled)["accepted"]


def test_a_working_paper_series_name_is_not_compared_with_the_institution():
    cited = {"title": "Bus Rapid Transit and Commuter Welfare in Mid-Sized Cities", "authors": [{"family": "Doe"}],
             "year": "2012", "container": "Working Paper Series", "type": "article",
             "doi": "10.3386/w99999"}
    cr = Record("crossref", "10.3386/w99999", title=cited["title"], authors=[{"family": "Doe"}], year=2012,
                type="report", doi="10.3386/w99999", publisher="National Bureau of Economic Research")
    oa = Record("openalex", "W9", title=cited["title"], authors=[{"name": "J. Doe"}], year=2012, type="article",
                container="National Bureau of Economic Research")
    evs = [policy.evaluate(cited, cr, "doi"), policy.evaluate(cited, oa, "doi")]
    checks = {c["field"]: c for c in policy.field_checks(cited, evs)}
    assert checks["container"]["status"] == "unknown" and checks["container"]["found"]
    assert not [c for c in checks.values() if c["status"] == "differs"]


def test_a_wrong_year_and_a_missing_doi_in_one_entry_are_one_finding():
    from paper_check.checks import Context
    from paper_check.lookups.findings import Builder
    raw = "Doe, J. (2010). Ferry Fares and Island Tourism. Journal of Examples, 3, 1-20."
    record = {"source": "crossref", "doi": "10.5555/ferry.1", "title": "Ferry Fares and Island Tourism",
              "authors": ["Doe, Jane"], "year": 2011, "container": "Journal of Examples"}
    card = {"ref": "r001", "key": "doe2010", "raw": raw, "verdict": "metadata_drift", "severity": "minor",
            "matched": record, "matched_in": ["Crossref", "OpenAlex"], "queries": [], "anchor": {},
            "field_checks": [
                {"field": "year", "cited": "2010", "found": 2011, "status": "differs",
                 "sources": {"crossref": [2011], "openalex": [2011]}, "contradicting": ["crossref", "openalex"],
                 "agreeing": []},
                {"field": "doi", "cited": None, "found": "10.5555/ferry.1", "status": "missing",
                 "sources": {"crossref": "10.5555/ferry.1"}}]}
    block = Block(id="b0001", kind="reference", text=raw, anchor=Anchor(file="x.bib", line=1))
    b = Builder(Context(work=Path("."), producer="refs"), {"r001": block})
    b.metadata(card)
    b.missing_parts(card)
    cit03 = [f for f in b.findings if f.check_id == "CIT-03"]
    assert len(cit03) == 1
    f = cit03[0]
    assert "year" in f.title and "DOI missing" in f.title and "10.5555/ferry.1" in f.problem
    assert "10.5555/ferry.1" in f.fix.detail and f.fix.replacement == "2011"


def _book_card(tmp_path, raw, year="2021"):
    book = {"DOI": "10.5555/book.1", "type": "book", "title": ["Methods for Counting Ferries"],
            "author": [{"family": "Doe", "given": "Jane"}], "issued": {"date-parts": [[2009]]},
            "publisher": "Example Press"}

    def answer(url, headers, n):
        if "api.crossref.org/works?" in url:
            return 200, {}, {"message": {"items": [book]}}
        return empty_answers(url, headers, n)
    card, rc, _ = stub_check(tmp_path, {"type": "book", "title": "Methods for Counting Ferries",
                                        "authors": [{"family": "Doe"}], "year": year, "publisher": "Example Press"},
                             raw, answer)
    return card


def test_a_later_year_for_a_book_is_an_edition_question_not_a_wrong_year(tmp_path):
    from paper_check.checks import Context
    from paper_check.lookups.findings import Builder
    raw = "Doe, J. (2021) Methods for Counting Ferries. Example Press."
    card = _book_card(tmp_path, raw)
    assert card["verdict"] != "metadata_drift", card["field_checks"]
    year = next(c for c in card["field_checks"] if c["field"] == "year")
    assert year["status"] == "edition" and not year["edition_named"]
    assert not [c for c in card["field_checks"] if c["status"] == "missing"]     # no first-edition DOI proposed
    block = Block(id="b0001", kind="reference", text=raw, anchor=Anchor(file="x.bib", line=1))
    b = Builder(Context(work=Path("."), producer="refs"), {card["ref"]: block})
    b.metadata(card)
    b.editions(card)
    assert [(f.check_id, f.severity, f.status) for f in b.findings] == [("CIT-03", "suggestion", "needs_human")]
    assert "2009" in b.findings[0].problem and "2nd ed." in b.findings[0].fix.detail


def test_a_book_that_names_its_edition_needs_no_finding(tmp_path):
    from paper_check.checks import Context
    from paper_check.lookups.findings import Builder
    raw = "Doe, J. (2021) Methods for Counting Ferries (2nd ed.). Example Press."
    card = _book_card(tmp_path, raw)
    year = next(c for c in card["field_checks"] if c["field"] == "year")
    assert year["status"] == "edition" and year["edition_named"]
    block = Block(id="b0001", kind="reference", text=raw, anchor=Anchor(file="x.bib", line=1))
    b = Builder(Context(work=Path("."), producer="refs"), {card["ref"]: block})
    b.metadata(card)
    b.editions(card)
    assert not b.findings
