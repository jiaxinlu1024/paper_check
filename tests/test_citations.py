"""Citation support scripts: propositions, full-text cascade, sources folder, STW terms, scan."""

import datetime as dt
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from paper_check.citations import fulltext, prepare as prep, scan as scanmod, terms
from paper_check.citations.fulltext import Cascade, Fetcher
from paper_check.model import Anchor, Block, Citation, PaperMap, Reference, Sentence
from paper_check.textutil import find_quote

FIX = Path(__file__).resolve().parent / "fixtures" / "citations"
RECORDED = FIX / "recorded"
FILLER = ["Further lines of ordinary prose give this page a realistic amount of text for extraction.",
          "They mention nothing that the tests search for, and they keep the text layer checks honest."]


def make_pdf(pages):
    """A small valid PDF with one text line per string (Helvetica), for tests without LibreOffice."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for lines in pages:
        content = ["BT", "/F1 11 Tf", "14 TL", "72 740 Td"]
        for line in lines:
            content.append("(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*")
        content.append("ET")
        stream = "\n".join(content).encode("cp1252")
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (len(objs)))
        kids.append(len(objs))
    objs[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % len(kids)
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def _lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


# ================================================================ propositions
def test_gym_sentence_is_one_proposition_with_its_reference(latex_map):
    pm, _ = latex_map
    props = prep.extract_propositions(pm)
    gym = [p for p in props if "gym attendance" in p["sentence"]]
    assert len(gym) == 1
    p = gym[0]
    assert p["sentence"] == "Earlier studies have also examined present bias in gym attendance (Madrian and Shea, 2001)."
    assert p["keys"] == ["madrian2001"]
    assert p["ref_ids"] == [pm.reference("madrian2001").id]
    assert p["citation"] == "(Madrian and Shea, 2001)"
    assert p["claim_type"] == "topic" and p["section"] == ["1 Introduction"]
    block = pm.block(p["block"])
    sentence = next(s for s in block.sentences if s.id == p["sentence_id"])
    assert block.sentence_text(sentence) == p["sentence"]
    # it opens its paragraph, so the sentence before comes from the previous paragraph
    assert p["previous_sentence"].endswith("in the firm studied by Madrian and Shea (2001).")


def test_citation_groups_claim_types_and_unresolved_keys(latex_map):
    pm, _ = latex_map
    props = prep.extract_propositions(pm)
    assert [p["id"] for p in props] == [f"c{i:03d}" for i in range(1, 8)]
    by_keys = {tuple(p["keys"]): p for p in props}
    rid = lambda key: pm.reference(key).id  # noqa: E731
    assert by_keys[("laibson1997", "odonoghue1999")]["ref_ids"] == [rid("laibson1997"), rid("odonoghue1999")]
    trio = by_keys[("thaler2004", "smithson2019", "brown2015")]
    assert trio["ref_ids"] == [rid("thaler2004"), rid("smithson2019"), rid("brown2015")]
    assert trio["claim_type"] == "topic"
    kt = by_keys[("kahneman1979",)]
    assert kt["claim_type"] == "origin" and "number" in kt["claim_types"] and kt["cues"]["number"] == ["2.25"]
    dv = by_keys[("dellavigna2006",)]
    assert dv["narrative"] and dv["claim_type"] == "finding"
    lu = by_keys[("lu2024",)]
    assert lu["ref_ids"] == [] and lu["unresolved_keys"] == ["lu2024"]
    assert sum(1 for p in props if p["keys"] == ["madrian2001"]) == 2
    # 401(k) is a plan name, not a number claim
    raised = next(p for p in props if "401(k) participation" in p["sentence"])
    assert raised["claim_type"] == "direction" and "number" not in raised["claim_types"]


def test_prepare_offline_writes_every_output(work_copy, capsys):
    assert prep.prepare(work_copy, offline=True) == 0
    out = work_copy / "citations"
    pm = PaperMap.load(work_copy / "paper_map.json")
    props = _lines(out / "propositions.jsonl")
    assert len(props) == 7
    by_ref = json.loads((out / "by_ref.json").read_text())
    madrian = pm.reference("madrian2001").id
    assert by_ref["references"][madrian]["propositions"] == [p["id"] for p in props if p["keys"] == ["madrian2001"]]
    assert list(by_ref["unresolved_keys"]) == ["lu2024"]
    status = json.loads((out / "status.json").read_text())
    assert status["offline"] is True
    assert status["references"]["cited"] == 8 and status["references"]["full_text"] == 0
    assert status["readiness"]["state"] == "no_full_text"
    meta = json.loads((out / "sources" / f"{madrian}.json").read_text())
    assert meta["status"] == "not_found" and meta["note"].startswith("cannot verify: no full text")
    assert meta["abstract_only"] is False and "fetched" in meta
    assert "Citation support: 7 propositions" in capsys.readouterr().out


# ================================================================ scan
SYNTH = """[[page 1]]
Automatic Enrollment and Saving
We study automatic enrollment in 401(k) plans. Employees procras-
tinate in changing their contribution rate, and inertia is strong.

