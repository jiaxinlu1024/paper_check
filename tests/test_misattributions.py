"""Structure of the classic-misattributions list used by BEH-15 and the citation judge.

These checks run offline. They do not re-verify DOIs or quotes against their sources;
that was done when the entries were written (see the header of the YAML file).
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
GUIDELINES = ROOT / ".claude" / "skills" / "paper-check" / "references" / "guidelines"
YAML_PATH = GUIDELINES / "misattributions.yaml"
MD_PATH = GUIDELINES / "misattributions.md"

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
URL_RE = re.compile(r"^https?://\S+$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ENTRY_FIELDS = ("id", "topic", "finding", "terms", "original", "often_miscited_as", "rule", "evidence", "status")
ORIGINAL_FIELDS = ("authors", "year", "title", "container", "volume", "issue", "pages", "doi")
STATUSES = {"verified", "likely"}
MAX_QUOTE_CHARS = 400


@pytest.fixture(scope="module")
def data():
    with open(YAML_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def entries(data):
    return data["entries"]


def _label(entry):
    return entry.get("id", "<no id>")


def test_header_and_date(data):
    text = YAML_PATH.read_text(encoding="utf-8")
    assert text.startswith("#"), "the file opens with a header comment"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data["checked_on"]))
    assert data["codes"] and data["evidence_kinds"]


def test_entry_count(entries):
    assert 30 <= len(entries) <= 45


def test_required_fields(entries):
    for e in entries:
        missing = [f for f in ENTRY_FIELDS if f not in e]
        assert not missing, f"{_label(e)}: missing {missing}"
        for f in ("id", "topic", "finding", "rule"):
            assert isinstance(e[f], str) and e[f].strip(), f"{_label(e)}: empty {f}"
        assert e["terms"] and all(isinstance(t, str) and t.strip() for t in e["terms"]), _label(e)
        assert e["often_miscited_as"], f"{_label(e)}: no common misattribution listed"
        for m in e["often_miscited_as"]:
            assert isinstance(m.get("source"), str) and m["source"].strip(), _label(e)
            assert isinstance(m.get("why"), str) and m["why"].strip(), _label(e)
        assert isinstance(e["evidence"], list), _label(e)
        assert e["status"] in STATUSES, f"{_label(e)}: status {e['status']!r}"


def test_original_fields(entries):
    for e in entries:
        o = e["original"]
        missing = [f for f in ORIGINAL_FIELDS if f not in o]
        assert not missing, f"{_label(e)}: original is missing {missing}"
        assert o["authors"] and all(isinstance(a, str) and a.strip() for a in o["authors"]), _label(e)
        assert isinstance(o["year"], int) and 1700 <= o["year"] <= 2100, _label(e)
        assert isinstance(o["title"], str) and o["title"].strip(), _label(e)
        assert isinstance(o["container"], str) and o["container"].strip(), _label(e)


def test_ids_unique_and_slugs(entries):
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for i in ids:
        assert ID_RE.match(i), f"id {i!r} is not a short slug"


def test_dois_look_like_dois(entries):
    for e in entries:
        doi = e["original"]["doi"]
        if doi is not None:
            assert isinstance(doi, str) and DOI_RE.match(doi), f"{_label(e)}: bad DOI {doi!r}"
        for m in e["often_miscited_as"]:
            if m.get("doi") is not None:
                assert isinstance(m["doi"], str) and DOI_RE.match(m["doi"]), f"{_label(e)}: bad DOI {m['doi']!r}"


def test_verified_entries_have_doi_and_quoted_evidence(entries):
    for e in entries:
        if e["status"] != "verified":
            continue
        assert e["original"]["doi"], f"{_label(e)}: verified without a DOI"
        good = [ev for ev in e["evidence"]
                if isinstance(ev.get("url"), str) and URL_RE.match(ev["url"])
                and isinstance(ev.get("quote"), str) and ev["quote"].strip()]
        assert good, f"{_label(e)}: verified without an evidence item that has a URL and a quote"


def test_likely_entries_explain_what_is_missing(entries):
    for e in entries:
        if e["status"] == "likely":
            assert isinstance(e.get("notes"), str) and e["notes"].strip(), f"{_label(e)}: likely without notes"


def test_evidence_items(data, entries):
    kinds = set(data["evidence_kinds"])
    for e in entries:
        for ev in e["evidence"]:
            assert URL_RE.match(ev.get("url", "")), f"{_label(e)}: evidence without a URL"
            assert isinstance(ev.get("quote"), str) and ev["quote"].strip(), f"{_label(e)}: evidence without a quote"
            assert len(ev["quote"]) <= MAX_QUOTE_CHARS, f"{_label(e)}: quote longer than {MAX_QUOTE_CHARS} characters"
            assert ev.get("kind") in kinds, f"{_label(e)}: unknown evidence kind {ev.get('kind')!r}"


def test_codes_and_replication(data, entries):
    codes = set(data["codes"])
    for e in entries:
        for m in e["often_miscited_as"]:
            if "code" in m:
                assert m["code"] in codes, f"{_label(e)}: unknown code {m['code']!r}"
        if "replication" in e:
            rep = e["replication"]
            assert isinstance(rep.get("note"), str) and rep["note"].strip(), _label(e)
            assert URL_RE.match(rep.get("url", "")), f"{_label(e)}: replication without a source URL"


def test_entries_grouped_by_topic(entries):
    seen, last = set(), None
    for e in entries:
        if e["topic"] != last:
            assert e["topic"] not in seen, f"topic {e['topic']!r} appears in two separate blocks"
            seen.add(e["topic"])
            last = e["topic"]


def test_markdown_companion_lists_every_entry(entries):
    text = MD_PATH.read_text(encoding="utf-8")
    assert "S4" in text and "S5" in text
    for e in entries:
        assert f"`{e['id']}`" in text, f"{_label(e)} is missing from misattributions.md"
