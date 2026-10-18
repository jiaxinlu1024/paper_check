"""CIT-03 missing parts and CIT-04 published citations: the user's checklist items A3 and A4."""

from pathlib import Path

from paper_check.checks import Context
from paper_check.config import PaperSettings
from paper_check.lookups.findings import Builder, format_citation
from paper_check.lookups.policy import field_checks
from paper_check.lookups.records import Record

REC = Record(source="crossref", id="10.1162/003355301753265543", title="The Power of Suggestion",
             authors=[{"family": "Madrian", "given": "Brigitte C."}, {"family": "Shea", "given": "Dennis F."}],
             year=2001, container="Quarterly Journal of Economics", volume="116", issue="4", pages="1149-1187",
             doi="10.1162/003355301753265543", type="journal-article")


def _evs():
    return [{"record": REC, "via": "search", "score": 0.95, "title": 1.0, "authors": None, "container": 1.0}]


def test_parts_missing_from_the_entry_are_listed_with_the_records_values():
    cited = {"title": "The Power of Suggestion", "year": "2001", "container": "Quarterly Journal of Economics",
             "volume": "116", "type": "article"}
    checks = field_checks(cited, _evs())
    missing = {c["field"]: c["found"] for c in checks if c["status"] == "missing"}
    assert missing["doi"] == "10.1162/003355301753265543"
    assert missing["issue"] == "4" and missing["pages"] == "1149-1187"
    assert "volume" not in missing and "year" not in missing


def test_missing_parts_finding_and_fix(tmp_path):
    cited = {"title": "The Power of Suggestion", "year": "2001", "container": "Quarterly Journal of Economics",
             "volume": "116", "type": "article"}
    card = {"ref": "r005", "key": "madrian2001", "verdict": "verified",
            "raw": "Madrian, B. C., & Shea, D. F. (2001). The power of suggestion. Quarterly Journal of Economics, 116.",
            "field_checks": field_checks(cited, _evs()), "matched_in": ["Crossref", "OpenAlex"],
            "matched": {"source": "crossref", "title": REC.title, "authors": ["Madrian, Brigitte C.", "Shea, Dennis F."],
                        "year": 2001, "container": REC.container, "doi": REC.doi}}
    b = Builder(Context(work=tmp_path, settings=PaperSettings()), {})
    b.missing_parts(card)
    assert len(b.findings) == 1
    f = b.findings[0]
    assert f.check_id == "CIT-03" and f.severity == "minor" and f.fix.action == "insert"
    assert "issue: 4" in f.fix.detail and "doi" in f.problem.lower()
    # a DOI printed in the entry is not reported missing
    card["raw"] += " https://doi.org/10.1162/003355301753265543"
    b2 = Builder(Context(work=tmp_path, settings=PaperSettings()), {})
    b2.missing_parts(card)
    assert "DOI" not in b2.findings[0].title


def test_format_citation_gives_a_complete_published_citation():
    link = {"author_list": [{"family": "Madrian", "given": "Brigitte C."}, {"family": "Shea", "given": "Dennis F."}],
            "year": 2001, "title": "The Power of Suggestion", "container": "Quarterly Journal of Economics",
            "volume": "116", "issue": "4", "pages": "1149-1187", "doi": "10.1162/003355301753265543"}
    assert format_citation(link) == ("Madrian, B. C., & Shea, D. F. (2001). The Power of Suggestion. Quarterly "
                                     "Journal of Economics, 116(4), 1149–1187. https://doi.org/10.1162/003355301753265543")