[[page 2]]
Present bias, or present-biased preferences, are modelled with quasi-hyperbolic
discounting where β = 0.7. Self-
control problems matter, and present bias explains the delay.

[[page 3]]
The gymnasium is not a gym. Nothing about exercise. Studies of defaults and gyms.
Later we return to present bias once more, in a long and otherwise unrelated discussion of plan fees,
investment menus, fund expense ratios, account statements and employer matching formulas.
"""


def test_scan_counts_hits_with_pages_and_ranks_passages():
    terms_ = ["present bias", "procrastinat*", "self-control", "gym", "gym attendance", r"re:β\s*=\s*0\.\d+", "study"]
    result = scanmod.scan(SYNTH, terms_, context=80, top=4)
    t = {e["term"]: e for e in result["terms"]}
    assert t["present bias"]["hits"] == 3 and t["present bias"]["pages"] == [2, 3]
    assert t["procrastinat*"]["hits"] == 1 and t["procrastinat*"]["pages"] == [1]   # hyphenated across a line
    assert t["self-control"]["forms"] == {"Self-control": 1}                     # "Self-" + line break + "control"
    assert t["gym"]["hits"] == 2 and t["gym"]["forms"] == {"gym": 1, "gyms": 1}  # not "gymnasium"
    assert t["study"]["forms"] == {"study": 1, "Studies": 1}
    assert t[r"re:β\s*=\s*0\.\d+"]["hits"] == 1 and t[r"re:β\s*=\s*0\.\d+"]["pages"] == [2]
    assert t["gym attendance"]["hits"] == 0 and t["gym attendance"]["pages"] == []
    assert result["terms_without_hits"] == ["gym attendance"]
    assert result["pages_scanned"]["count"] == 3
    for p in result["passages"]:  # passages are verbatim: verify.py can find any quote taken from them
        assert find_quote(p["text"], SYNTH)
        assert "[[page" not in p["text"]
    # ranking: page 2 has both terms and the phrase twice; page 3 mentions present bias once in a long passage
    passages = scanmod.scan(SYNTH, ["present bias", "quasi-hyperbolic"], context=120, top=3)["passages"]
    assert [p["page"] for p in passages] == [2, 3]
    assert passages[0]["terms"] == {"present bias": 2, "quasi-hyperbolic": 1}
    assert passages[0]["score"] > passages[1]["score"] > 0


def test_hits_in_the_reference_list_are_marked_and_ranked_lower():
    body = "\n".join(["Workers rarely change their contribution rate once enrolled."] * 12)
    text = (f"[[page 1]]\n{body}\nSome workers report weak self-control when saving.\n\n"
            "[[page 2]]\nReferences\nDoe, J. (2001). Self-Control and Saving. Journal of Tests.\n")
    result = scanmod.scan(text, ["self-control"], context=60)
    entry = result["terms"][0]
    assert entry["hits"] == 2 and entry["hits_in_reference_list"] == 1
    assert result["reference_list"]["pages"] == [2]
    assert result["passages"][0]["page"] == 1 and "in_reference_list" not in result["passages"][0]
    assert result["passages"][1]["in_reference_list"] is True


def test_scan_without_any_hit_returns_the_closest_passages():
    result = scanmod.scan(SYNTH, ["gym attendance", "exercise habit"], top=2)
    assert all(e["hits"] == 0 for e in result["terms"]) and result["total_hits"] == 0
    assert result["passage_basis"].startswith("no term occurs")
    assert result["passages"] and result["passages"][0]["page"] == 3   # where "gym" and "exercise" appear


def test_scan_command_prints_and_appends_the_absence_record(work_copy, capsys):
    pm = PaperMap.load(work_copy / "paper_map.json")
    rid = pm.reference("madrian2001").id
    src = work_copy / "citations" / "sources"
    src.mkdir(parents=True, exist_ok=True)
    (src / f"{rid}.txt").write_text(SYNTH, encoding="utf-8")
    (src / f"{rid}.json").write_text(json.dumps({
        "ref": rid, "status": "full_text", "source": "sources", "version": "published", "pages": 3,
        "pages_with_text": 3, "abstract_only": False, "fetched": "2026-10-17"}), encoding="utf-8")
    assert scanmod.scan_command(work_copy, "madrian2001", ["gym attendance", "present bias"], 100, 3) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["ref"] == rid and record["key"] == "madrian2001"
    assert record["version_read"]["version"] == "published" and record["scope"] == "full text, PDF pages 1-3"
    assert {e["term"]: e["hits"] for e in record["terms"]} == {"gym attendance": 0, "present bias": 3}
    assert record["passages"] and record["opening"].startswith("Automatic Enrollment and Saving")
    scans = work_copy / "citations" / "scans" / f"{rid}.jsonl"
    assert len(_lines(scans)) == 1
    scanmod.scan_command(work_copy, rid, ["inertia"], 100, 3)
    capsys.readouterr()
    assert [r["terms"][0]["term"] for r in _lines(scans)] == ["gym attendance", "inertia"]
    # no cached text: the record says so, and the exit code is 1
    assert scanmod.scan_command(work_copy, "smithson2019", ["gym"], 100, 3) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "no_text"


def test_abstract_only_text_carries_the_caveat(work_copy, capsys):
    pm = PaperMap.load(work_copy / "paper_map.json")
    rid = pm.reference("thaler2004").id
    src = work_copy / "citations" / "sources"
    src.mkdir(parents=True, exist_ok=True)
    (src / f"{rid}.txt").write_text("[[abstract]]\nA program that commits employees to save more later.\n")
    (src / f"{rid}.json").write_text(json.dumps({"ref": rid, "status": "abstract_only", "abstract_only": True,
                                                 "version": "abstract", "pages": 0}))
    scanmod.scan_command(work_copy, rid, ["choice architecture"], 100, 3)
    record = json.loads(capsys.readouterr().out)
    assert record["scope"] == "abstract only"
    assert any(c.startswith("Abstract only") for c in record["caveats"])


# ================================================================ sources folder (LibreOffice-made PDFs)
@pytest.fixture(scope="module")
def source_pdfs(tmp_path_factory):
    soffice = shutil.which("soffice") or "/usr/bin/soffice"
    if not Path(soffice).exists():
        pytest.skip("LibreOffice (soffice) is not installed")
    import docx

    base = tmp_path_factory.mktemp("sources_docx")
    docs = {
        "download (3)": [
            ["The Power of Suggestion: Inertia in 401(k) Participation and Savings Behavior",
             "Brigitte C. Madrian and Dennis F. Shea", "Quarterly Journal of Economics, 2001"],
            ["We find that automatic enrollment raised participation among new hires.",
             "Inertia keeps most participants at the default contribution rate."],
            ["Employees procrastinate in changing their contribution rate."]],
        "scan_0042": [
            ["Prospect Theory: An Analysis of Decision under Risk", "Daniel Kahneman and Amos Tversky",
             "Econometrica, doi:10.2307/1914185"],
            ["The value function is steeper for losses than for gains."]],
        "notes": [["A Field Study of Commuting Choices", "Jane Doe", "doi:10.9999/commute.2020"],
                  ["Nothing here concerns the cited works."]],
    }
    for name, pages in docs.items():
        document = docx.Document()
        for i, page in enumerate(pages):
            if i:
                document.add_page_break()
            for paragraph in page + FILLER:
                document.add_paragraph(paragraph)
        document.save(str(base / f"{name}.docx"))
    out = base / "pdf"
    out.mkdir()
    cmd = [soffice, "--headless", "--norestore", f"-env:UserInstallation={(base / 'lo_profile').as_uri()}",
           "--convert-to", "pdf", "--outdir", str(out)] + [str(base / f"{name}.docx") for name in docs]
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if len(list(out.glob("*.pdf"))) != len(docs):
        pytest.skip(f"soffice could not convert the test documents: {proc.stderr[-300:]!r}")
    return out


def test_sources_folder_pdfs_are_matched_by_doi_or_title(work_copy, source_pdfs, capsys):
    assert prep.prepare(work_copy, sources=str(source_pdfs), offline=True) == 0
    pm = PaperMap.load(work_copy / "paper_map.json")
    madrian, kt, brown = (pm.reference(k).id for k in ("madrian2001", "kahneman1979", "brown2015"))
    out = work_copy / "citations"
    status = json.loads((out / "status.json").read_text())
    folder = status["sources_folder"]
    assert folder["matched"] == {madrian: "download (3).pdf", kt: "scan_0042.pdf"}   # file names do not matter
    assert [u["file"] for u in folder["unmatched_pdfs"]] == ["notes.pdf"]
    # brown2015 carries Kahneman and Tversky's DOI: the PDF is not given to it, and the mismatch is reported
    assert any(brown in w and "DOI" in w for w in folder["warnings"])
    meta = json.loads((out / "sources" / f"{madrian}.json").read_text())
    assert meta["status"] == "full_text" and meta["source"] == "sources" and meta["pages"] == 3
    assert meta["version"] == "published" and meta["abstract_only"] is False
    assert meta["sources_match"]["basis"].startswith("title")
    text = (out / "sources" / f"{madrian}.txt").read_text()
    assert text.startswith("[[page 1]]\n") and "[[page 2]]" in text and "[[page 3]]" in text
    assert find_quote("automatic enrollment raised participation among new hires", text)
    assert scanmod.scan(text, ["procrastinat*"])["terms"][0]["pages"] == [3]
    kt_meta = json.loads((out / "sources" / f"{kt}.json").read_text())
    assert kt_meta["sources_match"]["basis"] == "DOI and title"
    assert json.loads((out / "sources" / f"{brown}.json").read_text())["status"] == "not_found"
    # a second run takes the folder from the settings saved at ingest, and reuses the extraction
    capsys.readouterr()
    from paper_check.config import PaperSettings

    if hasattr(PaperSettings, "save"):
        PaperSettings(sources=str(source_pdfs)).save(work_copy)
        prep.prepare(work_copy, offline=True)
    else:
        prep.prepare(work_copy, sources=str(source_pdfs), offline=True)
    items = {i["ref"]: i for i in json.loads((out / "status.json").read_text())["items"]}
    assert items[madrian]["reused"] is True


# ================================================================ cascade with recorded responses
def _transport(routes):
    calls = []

    def transport(url, headers, timeout, max_bytes):
        clean = fulltext.strip_secrets(url)
        calls.append((clean, dict(headers)))
        if clean in routes:
            status, ctype, body, extra = (routes[clean] + ({},))[:4]
            return status, {"content-type": ctype, **extra}, body, url
        return 404, {"content-type": "application/json"}, b'{"error": "not found"}', url

    transport.calls = calls
    return transport


def test_cascade_with_recorded_responses(latex_map, tmp_path):
    pm, _ = latex_map
    laibson, brown, madrian = (pm.reference(k) for k in ("laibson1997", "brown2015", "madrian2001"))
    pdf = make_pdf([["Golden Eggs and Hyperbolic Discounting", "David Laibson", "Harvard University"] + FILLER,
                    ["Hyperbolic discount functions induce dynamically inconsistent preferences."] + FILLER])
    dash = "https://dash.harvard.edu/bitstream/1/4481499/2/Laibson_GoldenEggs.pdf"
    routes = {
        "https://api.openalex.org/works/doi:10.1162/003355397555253":
            (200, "application/json", (RECORDED / "openalex_doi_laibson1997.json").read_bytes()),
        "https://api.openalex.org/works/doi:10.2307/1914185":
            (200, "application/json", (RECORDED / "openalex_doi_10.2307_1914185.json").read_bytes()),
        "https://api.openalex.org/works/doi:10.1162/003355301753265543":
            (200, "application/json", (RECORDED / "openalex_doi_madrian2001.json").read_bytes()),
        dash: (200, "application/pdf", pdf),
    }
    transport = _transport(routes)
    fetcher = Fetcher(tmp_path / "cache", email="tests@example.org", transport=transport, sleep=lambda s: None)
    cascade = Cascade(fetcher, tmp_path / "sources", email="tests@example.org", openalex_key="KEY-FOR-TESTS")

    meta = cascade.run(laibson)  # OpenAlex's best open-access location
    assert meta["status"] == "full_text" and meta["source"] == "openalex" and meta["url"] == dash
    assert meta["version"] == "submitted" and meta["pages"] == 2 and meta["abstract_only"] is False
    assert meta["license"] == "cc-by" and meta["fetched"]
    text = (tmp_path / "sources" / f"{laibson.id}.txt").read_text()
    assert text.startswith("[[page 1]]\nGolden Eggs and Hyperbolic Discounting") and "[[page 2]]" in text
    assert (tmp_path / "sources" / f"{laibson.id}.pdf").read_bytes() == pdf

    meta = cascade.run(brown)  # its DOI belongs to Kahneman and Tversky (1979)
    assert meta["status"] == "not_found" and meta["note"] == "cannot verify: no full text"
    assert any("belongs to a different work" in w for w in meta["warnings"])
    assert not any("unpaywall" in url and "1914185" in url for url, _ in transport.calls)

    meta = cascade.run(madrian)  # closed access: the abstract alone
    assert meta["status"] == "abstract_only" and meta["version"] == "abstract" and meta["abstract_only"] is True
    assert (tmp_path / "sources" / f"{madrian.id}.txt").read_text().startswith("[[abstract]]\nSynthetic abstract")

    # identity: the contact email goes only to scholarly APIs, and no key or email reaches the cache or metadata
    for url, headers in transport.calls:
        if "tests@example.org" in headers["User-Agent"]:
            assert url.split("/")[2] in fulltext.API_HOSTS
    for path in (tmp_path).rglob("*"):
        if path.is_file() and path.suffix in (".json", ".txt"):
            assert "KEY-FOR-TESTS" not in path.read_text(errors="replace")


def test_wrong_pdfs_challenges_and_rate_limits_are_not_used(latex_map, tmp_path):
    pm, _ = latex_map
    laibson = pm.reference("laibson1997")
    record = (RECORDED / "openalex_doi_laibson1997.json").read_bytes()
    oa = "https://api.openalex.org/works/doi:10.1162/003355397555253"
    dash = "https://dash.harvard.edu/bitstream/1/4481499/2/Laibson_GoldenEggs.pdf"
    cases = {
        "wrong work": (200, "application/pdf", make_pdf([["Fisheries Management in the Baltic Sea", "A. Nother"] + FILLER,
                                                         ["Cod stocks and quotas."] + FILLER])),
        "challenge": (403, "text/html", b"<html><head><title>Just a moment...</title></head><body>cf-chl</body></html>"),
        "rate limit": (429, "text/plain", b"", {"retry-after": "900"}),
    }
    outcomes = {}
    for name, answer in cases.items():
        transport = _transport({oa: (200, "application/json", record), dash: answer})
        cascade = Cascade(Fetcher(tmp_path / name / "cache", transport=transport, sleep=lambda s: None),
                          tmp_path / name / "sources")
        meta = cascade.run(laibson)
        assert meta["status"] != "full_text"
        outcomes[name] = (meta, [a["outcome"] for a in meta["attempts"] if a.get("url") == dash], transport.calls)
    assert outcomes["wrong work"][1][0].startswith("PDF rejected")
    assert outcomes["challenge"][1][0] == "blocked by bot protection (not bypassed)"
    meta, attempts, calls = outcomes["rate limit"]
    assert "asks to wait 900 s" in attempts[0] and meta["transient_failure"] is True
    assert sum(1 for url, _ in calls if url == dash) == 1   # no retries against a long Retry-After


def test_fetcher_caches_and_works_offline(tmp_path):
    transport = _transport({"https://api.openalex.org/works/W1": (200, "application/json", b'{"id": "W1"}')})
    fetcher = Fetcher(tmp_path, transport=transport, sleep=lambda s: None)
    assert fetcher.get("https://api.openalex.org/works/W1?api_key=SECRET").json() == {"id": "W1"}
    again = fetcher.get("https://api.openalex.org/works/W1")  # same cache key without the secret
    assert again.from_cache and len(transport.calls) == 1
    offline = Fetcher(tmp_path, offline=True)
    assert offline.get("https://api.openalex.org/works/W1").json() == {"id": "W1"}
    assert offline.get("https://api.openalex.org/works/W2").status is None
    assert not any("SECRET" in p.read_text(errors="replace") for p in tmp_path.rglob("*.json"))


def test_an_unreachable_host_is_left_alone_after_two_failures(tmp_path):
    calls = []

    def down(url, headers, timeout, max_bytes):
        calls.append(url)
        raise OSError("Name or service not known")

    fetcher = Fetcher(tmp_path, transport=down, sleep=lambda s: None)
    for n in range(4):
        response = fetcher.get(f"https://down.example/paper{n}.pdf")
        assert response.status is None and response.transient
    assert len(calls) == 4   # two calls, each tried twice; the next two never reach the network
    assert "unreachable earlier in this run" in response.error


def test_identifiers_from_reference_fields():
    assert fulltext.nber_numbers({"doi": "10.3386/w7682"}) == ["7682"]
    assert fulltext.nber_numbers({"number": "w10819", "container": "NBER Working Paper"}) == ["10819"]
    assert fulltext.nber_numbers({"number": "12", "container": "Journal of Things"}) == []
    assert fulltext.arxiv_ids({"url": "https://arxiv.org/abs/1710.02926v4"}) == ["1710.02926"]
    assert fulltext.arxiv_ids({"note": "arXiv:2101.00001"}) == ["2101.00001"]
    assert fulltext.norm_doi("https://doi.org/10.1257/AER.96.3.694.") == "10.1257/aer.96.3.694"


# ================================================================ STW thesaurus
@pytest.fixture(scope="module")
def sample_thesaurus():
    thesaurus, note = terms.Thesaurus.load(source=FIX / "stw_sample.nt")
    assert thesaurus is not None, note
    return thesaurus


def _rel(result):
    return {(t["term"], t["relation"]) for t in result["terms"]}


def test_stw_expansion_keeps_each_relation(sample_thesaurus):
    r = terms.expand("hyperbolic discounting", thesaurus=sample_thesaurus, use_glossary=False)
    assert {("Time consistency", "synonym"), ("Time inconsistency", "synonym"),
            ("Quasi-hyperbolic discounting", "narrower"), ("Intertemporal choice", "broader"),
            ("Discounting", "related"), ("V.99 Test category", "category")} <= _rel(r)
    assert r["matches"][0]["match"] == "exact (alt)"
    assert r["attribution"].startswith("Thesaurus terms from the STW Thesaurus for Economics v0.1-test (2026-01-01)")
    assert "CC BY 4.0" in r["attribution"]
    # a narrower entry term: its descriptor is broader
    r = terms.expand("quasi-hyperbolic discounting", thesaurus=sample_thesaurus, use_glossary=False)
    assert ("Time consistency", "broader") in _rel(r)
    # a related entry term, a deprecated concept, and a partial match
    assert ("Prospect theory", "related") in _rel(terms.expand("framing effect", thesaurus=sample_thesaurus, use_glossary=False))
    r = terms.expand("old discount concept", thesaurus=sample_thesaurus, use_glossary=False)
    assert ("Discount factor", "synonym") in _rel(r) and any("deprecated" in n for n in r["notes"])
    r = terms.expand("loss aversion", thesaurus=sample_thesaurus, use_glossary=False)
    assert ("Prospect theory", "related") in _rel(r) and not any(t["relation"] == "synonym" for t in r["terms"])
    assert sample_thesaurus.label("descriptor/90006-6", "de") == "Verhaltensökonomik"
    assert terms.expand("behavioural economics", thesaurus=sample_thesaurus)["matches"]


def test_glossary_gives_models_and_symbols_for_present_bias(sample_thesaurus):
    r = terms.expand("present bias", thesaurus=sample_thesaurus)
    rel = _rel(r)
    assert {("quasi-hyperbolic discounting", "model"), ("β", "symbol"), ("hyperbolic discounting", "related"),
            ("present-biased", "synonym")} <= rel
    assert all(t["relation"] != "synonym" or t["source"] != "STW" for t in r["terms"])


def test_stw_is_parsed_from_the_cached_zip_once(tmp_path, monkeypatch):
    monkeypatch.setattr(terms, "MIN_CONCEPTS", 1)
    with zipfile.ZipFile(tmp_path / "stw.nt.zip", "w") as zf:
        zf.write(FIX / "stw_sample.nt", "stw.nt")
    data, note = terms.ensure_stw(cache_dir=tmp_path, offline=True)
    assert data and note == "STW parsed from the cached download"
    assert json.loads((tmp_path / "stw_meta.json").read_text())["version"] == "0.1-test"
    data, note = terms.ensure_stw(cache_dir=tmp_path, offline=True)
    assert note == "STW read from the cache"


def test_stw_unavailable_degrades_to_the_glossary(tmp_path):
    r = terms.expand("present bias", offline=True, cache_dir=tmp_path / "no-cache")
    assert r["sources"]["stw"]["available"] is False and r["attribution"] is None
    assert any("STW thesaurus unavailable" in n for n in r["notes"])
    assert ("β", "symbol") in _rel(r)


# ================================================================ network
def _mini_work(tmp_path, fields, sentence, citation_text):
    text = f"{sentence} {citation_text}."
    start = text.index(citation_text)
    block = Block(id="b0001", kind="paragraph", text=text, anchor=Anchor(file="main.tex", line=1),
                  section=["1 Introduction"], sentences=[Sentence(id="b0001.s1", start=0, end=len(text))],
                  citations=[Citation(keys=["ref1"], start=start, end=start + len(citation_text),
                                      command="citep", raw="\\citep{ref1}")])
    ref = Reference(id="r001", raw=fields["title"], anchor=Anchor(file="refs.bib", line=1), source="bibtex",
                    key="ref1", fields=fields)
    pm = PaperMap(source={"path": str(tmp_path), "paper_dir": str(tmp_path), "format": "latex"},
                  blocks=[block], references=[ref])
    work = tmp_path / "paper-check-work"
    work.mkdir()
    pm.save(work / "paper_map.json")
    return work, ref


@pytest.mark.network
def test_network_fetches_an_open_access_econ_paper_end_to_end(tmp_path, capsys):
    fields = {"title": "When Should You Adjust Standard Errors for Clustering?", "year": "2017",
              "authors": [{"family": "Abadie", "given": "Alberto"}, {"family": "Athey", "given": "Susan"},
                          {"family": "Imbens", "given": "Guido W."}, {"family": "Wooldridge", "given": "Jeffrey M."}],
              "url": "https://arxiv.org/abs/1710.02926", "type": "article"}
    work, ref = _mini_work(tmp_path, fields, "Clustered standard errors are often conservative",
                           "(Abadie, Athey, Imbens and Wooldridge, 2017)")
    assert prep.prepare(work) == 0
    capsys.readouterr()
    meta = json.loads((work / "citations" / "sources" / "r001.json").read_text())
    assert meta["status"] == "full_text", meta["attempts"]
    assert meta["version"] in ("submitted", "accepted", "published") and meta["pages"] >= 20
    assert meta["url"] and meta["fetched"]
    text = (work / "citations" / "sources" / "r001.txt").read_text()
    assert text.startswith("[[page 1]]") and "[[page 20]]" in text
    assert scanmod.scan_command(work, "r001", ["cluster*", "gym attendance"], 200, 3) == 0
    record = json.loads(capsys.readouterr().out)
    hits = {e["term"]: e["hits"] for e in record["terms"]}
    assert hits["cluster*"] > 20 and hits["gym attendance"] == 0
    # the arXiv step alone, as the last open-access resort
    cascade = Cascade(Fetcher(work / "citations" / "cache"), tmp_path / "arxiv_only")
    meta = cascade.run(ref, steps=["arxiv"])
    assert meta["status"] == "full_text" and meta["source"] == "arxiv" and meta["version"] == "submitted"


@pytest.mark.network
def test_network_downloads_stw_once(tmp_path):
    thesaurus, note = terms.Thesaurus.load(cache_dir=tmp_path)
    assert thesaurus is not None, note
    r = terms.expand("hyperbolic discounting", thesaurus=thesaurus, use_glossary=False)
    assert any(t["relation"] == "synonym" for t in r["terms"])
    assert "STW Thesaurus for Economics" in r["attribution"]
    assert "CC BY" in r["attribution"] or "ODbL" in r["attribution"]
    again, note = terms.Thesaurus.load(cache_dir=tmp_path, offline=True)
    assert again is not None and note == "STW read from the cache"


def test_a_stem_without_its_star_is_not_recorded_as_absent():
    result = scanmod.scan(SYNTH, ["procrastinat", "gymnas", "gym attendance", "re:zzz"])
    t = {e["term"]: e for e in result["terms"]}
    assert t["procrastinat"]["hits"] == 0
    assert t["procrastinat"]["inside_longer_words"]["hits"] == 1
    assert "procrastinat*" in t["procrastinat"]["warning"]
    assert t["gymnas"]["inside_longer_words"]["forms"] == {"gymnasium": 1}
    assert "inside_longer_words" not in t["gym attendance"] and "inside_longer_words" not in t["re:zzz"]
    assert result["terms_without_hits"] == ["gym attendance", "re:zzz"]
    assert result["terms_only_inside_longer_words"] == ["procrastinat", "gymnas"]


# ================================================================ the URL printed in a reference entry
def _ref(rid, raw, fields):
    return Reference(id=rid, raw=raw, anchor=Anchor(), source="text", key=rid, fields=fields)


NEWS_HTML = (b"<html><head><title>City adopts a new transit plan for its outer districts | Example News"
             b"</title><script>var x = 1;</script></head><body><nav>Home About Donate</nav><article>"
             b"<h1>City adopts a new transit plan for its outer districts</h1><p>By Jane Roe</p>"
             + b"".join(b"<p>The transit office estimated that average commuting time was 48 minutes last year, "
                        b"and bus ridership rose sharply after the new routes opened. </p>" for _ in range(12))
             + b"</article><footer>Copyright</footer></body></html>")


def test_a_news_page_in_the_entry_is_read_as_the_full_text(tmp_path):
    url = "https://news.example.org/2020/12/02/transit-plan"
    ref = _ref("r027", f"Roe, J. (2020, December 2). City adopts a new transit plan for its outer districts. "
                       f"Example News. {url}",
               {"title": "City adopts a new transit plan for its outer districts", "year": "2020",
                "authors": [{"family": "Roe", "given": "Jane"}], "type": "post-weblog", "url": url})
    transport = _transport({url: (200, "text/html; charset=utf-8", NEWS_HTML)})
    cascade = Cascade(Fetcher(tmp_path / "cache", transport=transport, sleep=lambda s: None), tmp_path / "sources")
    meta = cascade.run(ref)
    assert meta["status"] == "full_text" and meta["source"] == "entry_url" and meta["web_page"] is True
    text = (tmp_path / "sources" / "r027.txt").read_text()
    assert text.startswith("[[text]]\nCity adopts a new transit plan") and "48 minutes last year" in text
    assert "var x" not in text and "Donate" not in text and "Copyright" not in text
    result = scanmod.scan(text, ["48 minutes", "median*"])
    assert result["terms"][0]["hits"] == 12 and result["terms"][1]["hits"] == 0


def test_a_journal_landing_page_is_not_read_as_the_article(tmp_path):
    url = "https://www.journal.example.org/article/credit-access-and-spending"
    landing = (b"<html><head><title>Credit access and household spending</title></head><body><article>"
               + b"<p>Abstract. We study credit access and household spending in many states. </p>" * 30
               + b"<a href='/content/credit.pdf'>Download PDF</a></article></body></html>")
    ref = _ref("r010", f"Doe, J. (2018). Credit access and household spending. Journal of Tests, 76, 40-54. "
                       f"https://doi.org/10.1016/j.x.2018.01.001 {url}",
               {"title": "Credit access and household spending", "year": "2018", "type": "article-journal",
                "authors": [{"family": "Doe", "given": "J."}], "doi": "10.1016/j.x.2018.01.001", "volume": "76"})
    transport = _transport({url: (200, "text/html", landing)})
    cascade = Cascade(Fetcher(tmp_path / "cache", transport=transport, sleep=lambda s: None), tmp_path / "sources",
                      offline=False)
    meta = cascade.run(ref, steps=["entry_url"])
    assert meta["status"] == "not_found"
    outcomes = [a["outcome"] for a in meta["attempts"] if a["step"] == "entry_url"]
    assert any(o.startswith("web page; trying the 1 PDF") for o in outcomes)
    assert not any("doi.org" in u for u, _ in transport.calls)


def test_a_page_with_another_title_is_rejected(tmp_path):
    url = "https://news.example.org/story"
    ref = _ref("r018", f"Poe, D. (2019). Changes in state transit law create new commuting options. Example Radio. {url}",
               {"title": "Changes in state transit law create new commuting options", "year": "2019",
                "type": "post-weblog", "authors": [{"family": "Poe", "given": "D."}], "url": url})
    other = b"<html><head><title>Weather today</title></head><body>" + b"<p>Rain and wind all day long.</p>" * 60 + b"</body></html>"
    transport = _transport({url: (200, "text/html", other)})
    meta = Cascade(Fetcher(tmp_path / "cache", transport=transport, sleep=lambda s: None),
                   tmp_path / "sources").run(ref, steps=["entry_url"])
    assert meta["status"] == "not_found"
    assert any(a["outcome"].startswith("page rejected") for a in meta["attempts"])


def test_web_check_pages_feed_the_cascade(tmp_path):
    work = tmp_path / "w"
    (work / "references").mkdir(parents=True)
    rows = [{"ref": "r006", "dedicated_page": "https://www.example.org/report.pdf", "outcome": "exists, not indexed"},
            {"ref": "r044", "dedicated_page": None, "outcome": "likely non-existent"},
            {"ref": "r045", "dedicated_page": "https://x.example/p", "outcome": "unverified"}]
    (work / "references" / "web_checks_1.json").write_text(json.dumps(rows))
    assert prep._web_pages(work) == {"r006": ["https://www.example.org/report.pdf"]}
    prev = {"status": "not_found", "attempts": [{"step": "openalex", "outcome": "no match"}], "fetched_at":
            dt.datetime.now(dt.timezone.utc).isoformat()}
    assert prep._reusable(prev, None, False, ["https://www.example.org/report.pdf"]) is False
    assert prep._reusable(prev, None, False, []) is True


def test_a_report_page_gives_its_full_report_not_the_summary(tmp_path):
    page = "https://www.agency.example.gov/publications/123"
    title = "Measuring Household Food Purchases with Retail Scanner Data"
    summary_pdf = make_pdf([[title, "Report summary"] + FILLER] * 2)
    full_pdf = make_pdf([[title, "Ann Example"] + FILLER] * 5)
    landing = (b"<html><head><title>Measuring Household Food Purchases</title></head><body>"
               b"<a href='/media/7545/tb-123-report-summary.pdf'>Download the report summary (PDF)</a>"
               b"<a href='/media/7544/tb-123.pdf'>Download the full report (PDF)</a></body></html>")
    routes = {page: (200, "text/html", landing),
              "https://www.agency.example.gov/media/7545/tb-123-report-summary.pdf": (200, "application/pdf", summary_pdf),
              "https://www.agency.example.gov/media/7544/tb-123.pdf": (200, "application/pdf", full_pdf)}
    ref = _ref("r008", f"Example, A. et al. (2019). {title} (TB-123). Example Agency. {page}",
               {"title": title, "year": "2019", "type": "report", "authors": [{"family": "Example", "given": "Ann"}],
                "url": page})
    meta = Cascade(Fetcher(tmp_path / "cache", transport=_transport(routes), sleep=lambda s: None),
                   tmp_path / "sources").run(ref, steps=["entry_url"])
    assert meta["status"] == "full_text" and meta["pages"] == 5 and meta["url"].endswith("tb-123.pdf")


def test_a_report_on_a_newsroom_page_is_read_from_its_html(tmp_path):
    url = "https://newsroom.example.com/news-releases/2026/money-study"
    title = "Example Bank 2026 Money Study Finds Savers Are Rethinking Their Goals"
    page = (f"<html><head><title>{title}</title></head><body><article><h1>{title}</h1>".encode()
            + b"<p>The survey of 3,000 adults found that many savers changed their goals this year. </p>" * 20
            + b"</article></body></html>")
    ref = _ref("r054", f"Example Bank (2026) {title}. Available at: {url}",
               {"title": title, "year": "2026", "type": "report", "url": url})
    meta = Cascade(Fetcher(tmp_path / "cache", transport=_transport({url: (200, "text/html", page)}),
                           sleep=lambda s: None), tmp_path / "sources").run(ref, steps=["entry_url"])
    assert meta["status"] == "full_text" and meta["web_page"] is True
